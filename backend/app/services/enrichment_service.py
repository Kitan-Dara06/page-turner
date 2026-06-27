"""
Enrichment Pipeline — Step-based Book Intelligence Layer
Implements SRS Section 5.6 with per-step failure handling and safe Celery retries.

Pipeline order:
   1. Google Books  (hard failure — retry 3x, then fail)
   2. OpenLibrary   (soft failure — retry 3x, then continue)
   3. LLM Extraction (soft failure — retry 2x, write orphans, continue)
      3a. Stage 1: extract from metadata
      3b. Stage 2: parametric inference if Stage 1 returns < 4 leaf tropes
   4. Tavily        (seed books: Wikipedia enrichment instead; live: full Tavily)
   5. Qdrant Upsert (hard failure — retry 3x, then fail)
"""

import logging
import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.config import settings
from app.integrations import google_books, llm, openlibrary, qdrant, reddit, tavily
from app.models.authors import Person
from app.models.books import Edition, Work
from app.models.enrichment import EnrichmentCache
from app.models.series import Series, SeriesWork
from app.models.tropes import BookTrope, OrphanQueue, Trope

logger = logging.getLogger(__name__)

STEPS = [
    "google_books",
    "openlibrary",
    "series_detection",
    "llm_extraction",
    "tavily",
    "qdrant",
]


def enrich_book(
    db: Session,
    title: str,
    author_name: str,
    isbn: Optional[str] = None,
    skip_tavily: bool = True,
) -> Work:
    """
    Main entry point. Runs the full enrichment pipeline.

    Args:
        skip_tavily: Skip Tavily for seed catalog books (default True).
                     Set False for books entered via user action.
    """
    work, cache = _resolve_work_and_cache(db, title, author_name, isbn)
    start_from = _resolve_start_step(cache)

    for step in STEPS[start_from:]:
        try:
            if step == "google_books":
                _run_google_books(db, work, cache, title, author_name, isbn)
            elif step == "openlibrary":
                _run_openlibrary(db, work, cache, title, author_name)
            elif step == "series_detection":
                _run_series_detection(db, work, cache, title, author_name)
            elif step == "llm_extraction":
                _run_llm_extraction(db, work, cache)
            elif step == "tavily":
                if skip_tavily:
                    cache.hallucination_verified = "unverifiable"
                    # Wikipedia enrichment replaces the no-op — free, in-stack,
                    # targets the thematic context Google Books description misses
                    _run_wikipedia_enrichment(work, cache, title, author_name)
                else:
                    _run_tavily(db, work, cache, title, author_name)
            elif step == "qdrant":
                _run_qdrant_upsert(db, work, cache, title, author_name)

            cache.last_completed_step = step
            db.flush()
            logger.info(f"Step '{step}' complete for work {work.work_uuid}")

        except Exception as e:
            logger.error(f"Step '{step}' failed for work {work.work_uuid}: {e}")
            _handle_step_failure(step, work, cache, db)
            if _is_hard_failure(step):
                raise

    work.enrichment_status = "complete"
    cache.enriched_at = datetime.now(timezone.utc)
    db.commit()
    return work


# ------------------------------------------------------------------
# Step 1: Google Books
# ------------------------------------------------------------------


def _run_google_books(
    db: Session,
    work: Work,
    cache: EnrichmentCache,
    title: str,
    author_name: str,
    isbn: Optional[str],
) -> None:
    """Fetch base metadata. Hard failure — without this, stop."""
    gb_data = None
    if isbn:
        gb_data = google_books.fetch_by_isbn(isbn)
    if not gb_data:
        results = google_books.search_by_title_author(title, author_name)
        if results:
            gb_data = results[0]

    if not gb_data:
        logger.warning(f"Google Books: no results for '{title}' by {author_name}")
        return

    vol_info = gb_data.get("volumeInfo", {})
    work.publication_date = _parse_date(vol_info.get("publishedDate"))

    # Edition
    edition = db.execute(
        select(Edition).where(Edition.work_uuid == work.work_uuid)
    ).scalar_one_or_none()
    if not edition:
        edition = Edition(work_uuid=work.work_uuid)
        db.add(edition)
    edition.publisher = vol_info.get("publisher")
    edition.page_count = vol_info.get("pageCount")
    edition.cover_url = vol_info.get("imageLinks", {}).get("thumbnail")

    # Cache
    cache.description = vol_info.get("description", "")[:1000]
    cache.raw_categories = vol_info.get("categories", [])


