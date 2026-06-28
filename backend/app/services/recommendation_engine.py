import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func as sa_func
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.integrations import google_books, llm, openlibrary, qdrant, tavily
from app.logging import log_entry_exit
from app.models.authors import Person
from app.models.books import Work
from app.models.enrichment import EnrichmentCache
from app.models.events import EventType, InteractionEvent
from app.models.recommendations import (
    RecommendationLog,
    RecommendationSource,
    RecommendationStatus,
)
from app.models.tbr import TBREntry, TBRStatus
from app.models.users import UserProfile
from app.schemas.recommendations import (
    AuthorSpotlight,
    AuthorSpotlightBook,
    RecommendationResponse,
    RecommendedItem,
    WorkResponse,
)
from app.schemas.users import Tower1Profile
from app.services import exploration_service, query_engine, reranker, user_intelligence
from app.services.enrichment_service import (
    _parse_date,
    _resolve_work_and_cache,
    _run_google_books,
)
from app.services.series_resolver import resolve_series_from_query
from app.workers.enrichment_tasks import enrich_book_task

logger = logging.getLogger(__name__)

# ── Import ThreadPoolExecutor for parallel LLM calls ──
from concurrent.futures import ThreadPoolExecutor, as_completed


@log_entry_exit()
def generate_recommendations(
    db: Session, user_uuid: str, raw_query: str, session_id: str
) -> RecommendationResponse:
    logger.info(
        f"Starting recommendation pipeline for user {user_uuid}. Session: {session_id}"
    )
    _verify_no_blocking_checkpoints(db, user_uuid)

    # Ensure user profile exists (new users from real auth have none)
    user_intelligence.initialize_user_profile(db, user_uuid)

    # ── Parallel: Series detection + Query engine ──
    # These are independent LLM calls. Running them concurrently
    # cuts pipeline latency from ~13s to ~8s.
    series_ctx = None
    _series_tropes = None
    query_type_from_series = None
    expanded_query = raw_query
    mood_tags_delta = {}
    query_trope_names: List[str] = []
    anchor_author: Optional[str] = None
    query_intent = "discovery"

    def _run_series():
        return resolve_series_from_query(db, raw_query)

    def _run_query():
        return query_engine.process_reader_query(db, user_uuid, raw_query)

    with ThreadPoolExecutor(max_workers=2) as pool:
        future_series = pool.submit(_run_series)
        future_query = pool.submit(_run_query)

        # Process series result (usually finishes first)
        series_ctx = future_series.result()
        if series_ctx:
            logger.info(
                f"Series detected: {series_ctx.series_title} "
                f"({series_ctx.book_count} books, source={series_ctx.source})"
            )
            if series_ctx.aggregated_tropes:
                _series_tropes = [name for name, _ in series_ctx.aggregated_tropes[:8]]
                logger.info(f"Series aggregated tropes: {_series_tropes}")
            query_type_from_series = "similarity"

        # Process query result
        (
            expanded_query,
            mood_tags_delta,
            query_trope_names,
            anchor_author,
            query_intent,
        ) = future_query.result()

    # Intent priority: series detection > query engine intent
    query_type = query_type_from_series or query_intent
    logger.info(
        f"Query intent: {query_type} (series_override={bool(query_type_from_series)})"
    )

    # Merge series tropes into LLM-extracted tropes (series takes priority)
    if _series_tropes:
        _existing = set(query_trope_names)
        query_trope_names = (
            _series_tropes
            + [t for t in query_trope_names if t not in set(_series_tropes)]
        )[:8]
        _t1_str = " ".join(
            f"{k.replace('_', ' ')} {v:.1f}"
            for k, v in (series_ctx.aggregated_tower1 or {}).items()
            if v >= 0.5
        )
        _prefix = (
            f"Books similar to the {series_ctx.series_title} series by "
            f"{series_ctx.author_name}. Core tropes: {', '.join(_series_tropes[:6])}. "
            f"Profile: {_t1_str}. "
        )
        expanded_query = _prefix + expanded_query
        logger.info(f"Series-augmented query: {expanded_query[:200]}...")
    elif series_ctx and series_ctx.series_description:
        # No canonical tropes matched, but we have a rich natural-language
        # vibe description from Tavily. Inject it for vector search.
        _vibe_prefix = (
            f"Books similar to the {series_ctx.series_title} series by "
            f"{series_ctx.author_name}. Series vibe: {series_ctx.series_description}. "
        )
        expanded_query = _vibe_prefix + expanded_query
        logger.info(f"Series vibe-augmented query: {expanded_query[:250]}...")
    logger.info(f"Query tropes extracted: {query_trope_names}")
    logger.info(f"Anchor author detected: {anchor_author}")

    # Tavily fallback: when the LLM had no trope/author context (bare title queries
    # like "books like play along"), search for the anchor title to recover both.
    if query_type == "similarity" and (not query_trope_names or not anchor_author):
        enriched = _tavily_enrich_similarity_context(
            raw_query, query_trope_names, anchor_author
        )
        if enriched:
            new_tropes, new_author = enriched
            if new_tropes and not query_trope_names:
                query_trope_names = new_tropes
                logger.info(f"Tavily enriched tropes: {query_trope_names}")
            if new_author and not anchor_author:
                anchor_author = new_author
                logger.info(f"Tavily enriched author: {anchor_author}")

    db_profile = db.execute(
        select(UserProfile).where(UserProfile.user_uuid == user_uuid)
    ).scalar_one()
    tower1_profile = Tower1Profile.model_validate(db_profile)

    # Compute IDF weights once per request — used for query-trope scoring
    idf_weights = reranker.compute_trope_idf(db)

    candidates: List[reranker.CandidateContext] = []
    seen: set = set()
    anchor_defining_tropes: List[str] = []  # confidence-1.0 tropes from anchor book

    # Part 0: Exclude series books from results — user already read them.
    # For DB-resolved series, work_uuids are definitive. For Tavily-resolved
    # series, search local DB for works matching the resolved book titles.
    if series_ctx:
        if series_ctx.work_uuids:
            for _wid in series_ctx.work_uuids:
                seen.add(_wid)
            logger.info(
                f"Excluded {len(series_ctx.work_uuids)} series books from results"
            )
        elif series_ctx.source == "tavily" and series_ctx.book_titles:
            from sqlalchemy import func as _sf

            for _title in series_ctx.book_titles:
                _match = db.execute(
                    select(Work.work_uuid).where(
                        _sf.lower(Work.title) == _title.lower()
                    )
                ).scalar_one_or_none()
                if _match:
                    seen.add(str(_match))
            logger.info(f"Tavily series exclusion: matched {len(seen)} works by title")

    # Part 1: Seed `seen` with ALL active TBR work_uuids before any candidate pulling.
    # TBR books are conceptually separate from recommendations (reading queue vs discovery).
    # They are returned in tbr_matches, a separate strip, not mixed into the main list.
    _tbr_uuids: set = set()
    _tbr_rows = (
        db.execute(
            select(TBREntry.work_uuid)
            .where(TBREntry.user_uuid == user_uuid)
            .where(TBREntry.status == TBRStatus.ACTIVE)
        )
        .scalars()
        .all()
    )
    for _wu in _tbr_rows:
        _tbr_uuids.add(str(_wu))
        seen.add(str(_wu))

    # Similarity anchor resolution:
    # 1. Exclude the anchor book from its own results (seed `seen`).
    # 2. When the anchor is fully enriched in our DB, use its actual tropes and
    #    Tower1 profile to augment both query_trope_names and expanded_query.
    #
    # Why this matters: "books like God of Fury" expands to generic dark romance
    # vocabulary and embeds in the mafia/dark cluster in Qdrant. Heated Rivalry,
    # Captive Prince, etc. never surface because they embed differently (sports,
    # fantasy). The anchor book's DB tropes are the authoritative signal — MM Romance
    # at confidence 1.0 should drive both the Qdrant search direction and the
    # zero-overlap gate that suppresses non-MM dark romance books.
    if query_type == "similarity":
        import re as _re

        _title_match = _re.search(
            r"(?:like|similar to|reminiscent of|more like|in the style of)\s+(.+?)(?:\s+by\s+|$)",
            raw_query.strip(),
            _re.IGNORECASE,
        )
        if _title_match:
            _anchor_title = _title_match.group(1).strip().strip("\"'")
            if _anchor_title and len(_anchor_title) >= 3:
                from sqlalchemy import func as _sf

                _anchor_work = (
                    db.execute(
                        select(Work).where(
                            _sf.lower(Work.title) == _anchor_title.lower()
                        )
                    )
                    .scalars()
                    .first()
                )
                if _anchor_work:
                    seen.add(str(_anchor_work.work_uuid))
                    logger.info(
                        f"Anchor exclusion: seeded seen with '{_anchor_work.title}' "
                        f"({_anchor_work.work_uuid})"
                    )

                    # Load anchor book tropes if fully enriched — use as authoritative
                    # query signal rather than relying on the LLM's title-text guess.
                    if _anchor_work.enrichment_status == "complete":
                        from app.models.tropes import BookTrope as _BT
                        from app.models.tropes import Trope as _Trope

                        _anchor_trope_rows = db.execute(
                            select(_Trope.canonical_name, _BT.confidence_score)
                            .join(_BT, _BT.trope_uuid == _Trope.trope_uuid)
                            .where(_BT.work_uuid == _anchor_work.work_uuid)
                            .where(_BT.confidence_score >= 0.5)
                            .order_by(_BT.confidence_score.desc())
                        ).all()

                        _anchor_trope_names = [name for name, _ in _anchor_trope_rows]

                        # Confidence-1.0 only — the book's identity-level descriptors.
                        # Passed to rank_candidates as anchor_defining_tropes.
                        anchor_defining_tropes = [
                            name for name, score in _anchor_trope_rows if score == 1.0
                        ]
                        if anchor_defining_tropes:
                            logger.info(
                                f"Anchor defining tropes (conf=1.0): {anchor_defining_tropes}"
                            )

                        if _anchor_trope_names:
                            # Merge: anchor tropes take priority, then fill with LLM
                            # tropes not already present (up to 8 total)
                            _merged = list(
                                dict.fromkeys(
                                    _anchor_trope_names
                                    + [
                                        t
                                        for t in query_trope_names
                                        if t not in set(_anchor_trope_names)
                                    ]
                                )
                            )[:8]
                            if _merged != query_trope_names:
                                logger.info(
                                    f"Anchor trope augmentation: {query_trope_names} → {_merged}"
                                )
                                query_trope_names = _merged

                        # Augment expanded_query with anchor's actual trope + Tower1 data
                        # so the Qdrant embedding lands in the right neighbourhood.
                        _anchor_cache = db.execute(
                            select(EnrichmentCache).where(
                                EnrichmentCache.work_uuid == _anchor_work.work_uuid
                            )
                        ).scalar_one_or_none()

                        if _anchor_cache and _anchor_trope_names:
                            _trope_str = ", ".join(_anchor_trope_names[:6])
                            _t1 = _anchor_cache.tower1_snapshot or {}
                            _t1_str = " ".join(
                                f"{k.replace('_', ' ')} {v:.1f}"
                                for k, v in _t1.items()
                                if isinstance(v, float) and v >= 0.6
                            )
                            _anchor_prefix = (
                                f"{_anchor_work.title} core tropes: {_trope_str}. "
                                f"Defining qualities: {_t1_str}. "
                            )
                            expanded_query = _anchor_prefix + expanded_query
                            logger.info(
                                f"Anchor query augmentation prepended for '{_anchor_work.title}'"
                            )

    # TBR books are excluded from the main candidate pool (seeded into `seen` above).
    # They surface via _build_tbr_matches() after ranking, as a separate strip.

    # Route by query type — pass anchor_author for lookup to use directly
    if query_type == "lookup":
        _handle_lookup_query(db, expanded_query, candidates, seen, anchor_author)
    elif query_type == "similarity":
        _handle_similarity_query(db, expanded_query, candidates, seen)
    elif query_type == "departure":
        # User wants something DIFFERENT from the reference point.
        # Route to discovery — the series tropes act as negative signal.
        # If a series was resolved, mark its aggregated tropes for downranking.
        if series_ctx and series_ctx.aggregated_tropes:
            _departure_tropes = [name for name, _ in series_ctx.aggregated_tropes[:6]]
            logger.info(f"Departure: downranking tropes {_departure_tropes}")
            # Map departure tropes to negative IDF weights for reranker
            _departure_idf = {
                t: -idf_weights.get(t, 0.5) * 2 for t in _departure_tropes
            }
            idf_weights = {**idf_weights, **_departure_idf}
        _handle_discovery_query(db, expanded_query, candidates, seen)
    else:
        _handle_discovery_query(db, expanded_query, candidates, seen)

    # Batch-load book trope names for all candidates (single DB round-trip)
    _enrich_candidate_tropes(db, candidates)

    # Stamp is_interested for books the user has soft-flagged (single DB round-trip)
    _stamp_interested_candidates(db, user_uuid, candidates)

    # Part 2: Stamp is_in_tbr on candidates that are in TBR via non-TBR path.
    # After Part 1 exclusion this is rare, but possible if a book was added to TBR
    # after the last enrichment cycle. Single set lookup — no extra DB call.
    for _c in candidates:
        if _c.work_uuid in _tbr_uuids:
            _c.is_in_tbr = True

    # Issue 5 fix: populate book_inferred_profile and is_narrative from enrichment cache.
    # Previously every candidate had book_inferred_profile={}, causing Tower1 to return
    # the 0.5 neutral fallback for every book. is_narrative was also never read.
    _enrich_candidate_metadata(db, candidates)

    # FR-PH: Detect reader phase for genre sprint boost + exploration tuning
    reader_phase = user_intelligence.detect_reader_phase(db, user_uuid)

    # FR-EX: Exploration Loop — surface book outside reader's taste profile
    _explorer = exploration_service.ExplorationService(db)
    # Comfort phase → reduce exploration (don't interrupt re-reads)
    if reader_phase and reader_phase.get("phase") == "comfort":
        _explorer.EXPLORATION_BASE_RATE = 12  # 1-in-12 instead of 1-in-5
    # Genre sprint → reduce exploration (stay in the sprint)
    elif reader_phase and reader_phase.get("phase") == "genre_sprint":
        _explorer.EXPLORATION_BASE_RATE = 10
    _exploration_candidate = None
    if _explorer.should_explore(uuid.UUID(user_uuid)):
        _exploration_candidate = _explorer.get_exploration_candidate(
            uuid.UUID(user_uuid),
            [uuid.UUID(c.work_uuid) for c in candidates],
        )
        if _exploration_candidate:
            logger.info(
                f"Exploration candidate selected: {_exploration_candidate.title}"
            )

    # FR-QR-07: Temporal reading pattern boost
    _now = datetime.now(timezone.utc)
    _fingerprint = user_intelligence.get_temporal_fingerprint(db, user_uuid)
    _temporal_pref = user_intelligence.get_temporal_slot_preference(
        _fingerprint, _now.hour, _now.weekday()
    )

    ranked_candidates = reranker.rank_candidates(
        candidates,
        tower1_profile,
        idf_weights=idf_weights,
        query_trope_names=query_trope_names,
        anchor_defining_tropes=anchor_defining_tropes or None,
        current_hour=_now.hour,
        day_of_week=_now.weekday(),
        temporal_preference=_temporal_pref,
        reader_phase=reader_phase,
    )

    # Build results with same-author cap and trope-based explanations
    # Lookup queries need a higher cap — showing the author's catalog is the point.
    max_per_author = 10 if query_type == "lookup" else 2
    results = []
    seen_authors: Dict[str, int] = {}
    for candidate in ranked_candidates:
        if len(results) >= 10:
            break
        # Same-author cap
        author_uuid = str(candidate.raw_record.person_uuid)
        if seen_authors.get(author_uuid, 0) >= max_per_author:
            continue
        seen_authors[author_uuid] = seen_authors.get(author_uuid, 0) + 1

        explanation = _build_explanation(
            candidate.book_trope_names,
            query_trope_names,
            candidate.match_source,
            candidate.explanation_factors,
        )

        rank = len(results)
        rec_log = RecommendationLog(
            user_uuid=user_uuid,
            session_id=session_id,
            work_uuid=uuid.UUID(candidate.work_uuid),
            rank_position=rank + 1,
            source=RecommendationSource(candidate.match_source)
            if candidate.match_source in ("tbr", "vector", "llm", "exploration")
            else RecommendationSource.LLM,
            query_text=raw_query,
            status=RecommendationStatus.DELIVERED,
        )
        db.add(rec_log)
        try:
            work_schema = WorkResponse.model_validate(candidate.raw_record)
        except Exception as _e:
            logger.warning(f"Failed to serialize candidate {candidate.work_uuid}: {_e}")
            continue
        results.append(
            RecommendedItem(
                work=work_schema,
                explanation=explanation,
                match_source=candidate.match_source,
                tbr_context_bonus=candidate.is_tbr_context_match,
                is_in_tbr=getattr(candidate, "is_in_tbr", False),
                description=candidate.description,
            )
        )

    # FR-EX: Inject exploration candidate at position 3
    if _exploration_candidate:
        try:
            _expl_schema = WorkResponse.model_validate(_exploration_candidate)
        except Exception as _e:
            logger.warning(f"Failed to serialize exploration candidate: {_e}")
        else:
            _expl_item = RecommendedItem(
                work=_expl_schema,
                explanation="Something outside your usual — see if it surprises you.",
                match_source="exploration",
            )
            _pos = min(3, len(results))
            results.insert(_pos, _expl_item)
            logger.info(
                f"Exploration candidate '{_exploration_candidate.title}' injected at position {_pos}"
            )

    # Author spotlight — DB-only (no Google Books on hot path).
    # Returns catalog entries already in the system. Frontend can load
    # the full spotlight separately via the authors endpoint.
    author_spotlight = None
    if anchor_author and query_type in ("similarity", "lookup"):
        author_spotlight = _build_author_spotlight(
            db, anchor_author, fallback_to_gb=False
        )

    # TBR strip — mood-matched TBR books returned as a separate component
    tbr_matches = (
        _build_tbr_matches(db, _tbr_uuids, query_trope_names, idf_weights)
        if query_type != "lookup"
        else []
    )

    try:
        db.commit()
    except Exception as e:
        logger.error(f"Commit failed, rolling back: {e}")
        db.rollback()
    logger.info(
        f"Pipeline complete. Delivered {len(results)} recommendations, "
        f"{len(tbr_matches)} TBR matches."
    )
    return RecommendationResponse(
        session_id=session_id,
        query_rewritten=expanded_query,
        mood_tags_extracted=list(mood_tags_delta.keys()),
        results=results,
        author_spotlight=author_spotlight,
        tbr_matches=tbr_matches,
        content_mode=_detect_content_mode(query_trope_names, raw_query),
    )


