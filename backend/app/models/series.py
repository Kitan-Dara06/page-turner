import uuid
from typing import List, Optional

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Series(Base):
    __tablename__ = "series"

    series_uuid: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    title: Mapped[str] = mapped_column(String, nullable=False)
    person_uuid: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("persons.person_uuid"), nullable=False
    )
    total_core_works: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Relationships
    person: Mapped["Person"] = relationship("Person", back_populates="series")
    works: Mapped[List["SeriesWork"]] = relationship(
        "SeriesWork", back_populates="series"
    )


class SeriesWork(Base):
    __tablename__ = "series_works"

    series_uuid: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("series.series_uuid"), primary_key=True
    )
    work_uuid: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("works.work_uuid"), primary_key=True
    )
    order_float: Mapped[float] = mapped_column(Float, nullable=False)
    is_core_storyline: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )

    # Relationships
    series: Mapped["Series"] = relationship("Series", back_populates="works")
    work: Mapped["Work"] = relationship("Work", back_populates="series_links")
