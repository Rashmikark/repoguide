"""Onboarding API routes. Plugged into main.py with app.include_router(router)."""
from fastapi import APIRouter, HTTPException
from google.genai.errors import APIError
from langfuse import observe
from pydantic import BaseModel, Field, ValidationError

from backend.app.db import with_conn
from backend.app.onboarding.facts import load_repo_facts
from backend.app.onboarding.path import MAX_DAYS, MAX_HOURS, MIN_HOURS
from backend.app.onboarding.path_service import build_path
from backend.app.tracing import current_trace_id

router = APIRouter(tags=["onboarding"])

STATUS_SQL = "SELECT status FROM repos WHERE id = %s"


class PathRequest(BaseModel):
    days: int = Field(5, ge=1, le=MAX_DAYS)
    hours_per_day: float = Field(2.0, ge=MIN_HOURS, le=MAX_HOURS)


@observe(name="onboarding.path", capture_input=False, capture_output=False)
def _make_path(conn, repo_id: int, req: PathRequest) -> dict:
    facts = load_repo_facts(conn, repo_id)
    plan = build_path(conn, facts, req.days, req.hours_per_day)
    return {**plan, "trace_id": current_trace_id()}


@router.post("/repos/{repo_id}/onboarding/path")
def onboarding_path(repo_id: int, req: PathRequest):
    def run(conn):
        row = conn.execute(STATUS_SQL, (repo_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "repo not found")
        if row[0] != "ready":
            raise HTTPException(409, f"repo is not ready (status: {row[0]})")
        return _make_path(conn, repo_id, req)

    try:
        # retries=0: this calls Gemini and writes to the DB - a retry could pay twice.
        return with_conn(run, retries=0)
    except APIError as e:
        raise HTTPException(503, "LLM service unavailable, try again later") from e
    except ValidationError as e:
        raise HTTPException(502, "LLM returned an invalid response") from e