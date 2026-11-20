from datetime import datetime, timezone

import pytest

from backend.app.onboarding import issues_service as svc

FACTS = {"repo_id": 1, "url": "https://github.com/x/y", "commit_sha": "abc"}


class FakeConn:
    def __init__(self, row):
        self.row = row

    def execute(self, sql, params):
        return self

    def fetchone(self):
        return self.row


def _no_call(*a, **k):
    raise AssertionError("should not be called")


def test_saved_copy_returned_without_github(monkeypatch):
    monkeypatch.setattr(svc, "get_saved", lambda *a: {"issues": ["saved"], "issues_version": 1})
    out = svc.build_issues(object(), FACTS, fetch=_no_call)
    assert out["cached"] is True and out["issues"] == ["saved"]


def test_fresh_fetch_is_picked_related_and_saved(monkeypatch):
    saved, asked = {}, []
    monkeypatch.setattr(svc, "get_saved", lambda *a: None)
    monkeypatch.setattr(svc, "attach_related",
                        lambda conn, rid, url, sha, picked: {**picked, "related_note": "n"})
    monkeypatch.setattr(svc, "save_issues",
                        lambda conn, rid, sha, data: saved.update(key=(rid, sha), data=data))

    def fetch(owner, name):
        asked.append((owner, name))
        return []

    out = svc.build_issues(FakeConn(("x", "y")), FACTS, fetch=fetch)
    assert asked == [("x", "y")]                     # owner/name came from the repos table
    assert out["cached"] is False and out["issues"] == []
    assert saved["key"] == (1, "abc")
    assert saved["data"]["issues_version"] == svc.ISSUES_VERSION
    assert "cached" not in saved["data"]


def test_unknown_repo_raises(monkeypatch):
    monkeypatch.setattr(svc, "get_saved", lambda *a: None)
    with pytest.raises(LookupError):
        svc.build_issues(FakeConn(None), FACTS, fetch=_no_call)


def test_get_saved_checks_version():
    when = datetime(2026, 11, 20, tzinfo=timezone.utc)
    assert svc.get_saved(FakeConn(({"issues_version": 0}, when)), 1, "abc") is None
    assert svc.get_saved(FakeConn(None), 1, "abc") is None
    out = svc.get_saved(FakeConn(({"issues_version": svc.ISSUES_VERSION, "issues": []}, when)), 1, "abc")
    assert out["fetched_at"].startswith("2026-11-20")