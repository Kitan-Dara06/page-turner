"""
Background Enrichment Tasks — deferred full enrichment and stuck-partial sweeper.

Two tasks:

1. ``enrich_book_background(work_uuid)``
   Called by the hot path after Google Books metadata has been fetched.
   Runs OpenLibrary, LLM extraction, Tavily verification, and Qdrant upsert.
   Safe to retry — uses ``last_completed_step`` resume logic.

2. ``sweep_stuck_partials()``
   Celery Beat periodic task (every 5 minutes). Finds Work records stuck in
   ``"partial"`` for more than 5 minutes and re-queues them.
   After ``PARTIAL_MAX_RETRIES`` attempts, marks ``enrichment_status = "partial_failed"``.
"""

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from app.config import settings
from app.db.session import SessionLocal
from app.models.books import Work
from app.models.enrichment import EnrichmentCache
from app.services.enrichment_service import enrich_book
from app.tasks.celery_app import celery

logger = logging.getLogger(__name__)

# ── Configuration ────────────────────────────────────────────────────────────

# How many times a partial book gets re-queued before being abandoned.
PARTIAL_MAX_RETRIES = 3

# How old (in seconds) a partial must be before the sweeper considers it stuck.
PARTIAL_STUCK_AGE_SECONDS = 300  # 5 minutes


# ── Task 1: Complete enrichment for a partially-enriched book ────────────────


@celery.task(
    bind=True,
    max_retries=3,
    default_retry_delay=30,  # seconds between retries
    acks_late=True,  # don't lose the task if the worker crashes mid-execution
)
def enrich_book_background(self, work_uuid: str, skip_tavily: bool = True) -> str:
    """
    Background enrichment: runs steps 2-5 of the pipeline
    (OpenLibrary → LLM extraction → Tavily → Qdrant) on a book that
    already has Google Books metadata.

    skip_tavily=True (default): seed/hot-path books skip Tavily.
    skip_tavily=False: user-requested enrichment runs full Tavily check.

    The enrichment pipeline resumes from ``last_completed_step``, so if a
    previous background attempt completed OpenLibrary but failed on LLM
    extraction, this retry picks up at LLM extraction — no rework.
    """
    db = SessionLocal()
    try:
        work = db.execute(
            select(Work).where(Work.work_uuid == uuid.UUID(work_uuid))
        ).scalar_one_or_none()

        if not work:
            logger.warning(f"Background enrich: work {work_uuid} not found, skipping.")
            return "not_found"

        if work.enrichment_status not in ("partial", "pending"):
            logger.info(
                f"Background enrich: {work.title} status is '{work.enrichment_status}' — "
                "already complete or failed, skipping."
            )
            return work.enrichment_status

        title = work.title

        # Resolve author name from the Person relationship
        from app.models.authors import Person

        person = db.execute(
            select(Person).where(Person.person_uuid == work.person_uuid)
        ).scalar_one_or_none()
        author_name = person.canonical_name if person else "Unknown"

        # enrich_book handles resume from last_completed_step, sets
        # enrichment_status = "complete" on success, and commits.
        enrich_book(db, title, author_name, skip_tavily=skip_tavily)
        logger.info(f"Background enrich complete: {title}")
        return "complete"

    except Exception as exc:
        logger.error(f"Background enrich failed for {work_uuid}: {exc}")
        # Increment retry count on cache so the sweeper can detect exhaustion
        try:
            cache = db.execute(
                select(EnrichmentCache).where(
                    EnrichmentCache.work_uuid == uuid.UUID(work_uuid)
                )
            ).scalar_one_or_none()
            if cache is not None:
                cache.partial_retry_count = (cache.partial_retry_count or 0) + 1
                db.commit()
        except Exception:
            db.rollback()
        raise self.retry(exc=exc)

    finally:
        db.close()


# ── Task 2: Stuck-partial sweeper (Celery Beat) ─────────────────────────────


@celery.task
def sweep_stuck_partials() -> int:
    """
    Periodic task: find Work records stuck in ``"partial"`` for >5 minutes
    and re-queue them for background enrichment.

    After ``PARTIAL_MAX_RETRIES`` attempts, marks them ``"partial_failed"``
    so they stop appearing as "Newly added" without explanation.
    """
    db = SessionLocal()
    try:
        cutoff = datetime.now(timezone.utc)

        # We need to find partial Work records whose cache hasn't been
        # enriched recently. Since enriched_at stays at its original value
        # for partials, we check last_completed_step instead — if it's
        # still "google_books" and the record is old, it's stuck.

        stuck = db.execute(
            select(Work, EnrichmentCache)
            .join(EnrichmentCache, Work.work_uuid == EnrichmentCache.work_uuid)
            .where(Work.enrichment_status == "partial")
            .where(EnrichmentCache.last_completed_step == "google_books")
            .where(EnrichmentCache.partial_retry_count < PARTIAL_MAX_RETRIES)
        ).all()

        if not stuck:
            return 0

        re_queued = 0
        for work, cache in stuck:
            try:
                title = work.title

                # Resolve author from Person relationship
                from app.models.authors import Person as _Person

                _person = db.execute(
                    select(_Person).where(_Person.person_uuid == work.person_uuid)
                ).scalar_one_or_none()
                author_name = _person.canonical_name if _person else "Unknown"

                # Bump retry count before firing so if the task fails again,
                # the next sweep picks up the incremented count.
                cache.partial_retry_count = (cache.partial_retry_count or 0) + 1
                db.flush()

                enrich_book_background.delay(str(work.work_uuid))
                re_queued += 1
                logger.info(f"Sweeper re-queued: {title} ({work.work_uuid})")

            except Exception as e:
                logger.error(f"Sweeper failed to re-queue {work.work_uuid}: {e}")
                db.rollback()

        db.commit()
        logger.info(f"Sweeper: re-queued {re_queued} stuck partials.")
        return re_queued

    except Exception as e:
        logger.error(f"Sweeper query failed: {e}")
        db.rollback()
        return 0
    finally:
        db.close()
