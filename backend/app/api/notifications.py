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
    from sqlalchemy import text

    rows = db.execute(
        text(
            "SELECT event_uuid, mood_tags, event_timestamp, work_uuid "
            "FROM interaction_events "
            "WHERE user_uuid = :uid "
            "AND event_type = 'author_new_release' "
            "AND (mood_tags->>'dismissed' IS NULL OR mood_tags->>'dismissed' != 'true') "
            "ORDER BY event_timestamp DESC "
            "LIMIT 50"
        ),
        {"uid": user_uuid},
    ).all()

    return {
        "count": len(rows),
        "releases": [
            {
                "event_uuid": str(r[0]),
                "title": (r[1] or {}).get("title", "Unknown"),
                "author_name": (r[1] or {}).get("author_name", "Unknown"),
                "publication_date": str((r[1] or {}).get("publication_date", "")),
                "work_uuid": str(r[3]) if r[3] else None,
                "dismissed": (r[1] or {}).get("dismissed", False),
            }
            for r in rows
        ],
    }


@router.post("/releases/{event_uuid}/dismiss")
def dismiss_release(
    event_uuid: str,
    db: Session = Depends(get_db),
    user_uuid: str = Depends(get_current_user_uuid),
):
    """FR-AT-02: Marks a release notification as dismissed."""
    from sqlalchemy import text

    result = db.execute(
        text(
            "UPDATE interaction_events "
            "SET mood_tags = jsonb_set(mood_tags, '{dismissed}', 'true'::jsonb) "
            "WHERE event_uuid = :eid "
            "AND user_uuid = :uid "
            "AND event_type = 'author_new_release'"
        ),
        {"eid": event_uuid, "uid": user_uuid},
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Release notification not found.")
    db.commit()
    return {"status": "dismissed"}
