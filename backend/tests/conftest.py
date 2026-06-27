"""
PAGETURNER Test Fixtures
Shared fixtures for all test modules.
Mocks all external integrations at the boundary.
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Generator, List, Optional
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app

# ------------------------------------------------------------------
# Test Database
# ------------------------------------------------------------------

# Use the configured DATABASE_URI — the .env should point to a test DB
TEST_DATABASE_URL = settings.DATABASE_URI

engine = create_engine(TEST_DATABASE_URL)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="session")
def test_engine():
    """Creates all tables once per test session."""
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db(test_engine) -> Generator[Session, None, None]:
    """Provides a clean database session per test function."""
    connection = test_engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)

    # Nested transactions for perfect isolation
    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def client(db) -> Generator[TestClient, None, None]:
    """FastAPI TestClient that overrides the DB dependency."""

    def _get_test_db():
        yield db

    app.dependency_overrides[get_db] = _get_test_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ------------------------------------------------------------------
# Mock Helpers
# ------------------------------------------------------------------

MOCK_USER_UUID = "00000000-0000-0000-0000-000000000001"


@pytest.fixture(autouse=True)
def mock_all_integrations():
    """
    Mocks all external API integrations so tests never hit real APIs.
    Uses create=True so tests that don't import integration modules still work.
    Each test can override individual mocks via fixture overrides.
    """
    with (
        patch("app.integrations.llm.complete", create=True) as mock_llm,
        patch("app.integrations.qdrant.search_knn", create=True) as mock_qdrant_search,
        patch(
            "app.integrations.qdrant.upsert_vector", create=True
        ) as mock_qdrant_upsert,
        patch("app.integrations.qdrant.create_collection_if_not_exists", create=True),
        patch(
            "app.integrations.tavily.verify_hallucination", create=True
        ) as mock_tavily,
        patch("app.integrations.tavily.search", create=True) as mock_tavily_search,
        patch(
            "app.integrations.google_books.search_by_title_author", create=True
        ) as mock_gb,
        patch(
            "app.integrations.google_books.fetch_by_isbn", create=True
        ) as mock_gb_isbn,
        patch("app.integrations.openlibrary.lookup_work", create=True) as mock_ol,
    ):
        # Default mock responses
        mock_llm.return_value = {
            "expanded_query": "a slow burn enemies to lovers fantasy romance",
            "tower1_delta": {"pacing_preference": 0.2, "romance_centrality": 0.8},
        }
        mock_qdrant_search.return_value = []
        mock_qdrant_upsert.return_value = None
        mock_tavily.return_value = True
        mock_tavily_search.return_value = {"results": [{"title": "Test Book"}]}
        mock_gb.return_value = []
        mock_gb_isbn.return_value = None
        mock_ol.return_value = None

        yield


# ------------------------------------------------------------------
# Seed Fixtures — produce real DB rows
# ------------------------------------------------------------------


@pytest.fixture
def seed_person(db) -> dict:
    """Creates a Person (author) and returns its data dict."""
    from app.models.authors import Person

    person = Person(canonical_name="Test Author")
    db.add(person)
    db.commit()
    return {
        "person_uuid": str(person.person_uuid),
        "canonical_name": person.canonical_name,
    }


@pytest.fixture
def seed_pen_name(db, seed_person) -> dict:
    """Creates a PenName linked to seed_person."""
    from app.models.authors import PenName

    pn = PenName(
        person_uuid=uuid.UUID(seed_person["person_uuid"]),
        display_name="Test Pen Name",
        primary_genre="fantasy",
    )
    db.add(pn)
    db.commit()
    return {"pen_name_uuid": str(pn.pen_name_uuid), "display_name": pn.display_name}


@pytest.fixture
def seed_work(db, seed_person) -> dict:
    """Creates a Work + Edition + EnrichmentCache."""
    from app.models.books import Edition, Work
    from app.models.enrichment import EnrichmentCache

    work = Work(
        person_uuid=uuid.UUID(seed_person["person_uuid"]),
        title="Test Book Title",
    )
    db.add(work)
    db.flush()

    edition = Edition(
        work_uuid=work.work_uuid,
        page_count=300,
        cover_url="https://example.com/cover.jpg",
    )
    db.add(edition)

    cache = EnrichmentCache(
        work_uuid=work.work_uuid,
        community_buzz_score=0.75,
        hallucination_verified=True,
    )
    db.add(cache)
    db.commit()

    return {
        "work_uuid": str(work.work_uuid),
        "title": work.title,
        "person_uuid": seed_person["person_uuid"],
    }


@pytest.fixture
def seed_user(db) -> dict:
    """Creates a User with a populated Tower 1 profile."""
    from app.models.users import User, UserProfile

    user = User(user_uuid=uuid.UUID(MOCK_USER_UUID))
    db.add(user)
    db.flush()

    profile = UserProfile(
        user_uuid=user.user_uuid,
        darkness_tolerance=0.3,
        angst_level=0.6,
        thematic_density=0.8,
        pacing_preference=0.4,
        standalone_preference=0.7,
        exploration_tolerance=0.5,
    )
    db.add(profile)
    db.commit()

    return {"user_uuid": str(user.user_uuid)}


@pytest.fixture
def seed_tbr_entry(db, seed_user, seed_work) -> dict:
    """Creates an active TBR entry."""
    from app.models.tbr import TBREntry, TBRStatus

    entry = TBREntry(
        user_uuid=uuid.UUID(seed_user["user_uuid"]),
        work_uuid=uuid.UUID(seed_work["work_uuid"]),
        priority_score=0.9,
        skip_count=0,
        status=TBRStatus.ACTIVE,
        add_query_text="slow burn fantasy",
        add_mood_tags={"pacing_preference": 0.2, "romance_centrality": 0.8},
    )
    db.add(entry)
    db.commit()

    return {
        "tbr_uuid": str(entry.tbr_uuid),
        "work_uuid": seed_work["work_uuid"],
        "user_uuid": seed_user["user_uuid"],
    }


@pytest.fixture
def seed_interaction_event(db, seed_user, seed_work) -> dict:
    """Creates a LOGGED_READ interaction event."""
    from app.models.events import EventType, InteractionEvent

    event = InteractionEvent(
        user_uuid=uuid.UUID(seed_user["user_uuid"]),
        work_uuid=uuid.UUID(seed_work["work_uuid"]),
        event_type=EventType.LOGGED_READ,
        session_id="test-session",
        stated_rating=4,
    )
    db.add(event)
    db.commit()

    return {"event_uuid": str(event.event_uuid)}


@pytest.fixture
def seed_trope(db) -> dict:
    """Creates a single trope node."""
    from app.models.tropes import Trope

    trope = Trope(canonical_name="Slow Burn", depth_level=3, is_root_hub=False)
    db.add(trope)
    db.commit()

    return {"trope_uuid": str(trope.trope_uuid), "canonical_name": trope.canonical_name}


@pytest.fixture
def seed_series(db, seed_person) -> dict:
    """Creates a Series."""
    from app.models.series import Series

    series = Series(
        title="Test Series",
        person_uuid=uuid.UUID(seed_person["person_uuid"]),
        total_core_works=3,
    )
    db.add(series)
    db.commit()

    return {"series_uuid": str(series.series_uuid), "title": series.title}
