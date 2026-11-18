import sys
import time

import psycopg

from backend.app.config import settings
from backend.app.ingest.chunker import chunk_file
from backend.app.ingest.repo_loader import load_repo
from backend.app.ingest.store import embed_missing, mark_failed, mark_ready, save_repo

start = time.perf_counter()
repo = load_repo(sys.argv[1])
file_chunks = [(f, chunk_file(f)) for f in repo.files]
total = sum(len(chunks) for _, chunks in file_chunks)
print(f"{repo.owner}/{repo.name} @ {repo.commit_sha[:10]}: "
      f"{len(repo.files)} files, {total} chunks")

with psycopg.connect(settings.database_url) as conn:
    repo_id = save_repo(conn, repo, file_chunks)
    print(f"saved to database (repo_id={repo_id}), embedding...")
    try:
        embed_missing(conn, repo_id)
        mark_ready(conn, repo_id)
    except Exception as e:
        mark_failed(conn, repo_id, str(e))
        raise

print(f"done in {time.perf_counter() - start:.1f}s")