from urllib.parse import quote


def github_line_url(repo_url: str, commit_sha: str, path: str, start: int, end: int) -> str:
    """Permalink to exact lines at the indexed commit, so it stays correct
    even after the file changes on the main branch."""
    anchor = f"#L{start}" if start == end else f"#L{start}-L{end}"
    return f"{repo_url}/blob/{commit_sha}/{quote(path)}{anchor}"