# ------------------------------------------------------------------
# Step 2: OpenLibrary
# ------------------------------------------------------------------


def _run_openlibrary(
    db: Session,
    work: Work,
    cache: EnrichmentCache,
    title: str,
    author_name: str,
) -> None:
    """Fetch subject tags and series info. Soft failure — continue on miss."""
    ol_data = openlibrary.lookup_work(title, author_name)
    if not ol_data:
        logger.info(f"OpenLibrary: no results for '{title}'")
        return

    subjects = ol_data.get("subject", [])
    cache.subject_tags = subjects[:20] if subjects else []

    # Series detection
    series_raw = ol_data.get("series")
    if series_raw and isinstance(series_raw, list):
        cache.series_raw = str(series_raw)
        for s in series_raw:
            _ensure_series(db, work, s)


def _ensure_series(db: Session, work: Work, series_data: Any) -> None:
    """Create Series + SeriesWork if not already linked."""
    if isinstance(series_data, dict):
        name = series_data.get("name", "Unknown Series")
        position = series_data.get("position", 1.0)
    else:
        name = str(series_data)
        position = 1.0

    existing = db.execute(
        select(Series).where(
            Series.person_uuid == work.person_uuid,
            Series.title == name,
        )
    ).scalar_one_or_none()

    if not existing:
        existing = Series(
            title=name,
            person_uuid=work.person_uuid,
        )
        db.add(existing)
        db.flush()

    link_exists = db.execute(
        select(SeriesWork).where(
            SeriesWork.series_uuid == existing.series_uuid,
            SeriesWork.work_uuid == work.work_uuid,
        )
    ).first()
    if not link_exists:
        db.add(
            SeriesWork(
                series_uuid=existing.series_uuid,
                work_uuid=work.work_uuid,
                order_float=float(position),
            )
        )


# ------------------------------------------------------------------ #
# Step 2.5: Series Detection via Tavily                               #
# ------------------------------------------------------------------ #


def _run_series_detection(db, work, cache, title, author_name):
    """Supplement OpenLibrary series detection with Tavily for indie/genre coverage."""
    existing = db.execute(
        select(SeriesWork).where(SeriesWork.work_uuid == work.work_uuid)
    ).first()
    if existing:
        return
    try:
        query = f'"{title}" "{author_name}" series books'
        results = tavily.search(query, search_depth="basic")
        if not results or not results.get("results"):
            return
        snippets = "\n".join(
            r.get("content", "")[:300] for r in results.get("results", [])[:3]
        )
        if len(snippets) < 50:
            return
        prompt = (
            f"Book: {title} by {author_name}\n\n"
            f"Web results:\n{snippets[:1500]}\n\n"
            "Is this book part of a series? Extract series name and position.\n"
            "Return nulls if standalone or unclear.\n"
            'JSON: {{"series_name": "..."|"", "position": 1, '
            '"total_books": null}}'
        )
        result = llm.complete(prompt, require_json=True, timeout=15)
        if not result or not isinstance(result, dict):
            return
        name = (result.get("series_name") or "").strip()
        if not name or len(name) < 2:
            return
        pos = result.get("position") or 1.0
        total = result.get("total_books")
        _ensure_series(db, work, {"name": name, "position": float(pos)})
        if total:
            s = db.execute(
                select(Series).where(
                    Series.person_uuid == work.person_uuid, Series.title == name
                )
            ).scalar_one_or_none()
            if s and not s.total_core_works:
                s.total_core_works = int(total)
        logger.info(f"Series via Tavily: '{title}' → {name} #{pos}")
    except Exception as e:
        logger.warning(f"Series detection failed for '{title}': {e}")


# ------------------------------------------------------------------
# Step 3: LLM Extraction
# --------------------------------------------------# Structural branch nodes: direct children of root hubs that are organisational,
# not descriptors. Excluded from the canonical names list and blocked at write time.
_STRUCTURAL_BRANCH_NAMES = frozenset({"Scale", "Reality", "Timeline"})

# Minimum leaf-trope count before Stage 2 parametric inference fires
_STAGE2_THRESHOLD = 4


