-- Step 21: saved good-first-issues (GitHub data, refreshed after a TTL or a new commit)
CREATE TABLE IF NOT EXISTS onboarding_issues (
    repo_id     BIGINT PRIMARY KEY REFERENCES repos(id) ON DELETE CASCADE,
    commit_sha  TEXT NOT NULL,
    data        JSONB NOT NULL,
    fetched_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);