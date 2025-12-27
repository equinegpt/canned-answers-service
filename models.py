# models.py
import uuid
from datetime import datetime

from sqlalchemy import (
    Column,
    String,
    Integer,
    Date,
    DateTime,
    Text,
    UniqueConstraint,
    Index,
)
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
    prompt_text = Column(Text, nullable=True)   # human-facing text ("Value Play", etc)
    raw_response = Column(Text, nullable=False) # raw iReel text

    # Usage metrics
    use_count = Column(Integer, nullable=False, default=0)

    # Optional metadata
    first_used_at = Column(DateTime, nullable=True)
    first_used_ip = Column(String(64), nullable=True)
    first_used_ua = Column(String(255), nullable=True)

    last_used_at = Column(DateTime, nullable=True)
    last_used_ip = Column(String(64), nullable=True)
    last_used_ua = Column(String(255), nullable=True)

    # Audit
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    __table_args__ = (
        UniqueConstraint(
            "date",
            "pf_meeting_id",
            "race_number",
            "prompt_type",
            name="uq_canned_key",
        ),
    )


class MeetingLabel(Base):
    """
    Simple cache of pf_meeting_id → "Track (STATE)" so we don't depend
    on RA-crawler after 2pm reset.
    """
    __tablename__ = "meeting_labels"

    id = Column(Integer, primary_key=True, index=True)
    pf_meeting_id = Column(Integer, unique=True, index=True, nullable=False)
    label = Column(String(200), nullable=False)


class FreeformQuestion(Base):
    """
    Cached freeform Q&A pairs with normalized tokens for fuzzy matching.
    """
    __tablename__ = "freeform_questions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Key fields (composite index for race-scoped lookups)
    date = Column(Date, nullable=False)
    pf_meeting_id = Column(Integer, nullable=False)
    race_number = Column(Integer, nullable=False)

    # Question storage
    question = Column(Text, nullable=False)              # Original question as-is
    question_normalized = Column(Text, nullable=False)   # Lowercase, punctuation stripped
    question_tokens = Column(Text, nullable=False)       # JSON array of tokens (stop words removed)

    # Response
    raw_response = Column(Text, nullable=False)

    # Usage metrics
    use_count = Column(Integer, nullable=False, default=0)

    # Audit
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    __table_args__ = (
        # Composite index for race-scoped queries (critical for performance)
        Index("ix_freeform_race_scope", "date", "pf_meeting_id", "race_number"),
    )
