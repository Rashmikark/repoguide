"""Show the reading plan for one repo.  python -m backend.scripts.show_path <repo_id> [days] [hours]"""
import argparse

import psycopg

from backend.app.config import settings
from backend.app.onboarding.facts import load_repo_facts
from backend.app.onboarding.path import plan_reading
from backend.app.onboarding.sizes import load_sizes


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("repo_id", type=int)
    p.add_argument("days", type=int, nargs="?", default=5)
    p.add_argument("hours", type=float, nargs="?", default=2.0)
    a = p.parse_args()

    with psycopg.connect(settings.database_url) as conn:
        facts = load_repo_facts(conn, a.repo_id)
        sizes = load_sizes(conn, a.repo_id)

    # File list comes from sizes (every indexed file), not facts["files"] (capped at 300).
    plan = plan_reading(list(sizes), sizes, facts["entry_points"], facts["readme_path"],
                        a.days, a.hours)

    print(f"{facts['url']}  files in index: {len(sizes)}  ({a.days} days x {a.hours} h)")
    for d in plan["days"]:
        flag = "  OVER BUDGET" if d["over_budget"] else ""
        print(f"\nDay {d['day']}: {d['minutes']} min{flag}")
        for it in d["items"]:
            print(f"  {it['minutes']:>4} min  {it['group']:<6} {it['path']} ({it['lines']} lines){'  SKIM' if it['skim'] else ''}")
    planned = sum(len(d["items"]) for d in plan["days"])
    skipped = plan["skipped"]
    print(f"\nplanned files: {planned}   skipped (no time left): {len(skipped)}")
    for s in skipped[:10]:
        print(f"  skipped: {s}")
    if len(skipped) > 10:
        print(f"  ... and {len(skipped) - 10} more")
    print(f"planned {plan['planned_minutes']} of {plan['budget_minutes']:.0f} budget minutes")
    print(f"assumptions: {plan['assumptions']}")


if __name__ == "__main__":
    main()