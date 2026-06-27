"""
TBR Service Tests — Phase 1
Tests priority decay formula, drop thresholds, and TBR lifecycle.

Phase 2 items are marked with @pytest.mark.phase2 and will be skipped.
"""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from app.models.tbr import TBRStatus
from app.services.tbr_service import (
    add_to_tbr,
    apply_global_tbr_decay,
    drop_tbr_entry,
    get_drop_prompt_candidates,
    record_tbr_skip,
)


class TestAddToTBR:
    """Creating TBR entries with context."""

    def test_add_to_tbr_creates_entry(self, db, seed_user, seed_work):
        entry = add_to_tbr(
            db=db,
            user_uuid=seed_user["user_uuid"],
            work_uuid=seed_work["work_uuid"],
            query_text="slow burn fantasy",
        )
        assert entry.tbr_uuid is not None
        assert entry.status == TBRStatus.ACTIVE
        assert entry.priority_score == 1.0
        assert entry.add_query_text == "slow burn fantasy"

    def test_add_to_tbr_with_mood_tags(self, db, seed_user, seed_work):
        entry = add_to_tbr(
            db=db,
            user_uuid=seed_user["user_uuid"],
            work_uuid=seed_work["work_uuid"],
            query_text="dark romance",
            mood_tags={"darkness_tolerance": 0.9, "romance_centrality": 0.8},
        )
        assert entry.add_mood_tags is not None
        assert entry.add_mood_tags["darkness_tolerance"] == 0.9

    def test_re_add_reactivates_dropped_entry(self, db, seed_user, seed_work):
        """Re-adding a dropped entry resets its priority and status."""
        entry = add_to_tbr(
            db=db,
            user_uuid=seed_user["user_uuid"],
            work_uuid=seed_work["work_uuid"],
        )
        # Drop it
        drop_tbr_entry(db, seed_user["user_uuid"], str(entry.tbr_uuid))
        assert entry.status == TBRStatus.DROPPED

        # Re-add — should reactivate
        re_added = add_to_tbr(
            db=db,
            user_uuid=seed_user["user_uuid"],
            work_uuid=seed_work["work_uuid"],
            query_text="re-add test",
        )
        assert re_added.tbr_uuid == entry.tbr_uuid
        assert re_added.status == TBRStatus.ACTIVE
        assert re_added.priority_score == 1.0
        assert re_added.skip_count == 0


class TestPriorityDecay:
    """Priority decay formula produces correct values at known intervals."""

    def test_fresh_entry_max_priority(self, db, seed_user, seed_work):
        entry = add_to_tbr(
            db=db,
            user_uuid=seed_user["user_uuid"],
            work_uuid=seed_work["work_uuid"],
        )
        assert entry.priority_score == 1.0

    def test_decay_after_one_day(self, db, seed_user, seed_work):
        """After 1 day, priority should still be very close to 1.0."""
        entry = add_to_tbr(
            db=db,
            user_uuid=seed_user["user_uuid"],
            work_uuid=seed_work["work_uuid"],
        )
        # Simulate 1 day passing by manipulating added_at
        entry.added_at = datetime.now(timezone.utc) - timedelta(days=1)
        db.commit()

        apply_global_tbr_decay(db)
        db.refresh(entry)
        # e^(-0.005 * 1) ≈ 0.995
        assert entry.priority_score == pytest.approx(0.995, abs=0.01)

    def test_decay_at_day_30(self, db, seed_user, seed_work):
        """After 30 days, priority should be noticeably lower."""
        entry = add_to_tbr(
            db=db,
            user_uuid=seed_user["user_uuid"],
            work_uuid=seed_work["work_uuid"],
        )
        entry.added_at = datetime.now(timezone.utc) - timedelta(days=30)
        db.commit()

        apply_global_tbr_decay(db)
        db.refresh(entry)
        # e^(-0.005 * 30) ≈ 0.861
        assert entry.priority_score == pytest.approx(0.861, abs=0.01)

    def test_decay_at_day_90(self, db, seed_user, seed_work):
        """After 90 days, priority drops significantly."""
        entry = add_to_tbr(
            db=db,
            user_uuid=seed_user["user_uuid"],
            work_uuid=seed_work["work_uuid"],
        )
        entry.added_at = datetime.now(timezone.utc) - timedelta(days=90)
        db.commit()

        apply_global_tbr_decay(db)
        db.refresh(entry)
        # e^(-0.005 * 90) ≈ 0.638
        assert entry.priority_score == pytest.approx(0.638, abs=0.01)

    def test_skip_penalty_on_decay(self, db, seed_user, seed_work):
        """Skip count accelerates decay."""
        entry = add_to_tbr(
            db=db,
            user_uuid=seed_user["user_uuid"],
            work_uuid=seed_work["work_uuid"],
        )
        entry.added_at = datetime.now(timezone.utc) - timedelta(days=30)
        entry.skip_count = 4
        db.commit()

        apply_global_tbr_decay(db)
        db.refresh(entry)
        # e^(-(0.005*30 + 0.15*4)) = e^(-0.75) ≈ 0.472
        assert entry.priority_score == pytest.approx(0.472, abs=0.01)

    def test_skip_penalty_alone(self, db, seed_user, seed_work):
        """Multiple skips without significant time passing still reduces priority."""
        entry = add_to_tbr(
            db=db,
            user_uuid=seed_user["user_uuid"],
            work_uuid=seed_work["work_uuid"],
        )
        entry.added_at = datetime.now(timezone.utc) - timedelta(hours=1)
        entry.skip_count = 5
        db.commit()

        record_tbr_skip(db, seed_user["user_uuid"], seed_work["work_uuid"])
        db.refresh(entry)
        # 6 skips now: e^(-(0.005*0 + 0.15*6)) = e^(-0.9) ≈ 0.407
        assert entry.priority_score == pytest.approx(0.407, abs=0.01)