def _build_extraction_prompt(db: Session) -> str:
    """
    Build the LLM system prompt dynamically from the live tropes table.
    Excludes root hubs (is_root_hub=True) and structural branch nodes that are
    organisational, not book descriptors. Called once per enrichment run.
    """
    trope_names = (
        db.execute(
            select(Trope.canonical_name)
            .where(Trope.is_root_hub == False)  # noqa: E712
            .where(~Trope.canonical_name.in_(_STRUCTURAL_BRANCH_NAMES))
            .order_by(Trope.depth_level, Trope.canonical_name)
        )
        .scalars()
        .all()
    )
    trope_list = ", ".join(trope_names)

    return f"""You are the PAGETURNER Taxonomy Engine.
Analyze the following book metadata and extract structured attributes.

Output STRICT JSON with these keys:
1. "trope_mappings": list of {{"canonical_name": str, "confidence": float}}
   Only include tropes where confidence >= 0.4.
   Use the EXACT canonical names from the list below. Do not paraphrase or invent names.
2. "tower1_attributes": dict of Tower 1 dimensions this book exemplifies (0.0-1.0).
   Keys: darkness_tolerance, angst_level, violence_tolerance, thematic_density,
   pacing_preference, prose_density, narrative_linearity, plot_vs_character,
   setting_scope, speculative_deviation, world_building_appetite, emotional_intensity,
   standalone_preference.
3. "orphan_candidates": list of raw tag strings that are relevant but don't match
   any canonical trope with confidence >= 0.4.
4. "is_narrative": boolean. true if this work tells a story with characters and plot —
   novels, short story collections, graphic novels, AND narrative non-fiction
   (memoir, true crime narrative, narrative nonfiction, immersive journalism).
   false ONLY for non-narrative, non-story works — textbooks, self-help, reference,
   philosophy treatise, history survey, expository science writing.
   When in doubt, true.

Confidence scoring rubric (score CENTRALITY, not mere presence):
  1.0   = definitional — removing this trope makes the book unrecognisable
  0.7-0.9 = load-bearing — strongly shapes the reading experience
  0.4-0.69 = notable — present and meaningful, not the primary identity
  < 0.4 — do NOT include; put the tag in orphan_candidates instead

CRITICAL CONSTRAINTS:
- NEVER output root hub names as trope_mappings entries. These are organisational
  nodes, not book descriptors:
  "Setting & Environment", "Plot Catalysts & Structures",
  "Character Archetypes & Dynamics", "Thematic Core", "Conflict Typology"
- NEVER output structural branch names: "Scale", "Reality", "Timeline"
- Redemption Arc: requires the NARRATIVE to endorse growth as meaningful resolution.
  A character who suffers and changes but whose narrative withholds or refuses
  redemption does NOT score highly. Example: A Little Life → 0.1 (refused arc).
  Crime and Punishment → 1.0 (fully endorsed arc).

Canonical tropes (use these exact strings only):
{trope_list}
"""


