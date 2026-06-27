import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import ENUM as PgEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class EventType(str, Enum):
    LOGGED_READ = "logged_read"
    NOT_INTERESTED = "not_interested"
    REREAD = "reread"
    CHECKPOINT_UPDATE = "checkpoint_update"
    QUERY = "query"
    TBR_ADD = "tbr_add"
    INTERESTED = "interested"  # Soft positive — aware, open, not yet committed
    EXPLORATION_OUTCOME = "exploration_outcome"  # FR-EX: exploration loop feedback
    AUTHOR_NEW_RELEASE = "author_new_release"  # FR-AT-02: release alert


class AbandonmentStage(str, Enum):
    BARELY_STARTED = "barely_started"
    HALFWAY = "halfway"
    NEARLY_FINISHED = "nearly_finished"


class InteractionEvent(Base):
    __tablename__ = "interaction_events"

    event_uuid: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_uuid: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.user_uuid"), index=True, nullable=False
    )
    work_uuid: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("works.work_uuid"), nullable=True
    )
    event_type: Mapped[EventType] = mapped_column(
        PgEnum(EventType, name="event_type_enum", create_type=False), nullable=False
    )
    event_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    session_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    query_text: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    mood_tags: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    time_of_day: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    day_of_week: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    tower1_snapshot: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSONB, nullable=True
    )
    stated_rating: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    abandonment_stage: Mapped[Optional[AbandonmentStage]] = mapped_column(
        PgEnum(AbandonmentStage, name="abandonment_stage_enum", create_type=False),
        nullable=True,
    )

    # Relationships
    work: Mapped["Work"] = relationship("Work")
