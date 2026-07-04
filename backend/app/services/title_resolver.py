"""
Title Resolver — anchor resolution for similarity queries.

Task: given a bare title string extracted from a "books like X" query,
find the book and return its canonical tropes from the DB.

Pipeline:
  1. DB fuzzy lookup  — ILIKE trigram match on works.title
  2. Google Books     — when DB misses, resolve + create partial Work
  3. Tavily           — author name extraction only (not trope extraction)

This service does ZERO LLM calls. Tropes come from book_tropes (confidence ≥ 0.5),
not from LLM guesswork on a title string.

Tavily's role here is ONLY: "who wrote this book?" so that downstream enrichment
and the author spotlight have a name. Trope extraction from Tavily web snippets is
explicitly out of scope for this module — that's the job of the background enrichment
pipeline after the book is seeded.
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.integrations import google_books, tavily
from app.models.books import Work
from app.models.enrichment import EnrichmentCache
from app.models.tropes import BookTrope, Trope

logger = logging.getLogger(__name__)

# Minimum similarity score for fuzzy title match (0–1 range, applied post-query)
_FUZZY_MIN_WORDS = 0.5  # fraction of title words that must appear in query token


@dataclass
class TitleResolution:
    """Result of anchor title resolution."""

    work_uuid: Optional[str]  # None = book not in DB even after enrichment attempt
    title: str  # Canonical title (from DB or Google Books)
    author: Optional[str]  # Resolved author name
    trope_names: List[str] = field(default_factory=list)  # From book_tropes, conf ≥ 0.5
    anchor_defining_tropes: List[str] = field(
        default_factory=list
    )  # conf == 1.0 (identity-level)
    tower1_snapshot: Dict[str, float] = field(default_factory=dict)
    enrichment_status: str = "unknown"  # "complete" | "partial" | "pending" | "unknown"
    source: str = "miss"  # "db" | "google_books" | "tavily" | "miss"


def resolve(
    db: Session,
    anchor_title: str,
    author_hint: Optional[str] = None,
) -> Optional[TitleResolution]:
    """
    Resolve an anchor title to a TitleResolution.

    Args:
        anchor_title:  Raw title string extracted from the query, e.g.
                       "The Girl from Greenwich Street" or "girl from greenwich".
        author_hint:   Author name if the query contained "by <author>". Optional.

    Returns:
        TitleResolution if book found or seeded, None if completely unresolvable.
    """
    if not anchor_title or len(anchor_title.strip()) < 2:
        return None

    clean_title = anchor_title.strip().strip("\"'")

    # ── Layer 1: DB lookup ──────────────────────────────────────────────────────
    resolution = _resolve_from_db(db, clean_title, author_hint)
    if resolution:
        logger.info(
            f"TitleResolver DB hit: '{resolution.title}' "
            f"(status={resolution.enrichment_status}, "
            f"tropes={len(resolution.trope_names)})"
        )
        return resolution

    # ── Layer 2: Google Books ───────────────────────────────────────────────────
    resolution = _resolve_from_google_books(db, clean_title, author_hint)
    if resolution:
        logger.info(
            f"TitleResolver GB hit: '{resolution.title}' by {resolution.author} "
            f"(seeded as partial)"
        )
        return resolution

    # ── Layer 3: Tavily — author name only ─────────────────────────────────────
    resolution = _resolve_author_from_tavily(db, clean_title)
    if resolution:
        logger.info(
            f"TitleResolver Tavily author hit for '{clean_title}': "
            f"author={resolution.author}"
        )
        return resolution

    logger.info(f"TitleResolver: complete miss for '{clean_title}'")
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Layer 1: DB fuzzy lookup
# ─────────────────────────────────────────────────────────────────────────────


def _resolve_from_db(
    db: Session,
    title: str,
    author_hint: Optional[str],
) -> Optional[TitleResolution]:
    """
    Multi-pass fuzzy lookup:
      Pass A — exact case-insensitive match (fastest, most precise)
      Pass B — ILIKE contains match (handles truncated titles)
      Pass C — token-intersection fallback (handles word-order reorders)

    Author hint is used to narrow when multiple works share a title.
    """
    work = None

    # Pass A: exact
    stmt = select(Work).where(func.lower(Work.title) == title.lower())
    if author_hint:
        from app.models.authors import Person

        stmt = stmt.join(Person, Work.person_uuid == Person.person_uuid).where(
            func.lower(Person.canonical_name).contains(author_hint.split()[-1].lower())
        )
    work = db.execute(stmt).scalars().first()

    # Pass B: ILIKE contains
    if not work:
        stmt = select(Work).where(Work.title.ilike(f"%{title}%"))
        if author_hint:
            from app.models.authors import Person

            stmt = stmt.join(Person, Work.person_uuid == Person.person_uuid).where(
                func.lower(Person.canonical_name).contains(
                    author_hint.split()[-1].lower()
                )
            )
        candidates = db.execute(stmt).scalars().all()
        if candidates:
            # Prefer the candidate with the most title-word overlap
            work = _best_fuzzy_match(title, candidates)

    # Pass C: token intersection (handles reordering / partial title)
    if not work:
        query_tokens = set(_tokenize(title))
        if len(query_tokens) >= 2:
            # Pull all works whose title contains any of the significant tokens
            significant = [t for t in query_tokens if len(t) > 3]
            if significant:
                from sqlalchemy import or_

                conditions = [Work.title.ilike(f"%{tok}%") for tok in significant]
                candidates = (
                    db.execute(select(Work).where(or_(*conditions))).scalars().all()
                )
                if candidates:
                    work = _best_fuzzy_match(title, candidates)

    if not work:
        return None

    return _build_resolution_from_work(db, work, source="db")


def _tokenize(title: str) -> List[str]:
    """Lowercase word tokens, strip punctuation, filter stopwords."""
    _STOPWORDS = {"a", "an", "the", "of", "and", "in", "on", "at", "to", "by", "for"}
    return [
        w
        for w in re.sub(r"[^\w\s]", "", title.lower()).split()
        if w not in _STOPWORDS
    ]


def _best_fuzzy_match(query: str, candidates: List[Work]) -> Optional[Work]:
    """Return the Work whose title has the highest token overlap with query."""
    query_tokens = set(_tokenize(query))
    best_work = None
    best_score = 0.0

    for work in candidates:
        work_tokens = set(_tokenize(work.title))
        if not work_tokens:
            continue
        intersection = query_tokens & work_tokens
        # Jaccard-ish: |intersection| / |query_tokens| — rewards query coverage
        score = len(intersection) / max(len(query_tokens), 1)
        if score > best_score:
            best_score = score
            best_work = work

    if best_score < _FUZZY_MIN_WORDS:
        return None
    return best_work


def _build_resolution_from_work(
    db: Session, work: Work, source: str
) -> TitleResolution:
    """Load tropes + Tower1 from DB for a resolved Work."""
    from app.models.authors import Person

    person = db.execute(
        select(Person).where(Person.person_uuid == work.person_uuid)
    ).scalar_one_or_none()
    author = person.canonical_name if person else None

    cache = db.execute(
        select(EnrichmentCache).where(EnrichmentCache.work_uuid == work.work_uuid)
    ).scalar_one_or_none()

    # Load tropes from book_tropes (confidence ≥ 0.5, ordered descending)
    trope_rows = db.execute(
        select(Trope.canonical_name, BookTrope.confidence_score)
        .join(BookTrope, BookTrope.trope_uuid == Trope.trope_uuid)
        .where(BookTrope.work_uuid == work.work_uuid)
        .where(BookTrope.confidence_score >= 0.5)
        .order_by(BookTrope.confidence_score.desc())
    ).all()

    trope_names = [name for name, _ in trope_rows]
    # Identity-level tropes (conf == 1.0) — drive zero-overlap gate in reranker
    defining_tropes = [name for name, score in trope_rows if score == 1.0]

    tower1: Dict[str, float] = {}
    enrichment_status = work.enrichment_status or "unknown"
    if cache and cache.tower1_snapshot and isinstance(cache.tower1_snapshot, dict):
        tower1 = {
            k: float(v)
            for k, v in cache.tower1_snapshot.items()
            if isinstance(v, (int, float))
        }

    return TitleResolution(
        work_uuid=str(work.work_uuid),
        title=work.title,
        author=author,
        trope_names=trope_names,
        anchor_defining_tropes=defining_tropes,
        tower1_snapshot=tower1,
        enrichment_status=enrichment_status,
        source=source,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Layer 2: Google Books
# ─────────────────────────────────────────────────────────────────────────────


def _resolve_from_google_books(
    db: Session,
    title: str,
    author_hint: Optional[str],
) -> Optional[TitleResolution]:
    """
    Search Google Books for the title. On hit:
      - Create/update Work + EnrichmentCache (partial)
      - Fire background enrichment task
      - Return TitleResolution with source="google_books"

    Returns None on miss or API failure.
    """
    try:
        author_for_search = author_hint or ""
        results = google_books.search_by_title_author(title, author_for_search)
        if not results:
            return None

        vol = results[0].get("volumeInfo", {})
        resolved_title = vol.get("title", "").strip()
        gb_authors = vol.get("authors", [])
        resolved_author = gb_authors[0] if gb_authors else author_hint

        if not resolved_title or not resolved_author:
            return None

        # Reject if title mismatch is too severe (GB can return noise)
        if _title_distance(title, resolved_title) < 0.3:
            logger.info(
                f"GB title mismatch: query='{title}', returned='{resolved_title}' — rejected"
            )
            return None

        # Seed into DB using the shared hot-path helper
        from app.services.enrichment_service import _resolve_work_and_cache, _run_google_books
        from app.workers.enrichment_tasks import enrich_book_task

        savepoint = db.begin_nested()
        try:
            work, cache = _resolve_work_and_cache(db, resolved_title, resolved_author, None)
            _run_google_books(db, work, cache, resolved_title, resolved_author, None)

            has_metadata = bool(cache.description or cache.raw_categories)
            if not has_metadata:
                savepoint.rollback()
                return None

            work.enrichment_status = "partial"
            cache.last_completed_step = "google_books"
            cache.flashcard_pool = False
            db.flush()

            enrich_book_task.delay(title=resolved_title, author_name=resolved_author)
            logger.info(
                f"TitleResolver: seeded '{resolved_title}' by '{resolved_author}' (partial)"
            )
        except Exception as e:
            logger.warning(f"TitleResolver GB seed failed for '{title}': {e}")
            savepoint.rollback()
            return None

        return TitleResolution(
            work_uuid=str(work.work_uuid),
            title=resolved_title,
            author=resolved_author,
            trope_names=[],  # No tropes yet — enrichment running in background
            anchor_defining_tropes=[],
            tower1_snapshot={},
            enrichment_status="partial",
            source="google_books",
        )

    except Exception as e:
        logger.warning(f"TitleResolver Google Books failed for '{title}': {e}")
        return None


def _title_distance(query: str, candidate: str) -> float:
    """Token overlap ratio between query title and Google Books result title."""
    q_tokens = set(_tokenize(query))
    c_tokens = set(_tokenize(candidate))
    if not q_tokens or not c_tokens:
        return 0.0
    return len(q_tokens & c_tokens) / max(len(q_tokens), 1)


# ─────────────────────────────────────────────────────────────────────────────
# Layer 3: Tavily — author name resolution only
# ─────────────────────────────────────────────────────────────────────────────


def _resolve_author_from_tavily(
    db: Session,
    title: str,
) -> Optional[TitleResolution]:
    """
    Final fallback: ask Tavily "who wrote <title>?"

    SCOPE: author extraction ONLY.
    We do NOT extract tropes from Tavily snippets here. Web prose like
    "atmospheric historical mystery with gothic undertones" cannot be reliably
    mapped to canonical trope names without the full enrichment pipeline.
    Trope extraction from Tavily happens in the background enrichment task,
    not on the hot path.

    On author hit: attempt Google Books resolution with the resolved author name.
    Returns TitleResolution with source="tavily" if author found, None otherwise.
    """
    try:
        results = tavily.search(
            f'"{title}" book author',
            search_depth="basic",
            include_domains=[
                "goodreads.com",
                "amazon.com",
                "thestorygraph.com",
                "barnesandnoble.com",
            ],
        )
        entries = results.get("results", [])
        if not entries:
            return None

        # Extract author name from search result snippets via simple regex
        # (no LLM on hot path for author extraction — regex is sufficient)
        author = _extract_author_from_snippets(title, entries[:4])
        if not author:
            return None

        logger.info(f"TitleResolver Tavily: '{title}' → author='{author}'")

        # Retry Google Books with the resolved author
        gb_resolution = _resolve_from_google_books(db, title, author)
        if gb_resolution:
            gb_resolution.source = "tavily"
            return gb_resolution

        # Author found but GB still missed — return a bare resolution
        # so the engine at least knows the author name for spotlight
        return TitleResolution(
            work_uuid=None,
            title=title,
            author=author,
            trope_names=[],
            anchor_defining_tropes=[],
            tower1_snapshot={},
            enrichment_status="unknown",
            source="tavily",
        )

    except Exception as e:
        logger.warning(f"TitleResolver Tavily fallback failed for '{title}': {e}")
        return None


def _extract_author_from_snippets(title: str, entries: List[dict]) -> Optional[str]:
    """
    Lightweight author extraction from web snippets.
    Looks for "by <Author Name>" patterns near the title mention.
    No LLM — purely regex on the hot path.
    """
    combined = " ".join(e.get("content", "")[:300] for e in entries)
    title_words = title.lower().split()[:3]

    # Pattern: "Title ... by FirstName LastName" or "by Author, Title"
    patterns = [
        r"\bby\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})",
        r"author[:\s]+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})",
        r"written\s+by\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})",
    ]

    for pattern in patterns:
        for match in re.finditer(pattern, combined):
            candidate = match.group(1).strip()
            # Sanity: reject common false positives
            if candidate.lower() in {
                "the author",
                "an author",
                "a bestselling",
                "the new york",
            }:
                continue
            # Prefer candidates near a title word mention
            ctx_start = max(0, match.start() - 200)
            ctx = combined[ctx_start : match.end() + 100].lower()
            if any(tw in ctx for tw in title_words):
                return candidate
            # Accept even without proximity on first reasonable match
            return candidate

    return None


# ─────────────────────────────────────────────────────────────────────────────
# Utility: extract anchor title from raw query
# ─────────────────────────────────────────────────────────────────────────────

_SIMILARITY_PATTERNS = [
    r"(?:like|similar to|reminiscent of|more like|in the style of)\s+(.+?)(?:\s+by\s+|$)",
    r"(?:another|more)\s+(.+?)(?:\s+by\s+|\s+type|\s+kind|$)",
]

_AUTHOR_HINT_PATTERN = re.compile(
    r"\s+by\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})", re.IGNORECASE
)


def extract_anchor_from_query(
    raw_query: str,
) -> Tuple[Optional[str], Optional[str]]:
    """
    Extract (anchor_title, author_hint) from a similarity query.

    "books like The Girl from Greenwich Street by Lauren Willig"
        → ("The Girl from Greenwich Street", "Lauren Willig")
    "something like red rising"
        → ("red rising", None)
    "I want more books like it"
        → (None, None)

    Returns (None, None) when no anchor can be found.
    """
    query = raw_query.strip()

    for pattern in _SIMILARITY_PATTERNS:
        match = re.search(pattern, query, re.IGNORECASE)
        if match:
            full_anchor = match.group(1).strip().strip("\"'")
            if len(full_anchor) < 3:
                continue

            # Split off "by <Author>" if present
            author_match = _AUTHOR_HINT_PATTERN.search(full_anchor)
            if author_match:
                author_hint = author_match.group(1).strip()
                anchor_title = full_anchor[: author_match.start()].strip()
            else:
                anchor_title = full_anchor
                # Also check the full query for "by <Author>" after the title
                full_author = _AUTHOR_HINT_PATTERN.search(query)
                author_hint = full_author.group(1).strip() if full_author else None

            if anchor_title and len(anchor_title) >= 3:
                return anchor_title, author_hint

    return None, None
