"""
is_narrative Repair Script
Stamps is_narrative=False on already-enriched books that are clearly non-fiction.

Two passes:
  1. Known list — fast, no LLM, marks obvious non-fiction immediately.
  2. LLM pass — for books with ambiguous categories (narrative non-fiction, memoir),
     asks the LLM to classify using just title + description.

Run: PYTHONPATH=$PWD .venv/bin/python scripts/repair_is_narrative.py [--llm]
     --llm flag enables the LLM pass (costs API calls, skip if only doing known list).
"""

import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Register all SQLAlchemy model relationships — must happen before any query
import app.models.authors       # noqa: F401
import app.models.books         # noqa: F401
import app.models.enrichment    # noqa: F401
import app.models.events        # noqa: F401
import app.models.recommendations  # noqa: F401
import app.models.series        # noqa: F401
import app.models.tbr           # noqa: F401
import app.models.tropes        # noqa: F401
import app.models.users         # noqa: F401

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from app.config import settings
from app.models.books import Work
from app.models.enrichment import EnrichmentCache

# -----------------------------------------------------------------
# Pass 1: Known non-fiction — classify without LLM.
# Add any title (lowercase) here that is definitively non-fiction.
# -----------------------------------------------------------------
KNOWN_NON_FICTION: set[str] = {
    # History / science
    "sapiens",
    "thinking, fast and slow",
    "a brief history of time",
    "the selfish gene",
    # Philosophy
    "meditations",
    "thus spoke zarathustra",
    "the will to change",
    # Self-help / psychology
    "atomic habits",
    "the body keeps the score",
    "man's search for meaning",
    # True crime / narrative non-fiction
    "in cold blood",
    # Memoir / autobiography
    "educated",
    "i know why the caged bird sings",
    "the diary of a young girl",
    "becoming",
    "born a crime",
    # Reference / essay
    "the elements of style",
    "on writing",
}

# Titles that look fictional but are actually narrative non-fiction.
# LLM pass will handle these — just flag them for review here.
NARRATIVE_NONFICTION_AMBIGUOUS: set[str] = {
    "in cold blood",   # True crime — no tropes but real events
    "educated",        # Memoir — real events, no fictional tropes
}


def _repair_known(db, dry_run: bool = False) -> int:
    """Stamp is_narrative=False for all titles in KNOWN_NON_FICTION."""
    count = 0
    works = db.execute(select(Work)).scalars().all()
    for work in works:
        if work.title.lower().strip() in KNOWN_NON_FICTION:
            cache = db.execute(
                select(EnrichmentCache).where(EnrichmentCache.work_uuid == work.work_uuid)
            ).scalar_one_or_none()
            if cache and cache.is_narrative:
                if not dry_run:
                    cache.is_narrative = False
                    logger.info(f"  ✓ {work.title} → is_narrative=False (known list)")
                else:
                    logger.info(f"  [DRY] would mark: {work.title}")
                count += 1
    if not dry_run:
        db.commit()
    return count


def _repair_llm(db, dry_run: bool = False) -> int:
    """
    LLM pass: classify is_narrative for complete books with ambiguous categories.
    Only runs books that:
      - enrichment_status == 'complete'
      - is_narrative is currently True (default — could be wrong)
      - Have Google Books categories suggesting non-fiction
    """
    from app.integrations import llm

    NON_FICTION_CATEGORY_SIGNALS = {
        "nonfiction", "non-fiction", "biography", "autobiography", "memoir",
        "history", "science", "philosophy", "psychology", "self-help",
        "true crime", "reference", "essay", "politics", "economics",
        "social science", "nature", "travel", "cooking", "health",
    }

    works = db.execute(
        select(Work).where(Work.enrichment_status == "complete")
    ).scalars().all()

    count = 0
    for work in works:
        cache = db.execute(
            select(EnrichmentCache).where(EnrichmentCache.work_uuid == work.work_uuid)
        ).scalar_one_or_none()
        if not cache or not cache.is_narrative:
            continue  # Already marked or no cache

        # Check raw_categories for non-fiction signals
        raw_cats = [c.lower() for c in (cache.raw_categories or [])]
        has_nonfiction_signal = any(
            signal in cat
            for cat in raw_cats
            for signal in NON_FICTION_CATEGORY_SIGNALS
        )
        if not has_nonfiction_signal:
            continue  # Likely fiction — skip

        # LLM classification
        desc = (cache.description or "")[:400]
        prompt = (
            f'Title: {work.title}\n'
            f'Categories: {", ".join(cache.raw_categories or [])}\n'
            f'Description: {desc}\n\n'
            'Is this a novel, story collection, or other narrative fiction/fantasy/romance/thriller? '
            'Or is it non-fiction (history, memoir, science, self-help, essay, biography, true crime, philosophy)?\n'
            'Reply with JSON: {"is_narrative": true} for fiction/narrative, {"is_narrative": false} for non-fiction.'
        )
        try:
            response = llm.complete(
                prompt=prompt,
                system="You are a book classifier. Output only valid JSON.",
                require_json=True,
            )
            raw = response.get("is_narrative", True)
            if isinstance(raw, bool) and not raw:
                if not dry_run:
                    cache.is_narrative = False
                    db.commit()
                logger.info(f"  ✓ {work.title} → is_narrative=False (LLM)")
                count += 1
            else:
                logger.debug(f"  · {work.title} → is_narrative=True (LLM confirmed fiction)")
        except Exception as e:
            logger.warning(f"  ✗ LLM failed for {work.title}: {e}")

    return count


def main():
    dry_run = "--dry-run" in sys.argv
    run_llm = "--llm" in sys.argv

    _engine = create_engine(
        settings.DATABASE_URI,
        poolclass=NullPool,
        connect_args={"connect_timeout": 10},
    )
    _Session = sessionmaker(bind=_engine)
    db = _Session()

    try:
        logger.info("Pass 1: Known non-fiction list...")
        n1 = _repair_known(db, dry_run=dry_run)
        logger.info(f"Pass 1 complete: {n1} books marked.")

        if run_llm:
            logger.info("Pass 2: LLM classification for ambiguous categories...")
            n2 = _repair_llm(db, dry_run=dry_run)
            logger.info(f"Pass 2 complete: {n2} books marked.")
        else:
            logger.info("Pass 2 skipped (add --llm to enable LLM classification).")
    finally:
        db.close()


if __name__ == "__main__":
    main()
