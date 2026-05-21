-- Phase 2: 초기 데이터베이스 스키마 설계

-- 작업 상태 관리를 위한 열거형
CREATE TYPE job_status AS ENUM ('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED');

-- 영상 제작 작업 테이블
CREATE TABLE IF NOT EXISTS jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    status job_status DEFAULT 'PENDING',
    current_step TEXT,
    topic TEXT NOT NULL,
    video_path TEXT,
    youtube_id TEXT,
    retry_count INTEGER DEFAULT 0,
    error_log TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 에피소드 관리 테이블
CREATE TABLE IF NOT EXISTS episodes (
    id SERIAL PRIMARY KEY,
    series_name TEXT NOT NULL,
    episode_no INTEGER NOT NULL,
    job_id UUID REFERENCES jobs(id),
    title TEXT,
    video_path TEXT,
    youtube_url TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
