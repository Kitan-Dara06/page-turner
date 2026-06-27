"""
Enrichment Pipeline Tests — Phase 1
Tests deduplication, enrichment status transitions, Tavily validation, and Celery retry.

Phase 2 items are marked with @pytest.mark.phase2 and will be skipped.
"""

import uuid

import pytest
from sqlalchemy import select

from app.models.books import Edition
from app.models.enrichment import EnrichmentCache
from app.models.tropes import OrphanQueue
from app.services.enrichment_service import enrich_book


class TestDeduplication:
    """_find_existing_work correctly deduplicates."""

    def test_deduplicate_by_isbn(self, db, seed_work):
        """A book matching by ISBN returns the existing Work."""
        # Add an ISBN to the existing edition
        edition = db.execute(
            select(Edition).where(
                Edition.work_uuid == uuid.UUID(seed_work["work_uuid"])
            )
        ).scalar_one()
        edition.isbn = "978-3-16-148410-0"
        db.commit()

        # Mock all integrations so it doesn't hit real APIs
        with (
            patch("app.integrations.openlibrary.lookup_work") as mock_ol,
            patch("app.integrations.google_books.search_by_title_author") as mock_gb,
            patch("app.integrations.google_books.fetch_by_isbn") as mock_isbn,
            patch("app.integrations.llm.complete") as mock_llm,
            patch(
                "app.integrations.reddit.fetch_subreddit_posts_by_keyword"
            ) as mock_reddit,
            patch("app.integrations.tavily.verify_hallucination") as mock_tavily,
            patch("app.integrations.tavily.search") as mock_tavily_search,
            patch("app.integrations.qdrant.upsert_vector") as mock_qdrant,
        ):
            mock_ol.return_value = None
            mock_gb.return_value = []
            mock_isbn.return_value = {"volumeInfo": {"title": "Test Book Title"}}
            mock_llm.return_value = {"mapped_tropes": [], "unmapped_tags": []}
            mock_reddit.return_value = []
            mock_tavily.return_value = True
            mock_tavily_search.return_value = {"results": [{"title": "Test Book"}]}
            mock_qdrant.return_value = None

            # Run enrichment with the same ISBN — should find existing
            work = enrich_book(
                db=db,
                title="Test Book Title",
                author_name="Test Author",
                isbn="978-3-16-148410-0",
            )

        assert work.work_uuid == uuid.UUID(seed_work["work_uuid"]), (
            "Should return existing work"
        )

    def test_deduplicate_by_title_fallback(self, db, seed_work, seed_person):
        """When no ISBN, fall back to title+author match."""
        with (
            patch("app.integrations.openlibrary.lookup_work") as mock_ol,
            patch("app.integrations.google_books.search_by_title_author") as mock_gb,
            patch("app.integrations.google_books.fetch_by_isbn") as mock_isbn,
            patch("app.integrations.llm.complete") as mock_llm,
            patch(
                "app.integrations.reddit.fetch_subreddit_posts_by_keyword"
            ) as mock_reddit,
            patch("app.integrations.tavily.verify_hallucination") as mock_tavily,
            patch("app.integrations.tavily.search") as mock_tavily_search,
            patch("app.integrations.qdrant.upsert_vector") as mock_qdrant,
        ):
            mock_ol.return_value = {"subject": ["fantasy", "magic"]}
            mock_gb.return_value = []
            mock_isbn.return_value = None
            mock_llm.return_value = {"mapped_tropes": [], "unmapped_tags": []}
            mock_reddit.return_value = []
            mock_tavily.return_value = True
            mock_tavily_search.return_value = {"results": [{"title": "Test Book"}]}
            mock_qdrant.return_value = None

            work = enrich_book(
                db=db,
                title="Test Book Title",
                author_name="Test Author",
            )

        assert work.work_uuid == uuid.UUID(seed_work["work_uuid"]), (
            "Should return existing work by title match"
        )


