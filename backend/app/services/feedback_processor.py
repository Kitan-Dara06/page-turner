import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.integrations import qdrant
from app.models.books import Work
from app.models.enrichment import EnrichmentCache
from app.models.events import AbandonmentStage, EventType, InteractionEvent
from app.models.tracked_authors import TrackedAuthor
from app.models.users import UserProfile
from app.services import user_intelligence

logger = logging.getLogger(__name__)

# ==========================================
# Section 7.1: Signal Hierarchy Constants
# Polarity and magnitude of behavioral signals
# ==========================================
SIGNAL_REREAD = 1.0  # Strongest Positive
SIGNAL_FAST_FINISH = 0.9  # Very Strong Positive
SIGNAL_NOT_INTERESTED = -0.8  # Strong Negative (Anti-profile)
SIGNAL_FINISHED_STANDARD = 0.6  # Strong Positive
SIGNAL_EARLY_DNF = -0.5  # Medium Negative
SIGNAL_LATE_DNF = -0.2  # Medium Weak Negative
SIGNAL_HIGH_RATING = 0.3  # Weak Positive (Stated preference)
SIGNAL_LOW_RATING = -0.3  # Weak Negative (Stated preference)
SIGNAL_TBR_ADD = 0.2  # Weak Positive (Aspirational)
SIGNAL_INTERESTED = 0.3  # Soft Positive (Aware; no commit clock starts)
SIGNAL_TBR_SKIP = -0.1  # Weak Negative
SIGNAL_NEUTRAL = 0.0  # Confirmed Neutral (e.g., Haven't Started)


def process_interaction(
    db: Session,
    user_uuid: str,
    event_type: EventType,
    work_uuid: Optional[str] = None,
    session_id: Optional[str] = None,
    query_text: Optional[str] = None,
    mood_tags: Optional[Dict[str, Any]] = None,
    stated_rating: Optional[int] = None,
    abandonment_stage: Optional[AbandonmentStage] = None,
    is_reread: bool = False,
    is_fast_finish: bool = False,
) -> InteractionEvent:
    """
    The master entry point for all user interactions.
    1. Persists the raw event to the source-of-truth log.
    2. Calculates the behavioral signal weight.
    3. Routes the signal to the appropriate profile layers.
    """
    logger.info(f"Processing {event_type} event for user {user_uuid}")

    # 1. Take a snapshot of Tower 1 state BEFORE the event alters it (Section 10.1)
    current_profile = db.execute(
        select(UserProfile).where(UserProfile.user_uuid == user_uuid)
    ).scalar_one_or_none()
    current_tower1_state = (
        _extract_tower1_state(current_profile) if current_profile else {}
    )

    # 2. Persist the raw event to the database
    event = InteractionEvent(
        user_uuid=user_uuid,
        work_uuid=work_uuid,
        event_type=event_type,
        session_id=session_id,
        query_text=query_text,
        mood_tags=mood_tags,
        tower1_snapshot=current_tower1_state,
        stated_rating=stated_rating,
        abandonment_stage=abandonment_stage,
    )
    db.add(event)
    db.flush()

    # 3. Calculate the signal weight based on the Section 7 Hierarchy
    signal_weight = _calculate_signal_weight(
        event_type=event_type,
        stated_rating=stated_rating,
        abandonment_stage=abandonment_stage,
        is_reread=is_reread,
        is_fast_finish=is_fast_finish,
    )

    # 4. Route to Profile Layers
    if signal_weight != SIGNAL_NEUTRAL:
        _route_signal_to_profiles(
            db=db,
            user_uuid=user_uuid,
            event=event,
            signal_weight=signal_weight,
            work_uuid=work_uuid,
        )

    # 5. Auto-track author on LOGGED_READ / REREAD (FR-AT-01)
    if event_type in (EventType.LOGGED_READ, EventType.REREAD) and work_uuid:
        _auto_track_author(db, user_uuid, work_uuid)

    db.commit()
    return event


# ==========================================
# Private Routing & Calculation Helpers
# ==========================================


def _calculate_signal_weight(
    event_type: EventType,
    stated_rating: Optional[int],
    abandonment_stage: Optional[AbandonmentStage],
    is_reread: bool,
    is_fast_finish: bool,
) -> float:
    """
    Translates discrete user actions into a continuous float weight [-1.0, 1.0].
    Handles contradictory signals (Section 7.2) by aggregating standard behaviors.
    """
    weight = 0.0

    # Base Event Weight
    if event_type in (EventType.LOGGED_READ, EventType.REREAD):
        if is_reread or event_type == EventType.REREAD:
            weight += SIGNAL_REREAD
        elif is_fast_finish:
            weight += SIGNAL_FAST_FINISH
        else:
            weight += SIGNAL_FINISHED_STANDARD

    elif event_type == EventType.NOT_INTERESTED:
        weight += SIGNAL_NOT_INTERESTED

    elif event_type == EventType.INTERESTED:
        # Soft positive. Tropes get a small nudge; no TBR entry or priority decay clock.
        weight += SIGNAL_INTERESTED

    elif event_type == EventType.TBR_ADD:
        weight += SIGNAL_TBR_ADD

    elif event_type == EventType.CHECKPOINT_UPDATE:
        if abandonment_stage == AbandonmentStage.BARELY_STARTED:
            weight += SIGNAL_EARLY_DNF
        elif abandonment_stage in [
            AbandonmentStage.HALFWAY,
            AbandonmentStage.NEARLY_FINISHED,
        ]:
            weight += SIGNAL_LATE_DNF
        else:
            weight += SIGNAL_NEUTRAL  # "Haven't Started" or unhandled status

    # Stated Preference Modifier (Star Ratings)
    # Applied as a modifier to the base behavior. A fast finish (+0.9) with a
    # 2-star rating (-0.3) results in a net +0.6 (Compelled but dissatisfied).
    if stated_rating is not None:
        if stated_rating >= 4:
            weight += SIGNAL_HIGH_RATING
        elif stated_rating <= 2:
            weight += SIGNAL_LOW_RATING

    # Clamp the final weight to the [-1.0, 1.0] interval
    return max(-1.0, min(1.0, weight))


