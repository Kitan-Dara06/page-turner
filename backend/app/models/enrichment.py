from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class EnrichmentCache(Base):
    __tablename__ = "enrichment_cache"

    work_uuid: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("works.work_uuid"), primary_key=True
    )

    # Pipeline step tracking — enables safe Celery retries
    last_completed_step: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # Step 1: Google Books
    description: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    raw_categories: Mapped[Optional[list[str]]] = mapped_column(JSONB, nullable=True)

    # Step 2: OpenLibrary
    subject_tags: Mapped[Optional[list[str]]] = mapped_column(JSONB, nullable=True)
    series_raw: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    olid: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # Step 3: LLM Extraction
    tower1_snapshot: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSONB, nullable=True
    )

    # Step 4: Tavily
    tavily_sentiment: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    hallucination_verified: Mapped[Optional[str]] = mapped_column(
        String, default="unverifiable", nullable=True
    )
    community_buzz_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    sentiment_snippets: Mapped[Optional[list[str]]] = mapped_column(
        JSONB, nullable=True
    )
    cliffhanger_flag: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    trigger_warnings: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSONB, nullable=True
    )
    controversy_flag: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )

    # Metadata
    enriched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    flashcard_pool: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    refresh_due_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Enrichment intelligence flags
    # is_narrative=False → skip trope extraction, Tower 1 only (non-fiction)
    is_narrative: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # taxonomy_version stamped at enrichment time; divergence from settings value triggers re-queue
    taxonomy_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # parametric_inference=True → Stage 2 LLM used (metadata insufficient); confidence -0.1 applied
    parametric_inference: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )

    # Hot/background enrichment tracking
    # Incremented on each failed background enrichment attempt.
    # The sweeper uses this to detect stuck partials and gives up after PARTIAL_MAX_RETRIES.
    partial_retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Relationships
    work: Mapped["Work"] = relationship("Work")
