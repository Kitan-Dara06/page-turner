import logging
import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.books import Work
from app.models.tbr import TBREntry, TBRStatus

logger = logging.getLogger(__name__)

# ==========================================
# TBR Decay Constants (Tuning Parameters)
# ==========================================
# Alpha: Time-decay constant (per day).
# At 0.005, a book untouched for 6 months (180 days) decays to ~40% priority on time alone.
ALPHA_TIME_DECAY = 0.005

# Beta: Active skip penalty.
# At 0.15, skipping a book 4 times drops its priority to ~54% even if added yesterday.
BETA_SKIP_PENALTY = 0.15

# Threshold: When priority drops below this float, the Checkpoint prompts the user to drop it.
DROP_THRESHOLD = 0.30


def add_to_tbr(
    db: Session,
    user_uuid: str,
    work_uuid: str,
    query_text: Optional[str] = None,
    mood_tags: Optional[Dict[str, Any]] = None,
) -> TBREntry:
    """
    Implements FR-TBR-01: Context-Aware TBR Add.
    Captures the exact state of the user at the moment they added the book.
    """
    now = datetime.now(timezone.utc)

    # Check if it already exists (maybe they dropped it previously and are re-adding)
    existing_tbr = db.execute(
        select(TBREntry)
        .where(TBREntry.user_uuid == user_uuid)
        .where(TBREntry.work_uuid == work_uuid)
    ).scalar_one_or_none()

    if existing_tbr:
        # Reset the context and priority if re-added
        existing_tbr.status = TBRStatus.ACTIVE
        existing_tbr.priority_score = 1.0
        existing_tbr.skip_count = 0
        existing_tbr.added_at = now
        existing_tbr.add_query_text = query_text
        existing_tbr.add_mood_tags = mood_tags
        existing_tbr.add_time_of_day = _get_time_of_day(now)
        existing_tbr.add_day_of_week = now.strftime("%A").lower()
        db.commit()
        return existing_tbr

    # Create new entry with full context payload
    new_tbr = TBREntry(
        user_uuid=user_uuid,
        work_uuid=work_uuid,
        added_at=now,
        add_query_text=query_text,
        add_mood_tags=mood_tags,
        add_time_of_day=_get_time_of_day(now),
        add_day_of_week=now.strftime("%A").lower(),
        priority_score=1.0,
        skip_count=0,
        status=TBRStatus.ACTIVE,
    )
    db.add(new_tbr)
    db.commit()
    logger.info(f"Book {work_uuid} added to TBR for user {user_uuid} with priority 1.0")
    return new_tbr


def record_tbr_skip(db: Session, user_uuid: str, work_uuid: str):
    """
    Called when a TBR-sourced recommendation is surfaced to the user but they do not log an interaction.
    Increments the skip count and forces an immediate priority recalculation.
    """
    tbr = db.execute(
        select(TBREntry)
        .where(TBREntry.user_uuid == user_uuid)
        .where(TBREntry.work_uuid == work_uuid)
        .where(TBREntry.status == TBRStatus.ACTIVE)
    ).scalar_one_or_none()

    if tbr:
        tbr.skip_count += 1
        tbr.priority_score = _calculate_decay(tbr.added_at, tbr.skip_count)
        db.commit()
        logger.info(
            f"Recorded skip for TBR {work_uuid}. New skip count: {tbr.skip_count}, Score: {tbr.priority_score:.2f}"
        )


def apply_global_tbr_decay(db: Session):
    """
    Implements FR-TBR-02: TBR Priority Decay.
    Designed to be called by the `daily_tbr_priority_decay` Celery beat task.
    Iterates over all active TBR entries and updates their priority score based on time elapsed.
    """
    logger.info("Starting global TBR priority decay calculation...")

    # In a production environment with millions of rows, you would batch this query
    active_entries = (
        db.execute(select(TBREntry).where(TBREntry.status == TBRStatus.ACTIVE))
        .scalars()
        .all()
    )

    updated_count = 0
    for entry in active_entries:
        new_score = _calculate_decay(entry.added_at, entry.skip_count)
        if entry.priority_score != new_score:
            entry.priority_score = new_score
            updated_count += 1

    db.commit()
    logger.info(f"TBR decay complete. Updated {updated_count} active entries.")


def get_drop_prompt_candidates(db: Session, user_uuid: str) -> List[TBREntry]:
    """
    Called during the pre-recommendation Checkpoint flow.
    Surfaces TBR entries that have dropped below the priority threshold so the user can formally abandon them.
    """
    decayed_entries = (
        db.execute(
            select(TBREntry)
            .where(TBREntry.user_uuid == user_uuid)
            .where(TBREntry.status == TBRStatus.ACTIVE)
            .where(TBREntry.priority_score < DROP_THRESHOLD)
            .order_by(TBREntry.priority_score.asc())  # Show the most decayed first
        )
        .scalars()
        .all()
    )

    return decayed_entries


def drop_tbr_entry(db: Session, user_uuid: str, tbr_uuid: str) -> bool:
    """Marks a TBR entry as formally dropped (Graveyard)."""
    entry = db.execute(
        select(TBREntry)
        .where(TBREntry.tbr_uuid == tbr_uuid)
        .where(TBREntry.user_uuid == user_uuid)
    ).scalar_one_or_none()

    if entry:
        entry.status = TBRStatus.DROPPED
        db.commit()
        return True
    return False


# ==========================================
# Private Mathematical & Temporal Helpers
# ==========================================


def _calculate_decay(added_at: datetime, skip_count: int) -> float:
    """
    The core decay math: P = e^(-(alpha*t + beta*s))
    """
    # Calculate days elapsed (t)
    delta = datetime.now(timezone.utc) - added_at
    days_elapsed = max(0, delta.days)

    # Apply exponential decay
    exponent = (ALPHA_TIME_DECAY * days_elapsed) + (BETA_SKIP_PENALTY * skip_count)
    priority = math.exp(-exponent)

    # Clamp between 0.0 and 1.0, rounded for clean DB storage
    return round(max(0.0, min(1.0, priority)), 4)


def _get_time_of_day(dt: datetime) -> str:
    """Categorizes the timestamp for temporal pattern matching."""
    hour = dt.hour
    if 5 <= hour < 12:
        return "morning"
    elif 12 <= hour < 17:
        return "afternoon"
    elif 17 <= hour < 22:
        return "evening"
    else:
        return "late_night"
