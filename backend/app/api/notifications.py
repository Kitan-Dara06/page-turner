import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies import get_current_user_uuid
from app.models.events import EventType, InteractionEvent

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/releases")
def get_undismissed_releases(
    db: Session = Depends(get_db),
    user_uuid: str = Depends(get_current_user_uuid),
):
    """FR-AT-02: Returns undismissed author_new_release events for the current user."""
    events = (
        db.execute(
            select(InteractionEvent)
            .where(
                InteractionEvent.user_uuid == user_uuid,
                InteractionEvent.event_type == EventType.AUTHOR_NEW_RELEASE,
            )
            .order_by(InteractionEvent.event_timestamp.desc())
            .limit(20)
        )
        .scalars()
        .all()
    )
    undismissed = [e for e in events if not (e.mood_tags or {}).get("dismissed", False)]
    return {
        "count": len(undismissed),
        "releases": [
            {
                "event_uuid": str(e.event_uuid),
                "title": (e.mood_tags or {}).get("title", "Unknown"),
                "author_name": (e.mood_tags or {}).get("author_name", "Unknown"),
                "publication_date": str((e.mood_tags or {}).get("publication_date", "")),
                "work_uuid": str(e.work_uuid) if e.work_uuid else None,
                "dismissed": (e.mood_tags or {}).get("dismissed", False),
            }
            for e in undismissed
        ],
    }


@router.post("/releases/{event_uuid}/dismiss")
def dismiss_release(
    event_uuid: str,
    db: Session = Depends(get_db),
    user_uuid: str = Depends(get_current_user_uuid),
):
    """FR-AT-02: Marks a release notification as dismissed."""
    event = db.execute(
        select(InteractionEvent).where(
            InteractionEvent.event_uuid == event_uuid,
            InteractionEvent.user_uuid == user_uuid,
            InteractionEvent.event_type == EventType.AUTHOR_NEW_RELEASE,
        )
    ).scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="Release notification not found.")
    tags = event.mood_tags or {}
    tags["dismissed"] = True
    event.mood_tags = tags
    db.commit()
    return {"status": "dismissed"}
