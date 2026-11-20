import httpx
import pytest

from backend.app.ingest.repo_loader import GitHubUnavailable, RepoNotFound
from backend.app.onboarding.issues import GitHubRateLimited, fetch_open_issues, label_score, pick_issues


def _issue(n, labels=(), comments=0, created="2026-01-01T00:00:00Z", **extra):
    return {"number": n, "title": f"Issue {n}", "html_url": f"https://github.com/x/y/issues/{n}",
            "labels": [{"name": lb} for lb in labels], "comments": comments,
            "created_at": created, "body": "text", **extra}


def test_prs_assigned_locked_and_unlabelled_are_skipped_and_counted():
    raw = [
        _issue(1, ["good first issue"]),
        _issue(2, ["good first issue"], pull_request={"url": "x"}),
        _issue(3, ["good first issue"], assignee={"login": "a"}),
        _issue(4, ["good first issue"], locked=True),
        _issue(5, ["bug"]),
    ]
    out = pick_issues(raw)
    assert [i["number"] for i in out["issues"]] == [1]
    assert out["checks"] == {"open_items_checked": 5, "pull_requests": 1, "assigned": 1,
                             "locked": 1, "no_beginner_label": 1}


def test_ranking_score_then_comments_then_newest():
    raw = [
        _issue(1, ["help wanted"], comments=0),
        _issue(2, ["good first issue"], comments=5),
        _issue(3, ["good first issue"], comments=1, created="2026-01-01T00:00:00Z"),
        _issue(4, ["good first issue"], comments=1, created="2026-03-01T00:00:00Z"),
    ]
    assert [i["number"] for i in pick_issues(raw)["issues"]] == [4, 3, 2, 1]


def test_label_names_matched_loosely():
    assert label_score(["Good-First-Issue"]) == 3
    assert label_score(["status: good first issue"]) == 3
    assert label_score(["Help Wanted", "docs"]) == 2
    assert label_score(["bug", "enhancement"]) == 0


def test_empty_when_nothing_qualifies():
    out = pick_issues([_issue(1, ["bug"])])
    assert out["issues"] == [] and out["candidates"] == 0 and "most recently" in out["note"]


def _client(status, json_body=None, headers=None, seen=None):
    def handler(request):
        if seen is not None:
            seen.append(request)
        return httpx.Response(status, json=json_body if json_body is not None else {}, headers=headers or {})
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_fetch_ok_asks_for_open_issues():
    seen = []
    data = fetch_open_issues("x", "y", client=_client(200, [_issue(1)], seen=seen))
    assert data[0]["number"] == 1
    assert seen[0].url.path == "/repos/x/y/issues" and seen[0].url.params["state"] == "open"


def test_fetch_404_is_repo_not_found():
    with pytest.raises(RepoNotFound):
        fetch_open_issues("x", "y", client=_client(404))


def test_fetch_rate_limit_is_clear_error():
    headers = {"x-ratelimit-remaining": "0", "x-ratelimit-reset": "1790000000"}
    with pytest.raises(GitHubRateLimited):
        fetch_open_issues("x", "y", client=_client(403, headers=headers))


def test_fetch_server_error_is_unavailable():
    with pytest.raises(GitHubUnavailable):
        fetch_open_issues("x", "y", client=_client(500))