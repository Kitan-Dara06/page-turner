"""
Targeted re-enrichment script.
Only processes books where last_completed_step was reset (i.e. needs re-enrichment).
Skips books where last_completed_step = 'qdrant' (already fully enriched).

Run after:
    - Phase 1 DB purge (root hub rows deleted)
    - Phase 3 code changes deployed

Usage:
    PYTHONPATH=$PWD .venv/bin/python scripts/reenrich_targets.py [--dry-run]
"""

import logging
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app.models  # noqa: F401
from app.db.session import SessionLocal
from app.models.books import Work
from app.models.enrichment import EnrichmentCache
from app.services.enrichment_service import enrich_book
from sqlalchemy import select

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DRY_RUN = "--dry-run" in sys.argv


def main():
    db = SessionLocal()
    try:
        # Find all works where the pipeline needs to resume
        # (last_completed_step != 'qdrant' means not fully done)
        targets = db.execute(
            select(Work.title, Work.work_uuid, EnrichmentCache.last_completed_step,
                   EnrichmentCache.is_narrative)
            .join(EnrichmentCache, EnrichmentCache.work_uuid == Work.work_uuid)
            .where(EnrichmentCache.last_completed_step != "qdrant")
            .order_by(Work.title)
        ).all()

        if not targets:
            print("No books need re-enrichment. All at last_completed_step='qdrant'.")
            return

        print(f"Books queued for re-enrichment: {len(targets)}")
        for title, uuid, step, is_narrative in targets:
            kind = "[non-narrative]" if not is_narrative else ""
            print(f"  {title} (resume from: {step or 'start'}) {kind}")

        if DRY_RUN:
            print("\n--dry-run: no enrichment performed.")
            return

        print()
        enriched, failed = 0, 0
        for i, (title, uuid, step, is_narrative) in enumerate(targets, 1):
            # Find the author for this work (needed by enrich_book)
            from app.models.authors import Person
            person = db.execute(
                select(Person).join(Work, Work.person_uuid == Person.person_uuid)
                .where(Work.work_uuid == uuid)
            ).scalar_one_or_none()
            author_name = person.canonical_name if person else "Unknown"

            try:
                logger.info(f"[{i}/{len(targets)}] Re-enriching: {title} by {author_name}")
                work = enrich_book(
                    db,
                    title=title,
                    author_name=author_name,
                    skip_tavily=True,  # uses Wikipedia enrichment path
                )
                # Ensure flashcard_pool stays True
                cache = db.execute(
                    select(EnrichmentCache).where(EnrichmentCache.work_uuid == work.work_uuid)
                ).scalar_one()
                cache.flashcard_pool = True
                db.commit()
                enriched += 1
                logger.info(f"  ✓ Done: {title}")
            except Exception as e:
                logger.error(f"  ✗ Failed: {title} — {e}")
                db.rollback()
                failed += 1

            time.sleep(1.5)  # rate limit: Voyage + Gemini + Tavily

        print(f"\nRe-enrichment complete: {enriched} succeeded, {failed} failed.")
        if failed:
            print("Run this script again to retry failures (resume logic will skip completed steps).")

    finally:
        db.close()


if __name__ == "__main__":
    main()
