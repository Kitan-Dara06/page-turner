import logging
import uuid as _uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import sqlalchemy as sa
from sqlalchemy import and_, func, select, text
from sqlalchemy.orm import Session

from app.config import settings
from app.models.events import EventType, InteractionEvent
from app.models.users import User, UserProfile, UserProfileSnapshot

logger = logging.getLogger(__name__)

TOWER1_LEARNING_RATE = 0.3  # default fallback — blended rate replaces this
TOWER2_EMA_ALPHA = 0.2  # default fallback — dynamic alpha replaces this
ROMANCE_ACTIVATION_THRESHOLD = 5

# FR-MH: Three Memory Horizon Blending
SHORT_TERM_DAYS = 7
MEDIUM_TERM_DAYS = 90
HORIZON_WEIGHTS = (0.2, 0.3, 0.5)  # short, medium, long


def _ensure_user_row(db: Session, user_uuid: str) -> None:
    """
    Supabase creates rows in auth.users on signup but NOT in public.users.
    This guard upserts a minimal users row so FK constraints are always
    satisfied before touching user_profiles or any other child table.

    Uses raw SQL upsert (INSERT ... ON CONFLICT DO NOTHING) to avoid ORM
    edge cases where a flush-then-commit sequence loses the row.
    """
    user_uuid_obj = _uuid.UUID(user_uuid)
    exists = db.execute(
        select(User.user_uuid).where(User.user_uuid == user_uuid_obj)
    ).scalar_one_or_none()
    if exists:
        return
    # Raw upsert — bypasses ORM lifecycle, visible immediately to FK checks
    db.execute(
        text(
            "INSERT INTO users (user_uuid, created_at, calibration_complete) "
            "VALUES (:uid, now(), false) ON CONFLICT (user_uuid) DO NOTHING"
        ),
        {"uid": user_uuid_obj},
    )
    db.flush()


def initialize_user_profile(db: Session, user_uuid: str) -> UserProfile:
    # Always ensure the parent users row exists first (Supabase JWT auth gap)
    _ensure_user_row(db, user_uuid)

    profile = db.execute(
        select(UserProfile).where(UserProfile.user_uuid == user_uuid)
    ).scalar_one_or_none()
    if not profile:
        profile = UserProfile(user_uuid=user_uuid)
        db.add(profile)
        db.commit()
        _create_snapshot(db, profile, trigger_event="account_creation")
    return profile


def apply_tower1_delta(
    db: Session,
    user_uuid: str,
    delta: Dict[str, float],
    trigger_event: str,
    is_narrative: bool = True,
) -> UserProfile:
    # Ensure profile exists — new users (onboarding, first query) may not have one.
    # Also ensures the parent users row exists (FK constraint).
    profile = initialize_user_profile(db, user_uuid)

    _check_and_activate_romance_dimensions(db, profile, user_uuid, delta)

    # FR-MH: Blended learning rate from horizon segmentation
    blended_rate = _compute_blended_learning_rate(db, user_uuid)

    # Non-narrative works: only update shared dimensions (thematic_density,
    # pacing_preference, setting_scope, emotional_intensity, exploration_tolerance,
    # reread_tendency). Fiction-only and romance-conditional dims are meaningless
    # for non-fiction — skip them.
    _fiction_only_dims = {
        "darkness_tolerance",
        "angst_level",
        "violence_tolerance",
        "speculative_deviation",
        "world_building_appetite",
        "plot_vs_character",
        "standalone_preference",
        "series_completion_tendency",
        "pov_structure",
        "protagonist_agency",
        "narrative_linearity",
        "prose_density",
        # Romance-conditional — meaningless for non-fiction
        "explicit_content_level",
        "romance_centrality",
        "hea_requirement",
        "relationship_ratio",
        "role_rigidity",
        "relationship_pace",
    }

    for field, new_value in delta.items():
        if not is_narrative and field in _fiction_only_dims:
            continue  # skip fiction-only dims for non-narrative works
        if hasattr(profile, field):
            current_value = getattr(profile, field)
            if current_value is None:
                setattr(profile, field, float(new_value))
            else:
                blended_value = (current_value * (1 - blended_rate)) + (
                    new_value * blended_rate
                )
                setattr(profile, field, round(blended_value, 4))

    profile.updated_at = datetime.now(timezone.utc)
    db.flush()

    if _is_meaningful_interaction(trigger_event):
        _create_snapshot(db, profile, trigger_event=trigger_event)

    db.commit()
    return profile


