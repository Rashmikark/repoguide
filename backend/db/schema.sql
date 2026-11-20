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