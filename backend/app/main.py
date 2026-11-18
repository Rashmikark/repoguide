from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, HTTPException
from psycopg.rows import dict_row
from pydantic import BaseModel

from backend.app.db import pool, with_conn


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
    created_at: datetime
    indexed_at: datetime | None


REPO_COLUMNS = "id, url, status, error, commit_sha, file_count, chunk_count, created_at, indexed_at"


@app.get("/health")
def health() -> dict:
    with_conn(lambda c: c.execute("SELECT 1").fetchone())
    return {"status": "ok"}


@app.get("/repos", response_model=list[RepoOut])
def list_repos() -> list[dict]:
    return with_conn(lambda c: c.cursor(row_factory=dict_row).execute(
        f"SELECT {REPO_COLUMNS} FROM repos ORDER BY id"
    ).fetchall())


@app.get("/repos/{repo_id}", response_model=RepoOut)
def get_repo(repo_id: int) -> dict:
    row = with_conn(lambda c: c.cursor(row_factory=dict_row).execute(
        f"SELECT {REPO_COLUMNS} FROM repos WHERE id = %s", (repo_id,)
    ).fetchone())
    if row is None:
        raise HTTPException(status_code=404, detail="repo not found")
    return row