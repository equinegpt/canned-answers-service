# models.py
import uuid
from datetime import datetime, date

from sqlalchemy import Column, String, Integer, Date, DateTime, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from db import Base


class CannedAnswer(Base):
    __tablename__ = "canned_answers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Key fields
    date = Column(Date, nullable=False)
    pf_meeting_id = Column(Integer, nullable=False)
    race_number = Column(Integer, nullable=False)
    prompt_type = Column(String(50), nullable=False)  # e.g. "value_play"

    # Payload
    prompt_text = Column(Text, nullable=True)        # "Value Play", "Best at Conditions", etc
    raw_response = Column(Text, nullable=False)      # raw iReel text

    # Audit
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint(
            "date",
            "pf_meeting_id",
            "race_number",
            "prompt_type",
            name="uq_canned_key",
        ),
    )
