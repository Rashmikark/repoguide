"""Good first issues: fetch real open issues from GitHub, keep beginner-labelled ones, rank them.
A second tier lists other actionable open issues, clearly marked as NOT labelled for beginners.
Nothing is invented: if no issue qualifies, the lists are empty and the counts say why.
Issue text is untrusted data - stored and shown, never used as instructions."""
import httpx

from backend.app.ingest.repo_loader import GitHubUnavailable, RepoNotFound

API = "https://api.github.com"
PER_PAGE = 100
MAX_ISSUES = 5
BODY_CHARS = 300
NOTE = f"Only the {PER_PAGE} most recently created open issues are checked."

# Matched as substrings of the normalized label name ("Good-First-Issue" -> "good first issue").
LABEL_SCORES = {
    "good first issue": 3, "beginner": 3, "first timers only": 3,
    "easy": 2, "help wanted": 2,
    "documentation": 1, "docs": 1,
}
NOT_ACTIONABLE = ("question", "duplicate", "wontfix", "won't fix", "wont fix", "invalid", "discussion")


class GitHubRateLimited(Exception):
    pass


def _norm(label: str) -> str:
    return label.lower().replace("-", " ").replace("_", " ").strip()


def label_score(names: list[str]) -> int:
    return max((s for n in names for k, s in LABEL_SCORES.items() if k in _norm(n)), default=0)


def not_actionable(names: list[str]) -> bool:
    return any(k in _norm(n) for n in names for k in NOT_ACTIONABLE)


def fetch_open_issues(owner: str, name: str, client: httpx.Client | None = None) -> list[dict]:
    url = f"{API}/repos/{owner}/{name}/issues"
    params = {"state": "open", "per_page": PER_PAGE, "sort": "created", "direction": "desc"}
    headers = {"Accept": "application/vnd.github+json",
               "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "repoguide"}
    own = client is None
    client = client or httpx.Client(timeout=15)
    try:
        r = client.get(url, params=params, headers=headers)
    except httpx.HTTPError as e:
        raise GitHubUnavailable(f"GitHub API unreachable: {e}") from e
    finally:
        if own:
            client.close()
    if r.status_code == 404:
        raise RepoNotFound(f"GitHub repo {owner}/{name} not found")
    if r.status_code in (403, 429) and r.headers.get("x-ratelimit-remaining") == "0":
        raise GitHubRateLimited(
            f"GitHub API rate limit reached; resets at unix time {r.headers.get('x-ratelimit-reset')}")
    if r.status_code != 200:
        raise GitHubUnavailable(f"GitHub API returned {r.status_code}")
    return r.json()


def _entry(it: dict, names: list[str], score: int) -> dict:
    return {
        "number": it["number"],
        "title": it["title"],
        "url": it["html_url"],
        "labels": names,
        "score": score,
        "comments": it.get("comments", 0),
        "created_at": it.get("created_at", ""),
        "body": (it.get("body") or "")[:BODY_CHARS],
    }


def pick_issues(raw: list[dict], limit: int = MAX_ISSUES) -> dict:
    checks = {"open_items_checked": len(raw), "pull_requests": 0, "assigned": 0,
              "locked": 0, "not_actionable": 0, "no_beginner_label": 0}
    picked, others = [], []
    for it in raw:
        if "pull_request" in it:
            checks["pull_requests"] += 1
            continue
        if it.get("assignee") or it.get("assignees"):
            checks["assigned"] += 1
            continue
        if it.get("locked"):
            checks["locked"] += 1
            continue
        names = [lb["name"] if isinstance(lb, dict) else str(lb) for lb in it.get("labels", [])]
        if not_actionable(names):
            checks["not_actionable"] += 1
            continue
        score = label_score(names)
        if score == 0:
            checks["no_beginner_label"] += 1
            others.append(_entry(it, names, 0))
            continue
        picked.append(_entry(it, names, score))

    for lst in (picked, others):
        lst.sort(key=lambda p: p["created_at"], reverse=True)   # newest first...
    picked.sort(key=lambda p: (-p["score"], p["comments"]))     # ...then score, then fewest comments
    others.sort(key=lambda p: p["comments"])                     # ...then fewest comments
    return {"issues": picked[:limit], "candidates": len(picked),
            "other_open_issues": others[:limit],
            "checks": checks, "note": NOTE}