def update_tower2_ema(
    db: Session, user_uuid: str, new_book_vector: List[float], trigger_event: str
):
    profile = initialize_user_profile(db, user_uuid)

    if profile.tower2_embedding is None:
        profile.tower2_embedding = new_book_vector
    else:
        # FR-EV: Dynamic alpha from completion velocity
        alpha = _compute_dynamic_alpha(db, user_uuid)
        updated_vector = [
            round((new_val * alpha) + (old_val * (1 - alpha)), 6)
            for new_val, old_val in zip(new_book_vector, profile.tower2_embedding)
        ]
        profile.tower2_embedding = updated_vector

    profile.updated_at = datetime.now(timezone.utc)
    db.flush()
    _create_snapshot(db, profile, trigger_event=trigger_event)
    db.commit()


def _check_and_activate_romance_dimensions(
    db: Session, profile: UserProfile, user_uuid: str, current_delta: Dict[str, float]
):
    """Phase 2: romance dimension activation. Skipped if Supabase ?| operator unavailable."""
    pass


def _create_snapshot(db: Session, profile: UserProfile, trigger_event: str):
    snapshot_data = {
        column.name: getattr(profile, column.name)
        for column in profile.__table__.columns
        if column.name not in ["user_uuid", "tower2_embedding", "updated_at"]
    }
    snapshot = UserProfileSnapshot(
        user_uuid=profile.user_uuid,
        snapshot_json=snapshot_data,
        trigger_event=trigger_event,
    )
    db.add(snapshot)


def _is_meaningful_interaction(trigger_event: str) -> bool:
    meaningful_events = [
        EventType.LOGGED_READ.value,
        EventType.NOT_INTERESTED.value,
        EventType.QUERY.value,
        EventType.TBR_ADD.value,
        "checkpoint_update_finished",
        "checkpoint_update_abandoned",
    ]
    return trigger_event in meaningful_events


def get_temporal_fingerprint(
    db: Session, user_uuid: str, lookback_days: int = 90
) -> Dict[str, float]:
    """
    FR-QR-07: Build temporal reading preference fingerprint.

    Queries interaction_events for the last `lookback_days`, groups by
    (day_of_week, hour_bucket), and averages darkness_tolerance and
    emotional_intensity from tower1_snapshot at the time of each event.

    hour_bucket: 0=00-05, 1=06-11, 2=12-17, 3=18-23
    Slots with < 3 events are discarded as noise.
    """
    from datetime import datetime, timedelta, timezone

    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)

    rows = (
        db.execute(
            select(InteractionEvent)
            .where(
                InteractionEvent.user_uuid == user_uuid,
                InteractionEvent.event_timestamp >= cutoff,
                InteractionEvent.tower1_snapshot.isnot(None),
            )
            .order_by(InteractionEvent.event_timestamp)
        )
        .scalars()
        .all()
    )

    if not rows:
        return {}

    slot_accum: Dict[str, Dict[str, list]] = {}
    for event in rows:
        dow = event.event_timestamp.weekday()
        hour = event.event_timestamp.hour
        bucket = hour // 6
        slot_key = f"{dow}_{bucket}"

        if slot_key not in slot_accum:
            slot_accum[slot_key] = {"darkness_tolerance": [], "emotional_intensity": []}

        snap = event.tower1_snapshot or {}
        if "darkness_tolerance" in snap:
            slot_accum[slot_key]["darkness_tolerance"].append(
                snap["darkness_tolerance"]
            )
        if "emotional_intensity" in snap:
            slot_accum[slot_key]["emotional_intensity"].append(
                snap["emotional_intensity"]
            )

    result: Dict[str, float] = {}
    for slot_key, acc in slot_accum.items():
        for dim, values in acc.items():
            if len(values) >= 3:
                result[f"{slot_key}_{dim}"] = round(sum(values) / len(values), 4)

    return result


def get_temporal_slot_preference(
    fingerprint: Dict[str, float],
    current_hour: int,
    day_of_week: int,
) -> Optional[Dict[str, float]]:
    """
    FR-QR-07: Extract preference for the current time slot from fingerprint.
    """
    if not fingerprint:
        return None

    bucket = current_hour // 6
    slot_key = f"{day_of_week}_{bucket}"

    darkness = fingerprint.get(f"{slot_key}_darkness_tolerance")
    emotional = fingerprint.get(f"{slot_key}_emotional_intensity")

    if darkness is None and emotional is None:
        return None

    return {
        "darkness_tolerance": darkness or 0.5,
        "emotional_intensity": emotional or 0.5,
    }


