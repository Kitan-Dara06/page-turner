"""
Query Engine Tests — Phase 1
Tests the LLM-based query expansion and Tower 1 delta extraction.
External LLM is mocked — we test that the engine handles the LLM output correctly.
"""

from unittest.mock import patch

import pytest

from app.services.query_engine import process_reader_query


class TestQueryEngine:
    """Query rewriting returns both expected outputs."""

    def test_returns_tuple(self, db, seed_user):
        """Returns (expanded_query, tower1_delta) tuple."""
        expanded, delta = process_reader_query(
            db=db,
            user_uuid=seed_user["user_uuid"],
            raw_query="something slow and angsty",
        )
        assert isinstance(expanded, str)
        assert isinstance(delta, dict)

    def test_expanded_query_is_string(self, db, seed_user):
        """Expanded query is a non-empty string."""
        expanded, delta = process_reader_query(
            db=db,
            user_uuid=seed_user["user_uuid"],
            raw_query="slow burn fantasy with romance",
        )
        assert len(expanded) > 0
        assert isinstance(expanded, str)

    def test_delta_contains_valid_tower1_keys(self, db, seed_user):
        """Tower 1 delta only contains valid profile fields."""
        _, delta = process_reader_query(
            db=db,
            user_uuid=seed_user["user_uuid"],
            raw_query="something dark and fast paced",
        )
        valid_keys = {
            "darkness_tolerance",
            "angst_level",
            "violence_tolerance",
            "thematic_density",
            "pacing_preference",
            "prose_density",
            "narrative_linearity",
            "plot_vs_character",
            "setting_scope",
            "speculative_deviation",
            "emotional_intensity",
            "standalone_preference",
            "explicit_content_level",
            "romance_centrality",
            "hea_requirement",
        }
        for key in delta.keys():
            assert key in valid_keys, f"Unexpected key: {key}"

    def test_values_are_between_zero_and_one(self, db, seed_user):
        """All delta values are in [0.0, 1.0]."""
        _, delta = process_reader_query(
            db=db,
            user_uuid=seed_user["user_uuid"],
            raw_query="very dark and extremely slow burn",
        )
        for key, val in delta.items():
            assert 0.0 <= val <= 1.0, f"{key} = {val} out of range"

    def test_malformed_llm_response_does_not_crash(self, db, seed_user):
        """LLM returning garbage doesn't crash — falls back to raw query."""
        with patch("app.integrations.llm.complete") as mock:
            mock.side_effect = Exception("LLM is down")
            expanded, delta = process_reader_query(
                db=db,
                user_uuid=seed_user["user_uuid"],
                raw_query="give me something good",
            )
            assert expanded == "give me something good"
            assert delta == {}

    def test_llm_returning_non_json_falls_back(self, db, seed_user):
        """LLM returning plain text instead of JSON doesn't crash."""
        with patch("app.integrations.llm.complete") as mock:
            mock.return_value = "this is not json"
            expanded, delta = process_reader_query(
                db=db,
                user_uuid=seed_user["user_uuid"],
                raw_query="test query",
            )
            # Should fall back gracefully
            assert isinstance(expanded, str)
            assert isinstance(delta, dict)


class TestEmptyAndEdgeQueries:
    """Delta is structured correctly even when the query has no strong signal."""

    def test_empty_query_returns_empty_delta(self, db, seed_user):
        """Empty query should not crash — falls back gracefully."""
        expanded, delta = process_reader_query(
            db=db,
            user_uuid=seed_user["user_uuid"],
            raw_query="",
        )
        assert expanded == ""
        assert isinstance(delta, dict)

    def test_neutral_query_returns_empty_delta(self, db, seed_user):
        """ "just give me something good" returns empty delta, not crash."""
        with patch("app.integrations.llm.complete") as mock:
            mock.return_value = {
                "expanded_query": "highly rated popular fiction",
                "tower1_delta": {},
            }
            expanded, delta = process_reader_query(
                db=db,
                user_uuid=seed_user["user_uuid"],
                raw_query="just give me something good",
            )
            assert delta == {}


class TestMoodTagExtraction:
    """Mood tags are extracted as a distinct artifact from the expanded query."""

    def test_delta_is_not_identical_to_query(self, db, seed_user):
        """The delta dict should not be the same as the raw query string."""
        with patch("app.integrations.llm.complete") as mock:
            mock.return_value = {
                "expanded_query": "dark fantasy with slow burn romance",
                "tower1_delta": {"darkness_tolerance": 0.8, "pacing_preference": 0.2},
            }
            expanded, delta = process_reader_query(
                db=db,
                user_uuid=seed_user["user_uuid"],
                raw_query="dark and slow",
            )
            # The delta is a dict, the expanded query is a string — they can't be identical
            assert delta != expanded
            # But the delta keys should relate to the sentiment of the query
            assert "darkness_tolerance" in delta or "pacing_preference" in delta

    def test_invalid_delta_keys_stripped(self, db, seed_user):
        """LLM invented keys should be stripped out."""
        with patch("app.integrations.llm.complete") as mock:
            mock.return_value = {
                "expanded_query": "some query",
                "tower1_delta": {
                    "darkness_tolerance": 0.8,
                    "made_up_key": 0.5,  # Not a valid Tower 1 field
                    "invalid_field": 999,  # Also invalid
                },
            }
            _, delta = process_reader_query(
                db=db,
                user_uuid=seed_user["user_uuid"],
                raw_query="dark book",
            )
            assert "darkness_tolerance" in delta
            assert "made_up_key" not in delta
            assert "invalid_field" not in delta
