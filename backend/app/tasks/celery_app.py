"""
Celery Application — configured from the shared PageTurner settings.

Single worker pool shared across all background task modules.
Uses the same Upstash Redis URL as the result backend and broker.
"""

import ssl

from celery import Celery

from app.config import settings

# Build broker/backend URL using the same Redis config the rest of the app uses.
# UPSTASH Redis over TLS requires the rediss:// scheme and SSL cert options.
broker_url = settings.REDIS_URL or "redis://localhost:6379/0"
result_backend = broker_url

celery = Celery(
    "pageturner",
    broker=broker_url,
    backend=result_backend,
)

# ── Force task module import ───────────────────────────────────────────────
# The @celery.task decorator registers the task function in celery.tasks at
# module import time. Importing the module here ensures both the worker and
# beat scheduler see sweep_stuck_partials and enrich_book_background.
from app.tasks import enrichment_tasks  # noqa: F401

# TLS config — required for Upstash (rediss://), harmless on local Redis
celery.conf.broker_use_ssl = {"ssl_cert_reqs": ssl.CERT_NONE}
celery.conf.redis_backend_use_ssl = {"ssl_cert_reqs": ssl.CERT_NONE}

# Task serialization (standard JSON — pickle not needed)
celery.conf.task_serializer = "json"
celery.conf.result_serializer = "json"
celery.conf.accept_content = ["json"]

# Celery Beat schedule — periodic tasks
celery.conf.beat_schedule = {
    "sweep-stuck-partials-every-5-minutes": {
        "task": "app.tasks.enrichment_tasks.sweep_stuck_partials",
        "schedule": 300.0,  # 5 minutes
    },
}