def _run_llm_extraction(
    db: Session,
    work: Work,
    cache: EnrichmentCache,
) -> None:
    """Extract tropes and Tower 1 attributes via LLM. Soft failure.

    Two-stage:
      Stage 1 — extraction from supplied metadata.
      Stage 2 — parametric inference if Stage 1 returns < _STAGE2_THRESHOLD leaf tropes.
    Non-narrative works (is_narrative=False) skip trope extraction entirely.
    """
    # 3C: Gate — skip trope extraction for non-narrative works
    if not cache.is_narrative:
        logger.info(
            f"Non-narrative work {work.work_uuid} ({work.title}) — "
            "skipping trope extraction, running Tower 1 only"
        )
        _run_tower1_only(work, cache)
        cache.taxonomy_version = settings.TAXONOMY_VERSION
        return

    desc = cache.description or ""
    subjects = ", ".join(cache.subject_tags or [])
    categories = ", ".join(cache.raw_categories or [])
    # Include Wikipedia snippets in context if available
    wiki_context = ""
    if cache.sentiment_snippets:
        wiki_context = (
            "\nThematic context: " + " ".join(cache.sentiment_snippets[:2])[:400]
        )

    # StoryGraph community tags — primary source for romance community vocabulary.
    # Mood, pace, tropes, and content warnings from reader-generated tags.
    # Falls back to empty string on timeout or failure (soft dependency).
    storygraph_context = ""
    try:
        from app.integrations import storygraph

        author_name = (
            db.execute(
                select(Person.canonical_name).where(
                    Person.person_uuid == work.person_uuid
                )
            ).scalar_one_or_none()
            or ""
        )
        sg_tags = storygraph.fetch_tags(work.title, author_name)
        if sg_tags:
            parts = []
            if sg_tags.get("moods"):
                parts.append(f"Moods: {', '.join(sg_tags['moods'])}")
            if sg_tags.get("pace"):
                parts.append(f"Pace: {sg_tags['pace']}")
            if sg_tags.get("tropes"):
                parts.append(f"Community tags: {', '.join(sg_tags['tropes'][:10])}")
            if sg_tags.get("warnings"):
                parts.append(f"Content warnings: {', '.join(sg_tags['warnings'][:8])}")
            if parts:
                storygraph_context = "\nStoryGraph: " + " | ".join(parts) + ""
                logger.debug(f"StoryGraph context built for '{work.title}'")
    except Exception as e:
        logger.debug(f"StoryGraph unavailable for '{work.title}': {e}")

    prompt = (
        f"Title: {work.title}\n"
        f"Description: {desc}\n"
        f"Subjects: {subjects}\n"
        f"Categories: {categories}"
        f"{wiki_context}"
        f"{storygraph_context}\n\n"
        "Output JSON:"
    )

    # 3A: System prompt built from live taxonomy — excludes root hubs + structural branches
    system_prompt = _build_extraction_prompt(db)

    try:
        response = llm.complete(
            prompt=prompt,
            system=system_prompt,
            require_json=True,
        )
    except Exception as e:
        logger.warning(f"LLM extraction failed for {work.work_uuid}: {e}")
        return

    # Guard: LLM occasionally returns a string when JSON parsing fails
    if not isinstance(response, dict):
        logger.warning(
            f"LLM extraction returned non-dict for {work.work_uuid}: "
            f"{str(response)[:100]}"
        )
        return

    _write_trope_mappings(db, work, response.get("trope_mappings", []))

    # B2 fix: persist is_narrative classification from LLM response.
    # Defaults to True on missing/non-bool so we never falsely block fiction.
    # Only set False when the LLM explicitly returns false for a non-narrative work.
    raw_narrative = response.get("is_narrative", True)
    if isinstance(raw_narrative, bool):
        cache.is_narrative = raw_narrative
    # Non-bool response (e.g. string, null) → leave the current value untouched.

    # Write orphan candidates (atomic upsert)
    from sqlalchemy import text as sa_text

    for tag in response.get("orphan_candidates", []):
        clean = tag.lower().strip()
        db.execute(
            sa_text(
                "INSERT INTO orphan_queue (tag_text, source, frequency_count, first_seen, last_seen) "
                "VALUES (:tag, 'llm_extraction', 1, now(), now()) "
                "ON CONFLICT (tag_text) DO UPDATE SET frequency_count = orphan_queue.frequency_count + 1, last_seen = now()"
            ),
            {"tag": clean},
        )

    # Store Tower 1 snapshot
    tower1 = response.get("tower1_attributes", {})
    if tower1:
        cache.tower1_snapshot = tower1

    # 3D: Stage 2 — parametric inference if metadata was insufficient
    leaf_count = (
        db.execute(
            select(func.count())
            .select_from(BookTrope)
            .join(Trope, Trope.trope_uuid == BookTrope.trope_uuid)
            .where(BookTrope.work_uuid == work.work_uuid)
            .where(Trope.is_root_hub == False)  # noqa: E712
            .where(~Trope.canonical_name.in_(_STRUCTURAL_BRANCH_NAMES))
        ).scalar()
        or 0
    )

    if leaf_count < _STAGE2_THRESHOLD:
        logger.info(
            f"Stage 1 returned {leaf_count} leaf tropes for '{work.title}' — "
            "firing Stage 2 parametric inference"
        )
        _run_parametric_inference(db, work, cache)

    # 3F: Stamp taxonomy version
    cache.taxonomy_version = settings.TAXONOMY_VERSION


# ------------------------------------------------------------------ #
# Stage 2: Parametric inference (metadata-poor books)                #
# ------------------------------------------------------------------ #


