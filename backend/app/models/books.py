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

    @property
    def page_count(self) -> Optional[int]:
        """Return page count from the first edition that has one."""
        if self.editions:
            for edition in self.editions:
                if edition.page_count is not None:
                    return edition.page_count
        return None

    @property
    def publication_year(self) -> Optional[int]:
        """Derive publication year from publication_date or first edition."""
        if self.publication_date:
            return self.publication_date.year
        if self.editions:
            for edition in self.editions:
                if edition.publication_date:
                    return edition.publication_date.year
        return None

    @property
    def series(self):
        """Return the primary SeriesWork link (for SeriesInfo serialization), or None."""
        if self.series_links:
            # Prefer core storyline entries; fall back to first link
            core = [sl for sl in self.series_links if sl.is_core_storyline]
            link = core[0] if core else self.series_links[0]
            # Return an object whose attributes match SeriesInfo
            return _SeriesInfoProxy(link)
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


class _SeriesInfoProxy:
    """
    Lightweight bridge so `Work.series` (a property returning a SeriesWork link)
    presents the attribute shape that `SeriesInfo(from_attributes=True)` expects:
      series_uuid, title, order_float, is_core_storyline
    """

    __slots__ = ("series_uuid", "title", "order_float", "is_core_storyline")

    def __init__(self, link: "SeriesWork") -> None:
        self.series_uuid = link.series.series_uuid
        self.title = link.series.title
        self.order_float = link.order_float
        self.is_core_storyline = link.is_core_storyline

