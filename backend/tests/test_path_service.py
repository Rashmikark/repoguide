import pytest

from backend.app.onboarding import path_service as ps

FACTS = {"repo_id": 1, "url": "https://github.com/x/y", "commit_sha": "abc",
         "entry_points": [], "readme_path": "README.md"}


class FakeConn:
    def __init__(self, row):
        self.row = row

    def execute(self, sql, params):
        return self

    def fetchone(self):
        return self.row


def _no_call(*a, **k):
    raise AssertionError("should not be called")


def test_saved_plan_is_returned_without_gemini(monkeypatch):
    monkeypatch.setattr(ps, "get_saved", lambda *a: {"days": ["saved"], "planner_version": 1})
    monkeypatch.setattr(ps, "explain_path", _no_call)
    out = ps.build_path(object(), FACTS, 5, 2.0)
    assert out["cached"] is True and out["days"] == ["saved"]


def test_new_plan_is_built_explained_and_saved(monkeypatch):
    saved = {}
    monkeypatch.setattr(ps, "get_saved", lambda *a: None)
    monkeypatch.setattr(ps, "load_sizes", lambda conn, rid: {"README.md": 40})
    monkeypatch.setattr(ps, "explain_path", lambda conn, facts, plan: {**plan, "checks": {}})
    monkeypatch.setattr(ps, "save_plan",
                        lambda conn, rid, sha, days, minutes, plan: saved.update(
                            key=(rid, sha, days, minutes), plan=plan))
    out = ps.build_path(object(), FACTS, 3, 1.5)
    assert out["cached"] is False
    assert saved["key"] == (1, "abc", 3, 90)                 # 1.5 h stored as 90 minutes
    assert saved["plan"]["planner_version"] == ps.PLANNER_VERSION
    assert "cached" not in saved["plan"]                     # the flag is not stored


def test_no_commit_means_no_cache(monkeypatch):
    monkeypatch.setattr(ps, "get_saved", _no_call)
    monkeypatch.setattr(ps, "save_plan", _no_call)
    monkeypatch.setattr(ps, "load_sizes", lambda conn, rid: {"README.md": 40})
    monkeypatch.setattr(ps, "explain_path", lambda conn, facts, plan: plan)
    out = ps.build_path(object(), dict(FACTS, commit_sha=None), 3, 1.0)
    assert out["cached"] is False


def test_bad_days_rejected(monkeypatch):
    monkeypatch.setattr(ps, "get_saved", lambda *a: None)
    monkeypatch.setattr(ps, "load_sizes", lambda conn, rid: {})
    with pytest.raises(ValueError):
        ps.build_path(object(), FACTS, 0, 2.0)


def test_old_planner_version_is_ignored():
    assert ps.get_saved(FakeConn(({"planner_version": 0},)), 1, "abc", 5, 120) is None
    assert ps.get_saved(FakeConn(None), 1, "abc", 5, 120) is None
    plan = {"planner_version": ps.PLANNER_VERSION, "days": []}
    assert ps.get_saved(FakeConn((plan,)), 1, "abc", 5, 120) == plan