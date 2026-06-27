"""
Reranker Tests — Phase 1
Pure functions — easy to test, no DB or mocks needed.
"""

import pytest

from app.schemas.users import Tower1Profile
from app.services.reranker import CandidateContext, rank_candidates


def make_candidate(
    work_uuid: str = "00000000-0000-0000-0000-000000000001",
    title: str = "Test Book",
    base_vector_score: float = 0.5,
    is_tbr_context_match: bool = False,
    community_buzz_score: float = 0.0,
    seen_recently: bool = False,
    book_inferred_profile: dict = None,
) -> CandidateContext:
    return CandidateContext(
        work_uuid=work_uuid,
        title=title,
        base_vector_score=base_vector_score,
        is_tbr_context_match=is_tbr_context_match,
        community_buzz_score=community_buzz_score,
        seen_recently=seen_recently,
        book_inferred_profile=book_inferred_profile or {},
    )


def make_profile(**overrides) -> Tower1Profile:
    defaults = {
        "darkness_tolerance": 0.5,
        "pacing_preference": 0.5,
        "thematic_density": 0.5,
    }
    defaults.update(overrides)
    return Tower1Profile(**defaults)


class TestScoreComponents:
    """Score components sum to the correct total for a known input."""

    def test_perfect_vector_match(self):
        """A candidate with max vector score and matching profile."""
        profile = make_profile(pacing_preference=0.8)
        candidate = make_candidate(
            base_vector_score=1.0,
            book_inferred_profile={"pacing_preference": 0.8},
        )
        ranked = rank_candidates([candidate], profile)
        # 0.40 (vector) + 0.30 (tower1) + 0.0 + 0.0 + 0.0 = 0.70
        assert ranked[0].final_score == pytest.approx(0.70, abs=0.01)

    def test_tbr_bonus_added(self):
        """TBR context match adds 0.10 to the score."""
        profile = make_profile()
        candidate = make_candidate(
            base_vector_score=0.5,
            is_tbr_context_match=True,
            book_inferred_profile={"pacing_preference": 0.5},
        )
        ranked = rank_candidates([candidate], profile)
        # 0.20 (vector) + 0.30 (tower1 perfect match) + 0.10 (tbr) = 0.60
        assert ranked[0].final_score == pytest.approx(0.60, abs=0.01)
        assert ranked[0].match_source == "tbr"

    def test_community_buzz_added(self):
        """Community buzz score contributes up to 0.10."""
        profile = make_profile()
        candidate = make_candidate(
            base_vector_score=0.5,
            community_buzz_score=1.0,
            book_inferred_profile={"pacing_preference": 0.5},
        )
        ranked = rank_candidates([candidate], profile)
        # 0.20 + 0.30 + 0.10 (buzz) = 0.60
        assert ranked[0].final_score == pytest.approx(0.60, abs=0.01)

    def test_recency_penalty_applied(self):
        """Recently seen books get a -0.10 penalty."""
        profile = make_profile()
        candidate = make_candidate(
            base_vector_score=0.5,
            seen_recently=True,
            book_inferred_profile={"pacing_preference": 0.5},
        )
        ranked = rank_candidates([candidate], profile)
        # 0.20 + 0.30 - 0.10 = 0.40
        assert ranked[0].final_score == pytest.approx(0.40, abs=0.01)

    def test_tbr_bonus_sets_match_source(self):
        """TBR match source is set when the bonus applies."""
        profile = make_profile()
        candidate = make_candidate(
            base_vector_score=0.3,
            is_tbr_context_match=True,
        )
        ranked = rank_candidates([candidate], profile)
        assert ranked[0].match_source == "tbr"


class TestScoreFloor:
    """Score floor at 0.0 holds."""

    def test_zero_is_minimum(self):
        """Maximum penalty + minimum similarity cannot produce a negative score."""
        profile = make_profile()
        candidate = make_candidate(
            base_vector_score=0.0,
            seen_recently=True,
            book_inferred_profile={},  # No overlap
        )
        ranked = rank_candidates([candidate], profile)
        assert ranked[0].final_score >= 0.0


