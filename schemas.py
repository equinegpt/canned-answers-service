# schemas.py
from datetime import date
from pydantic import BaseModel, Field


class CannedKey(BaseModel):
    date: date
    pf_meeting_id: int
    race_number: int
    prompt_type: str   # "value_play", "best_conditions", ...


class CannedAnswerOut(CannedKey):
    raw_response: str


class CannedAnswerIn(CannedKey):
    prompt_text: str | None = None
    raw_response: str


# --- Freeform Question Schemas ---

class FreeformQuestionKey(BaseModel):
    """Base key fields for race scoping"""
    date: date
    pf_meeting_id: int
    race_number: int


class FreeformQuestionIn(FreeformQuestionKey):
    """Input schema for POST /freeform"""
    question: str
    raw_response: str


class FreeformQuestionOut(FreeformQuestionKey):
    """Output schema for stored question"""
    question: str
    raw_response: str
    use_count: int


class FreeformMatchResult(BaseModel):
    """Response for successful match"""
    question: str        # The original stored question
    raw_response: str
    confidence: float    # Jaccard similarity score
