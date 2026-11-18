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