def _detect_content_mode(trope_names: list[str], raw_query: str) -> str:
    """Detect whether this query targets fiction or non-fiction."""
    nonfiction_nodes = {
        "Nonfiction",
        "Narrative Nonfiction",
        "Memoir",
        "True Crime",
        "Biography",
        "History",
        "Philosophy",
        "Popular Science",
        "Self-Help",
        "Essays",
        "Psychology",
        "Sociology",
        "Economics",
        "Political Theory",
        "Cultural Criticism",
    }
    if trope_names:
        if any(t in nonfiction_nodes for t in trope_names):
            return "nonfiction"
    q = raw_query.lower()
    nf_keywords = [
        "memoir",
        "biography",
        "history of",
        "self-help",
        "non-fiction",
        "nonfiction",
        "true crime",
        "essays",
        "philosophy",
        "science of",
        "how to",
    ]
    if any(kw in q for kw in nf_keywords):
        return "nonfiction"
    return "fiction"


# ------------------------------------------------------------------
# Query Classification
# ------------------------------------------------------------------


# ------------------------------------------------------------------
# Lookup — Author search via Google Books first, then OpenLibrary, then Tavily
# ------------------------------------------------------------------


def _handle_lookup_query(db, query, candidates, seen, anchor_author=None):
    author_name = None
    if anchor_author:
        author_name = anchor_author
        logger.info(f"Lookup path: using anchor_author '{author_name}'")
    else:
        author_match = re.search(
            r"(?:by|from)\s+([^,.]+?)(?:\s*[,\.]|$)", query, re.IGNORECASE
        )
        if not author_match:
            return
        author_name = author_match.group(1).strip().rstrip(".!?")
        if len(author_name.split()) > 5:
            author_name = " ".join(author_name.split()[:3])
        logger.info(f"Lookup path: searching for '{author_name}'")

    found = set()

    # 1. Google Books author search — fetch up to 20 to catch past pagination
    try:
        for item in google_books.search_by_title_author("", author_name)[:20]:
            vol = item.get("volumeInfo", {})
            title = vol.get("title", "").strip()
            authors = vol.get("authors", [author_name])
            book_author = authors[0] if authors else author_name
            if not title or title in found:
                continue
            # Skip retail bundle/collection listings that pollute the bibliography
            _skip_patterns = [
                "collection",
                "box set",
                "books set",
                "bundle",
                "2 books",
                "3 books",
                "4 books",
            ]
            if any(p in title.lower() for p in _skip_patterns):
                continue
            _try_enrich_book(db, title, book_author, candidates, seen)
            found.add(title)
    except Exception as e:
        logger.warning(f"Google Books author search failed: {e}")

    # 1b. Local catalog supplement — pull all Works by this author that are
    # already in the DB, even if Google Books didn't return them.
    from sqlalchemy import func as _sf

    _person = (
        db.execute(
            select(Person).where(
                _sf.lower(Person.canonical_name) == author_name.lower()
            )
        )
        .scalars()
        .first()
    )
    if _person:
        _catalog_works = (
            db.execute(select(Work).where(Work.person_uuid == _person.person_uuid))
            .scalars()
            .all()
        )
        for _w in _catalog_works:
            if _w.title not in found and str(_w.work_uuid) not in seen:
                _cache = db.execute(
                    select(EnrichmentCache).where(
                        EnrichmentCache.work_uuid == _w.work_uuid
                    )
                ).scalar_one_or_none()
                candidates.append(
                    reranker.CandidateContext(
                        work_uuid=str(_w.work_uuid),
                        title=_w.title,
                        base_vector_score=0.7,
                        is_tbr_context_match=False,
                        community_buzz_score=(_cache.community_buzz_score or 0.0)
                        if _cache
                        else 0.0,
                        seen_recently=False,
                        book_inferred_profile={},
                        is_narrative=getattr(_cache, "is_narrative", True)
                        if _cache
                        else True,
                        raw_record=_w,
                        match_source="llm",
                    )
                )
                seen.add(str(_w.work_uuid))
                found.add(_w.title)
    if len(found) < 5:
        try:
            results = tavily.search(
                f"{author_name} author books series list",
                search_depth="basic",
                include_domains=["goodreads.com", "amazon.com", "thestorygraph.com"],
            )
            for entry in results.get("results", [])[:5]:
                content = entry.get("content", "")
                # Extract book titles from Goodreads/Amazon content snippets
                # via LLM mini-extraction rather than fragile regex
                if author_name.split()[-1].lower() in content.lower():
                    try:
                        extracted = llm.complete(
                            prompt=(
                                f"Author: {author_name}\n"
                                f"Page content: {content[:600]}\n\n"
                                "List up to 3 book titles by this author mentioned in the content. "
                                'Output JSON: {{"titles": ["Title 1", "Title 2"]}}'
                            ),
                            require_json=True,
                        )
                        for title in extracted.get("titles", [])[:3]:
                            title = title.strip()
                            if title and title not in found:
                                _try_enrich_book(
                                    db, title, author_name, candidates, seen
                                )
                                found.add(title)
                    except Exception:
                        pass
        except Exception as e:
            logger.warning(f"Tavily author fallback failed: {e}")

    # 3. OpenLibrary final fallback
    if len(found) < 3:
        try:
            ol_data = openlibrary.lookup_work("", author_name)
            if ol_data and ol_data.get("title"):
                title = ol_data["title"].strip()
                if title not in found:
                    _try_enrich_book(db, title, author_name, candidates, seen)
                    found.add(title)
        except Exception:
            pass


