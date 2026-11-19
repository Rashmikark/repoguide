import time

import psycopg

from backend.app.config import settings
from backend.app.ingest import embedder
from backend.app.ingest.chunker import chunk_file
from backend.app.ingest.repo_loader import load_repo, parse_github_url
from backend.app.ingest.store import embed_missing, mark_ready, save_repo


def index_repo(url: str) -> dict:
    """Clone, chunk, store and embed one repo. Marks the repo failed on any error."""
    start = time.perf_counter()
    waited_before = embedder.wait_seconds
    try:
        repo = load_repo(url)
        file_chunks = [(f, chunk_file(f)) for f in repo.files]
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
        "files": len(repo.files),
        "chunks": sum(len(c) for _, c in file_chunks),
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