def _run_parametric_inference(db: Session, work: Work, cache: EnrichmentCache) -> None:
    """
    Stage 2 LLM enrichment using parametric knowledge rather than supplied metadata.
    Fires when Stage 1 returns fewer than _STAGE2_THRESHOLD leaf-node tropes.
    Confidence scores are reduced by 0.1 to signal parametric (not extracted) origin.
    Sets cache.parametric_inference = True.
    """
    system_prompt = _build_extraction_prompt(db)
    pub_year = work.publication_date.year if work.publication_date else "unknown"

    # Resolve author name — person_uuid is a UUID, not a human-readable name
    from app.models.authors import Person

    person = db.execute(
        select(Person).where(Person.person_uuid == work.person_uuid)
    ).scalar_one_or_none()
    author_name = person.canonical_name if person else "Unknown"

    prompt = (
        f"Title: {work.title}\n"
        f"Author: {author_name}\n"
        f"Publication year: {pub_year}\n\n"
        "The metadata for this book is insufficient for extraction. "
        "Use your pre-training knowledge of this specific title to identify its "
        "thematic, structural, and character-level tropes. "
        "If you do not have reliable knowledge of this book, return an empty trope_mappings list."
        "\nOutput JSON:"
    )
    try:
        response = llm.complete(prompt=prompt, system=system_prompt, require_json=True)
        if not isinstance(response, dict):
            logger.warning(
                f"Parametric inference returned non-dict for {work.work_uuid}"
            )
            return
        cache.parametric_inference = True

        # Apply -0.1 confidence discount across all parametric results
        adjusted = [
            {
                "canonical_name": m.get("canonical_name", ""),
                "confidence": max(0.0, float(m.get("confidence", 0.0)) - 0.1),
            }
            for m in response.get("trope_mappings", [])
        ]
        _write_trope_mappings(db, work, adjusted)

        tower1 = response.get("tower1_attributes", {})
        if tower1 and not cache.tower1_snapshot:
            cache.tower1_snapshot = tower1

    except Exception as e:
        logger.warning(f"Parametric inference failed for {work.work_uuid}: {e}")


# ------------------------------------------------------------------ #
# Tower 1 only (non-narrative works: Meditations, Sapiens, etc.)     #
# ------------------------------------------------------------------ #


def _run_tower1_only(work: Work, cache: EnrichmentCache) -> None:
    """
    For non-narrative works: generate Tower 1 profile only.
    No trope mapping, no orphan candidates.
    Tower 2 (Qdrant embedding) handles similarity for these books.
    """
    prompt = (
        f"Title: {work.title}\n"
        f"Description: {cache.description or ''}\n\n"
        "This is a non-fiction or non-narrative work with no characters or plot arc. "
        "Output JSON with only 'tower1_attributes'. "
        "Do not include trope_mappings or orphan_candidates.\nOutput JSON:"
    )
    system = (
        "Extract Tower 1 reading profile dimensions for a non-narrative work. "
        "Output JSON with key 'tower1_attributes' only. "
        "Shared fiction/non-fiction keys: thematic_density, pacing_preference, "
        "prose_density, narrative_linearity, setting_scope, emotional_intensity, "
        "exploration_tolerance, reread_tendency. "
        "Non-fiction specific: factual_density, instructional_vs_conceptual. "
        "All floats 0.0-1.0."
    )
    try:
        response = llm.complete(prompt=prompt, system=system, require_json=True)
        if not isinstance(response, dict):
            return
        tower1 = response.get("tower1_attributes", {})
        if tower1:
            # Non-narrative works: null out fiction-only and romance-conditional
            # dimensions. 0.0 means "lowest value"; null means "not applicable."
            _nonfiction_null_dims = [
                "darkness_tolerance",
                "angst_level",
                "violence_tolerance",
                "speculative_deviation",
                "world_building_appetite",
                "plot_vs_character",
                "standalone_preference",
                "series_completion_tendency",
                "pov_structure",
                "protagonist_agency",
                # Romance-conditional
                "explicit_content_level",
                "romance_centrality",
                "hea_requirement",
                "relationship_ratio",
                "role_rigidity",
                "relationship_pace",
            ]
            for _dim in _nonfiction_null_dims:
                tower1.pop(_dim, None)
            cache.tower1_snapshot = tower1
    except Exception as e:
        logger.warning(f"Tower1-only extraction failed for {work.work_uuid}: {e}")


# ------------------------------------------------------------------ #
# Shared trope write helper                                          #
# ------------------------------------------------------------------ #