# ------------------------------------------------------------------
# Similarity — Vector first, LLM supplements
# ------------------------------------------------------------------


def _handle_similarity_query(db, query, candidates, seen):
    for c in _pull_vector_candidates(db, query):
        if c.work_uuid not in seen:
            candidates.append(c)
            seen.add(c.work_uuid)

    llm_cands = _generate_llm_expansion(query)
    validated = _validate_and_build_llm_candidates(db, llm_cands, skip_tavily=False)
    for c in validated:
        if c.work_uuid not in seen:
            candidates.append(c)
            seen.add(c.work_uuid)


# ------------------------------------------------------------------
# Discovery — LLM first, vector supplements
# ------------------------------------------------------------------


def _handle_discovery_query(db, query, candidates, seen):
    llm_cands = _generate_llm_expansion(query)
    validated = _validate_and_build_llm_candidates(db, llm_cands, skip_tavily=False)
    for c in validated:
        if c.work_uuid not in seen:
            candidates.append(c)
            seen.add(c.work_uuid)

    catalog_count = (
        db.execute(
            select(sa_func.count(Work.work_uuid)).where(
                Work.enrichment_status == "complete"
            )
        ).scalar()
        or 0
    )
    if catalog_count >= 20:
        for c in _pull_vector_candidates(db, query):
            if c.work_uuid not in seen:
                candidates.append(c)
                seen.add(c.work_uuid)