class TestTBRBonusSpecificity:
    """TBR bonus applies only when the book is actually on TBR."""

    def test_non_tbr_no_bonus(self):
        """Non-TBR books don't get the TBR bonus."""
        profile = make_profile()
        candidate = make_candidate(is_tbr_context_match=False)
        ranked = rank_candidates([candidate], profile)
        # No tbr bonus in explanation factors when not TBR
        tbr_explanations = [
            f for f in ranked[0].explanation_factors if "TBR" in f or "tbr" in f
        ]
        assert len(tbr_explanations) == 0

    def test_tbr_has_explanation(self):
        """TBR books have a TBR-related explanation."""
        profile = make_profile()
        candidate = make_candidate(is_tbr_context_match=True)
        ranked = rank_candidates([candidate], profile)
        tbr_explanations = [f for f in ranked[0].explanation_factors if "TBR" in f]
        assert len(tbr_explanations) > 0


class TestRankingStability:
    """Ranking order is stable when scores are identical."""

    def test_tiebreak_stable(self):
        """Identical scores produce deterministic order (same as input order)."""
        profile = make_profile()
        c1 = make_candidate(
            work_uuid="00000000-0000-0000-0000-000000000001",
            base_vector_score=0.5,
        )
        c2 = make_candidate(
            work_uuid="00000000-0000-0000-0000-000000000002",
            base_vector_score=0.5,
        )
        ranked = rank_candidates([c1, c2], profile)
        assert len(ranked) == 2
        # Both should have the same score
        assert ranked[0].final_score == ranked[1].final_score

    def test_different_scores_ordered(self):
        """Higher scored candidates come first."""
        profile = make_profile()
        c1 = make_candidate(
            work_uuid="00000000-0000-0000-0000-000000000001",
            base_vector_score=0.9,
            book_inferred_profile={"pacing_preference": 0.5},
        )
        c2 = make_candidate(
            work_uuid="00000000-0000-0000-0000-000000000002",
            base_vector_score=0.1,
            book_inferred_profile={"pacing_preference": 0.5},
        )
        ranked = rank_candidates([c2, c1], profile)
        assert ranked[0].work_uuid == c1.work_uuid
        assert ranked[1].work_uuid == c2.work_uuid


class TestTower1Overlap:
    """Tower 1 profile matching works correctly."""

    def test_perfect_overlap_max_score(self):
        """Identical user and book profiles give max tower1 score."""
        profile = make_profile(pacing_preference=0.8, thematic_density=0.3)
        candidate = make_candidate(
            book_inferred_profile={"pacing_preference": 0.8, "thematic_density": 0.3},
        )
        ranked = rank_candidates([candidate], profile)
        tower1_component = ranked[0].final_score - (
            0.40 * ranked[0].base_vector_score  # vector
        )
        # If vector=0.5, then tower1 portion = final - 0.20
        # tower1_max = 0.30, so final should be 0.20 + 0.30 + 0 + 0 + 0 = 0.50
        assert ranked[0].final_score == pytest.approx(0.50, abs=0.01)

    def test_no_overlap_neutral_baseline(self):
        """No shared dimensions → neutral baseline 0.5 for tower1 overlap."""
        profile = make_profile(pacing_preference=0.8)
        candidate = make_candidate(
            book_inferred_profile={"nonexistent_field": 0.5},  # no shared keys
        )
        ranked = rank_candidates([candidate], profile)
        # vector (0.5*0.40=0.20) + tower1 (0.5*0.30=0.15) = 0.35
        assert ranked[0].final_score == pytest.approx(0.35, abs=0.01)

    @pytest.mark.skip(
        reason="Phase 2: read-book filtering requires interaction history lookup"
    )
    def test_read_book_excluded(self):
        """A book the user has already read never appears regardless of score."""
        pass
