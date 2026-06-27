import logging
import uuid as py_uuid
from datetime import datetime, timezone
from typing import Dict, List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.db.session import get_db
from app.dependencies import get_current_user_uuid
from app.models.books import Work
from app.models.events import AbandonmentStage, EventType, InteractionEvent
from app.models.recommendations import (
    RecommendationLog,
    RecommendationStatus,
    RecommendationSource,
)
from app.schemas.books import WorkResponse
from app.schemas.feedback import FeedbackEventType, FeedbackSubmit
from app.services import exploration_service, feedback_processor

logger = logging.getLogger(__name__)
router = APIRouter()

_EVENT_TO_REC_STATUS = {
    FeedbackEventType.LOGGED_READ: RecommendationStatus.FINISHED,
    FeedbackEventType.NOT_INTERESTED: RecommendationStatus.NOT_INTERESTED,
    FeedbackEventType.INTERESTED: RecommendationStatus.INTERESTED,
}


@router.post("/")
def submit_feedback(
    request: FeedbackSubmit,
    db: Session = Depends(get_db),
    user_uuid: str = Depends(get_current_user_uuid),
):
    """FR-FL-01 through FR-FL-06: Routes interaction events to update Tower 1/2."""
    logger.info(
        f"[{user_uuid[:8]}] Feedback: {request.event_type} for {request.work_uuid}"
    )
    try:
        # 1. Process behavioral signal via the processor
        event = feedback_processor.process_interaction(
            db=db,
            user_uuid=user_uuid,
            event_type=request.event_type,
            work_uuid=str(request.work_uuid) if request.work_uuid else None,
            stated_rating=request.stated_rating,
            abandonment_stage=request.abandonment_stage,
            is_reread=(request.event_type == FeedbackEventType.REREAD),
            is_fast_finish=False,
        )

        # FR-EX: record exploration outcome for anti-profile building
        if (
            request.event_type == FeedbackEventType.EXPLORATION_OUTCOME
            and request.exploration_outcome
        ):
            _explorer = exploration_service.ExplorationService(db)
            _explorer.record_exploration_outcome(
                user_uuid=user_uuid,
                work_uuid=request.work_uuid,
                outcome=request.exploration_outcome,
            )

        # 2. Update RecommendationLog status if checkpoint_status is specified
        if request.checkpoint_status:
            status_map = {
                "finished": RecommendationStatus.FINISHED,
                "abandoned": RecommendationStatus.ABANDONED,
                "still_reading": RecommendationStatus.STILL_READING,
                "havent_started": RecommendationStatus.HAVENT_STARTED,
            }
            resolved_status = status_map.get(request.checkpoint_status)
            if resolved_status:
                rec_log = db.execute(
                    select(RecommendationLog)
                    .where(RecommendationLog.user_uuid == user_uuid)
                    .where(RecommendationLog.work_uuid == request.work_uuid)
                    .order_by(RecommendationLog.delivered_at.desc())
                    .limit(1)
                ).scalar_one_or_none()

                if not rec_log:
                    # Create recommendation log context (e.g. they started a TBR book)
                    rec_log = RecommendationLog(
                        user_uuid=user_uuid,
                        work_uuid=request.work_uuid,
                        session_id="manual",
                        rank_position=0,
                        source=RecommendationSource.TBR,
                        query_text="Added manually from library/cravings drawer",
                        status=resolved_status,
                        status_updated_at=datetime.now(timezone.utc),
                    )
                    db.add(rec_log)
                else:
                    rec_log.status = resolved_status
                    rec_log.status_updated_at = datetime.now(timezone.utc)
                db.commit()

        # 3. Close out the RecommendationLog for standard direct-action events
        elif request.event_type in _EVENT_TO_REC_STATUS:
            resolved_status = _EVENT_TO_REC_STATUS[request.event_type]
            rec_log = db.execute(
                select(RecommendationLog)
                .where(RecommendationLog.user_uuid == user_uuid)
                .where(RecommendationLog.work_uuid == request.work_uuid)
                .where(RecommendationLog.status == RecommendationStatus.DELIVERED)
                .order_by(RecommendationLog.delivered_at.desc())
                .limit(1)
            ).scalar_one_or_none()
            if rec_log:
                rec_log.status = resolved_status
                rec_log.status_updated_at = datetime.now(timezone.utc)
                db.commit()

        return {"status": "success", "event_id": str(event.event_uuid)}
    except Exception as e:
        logger.error(f"[{user_uuid[:8]}] Feedback error: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to process feedback.")


