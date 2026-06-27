from enum import Enum
from uuid import UUID

from pydantic import BaseModel

from .books import WorkResponse


class FlashcardDecision(str, Enum):
    READ_IT = "read_it"
    INTERESTED = "interested"
    NOT_INTERESTED = "not_interested"


class FlashcardSubmit(BaseModel):
    work_uuid: UUID
    decision: FlashcardDecision