def _write_trope_mappings(db: Session, work: Work, mappings: list[dict]) -> None:
    """
    Persist trope mappings to book_tropes using INSERT ... ON CONFLICT DO NOTHING.

    This is safe to call multiple times for the same work (Stage 1 + Stage 2,
    or retries) — duplicate (work_uuid, trope_uuid) pairs are silently skipped
    at the DB level regardless of flush state. No select-then-insert race.
    Root hub and structural branch nodes are rejected before the insert.
    """
    # Resolve and validate all mappings first — build a deduplicated insert list
    rows: list[dict] = []
    seen: set = set()  # trope_uuids accepted in this call (pre-DB dedup)

    for mapping in mappings:
        # Guard: LLM occasionally returns plain strings instead of {name, confidence}
        if isinstance(mapping, str):
            mapping = {"canonical_name": mapping, "confidence": 0.8}
        name = mapping.get("canonical_name", "")
        confidence = float(mapping.get("confidence", 0.0))
        if confidence < 0.4:
            continue

        trope = db.execute(
            select(Trope).where(Trope.canonical_name == name)
        ).scalar_one_or_none()

        if not trope:
            continue

        # 3B: Application-layer guard — reject root hubs and structural branches
        if trope.is_root_hub or trope.canonical_name in _STRUCTURAL_BRANCH_NAMES:
            logger.warning(
                f"LLM proposed non-taggable node '{name}' for '{work.title}' — rejected"
            )
            continue

        if trope.trope_uuid in seen:
            continue
        seen.add(trope.trope_uuid)

        rows.append(
            {
                "work_uuid": work.work_uuid,
                "trope_uuid": trope.trope_uuid,
                "confidence_score": confidence,
            }
        )

    if not rows:
        return

    # Single atomic INSERT ... ON CONFLICT DO NOTHING
    # Handles: LLM self-repetition, Stage1+Stage2 overlap, cross-call retries
    stmt = (
        pg_insert(BookTrope)
        .values(rows)
        .on_conflict_do_nothing(index_elements=["work_uuid", "trope_uuid"])
    )
    db.execute(stmt)


# ------------------------------------------------------------------
# Step 4: Tavily / Wikipedia enrichment
# ------------------------------------------------------------------


def _run_wikipedia_enrichment(
    work: Work,
    cache: EnrichmentCache,
    title: str,
    author_name: str,
) -> None:
    """
    Wikipedia enrichment for seed books (replaces the skip_tavily no-op).
    Queries Tavily scoped to Wikipedia to surface thematic/analysis content.
    Stored in sentiment_snippets and consumed as context in LLM extraction.
    Soft failure — missing Wikipedia data is not an error.
    """
    try:
        results = tavily.search(
            f'site:en.wikipedia.org "{title}" {author_name} themes analysis',
            search_depth="basic",
        )
        entries = results.get("results", [])
        snippets = [e.get("content", "")[:300] for e in entries[:2] if e.get("content")]
        if snippets:
            existing = cache.sentiment_snippets or []
            cache.sentiment_snippets = existing + snippets
            logger.info(f"Wikipedia enrichment: {len(snippets)} snippets for '{title}'")
    except Exception as e:
        logger.info(f"Wikipedia enrichment soft-failed for '{title}': {e}")


def _run_tavily(
    db: Session,
    work: Work,
    cache: EnrichmentCache,
    title: str,
    author_name: str,
) -> None:
    """Verify book exists, pull community sentiment. Soft failure."""
    is_real = tavily.verify_hallucination(title, author_name)
    if is_real:
        cache.hallucination_verified = "verified"
    else:
        cache.hallucination_verified = "suspected_fake"
        logger.warning(f"Tavily: '{title}' may be hallucinated")

    # Pull community data — author-first query avoids generic-title noise
    results = tavily.search(
        f'{author_name} "{title}" book',
        search_depth="basic",
        include_domains=[
            "goodreads.com",
            "amazon.com",
            "thestorygraph.com",
            "bookofthemonth.com",
            "barnesandnoble.com",
        ],
    )
    entries = results.get("results", [])
    if entries:
        # 300 chars per snippet for richer LLM context (was 200)
        snippets = [e.get("content", "")[:300] for e in entries[:3] if e.get("content")]
        cache.sentiment_snippets = snippets
        cache.community_buzz_score = min(1.0, len(entries) / 10.0)


# ------------------------------------------------------------------
# Step 5: Qdrant Upsert
# ------------------------------------------------------------------


