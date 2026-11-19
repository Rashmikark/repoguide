import logging
import time
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Literal

from fastapi import BackgroundTasks, FastAPI, HTTPException, Response
from google.genai import errors as genai_errors
from langfuse import observe
from psycopg.rows import dict_row
from pydantic import BaseModel, Field, ValidationError

from backend.app.answer.explainer import explain
from backend.app.config import settings
from backend.app.db import pool, with_conn
from backend.app.ingest.indexer import index_repo
from backend.app.ingest.repo_loader import (
    GitHubUnavailable,
    RepoNotFound,
    parse_github_url,
    remote_head_sha,
)
from backend.app.links import github_line_url
from backend.app.retrieval.pipeline import retrieve
from backend.app.tracing import current_trace_id, langfuse, trace_request

log = logging.getLogger("uvicorn.error")


@asynccontextmanager
async def lifespan(app: FastAPI):
    pool.open(wait=True, timeout=30)
    yield
    pool.close()
    try:
        langfuse.flush()   # send any queued traces before the process exits
    except Exception:
        pass


app = FastAPI(title="RepoGuide API", version="0.1.0", lifespan=lifespan)


# ---------- models ----------

class RepoOut(BaseModel):
    id: int
    url: str
    status: str
    error: str | None
    commit_sha: str | None
    file_count: int
    chunk_count: int
    total_chunks: int
    embedded_chunks: int
    stalled: bool
    created_at: datetime
    indexed_at: datetime | None
    heartbeat_at: datetime | None


class IndexRequest(BaseModel):
    url: str
    force: bool = False


class IndexResponse(BaseModel):
    repo: RepoOut
    started: bool
    reason: str


Mode = Literal["vector", "keyword", "hybrid", "rerank", "llm-rerank"]


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)
    mode: Mode = "hybrid"
    k: int = Field(default=5, ge=1, le=10)


class CitationOut(BaseModel):
    source: int
    path: str | None
    start_line: int
    end_line: int
    valid: bool
    reason: str
    url: str | None


class SourceOut(BaseModel):
    n: int
    path: str
    start_line: int
    end_line: int
    kind: str
    symbol: str | None
    url: str


class AskResponse(BaseModel):
    repo_id: int
    question: str
    mode: str
    found: bool
    answer: str
    citations: list[CitationOut]
    invalid_citations: int
    sources: list[SourceOut]
    timings_ms: dict[str, int]
    llm_usage: list[dict]
    trace_id: str | None


# ---------- SQL ----------

# The first %s is always settings.stale_after_minutes.
REPO_SELECT = """
SELECT r.id, r.url, r.status, r.error, r.commit_sha, r.file_count, r.chunk_count,
       r.created_at, r.indexed_at, r.heartbeat_at,
       (SELECT count(*)           FROM chunks c WHERE c.repo_id = r.id) AS total_chunks,
       (SELECT count(c.embedding) FROM chunks c WHERE c.repo_id = r.id) AS embedded_chunks,
       (r.status IN ('pending', 'indexing')
        AND coalesce(r.heartbeat_at, r.created_at) < now() - make_interval(mins => %s)) AS stalled
FROM repos r
"""

# A repo may be (re)claimed if it is finished, failed, never started, or stalled.
# One UPDATE = one row lock, so two concurrent requests can never both win.
CLAIM_SQL = """
UPDATE repos SET status = 'pending', error = NULL, heartbeat_at = now()
WHERE url = %s AND (
    status IN ('ready', 'failed')
    OR heartbeat_at IS NULL
    OR heartbeat_at < now() - make_interval(mins => %s)
)
RETURNING id
"""


def _one(conn, where: str, params: tuple):
    return conn.cursor(row_factory=dict_row).execute(
        REPO_SELECT + where, (settings.stale_after_minutes, *params)
    ).fetchone()


def _run_indexing(url: str) -> None:
    try:
        log.info("indexing %s finished: %s", url, index_repo(url))
    except Exception:
        log.exception("indexing %s failed", url)


# ---------- endpoints ----------

@app.get("/health")
def health() -> dict:
    with_conn(lambda c: c.execute("SELECT 1").fetchone())
    return {"status": "ok"}


@app.get("/repos", response_model=list[RepoOut])
def list_repos() -> list[dict]:
    return with_conn(lambda c: c.cursor(row_factory=dict_row).execute(
        REPO_SELECT + " ORDER BY r.id", (settings.stale_after_minutes,)
    ).fetchall())


@app.get("/repos/{repo_id}", response_model=RepoOut)
def get_repo(repo_id: int) -> dict:
    row = with_conn(lambda c: _one(c, " WHERE r.id = %s", (repo_id,)))
    if row is None:
        raise HTTPException(status_code=404, detail="repo not found")
    return row


