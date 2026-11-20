from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app import api_onboarding as api
from backend.app.ingest.repo_loader import GitHubUnavailable
from backend.app.onboarding.issues import GitHubRateLimited

app = FastAPI()
app.include_router(api.router)
client = TestClient(app)

READY = ("ready", "https://github.com/x/y", "abc")


class FakeConn:
    def __init__(self, row):
        self.row = row

    def execute(self, sql, params):
        return self

    def fetchone(self):
        return self.row


def _use_conn(monkeypatch, row):
    monkeypatch.setattr(api, "with_conn", lambda fn, retries=1: fn(FakeConn(row)))


# ---------- POST /repos/{id}/onboarding/path ----------

def test_unknown_repo_is_404(monkeypatch):
    _use_conn(monkeypatch, None)
    r = client.post("/repos/999/onboarding/path", json={"days": 5, "hours_per_day": 2})
    assert r.status_code == 404


def test_repo_not_ready_is_409(monkeypatch):
    _use_conn(monkeypatch, ("failed", "u", "s"))
    r = client.post("/repos/28/onboarding/path", json={"days": 5, "hours_per_day": 2})
    assert r.status_code == 409 and "failed" in r.json()["detail"]


def test_ready_repo_returns_plan(monkeypatch):
    _use_conn(monkeypatch, READY)
    monkeypatch.setattr(api, "_make_path",
                        lambda conn, rid, req: {"days": [], "asked": [req.days, req.hours_per_day]})
    r = client.post("/repos/1/onboarding/path", json={"days": 3, "hours_per_day": 1.5})
    assert r.status_code == 200 and r.json()["asked"] == [3, 1.5]


def test_bad_input_is_422_before_db(monkeypatch):
    monkeypatch.setattr(api, "with_conn", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no DB")))
    for body in ({"days": 0, "hours_per_day": 2}, {"days": 5, "hours_per_day": 20}):
        assert client.post("/repos/1/onboarding/path", json=body).status_code == 422


# ---------- GET /repos/{id}/onboarding/issues ----------

def _issues_raising(exc):
    def f(conn, rid, url, sha):
        raise exc
    return f


def test_issues_unknown_repo_is_404(monkeypatch):
    _use_conn(monkeypatch, None)
    assert client.get("/repos/999/onboarding/issues").status_code == 404


def test_issues_repo_not_ready_is_409(monkeypatch):
    _use_conn(monkeypatch, ("failed", "u", "s"))
    assert client.get("/repos/28/onboarding/issues").status_code == 409


def test_issues_ready_repo_passes_url_and_commit(monkeypatch):
    _use_conn(monkeypatch, READY)
    monkeypatch.setattr(api, "_get_issues",
                        lambda conn, rid, url, sha: {"issues": [], "asked": [rid, url, sha]})
    r = client.get("/repos/1/onboarding/issues")
    assert r.status_code == 200 and r.json()["asked"] == [1, "https://github.com/x/y", "abc"]


def test_issues_rate_limit_is_429(monkeypatch):
    _use_conn(monkeypatch, READY)
    monkeypatch.setattr(api, "_get_issues", _issues_raising(GitHubRateLimited("limit; resets at 123")))
    r = client.get("/repos/1/onboarding/issues")
    assert r.status_code == 429 and "resets" in r.json()["detail"]


def test_issues_github_down_is_503(monkeypatch):
    _use_conn(monkeypatch, READY)
    monkeypatch.setattr(api, "_get_issues", _issues_raising(GitHubUnavailable("unreachable")))
    assert client.get("/repos/1/onboarding/issues").status_code == 503


# ---------- POST /repos/{id}/onboarding/quiz ----------

def test_quiz_unknown_repo_is_404(monkeypatch):
    _use_conn(monkeypatch, None)
    assert client.post("/repos/999/onboarding/quiz", json={"questions": 5}).status_code == 404


def test_quiz_repo_not_ready_is_409(monkeypatch):
    _use_conn(monkeypatch, ("failed", "u", "s"))
    assert client.post("/repos/28/onboarding/quiz", json={"questions": 5}).status_code == 409


def test_quiz_ready_repo_and_bad_count(monkeypatch):
    _use_conn(monkeypatch, READY)
    monkeypatch.setattr(api, "_make_quiz", lambda conn, rid, n: {"quiz_id": 1, "asked": n})
    r = client.post("/repos/1/onboarding/quiz", json={"questions": 3})
    assert r.status_code == 200 and r.json()["asked"] == 3
    assert client.post("/repos/1/onboarding/quiz", json={"questions": 11}).status_code == 422


# ---------- POST /onboarding/quizzes/{id}/answers ----------

STORED = {"questions": [
    {"id": "q1", "question": "Q?", "options": ["a", "b", "c", "d"], "correct": 1,
     "explanation": "because b", "path": "a.py", "symbol": "f", "start": 1, "end": 5, "url": "u"},
]}


def test_answers_unknown_quiz_is_404(monkeypatch):
    _use_conn(monkeypatch, None)
    assert client.post("/onboarding/quizzes/99/answers", json={"answers": {"q1": 1}}).status_code == 404


def test_answers_are_graded_on_the_server(monkeypatch):
    _use_conn(monkeypatch, (5, STORED))
    r = client.post("/onboarding/quizzes/5/answers", json={"answers": {"q1": 1}})
    body = r.json()
    assert r.status_code == 200 and body["quiz_id"] == 5
    assert body["score"] == 1 and body["results"][0]["explanation"] == "because b"


def test_answer_outside_0_to_3_is_422(monkeypatch):
    _use_conn(monkeypatch, (5, STORED))
    assert client.post("/onboarding/quizzes/5/answers", json={"answers": {"q1": 7}}).status_code == 422