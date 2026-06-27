"""
Author Service Tests — Phase 1
Tests author catalog view and author tracking.

The async AuthorService class (services/author_service.py) is Phase 2.
Phase 1 tests cover the sync api/authors.py endpoint behavior.
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models.authors import PenName, Person
from app.models.series import Series, SeriesWork
from app.models.tracked_authors import TrackedAuthor


class TestAuthorCatalogAPI:
    """Tests for GET /api/v1/authors/{person_uuid}/catalog."""

    def test_catalog_returns_author_data(self, client, db, seed_person):
        """Returns author's canonical name and pen names."""
        response = client.get(f"/api/v1/authors/{seed_person['person_uuid']}/catalog")
        assert response.status_code == 200
        data = response.json()
        assert data["canonical_name"] == "Test Author"
        assert "pen_names" in data

    def test_catalog_includes_pen_names(self, client, db, seed_person, seed_pen_name):
        """Pen names appear in the catalog response."""
        response = client.get(f"/api/v1/authors/{seed_person['person_uuid']}/catalog")
        assert response.status_code == 200
        data = response.json()
        assert "Test Pen Name" in data["pen_names"]

    def test_catalog_returns_series(
        self, client, db, seed_person, seed_work, seed_series
    ):
        """Series linked to the author appear in the catalog."""
        # Link the work to the series
        sw = SeriesWork(
            series_uuid=uuid.UUID(seed_series["series_uuid"]),
            work_uuid=uuid.UUID(seed_work["work_uuid"]),
            order_float=1.0,
        )
        db.add(sw)
        db.commit()

        response = client.get(f"/api/v1/authors/{seed_person['person_uuid']}/catalog")
        assert response.status_code == 200
        data = response.json()
        assert len(data["series"]) > 0
        assert data["series"][0]["title"] == "Test Series"

    def test_catalog_404_for_unknown_author(self, client):
        """Non-existent person_uuid returns 404."""
        response = client.get(
            "/api/v1/authors/00000000-0000-0000-0000-000000000999/catalog"
        )
        assert response.status_code == 404


class TestTrackedAuthor:
    """Tests for the TrackedAuthor model and implicit tracking."""

    def test_track_author_creates_record(self, db, seed_user, seed_person):
        """Creating a TrackedAuthor record works."""
        ta = TrackedAuthor(
            user_uuid=uuid.UUID(seed_user["user_uuid"]),
            person_uuid=uuid.UUID(seed_person["person_uuid"]),
        )
        db.add(ta)
        db.commit()

        assert ta.tracked_since is not None

    def test_track_author_idempotent(self, db, seed_user, seed_person):
        """Duplicate tracking should not crash (PK constraint)."""
        ta1 = TrackedAuthor(
            user_uuid=uuid.UUID(seed_user["user_uuid"]),
            person_uuid=uuid.UUID(seed_person["person_uuid"]),
        )
        db.add(ta1)
        db.commit()

        ta2 = TrackedAuthor(
            user_uuid=uuid.UUID(seed_user["user_uuid"]),
            person_uuid=uuid.UUID(seed_person["person_uuid"]),
        )
        db.add(ta2)
        with pytest.raises(IntegrityError):
            db.commit()

    @pytest.mark.skip(reason="Phase 2: async AuthorService not wired to API yet")
    def test_tracked_authors_ordered_by_checked_at(self, db, seed_user, seed_person):
        """get_authors_due_for_check returns authors sorted properly."""
        pass

    @pytest.mark.skip(reason="Phase 2: async AuthorService not wired to API yet")
    def test_batch_size_cap(self, db, seed_user, seed_person):
        """At most 50 authors returned per call."""
        pass
