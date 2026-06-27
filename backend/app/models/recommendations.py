import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import ENUM as PgEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class RecommendationSource(str, Enum):
    TBR = "tbr"
    VECTOR = "vector"
    LLM = "llm"
    EXPLORATION = "exploration"


class RecommendationStatus(str, Enum):
    DELIVERED = "delivered"
    FINISHED = "finished"
    ABANDONED = "abandoned"
    NOT_INTERESTED = "not_interested"
    STILL_READING = "still_reading"
    HAVENT_STARTED = "havent_started"
    REREAD = "reread"
    INTERESTED = "interested"  # Soft positive — excluded from checkpoint, eligible for resurfacing


class RecommendationLog(Base):
    __tablename__ = "recommendations_log"

    rec_uuid: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_uuid: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.user_uuid"), index=True, nullable=False
    )
    session_id: Mapped[str] = mapped_column(String, nullable=False)
    work_uuid: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("works.work_uuid"), nullable=False
    )

    rank_position: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[RecommendationSource] = mapped_column(
        PgEnum(RecommendationSource, name="rec_source_enum", create_type=False),
        nullable=False,
    )
    query_text: Mapped[str] = mapped_column(String, nullable=False)

    delivered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    status: Mapped[RecommendationStatus] = mapped_column(
        PgEnum(RecommendationStatus, name="rec_status_enum", create_type=False),
        default=RecommendationStatus.DELIVERED,
        nullable=False,
    )
    status_updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    outcome_notes: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # Relationships
    work: Mapped["Work"] = relationship("Work")