# ── FR-MH: Three Memory Horizon Blending ────────────────────────────


def _compute_blended_learning_rate(db: Session, user_uuid: str) -> float:
    """
    Compute a blended EMA learning rate based on signal distribution across
    three time horizons.

    Short (0-7d)  → weight 0.2 — active reading phase, higher sensitivity
    Medium (8-90d) → weight 0.3 — stabilising
    Long (91+d)   → weight 0.5 — entrenched preference, resists drift

    Falls back to TOWER1_LEARNING_RATE (0.3) when no interaction data.
    """
    now = datetime.now(timezone.utc)
    short_cutoff = now - timedelta(days=SHORT_TERM_DAYS)
    medium_cutoff = now - timedelta(days=MEDIUM_TERM_DAYS)

    meaningful_types = [
        EventType.LOGGED_READ,
        EventType.NOT_INTERESTED,
        EventType.QUERY,
        EventType.TBR_ADD,
        EventType.INTERESTED,
    ]

    # Count per horizon
    counts = db.execute(
        select(
            func.count()
            .filter(InteractionEvent.event_timestamp >= short_cutoff)
            .label("short"),
            func.count()
            .filter(
                InteractionEvent.event_timestamp >= medium_cutoff,
                InteractionEvent.event_timestamp < short_cutoff,
            )
            .label("medium"),
            func.count()
            .filter(InteractionEvent.event_timestamp < medium_cutoff)
            .label("long"),
        ).where(
            InteractionEvent.user_uuid == user_uuid,
            InteractionEvent.event_type.in_(meaningful_types),
        )
    ).one()

    short_count, medium_count, long_count = counts.short, counts.medium, counts.long
    total = short_count + medium_count + long_count

    if total == 0:
        return TOWER1_LEARNING_RATE

    w_short, w_medium, w_long = HORIZON_WEIGHTS
    rate = (
        (short_count * w_short) + (medium_count * w_medium) + (long_count * w_long)
    ) / total

    return round(max(0.1, min(0.5, rate)), 3)


# ── FR-EV: EMA Alpha Velocity Tuning ─────────────────────────────────


def _compute_dynamic_alpha(db: Session, user_uuid: str) -> float:
    """
    Compute a dynamic Tower 2 EMA alpha based on recent completion velocity.

    High velocity (active, satisfied reader) → alpha 0.3 → faster profile updates
    Low velocity (dissatisfied or inactive) → alpha 0.1 → stable, resists drift

    Positive signals: LOGGED_READ, INTERESTED, TBR_ADD
    Negative signals: NOT_INTERESTED
    Velocity = positive / (positive + negative), clamped to [0, 1]
    Alpha = 0.1 + velocity × 0.2 → range [0.1, 0.3]

    Falls back to TOWER2_EMA_ALPHA (0.2) when no signal data.
    """
    last_10 = (
        db.execute(
            select(InteractionEvent.event_type)
            .where(
                InteractionEvent.user_uuid == user_uuid,
                InteractionEvent.event_type.in_(
                    [
                        EventType.LOGGED_READ,
                        EventType.INTERESTED,
                        EventType.TBR_ADD,
                        EventType.NOT_INTERESTED,
                    ]
                ),
            )
            .order_by(InteractionEvent.event_timestamp.desc())
            .limit(10)
        )
        .scalars()
        .all()
    )

    if not last_10:
        return TOWER2_EMA_ALPHA

    positive = sum(
        1
        for et in last_10
        if et in (EventType.LOGGED_READ, EventType.INTERESTED, EventType.TBR_ADD)
    )
    negative = sum(1 for et in last_10 if et == EventType.NOT_INTERESTED)

    if positive + negative == 0:
        return TOWER2_EMA_ALPHA

    velocity = positive / (positive + negative)
    alpha = 0.1 + (velocity * 0.2)

    return round(alpha, 3)


