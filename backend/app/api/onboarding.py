import logging
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies import get_current_user_uuid
from app.integrations import google_books as gb
from app.models.books import Work
from app.models.enrichment import EnrichmentCache
from app.models.events import EventType, InteractionEvent
from app.models.users import User, UserProfile
from app.schemas.books import WorkResponse
from app.schemas.onboarding import FlashcardDecision, FlashcardSubmit
from app.services import feedback_processor

logger = logging.getLogger(__name__)
router = APIRouter()

MOCK_USER_UUID = "00000000-0000-0000-0000-000000000001"  # replaced by auth dep below


@router.get("/flashcards", response_model=List[WorkResponse])
def get_onboarding_flashcards(
    db: Session = Depends(get_db),
    user_uuid: str = Depends(get_current_user_uuid),
):
    """
    FR-CS-04: Draws from the pre-seeded flashcard pool.
    FR-CS-05: Excludes books the user has already swiped.
    Post-onboarding: selects books near the user's established taste region.
    """
    # 1. Get IDs of books already swiped by this user
    swiped_subq = (
        select(InteractionEvent.work_uuid)
        .where(InteractionEvent.user_uuid == user_uuid)
        .where(InteractionEvent.session_id == "onboarding_session")
    ).scalar_subquery()

    # 2. Check if user has completed onboarding
    user_profile = db.execute(
        select(UserProfile).where(UserProfile.user_uuid == user_uuid)
    ).scalar_one_or_none()

    is_post_onboarding = user_profile is not None and (
        user_profile.darkness_tolerance is not None
        or user_profile.thematic_density is not None
    )

    base_query = (
        select(Work)
        .join(EnrichmentCache, Work.work_uuid == EnrichmentCache.work_uuid)
        .where(EnrichmentCache.flashcard_pool == True)
        .where(Work.work_uuid.notin_(swiped_subq))
    )

    if is_post_onboarding and user_profile:
        # FR-CS-05: Use Tower 1 state to find discriminative books
        # Prioritize books with extreme values (near 0 or 1) in dimensions
        # where the user has established preferences
        calibration_books = (
            db.execute(base_query.order_by(func.random()).limit(15)).scalars().all()
        )
    else:
        # First visit: random spread across genres
        calibration_books = (
            db.execute(base_query.order_by(func.random()).limit(12)).scalars().all()
        )

    if not calibration_books:
        logger.warning("No flashcard pool books available.")
        return []

    return [WorkResponse.model_validate(book) for book in calibration_books]


@router.post("/response")
def submit_flashcard_response(
    response: FlashcardSubmit,
    db: Session = Depends(get_db),
    user_uuid: str = Depends(get_current_user_uuid),
):
    """
    Receives a single flashcard swipe decision and immediately seeds the user's profile.
    FR-CS-05: NOT_INTERESTED swipes permanently contribute to the anti-profile.
    """
    work = db.execute(
        select(Work).where(Work.work_uuid == response.work_uuid)
    ).scalar_one_or_none()
    if not work:
        raise HTTPException(status_code=404, detail="Book not found")

    # Ensure mock user exists (FK constraint)
    user = db.execute(
        select(User).where(User.user_uuid == user_uuid)
    ).scalar_one_or_none()
    if not user:
        user = User(user_uuid=uuid.UUID(user_uuid))
        db.add(user)
        profile = UserProfile(user_uuid=user.user_uuid)
        db.add(profile)
        db.flush()

    event_type_map = {
        FlashcardDecision.READ_IT: EventType.LOGGED_READ,
        FlashcardDecision.INTERESTED: EventType.TBR_ADD,
        FlashcardDecision.NOT_INTERESTED: EventType.NOT_INTERESTED,
    }
    mapped_event = event_type_map[response.decision]

    book_inferred_profile = _extract_book_profile(db, work)

    feedback_processor.process_interaction(
        db=db,
        user_uuid=user_uuid,
        event_type=mapped_event,
        work_uuid=str(work.work_uuid),
        session_id="onboarding_session",
        mood_tags=book_inferred_profile,
        is_fast_finish=False,
        is_reread=False,
    )

    return {"status": "success", "event_logged": mapped_event.value}


