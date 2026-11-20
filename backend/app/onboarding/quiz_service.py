"""Build a quiz once, save it with an id, serve the saved copy afterwards.
Key: repo + commit + number of questions. The answer key is stored here and never
sent to the browser (the API strips it). A quiz with 0 kept questions is NOT saved,
so one bad Gemini response is not frozen forever."""
from psycopg.types.json import Jsonb

from backend.app.onboarding.path import order_files
from backend.app.onboarding.quiz_gen import make_quiz
from backend.app.onboarding.quiz_sources import (DEFAULT_QUESTIONS, load_candidates,
                                                 load_reference_counts, pick_quiz_sources)
from backend.app.onboarding.sizes import load_sizes

QUIZ_VERSION = 1      # bump when source picking or the quiz prompt changes
MAX_QUESTIONS = 10

GET_SQL = """
SELECT id, quiz FROM onboarding_quizzes
WHERE repo_id = %s AND commit_sha = %s AND questions = %s
"""

SAVE_SQL = """
INSERT INTO onboarding_quizzes (repo_id, commit_sha, questions, quiz)
VALUES (%s, %s, %s, %s)
ON CONFLICT (repo_id, commit_sha, questions)
DO UPDATE SET quiz = EXCLUDED.quiz, created_at = now()
RETURNING id
"""


def get_saved(conn, repo_id: int, sha: str, n: int) -> dict | None:
    row = conn.execute(GET_SQL, (repo_id, sha, n)).fetchone()
    if row is None or row[1].get("quiz_version") != QUIZ_VERSION:
        return None
    return {**row[1], "quiz_id": row[0]}


def save_quiz(conn, repo_id: int, sha: str, n: int, quiz: dict) -> int:
    quiz_id = conn.execute(SAVE_SQL, (repo_id, sha, n, Jsonb(quiz))).fetchone()[0]
    conn.commit()
    return quiz_id


def pick_sources(conn, facts: dict, n: int) -> list[dict]:
    rid = facts["repo_id"]
    sizes = load_sizes(conn, rid)
    order = order_files(list(sizes), sizes, facts["entry_points"], facts["readme_path"])
    preferred = [it.path for it in order if it.group in ("entry", "core")]
    return pick_quiz_sources(load_candidates(conn, rid), preferred, n,
                             load_reference_counts(conn, rid))


def build_quiz(conn, facts: dict, n: int = DEFAULT_QUESTIONS) -> dict:
    if not 1 <= n <= MAX_QUESTIONS:
        raise ValueError(f"questions must be 1-{MAX_QUESTIONS}")
    rid, sha = facts["repo_id"], facts.get("commit_sha")
    if sha:
        saved = get_saved(conn, rid, sha, n)
        if saved is not None:
            return {**saved, "cached": True}

    quiz = make_quiz(facts, pick_sources(conn, facts, n))
    quiz["quiz_version"] = QUIZ_VERSION
    quiz_id = None
    if sha and quiz["checks"]["kept"] > 0:
        quiz_id = save_quiz(conn, rid, sha, n, quiz)
    return {**quiz, "quiz_id": quiz_id, "cached": False}