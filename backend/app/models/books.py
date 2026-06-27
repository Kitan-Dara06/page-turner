from __future__ import annotations

import uuid
from datetime import datetime
from typing import List, Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Work(Base):
    __tablename__ = "works"

    work_uuid: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    title: Mapped[str] = mapped_column(String, nullable=False)
    language: Mapped[str] = mapped_column(String, nullable=False, default="en")
    aggregate_rating: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    person_uuid: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("persons.person_uuid"), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    enrichment_status: Mapped[str] = mapped_column(
        String, default="pending", nullable=False
    )
    publication_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    @property
    def author(self):
        return self.person

    @property
    def cover_url(self):
        """Return the cover thumbnail from the first edition, or None."""
        if self.editions:
            for edition in self.editions:
                if edition.cover_url:
                    return edition.cover_url
        return None

    # Relationships
    person: Mapped["Person"] = relationship("Person", back_populates="works")
    editions: Mapped[List["Edition"]] = relationship("Edition", back_populates="work")
    series_links: Mapped[List["SeriesWork"]] = relationship(
        "SeriesWork", back_populates="work"
    )
    tropes: Mapped[List["BookTrope"]] = relationship("BookTrope", back_populates="work")


class Edition(Base):
    __tablename__ = "editions"

    edition_uuid: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    work_uuid: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("works.work_uuid"), nullable=False
    )
    isbn: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    format: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    page_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    cover_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    publisher: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    publication_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    work: Mapped["Work"] = relationship("Work", back_populates="editions")
