CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS repos (
    id          BIGSERIAL PRIMARY KEY,
    url         TEXT NOT NULL UNIQUE,
    owner       TEXT NOT NULL,
    name        TEXT NOT NULL,
    commit_sha  TEXT,
    status      TEXT NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'indexing', 'ready', 'failed')),
    error       TEXT,
    file_count  INT NOT NULL DEFAULT 0,
    chunk_count INT NOT NULL DEFAULT 0,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    indexed_at  TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS files (
    id         BIGSERIAL PRIMARY KEY,
    repo_id    BIGINT NOT NULL REFERENCES repos(id) ON DELETE CASCADE,
    path       TEXT NOT NULL,
    language   TEXT,
    size_bytes INT NOT NULL,
    UNIQUE (repo_id, path)
);

CREATE TABLE IF NOT EXISTS chunks (
    id         BIGSERIAL PRIMARY KEY,
    repo_id    BIGINT NOT NULL REFERENCES repos(id) ON DELETE CASCADE,
    file_id    BIGINT NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    path       TEXT NOT NULL,
    start_line INT NOT NULL,
    end_line   INT NOT NULL,
    kind       TEXT NOT NULL,
    symbol     TEXT,
    content    TEXT NOT NULL,
    embedding  vector(768),
    CHECK (end_line >= start_line)
);

CREATE INDEX IF NOT EXISTS chunks_repo_idx
    ON chunks (repo_id);

CREATE INDEX IF NOT EXISTS chunks_embedding_idx
    ON chunks USING hnsw (embedding vector_cosine_ops);

-- Step 7: keyword search
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS search_text TEXT;

ALTER TABLE chunks ADD COLUMN IF NOT EXISTS search_tsv tsvector
    GENERATED ALWAYS AS (to_tsvector('english', coalesce(search_text, ''))) STORED;

CREATE INDEX IF NOT EXISTS chunks_search_idx
    ON chunks USING gin (search_tsv);

-- Step 11: background indexing heartbeat
ALTER TABLE repos ADD COLUMN IF NOT EXISTS heartbeat_at TIMESTAMPTZ;

-- Step 20: saved onboarding paths (same repo + commit + days + minutes -> same plan)
CREATE TABLE IF NOT EXISTS onboarding_paths (
    id              BIGSERIAL PRIMARY KEY,
    repo_id         BIGINT NOT NULL REFERENCES repos(id) ON DELETE CASCADE,
    commit_sha      TEXT NOT NULL,
    days            INT NOT NULL,
    minutes_per_day INT NOT NULL,
    plan            JSONB NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (repo_id, commit_sha, days, minutes_per_day)
);

-- Step 21: saved good-first-issues (GitHub data, refreshed after a TTL or a new commit)
CREATE TABLE IF NOT EXISTS onboarding_issues (
    repo_id     BIGINT PRIMARY KEY REFERENCES repos(id) ON DELETE CASCADE,
    commit_sha  TEXT NOT NULL,
    data        JSONB NOT NULL,
    fetched_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Step 22: saved quizzes (answer key stays on the server; graded by quiz id)
CREATE TABLE IF NOT EXISTS onboarding_quizzes (
    id          BIGSERIAL PRIMARY KEY,
    repo_id     BIGINT NOT NULL REFERENCES repos(id) ON DELETE CASCADE,
    commit_sha  TEXT NOT NULL,
    questions   INT NOT NULL,
    quiz        JSONB NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (repo_id, commit_sha, questions)
);