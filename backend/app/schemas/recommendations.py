from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict

from .books import WorkResponse


class RecommendationRequest(BaseModel):
    query: str


class RecommendedItem(BaseModel):
    work: WorkResponse
    explanation: str  # Trope-based per-book explanation (FR-QR-06)
    match_source: str  # "vector" | "llm" | "tbr" | "exploration"
    tbr_context_bonus: bool = False
    is_in_tbr: bool = False  # Book is already in the user's active TBR list
    description: Optional[str] = (
        None  # From EnrichmentCache, for expandable card detail
    )


class TBRMatch(BaseModel):
    """A mood-matched TBR book surfaced in the separate TBR strip."""

    work_uuid: str
    title: str
    author_name: str
    cover_url: Optional[str] = None
    explanation: str  # Why it fits the current query mood
    overlap_score: float = 0.0


class AuthorSpotlightBook(BaseModel):
    """A single book entry in the author spotlight sidebar."""

    work_uuid: str
    title: str
    cover_url: Optional[str] = None
    publication_year: Optional[int] = None
    series_label: Optional[str] = None  # e.g. "Something Series #1"


class AuthorSpotlight(BaseModel):
    """
    Supplementary author discovery panel.
    Surfaced when a similarity query mentions a specific author
    (e.g. 'books like Play Along by Liz Tomforde').
    Rendered as a separate UI section — not mixed into the main results.
    """

    author_name: str
    person_uuid: Optional[str] = None  # None if author not yet in DB
    pen_names: List[str] = []  # Other names this author writes under
    books: List[AuthorSpotlightBook]


class RecommendationResponse(BaseModel):
    session_id: str
    query_rewritten: str
    mood_tags_extracted: List[str]
    results: List[RecommendedItem]
    author_spotlight: Optional[AuthorSpotlight] = None
    tbr_matches: List[TBRMatch] = []
    content_mode: str = (
        "fiction"  # "fiction" | "nonfiction" — drives label set selection
    )


class TBRDropCandidate(BaseModel):
    """FR-TBR-02: Decayed TBR entry surfaced for keep/drop decision."""

    tbr_uuid: str
    work_uuid: str
    title: str
    author_name: str
    cover_url: Optional[str] = None
    priority_score: float
    days_since_added: int


class CheckpointItem(BaseModel):
    rec_uuid: str
    work: WorkResponse
    delivered_at: str


class CheckpointResponse(BaseModel):
    pending_items: List[CheckpointItem]
    drop_candidates: List[TBRDropCandidate] = []


class CheckpointUpdateItem(BaseModel):
    """FR-FL-02/03/04: Single checkpoint status update."""

    rec_uuid: str
    status: (
        str  # "finished" | "abandoned" | "still_reading" | "havent_started" | "reread"
    )
    abandonment_stage: Optional[str] = (
        None  # "barely_started" | "halfway" | "nearly_finished" — only for abandoned
    )
    stated_rating: Optional[int] = None  # 1-5, only for finished/reread


class CheckpointUpdateRequest(BaseModel):
    updates: List[CheckpointUpdateItem]


class CheckpointUpdateResponse(BaseModel):
    processed: int
    errors: List[str] = []
