import time

import psycopg

from backend.app.config import settings
from backend.app.ingest import embedder
from backend.app.ingest.chunker import chunk_file
from backend.app.ingest.repo_loader import load_repo, parse_github_url, remote_head_sha
from backend.app.ingest.store import embed_missing, mark_ready, save_repo


def plan_index(stored_sha: str | None, total_chunks: int, embedded_chunks: int,
               head_sha: str | None) -> str:
    """'resume' if this exact commit is fully chunked but only partly embedded,
    otherwise 'full'. save_repo writes all chunks in one transaction, so existing
    chunks are always complete - only embeddings can be partial."""
    if (stored_sha is not None and stored_sha == head_sha
            and total_chunks > 0 and embedded_chunks < total_chunks):
        return "resume"
    return "full"


def _stored_state(url: str) -> tuple[int | None, str | None, int, int]:
    with psycopg.connect(settings.database_url) as conn:
        row = conn.execute(
            """
            SELECT r.id, r.commit_sha,
                   (SELECT count(*)           FROM chunks c WHERE c.repo_id = r.id),
                   (SELECT count(c.embedding) FROM chunks c WHERE c.repo_id = r.id)
            FROM repos r WHERE r.url = %s
            """,
            (url,),
        ).fetchone()
    return row if row else (None, None, 0, 0)


def index_repo(url: str) -> dict:
    """Clone, chunk, store and embed one repo - or resume missing embeddings.
    Marks the repo failed on any error."""
    start = time.perf_counter()
    waited_before = embedder.wait_seconds
    owner, name = parse_github_url(url)
    canonical = f"https://github.com/{owner}/{name}"
    files = chunks = None
    try:
        repo_id, stored_sha, total, embedded = _stored_state(canonical)
        plan = plan_index(stored_sha, total, embedded, remote_head_sha(owner, name))

        if plan == "resume":
            with psycopg.connect(settings.database_url) as conn:
                conn.execute(
                    "UPDATE repos SET status = 'indexing', error = NULL, heartbeat_at = now() "
                    "WHERE id = %s",
                    (repo_id,),
                )
                conn.commit()
                embed_missing(conn, repo_id)
                mark_ready(conn, repo_id)
        else:
            repo = load_repo(url)
            file_chunks = [(f, chunk_file(f)) for f in repo.files]
            files = len(repo.files)
            chunks = sum(len(c) for _, c in file_chunks)
            with psycopg.connect(settings.database_url) as conn:
                repo_id = save_repo(conn, repo, file_chunks)
                embed_missing(conn, repo_id)
                mark_ready(conn, repo_id)
    except Exception as e:
        _mark_failed(url, e)
        raise
    elapsed = time.perf_counter() - start
    waited = embedder.wait_seconds - waited_before
    return {
        "repo_id": repo_id,
        "plan": plan,
        "files": files,
        "chunks": chunks,
        "seconds": round(elapsed, 1),
        "rate_limit_wait_seconds": round(waited, 1),
    }


def _mark_failed(url: str, error: Exception) -> None:
    """Best effort. If even this fails, the heartbeat marks the job as stalled."""
    try:
        owner, name = parse_github_url(url)
        with psycopg.connect(settings.database_url) as conn:
            conn.execute(
                "UPDATE repos SET status = 'failed', error = %s WHERE url = %s",
                (f"{type(error).__name__}: {error}"[:1000], f"https://github.com/{owner}/{name}"),
            )
    except Exception:
        pass