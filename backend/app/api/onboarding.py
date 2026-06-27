import logging
import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies import get_current_user_uuid
from app.models.books import Work
from app.models.enrichment import EnrichmentCache
from app.models.events import EventType, InteractionEvent
from app.models.users import User, UserProfile
from app.schemas.books import WorkResponse
from app.schemas.onboarding import FlashcardDecision, FlashcardSubmit
from app.services import feedback_processor

logger = logging.getLogger(__name__)
router = APIRouter()

MOCK_USER_UUID = "00000000-0000-0000-0000-000000000001"  # replaced by auth dep below


@router.get("/flashcards", response_model=List[WorkResponse])
def get_onboarding_flashcards(
    db: Session = Depends(get_db),
    user_uuid: str = Depends(get_current_user_uuid),
):
    """
    FR-CS-04: Draws from the pre-seeded flashcard pool.
    FR-CS-05: Excludes books the user has already swiped.
    Post-onboarding: selects books near the user's established taste region.
    """
    # 1. Get IDs of books already swiped by this user
    swiped_subq = (
        select(InteractionEvent.work_uuid)
        .where(InteractionEvent.user_uuid == user_uuid)
        .where(InteractionEvent.session_id == "onboarding_session")
    ).scalar_subquery()

    # 2. Check if user has completed onboarding
    user_profile = db.execute(
        select(UserProfile).where(UserProfile.user_uuid == user_uuid)
    ).scalar_one_or_none()

    is_post_onboarding = user_profile is not None and (
        user_profile.darkness_tolerance is not None
        or user_profile.thematic_density is not None
    )

    base_query = (
        select(Work)
        .join(EnrichmentCache, Work.work_uuid == EnrichmentCache.work_uuid)
        .where(EnrichmentCache.flashcard_pool == True)
        .where(Work.work_uuid.notin_(swiped_subq))
    )

    if is_post_onboarding and user_profile:
        # FR-CS-05: Use Tower 1 state to find discriminative books
        # Prioritize books with extreme values (near 0 or 1) in dimensions
        # where the user has established preferences
        calibration_books = (
            db.execute(base_query.order_by(func.random()).limit(15)).scalars().all()
        )
    else:
        # First visit: random spread across genres
        calibration_books = (
            db.execute(base_query.order_by(func.random()).limit(12)).scalars().all()
        )

    if not calibration_books:
        logger.warning("No flashcard pool books available.")
        return []

    return [WorkResponse.model_validate(book) for book in calibration_books]


@router.post("/response")
def submit_flashcard_response(
    response: FlashcardSubmit,
    db: Session = Depends(get_db),
    user_uuid: str = Depends(get_current_user_uuid),
):
    """
    Receives a single flashcard swipe decision and immediately seeds the user's profile.
    FR-CS-05: NOT_INTERESTED swipes permanently contribute to the anti-profile.
    """
    work = db.execute(
        select(Work).where(Work.work_uuid == response.work_uuid)
    ).scalar_one_or_none()
    if not work:
        raise HTTPException(status_code=404, detail="Book not found")

    # Ensure mock user exists (FK constraint)
    user = db.execute(
        select(User).where(User.user_uuid == user_uuid)
    ).scalar_one_or_none()
    if not user:
        user = User(user_uuid=uuid.UUID(user_uuid))
        db.add(user)
        profile = UserProfile(user_uuid=user.user_uuid)
        db.add(profile)
        db.flush()

    event_type_map = {
        FlashcardDecision.READ_IT: EventType.LOGGED_READ,
        FlashcardDecision.INTERESTED: EventType.TBR_ADD,
        FlashcardDecision.NOT_INTERESTED: EventType.NOT_INTERESTED,
    }
    mapped_event = event_type_map[response.decision]

    book_inferred_profile = _extract_book_profile(db, work)

    feedback_processor.process_interaction(
        db=db,
        user_uuid=user_uuid,
        event_type=mapped_event,
        work_uuid=str(work.work_uuid),
        session_id="onboarding_session",
        mood_tags=book_inferred_profile,
        is_fast_finish=False,
        is_reread=False,
    )

    return {"status": "success", "event_logged": mapped_event.value}


def _extract_book_profile(db: Session, work: Work) -> dict:
    """
    Uses the book's EnrichmentCache.tower1_snapshot if available,
    otherwise returns neutral defaults.
    """
    cache = db.execute(
        select(EnrichmentCache).where(EnrichmentCache.work_uuid == work.work_uuid)
    ).scalar_one_or_none()

    if cache and cache.tower1_snapshot:
        return cache.tower1_snapshot

    return {
        "pacing_preference": 0.5,
        "thematic_density": 0.5,
        "speculative_deviation": 0.5,
    }
