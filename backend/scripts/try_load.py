import sys
from collections import Counter

from backend.app.ingest.repo_loader import load_repo

repo = load_repo(sys.argv[1])
print(f"{repo.owner}/{repo.name} @ {repo.commit_sha[:10]}")
print("kept files:", len(repo.files))
print("by language:", dict(Counter(f.language for f in repo.files)))
print("skipped:", repo.skipped)
print("largest kept files:")
for f in sorted(repo.files, key=lambda f: f.size_bytes, reverse=True)[:5]:
    print(f"  {f.size_bytes:>7}  {f.path}")