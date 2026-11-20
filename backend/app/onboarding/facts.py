"""Repo facts for onboarding, built only from what is already in the database
(the cloned repo will not exist on disk in production)."""
from collections import Counter
from pathlib import PurePosixPath

import psycopg

CODE_SUFFIXES = {".py", ".js", ".jsx", ".ts", ".tsx"}
ENTRY_NAMES = {"__init__", "main", "index", "app", "cli", "server"}
TEST_DIRS = {"test", "tests", "__tests__", "test-d"}
README_LINES = 150
MAX_FILES_LISTED = 300


def is_test_path(path: str) -> bool:
    parts = PurePosixPath(path).parts
    name = parts[-1]
    return (any(p in TEST_DIRS for p in parts[:-1])
            or name.startswith("test_") or ".test." in name or ".spec." in name)


def top_level_summary(paths: list[str]) -> dict[str, int]:
    """{'src': 12, 'tests': 8, '(root)': 3} - biggest folders first."""
    counts = Counter(p.split("/")[0] if "/" in p else "(root)" for p in paths)
    return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))


def entry_point_guesses(paths: list[str], limit: int = 8) -> list[str]:
    """Non-test code files with entry-like names, closest to the root first."""
    named = [p for p in paths
             if PurePosixPath(p).suffix in CODE_SUFFIXES
             and PurePosixPath(p).stem in ENTRY_NAMES
             and not is_test_path(p)]
    return sorted(named, key=lambda p: (p.count("/"), p))[:limit]


def find_readme(paths: list[str]) -> str | None:
    root_readmes = [p for p in paths if "/" not in p and PurePosixPath(p).stem.lower() == "readme"]
    return sorted(root_readmes)[0] if root_readmes else None


def reconstruct_text(chunks: list[tuple[int, str]]) -> str:
    """Rebuild a file from (start_line, content) chunks. Overlapping windows are fine:
    each line number is kept once. Lines no chunk covered become empty."""
    lines: dict[int, str] = {}
    for start, content in chunks:
        for i, line in enumerate(content.split("\n")):
            lines.setdefault(start + i, line)
    if not lines:
        return ""
    return "\n".join(lines.get(n, "") for n in range(1, max(lines) + 1))


def load_repo_facts(conn: psycopg.Connection, repo_id: int) -> dict:
    repo = conn.execute(
        "SELECT url, commit_sha, status FROM repos WHERE id = %s", (repo_id,)
    ).fetchone()
    if repo is None:
        raise ValueError(f"repo {repo_id} not found")
    files = conn.execute(
        "SELECT path, language FROM files WHERE repo_id = %s ORDER BY path", (repo_id,)
    ).fetchall()
    paths = [f[0] for f in files]

    readme_path = find_readme(paths)
    readme = ""
    if readme_path:
        rows = conn.execute(
            "SELECT start_line, content FROM chunks WHERE repo_id = %s AND path = %s ORDER BY start_line",
            (repo_id, readme_path),
        ).fetchall()
        readme = "\n".join(reconstruct_text(rows).split("\n")[:README_LINES])

    return {
        "repo_id": repo_id,
        "url": repo[0],
        "commit_sha": repo[1],
        "status": repo[2],
        "file_count": len(paths),
        "languages": dict(Counter(f[1] for f in files).most_common()),
        "top_level": top_level_summary(paths),
        "test_files": sum(1 for p in paths if is_test_path(p)),
        "entry_points": entry_point_guesses(paths),
        "readme_path": readme_path,
        "readme": readme,
        "files": paths[:MAX_FILES_LISTED],
        "files_truncated": len(paths) > MAX_FILES_LISTED,
    }