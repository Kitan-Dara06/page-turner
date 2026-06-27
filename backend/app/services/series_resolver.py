"""
Series-aware query resolution.

When a user mentions a series name ("Sigma Sin series"), this resolver:
1. Checks the local DB for matching series entries
2. Falls back to Tavily + LLM extraction for unknown series
3. Returns the aggregated profile of all books in the series

This enables similarity search against the combined DNA of an entire series,
not just a single book or author.
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.integrations import llm, tavily
from app.integrations.llm import LLM_UNAVAILABLE
from app.models.authors import Person
from app.models.books import Work
from app.models.enrichment import EnrichmentCache
from app.models.series import Series, SeriesWork
from app.models.tropes import BookTrope, Trope

logger = logging.getLogger(__name__)

# Canonical trope names — cached per-process, same pattern as query_engine
_CANONICAL_TROPE_NAMES: Optional[List[str]] = None


def _get_canonical_trope_names(db: Session) -> List[str]:
    global _CANONICAL_TROPE_NAMES
    if _CANONICAL_TROPE_NAMES is None:
        rows = db.execute(select(Trope.canonical_name)).scalars().all()
        _CANONICAL_TROPE_NAMES = sorted(rows)
        logger.info(f"Cached {len(_CANONICAL_TROPE_NAMES)} canonical trope names")
    return _CANONICAL_TROPE_NAMES


@dataclass
class SeriesContext:
    """Aggregated profile of a series for similarity search."""

    series_title: str
    author_name: str
    person_uuid: Optional[str] = None
    book_count: int = 0
    work_uuids: List[str] = field(default_factory=list)
    book_titles: List[str] = field(default_factory=list)  # from Tavily resolution
    aggregated_tropes: List[Tuple[str, float]] = field(
        default_factory=list
    )  # (name, avg_confidence)
    aggregated_tower1: Dict[str, float] = field(default_factory=dict)
    series_description: str = ""  # Natural-language vibe from Tavily
    source: str = "db"  # "db" | "tavily"


def resolve_series_from_query(db: Session, raw_query: str) -> Optional[SeriesContext]:
    """
    Try to detect and resolve a series mention in a query.
    Returns SeriesContext if a series is found, None otherwise.

    Strategy:
      1. Extract candidate series name via LLM (cheap call, small prompt)
      2. Check local DB for matching series
      3. If DB miss, try Tavily + LLM extraction
    """
    candidate = _extract_series_candidate(raw_query)
    if not candidate:
        return None

    series_name, author_hint = candidate
    logger.info(
        f"Series candidate extracted: '{series_name}' (author hint: {author_hint})"
    )

    # Layer 1: Local DB
    ctx = _resolve_from_db(db, series_name, author_hint)
    if ctx:
        ctx.source = "db"
        logger.info(
            f"Series resolved from DB: {ctx.series_title} ({ctx.book_count} books)"
        )
        return ctx

    # Layer 2: Tavily + LLM
    ctx = _resolve_from_tavily(db, series_name, author_hint)
    if ctx:
        ctx.source = "tavily"
        logger.info(
            f"Series resolved from Tavily: {ctx.series_title} ({ctx.book_count} books)"
        )
        _persist_series(db, ctx)
        return ctx

    return None


# ------------------------------------------------------------------ #
# Layer 1: Local DB lookup                                            #
# ------------------------------------------------------------------ #


def _extract_series_candidate(raw_query: str) -> Optional[Tuple[str, Optional[str]]]:
    """Use a lightweight LLM call to extract a series name from the query."""
    prompt = (
        f'User query: "{raw_query}"\n\n'
        "If the user mentions a book SERIES by name, extract it. "
        "A series is a multi-book collection like 'Harry Potter', 'Sigma Sin', "
        "'A Court of Thorns and Roses'. Do NOT extract single book titles or "
        "author names as series.\n\n"
        'Output JSON: {{"series_name": "Series Name" or null, '
        '"author_hint": "Author Name" or null}}'
    )
    try:
        result = llm.complete(prompt, require_json=True, timeout=10)
        if result == LLM_UNAVAILABLE or not isinstance(result, dict):
            return None
        name = (result.get("series_name") or "").strip()
        if not name or len(name) < 2:
            return None
        author = (result.get("author_hint") or "").strip() or None
        return name, author
    except Exception:
        return None


def _resolve_from_db(
    db: Session, series_name: str, author_hint: Optional[str]
) -> Optional[SeriesContext]:
    """Search local Series table for a matching series and load its books."""
    query = select(Series).where(func.lower(Series.title).contains(series_name.lower()))
    if author_hint:
        # If we have an author hint, narrow the search
        query = query.join(Person).where(
            func.lower(Person.canonical_name).contains(author_hint.lower())
        )
    series = db.execute(query).scalars().first()
    if not series:
        return None

    # Load all series works with their tropes and Tower 1 profiles
    sw_rows = (
        db.execute(
            select(SeriesWork)
            .options(
                joinedload(SeriesWork.work)
                .joinedload(Work.tropes)
                .joinedload(BookTrope.trope)
            )
            .where(SeriesWork.series_uuid == series.series_uuid)
            .where(SeriesWork.is_core_storyline == True)
            .order_by(SeriesWork.order_float)
        )
        .unique()
        .scalars()
        .all()
    )

    if not sw_rows:
        return None

    work_uuids = [str(sw.work_uuid) for sw in sw_rows]
    author_name = series.person.canonical_name if series.person else "Unknown"

    # Aggregate tropes across all series books
    trope_scores: Dict[str, List[float]] = {}
    for sw in sw_rows:
        for bt in sw.work.tropes or []:
            name = bt.trope.canonical_name
            if name not in trope_scores:
                trope_scores[name] = []
            trope_scores[name].append(bt.confidence_score)

    aggregated_tropes = sorted(
        [(name, sum(scores) / len(scores)) for name, scores in trope_scores.items()],
        key=lambda x: x[1],
        reverse=True,
    )

    # Aggregate Tower 1 profiles (average across books)
    caches = (
        db.execute(
            select(EnrichmentCache).where(
                EnrichmentCache.work_uuid.in_([sw.work_uuid for sw in sw_rows])
            )
        )
        .scalars()
        .all()
    )
    aggregated_tower1: Dict[str, float] = {}
    count = 0
    for cache in caches:
        if cache.tower1_snapshot and isinstance(cache.tower1_snapshot, dict):
            count += 1
            for k, v in cache.tower1_snapshot.items():
                if isinstance(v, (int, float)):
                    aggregated_tower1[k] = aggregated_tower1.get(k, 0.0) + float(v)
    if count > 0:
        aggregated_tower1 = {
            k: round(v / count, 4) for k, v in aggregated_tower1.items()
        }

    return SeriesContext(
        series_title=series.title,
        author_name=author_name,
        person_uuid=str(series.person_uuid),
        book_count=len(work_uuids),
        work_uuids=work_uuids,
        aggregated_tropes=aggregated_tropes,
        aggregated_tower1=aggregated_tower1,
    )


# ------------------------------------------------------------------ #
# Layer 2: Tavily + LLM extraction                                     #
# ------------------------------------------------------------------ #


def _resolve_from_tavily(
    db: Session, series_name: str, author_hint: Optional[str]
) -> Optional[SeriesContext]:
    """Search Tavily for series info and extract with LLM."""
    query = f'"{series_name}" series books'
    if author_hint:
        query = f"{author_hint} {query}"

    try:
        results = tavily.search(query, search_depth="basic")
        if not results or not results.get("results"):
            return None

        # Combine snippet text from top results
        snippets = "\n".join(
            r.get("content", "")[:400] for r in results.get("results", [])[:5]
        )
        if len(snippets) < 50:
            return None

        # LLM extracts structured series info from web snippets
        prompt = (
            f"Series: {series_name}\n"
            f"Author: {author_hint or 'unknown'}\n\n"
            f"Web search results about this series:\n{snippets[:2000]}\n\n"
            "1. Extract the book titles in this series in reading order. "
            "Only include confirmed titles.\n"
            "2. Write a 1-2 sentence vibe description capturing the series's "
            "tone, tropes, and emotional register. Be specific — use the "
            "language readers and reviewers use on Goodreads/Reddit.\n"
            "3. Extract specific trope names from the list below. Max 8.\n\n"
            f"Canonical trope list: {_get_canonical_trope_names(db)}\n\n"
            'Output JSON: {{"series_title": "string", "author": "string", '
            '"books": [{{"title": "Book Title", "order": 1}}, ...], '
            '"vibe_description": "string", "tropes": ["Trope Name", ...]}}'
        )
        result = llm.complete(prompt, require_json=True, timeout=15)
        if result == LLM_UNAVAILABLE or not isinstance(result, dict):
            return None

        books = result.get("books") or []
        if len(books) < 2:
            return None

        resolved_title = result.get("series_title") or series_name
        resolved_author = result.get("author") or author_hint or "Unknown"
        vibe = (result.get("vibe_description") or "").strip()

        # Validate extracted tropes against canonical list
        raw_tropes = result.get("tropes") or []
        known = set(_get_canonical_trope_names(db))
        validated_tropes = [
            (t, 0.9) for t in raw_tropes if isinstance(t, str) and t.strip() in known
        ][:8]

        # Feed non-canonical tropes to orphan queue for taxonomy growth
        _phantom_tropes = [
            t
            for t in raw_tropes
            if isinstance(t, str) and t.strip() and t.strip() not in known
        ]
        if _phantom_tropes:
            _feed_orphans(db, _phantom_tropes)

        return SeriesContext(
            series_title=resolved_title,
            author_name=resolved_author,
            book_count=len(books),
            work_uuids=[],
            book_titles=[b.get("title", "") for b in books if b.get("title")],
            aggregated_tropes=validated_tropes,
            aggregated_tower1={},
            series_description=vibe,
        )

    except Exception as e:
        logger.warning(f"Tavily series resolution failed for '{series_name}': {e}")
        return None


def _persist_series(db: Session, ctx: SeriesContext) -> None:
    """Persist a Tavily-resolved series to the DB so future lookups hit Layer 1."""
    try:
        person = db.execute(
            select(Person).where(
                func.lower(Person.canonical_name) == ctx.author_name.lower()
            )
        ).scalar_one_or_none()
        if not person:
            person = Person(canonical_name=ctx.author_name)
            db.add(person)
            db.flush()

        existing = db.execute(
            select(Series).where(
                Series.person_uuid == person.person_uuid,
                func.lower(Series.title) == ctx.series_title.lower(),
            )
        ).scalar_one_or_none()
        if not existing:
            existing = Series(
                title=ctx.series_title,
                person_uuid=person.person_uuid,
                total_core_works=ctx.book_count,
            )
            db.add(existing)
            db.flush()
            logger.info(
                f"Persisted new series: {ctx.series_title} by {ctx.author_name}"
            )
    except Exception as e:
        logger.warning(f"Failed to persist series {ctx.series_title}: {e}")


def _feed_orphans(db: Session, tropes: List[str]) -> None:
    """Feed non-canonical trope names to the orphan queue for taxonomy growth."""
    try:
        from datetime import datetime, timezone

        for tag in tropes[:5]:
            db.execute(
                text(
                    "INSERT INTO orphan_queue (tag_text, source, frequency_count, "
                    "first_seen, last_seen, llm_closest_match, llm_confidence) "
                    "VALUES (:tag, 'tavily_series', 1, now(), now(), NULL, NULL) "
                    "ON CONFLICT (tag_text) DO UPDATE SET "
                    "frequency_count = orphan_queue.frequency_count + 1, "
                    "last_seen = now()"
                ),
                {"tag": tag},
            )
        db.commit()
        logger.info(f"Fed {len(tropes[:5])} non-canonical tropes to orphan queue")
    except Exception as e:
        logger.warning(f"Failed to feed orphans: {e}")
