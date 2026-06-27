import os

from celery import Celery
from celery.schedules import crontab

from app.config import settings

# For Upstash Redis (rediss://), Celery needs explicit SSL config
_redis_url = settings.REDIS_URL
if _redis_url and _redis_url.startswith("rediss://"):
    # Append SSL param if not already present
    if "?ssl_cert_reqs=" not in _redis_url:
        _redis_url += "?ssl_cert_reqs=CERT_NONE"

# Initialize the Celery application
celery_app = Celery(
    "pageturner_workers",
    broker=_redis_url,
    backend=_redis_url,
)

# --- Celery Configuration ---
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # Worker optimizations for Phase 1
    worker_prefetch_multiplier=1,  # Ensures fair distribution of long-running enrichment tasks
    task_acks_late=True,  # Tasks are only acknowledged after completion (prevents data loss on crash)
)

# --- Autodiscover Tasks ---
# Celery will look for @celery_app.task decorators in these specific files
celery_app.autodiscover_tasks(
    [
        "app.workers.enrichment_tasks",
        "app.workers.author_alert_tasks",
        "app.workers.tbr_decay_tasks",
    ]
)

# --- Celery Beat Schedule Skeleton ---
# This configures the recurring background jobs defined in the SRS
celery_app.conf.beat_schedule = {
    # Implements FR-AT-02: Release Alert Generation
    "daily_author_release_check": {
        "task": "app.workers.author_alert_tasks.check_tracked_authors_for_releases",
        # Runs every day at 00:00 UTC
        "schedule": crontab(hour=0, minute=0),
        # Optional args: e.g., passing the Phase 1 limit of 50 authors per run
        "args": (50,),
    },
    # Implements FR-TBR-02: TBR Priority Decay
    "daily_tbr_priority_decay": {
        "task": "app.workers.tbr_decay_tasks.apply_tbr_decay_formula",
        # Runs every day at 02:00 UTC (staggered to avoid DB lock contention with author checks)
        "schedule": crontab(hour=2, minute=0),
    },
    # Implements Section 5.6: Enrichment Cache Refresh
    "weekly_active_book_enrichment_refresh": {
        "task": "app.workers.enrichment_tasks.refresh_active_book_cache",
        # Runs every Sunday at 04:00 UTC
        "schedule": crontab(day_of_week="sunday", hour=4, minute=0),
    },
    # Stuck partial sweeper — re-queues books that got stuck mid-enrichment
    "sweep_stuck_partials_every_5_minutes": {
        "task": "app.workers.enrichment_tasks.sweep_stuck_partials",
        "schedule": 300.0,  # every 5 minutes
    },
}