# ------------------------------------------------------------------
# Shared helper: try to enrich a single book if not already in DB
# ------------------------------------------------------------------


def _try_enrich_book(db, title, author, candidates, seen):
    """
    Hot-path enrichment: Google Books only, then defer full enrichment to Celery.

    If the book exists in the DB (any enrichment_status), it's appended immediately
    as a partial candidate — the reranker handles empty trope/profile gracefully.

    If the book is new:
      1. Resolve/create Work + EnrichmentCache
      2. Fetch Google Books metadata (~300ms, single API call)
      3. If metadata found: mark enrichment_status="partial", fire Celery task, append candidate
      4. If no metadata found: rollback, book is silently dropped

    No Tavily, no OpenLibrary, no LLM extraction, no Qdrant on the hot path.
    """
    from sqlalchemy import func as sf

    # ── Existing book ──
    existing = (
        db.execute(select(Work).where(sf.lower(Work.title) == title.lower()))
        .scalars()
        .first()
    )
    if existing:
        cache = db.execute(
            select(EnrichmentCache).where(
                EnrichmentCache.work_uuid == existing.work_uuid
            )
        ).scalar_one_or_none()
        candidates.append(
            reranker.CandidateContext(
                work_uuid=str(existing.work_uuid),
                title=existing.title,
                base_vector_score=0.7,
                is_tbr_context_match=False,
                community_buzz_score=(cache.community_buzz_score or 0.0)
                if cache
                else 0.0,
                seen_recently=False,
                book_inferred_profile={},
                is_narrative=getattr(cache, "is_narrative", True) if cache else True,
                raw_record=existing,
                match_source="llm",
            )
        )
        seen.add(title)
        return

    # ── New book: hot path only (Google Books) ──
    savepoint = db.begin_nested()
    try:
        work, cache = _resolve_work_and_cache(db, title, author, None)
        _run_google_books(db, work, cache, title, author, None)

        # Google Books success == existence verified. No Tavily needed on hot path.
        has_metadata = bool(cache.description or cache.raw_categories)
        if not has_metadata:
            logger.info(
                f"Hot path rejected (no Google Books metadata): {title} by {author}"
            )
            savepoint.rollback()
            return

        # Mark as partial and defer full enrichment to background
        work.enrichment_status = "partial"
        cache.last_completed_step = "google_books"
        cache.flashcard_pool = False
        db.flush()

        # Fire background enrichment (non-blocking)
        enrich_book_task.delay(title=work.title, author_name=author)
        logger.info(f"Hot path: partial enrichment queued for {title} by {author}")

        candidates.append(
            reranker.CandidateContext(
                work_uuid=str(work.work_uuid),
                title=work.title,
                base_vector_score=0.7,
                is_tbr_context_match=False,
                community_buzz_score=0.0,
                seen_recently=False,
                book_inferred_profile={},
                is_narrative=True,  # default — background task will correct if needed
                raw_record=work,
                match_source="llm",
            )
        )
        seen.add(title)
    except Exception as e:
        logger.error(f"Hot path enrich failed for {title}: {e}")
        # Don't rollback — the session may have committed other candidates.
        # The orphan work/cache records are harmless (no metadata, will never surface).


