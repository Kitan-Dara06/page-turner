import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class TrackedAuthor(Base):
    __tablename__ = "tracked_authors"

    user_uuid: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.user_uuid"), primary_key=True
    )
    person_uuid: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("persons.person_uuid"), primary_key=True
    )
    tracked_since: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    last_known_release_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    person: Mapped["Person"] = relationship("Person")
