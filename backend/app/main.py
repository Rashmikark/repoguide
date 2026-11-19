import logging
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import BackgroundTasks, FastAPI, HTTPException, Response
from psycopg.rows import dict_row
from pydantic import BaseModel

from backend.app.config import settings
from backend.app.db import pool, with_conn
from backend.app.ingest.indexer import index_repo
from backend.app.ingest.repo_loader import (
    GitHubUnavailable,
    RepoNotFound,
    parse_github_url,
    remote_head_sha,
)

log = logging.getLogger("uvicorn.error")


@asynccontextmanager
async def lifespan(app: FastAPI):
    pool.open(wait=True, timeout=30)
    yield
    pool.close()


app = FastAPI(title="RepoGuide API", version="0.1.0", lifespan=lifespan)


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