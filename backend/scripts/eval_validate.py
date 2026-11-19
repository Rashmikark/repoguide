"""Validate eval/questions.jsonl. Usage:
    python -m backend.scripts.eval_validate           # check everything
    python -m backend.scripts.eval_validate --show    # also print the code at each gold span
"""
import json
import sys
from collections import Counter
from pathlib import Path

QUESTIONS = Path("eval/questions.jsonl")
REQUIRED = {"id", "repo", "category", "question", "answerable", "gold", "key_points"}
CATEGORIES = {"locate", "how", "usage", "docs", "negative"}


def repo_dir(repo: str) -> Path:
    owner, name = repo.split("/")
    return Path("data/repos") / f"{owner}__{name}"


def main() -> int:
    show = "--show" in sys.argv
    errors: list[str] = []
    ids: set[str] = set()
    per_repo: Counter = Counter()
    per_cat: Counter = Counter()

    if not QUESTIONS.exists():
        print(f"{QUESTIONS} not found")
        return 1

    for n, line in enumerate(QUESTIONS.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            q = json.loads(line)
        except json.JSONDecodeError as e:
            errors.append(f"line {n}: invalid JSON ({e})")
            continue

        missing = REQUIRED - q.keys()
        if missing:
            errors.append(f"line {n}: missing fields {sorted(missing)}")
            continue
        qid = q["id"]
        if qid in ids:
            errors.append(f"{qid}: duplicate id")
        ids.add(qid)
        if q["category"] not in CATEGORIES:
            errors.append(f"{qid}: unknown category {q['category']!r}")
        if not q["question"].strip():
            errors.append(f"{qid}: empty question")

        root = repo_dir(q["repo"])
        if not root.exists():
            errors.append(f"{qid}: repo not cloned at {root}")
            continue

        if q["answerable"]:
            if not q["gold"]:
                errors.append(f"{qid}: answerable but no gold spans")
            if not q["key_points"]:
                errors.append(f"{qid}: answerable but no key_points")
        else:
            if q["gold"]:
                errors.append(f"{qid}: not answerable but has gold spans")
            if q["category"] != "negative":
                errors.append(f"{qid}: not answerable must use category 'negative'")

        for g in q["gold"]:
            path = root / g["path"]
            if not path.is_file():
                errors.append(f"{qid}: gold path not found: {g['path']}")
                continue
            lines = path.read_text(encoding="utf-8").split("\n")
            if not 1 <= g["start"] <= g["end"] <= len(lines):
                errors.append(f"{qid}: lines {g['start']}-{g['end']} outside 1-{len(lines)} in {g['path']}")
                continue
            if show:
                print(f"\n{qid}  {g['path']}:L{g['start']}-{g['end']}  ({q['question']})")
                for i in range(g["start"], min(g["end"], g["start"] + 7) + 1):
                    print(f"  {i:>5}| {lines[i - 1]}")

        per_repo[q["repo"]] += 1
        per_cat[q["category"]] += 1

    print(f"\n{sum(per_repo.values())} questions")
    for repo, c in sorted(per_repo.items()):
        print(f"  {repo}: {c}")
    print("by category:", dict(per_cat))
    if errors:
        print(f"\n{len(errors)} ERROR(S):")
        for e in errors:
            print("  -", e)
        return 1
    print("\nOK: no errors")
    return 0


if __name__ == "__main__":
    sys.exit(main())