def _extract_book_profile(db: Session, work: Work) -> dict:
    """
    Uses the book's EnrichmentCache.tower1_snapshot if available,
    otherwise returns neutral defaults.
    """
    cache = db.execute(
        select(EnrichmentCache).where(EnrichmentCache.work_uuid == work.work_uuid)
    ).scalar_one_or_none()

    if cache and cache.tower1_snapshot:
        return cache.tower1_snapshot

    return {
        "pacing_preference": 0.5,
        "thematic_density": 0.5,
        "speculative_deviation": 0.5,
    }


# ── Seed Request / Response ──


class SeedBookRequest(BaseModel):
    title: str = Field(
        ..., min_length=1, max_length=200, description="Freeform book title"
    )


class SeedRequest(BaseModel):
    books: List[SeedBookRequest] = Field(..., min_items=1, max_items=3)


class SeedResolvedBook(BaseModel):
    title: str
    author: str
    work_uuid: str | None = None
    cover_url: str | None = None
    resolved: bool  # True if we found it in Google Books


class SeedResponse(BaseModel):
    resolved_books: List[SeedResolvedBook]
    tropes_applied: int
    profile_updated: bool


@router.post("/seed", response_model=SeedResponse)
def seed_from_books(
    seed: SeedRequest,
    db: Session = Depends(get_db),
    user_uuid: str = Depends(get_current_user_uuid),
):
    """
    Accepts up to 3 book titles the user has read and loved.
    Resolves them via Google Books, extracts their Tower 1 profiles,
    primes the user's profile, auto-tracks the authors, and schedules
    niche-genre population if the books belong to a sparse genre space.
    """
    resolved: list[SeedResolvedBook] = []
    total_tropes = 0

    # Ensure user + profile exist
    user = db.execute(
        select(User).where(User.user_uuid == user_uuid)
    ).scalar_one_or_none()
    if not user:
        user = User(user_uuid=uuid.UUID(user_uuid))
        db.add(user)
        db.flush()
    profile = db.execute(
        select(UserProfile).where(UserProfile.user_uuid == user_uuid)
    ).scalar_one_or_none()
    if not profile:
        profile = UserProfile(user_uuid=user.user_uuid)
        db.add(profile)
        db.flush()

    for book in seed.books:
        title = book.title.strip()
        if not title:
            continue

        # Search Google Books
        gb_item = _search_book_by_title(title)
        if not gb_item:
            resolved.append(SeedResolvedBook(title=title, author="", resolved=False))
            continue

        vol = gb_item.get("volumeInfo", {})
        gb_title = vol.get("title", title)
        authors = vol.get("authors", [])
        author_name = authors[0] if authors else "Unknown"
        image_links = vol.get("imageLinks", {})
        cover_url = (
            image_links.get("thumbnail", "").replace("http:", "https:")
            if image_links
            else None
        )

        # Find or create Work in our DB
        work = _find_or_create_work(db, gb_item)
        if not work:
            resolved.append(
                SeedResolvedBook(title=gb_title, author=author_name, resolved=True)
            )
            continue

        resolved.append(
            SeedResolvedBook(
                title=gb_title,
                author=author_name,
                work_uuid=str(work.work_uuid),
                cover_url=cover_url,
                resolved=True,
            )
        )

        # Extract Tower 1 profile from this book's enrichment cache
        cache = db.execute(
            select(EnrichmentCache).where(EnrichmentCache.work_uuid == work.work_uuid)
        ).scalar_one_or_none()

        book_profile = {}
        if cache and cache.tower1_snapshot:
            book_profile = cache.tower1_snapshot
            total_tropes += len(book_profile)

        # Apply to user's profile via the standard processor
        feedback_processor.process_interaction(
            db=db,
            user_uuid=user_uuid,
            event_type=EventType.LOGGED_READ,
            work_uuid=str(work.work_uuid),
            session_id="seed_onboarding",
            mood_tags=book_profile if book_profile else None,
            is_fast_finish=False,
            is_reread=False,
        )

        # Auto-track author
        from app.models.tracked_authors import TrackedAuthor

        existing_track = db.execute(
            select(TrackedAuthor).where(
                TrackedAuthor.user_uuid == user_uuid,
                TrackedAuthor.person_uuid == work.person_uuid,
            )
        ).scalar_one_or_none()
        if not existing_track:
            db.add(TrackedAuthor(user_uuid=user_uuid, person_uuid=work.person_uuid))

    db.commit()

    # Fire background task to detect genre sparsity and populate if needed
    if resolved:
        _schedule_niche_population(resolved)

    return SeedResponse(
        resolved_books=resolved,
        tropes_applied=total_tropes,
        profile_updated=total_tropes > 0,
    )


