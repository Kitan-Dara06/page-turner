import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import ENUM as PgEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class TBRStatus(str, Enum):
    ACTIVE = "active"
    DROPPED = "dropped"
    CONVERTED_TO_READ = "converted_to_read"


class TBREntry(Base):
    __tablename__ = "tbr_entries"

    tbr_uuid: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_uuid: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.user_uuid"), index=True, nullable=False
    )
    work_uuid: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("works.work_uuid"), nullable=False
    )

    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    add_query_text: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    add_mood_tags: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSONB, nullable=True
    )
    add_time_of_day: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    add_day_of_week: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    priority_score: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    skip_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[TBRStatus] = mapped_column(
        PgEnum(TBRStatus, name="tbr_status_enum", create_type=False),
        default=TBRStatus.ACTIVE,
        nullable=False,
    )

    # Relationships
    work: Mapped["Work"] = relationship("Work")
