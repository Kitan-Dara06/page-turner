import uuid
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Trope(Base):
    __tablename__ = "tropes"

    trope_uuid: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    canonical_name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    depth_level: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_root_hub: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Relationships
    aliases: Mapped[List["TropeAlias"]] = relationship(
        "TropeAlias", back_populates="trope"
    )


class TropeParent(Base):
    __tablename__ = "trope_parents"

    trope_uuid: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tropes.trope_uuid"), primary_key=True
    )
    parent_trope_uuid: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tropes.trope_uuid"), primary_key=True
    )


class TropeAlias(Base):
    __tablename__ = "trope_aliases"

    alias_uuid: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    trope_uuid: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tropes.trope_uuid"), nullable=False
    )
    alias_text: Mapped[str] = mapped_column(String, nullable=False)
    source: Mapped[str] = mapped_column(String, nullable=False)

    # Relationships
    trope: Mapped["Trope"] = relationship("Trope", back_populates="aliases")


class BookTrope(Base):
    __tablename__ = "book_tropes"

    work_uuid: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("works.work_uuid"), primary_key=True
    )
    trope_uuid: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tropes.trope_uuid"), primary_key=True
    )
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False)

    # Relationships
    work: Mapped["Work"] = relationship("Work", back_populates="tropes")
    trope: Mapped["Trope"] = relationship("Trope", foreign_keys=[trope_uuid])


class OrphanQueue(Base):
    __tablename__ = "orphan_queue"

    tag_text: Mapped[str] = mapped_column(String, primary_key=True)
    source: Mapped[str] = mapped_column(String, nullable=False)
    frequency_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    first_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    last_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    llm_closest_match: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    llm_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # Source book — populated when enrichment writes the orphan entry.
    # NULL for legacy entries from before this column was added.
    source_work_uuid: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("works.work_uuid"), nullable=True
    )
