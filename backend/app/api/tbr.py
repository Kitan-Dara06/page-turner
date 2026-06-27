import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies import get_current_user_uuid
from app.models.tbr import TBREntry, TBRStatus
from app.schemas.tbr import TBRAddRequest, TBREntryResponse
from app.services import tbr_service

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/", response_model=List[TBREntryResponse])
def get_active_tbr(
    db: Session = Depends(get_db),
    user_uuid: str = Depends(get_current_user_uuid),
):
    """Fetches the user's active TBR list, sorted by decaying priority score."""
    entries = (
        db.execute(
            select(TBREntry)
            .where(TBREntry.user_uuid == user_uuid)
            .where(TBREntry.status == TBRStatus.ACTIVE)
            .order_by(TBREntry.priority_score.desc())
        )
        .scalars()
        .all()
    )
    return [TBREntryResponse.model_validate(e) for e in entries]


@router.post("/", response_model=TBREntryResponse)
def add_to_tbr(
    request: TBRAddRequest,
    db: Session = Depends(get_db),
    user_uuid: str = Depends(get_current_user_uuid),
):
    """FR-TBR-01: Context-Aware TBR Add."""
    entry = tbr_service.add_to_tbr(
        db=db,
        user_uuid=user_uuid,
        work_uuid=str(request.work_uuid),
        query_text=request.current_query_text,
        mood_tags=request.current_mood_tags,
    )
    return TBREntryResponse.model_validate(entry)


@router.delete("/{tbr_uuid}")
def drop_from_tbr(
    tbr_uuid: str,
    db: Session = Depends(get_db),
    user_uuid: str = Depends(get_current_user_uuid),
):
    """Drops a book from the TBR."""
    success = tbr_service.drop_tbr_entry(db, user_uuid, tbr_uuid)
    if not success:
        raise HTTPException(status_code=404, detail="TBR entry not found.")
    return {"status": "dropped"}


@router.put("/{tbr_uuid}/reset-priority")
def reset_tbr_priority(
    tbr_uuid: str,
    db: Session = Depends(get_db),
    user_uuid: str = Depends(get_current_user_uuid),
):
    """FR-TBR-02: Reset TBR priority to 0.7 — user chose to keep."""
    entry = db.execute(
        select(TBREntry)
        .where(TBREntry.tbr_uuid == tbr_uuid)
        .where(TBREntry.user_uuid == user_uuid)
    ).scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="TBR entry not found.")
    entry.priority_score = 0.7
    entry.skip_count = 0
    db.commit()
    return {"status": "kept", "priority_score": 0.7}
