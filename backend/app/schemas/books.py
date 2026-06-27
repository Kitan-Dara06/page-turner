from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AuthorBase(BaseModel):
    person_uuid: UUID
    canonical_name: str


class AuthorResponse(AuthorBase):
    model_config = ConfigDict(from_attributes=True)


class SeriesInfo(BaseModel):
    series_uuid: UUID
    title: str
    order_float: float
    is_core_storyline: bool


class WorkResponse(BaseModel):
    work_uuid: UUID
    title: str
    author: Optional[AuthorResponse] = None
    language: str
    aggregate_rating: Optional[float] = None

    cover_url: Optional[str] = None
    page_count: Optional[int] = None
    publication_year: Optional[int] = None

    series: Optional[SeriesInfo] = None

    # Enrichment status — frontend uses this to show "Newly added" badge
    # for partial books that lack trope-based explanations.
    enrichment_status: str = "pending"

    model_config = ConfigDict(from_attributes=True)
