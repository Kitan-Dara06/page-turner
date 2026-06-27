"""
Exploration Service
Manages the exploration loop — surfacing books outside the reader's
established taste profile to prevent filter bubble calcification.
Implements SRS Section 6.4 (Exploration & Discovery Loop).
"""

import math
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.integrations import qdrant as qdrant_integration
from app.models.books import Work
from app.models.events import EventType, InteractionEvent
from app.models.recommendations import RecommendationLog
from app.models.users import UserProfile

# ------------------------------------------------------------------
# Constants (SRS Section 6.4)
# ------------------------------------------------------------------

EXPLORATION_INJECT_POSITION = 3  # 0-indexed, so 4th result
EXPLORATION_MINIMUM_INTERACTIONS = 20
EXPLORATION_BASE_RATE = 5
EXPLORATION_RATE_REDUCTION_THRESHOLD = 0.75
EXPLORATION_COOLDOWN_DAYS = 30
ANTI_PROFILE_DISTANCE_FACTOR = 0.35


class ExplorationService:
    """
    Manages exploration candidate selection and injection timing.
    """

    def __init__(self, session: Session):
        self.session = session

    # ------------------------------------------------------------------
    # Gate: should this request include an exploration candidate?
    # ------------------------------------------------------------------

    def should_explore(self, user_uuid: UUID) -> bool:
        interaction_count = self._get_interaction_count(user_uuid)
        if interaction_count < EXPLORATION_MINIMUM_INTERACTIONS:
            return False

        profile = self._get_profile(user_uuid)
        if not profile:
            return False

        effective_rate = self._compute_exploration_rate(profile)
        if interaction_count % effective_rate != 0:
            return False

        last_exploration = self._get_last_exploration_timestamp(user_uuid)
        if last_exploration:
            cutoff = datetime.now(timezone.utc) - timedelta(
                days=EXPLORATION_COOLDOWN_DAYS
            )
            if last_exploration > cutoff:
                return False

        return True

    def _compute_exploration_rate(self, profile: UserProfile) -> int:
        """
        FR-EX-03: Modulate exploration rate based on profile confidence
        AND recent satisfaction signals.
        - High satisfaction (fast completions, series continuation) -> explore more
        - Low satisfaction (repeated skips, not-interested) -> explore less
        """
        base_rate = EXPLORATION_BASE_RATE
        confidence = getattr(profile, "profile_confidence", 0.0) or 0.0
        if confidence >= EXPLORATION_RATE_REDUCTION_THRESHOLD:
            base_rate = base_rate * 2

        # FR-EX-03: satisfaction modulation
        satisfaction = self._get_recent_satisfaction(profile.user_uuid)
        if satisfaction >= 0.7:
            base_rate = max(2, base_rate // 2)
        elif satisfaction <= 0.3:
            base_rate = base_rate * 2

        return base_rate

    def _get_recent_satisfaction(self, user_uuid: UUID) -> float:
        """
        Compute 0.0-1.0 satisfaction from recent interaction signals.
        High: completions, rereads, TBR adds. Low: not-interested.
        Returns 0.5 (neutral) if insufficient data.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=14)
        recent = (
            self.session.execute(
                select(InteractionEvent)
                .where(InteractionEvent.user_uuid == user_uuid)
                .where(InteractionEvent.event_timestamp >= cutoff)
            )
            .scalars()
            .all()
        )
        pos = neg = 0.0
        for e in recent:
            if e.event_type == EventType.LOGGED_READ:
                pos += 1.0
            elif e.event_type == EventType.REREAD:
                pos += 2.0
            elif e.event_type == EventType.NOT_INTERESTED:
                neg += 1.0
            elif e.event_type == EventType.TBR_ADD:
                pos += 0.5
        total = pos + neg
        return pos / total if total > 0 else 0.5

    # ------------------------------------------------------------------
    # Candidate Selection
    # ------------------------------------------------------------------

    def get_exploration_candidate(
        self,
        user_uuid: UUID,
        exclude_work_uuids: list[UUID],
    ) -> Work | None:
        profile = self._get_profile(user_uuid)
        if not profile:
            return None

        recently_explored = self._get_recently_explored_work_uuids(user_uuid)
        full_exclusion = set(exclude_work_uuids) | recently_explored

        anti_profile_vector = self._build_anti_profile_vector(profile)
        if anti_profile_vector is None:
            return None

        candidates = qdrant_integration.search_knn(
            "books_catalog",
            anti_profile_vector,
            limit=20,
        )

        for candidate in candidates:
            work_uuid = UUID(candidate["id"])
            if work_uuid in full_exclusion:
                continue

            work = (
                self.session.execute(
                    select(Work)
                    .options(joinedload(Work.person))
                    .where(Work.work_uuid == work_uuid)
                )
                .unique()
                .scalar_one_or_none()
            )

            if work and work.enrichment_status == "complete":
                return work

        return None

    def _build_anti_profile_vector(self, profile: UserProfile) -> list[float] | None:
        centroid = getattr(profile, "embedding_centroid", None)
        if not centroid or not isinstance(centroid, list):
            return None

        dim = len(centroid)
        pivot = math.floor(dim * ANTI_PROFILE_DISTANCE_FACTOR)

        anti_vector = centroid[:]
        indexed = sorted(enumerate(centroid), key=lambda x: abs(x[1]))
        for i, _ in indexed[:pivot]:
            anti_vector[i] = -anti_vector[i]

        return anti_vector

    # ------------------------------------------------------------------
    # Outcome Recording
    # ------------------------------------------------------------------

    def record_exploration_outcome(
        self,
        user_uuid: UUID,
        work_uuid: UUID,
        outcome: str,
    ) -> None:
        """Records exploration outcome. 'negative' signals feed anti-profile."""
        event = InteractionEvent(
            user_uuid=user_uuid,
            work_uuid=work_uuid,
            event_type=EventType.EXPLORATION_OUTCOME,
            mood_tags={
                "exploration_outcome": outcome,
                "anti_profile_signal": outcome == "negative",
            },
        )
        self.session.add(event)
        self.session.flush()

    def get_anti_profile_signals(self, user_uuid: UUID) -> list[dict]:
        rows = (
            self.session.execute(
                select(InteractionEvent).where(
                    InteractionEvent.user_uuid == user_uuid,
                    InteractionEvent.event_type == EventType.EXPLORATION_OUTCOME,
                )
            )
            .scalars()
            .all()
        )

        return [
            {
                "work_uuid": e.work_uuid,
                "timestamp": e.event_timestamp,
                "outcome": (e.mood_tags or {}).get("exploration_outcome"),
            }
            for e in rows
            if (e.mood_tags or {}).get("anti_profile_signal") is True
        ]

    # ------------------------------------------------------------------
    # Injection
    # ------------------------------------------------------------------

    def inject_exploration_candidate(
        self,
        ranked_results: list,
        candidate,
    ) -> list:
        position = min(EXPLORATION_INJECT_POSITION, len(ranked_results))
        return ranked_results[:position] + [candidate] + ranked_results[position:]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_interaction_count(self, user_uuid: UUID) -> int:
        result = self.session.execute(
            select(func.count(InteractionEvent.event_uuid)).where(
                InteractionEvent.user_uuid == user_uuid
            )
        )
        return result.scalar_one() or 0

    def _get_profile(self, user_uuid: UUID) -> UserProfile | None:
        return self.session.execute(
            select(UserProfile).where(UserProfile.user_uuid == user_uuid)
        ).scalar_one_or_none()

    def _get_last_exploration_timestamp(self, user_uuid: UUID) -> datetime | None:
        return self.session.execute(
            select(InteractionEvent.event_timestamp)
            .where(
                InteractionEvent.user_uuid == user_uuid,
                InteractionEvent.event_type == EventType.EXPLORATION_OUTCOME,
            )
            .order_by(InteractionEvent.event_timestamp.desc())
            .limit(1)
        ).scalar_one_or_none()

    def _get_recently_explored_work_uuids(self, user_uuid: UUID) -> set[UUID]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=EXPLORATION_COOLDOWN_DAYS)
        rows = (
            self.session.execute(
                select(InteractionEvent.work_uuid).where(
                    InteractionEvent.user_uuid == user_uuid,
                    InteractionEvent.event_type == EventType.EXPLORATION_OUTCOME,
                    InteractionEvent.event_timestamp >= cutoff,
                )
            )
            .scalars()
            .all()
        )
        return {row for row in rows if row}