# ------------------------------------------------------------------
# New helpers: trope enrichment, explanations, author spotlight
# ------------------------------------------------------------------


def _tavily_enrich_similarity_context(
    raw_query: str,
    existing_tropes: List[str],
    existing_author: Optional[str],
) -> Optional[tuple]:
    """
    Tavily fallback for similarity queries where the LLM had no context.

    "books like play along" → Tavily search → LLM mini-extraction → (tropes, author)

    Returns (trope_names: List[str], author: str | None) or None on failure.
    Only fires when tropes or author are missing from the primary LLM expansion.
    """
    import re as _re

    # Extract anchor title from query
    # "books like play along"         → "play along"
    # "something like the hating game" → "the hating game"
    # "more like red rising"           → "red rising"
    title_match = _re.search(
        r"(?:like|similar to|reminiscent of|more like|in the style of)\s+(.+?)(?:\s+by\s+|$)",
        raw_query.strip(),
        _re.IGNORECASE,
    )
    if not title_match:
        return None

    anchor_title = title_match.group(1).strip().strip("\"'")
    if not anchor_title or len(anchor_title) < 3:
        return None

    logger.info(f"Tavily: searching for anchor title '{anchor_title}'")

    try:
        results = tavily.search(
            f'"{anchor_title}" book tropes themes author romance novel',
            search_depth="basic",
            include_domains=[
                "goodreads.com",
                "amazon.com",
                "thestorygraph.com",
                "bookofthemonth.com",
                "barnesandnoble.com",
            ],
        )
        snippets = [
            e.get("content", "")[:400]
            for e in results.get("results", [])[:4]
            if e.get("content")
        ]
        if not snippets:
            return None

        combined = "\n\n".join(snippets)

        extraction = llm.complete(
            prompt=(
                f'Book title: "{anchor_title}"\n'
                f"Search result snippets:\n{combined}\n\n"
                "From these snippets, extract:\n"
                "1. The author's full name (null if not mentioned)\n"
                "2. Up to 6 canonical romance/fiction tropes from these snippets "
                "(e.g. Marriage of Convenience, Forced Proximity, Enemies to Lovers, "
                "Grumpy-Sunshine, Fake Dating, Sports Romance, Slow Burn, Found Family).\n"
                'Output JSON: {"author": "Full Name" | null, "tropes": ["Trope1", ...]}'
            ),
            require_json=True,
        )

        tropes = [
            t.strip()
            for t in extraction.get("tropes", [])
            if isinstance(t, str) and t.strip()
        ][:6]
        author = extraction.get("author") or None
        if author:
            author = str(author).strip() or None

        return (tropes, author)

    except Exception as e:
        logger.warning(f"Tavily similarity enrichment failed for '{anchor_title}': {e}")
        return None


