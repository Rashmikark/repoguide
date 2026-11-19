import argparse
import sys

import psycopg

from backend.app.config import settings
from backend.app.ingest.indexer import index_repo
from backend.app.ingest.repo_loader import parse_github_url, remote_head_sha

parser = argparse.ArgumentParser(description="Index a public GitHub repo")
parser.add_argument("url")
parser.add_argument("--force", action="store_true", help="re-index even if unchanged")
args = parser.parse_args()

owner, name = parse_github_url(args.url)
url = f"https://github.com/{owner}/{name}"

with psycopg.connect(settings.database_url) as conn:
    row = conn.execute("SELECT status, commit_sha FROM repos WHERE url = %s", (url,)).fetchone()
if row and row[0] == "ready" and not args.force:
    head = remote_head_sha(owner, name)
    if head == row[1]:
        sys.exit(f"{owner}/{name} already indexed at {head[:10]}; skipping (use --force)")

result = index_repo(args.url)
print(f"done: {result}")