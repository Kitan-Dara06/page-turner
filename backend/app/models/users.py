import uuid
from datetime import datetime, timezone
from typing import Any, List, Optional

from sqlalchemy import ARRAY, Boolean, DateTime, Float, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class User(Base):
    __tablename__ = "users"

    user_uuid: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    calibration_ends_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    calibration_complete: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )

    # Relationships
    profile: Mapped["UserProfile"] = relationship(
        "UserProfile", back_populates="user", uselist=False
    )


class UserProfile(Base):
    __tablename__ = "user_profiles"

    user_uuid: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.user_uuid"), primary_key=True
    )

    # ── Tower 1: Universal Dimensions (18 fields, SRS §4.2) ──
    darkness_tolerance: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    angst_level: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    violence_tolerance: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    thematic_density: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    pacing_preference: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    prose_density: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    narrative_linearity: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    plot_vs_character: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    setting_scope: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    speculative_deviation: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    world_building_appetite: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True
    )
    emotional_intensity: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    standalone_preference: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    series_completion_tendency: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True
    )
    reread_tendency: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    exploration_tolerance: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    pov_structure: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    protagonist_agency: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # ── Tower 1: Non-Fiction Conditional (2 fields, SRS §4.2) ──
    factual_density: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    instructional_vs_conceptual: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True
    )

    # ── Tower 1: Romance Conditional (6 fields, SRS §4.2) ──
    explicit_content_level: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True
    )
    romance_centrality: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    hea_requirement: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    relationship_ratio: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    role_rigidity: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    relationship_pace: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # ── Tower 2 Latent Profile ──
    tower2_embedding: Mapped[Optional[List[float]]] = mapped_column(
        ARRAY(Float), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="profile")


class UserProfileSnapshot(Base):
    __tablename__ = "user_profile_snapshots"

    snapshot_uuid: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_uuid: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.user_uuid"), index=True, nullable=False
    )
    snapshot_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    taken_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    trigger_event: Mapped[str] = mapped_column(String, nullable=False)