def _get_genre_counts(db: Session, user_uuid: str, days: int = 365) -> dict:
    """Count genre-register trope assignments across the user's reading history."""
    from app.models.tropes import BookTrope, Trope

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    rows = (
        db.execute(
            select(Trope.canonical_name)
            .join(BookTrope, BookTrope.trope_uuid == Trope.trope_uuid)
            .join(InteractionEvent, InteractionEvent.work_uuid == BookTrope.work_uuid)
            .where(
                InteractionEvent.user_uuid == user_uuid,
                InteractionEvent.event_type == EventType.LOGGED_READ,
                InteractionEvent.event_timestamp >= cutoff,
            )
        )
        .scalars()
        .all()
    )

    counts: dict = {}
    for t in rows:
        if t.endswith("Fiction") or t in (
            "Thriller",
            "Horror",
            "Fantasy",
            "Romance",
            "Sci-Fi",
            "Mystery",
            "Nonfiction",
        ):
            counts[t] = counts.get(t, 0) + 1
    return counts


# ── Phase Detection ────────────────────────────────────────────────


def detect_reader_phase(db: Session, user_uuid: str) -> dict:
    """
    Detect the reader's current behavioural phase from recent interaction patterns.

    Phases:
      - genre_sprint: 3+ books in same genre within 14 days
      - exploration: reading outside established taste profile
      - comfort: re-reading or high-similarity reads
      - dormant: no reads in 30+ days
      - active: normal mixed reading
    """
    now = datetime.now(timezone.utc)
    fourteen_days = now - timedelta(days=14)
    thirty_days = now - timedelta(days=30)

    # Recent reads
    recent_reads = (
        db.execute(
            select(InteractionEvent)
            .where(
                InteractionEvent.user_uuid == user_uuid,
                InteractionEvent.event_type == EventType.LOGGED_READ,
                InteractionEvent.event_timestamp >= thirty_days,
            )
            .order_by(InteractionEvent.event_timestamp.desc())
            .limit(50)
        )
        .scalars()
        .all()
    )

    if not recent_reads:
        return {
            "phase": "dormant",
            "confidence": 1.0,
            "description": "No recent reading activity.",
        }

    # Count reads in last 14 days
    reads_14d = [r for r in recent_reads if r.event_timestamp >= fourteen_days]

    if not reads_14d:
        return {
            "phase": "dormant",
            "confidence": 0.8,
            "description": "Last read was more than two weeks ago.",
        }

    # REREAD detection
    rereads = [r for r in reads_14d if r.event_type == EventType.REREAD]
    if len(rereads) >= 2:
        return {
            "phase": "comfort",
            "confidence": 0.9,
            "description": "You've been revisiting old favourites.",
        }

    # Genre sprint detection — load tropes for recent books
    from app.models.tropes import BookTrope, Trope

    genre_counts: dict = {}
    for r in reads_14d[:20]:
        if not r.work_uuid:
            continue
        tropes = (
            db.execute(
                select(Trope.canonical_name)
                .join(BookTrope, BookTrope.trope_uuid == Trope.trope_uuid)
                .where(BookTrope.work_uuid == r.work_uuid)
            )
            .scalars()
            .all()
        )

        for t in tropes:
            if t.endswith("Fiction") or t in (
                "Thriller",
                "Horror",
                "Fantasy",
                "Romance",
                "Sci-Fi",
                "Mystery",
                "Nonfiction",
            ):
                genre_counts[t] = genre_counts.get(t, 0) + 1

    if genre_counts:
        top_genre, top_count = max(genre_counts.items(), key=lambda x: x[1])
        if top_count >= 3:
            return {
                "phase": "genre_sprint",
                "genre": top_genre,
                "count": top_count,
                "confidence": min(1.0, top_count / 6),
                "description": f"You've been deep in {top_genre} lately — {top_count} books in two weeks.",
                "velocity": len(reads_14d),
            }

    # Exploration detection — reading genres outside historical norm
    if len(reads_14d) >= 2 and len(recent_reads) >= 10:
        # Check if recent reads are in genres the user rarely visits
        all_time_genres = _get_genre_counts(db, user_uuid, days=365)
        recent_genres = set(genre_counts.keys())
        historical_genres = set(all_time_genres.keys())
        new_genres = recent_genres - historical_genres
        if new_genres:
            return {
                "phase": "exploration",
                "confidence": 0.7,
                "description": f"You're exploring new territory — trying {', '.join(sorted(new_genres))}.",
                "velocity": len(reads_14d),
            }

    # Active — default for engaged readers
    return {
        "phase": "active",
        "confidence": 0.5,
        "description": "You're reading steadily across genres.",
        "velocity": len(reads_14d),
    }
