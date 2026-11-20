"""Pick the code chunks a quiz is built from. Code decides; Gemini only writes questions later.
Rules: real function/class chunks of 8-120 lines, not tests/docs/noise.
Files: reading-plan order. Within a file: public symbols first, then MOST REFERENCED first
(in how many chunks the name appears), size only breaks ties.
Picking: one chunk per file per round over PUBLIC modules until they run out; private modules
(_json.py, _native.py) only after that. A name already picked is never picked twice."""
import re
from collections import Counter
from pathlib import PurePosixPath

from backend.app.onboarding.facts import is_test_path
from backend.app.onboarding.issue_code import is_doc, is_noise

QUIZ_KINDS = ("function", "class")
MIN_LINES, MAX_LINES = 8, 120
DEFAULT_QUESTIONS = 5
GENERIC_METHODS = {"constructor", "__init__", "__new__", "__call__", "__repr__", "__str__"}
TOKEN = re.compile(r"[A-Za-z_$][A-Za-z0-9_$]*")

SOURCES_SQL = """
SELECT id, path, start_line, end_line, kind, symbol, content
FROM chunks
WHERE repo_id = %s AND kind = ANY(%s)
ORDER BY path, start_line
"""

CONTENT_SQL = "SELECT content FROM chunks WHERE repo_id = %s"


def load_candidates(conn, repo_id: int) -> list[dict]:
    rows = conn.execute(SOURCES_SQL, (repo_id, list(QUIZ_KINDS))).fetchall()
    return [{"chunk_id": r[0], "path": r[1], "start": r[2], "end": r[3],
             "kind": r[4], "symbol": r[5], "content": r[6]} for r in rows]


def doc_freq(texts) -> Counter:
    """In how many texts does each name appear? (each text counts once per name)"""
    freq: Counter = Counter()
    for t in texts:
        freq.update(set(TOKEN.findall(t)))
    return freq


def load_reference_counts(conn, repo_id: int) -> Counter:
    return doc_freq(r[0] for r in conn.execute(CONTENT_SQL, (repo_id,)).fetchall())


def ref_name(symbol: str | None) -> str:
    if not symbol:
        return ""
    parts = symbol.split(".")
    last = parts[-1].lstrip("#")
    if last in GENERIC_METHODS and len(parts) > 1:
        return parts[-2]
    return last


def _private(symbol: str | None) -> bool:
    if not symbol:
        return True
    last = symbol.split(".")[-1]
    return last.startswith("_") or last.startswith("#")


def _private_module(path: str) -> bool:
    stem = PurePosixPath(path).stem
    return stem.startswith("_") and not stem.startswith("__")


def usable(c: dict) -> bool:
    lines = c["end"] - c["start"] + 1
    return (c["kind"] in QUIZ_KINDS
            and MIN_LINES <= lines <= MAX_LINES
            and not is_test_path(c["path"])
            and not is_doc(c["path"])
            and not is_noise(c["path"]))


def _round_robin(queues: list[list[dict]], n: int, picked: list[dict], used: set[str],
                 refs: Counter) -> None:
    """One chunk per file per round; skip names already used; stop at n or when empty."""
    while len(picked) < n and any(queues):
        for q in queues:
            while q:
                c = q.pop(0)
                name = ref_name(c["symbol"])
                if name and name in used:
                    continue                       # same concept already in the quiz
                used.add(name)
                picked.append({**c, "refs": refs.get(name, 0)})
                break
            if len(picked) >= n:
                return


def pick_quiz_sources(candidates: list[dict], preferred_paths: list[str],
                      n: int = DEFAULT_QUESTIONS, refs: Counter | None = None) -> list[dict]:
    rank = {p: i for i, p in enumerate(preferred_paths)}
    refs = refs or Counter()

    def key(c):
        return (rank.get(c["path"], len(rank)), c["path"],
                _private(c["symbol"]), -refs.get(ref_name(c["symbol"]), 0),
                -(c["end"] - c["start"]), c["start"])

    pool = sorted((c for c in candidates if usable(c)), key=key)
    public: dict[str, list[dict]] = {}
    private: dict[str, list[dict]] = {}
    for c in pool:                                   # dicts keep the sorted file order
        (private if _private_module(c["path"]) else public).setdefault(c["path"], []).append(c)

    picked: list[dict] = []
    used: set[str] = set()
    _round_robin([list(q) for q in public.values()], n, picked, used, refs)
    _round_robin([list(q) for q in private.values()], n, picked, used, refs)
    return picked