def _enrich_candidate_tropes(
    db: Session, candidates: List[reranker.CandidateContext]
) -> None:
    """
    Batch-load top tropes for all candidates in a single DB round-trip.
    Populates candidate.book_trope_names in-place.
    """
    from app.models.tropes import BookTrope
    from app.models.tropes import Trope as TropeModel

    if not candidates:
        return

    work_uuids = [uuid.UUID(c.work_uuid) for c in candidates]
    rows = db.execute(
        select(
            BookTrope.work_uuid,
            TropeModel.canonical_name,
            BookTrope.confidence_score,
        )
        .join(TropeModel, BookTrope.trope_uuid == TropeModel.trope_uuid)
        .where(BookTrope.work_uuid.in_(work_uuids))
        .order_by(BookTrope.work_uuid, BookTrope.confidence_score.desc())
    ).all()

    # Group by work_uuid, keep top 6 tropes per book
    trope_map: Dict[str, List[str]] = {}
    for work_uuid_val, name, _ in rows:
        key = str(work_uuid_val)
        if key not in trope_map:
            trope_map[key] = []
        if len(trope_map[key]) < 6:
            trope_map[key].append(name)

    for candidate in candidates:
        candidate.book_trope_names = trope_map.get(candidate.work_uuid, [])


def _stamp_interested_candidates(
    db: Session, user_uuid: str, candidates: List[reranker.CandidateContext]
) -> None:
    """
    Single DB round-trip: fetch all work_uuids where the user has an INTERESTED
    interaction event, then stamp is_interested=True on matching candidates in-place.

    An interested book gets a small resurfacing bonus in the reranker (0.05) that
    counteracts the recency penalty without elevating it to TBR level.
    """
    if not candidates:
        return

    work_uuids = [uuid.UUID(c.work_uuid) for c in candidates]
    rows = (
        db.execute(
            select(InteractionEvent.work_uuid)
            .where(InteractionEvent.user_uuid == user_uuid)
            .where(InteractionEvent.event_type == EventType.INTERESTED)
            .where(InteractionEvent.work_uuid.in_(work_uuids))
            .distinct()
        )
        .scalars()
        .all()
    )

    interested_set = {str(w) for w in rows}
    for candidate in candidates:
        if candidate.work_uuid in interested_set:
            candidate.is_interested = True


def _enrich_candidate_metadata(
    db: Session, candidates: List[reranker.CandidateContext]
) -> None:
    """
    Single DB round-trip: load tower1_snapshot and is_narrative from EnrichmentCache
    and stamp both fields onto each candidate in-place.

    Fixes two silent bugs:
    - Bug A: book_inferred_profile was always {} in every CandidateContext constructor,
      causing _calculate_tower1_overlap to return the 0.5 neutral fallback for every book
      (even non-fiction), giving all books an identical free Tower1 score of 0.125.
    - Bug B: is_narrative was never propagated from the DB, so the reranker couldn't
      zero Tower1 for non-fiction works.
    """
    if not candidates:
        return

    work_uuids = [uuid.UUID(c.work_uuid) for c in candidates]
    caches = (
        db.execute(
            select(EnrichmentCache).where(EnrichmentCache.work_uuid.in_(work_uuids))
        )
        .scalars()
        .all()
    )

    cache_map: Dict[str, EnrichmentCache] = {str(c.work_uuid): c for c in caches}

    # Batch-load Person relationships so WorkResponse serialization
    # never gets null author on frontend cards.
    works = (
        db.execute(
            select(Work)
            .options(joinedload(Work.person))
            .where(Work.work_uuid.in_(work_uuids))
        )
        .unique()
        .scalars()
        .all()
    )
    work_map: Dict[str, Work] = {str(w.work_uuid): w for w in works}

    for candidate in candidates:
        loaded_work = work_map.get(candidate.work_uuid)
        if loaded_work:
            candidate.raw_record = loaded_work
        cache = cache_map.get(candidate.work_uuid)
        if cache:
            # Populate Tower 1 profile from LLM extraction snapshot
            if cache.tower1_snapshot and isinstance(cache.tower1_snapshot, dict):
                candidate.book_inferred_profile = {
                    k: float(v)
                    for k, v in cache.tower1_snapshot.items()
                    if isinstance(v, (int, float))
                }
            # Propagate narrative flag — False zeros Tower1 in the reranker
            candidate.is_narrative = cache.is_narrative
            # Book description for expandable card detail
            candidate.description = cache.description or None


def _build_explanation(
    book_trope_names: List[str],
    query_trope_names: List[str],
    match_source: str,
    fallback_factors: List[str],
) -> str:
    """
    Build a book-specific, reader-facing explanation string.
    Prefers tropes that overlap between the book and the current query.
    Falls back to top book tropes, then to the reranker's explanation_factors.
    """
    if book_trope_names:
        # Show tropes that directly match what the query asked for (most relevant)
        matching = [t for t in book_trope_names if t in query_trope_names]
        non_matching = [t for t in book_trope_names if t not in query_trope_names]

        if len(matching) >= 2:
            shown = matching[:3]
            return f"{', '.join(shown)} — matches your query."
        elif len(matching) == 1 and non_matching:
            shown = [matching[0]] + non_matching[:1]
            return f"{', '.join(shown)}."
        elif book_trope_names:
            # No query overlap — show top book tropes as discovery context
            return f"Known for {', '.join(book_trope_names[:3])}."

    # Fallback to reranker-generated explanation factors
    if fallback_factors:
        return " ".join(fallback_factors)

    return "Semantically matches your current mood query."


