"""Good first issues with a saved copy. GitHub data changes, so the copy expires after
TTL_MINUTES, and a new commit (related-code links depend on it) also forces a refresh."""
from psycopg.types.json import Jsonb

from backend.app.onboarding.issue_code import attach_related
from backend.app.onboarding.issues import fetch_open_issues, pick_issues

ISSUES_VERSION = 1    # bump when picking/ranking/related-code rules change
TTL_MINUTES = 60      # GitHub allows 60 unauthenticated requests per hour

GET_SQL = """
SELECT data, fetched_at FROM onboarding_issues
WHERE repo_id = %s AND commit_sha = %s AND fetched_at > now() - make_interval(mins => %s)
"""

SAVE_SQL = """
INSERT INTO onboarding_issues (repo_id, commit_sha, data) VALUES (%s, %s, %s)
ON CONFLICT (repo_id)
DO UPDATE SET commit_sha = EXCLUDED.commit_sha, data = EXCLUDED.data, fetched_at = now()
"""

OWNER_SQL = "SELECT owner, name FROM repos WHERE id = %s"


def get_saved(conn, repo_id: int, sha: str) -> dict | None:
    row = conn.execute(GET_SQL, (repo_id, sha, TTL_MINUTES)).fetchone()
    if row is None or row[0].get("issues_version") != ISSUES_VERSION:
        return None
    return {**row[0], "fetched_at": row[1].isoformat()}


def save_issues(conn, repo_id: int, sha: str, data: dict) -> None:
    conn.execute(SAVE_SQL, (repo_id, sha, Jsonb(data)))
    conn.commit()


def build_issues(conn, facts: dict, fetch=fetch_open_issues) -> dict:
    rid, sha = facts["repo_id"], facts.get("commit_sha")
    if sha:
        saved = get_saved(conn, rid, sha)
        if saved is not None:
            return {**saved, "cached": True}

    row = conn.execute(OWNER_SQL, (rid,)).fetchone()
    if row is None:
        raise LookupError(f"repo {rid} not found")
    data = attach_related(conn, rid, facts["url"], sha, pick_issues(fetch(row[0], row[1])))
    data["issues_version"] = ISSUES_VERSION
    if sha:
        save_issues(conn, rid, sha, data)
    return {**data, "cached": False}