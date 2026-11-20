"""Generate a quiz for one repo and print it WITH the answer key (dev only).
python -m backend.scripts.show_quiz <repo_id> [n]"""
import argparse
import json

import psycopg

from backend.app.config import settings
from backend.app.onboarding.facts import load_repo_facts
from backend.app.onboarding.path import order_files
from backend.app.onboarding.quiz_gen import make_quiz
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
    sources = pick_quiz_sources(candidates, preferred, a.n, refs)
    quiz = make_quiz(facts, sources)

    print(facts["url"])
    for q in quiz["questions"]:
        print(f"\n{q['id']}. {q['question']}")
        for i, opt in enumerate(q["options"]):
            print(f"   {'*' if i == q['correct'] else ' '} {'ABCD'[i]}) {opt}")
        print(f"   why: {q['explanation']}")
        print(f"   proof: {q['path']} L{q['start']}-{q['end']}  {q['url']}")
    print(f"\nchecks: {json.dumps(quiz['checks'])}")
    print(f"usage: {quiz['usage']}")


if __name__ == "__main__":
    main()