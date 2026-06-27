"""
Author Service
Handles author catalog management and new release detection.
Implements FR-AT-01, FR-AT-02, FR-AT-03 from the SRS.
"""

from datetime import date, timedelta
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.google_books import GoogleBooksClient
from app.integrations.openlibrary import OpenLibraryClient
from app.models.authors import PenName, Person
from app.models.books import Edition, Work
from app.models.events import InteractionEvent
from app.models.recommendations import RecommendationLog
from app.models.tracked_authors import TrackedAuthor


class AuthorService:
    """
    Manages tracked author state and release detection.

    Release detection runs as a Celery beat task via workers/author_alert_tasks.py.
    This service contains the logic; the task is a thin wrapper.
    """

    # SRS FR-AT-02: process at most 50 authors per daily run to stay within
    # Google Books and OpenLibrary rate limits.
    DAILY_AUTHOR_BATCH_SIZE = 50

    # A new Work is considered "recent" if its publication date falls within
    # this window. Guards against re-alerting on books published before
    # the user started tracking the author.
    RELEASE_LOOKBACK_DAYS = 90

    def __init__(
        self,
        session: AsyncSession,
        google_books: GoogleBooksClient,
        openlibrary: OpenLibraryClient,
    ):
        self.session = session
        self.google_books = google_books
        self.openlibrary = openlibrary

    # ------------------------------------------------------------------
    # Tracking Management
    # ------------------------------------------------------------------

    async def track_author(self, user_uuid: UUID, person_uuid: UUID) -> TrackedAuthor:
        """
        Adds an author to a user's tracked list.
        Called when a user explicitly follows an author (FR-AT-01).
        Also called implicitly when a user logs a book (high-signal follow).
        """
        # Idempotent — if already tracking, return existing record
        result = await self.session.execute(
            select(TrackedAuthor).where(
                TrackedAuthor.user_uuid == user_uuid,
                TrackedAuthor.person_uuid == person_uuid,
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            return existing

        entry = TrackedAuthor(
            user_uuid=user_uuid,
            person_uuid=person_uuid,
        )
        self.session.add(entry)
        await self.session.flush()
        return entry

    async def untrack_author(self, user_uuid: UUID, person_uuid: UUID) -> bool:
        """Returns True if a record was deleted, False if it didn't exist."""
        result = await self.session.execute(
            select(TrackedAuthor).where(
                TrackedAuthor.user_uuid == user_uuid,
                TrackedAuthor.person_uuid == person_uuid,
            )
        )
        entry = result.scalar_one_or_none()
        if not entry:
            return False
        await self.session.delete(entry)
        await self.session.flush()
        return True

    async def get_tracked_authors(self, user_uuid: UUID) -> list[TrackedAuthor]:
        result = await self.session.execute(
            select(TrackedAuthor)
            .where(TrackedAuthor.user_uuid == user_uuid)
            .order_by(TrackedAuthor.created_at.desc())
        )
        return list(result.scalars().all())

    # ------------------------------------------------------------------
    # Author Catalog
    # ------------------------------------------------------------------

    async def get_author_catalog(self, person_uuid: UUID) -> dict:
        """
        Returns a Person's full catalog — all PenNames and their Works.
        Used by api/authors.py for the catalog view.
        """
        person_result = await self.session.execute(
            select(Person).where(Person.person_uuid == person_uuid)
        )
        person = person_result.scalar_one_or_none()
        if not person:
            return {}

        pen_names_result = await self.session.execute(
            select(PenName).where(PenName.person_uuid == person_uuid)
        )
        pen_names = list(pen_names_result.scalars().all())

        catalog = {"person": person, "pen_names": []}
        for pen_name in pen_names:
            works_result = await self.session.execute(
                select(Work)
                .where(Work.pen_name_uuid == pen_name.pen_name_uuid)
                .order_by(Work.publication_date.desc())
            )
            works = list(works_result.scalars().all())
            catalog["pen_names"].append({"pen_name": pen_name, "works": works})

        return catalog

    # ------------------------------------------------------------------
    # Release Detection (called by beat task)
    # ------------------------------------------------------------------

    async def get_authors_due_for_check(self) -> list[TrackedAuthor]:
        """
        Returns up to DAILY_AUTHOR_BATCH_SIZE tracked authors whose
        last_checked_at is oldest (or null). Beat task calls this to
        determine which authors to check in a given daily run.
        """
        result = await self.session.execute(
            select(TrackedAuthor)
            .order_by(TrackedAuthor.last_checked_at.asc().nullsfirst())
            .limit(self.DAILY_AUTHOR_BATCH_SIZE)
        )
        return list(result.scalars().all())

    async def check_author_for_new_releases(self, tracked: TrackedAuthor) -> list[Work]:
        """
        Queries Google Books and OpenLibrary for new Works by this author.
        Compares against existing Works in DB to detect genuinely new entries.
        Returns a list of newly detected Work rows (already persisted).

        SRS FR-AT-02: "new Work is detected" means publication_date is within
        RELEASE_LOOKBACK_DAYS and the work_uuid does not already exist in the DB.
        """
        person_result = await self.session.execute(
            select(Person).where(Person.person_uuid == tracked.person_uuid)
        )
        person = person_result.scalar_one_or_none()
        if not person:
            return []

        pen_names_result = await self.session.execute(
            select(PenName).where(PenName.person_uuid == tracked.person_uuid)
        )
        pen_names = list(pen_names_result.scalars().all())
        pen_name_strings = [pn.name for pn in pen_names]

        cutoff = date.today() - timedelta(days=self.RELEASE_LOOKBACK_DAYS)
        new_works: list[Work] = []

        for pen_name_str in pen_name_strings:
            # Pull candidates from both sources; deduplicate by ISBN/title+author
            candidates = await self._fetch_candidates(pen_name_str, cutoff)

            for candidate in candidates:
                existing = await self._find_existing_work(candidate)
                if existing:
                    continue

                work = await self._persist_candidate(candidate, pen_names, pen_name_str)
                if work:
                    new_works.append(work)

        # Update last_checked_at regardless of whether we found anything
        await self.session.execute(
            update(TrackedAuthor)
            .where(TrackedAuthor.tracked_uuid == tracked.tracked_uuid)
            .values(last_checked_at=date.today())
        )
        await self.session.flush()

        return new_works

    async def _fetch_candidates(self, pen_name: str, cutoff: date) -> list[dict]:
        """
        Merges results from Google Books and OpenLibrary.
        Both clients return a normalised dict with keys:
            title, authors, isbn_13, publication_date, description
        Deduplication is by isbn_13 where available, else title+author fuzzy match.
        """
        google_results = await self.google_books.search_by_author(
            pen_name, published_after=cutoff
        )
        ol_results = await self.openlibrary.search_by_author(
            pen_name, published_after=cutoff
        )

        seen_isbns: set[str] = set()
        merged: list[dict] = []

        for item in google_results + ol_results:
            isbn = item.get("isbn_13")
            if isbn:
                if isbn in seen_isbns:
                    continue
                seen_isbns.add(isbn)
            merged.append(item)

        return merged

    async def _find_existing_work(self, candidate: dict) -> Work | None:
        """
        Checks if this candidate already exists in the DB.
        Primary key: isbn_13 via Edition table.
        Fallback: normalised title + pen_name match on Work table.
        """
        isbn = candidate.get("isbn_13")
        if isbn:
            edition_result = await self.session.execute(
                select(Edition).where(Edition.isbn_13 == isbn)
            )
            edition = edition_result.scalar_one_or_none()
            if edition:
                work_result = await self.session.execute(
                    select(Work).where(Work.work_uuid == edition.work_uuid)
                )
                return work_result.scalar_one_or_none()

        # Fallback: normalised title match (lowercase, stripped)
        title_normalised = candidate.get("title", "").lower().strip()
        works_result = await self.session.execute(select(Work))
        for work in works_result.scalars().all():
            if work.title.lower().strip() == title_normalised:
                return work

        return None

    async def _persist_candidate(
        self, candidate: dict, pen_names: list[PenName], pen_name_str: str
    ) -> Work | None:
        """
        Persists a new Work (and Edition if ISBN available) from a candidate dict.
        The enrichment pipeline (EnrichmentService) handles tag/vector enrichment
        separately — this only creates the bare Work row.
        """
        matched_pen_name = next(
            (pn for pn in pen_names if pn.name == pen_name_str), None
        )
        if not matched_pen_name:
            return None

        pub_date = candidate.get("publication_date")
        if isinstance(pub_date, str):
            try:
                pub_date = date.fromisoformat(pub_date)
            except ValueError:
                pub_date = None

        work = Work(
            pen_name_uuid=matched_pen_name.pen_name_uuid,
            title=candidate["title"],
            publication_date=pub_date,
            enrichment_status="pending",
        )
        self.session.add(work)
        await self.session.flush()  # get work_uuid before Edition insert

        isbn = candidate.get("isbn_13")
        if isbn:
            edition = Edition(
                work_uuid=work.work_uuid,
                isbn_13=isbn,
                format="unknown",
            )
            self.session.add(edition)
            await self.session.flush()

        return work

    # ------------------------------------------------------------------
    # Notification Write
    # ------------------------------------------------------------------

    async def write_release_notification(self, user_uuid: UUID, work: Work) -> None:
        """
        Writes an in-app notification record for a new release.
        SRS FR-AT-03: notification is surfaced on next app open.
        Currently writes to InteractionEvent with event_type='release_alert'.
        A dedicated notifications table is a Phase 2 concern.
        """
        event = InteractionEvent(
            user_uuid=user_uuid,
            work_uuid=work.work_uuid,
            event_type="release_alert",
            metadata={"title": work.title},
        )
        self.session.add(event)
        await self.session.flush()