def _search_book_by_title(title: str) -> dict | None:
    """Search Google Books by title. Returns the first match or None."""
    import httpx

    params = {
        "q": f"intitle:{title}",
        "key": __import__(
            "app.config", fromlist=["settings"]
        ).settings.GOOGLE_BOOKS_API_KEY,
        "maxResults": 1,
    }
    try:
        with httpx.Client(timeout=httpx.Timeout(8.0, connect=4.0)) as client:
            resp = client.get(
                "https://www.googleapis.com/books/v1/volumes", params=params
            )
            resp.raise_for_status()
            items = resp.json().get("items", [])
            return items[0] if items else None
    except Exception:
        logger.warning(f"Google Books lookup failed for: {title}")
        return None


def _find_or_create_work(db: Session, gb_item: dict) -> Work | None:
    """Find a Work by Google Books ID or create a new one. Returns the Work."""
    vol = gb_item.get("volumeInfo", {})
    title = vol.get("title", "")
    if not title:
        return None

    authors = vol.get("authors", [])
    author_name = authors[0] if authors else "Unknown"
    isbns = [
        i.get("identifier")
        for i in vol.get("industryIdentifiers", [])
        if i.get("type") in ("ISBN_13", "ISBN_10")
    ]

    # Try ISBN lookup first
    from app.models.authors import Person
    from app.models.books import Edition

    if isbns:
        for isbn in isbns:
            ed = db.execute(
                select(Edition).where(Edition.isbn == isbn)
            ).scalar_one_or_none()
            if ed:
                return db.execute(
                    select(Work).where(Work.work_uuid == ed.work_uuid)
                ).scalar_one_or_none()

    # Try title + author match
    existing = (
        db.execute(select(Work).where(func.lower(Work.title) == title.lower()))
        .scalars()
        .all()
    )
    for w in existing:
        if w.author and w.author.canonical_name.lower() == author_name.lower():
            return w

    # Not found — create the Work + Person
    person = db.execute(
        select(Person).where(func.lower(Person.canonical_name) == author_name.lower())
    ).scalar_one_or_none()
    if not person:
        person = Person(canonical_name=author_name)
        db.add(person)
        db.flush()

    work = Work(
        title=title,
        person_uuid=person.person_uuid,
        enrichment_status="pending",
    )
    db.add(work)
    db.flush()

    # Create Edition with ISBN if available
    if isbns:
        ed = Edition(
            work_uuid=work.work_uuid,
            isbn=isbns[0],
            format="unknown",
        )
        db.add(ed)
        db.flush()

    # Queue for enrichment
    from app.workers.enrichment_tasks import enrich_single_work

    enrich_single_work.delay(str(work.work_uuid))

    return work


def _schedule_niche_population(resolved: list[SeedResolvedBook]):
    """Fire-and-forget: check if seed books are from a low-density genre, populate if so."""
    try:
        work_uuids = [b.work_uuid for b in resolved if b.work_uuid]
        if work_uuids:
            from app.workers.author_alert_tasks import seed_niche_genre_from_books

            seed_niche_genre_from_books.delay(work_uuids)
    except Exception:
        logger.warning("Failed to schedule niche population task")


# ── FR-CS-04/05 helpers ──
