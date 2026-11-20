"""Show which chunks a quiz would be built from.  python -m backend.scripts.show_quiz_sources <repo_id> [n]"""
import argparse

import psycopg

from backend.app.config import settings
from backend.app.onboarding.facts import load_repo_facts
from backend.app.onboarding.path import order_files
from backend.app.onboarding.quiz_sources import (load_candidates, load_reference_counts,
                                                 pick_quiz_sources)
from backend.app.onboarding.sizes import load_sizes


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("repo_id", type=int)
    p.add_argument("n", type=int, nargs="?", default=5)
    a = p.parse_args()

    with psycopg.connect(settings.database_url) as conn:
        facts = load_repo_facts(conn, a.repo_id)
        sizes = load_sizes(conn, a.repo_id)
        candidates = load_candidates(conn, a.repo_id)
        refs = load_reference_counts(conn, a.repo_id)

    order = order_files(list(sizes), sizes, facts["entry_points"], facts["readme_path"])
    preferred = [it.path for it in order if it.group in ("entry", "core")]
    picked = pick_quiz_sources(candidates, preferred, a.n, refs)

    print(f"{facts['url']}  function/class chunks: {len(candidates)}  picked: {len(picked)}")
    for c in picked:
        print(f"  {c['path']} L{c['start']}-{c['end']}  {c['kind']} {c['symbol']}  "
              f"({c['end'] - c['start'] + 1} lines, refs {c['refs']})")


if __name__ == "__main__":
    main()