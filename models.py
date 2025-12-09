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

    # Usage metrics
    # How many times this cached answer has been served/used
    use_count = Column(Integer, nullable=False, default=0)

# NEW optional metadata
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

    # Usage metrics
    # How many times this cached answer has been served/used
    use_count = Column(Integer, nullable=False, default=0)

    # NEW optional metadata
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


# Optional: only needed if you actually use Meeting anywhere
class Meeting(Base):
    __tablename__ = "meetings"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, index=True)
    track_name = Column(String, index=True)
    state = Column(String(3), index=True)
    pf_meeting_id = Column(Integer, index=True, unique=True)


class MeetingLabel(Base):
    __tablename__ = "meeting_labels"

    id = Column(Integer, primary_key=True, index=True)
    pf_meeting_id = Column(Integer, unique=True, index=True, nullable=False)
    label = Column(String(200), nullable=False)