class TestEnrichmentStatus:
    """Enrichment pipeline produces complete status with Qdrant vector."""

    def test_enrichment_completes(self, db, seed_person):
        """A book entering 'pending' exits with enrichment data."""
        with (
            patch("app.integrations.openlibrary.lookup_work") as mock_ol,
            patch("app.integrations.google_books.search_by_title_author") as mock_gb,
            patch("app.integrations.google_books.fetch_by_isbn") as mock_isbn,
            patch("app.integrations.llm.complete") as mock_llm,
            patch(
                "app.integrations.reddit.fetch_subreddit_posts_by_keyword"
            ) as mock_reddit,
            patch("app.integrations.tavily.verify_hallucination") as mock_tavily,
            patch("app.integrations.tavily.search") as mock_tavily_search,
            patch("app.integrations.qdrant.upsert_vector") as mock_qdrant,
        ):
            mock_ol.return_value = {"subject": ["fantasy"]}
            mock_gb.return_value = [
                {"volumeInfo": {"title": "New Book", "pageCount": 200}}
            ]
            mock_isbn.return_value = None
            mock_llm.return_value = {"mapped_tropes": [], "unmapped_tags": []}
            mock_reddit.return_value = []
            mock_tavily.return_value = True
            mock_tavily_search.return_value = {"results": [{"title": "New Book"}]}
            mock_qdrant.return_value = None

            work = enrich_book(
                db=db,
                title="New Book",
                author_name="Test Author",
            )

        # Check enrichment cache was created
        cache = db.execute(
            select(EnrichmentCache).where(EnrichmentCache.work_uuid == work.work_uuid)
        ).scalar_one()
        assert cache is not None
        assert cache.hallucination_verified is True
        assert cache.enriched_at is not None


class TestTavilyValidation:
    """Books failing Tavily hallucination check get flagged."""

    def test_tavily_failure_flagged(self, db, seed_person):
        """When Tavily says the book doesn't exist, it's flagged."""
        with (
            patch("app.integrations.openlibrary.lookup_work") as mock_ol,
            patch("app.integrations.google_books.search_by_title_author") as mock_gb,
            patch("app.integrations.google_books.fetch_by_isbn") as mock_isbn,
            patch("app.integrations.llm.complete") as mock_llm,
            patch(
                "app.integrations.reddit.fetch_subreddit_posts_by_keyword"
            ) as mock_reddit,
            patch("app.integrations.tavily.verify_hallucination") as mock_tavily,
            patch("app.integrations.qdrant.upsert_vector") as mock_qdrant,
        ):
            mock_ol.return_value = None
            mock_gb.return_value = []
            mock_isbn.return_value = None
            mock_llm.return_value = {"mapped_tropes": [], "unmapped_tags": []}
            mock_reddit.return_value = []
            mock_tavily.return_value = False  # Hallucination!
            mock_qdrant.return_value = None

            work = enrich_book(
                db=db,
                title="Fake Book That Doesn't Exist",
                author_name="Fake Author",
            )

        cache = db.execute(
            select(EnrichmentCache).where(EnrichmentCache.work_uuid == work.work_uuid)
        ).scalar_one()
        assert cache.hallucination_verified is False


class TestLLMTagTranslation:
    """LLM tag translation produces parseable DAG-mappable output."""

    def test_orphan_queue_writes_on_low_confidence(self, db, seed_person):
        """When LLM confidence is low, unmapped tags go to OrphanQueue."""
        with (
            patch("app.integrations.openlibrary.lookup_work") as mock_ol,
            patch("app.integrations.google_books.search_by_title_author") as mock_gb,
            patch("app.integrations.google_books.fetch_by_isbn") as mock_isbn,
            patch("app.integrations.llm.complete") as mock_llm,
            patch(
                "app.integrations.reddit.fetch_subreddit_posts_by_keyword"
            ) as mock_reddit,
            patch("app.integrations.tavily.verify_hallucination") as mock_tavily,
            patch("app.integrations.qdrant.upsert_vector") as mock_qdrant,
        ):
            mock_ol.return_value = {"subject": ["weird new concept", "another thing"]}
            mock_gb.return_value = []
            mock_isbn.return_value = None
            mock_llm.return_value = {
                "mapped_tropes": [],
                "unmapped_tags": ["weird new concept", "another thing"],
            }
            mock_reddit.return_value = []
            mock_tavily.return_value = True
            mock_qdrant.return_value = None

            work = enrich_book(
                db=db,
                title="Book With New Tropes",
                author_name="Test Author",
            )

        orphans = db.execute(select(OrphanQueue)).scalars().all()
        assert len(orphans) > 0
        tags = [o.tag_text for o in orphans]
        assert "weird new concept" in tags


class TestCeleryRetry:
    """Celery retry fires on transient failure."""

    @pytest.mark.skip(
        reason="Phase 2: requires running Celery task worker or detailed mocking"
    )
    def test_retry_on_transient_failure(self):
        """Mock integration throws, verify retry count increments."""
        pass