def _build_author_spotlight(
    db: Session, author_name: str, fallback_to_gb: bool = True
) -> Optional[AuthorSpotlight]:
    """
    Build an author spotlight showing the author's catalog.
    When fallback_to_gb=False (hot path), only returns DB entries — no API calls.
    """
    from sqlalchemy import func as sf

    # 1. Try to find author in DB
    person = (
        db.execute(
            select(Person).where(
                sf.lower(Person.canonical_name).contains(
                    author_name.split()[-1].lower()  # match on last name
                )
            )
        )
        .scalars()
        .first()
    )

    # Retail bundle/collection patterns to exclude from sidebar
    _SKIP_TITLE_PATTERNS = [
        "collection",
        "box set",
        "books set",
        "bundle",
        "2 books",
        "3 books",
        "4 books",
        "5 books",
    ]

    seen_titles: set = set()
    spotlight_books: List[AuthorSpotlightBook] = []

    if person:
        # Include all enrichment_statuses — partial and pending books
        # are still valid catalog entries.
        works = (
            db.execute(
                select(Work).where(Work.person_uuid == person.person_uuid).limit(10)
            )
            .scalars()
            .all()
        )

        for w in works:
            seen_titles.add(w.title.lower())
            series_label = None
            if hasattr(w, "series_memberships") and w.series_memberships:
                sm = w.series_memberships[0]
                series_label = f"{sm.series.title} #{int(sm.order_float)}"
            spotlight_books.append(
                AuthorSpotlightBook(
                    work_uuid=str(w.work_uuid),
                    title=w.title,
                    cover_url=w.cover_url if hasattr(w, "cover_url") else None,
                    publication_year=w.publication_date.year
                    if w.publication_date
                    else None,
                    series_label=series_label,
                )
            )

    # 2. Google Books supplement — skip on hot path.
    #    On cold path: fills gaps in the catalog. On hot path: adds 6s latency.
    if fallback_to_gb:
        try:
            gb_results = google_books.search_by_title_author("", author_name)[:20]
            for item in gb_results:
                vol = item.get("volumeInfo", {})
                title = vol.get("title", "").strip()
                if not title or title.lower() in seen_titles:
                    continue
                if any(p in title.lower() for p in _SKIP_TITLE_PATTERNS):
                    continue
                seen_titles.add(title.lower())
                _existing = (
                    db.execute(
                        select(Work).where(sf.lower(Work.title) == title.lower())
                    )
                    .scalars()
                    .first()
                )
                if not _existing:
                    continue
                spotlight_books.append(
                    AuthorSpotlightBook(
                        work_uuid=str(_existing.work_uuid),
                        title=_existing.title,
                        cover_url=_existing.cover_url
                        if hasattr(_existing, "cover_url")
                        else None,
                        publication_year=_existing.publication_date.year
                        if _existing.publication_date
                        else None,
                    )
                )
        except Exception as e:
            logger.warning(f"Google Books spotlight supplement failed: {e}")

    if not spotlight_books:
        return None

    author_display = person.canonical_name if person else author_name
    person_uuid = str(person.person_uuid) if person else ""
    pen_names = [pn.display_name for pn in person.pen_names] if person else []
    return AuthorSpotlight(
        author_name=author_display,
        person_uuid=person_uuid,
        pen_names=pen_names,
        books=spotlight_books[:10],
    )


def _verify_no_blocking_checkpoints(db: Session, user_uuid: str):
    pass


def _pull_tbr_candidates(
    db: Session, user_uuid: str, current_query: str
) -> List[reranker.CandidateContext]:
    """
    Returns all active TBR books as candidates.

    B1 fix: previously filtered by bag-of-words keyword overlap between the current
    query and the query text used when the book was added to TBR. This was an
    approximation for trope alignment — but it was a bad one. A book added under
    "dark romance" could share the word "dark" with a "dark academia" query and
    surface incorrectly. Now all active TBRs enter the candidate pool and the
    reranker's trope alignment gate determines actual relevance.

    The TBR bonus in rank_candidates only fires when query_trope_component > 0,
    so books in TBR that have zero overlap with the current query's tropes will
    not receive the bonus and will be strongly suppressed by the zero-overlap gate.
    """
    active_tbrs = db.execute(
        select(TBREntry, Work, EnrichmentCache)
        .join(Work, TBREntry.work_uuid == Work.work_uuid)
        .outerjoin(EnrichmentCache, Work.work_uuid == EnrichmentCache.work_uuid)
        .where(TBREntry.user_uuid == user_uuid)
        .where(TBREntry.status == TBRStatus.ACTIVE)
    ).all()
    candidates = []
    for tbr, work, cache in active_tbrs:
        candidates.append(
            reranker.CandidateContext(
                work_uuid=str(work.work_uuid),
                title=work.title,
                base_vector_score=0.7,
                is_tbr_context_match=True,
                community_buzz_score=(cache.community_buzz_score or 0.0)
                if cache
                else 0.0,
                seen_recently=False,
                book_inferred_profile={},
                raw_record=work,
                match_source="tbr",
            )
        )
    return candidates


def _build_tbr_matches(
    db: Session,
    tbr_uuids: set,
    query_trope_names: List[str],
    idf_weights: Dict[str, float],
) -> List["TBRMatch"]:
    """
    Builds the TBR strip — mood-matched TBR books surfaced as a separate component.

    Scores each active TBR book by IDF-weighted trope overlap with the current query.
    Returns top 3 with overlap > 0 (mood-relevant only). Books with no overlap are
    excluded — if your TBR is all dark romance and you query sci-fi, the strip is empty.
    """
    from app.models.authors import Person
    from app.models.books import Edition
    from app.models.tropes import BookTrope, Trope
    from app.schemas.recommendations import TBRMatch

    if not tbr_uuids or not query_trope_names:
        return []

    query_set = set(query_trope_names)
    results = []

    for work_uuid_str in tbr_uuids:
        try:
            _work_uuid = uuid.UUID(work_uuid_str)
        except ValueError:
            continue

        work = db.execute(
            select(Work).where(Work.work_uuid == _work_uuid)
        ).scalar_one_or_none()
        if not work:
            continue

        book_trope_names = (
            db.execute(
                select(Trope.canonical_name)
                .join(BookTrope, BookTrope.trope_uuid == Trope.trope_uuid)
                .where(BookTrope.work_uuid == _work_uuid)
            )
            .scalars()
            .all()
        )

        overlap = reranker.calculate_trope_overlap(
            list(query_trope_names), list(book_trope_names), idf_weights
        )
        if overlap <= 0:
            continue

        person = db.execute(
            select(Person).where(Person.person_uuid == work.person_uuid)
        ).scalar_one_or_none()
        author_name = person.canonical_name if person else ""

        edition = db.execute(
            select(Edition).where(Edition.work_uuid == _work_uuid)
        ).scalar_one_or_none()
        cover_url = edition.cover_url if edition else None

        overlapping = [t for t in book_trope_names if t in query_set]
        explanation = (
            f"Saved for {', '.join(overlapping[:3])} — matches your current mood."
            if overlapping
            else "Matches the mood of your current query."
        )

        results.append(
            TBRMatch(
                work_uuid=work_uuid_str,
                title=work.title,
                author_name=author_name,
                cover_url=cover_url,
                explanation=explanation,
                overlap_score=overlap,
            )
        )

    results.sort(key=lambda x: x.overlap_score, reverse=True)
    return results[:3]


