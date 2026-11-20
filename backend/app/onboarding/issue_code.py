"""Possibly related code for each issue: keyword search on the issue TITLE.
A starting point, not a claim about where the fix is. No match -> empty list.
Keyword only: no embeddings needed, and titles are full of identifiers.
Noise files (changelog, license, config, dot-folders) are skipped - same lists as the
planner - and code files are ranked before docs, keeping search order within each group."""
from pathlib import PurePosixPath

from backend.app.links import github_line_url
from backend.app.onboarding.path import CONFIG_ENDINGS, CONFIG_NAMES, DOC_SUFFIXES, SKIP_STEMS
from backend.app.retrieval.keyword_search import keyword_search

SEARCH_HITS = 20      # ask for more chunks than we show (filtering removes some)...
RELATED_FILES = 3     # ...then keep the top 3 DIFFERENT files


def is_noise(path: str) -> bool:
    p = PurePosixPath(path)
    name = p.name.lower()
    return (any(part.startswith(".") for part in p.parts)
            or p.stem.lower() in SKIP_STEMS
            or name in CONFIG_NAMES
            or name.endswith(CONFIG_ENDINGS))


def is_doc(path: str) -> bool:
    return PurePosixPath(path).suffix.lower() in DOC_SUFFIXES


def related_code(conn, repo_id: int, title: str, repo_url: str, commit_sha: str,
                 search=keyword_search) -> list[dict]:
    candidates, seen = [], set()
    for h in search(conn, repo_id, title, k=SEARCH_HITS):
        if h.path in seen or is_noise(h.path):
            continue
        seen.add(h.path)
        candidates.append(h)
    candidates.sort(key=lambda h: is_doc(h.path))     # stable: code first, search order kept
    return [{
        "path": h.path, "start": h.start_line, "end": h.end_line,
        "kind": h.kind, "symbol": h.symbol,
        "url": github_line_url(repo_url, commit_sha, h.path, h.start_line, h.end_line),
    } for h in candidates[:RELATED_FILES]]


def attach_related(conn, repo_id: int, repo_url: str, commit_sha: str, picked: dict,
                   search=keyword_search) -> dict:
    """Adds 'related' to every issue in both tiers. Returns a new dict."""
    def add(items):
        return [{**i, "related": related_code(conn, repo_id, i["title"], repo_url, commit_sha, search)}
                for i in items]
    return {**picked, "issues": add(picked["issues"]),
            "other_open_issues": add(picked["other_open_issues"]),
            "related_note": "Possibly related code, found by keyword search on the issue title "
                            "(code files ranked before docs)."}