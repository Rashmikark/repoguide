"""Build an onboarding path once, save it, and serve the saved copy afterwards.
Key: repo + commit + days + minutes per day. A plan made by an older planner
version is ignored and replaced."""
from psycopg.types.json import Jsonb

from backend.app.onboarding.path import plan_reading
from backend.app.onboarding.path_explain import explain_path
from backend.app.onboarding.sizes import load_sizes

PLANNER_VERSION = 1   # bump when the planner rules or the explain prompt change

GET_SQL = """
SELECT plan FROM onboarding_paths
WHERE repo_id = %s AND commit_sha = %s AND days = %s AND minutes_per_day = %s
"""

SAVE_SQL = """
INSERT INTO onboarding_paths (repo_id, commit_sha, days, minutes_per_day, plan)
VALUES (%s, %s, %s, %s, %s)
ON CONFLICT (repo_id, commit_sha, days, minutes_per_day)
DO UPDATE SET plan = EXCLUDED.plan, created_at = now()
"""


def get_saved(conn, repo_id: int, sha: str, days: int, minutes: int) -> dict | None:
    row = conn.execute(GET_SQL, (repo_id, sha, days, minutes)).fetchone()
    if row is None or row[0].get("planner_version") != PLANNER_VERSION:
        return None
    return row[0]


def save_plan(conn, repo_id: int, sha: str, days: int, minutes: int, plan: dict) -> None:
    conn.execute(SAVE_SQL, (repo_id, sha, days, minutes, Jsonb(plan)))
    conn.commit()


def build_path(conn, facts: dict, days: int, hours_per_day: float) -> dict:
    minutes = round(hours_per_day * 60)
    sha = facts.get("commit_sha")
    if sha:
        saved = get_saved(conn, facts["repo_id"], sha, days, minutes)
        if saved is not None:
            return {**saved, "cached": True}

    sizes = load_sizes(conn, facts["repo_id"])
    # File list comes from sizes (every indexed file), not facts["files"] (capped at 300).
    plan = plan_reading(list(sizes), sizes, facts["entry_points"], facts["readme_path"],
                        days, hours_per_day)
    plan = explain_path(conn, facts, plan)
    plan["planner_version"] = PLANNER_VERSION
    if sha:
        save_plan(conn, facts["repo_id"], sha, days, minutes, plan)
    return {**plan, "cached": False}