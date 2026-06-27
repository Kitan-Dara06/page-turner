import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.orm import Session, joinedload

from app.db.session import get_db
from app.dependencies import get_current_user_uuid
from app.models.tropes import Trope, BookTrope
from app.models.authors import Person
from app.models.books import Edition, Work
from app.models.events import AbandonmentStage, EventType, InteractionEvent
from app.models.recommendations import RecommendationLog, RecommendationStatus
from app.models.tbr import TBREntry, TBRStatus
from app.schemas.books import WorkResponse
from app.schemas.recommendations import (
    CheckpointItem,
    CheckpointResponse,
    CheckpointUpdateRequest,
    CheckpointUpdateResponse,
    RecommendationRequest,
    RecommendationResponse,
    TBRDropCandidate,
)
from app.services import recommendation_engine

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/", response_model=RecommendationResponse)
def get_recommendations(
    request: RecommendationRequest,
    db: Session = Depends(get_db),
    user_uuid: str = Depends(get_current_user_uuid),
):
    """
    FR-QR-01 to FR-QR-07: Core Recommendation Pipeline.
    """
    logger.info(f"[{user_uuid[:8]}] Recommendation request: '{request.query}'")
    session_id = str(uuid.uuid4())
    try:
        response = recommendation_engine.generate_recommendations(
            db=db,
            user_uuid=user_uuid,
            raw_query=request.query,
            session_id=session_id,
        )
        return response
    except Exception as e:
        logger.error(
            f"[{user_uuid[:8]}] Recommendation pipeline failed: {e}", exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail="An error occurred while generating recommendations. Please try again.",
        )


@router.get("/checkpoint", response_model=CheckpointResponse)
def get_pending_checkpoints(
    db: Session = Depends(get_db),
    user_uuid: str = Depends(get_current_user_uuid),
):
    """FR-FL-02: Surfaces unresolved recommendation logs and decayed TBR entries."""
    pending_logs = (
        db.execute(
            select(RecommendationLog)
            .options(joinedload(RecommendationLog.work).joinedload(Work.person))
            .where(RecommendationLog.user_uuid == user_uuid)
            .where(RecommendationLog.status == RecommendationStatus.DELIVERED)
            .order_by(RecommendationLog.delivered_at.desc())
            .limit(10)
        )
        .unique()
        .scalars()
        .all()
    )

    items = []
    for log in pending_logs:
        try:
            work_schema = WorkResponse.model_validate(log.work)
            items.append(
                CheckpointItem(
                    rec_uuid=str(log.rec_uuid),
                    work=work_schema,
                    delivered_at=log.delivered_at.isoformat(),
                )
            )
        except Exception as e:
            logger.warning(f"Failed to serialize checkpoint item {log.rec_uuid}: {e}")

    # FR-TBR-02: decayed TBR entries for keep/drop prompt
    _now = datetime.now(timezone.utc)
    _decayed = (
        db.execute(
            select(TBREntry)
            .where(TBREntry.user_uuid == user_uuid)
            .where(TBREntry.status == TBRStatus.ACTIVE)
            .where(TBREntry.priority_score < 0.30)
            .order_by(TBREntry.priority_score.asc())
            .limit(5)
        )
        .scalars()
        .all()
    )
    drop_candidates = []
    for _tbr in _decayed:
        _work = db.execute(
            select(Work).where(Work.work_uuid == _tbr.work_uuid)
        ).scalar_one_or_none()
        if not _work:
            continue
        _person = db.execute(
            select(Person).where(Person.person_uuid == _work.person_uuid)
        ).scalar_one_or_none()
        _edition = db.execute(
            select(Edition).where(Edition.work_uuid == _work.work_uuid)
        ).scalar_one_or_none()
        drop_candidates.append(
            TBRDropCandidate(
                tbr_uuid=str(_tbr.tbr_uuid),
                work_uuid=str(_work.work_uuid),
                title=_work.title,
                author_name=_person.canonical_name if _person else "Unknown",
                cover_url=_edition.cover_url if _edition else None,
                priority_score=round(_tbr.priority_score, 3),
                days_since_added=(_now - _tbr.added_at).days,
            )
        )

    return CheckpointResponse(pending_items=items, drop_candidates=drop_candidates)


# ── POST /checkpoint — Update recommendation statuses ────────────────


