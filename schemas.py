# schemas.py
from datetime import date
from pydantic import BaseModel


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