def _run_qdrant_upsert(
    db: Session,
    work: Work,
    cache: EnrichmentCache,
    title: str,
    author_name: str,
) -> None:
    """Build embedding string and upsert to Qdrant. Hard failure."""
    trope_names = _get_trope_names(db, work)
    tower1_str = _stringify_tower1(cache.tower1_snapshot)
    subjects = ", ".join(cache.subject_tags or [])
    desc = (cache.description or "")[:1500]  # truncate

    embedding_text = (
        f"{title} by {author_name}. {desc} "
        f"Tropes: {trope_names}. "
        f"Mood: {tower1_str}. "
        f"Tags: {subjects}."
    )[:2000]  # hard token cap

    # RC-4: Real 1536-dim embedding via Voyage AI voyage-large-2
    vector = llm.embed(embedding_text)

    qdrant.create_collection_if_not_exists("books_catalog")
    qdrant.upsert_vector(
        collection_name="books_catalog",
        point_id=str(work.work_uuid),
        vector=vector,
        payload={
            "work_uuid": str(work.work_uuid),
            "title": work.title,
            "author": author_name,
            "hallucination_verified": cache.hallucination_verified or "unverifiable",
        },
    )


def _get_trope_names(db: Session, work: Work) -> str:
    """Get comma-joined trope names for this work."""
    rows = db.execute(
        select(Trope.canonical_name)
        .join(BookTrope, Trope.trope_uuid == BookTrope.trope_uuid)
        .where(BookTrope.work_uuid == work.work_uuid)
    ).all()
    return ", ".join(r[0] for r in rows)


def _stringify_tower1(snapshot: Optional[dict]) -> str:
    if not snapshot:
        return ""
    return ", ".join(
        f"{k}={v}" for k, v in snapshot.items() if isinstance(v, (int, float))
    )


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _resolve_work_and_cache(
    db: Session,
    title: str,
    author_name: str,
    isbn: Optional[str],
) -> Tuple[Work, EnrichmentCache]:
    """Find existing work or create new, ensuring cache exists."""
    norm_title = title.lower().strip()
    norm_author = author_name.lower().strip()

    # Author resolution — .first() handles duplicate Person rows gracefully
    person = (
        db.execute(
            select(Person).where(func.lower(Person.canonical_name) == norm_author)
        )
        .scalars()
        .first()
    )
    if not person:
        person = Person(canonical_name=author_name)
        db.add(person)
        db.flush()

    # Work resolution — .first() handles duplicates from prior seed runs
    work = (
        db.execute(
            select(Work)
            .where(Work.person_uuid == person.person_uuid)
            .where(func.lower(Work.title) == norm_title)
        )
        .scalars()
        .first()
    )
    if not work:
        work = Work(title=title, person_uuid=person.person_uuid)
        db.add(work)
        db.flush()

    # Enrichment cache
    cache = (
        db.execute(
            select(EnrichmentCache).where(EnrichmentCache.work_uuid == work.work_uuid)
        )
        .scalars()
        .first()
    )
    if not cache:
        cache = EnrichmentCache(work_uuid=work.work_uuid)
        db.add(cache)
        db.flush()

    return work, cache


def _resolve_start_step(cache: EnrichmentCache) -> int:
    """Determine which step to resume from."""
    if cache.last_completed_step:
        try:
            return STEPS.index(cache.last_completed_step) + 1
        except ValueError:
            return 0
    return 0


def _handle_step_failure(
    step: str, work: Work, cache: EnrichmentCache, db: Session
) -> None:
    """Mark enrichment_status on hard failures."""
    if step in ("google_books", "qdrant"):
        work.enrichment_status = "failed"
        db.flush()


def _is_hard_failure(step: str) -> bool:
    return step in ("google_books", "qdrant")


def _parse_date(date_str: Optional[str]) -> Optional[datetime]:
    if not date_str:
        return None
    try:
        if len(date_str) == 4:
            return datetime(int(date_str), 1, 1, tzinfo=timezone.utc)
        elif len(date_str) == 7:
            return datetime.strptime(date_str, "%Y-%m").replace(tzinfo=timezone.utc)
        else:
            return datetime.strptime(date_str[:10], "%Y-%m-%d").replace(
                tzinfo=timezone.utc
            )
    except (ValueError, TypeError):
        return None
