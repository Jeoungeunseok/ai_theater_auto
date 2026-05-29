-- 팡이 v2 초기 데이터베이스 스키마

CREATE TYPE job_status AS ENUM ('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED');

CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ── 작업 테이블 ──────────────────────────────────────────
CREATE TABLE IF NOT EXISTS jobs (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    status       job_status DEFAULT 'PENDING',
    current_step TEXT,
    topic        TEXT NOT NULL,
    category     TEXT,                   -- 직장 | 욕망 | 부부 | 일상
    episode_no   INTEGER,
    vote_options TEXT,                   -- JSON list
    video_path   TEXT,
    youtube_id   TEXT,
    retry_count  INTEGER DEFAULT 0,
    error_log    TEXT,
    created_at   TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at   TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TRIGGER trg_jobs_updated_at
    BEFORE UPDATE ON jobs
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE INDEX IF NOT EXISTS idx_jobs_status     ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs(created_at DESC);

-- ── 에피소드 테이블 ──────────────────────────────────────
CREATE TABLE IF NOT EXISTS episodes (
    id               SERIAL PRIMARY KEY,
    category         TEXT NOT NULL,      -- 직장 | 욕망 | 부부 | 일상
    episode_no       INTEGER NOT NULL,
    job_id           UUID REFERENCES jobs(id),
    title            TEXT,
    video_path       TEXT,
    youtube_url      TEXT,
    youtube_video_id TEXT,
    vote_options     TEXT,               -- JSON list
    created_at       TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_episodes_category ON episodes(category);

-- ── 소재 풀 테이블 ────────────────────────────────────────
CREATE TABLE IF NOT EXISTS topics (
    id         SERIAL PRIMARY KEY,
    category   TEXT NOT NULL,
    title      TEXT NOT NULL,
    source     TEXT,                     -- archetype | submission | trend | ai_original
    status     TEXT DEFAULT 'pending',   -- pending | used | rejected
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_topics_status   ON topics(status);
CREATE INDEX IF NOT EXISTS idx_topics_category ON topics(category);

-- ── 투표 테이블 ───────────────────────────────────────────
CREATE TABLE IF NOT EXISTS votes (
    id          SERIAL PRIMARY KEY,
    episode_id  INTEGER REFERENCES episodes(id),
    choice_key  TEXT NOT NULL,
    count       INTEGER DEFAULT 0,
    snapshot_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (episode_id, choice_key)
);

CREATE INDEX IF NOT EXISTS idx_votes_episode ON votes(episode_id);

-- ── 시청자 제보 테이블 ────────────────────────────────────
CREATE TABLE IF NOT EXISTS submissions (
    id              SERIAL PRIMARY KEY,
    raw_text        TEXT NOT NULL,
    consent         BOOLEAN DEFAULT FALSE,
    status          TEXT DEFAULT 'pending',  -- pending | used | rejected
    used_episode_id INTEGER REFERENCES episodes(id),
    created_at      TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_submissions_status ON submissions(status);
