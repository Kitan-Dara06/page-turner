"""
Exploration Service Tests — ⚠️ PHASE 2 ⚠️
The exploration service is async and depends on model fields that don't exist yet
(embedding_centroid, profile_confidence, InteractionEvent.created_at, InteractionEvent.metadata).

All tests are marked @pytest.mark.phase2 and will be skipped in Phase 1.
"""

import pytest

pytestmark = pytest.mark.skip(
    reason="Phase 2: requires async refactor + model field additions"
)


class TestExplorationGate:
    """should_explore returns False when conditions aren't met."""

    @pytest.mark.phase2
    def test_should_explore_false_under_20_interactions(self):
        """Returns False for users under 20 interactions (calibration mode)."""
        pass

    @pytest.mark.phase2
    def test_should_explore_false_in_cooldown(self):
        """Returns False within the 30-day cooldown window."""
        pass

    @pytest.mark.phase2
    def test_rate_halves_above_confidence_threshold(self):
        """Rate halves correctly when profile_confidence exceeds 0.75."""
        pass


class TestExplorationInjection:
    """Exploration candidate injection is correct."""

    @pytest.mark.phase2
    def test_inject_not_position_0_or_1(self):
        """inject_exploration_candidate never places at position 0 or 1."""
        pass

    @pytest.mark.phase2
    def test_inject_is_pure_function(self):
        """Same input always produces same output."""
        pass


class TestAntiProfileBuilding:
    """Anti-profile signal recording is correct."""

    @pytest.mark.phase2
    def test_record_negative_outcome_sets_flag(self):
        """record_exploration_outcome with 'negative' sets anti_profile_signal."""
        pass

    @pytest.mark.phase2
    def test_get_anti_profile_only_negative(self):
        """get_anti_profile_signals only returns negative outcomes."""
        pass
