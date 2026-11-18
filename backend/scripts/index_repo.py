import argparse
import sys
import time

import psycopg

from backend.app.config import settings
from backend.app.ingest import embedder
from backend.app.ingest.chunker import chunk_file
from backend.app.ingest.repo_loader import load_repo, parse_github_url, remote_head_sha
from backend.app.ingest.store import embed_missing, mark_failed, mark_ready, save_repo

parser = argparse.ArgumentParser(description="Index a public GitHub repo")
parser.add_argument("url")
parser.add_argument("--force", action="store_true", help="re-index even if unchanged")
args = parser.parse_args()

owner, name = parse_github_url(args.url)
url = f"https://github.com/{owner}/{name}"

with psycopg.connect(settings.database_url) as conn:
    row = conn.execute(
        "SELECT status, commit_sha FROM repos WHERE url = %s", (url,)
    ).fetchone()
    if row and row[0] == "ready" and not args.force:
        head = remote_head_sha(owner, name)
        if head == row[1]:
            print(f"{owner}/{name} already indexed at {head[:10]}; skipping "
                  "(use --force to re-index)")
            sys.exit(0)

start = time.perf_counter()
repo = load_repo(args.url)
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

elapsed = time.perf_counter() - start
waited = embedder.wait_seconds
print(f"done in {elapsed:.1f}s  (rate-limit waiting {waited:.1f}s, work {elapsed - waited:.1f}s)")