def _pull_vector_candidates(
    db: Session, expanded_query: str
) -> List[reranker.CandidateContext]:
    # Embed the actual expanded query — never use a dummy vector
    try:
        query_vector = llm.embed(expanded_query)
    except Exception as e:
        logger.error(f"Failed to embed query for vector search: {e}")
        return []
    try:
        search_results = qdrant.search_knn("books_catalog", query_vector, limit=10)
    except Exception as e:
        logger.error(f"Vector search failed: {e}")
        return []

    candidates = []
    for hit in search_results:
        work_uuid = hit["id"]
        work = db.execute(
            select(Work).where(Work.work_uuid == uuid.UUID(work_uuid))
        ).scalar_one_or_none()
        if work:
            cache = db.execute(
                select(EnrichmentCache).where(
                    EnrichmentCache.work_uuid == work.work_uuid
                )
            ).scalar_one_or_none()
            candidates.append(
                reranker.CandidateContext(
                    work_uuid=str(work.work_uuid),
                    title=work.title,
                    base_vector_score=hit["score"],
                    is_tbr_context_match=False,
                    community_buzz_score=(cache.community_buzz_score or 0.0)
                    if cache
                    else 0.0,
                    seen_recently=False,
                    book_inferred_profile={},
                    raw_record=work,
                    match_source="vector",
                )
            )
    return candidates


def _generate_llm_expansion(
    expanded_query: str, count: int = 3
) -> List[Dict[str, str]]:
    """
    Ask Gemini to suggest book (title, author) pairs matching the query.

    ``count`` defaults to 3 for the hot path. Each candidate requires a
    Google Books API call (~6s), so keeping this small is critical for latency.
    """
    prompt = (
        f"Suggest {count} specific book titles that perfectly match this "
        f"criteria: '{expanded_query}'. Output strict JSON array of objects "
        "with 'title' and 'author' keys."
    )
    system = "You are a book database. Output only JSON."
    try:
        response = llm.complete(prompt, system=system, require_json=True)
        return response if isinstance(response, list) else []
    except Exception:
        return []


def _validate_and_build_llm_candidates(
    db: Session,
    suggestions: List[Dict[str, str]],
    skip_tavily: bool = False,  # kept for backwards compat, no longer used on hot path
) -> List[reranker.CandidateContext]:
    """
    Hot-path validation + shallow enrichment for LLM-suggested book candidates.

    Two passes:
      1. Sequential: check DB for existing matches — fast, no API calls.
      2. Parallel: Google Books lookups for new books via ThreadPoolExecutor.
         Each HTTP call was taking ~6s sequentially; parallel reduces 5×6s → 6s.

    On metadata success, marks ``enrichment_status="partial"`` and fires
    ``enrich_book_task.delay()``.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    from sqlalchemy import func as sf

    candidates: List[reranker.CandidateContext] = []
    new_pairs: List[tuple] = []  # (title, author) for books not yet in DB

    # ── Pass 1: Check existing books (fast, sequential) ──
    for book in suggestions:
        title = book.get("title", "").strip()
        author = book.get("author", "").strip()
        if not title or not author:
            continue

        existing = (
            db.execute(
                select(Person).where(sf.lower(Person.canonical_name) == author.lower())
            )
            .scalars()
            .first()
        )
        if existing:
            work = db.execute(
                select(Work)
                .where(Work.person_uuid == existing.person_uuid)
                .where(sf.lower(Work.title) == title.lower())
            ).scalar_one_or_none()
            if work:
                cache = db.execute(
                    select(EnrichmentCache).where(
                        EnrichmentCache.work_uuid == work.work_uuid
                    )
                ).scalar_one_or_none()
                candidates.append(
                    reranker.CandidateContext(
                        work_uuid=str(work.work_uuid),
                        title=work.title,
                        base_vector_score=0.6,
                        is_tbr_context_match=False,
                        community_buzz_score=(cache.community_buzz_score or 0.0)
                        if cache
                        else 0.0,
                        seen_recently=False,
                        book_inferred_profile={},
                        is_narrative=getattr(cache, "is_narrative", True)
                        if cache
                        else True,
                        raw_record=work,
                        match_source="llm",
                    )
                )
                continue

        # Not in DB — queue for parallel Google Books lookup
        new_pairs.append((title, author))

    if not new_pairs:
        return candidates

    # ── Pass 2: Parallel Google Books lookups ──
    def _fetch_gb(title: str, author: str) -> tuple:
        """Pure HTTP call — no DB. Returns (title, author, vol_info_or_None)."""
        try:
            results = google_books.search_by_title_author(title, author)
            if results:
                vol_info = results[0].get("volumeInfo", {})
                if vol_info.get("description") or vol_info.get("categories"):
                    return (title, author, vol_info)
        except Exception:
            pass
        return (title, author, None)

    gb_results: List[tuple] = []
    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {pool.submit(_fetch_gb, t, a): (t, a) for t, a in new_pairs}
        for future in as_completed(futures):
            gb_results.append(future.result())

    # ── Pass 3: Sequential DB writes (fast — no HTTP calls) ──
    for title, author, vol_info in gb_results:
        if not vol_info:
            logger.info(
                f"Hot path rejected LLM candidate (no metadata): {title} by {author}"
            )
            continue

        try:
            work, cache = _resolve_work_and_cache(db, title, author, None)

            # Write Google Books metadata (DB only, no HTTP)
            work.publication_date = (
                _parse_date(vol_info.get("publishedDate"))
                if hasattr(vol_info, "get")
                else None
            )
            from app.models.books import Edition

            edition = db.execute(
                select(Edition).where(Edition.work_uuid == work.work_uuid)
            ).scalar_one_or_none()
            if not edition:
                edition = Edition(work_uuid=work.work_uuid)
                db.add(edition)
            edition.publisher = vol_info.get("publisher")
            edition.page_count = vol_info.get("pageCount")
            edition.cover_url = vol_info.get("imageLinks", {}).get("thumbnail")

            cache.description = (vol_info.get("description") or "")[:1000]
            cache.raw_categories = vol_info.get("categories", [])

            work.enrichment_status = "partial"
            cache.last_completed_step = "google_books"
            cache.flashcard_pool = False
            db.flush()

            enrich_book_task.delay(title=title, author_name=author)
            logger.info(f"Hot path: LLM candidate partial queued: {title} by {author}")

            candidates.append(
                reranker.CandidateContext(
                    work_uuid=str(work.work_uuid),
                    title=work.title,
                    base_vector_score=0.6,
                    is_tbr_context_match=False,
                    community_buzz_score=0.0,
                    seen_recently=False,
                    book_inferred_profile={},
                    is_narrative=True,
                    raw_record=work,
                    match_source="llm",
                )
            )
        except Exception as e:
            logger.error(f"Hot path failed for LLM candidate {title}: {e}")
            # Don't rollback — may invalidate other candidates from earlier iterations.
            # The orphan work/cache records are harmless (no metadata, will never surface).

    return candidates
