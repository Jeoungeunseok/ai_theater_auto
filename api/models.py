from sqlalchemy import Column, String, Integer, DateTime, Text, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
from .database import Base
import uuid
import datetime
import enum

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
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