def _route_signal_to_profiles(
    db: Session,
    user_uuid: str,
    event: InteractionEvent,
    signal_weight: float,
    work_uuid: Optional[str],
):
    """
    Distributes the weighted signal to Tower 1 (Explicit) and Tower 2 (Latent).
    """
    # ---------------------------------------------------------
    # Route to Tower 1: Explicit Structured Profile
    # ---------------------------------------------------------
    # Tower 1 only updates if the event carried explicit emotional/structured context (mood_tags).
    # Examples: An onboarding flashcard, a complex search query, or a TBR add with context.
    if event.mood_tags:
        # Scale the delta by the signal weight.
        scaled_delta = {
            k: max(0.0, min(1.0, float(v) * abs(signal_weight)))
            for k, v in event.mood_tags.items()
        }

        # Check if this book is narrative — skip delta for non-narrative works
        _is_narrative = True
        if event.work_uuid:
            _cache = db.execute(
                select(EnrichmentCache.is_narrative).where(
                    EnrichmentCache.work_uuid == event.work_uuid
                )
            ).scalar_one_or_none()
            if _cache is not None:
                _is_narrative = _cache

        user_intelligence.apply_tower1_delta(
            db=db,
            user_uuid=user_uuid,
            delta=scaled_delta,
            trigger_event=event.event_type.value,
            is_narrative=_is_narrative,
        )

    # ---------------------------------------------------------
    # Route to Tower 2: Latent Embedding Profile
    # ---------------------------------------------------------
    # Tower 2 updates via vector math. We need the actual embedding of the book
    # the user interacted with. Uses fetch_vector_by_id (primary key lookup)
    # instead of filtered search — avoids needing a payload index on work_uuid.
    if work_uuid:
        try:
            qdrant_response = qdrant.fetch_vector_by_id(
                collection_name="books_catalog",
                point_id=work_uuid,  # Qdrant point ID = work_uuid
            )

            if qdrant_response and qdrant_response.get("vector"):
                book_vector = qdrant_response["vector"]

                if signal_weight < 0:
                    # ANTI-PROFILE LOGIC:
                    # If the signal is negative (Not Interested, Early DNF), we invert the book's vector
                    # before applying it to the EMA, actively pushing the user's latent profile AWAY from this semantic space.
                    book_vector = [-v for v in book_vector]

                # The `user_intelligence` module handles the EMA math and the snapshot creation.
                # In a complete Phase 2 system, you would pass the absolute `signal_weight` into
                # `update_tower2_ema` to dynamically scale the EMA Alpha.
                user_intelligence.update_tower2_ema(
                    db=db,
                    user_uuid=user_uuid,
                    new_book_vector=book_vector,
                    trigger_event=event.event_type.value,
                )
        except Exception as e:
            logger.error(
                f"Failed to route Tower 2 latent update for event {event.event_uuid}: {e}"
            )


def _extract_tower1_state(profile: UserProfile) -> Dict[str, Any]:
    """Helper to dump current float values for the event snapshot."""
    if not profile:
        return {}
    return {
        column.name: getattr(profile, column.name)
        for column in profile.__table__.columns
        if column.name not in ["user_uuid", "tower2_embedding", "updated_at"]
        and getattr(profile, column.name) is not None
    }


def _auto_track_author(db: Session, user_uuid: str, work_uuid: str):
    """
    When a user finishes a book, automatically add the author to their
    tracked authors list. Idempotent — does nothing if already tracked.
    """
    from sqlalchemy import select as _select

    work = db.execute(
        _select(Work).where(Work.work_uuid == work_uuid)
    ).scalar_one_or_none()
    if not work:
        return

    existing = db.execute(
        _select(TrackedAuthor).where(
            TrackedAuthor.user_uuid == user_uuid,
            TrackedAuthor.person_uuid == work.person_uuid,
        )
    ).scalar_one_or_none()
    if not existing:
        db.add(
            TrackedAuthor(
                user_uuid=user_uuid,
                person_uuid=work.person_uuid,
            )
        )
        logger.info(f"Auto-tracked author {work.person_uuid} for user {user_uuid}")