class TestDropThreshold:
    """Drop prompt threshold fires at the right priority floor."""

    def test_above_threshold_not_in_drop_prompt(self, db, seed_user, seed_work):
        entry = add_to_tbr(
            db=db,
            user_uuid=seed_user["user_uuid"],
            work_uuid=seed_work["work_uuid"],
        )
        candidates = get_drop_prompt_candidates(db, seed_user["user_uuid"])
        assert len(candidates) == 0  # Not below threshold

    def test_below_threshold_in_drop_prompt(self, db, seed_user, seed_work):
        entry = add_to_tbr(
            db=db,
            user_uuid=seed_user["user_uuid"],
            work_uuid=seed_work["work_uuid"],
        )
        # Manually set priority below threshold
        entry.priority_score = 0.25
        db.commit()

        candidates = get_drop_prompt_candidates(db, seed_user["user_uuid"])
        assert len(candidates) == 1
        assert candidates[0].tbr_uuid == entry.tbr_uuid

    def test_drop_prompt_includes_only_active(self, db, seed_user, seed_work):
        """Dropped entries should not appear in drop prompts."""
        entry = add_to_tbr(
            db=db,
            user_uuid=seed_user["user_uuid"],
            work_uuid=seed_work["work_uuid"],
        )
        entry.priority_score = 0.25
        entry.status = TBRStatus.DROPPED
        db.commit()

        candidates = get_drop_prompt_candidates(db, seed_user["user_uuid"])
        assert len(candidates) == 0  # Dropped, not active


class TestDropTBR:
    """Dropping TBR entries works correctly."""

    def test_drop_active_entry(self, db, seed_user, seed_tbr_entry):
        result = drop_tbr_entry(db, seed_user["user_uuid"], seed_tbr_entry["tbr_uuid"])
        assert result is True

    def test_drop_nonexistent_entry(self, db, seed_user):
        result = drop_tbr_entry(
            db, seed_user["user_uuid"], "00000000-0000-0000-0000-000000000999"
        )
        assert result is False

    def test_dropped_entry_status_changed(self, db, seed_user, seed_tbr_entry):
        from sqlalchemy import select

        from app.models.tbr import TBREntry

        drop_tbr_entry(db, seed_user["user_uuid"], seed_tbr_entry["tbr_uuid"])
        entry = db.execute(
            select(TBREntry).where(
                TBREntry.tbr_uuid == uuid.UUID(seed_tbr_entry["tbr_uuid"])
            )
        ).scalar_one()
        assert entry.status == TBRStatus.DROPPED
