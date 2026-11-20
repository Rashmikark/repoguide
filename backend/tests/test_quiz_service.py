import pytest

from backend.app.onboarding import quiz_service as qs

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


def _quiz(kept):
    return {"questions": [{"id": "q1"}] * kept, "usage": {},
            "checks": {"kept": kept, "dropped": {}, "missing_sources": 0}}


def test_saved_quiz_returned_without_gemini(monkeypatch):
    monkeypatch.setattr(qs, "get_saved", lambda *a: {"questions": ["saved"], "quiz_id": 7})
    monkeypatch.setattr(qs, "make_quiz", _no_call)
    out = qs.build_quiz(object(), FACTS, 5)
    assert out["cached"] is True and out["quiz_id"] == 7


def test_new_quiz_built_saved_and_given_an_id(monkeypatch):
    saved = {}
    monkeypatch.setattr(qs, "get_saved", lambda *a: None)
    monkeypatch.setattr(qs, "pick_sources", lambda conn, facts, n: ["src"] * n)
    monkeypatch.setattr(qs, "make_quiz", lambda facts, sources: _quiz(len(sources)))

    def fake_save(conn, rid, sha, n, quiz):
        saved.update(key=(rid, sha, n), quiz=quiz)
        return 42

    monkeypatch.setattr(qs, "save_quiz", fake_save)
    out = qs.build_quiz(object(), FACTS, 3)
    assert out["cached"] is False and out["quiz_id"] == 42
    assert saved["key"] == (1, "abc", 3)
    assert saved["quiz"]["quiz_version"] == qs.QUIZ_VERSION
    assert "cached" not in saved["quiz"] and "quiz_id" not in saved["quiz"]


def test_empty_quiz_is_not_saved(monkeypatch):
    monkeypatch.setattr(qs, "get_saved", lambda *a: None)
    monkeypatch.setattr(qs, "pick_sources", lambda conn, facts, n: ["src"])
    monkeypatch.setattr(qs, "make_quiz", lambda facts, sources: _quiz(0))
    monkeypatch.setattr(qs, "save_quiz", _no_call)
    out = qs.build_quiz(object(), FACTS, 5)
    assert out["quiz_id"] is None and out["questions"] == []


@pytest.mark.parametrize("n", [0, 11])
def test_bad_question_count_rejected(n):
    with pytest.raises(ValueError):
        qs.build_quiz(object(), FACTS, n)


def test_get_saved_checks_version_and_adds_id():
    assert qs.get_saved(FakeConn((3, {"quiz_version": 0})), 1, "abc", 5) is None
    assert qs.get_saved(FakeConn(None), 1, "abc", 5) is None
    out = qs.get_saved(FakeConn((3, {"quiz_version": qs.QUIZ_VERSION, "questions": []})), 1, "abc", 5)
    assert out["quiz_id"] == 3