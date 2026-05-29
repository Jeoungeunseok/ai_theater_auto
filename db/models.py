import enum
import uuid
import datetime
from sqlalchemy import Column, String, Integer, Text, Boolean, Enum as SQLEnum, DateTime, ForeignKey
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
    category = Column(String)           # 직장 | 욕망 | 부부 | 일상
    episode_no = Column(Integer)
    vote_options = Column(Text)         # JSON list — 다음 본심 주제 후보
    video_path = Column(String)
    youtube_id = Column(String)
    retry_count = Column(Integer, default=0)
    error_log = Column(Text)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)


class Episode(Base):
    __tablename__ = "episodes"

    id = Column(Integer, primary_key=True, index=True)
    category = Column(String, nullable=False)   # 직장 | 욕망 | 부부 | 일상
    episode_no = Column(Integer, nullable=False)
    job_id = Column(UUID(as_uuid=True), ForeignKey("jobs.id"))
    title = Column(String)
    video_path = Column(String)
    youtube_url = Column(String)
    youtube_video_id = Column(String)
    vote_options = Column(Text)         # JSON list
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class Topic(Base):
    """소재 풀 — 아키타입 뱅크 / 제보 / 트렌드 / AI 오리지널"""
    __tablename__ = "topics"

    id = Column(Integer, primary_key=True, index=True)
    category = Column(String, nullable=False)
    title = Column(Text, nullable=False)
    source = Column(String)             # archetype | submission | trend | ai_original
    status = Column(String, default="pending")  # pending | used | rejected
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class Vote(Base):
    __tablename__ = "votes"

    id = Column(Integer, primary_key=True, index=True)
    episode_id = Column(Integer, ForeignKey("episodes.id"))
    choice_key = Column(String, nullable=False)
    count = Column(Integer, default=0)
    snapshot_at = Column(DateTime, default=datetime.datetime.utcnow)


class Submission(Base):
    """시청자 제보 — 동의·익명화 처리 필수"""
    __tablename__ = "submissions"

    id = Column(Integer, primary_key=True, index=True)
    raw_text = Column(Text, nullable=False)
    consent = Column(Boolean, default=False)
    status = Column(String, default="pending")  # pending | used | rejected
    used_episode_id = Column(Integer, ForeignKey("episodes.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
