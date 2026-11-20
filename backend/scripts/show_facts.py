import json
import sys

import psycopg

from backend.app.config import settings
from backend.app.onboarding.facts import load_repo_facts

repo_id = int(sys.argv[1])
with psycopg.connect(settings.database_url) as conn:
    facts = load_repo_facts(conn, repo_id)

readme = facts.pop("readme")
files = facts.pop("files")
print(json.dumps(facts, indent=2))
print(f"\nfiles listed: {len(files)} (first 5: {files[:5]})")
print(f"README: {len(readme.splitlines())} lines; first 6:")
for line in readme.splitlines()[:6]:
    print("   |", line)