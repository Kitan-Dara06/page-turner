import logging
import uuid
from datetime import datetime, timezone

from celery.exceptions import MaxRetriesExceededError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.books import Work
from app.models.enrichment import EnrichmentCache
from app.services import enrichment_service
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

PARTIAL_MAX_RETRIES = 3


@celery_app.task(bind=True, max_retries=5, acks_late=True)
def enrich_book_task(self, title: str, author_name: str, isbn: str = None):
    """
    Async Celery wrapper for the Book Intelligence Layer.
    Executes the enrichment pipeline with exponential backoff for API rate limits.
    """
    # Workers run in separate processes; they must spawn their own DB sessions
    db: Session = SessionLocal()

    try:
        logger.info(
            f"Task starting: Enriching '{title}' by {author_name} (Attempt {self.request.retries + 1})"
        )

        # Call the pure service function
        work = enrichment_service.enrich_book(
            db, title=title, author_name=author_name, isbn=isbn, skip_tavily=False
        )

        return {
            "status": "success",
            "work_uuid": str(work.work_uuid),
            "title": work.title,
        }

    except Exception as exc:
        logger.warning(f"Enrichment task failed for '{title}': {str(exc)}")

        # Exponential backoff: 2^retries * 60 seconds (1m, 2m, 4m, 8m, 16m)
        # This protects you from temporary OpenLibrary/Google Books rate limits
        backoff_seconds = (2**self.request.retries) * 60

        try:
            # self.retry raises an exception that Celery catches to requeue the task
            raise self.retry(exc=exc, countdown=backoff_seconds)
        except MaxRetriesExceededError:
            logger.error(f"FATAL: Max retries exceeded for book enrichment: {title}")
            # Do not raise here; return the failure state so the worker doesn't crash
            return {"status": "failed", "error": str(exc)}

    finally:
        # Crucial: Always return the connection to the pool to prevent worker lockups
        db.close()


@celery_app.task(bind=True)
def refresh_active_book_cache(self):
    """
    Scheduled beat task (runs weekly per celery_app.py).
    Finds books that have been recently interacted with but have stale enrichment data,
    and queues them for a refresh.
    """
    logger.info("Executing weekly active book enrichment refresh...")

    db: Session = SessionLocal()
    try:
        # Phase 2 implementation:
        # 1. Query `interaction_events` for recent work_uuids
        # 2. Join `enrichment_cache` where `enriched_at` > 30 days
        # 3. For each result: enrich_book_task.delay(title=work.title, ...)
        pass
    finally:
        db.close()


@celery_app.task
def sweep_stuck_partials() -> int:
    """
    Periodic beat task: find Work records stuck in ``"partial"`` enrichment
    and re-queue them for background enrichment.

    After ``PARTIAL_MAX_RETRIES`` attempts, marks them ``"partial_failed"``.
    """
    db: Session = SessionLocal()
    try:
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
                cache.partial_retry_count = (cache.partial_retry_count or 0) + 1
                db.flush()
                enrich_book_task.delay(
                    title=work.title,
                    author_name="Unknown",
                )
                re_queued += 1
                logger.info(f"Sweeper re-queued: {work.title} ({work.work_uuid})")
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
