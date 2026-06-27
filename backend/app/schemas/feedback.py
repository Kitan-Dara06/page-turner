from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class FeedbackEventType(str, Enum):
    LOGGED_READ = "logged_read"
    NOT_INTERESTED = "not_interested"
    REREAD = "reread"
    CHECKPOINT_UPDATE = "checkpoint_update"
    INTERESTED = "interested"
    EXPLORATION_OUTCOME = "exploration_outcome"  # FR-EX


class CheckpointStatus(str, Enum):
    FINISHED = "finished"
    STILL_READING = "still_reading"
    ABANDONED = "abandoned"
    HAVENT_STARTED = "havent_started"


class AbandonmentStage(str, Enum):
    BARELY_STARTED = "barely_started"  # Under 20%
    HALFWAY = "halfway"  # 20 - 60%
    NEARLY_FINISHED = "nearly_finished"  # Over 60%


class FeedbackSubmit(BaseModel):
    work_uuid: UUID
    event_type: FeedbackEventType

    # Optional fields depending on the event_type
    checkpoint_status: Optional[CheckpointStatus] = None
    stated_rating: Optional[int] = Field(None, ge=1, le=5)
    abandonment_stage: Optional[AbandonmentStage] = None
    exploration_outcome: Optional[str] = (
        None  # FR-EX: "positive" | "negative" | "neutral"
    )
