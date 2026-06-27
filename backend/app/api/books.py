import logging
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.workers.enrichment_tasks import enrich_book_task

logger = logging.getLogger(__name__)
router = APIRouter()


class ManualLogRequest(BaseModel):
    title: str
    author: str
    isbn: Optional[str] = None


@router.post("/log")
def log_manual_book(request: ManualLogRequest):
    """
    Allows a user to manually log a book not surfaced by the recommendation engine.
    Fires the async Celery enrichment pipeline.
    """
    logger.info(f"Manual book log requested: '{request.title}' by {request.author}")

    # Fire and forget the background enrichment task
    enrich_book_task.delay(
        title=request.title, author_name=request.author, isbn=request.isbn
    )

    return {
        "status": "queued",
        "message": "Book has been queued for enrichment and will appear in your history shortly.",
    }
