"""Show good first issues for one indexed repo.  python -m backend.scripts.show_issues <repo_id>"""
import argparse
import json

import psycopg

from backend.app.config import settings
from backend.app.onboarding.issue_code import attach_related
from backend.app.onboarding.issues import fetch_open_issues, pick_issues


def _show(title: str, items: list[dict]) -> None:
    print(f"\n== {title}: {len(items)}")
    for i in items:
        print(f"\n#{i['number']}  score {i['score']}  comments {i['comments']}  {i['created_at'][:10]}")
        print(f"  {i['title']}")
        print(f"  labels: {i['labels']}")
        print(f"  {i['url']}")
        if not i["related"]:
            print("  possibly related code: (no keyword match)")
        for r in i["related"]:
            print(f"  possibly related: {r['path']} L{r['start']}-{r['end']} "
                  f"{r['kind']} {r['symbol'] or ''}")
            print(f"      {r['url']}")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("repo_id", type=int)
    a = p.parse_args()

    with psycopg.connect(settings.database_url) as conn:
        row = conn.execute("SELECT owner, name, url, commit_sha FROM repos WHERE id = %s",
                           (a.repo_id,)).fetchone()
        if row is None:
            raise SystemExit(f"repo {a.repo_id} not found")
        owner, name, url, sha = row
        picked = pick_issues(fetch_open_issues(owner, name))
        out = attach_related(conn, a.repo_id, url, sha, picked)

    print(f"{owner}/{name}")
    print(json.dumps({k: out[k] for k in ("candidates", "checks", "note", "related_note")}, indent=2))
    _show("Good first issues (beginner-labelled)", out["issues"])
    _show("Other open issues (NOT labelled for beginners)", out["other_open_issues"])


if __name__ == "__main__":
    main()