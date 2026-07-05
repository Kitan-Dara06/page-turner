"""Async recommendation tasks — runs pipeline in Celery to bypass Heroku 30s limit."""

import json
import logging
import uuid
from json import JSONEncoder

from app.db.session import SessionLocal
from app.services import recommendation_engine
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

REDIS_TTL = 300  # 5 minutes


class _UUIDEncoder(JSONEncoder):
    def default(self, o):
        if isinstance(o, uuid.UUID):
            return str(o)
        return super().default(o)


@celery_app.task(bind=True, max_retries=1, acks_late=True, time_limit=60)
def generate_recommendations_async(self, user_uuid: str, raw_query: str, task_id: str):
    """
    Runs the full recommendation pipeline in a Celery worker.
    Stores serialised result in Redis under the task_id key.
    """
    redis = celery_app.backend.client
    db = SessionLocal()
    session_id = str(uuid.uuid4())

    try:
        redis.set(
            task_id,
            json.dumps({"status": "processing", "task_id": task_id}, cls=_UUIDEncoder),
            ex=REDIS_TTL,
        )

        response = recommendation_engine.generate_recommendations(
            db=db,
            user_uuid=user_uuid,
            raw_query=raw_query,
            session_id=session_id,
        )

        result = {
            "status": "complete",
            "task_id": task_id,
            "session_id": response.session_id,
            "query_rewritten": response.query_rewritten,
            "mood_tags_extracted": response.mood_tags_extracted,
            "results": [
                {
                    "work": r.work.model_dump(),
                    "explanation": r.explanation,
                    "match_source": r.match_source,
                    "tbr_context_bonus": r.tbr_context_bonus,
                    "is_in_tbr": r.is_in_tbr,
                    "description": r.description,
                }
                for r in response.results
            ],
            "author_spotlight": (
                response.author_spotlight.model_dump()
                if response.author_spotlight
                else None
            ),
            "tbr_matches": [m.model_dump() for m in response.tbr_matches],
            "content_mode": response.content_mode,
            "unmatched_tropes": response.unmatched_tropes,
        }

        redis.set(task_id, json.dumps(result, cls=_UUIDEncoder), ex=REDIS_TTL)
        logger.info(
            f"Async recommendation complete: {task_id} ({len(response.results)} results)"
        )
        return result

    except Exception as e:
        logger.exception(f"Async recommendation failed: {task_id}")
        redis.set(
            task_id,
            json.dumps(
                {
                    "status": "error",
                    "task_id": task_id,
                    "detail": str(e),
                },
                cls=_UUIDEncoder,
            ),
            ex=REDIS_TTL,
        )
        raise
    finally:
        db.close()