@router.post("/checkpoint", response_model=CheckpointUpdateResponse)
def update_checkpoints(
    request: CheckpointUpdateRequest,
    db: Session = Depends(get_db),
    user_uuid: str = Depends(get_current_user_uuid),
):
    """
    FR-FL-02/03/04: Process checkpoint status updates.
    Accepts a list of status updates for previously delivered recommendations.
    For abandoned items, accepts optional abandonment_stage.
    For finished/reread items, accepts optional stated_rating.
    Also fires InteractionEvents for finished, abandoned, and reread statuses.
    """
    valid_statuses = {
        "finished",
        "abandoned",
        "still_reading",
        "havent_started",
        "reread",
    }
    valid_stages = {"barely_started", "halfway", "nearly_finished"}

    processed = 0
    errors = []

    for update in request.updates:
        if update.status not in valid_statuses:
            errors.append(f"Invalid status '{update.status}' for {update.rec_uuid}")
            continue

        try:
            rec_uuid = uuid.UUID(update.rec_uuid)
        except (ValueError, AttributeError):
            errors.append(f"Invalid rec_uuid: {update.rec_uuid}")
            continue

        log = db.execute(
            select(RecommendationLog)
            .where(RecommendationLog.rec_uuid == rec_uuid)
            .where(RecommendationLog.user_uuid == user_uuid)
        ).scalar_one_or_none()

        if not log:
            errors.append(f"Recommendation log {update.rec_uuid} not found")
            continue

        # Map string status to enum
        status_map = {
            "finished": RecommendationStatus.FINISHED,
            "abandoned": RecommendationStatus.ABANDONED,
            "still_reading": RecommendationStatus.STILL_READING,
            "havent_started": RecommendationStatus.HAVENT_STARTED,
            "reread": RecommendationStatus.REREAD,
        }
        new_status = status_map[update.status]

        # Update the recommendation log
        log.status = new_status
        log.status_updated_at = datetime.now(timezone.utc)

        # Fire interaction event for statuses that carry signal
        if update.status in ("finished", "abandoned", "reread"):
            event_type = (
                EventType.REREAD
                if update.status == "reread"
                else (
                    EventType.LOGGED_READ
                    if update.status == "finished"
                    else EventType.CHECKPOINT_UPDATE
                )
            )

            abandonment_stage = None
            if update.status == "abandoned" and update.abandonment_stage:
                if update.abandonment_stage in valid_stages:
                    abandonment_stage = AbandonmentStage(update.abandonment_stage)
                else:
                    errors.append(
                        f"Invalid abandonment_stage '{update.abandonment_stage}' "
                        f"for {update.rec_uuid}"
                    )
                    continue

            event = InteractionEvent(
                user_uuid=uuid.UUID(user_uuid),
                work_uuid=log.work_uuid,
                event_type=event_type,
                session_id=log.session_id,
                query_text=log.query_text,
                abandonment_stage=abandonment_stage,
                stated_rating=update.stated_rating,
                time_of_day=datetime.now(timezone.utc).strftime("%H"),
                day_of_week=datetime.now(timezone.utc).strftime("%A"),
            )
            db.add(event)
            logger.info(
                f"Checkpoint: {update.status} for {log.work_uuid} "
                f"(stage={update.abandonment_stage}, rating={update.stated_rating})"
            )

        processed += 1

    try:
        db.commit()
    except Exception as e:
        logger.error(f"Checkpoint update commit failed: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to save checkpoint updates")

    return CheckpointUpdateResponse(processed=processed, errors=errors)


@router.get("/tropes")
def list_public_tropes(db: Session = Depends(get_db)):
    """
    Returns tropes having at least one work association, ordered descending by frequency.
    """
    try:
        rows = (
            db.execute(
                select(Trope.canonical_name, Trope.trope_uuid, func.count(BookTrope.work_uuid).label("book_count"))
                .join(BookTrope, BookTrope.trope_uuid == Trope.trope_uuid)
                .group_by(Trope.trope_uuid, Trope.canonical_name)
                .order_by(func.count(BookTrope.work_uuid).desc())
            ).all()
        )
        return {
            "tropes": [
                {
                    "canonical_name": r.canonical_name,
                    "trope_uuid": str(r.trope_uuid),
                    "book_count": r.book_count
                }
                for r in rows
            ]
        }
    except Exception as e:
        logger.error(f"Error fetching tropes: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve tropes list.")


@router.get("/tropes/{trope_uuid}")
def get_books_by_trope(trope_uuid: str, db: Session = Depends(get_db)):
    """
    Returns the works associated with a specific trope, ordered descending by confidence score.
    """
    try:
        try:
            trope_id = uuid.UUID(trope_uuid)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid trope UUID format.")

        trope = db.execute(select(Trope).where(Trope.trope_uuid == trope_id)).scalar_one_or_none()
        if not trope:
            raise HTTPException(status_code=404, detail="Trope not found.")

        book_tropes = (
            db.execute(
                select(BookTrope)
                .options(joinedload(BookTrope.work).joinedload(Work.person))
                .where(BookTrope.trope_uuid == trope_id)
                .order_by(BookTrope.confidence_score.desc())
                .limit(50)
            )
            .scalars()
            .all()
        )

        works = []
        for bt in book_tropes:
            if bt.work:
                try:
                    works.append(WorkResponse.model_validate(bt.work))
                except Exception as ex:
                    logger.warning(f"Failed to serialize work {bt.work_uuid} in trope view: {ex}")

        return {
            "trope": {
                "canonical_name": trope.canonical_name,
                "trope_uuid": str(trope.trope_uuid),
            },
            "works": works,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching books for trope {trope_uuid}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve books for trope.")
