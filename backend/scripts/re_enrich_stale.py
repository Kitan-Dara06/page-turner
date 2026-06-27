"""
Targeted LLM re-extraction for stale taxonomy versions.

Only re-runs the LLM extraction + Qdrant steps for books whose existing
trope assignments suggest they could match newly-added taxonomy nodes.
Skips Google Books, OpenLibrary, and Tavily entirely.

Usage:
    PYTHONPATH=$PWD .venv/bin/python scripts/re_enrich_stale.py [--dry-run] [--limit N]
"""

import logging
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import func, select

import app.models  # noqa: F401
from app.config import settings
from app.db.session import SessionLocal
from app.models.authors import Person
from app.models.books import Work
from app.models.enrichment import EnrichmentCache
from app.models.tropes import BookTrope, Trope
from app.services.enrichment_service import enrich_book

logging.basicConfig(level=logging.INFO, format="%(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)

DRY_RUN = "--dry-run" in sys.argv
LIMIT = None
for i, arg in enumerate(sys.argv):
    if arg == "--limit" and i + 1 < len(sys.argv):
        LIMIT = int(sys.argv[i + 1])

# Ancestor nodes whose children were added in taxonomy version bumps.
# Books with any trope in these ancestor sets are eligible for re-extraction.
ANCESTOR_FILTERS = {
    # v8.0: Literary Fiction sub-genres (Absurdist, Postcolonial, Bildungsroman, etc.)
    10: [
        "Literary Fiction",
        "Existentialism",
        "Identity/Self-Discovery",
        "Colonialism/Post-Colonialism",
        "Grief/Loss",
        "Memory & Time",
        "Historical",
        "Gothic Horror",
        "Moral Ambiguity",
        "Reality",
        "War & Its Aftermath",
        "Systemic/Societal Conflict",
    ],
    # v9.0: Non-Fiction nodes (Memoir, True Crime, Narrative Nonfiction, etc.)
    11: [
        "Nonfiction",
        "Narrative Nonfiction",
        "Memoir",
        "True Crime Narrative",
        "Identity/Self-Discovery",
        "Systemic/Societal Conflict",
        "Mysteries",
    ],
    # v10.0: Historical Fiction (War Fiction, Victorian, Ancient, Medieval, etc.)
    12: [
        "Historical Fiction",
        "Literary Fiction",
        "Historical",
        "Gothic Horror",
        "War & Its Aftermath",
        "Epic",
        "Mysteries",
        "Quests",
        "Alternate History",
        "Gaslamp Fantasy",
        "Colonialism/Post-Colonialism",
        "Class Struggle",
        "Survival/External",
        "Bildungsroman",
        "Experimental Fiction",
    ],
    # v11.0: Mystery Fiction + Memoir/Biography refinements
    13: [
        "Mysteries",
        "Whodunit",
        "Anti-Hero",
        "Psychological Horror",
        "Psychological Thriller",
        "Domestic Thriller",
        "Legal Thriller",
        "Cozy Mystery",
        "Man vs Technology",
        "Memoir",
        "Biography",
        "Bildungsroman",
        "Grief/Loss",
        "Systemic/Societal Conflict",
        "Literary Fiction",
        "Popular Science",
    ],
}


def main():
    db = SessionLocal()
    current_version = settings.TAXONOMY_VERSION
    stale = set()
    books_by_version = {}

    try:
        # Find all stale enrichment caches
        stale_entries = db.execute(
            select(EnrichmentCache.work_uuid, EnrichmentCache.taxonomy_version).where(
                EnrichmentCache.taxonomy_version < current_version,
                EnrichmentCache.flashcard_pool == True,
            )
        ).all()

        if not stale_entries:
            logger.info("No stale enrichments found.")
            return

        # Group by version
        for wu, ver in stale_entries:
            books_by_version.setdefault(ver, []).append(wu)

        # For each version, filter to books with ancestor tropes
        for version, work_uuids in books_by_version.items():
            ancestors = ANCESTOR_FILTERS.get(version, [])
            if not ancestors:
                continue

            ancestor_ids = (
                db.execute(
                    select(Trope.trope_uuid).where(Trope.canonical_name.in_(ancestors))
                )
                .scalars()
                .all()
            )

            if not ancestor_ids:
                continue

            matching = (
                db.execute(
                    select(func.distinct(BookTrope.work_uuid)).where(
                        BookTrope.work_uuid.in_(work_uuids),
                        BookTrope.trope_uuid.in_(ancestor_ids),
                    )
                )
                .scalars()
                .all()
            )

            for wu in matching:
                stale.add(str(wu))

        total = len(stale)
        logger.info(
            f"Stale total: {len(stale_entries)} books, "
            f"ancestor-filtered: {total} eligible for LLM re-extraction"
        )

        if not stale:
            logger.info("No books match ancestor filters. Nothing to re-enrich.")
            return

        # Reset last_completed_step to 'openlibrary' to resume from LLM extraction
        reset_count = 0
        for wu in stale:
            cache = db.execute(
                select(EnrichmentCache).where(EnrichmentCache.work_uuid == wu)
            ).scalar_one_or_none()
            if cache and cache.last_completed_step != "openlibrary":
                cache.last_completed_step = "openlibrary"
                reset_count += 1

        db.commit()
        logger.info(
            f"Reset {reset_count} enrichment caches to resume from LLM extraction."
        )

        if DRY_RUN:
            logger.info(f"DRY RUN: would re-enrich {total} books. No changes made.")
            return

        # Re-enrich
        enriched = failed = 0
        for i, wu_str in enumerate(sorted(stale), 1):
            if LIMIT and i > LIMIT:
                logger.info(f"Limit {LIMIT} reached. Stopping.")
                break

            wu = wu_str
            work = db.execute(
                select(Work).where(Work.work_uuid == wu)
            ).scalar_one_or_none()

            if not work:
                continue

            person = db.execute(
                select(Person).where(Person.person_uuid == work.person_uuid)
            ).scalar_one_or_none()
            author_name = person.canonical_name if person else "Unknown"

            try:
                logger.info(f"[{i}/{total}] Re-extracting: {work.title}")
                enrich_book(
                    db,
                    title=work.title,
                    author_name=author_name,
                    skip_tavily=True,
                )
                enriched += 1
                logger.info(f"  ✓ Done: {work.title}")
            except Exception as e:
                logger.error(f"  ✗ Failed: {work.title} — {e}")
                db.rollback()
                failed += 1

            time.sleep(0.5)

        logger.info(f"Complete. enriched={enriched} failed={failed}")

    finally:
        db.close()


if __name__ == "__main__":
    main()
