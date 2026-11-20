"""Onboarding API routes. Plugged into main.py with app.include_router(router)."""
from typing import Annotated

from fastapi import APIRouter, HTTPException
from google.genai.errors import APIError
from langfuse import observe
from pydantic import BaseModel, Field, ValidationError

from backend.app.db import with_conn
from backend.app.ingest.repo_loader import GitHubUnavailable, RepoNotFound
from backend.app.onboarding.facts import load_repo_facts
from backend.app.onboarding.issues import GitHubRateLimited
from backend.app.onboarding.issues_service import build_issues
from backend.app.onboarding.path import MAX_DAYS, MAX_HOURS, MIN_HOURS
from backend.app.onboarding.path_service import build_path
from backend.app.onboarding.quiz_grade import grade, load_quiz_by_id, public_view
from backend.app.onboarding.quiz_service import MAX_QUESTIONS, build_quiz
from backend.app.onboarding.quiz_sources import DEFAULT_QUESTIONS
from backend.app.tracing import current_trace_id

router = APIRouter(tags=["onboarding"])

REPO_SQL = "SELECT status, url, commit_sha FROM repos WHERE id = %s"


class PathRequest(BaseModel):
    days: int = Field(5, ge=1, le=MAX_DAYS)
    hours_per_day: float = Field(2.0, ge=MIN_HOURS, le=MAX_HOURS)


class QuizRequest(BaseModel):
    questions: int = Field(DEFAULT_QUESTIONS, ge=1, le=MAX_QUESTIONS)


class AnswersRequest(BaseModel):
    answers: dict[str, Annotated[int, Field(ge=0, le=3)]]


def _ready_repo(conn, repo_id: int):
    """Returns (status, url, commit_sha) or raises 404 / 409."""
    row = conn.execute(REPO_SQL, (repo_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "repo not found")
    if row[0] != "ready":
        raise HTTPException(409, f"repo is not ready (status: {row[0]})")
    return row


def _llm_errors(fn):
    """Run fn; map Gemini failures to clear HTTP errors."""
    try:
        return fn()
    except APIError as e:
        raise HTTPException(503, "LLM service unavailable, try again later") from e
    except ValidationError as e:
        raise HTTPException(502, "LLM returned an invalid response") from e


@observe(name="onboarding.path", capture_input=False, capture_output=False)
def _make_path(conn, repo_id: int, req: PathRequest) -> dict:
    facts = load_repo_facts(conn, repo_id)
    plan = build_path(conn, facts, req.days, req.hours_per_day)
    return {**plan, "trace_id": current_trace_id()}


@observe(name="onboarding.issues", capture_input=False, capture_output=False)
def _get_issues(conn, repo_id: int, url: str, sha: str) -> dict:
    data = build_issues(conn, {"repo_id": repo_id, "url": url, "commit_sha": sha})
    return {**data, "trace_id": current_trace_id()}


@observe(name="onboarding.quiz", capture_input=False, capture_output=False)
def _make_quiz(conn, repo_id: int, n: int) -> dict:
    facts = load_repo_facts(conn, repo_id)
    return {**public_view(build_quiz(conn, facts, n)), "trace_id": current_trace_id()}


@router.post("/repos/{repo_id}/onboarding/path")
def onboarding_path(repo_id: int, req: PathRequest):
    def run(conn):
        _ready_repo(conn, repo_id)
        return _make_path(conn, repo_id, req)

    # retries=0: this calls Gemini and writes to the DB - a retry could pay twice.
    return _llm_errors(lambda: with_conn(run, retries=0))


@router.get("/repos/{repo_id}/onboarding/issues")
def onboarding_issues(repo_id: int):
    def run(conn):
        row = _ready_repo(conn, repo_id)
        return _get_issues(conn, repo_id, row[1], row[2])

    try:
        # retries=0: each retry would spend one of GitHub's 60 requests per hour.
        return with_conn(run, retries=0)
    except GitHubRateLimited as e:
        raise HTTPException(429, str(e)) from e
    except RepoNotFound as e:
        raise HTTPException(502, f"GitHub could not find this repo: {e}") from e
    except GitHubUnavailable as e:
        raise HTTPException(503, "GitHub unavailable, try again later") from e


@router.post("/repos/{repo_id}/onboarding/quiz")
def onboarding_quiz(repo_id: int, req: QuizRequest):
    """Questions only - the answer key, explanations, proof lines and checks stay on the server."""
    def run(conn):
        _ready_repo(conn, repo_id)
        return _make_quiz(conn, repo_id, req.questions)

    # retries=0: this calls Gemini and writes to the DB - a retry could pay twice.
    return _llm_errors(lambda: with_conn(run, retries=0))


@router.post("/onboarding/quizzes/{quiz_id}/answers")
def quiz_answers(quiz_id: int, req: AnswersRequest):
    def run(conn):
        quiz = load_quiz_by_id(conn, quiz_id)
        if quiz is None:
            raise HTTPException(404, "quiz not found")
        return grade(quiz, req.answers)

    return with_conn(run)          # a pure read: the default single retry is safe