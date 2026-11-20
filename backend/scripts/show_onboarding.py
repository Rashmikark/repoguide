"""Run the onboarding graph on one repo.  python -m backend.scripts.show_onboarding <repo_id> [days] [hours]"""
import argparse
import json

import psycopg

from backend.app.config import settings
from backend.app.onboarding.graph import build_graph


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("repo_id", type=int)
    p.add_argument("days", type=int, nargs="?", default=5)
    p.add_argument("hours", type=float, nargs="?", default=2.0)
    a = p.parse_args()

    with psycopg.connect(settings.database_url) as conn:
        out = build_graph().invoke(
            {"repo_id": a.repo_id, "days": a.days, "hours_per_day": a.hours, "errors": []},
            config={"configurable": {"conn": conn}},
        )

    facts = out.get("facts") or {}
    ov = out.get("overview") or {}
    print(json.dumps({
        "errors": out.get("errors", []),
        "facts": {k: facts.get(k) for k in ("url", "file_count", "languages", "entry_points", "readme_path")},
        "overview_summary": ov.get("summary"),
        "overview_invalid_citations": ov.get("invalid_citations"),
        "overview_unknown_paths": ov.get("unknown_paths"),
        "path_items": len(out.get("path", [])),
        "issues": len(out.get("issues", [])),
        "quiz": len(out.get("quiz", [])),
    }, indent=2))


if __name__ == "__main__":
    main()