@router.get("/history")
def get_reading_history(
    db: Session = Depends(get_db),
    user_uuid: str = Depends(get_current_user_uuid),
):
    """
    Returns the user's library and reading history.
    - 'reading': books currently marked as 'still_reading' in RecommendationLog.
    - 'finished': books marked as finished (RecommendationStatus.FINISHED in RecommendationLog
      or EventType.LOGGED_READ in InteractionEvent).
    """
    try:
        # Fetch currently reading logs
        reading_logs = (
            db.execute(
                select(RecommendationLog)
                .where(RecommendationLog.user_uuid == user_uuid)
                .where(RecommendationLog.status == RecommendationStatus.STILL_READING)
                .order_by(RecommendationLog.status_updated_at.desc())
            )
            .scalars()
            .all()
        )

        reading_works = []
        seen_reading = set()
        for log in reading_logs:
            if log.work_uuid not in seen_reading:
                seen_reading.add(log.work_uuid)
                try:
                    reading_works.append(WorkResponse.model_validate(log.work))
                except Exception as ex:
                    logger.warning(f"Error validating reading log work: {ex}")

        # Fetch finished recommendation logs
        finished_logs = (
            db.execute(
                select(RecommendationLog)
                .where(RecommendationLog.user_uuid == user_uuid)
                .where(RecommendationLog.status == RecommendationStatus.FINISHED)
                .order_by(RecommendationLog.status_updated_at.desc())
            )
            .scalars()
            .all()
        )

        # Fetch finished interaction events
        finished_events = (
            db.execute(
                select(InteractionEvent)
                .where(InteractionEvent.user_uuid == user_uuid)
                .where(InteractionEvent.event_type == EventType.LOGGED_READ)
                .order_by(InteractionEvent.event_timestamp.desc())
            )
            .scalars()
            .all()
        )

        finished_works = []
        seen_finished = set()

        for log in finished_logs:
            if log.work_uuid not in seen_finished:
                seen_finished.add(log.work_uuid)
                try:
                    finished_works.append(WorkResponse.model_validate(log.work))
                except Exception as ex:
                    logger.warning(f"Error validating finished log work: {ex}")

        for event in finished_events:
            if event.work_uuid and event.work_uuid not in seen_finished:
                seen_finished.add(event.work_uuid)
                try:
                    finished_works.append(WorkResponse.model_validate(event.work))
                except Exception as ex:
                    logger.warning(f"Error validating finished event work: {ex}")

        return {"reading": reading_works, "finished": finished_works}
    except Exception as e:
        logger.error(f"Error fetching reading history: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to load reading history.")


@router.get("/timeline")
def get_interaction_timeline(
    db: Session = Depends(get_db),
    user_uuid: str = Depends(get_current_user_uuid),
):
    """
    Returns a chronological feed of all user interactions (reads, passes, saves, ratings, etc.)
    with work metadata and the profile snapshots at that moment.
    """
    try:
        events = (
            db.execute(
                select(InteractionEvent)
                .options(joinedload(InteractionEvent.work).joinedload(Work.person))
                .where(InteractionEvent.user_uuid == user_uuid)
                .order_by(InteractionEvent.event_timestamp.desc())
                .limit(100)
            )
            .scalars()
            .all()
        )

        timeline = []
        for e in events:
            work_data = None
            if e.work:
                try:
                    work_data = WorkResponse.model_validate(e.work)
                except Exception as ex:
                    logger.warning(f"Error serializing work in timeline: {ex}")

            timeline.append({
                "event_uuid": str(e.event_uuid),
                "event_type": e.event_type.value if hasattr(e.event_type, "value") else str(e.event_type),
                "event_timestamp": e.event_timestamp.isoformat(),
                "query_text": e.query_text,
                "mood_tags": e.mood_tags,
                "stated_rating": e.stated_rating,
                "abandonment_stage": e.abandonment_stage.value if e.abandonment_stage and hasattr(e.abandonment_stage, "value") else str(e.abandonment_stage) if e.abandonment_stage else None,
                "tower1_snapshot": e.tower1_snapshot,
                "work": work_data,
            })

        return {"timeline": timeline}
    except Exception as err:
        logger.error(f"Error fetching interaction timeline: {err}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to load interaction timeline.")
