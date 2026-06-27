from __future__ import annotations

import uuid
from typing import List, Optional

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Person(Base):
    __tablename__ = "persons"

    person_uuid: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    canonical_name: Mapped[str] = mapped_column(String, nullable=False)

    # Relationships
    pen_names: Mapped[List["PenName"]] = relationship(
        "PenName", back_populates="person"
    )
    works: Mapped[List["Work"]] = relationship("Work", back_populates="person")
    series: Mapped[List["Series"]] = relationship("Series", back_populates="person")


class PenName(Base):
    __tablename__ = "pen_names"

    pen_name_uuid: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    person_uuid: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("persons.person_uuid"), nullable=False
    )
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    primary_genre: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # Relationships
    person: Mapped["Person"] = relationship("Person", back_populates="pen_names")