@app.post("/repos", response_model=IndexResponse, status_code=202)
def create_repo(req: IndexRequest, background: BackgroundTasks, response: Response) -> dict:
    try:
        owner, name = parse_github_url(req.url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    url = f"https://github.com/{owner}/{name}"

    try:
        head = remote_head_sha(owner, name)
    except RepoNotFound:
        raise HTTPException(status_code=404, detail="repository not found or not public")
    except GitHubUnavailable as e:
        log.warning("git ls-remote failed for %s: %s", url, e)
        raise HTTPException(status_code=503, detail=f"could not reach GitHub, try again: {str(e)[:200]}")
    if head is None:
        raise HTTPException(status_code=400, detail="repository has no commits")

    def claim(conn):
        existing = _one(conn, " WHERE r.url = %s", (url,))
        if (existing and existing["status"] == "ready"
                and existing["commit_sha"] == head and not req.force):
            return existing, False, "already indexed at latest commit"
        conn.execute(
            "INSERT INTO repos (url, owner, name, status) VALUES (%s, %s, %s, 'pending') "
            "ON CONFLICT (url) DO NOTHING",
            (url, owner, name),
        )
        claimed = conn.execute(CLAIM_SQL, (url, settings.stale_after_minutes)).fetchone()
        repo = _one(conn, " WHERE r.url = %s", (url,))
        if claimed:
            return repo, True, "indexing started"
        return repo, False, "indexing already in progress"

    repo, started, reason = with_conn(claim, retries=0)   # writes: never retry
    if started:
        background.add_task(_run_indexing, url)
    else:
        response.status_code = 200
    return {"repo": repo, "started": started, "reason": reason}


@app.post("/repos/{repo_id}/ask", response_model=AskResponse)
def ask(repo_id: int, req: AskRequest) -> dict:
    repo = with_conn(lambda c: c.cursor(row_factory=dict_row).execute(
        "SELECT id, url, status, commit_sha FROM repos WHERE id = %s", (repo_id,)
    ).fetchone())
    if repo is None:
        raise HTTPException(status_code=404, detail="repo not found")
    if repo["status"] != "ready":
        raise HTTPException(status_code=409, detail=f"repo is not ready (status: {repo['status']})")

    try:
        return _answer(repo, req)
    except genai_errors.APIError as e:
        log.warning("Gemini failed for repo %s: %s", repo_id, e)
        raise HTTPException(status_code=503, detail="AI service unavailable, please try again")
    except ValidationError:
        log.exception("Gemini returned a malformed answer for repo %s", repo_id)
        raise HTTPException(status_code=502, detail="AI service returned a malformed answer")


@observe(name="ask", capture_input=False, capture_output=False)
def _answer(repo: dict, req: AskRequest) -> dict:
    """Root of the trace: retrieve -> explain, with every Gemini call nested inside."""
    repo_id, repo_url, sha = repo["id"], repo["url"], repo["commit_sha"]
    trace_request(
        name="ask",
        tags=[req.mode],
        metadata={"repo_id": repo_id, "repo_url": repo_url, "commit_sha": sha, "mode": req.mode},
        input={"question": req.question, "mode": req.mode, "k": req.k},
    )

    started = time.perf_counter()
    hits, info = with_conn(lambda c: retrieve(c, repo_id, req.question, req.mode, req.k))
    t = time.perf_counter()
    exp = explain(req.question, hits)
    info["timings_ms"]["answer"] = round(1000 * (time.perf_counter() - t))
    info["timings_ms"]["total"] = round(1000 * (time.perf_counter() - started))
    info["llm_usage"].append(exp.usage)

    citations = [
        {
            "source": c.source, "path": c.path, "start_line": c.start, "end_line": c.end,
            "valid": c.valid, "reason": c.reason,
            "url": github_line_url(repo_url, sha, c.path, c.start, c.end) if c.valid else None,
        }
        for c in exp.citations
    ]
    sources = [
        {
            "n": i, "path": h.path, "start_line": h.start_line, "end_line": h.end_line,
            "kind": h.kind, "symbol": h.symbol,
            "url": github_line_url(repo_url, sha, h.path, h.start_line, h.end_line),
        }
        for i, h in enumerate(hits, start=1)
    ]
    invalid = sum(1 for c in exp.citations if not c.valid)

    trace_request(output={
        "found": exp.found,
        "answer": exp.answer,
        "citations": len(citations),
        "invalid_citations": invalid,
        "timings_ms": info["timings_ms"],
    })
    return {
        "repo_id": repo_id,
        "question": req.question,
        "mode": req.mode,
        "found": exp.found,
        "answer": exp.answer,
        "citations": citations,
        "invalid_citations": invalid,
        "sources": sources,
        "timings_ms": info["timings_ms"],
        "llm_usage": info["llm_usage"],
        "trace_id": current_trace_id(),
    }