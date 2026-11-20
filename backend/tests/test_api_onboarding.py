from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app import api_onboarding as api

app = FastAPI()
app.include_router(api.router)
client = TestClient(app)


class FakeConn:
    def __init__(self, row):
        self.row = row

    def execute(self, sql, params):
        return self

    def fetchone(self):
        return self.row


def _use_conn(monkeypatch, row):
    monkeypatch.setattr(api, "with_conn", lambda fn, retries=1: fn(FakeConn(row)))


def test_unknown_repo_is_404(monkeypatch):
    _use_conn(monkeypatch, None)
    r = client.post("/repos/999/onboarding/path", json={"days": 5, "hours_per_day": 2})
    assert r.status_code == 404


def test_repo_not_ready_is_409(monkeypatch):
    _use_conn(monkeypatch, ("failed",))
    r = client.post("/repos/28/onboarding/path", json={"days": 5, "hours_per_day": 2})
    assert r.status_code == 409 and "failed" in r.json()["detail"]


def test_ready_repo_returns_plan(monkeypatch):
    _use_conn(monkeypatch, ("ready",))
    monkeypatch.setattr(api, "_make_path",
                        lambda conn, rid, req: {"days": [], "asked": [req.days, req.hours_per_day]})
    r = client.post("/repos/1/onboarding/path", json={"days": 3, "hours_per_day": 1.5})
    assert r.status_code == 200 and r.json()["asked"] == [3, 1.5]


def test_bad_input_is_422_before_db(monkeypatch):
    monkeypatch.setattr(api, "with_conn", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no DB")))
    for body in ({"days": 0, "hours_per_day": 2}, {"days": 5, "hours_per_day": 20}):
        assert client.post("/repos/1/onboarding/path", json=body).status_code == 422