import enum
import uuid
from sqlalchemy import Column, String, Integer, Text, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy import DateTime
from database import Base


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
    youtube_id = Column(String)
    retry_count = Column(Integer, default=0)
    error_log = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Episode(Base):
    __tablename__ = "episodes"

    id = Column(Integer, primary_key=True, index=True)
    series_name = Column(String, nullable=False)
    episode_no = Column(Integer, nullable=False)
    job_id = Column(UUID(as_uuid=True))
    title = Column(String)
    video_path = Column(String)
    youtube_id = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
