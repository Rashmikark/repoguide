"""Show good first issues for one indexed repo.  python -m backend.scripts.show_issues <repo_id>"""
import argparse
import json

import psycopg

from backend.app.config import settings
from backend.app.onboarding.issues import fetch_open_issues, pick_issues


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("repo_id", type=int)
    a = p.parse_args()

    with psycopg.connect(settings.database_url) as conn:
        row = conn.execute("SELECT owner, name FROM repos WHERE id = %s", (a.repo_id,)).fetchone()
    if row is None:
        raise SystemExit(f"repo {a.repo_id} not found")

    out = pick_issues(fetch_open_issues(row[0], row[1]))
    print(f"{row[0]}/{row[1]}")
    print(json.dumps({k: out[k] for k in ("candidates", "checks", "note")}, indent=2))
    for i in out["issues"]:
        print(f"\n#{i['number']}  score {i['score']}  comments {i['comments']}  {i['created_at'][:10]}")
        print(f"  {i['title']}")
        print(f"  labels: {i['labels']}")
        print(f"  {i['url']}")


if __name__ == "__main__":
    main()