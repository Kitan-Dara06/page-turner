from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from .books import WorkResponse


class TBRAddRequest(BaseModel):
    work_uuid: UUID
    # The UI sends the current query text so it travels with the book
    current_query_text: Optional[str] = None
    current_mood_tags: Optional[List[str]] = None


class TBREntryResponse(BaseModel):
    tbr_uuid: UUID
    work: WorkResponse
    added_at: datetime
    priority_score: float

    # Context
    add_query_text: Optional[str] = None
    add_time_of_day: Optional[str] = None
    add_day_of_week: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)
