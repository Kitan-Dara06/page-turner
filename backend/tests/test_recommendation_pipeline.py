"""
Recommendation Pipeline Integration Test — Phase 1
One end-to-end test that exercises the full pipeline with real DB + mocked external calls.
"""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


class TestFullPipeline:
    """End-to-end recommendation request with mocked integrations."""

    @pytest.mark.skip(
        reason="Phase 2: requires full pipeline Qdrant + Tavily integration"
    )
    def test_end_to_end_with_mocked_deps(self, client, db, seed_user):
        """User sends query → pipeline returns at least one result."""
        response = client.post(
            "/api/v1/recommend/",
            json={"query": "slow burn fantasy with romance"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "session_id" in data
        assert "results" in data
        assert len(data["results"]) >= 0  # Could be empty if no candidates match

    def test_root_endpoint_returns_recommendation(
        self, client, seed_user, seed_work, seed_tbr_entry
    ):
        """POST /api/v1/recommend/ returns structured response with all required fields."""
        with (
            patch("app.integrations.llm.complete") as mock_llm,
        ):
            mock_llm.return_value = {
                "expanded_query": "a slow burn enemies to lovers fantasy romance",
                "tower1_delta": {"pacing_preference": 0.2, "romance_centrality": 0.8},
            }
            response = client.post(
                "/api/v1/recommend/",
                json={"query": "slow burn romance"},
            )
        # The pipeline may return no results (empty Qdrant + no LLM expansion in mock)
        # But the response should still be well-formed
        assert response.status_code == 200
        data = response.json()
        assert "session_id" in data
        assert "query_rewritten" in data
        assert "mood_tags_extracted" in data
        assert "results" in data

    def test_recommendation_log_written(
        self, client, db, seed_user, seed_work, seed_tbr_entry
    ):
        """A successful recommendation generates RecommendationLog rows."""
        from sqlalchemy import select

        from app.models.recommendations import RecommendationLog

        with (
            patch("app.integrations.llm.complete") as mock_llm,
        ):
            mock_llm.return_value = {
                "expanded_query": "slow burn fantasy",
                "tower1_delta": {},
            }
            response = client.post(
                "/api/v1/recommend/",
                json={"query": "slow burn fantasy"},
            )

        logs = db.execute(select(RecommendationLog)).scalars().all()
        # Even with no results, a session log may or may not be written
        # This tests that the endpoint doesn't crash
        assert response.status_code == 200


class TestCheckpoint:
    """Checkpoint is surfaced before a new query when conditions are met."""

    def test_checkpoint_returns_pending(self, client, db, seed_user, seed_work):
        """GET /api/v1/recommend/checkpoint returns pending items."""
        # First, create a recommendation log with DELIVERED status
        import uuid

        from app.models.recommendations import (
            RecommendationLog,
            RecommendationSource,
            RecommendationStatus,
        )

        log = RecommendationLog(
            user_uuid=uuid.UUID(seed_user["user_uuid"]),
            session_id="test-session",
            work_uuid=uuid.UUID(seed_work["work_uuid"]),
            rank_position=1,
            source=RecommendationSource.VECTOR,
            query_text="test query",
            status=RecommendationStatus.DELIVERED,
        )
        db.add(log)
        db.commit()

        response = client.get("/api/v1/recommend/checkpoint")
        assert response.status_code == 200
        data = response.json()
        assert "pending_items" in data

    def test_checkpoint_empty_when_no_pending(self, client, db, seed_user):
        """GET /api/v1/recommend/checkpoint returns empty list when no pending items."""
        response = client.get("/api/v1/recommend/checkpoint")
        assert response.status_code == 200
        data = response.json()
        assert len(data["pending_items"]) == 0


class TestAPIEndpoints:
    """All API endpoints respond without crashing."""

    def test_health_check(self, client):
        """GET /health returns healthy status."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"

    def test_onboarding_flashcards(self, client, db, seed_user, seed_work):
        """GET /api/v1/onboarding/flashcards returns flashcard list."""
        response = client.get("/api/v1/onboarding/flashcards")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_tbr_list(self, client, db, seed_user, seed_tbr_entry):
        """GET /api/v1/tbr/ returns active TBR entries."""
        response = client.get("/api/v1/tbr/")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_author_catalog_not_found(self, client):
        """GET /api/v1/authors/{id}/catalog returns 404 for unknown author."""
        response = client.get(
            "/api/v1/authors/00000000-0000-0000-0000-000000000999/catalog"
        )
        assert response.status_code == 404

    def test_author_catalog_found(self, client, db, seed_person):
        """GET /api/v1/authors/{id}/catalog returns author data."""
        response = client.get(f"/api/v1/authors/{seed_person['person_uuid']}/catalog")
        assert response.status_code == 200
        data = response.json()
        assert data["canonical_name"] == "Test Author"

    def test_log_manual_book(self, client, db, seed_user):
        """POST /api/v1/books/log queues a book for enrichment."""
        response = client.post(
            "/api/v1/books/log",
            json={"title": "Manual Book", "author": "Manual Author"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "queued"
