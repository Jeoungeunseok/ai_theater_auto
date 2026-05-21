import enum
import uuid
import datetime
from sqlalchemy import Column, String, Integer, Text, Enum as SQLEnum, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from .database import Base

class JobStatus(enum.Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

class Job(Base):
    __tablename__ = "jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    status = Column(SQLEnum(JobStatus), default=JobStatus.PENDING)
    current_step = Column(String)
    topic = Column(Text, nullable=False)
    series_name = Column(String)
    choices = Column(Text)
    video_path = Column(String)
    youtube_id = Column(String)
    retry_count = Column(Integer, default=0)
    error_log = Column(Text)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

class Episode(Base):
    __tablename__ = "episodes"

    id = Column(Integer, primary_key=True, index=True)
    series_name = Column(String, nullable=False)
    episode_no = Column(Integer, nullable=False)
    job_id = Column(UUID(as_uuid=True))
    title = Column(String)
    video_path = Column(String)
    youtube_url = Column(String)
    youtube_video_id = Column(String)
    choices = Column(Text)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class Vote(Base):
    __tablename__ = "votes"

    id = Column(Integer, primary_key=True, index=True)
    episode_id = Column(Integer, ForeignKey("episodes.id"))
    choice_key = Column(String, nullable=False)
    count = Column(Integer, default=0)
    snapshot_at = Column(DateTime, default=datetime.datetime.utcnow)
