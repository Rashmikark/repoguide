from backend.app.onboarding import graph

FAKE_CONN = object()
START_STATE = {"repo_id": 1, "days": 3, "hours_per_day": 2, "errors": []}
CONFIG = {"configurable": {"conn": FAKE_CONN}}


def _run(config=CONFIG):
    return graph.build_graph().invoke(dict(START_STATE), config=config)


def _fake_path(conn, facts, days, hours):
    return {"days": [], "asked": (days, hours), "cached": False}


def _fake_issues(conn, facts):
    return {"issues": [], "other_open_issues": [], "cached": False}


def _all_ok(monkeypatch):
    monkeypatch.setattr(graph, "load_repo_facts", lambda c, r: {"repo_id": r})
    monkeypatch.setattr(graph, "make_overview", lambda c, f: {"summary": "ok"})
    monkeypatch.setattr(graph, "build_path", _fake_path)
    monkeypatch.setattr(graph, "build_issues", _fake_issues)


def test_happy_path_runs_every_node(monkeypatch):
    seen = {}

    def fake_facts(conn, repo_id):
        seen["conn"] = conn
        return {"repo_id": repo_id, "url": "https://github.com/x/y"}

    _all_ok(monkeypatch)
    monkeypatch.setattr(graph, "load_repo_facts", fake_facts)
    out = _run()
    assert seen["conn"] is FAKE_CONN          # the node received the connection from config
    assert out["facts"]["repo_id"] == 1
    assert out["overview"] == {"summary": "ok"}
    assert out["path"]["asked"] == (3, 2)     # days and hours came from the state
    assert out["issues"]["other_open_issues"] == []
    assert out["quiz"] == []
    assert out["errors"] == []


def test_facts_failure_skips_everything_after(monkeypatch):
    def boom(conn, repo_id):
        raise ValueError("db down")

    called = []
    monkeypatch.setattr(graph, "load_repo_facts", boom)
    monkeypatch.setattr(graph, "make_overview", lambda c, f: called.append("overview"))
    monkeypatch.setattr(graph, "build_path", lambda *a: called.append("path"))
    monkeypatch.setattr(graph, "build_issues", lambda *a: called.append("issues"))
    out = _run()
    assert called == []                       # nothing ran on empty facts
    assert out["errors"] == ["load_facts: ValueError: db down",
                             "overview: skipped because facts are missing",
                             "path: skipped because facts are missing",
                             "issues: skipped because facts are missing"]


def test_overview_failure_is_recorded_not_raised(monkeypatch):
    def boom(conn, facts):
        raise RuntimeError("quota")

    _all_ok(monkeypatch)
    monkeypatch.setattr(graph, "make_overview", boom)
    out = _run()
    assert out["overview"] == {}
    assert out["path"]["asked"] == (3, 2)     # later nodes still ran
    assert out["errors"] == ["overview: RuntimeError: quota"]


def test_path_failure_is_recorded_not_raised(monkeypatch):
    def boom(conn, facts, days, hours):
        raise ValueError("days must be 1-30")

    _all_ok(monkeypatch)
    monkeypatch.setattr(graph, "build_path", boom)
    out = _run()
    assert out["path"] == {} and out["overview"] == {"summary": "ok"}
    assert out["errors"] == ["path: ValueError: days must be 1-30"]


def test_issues_failure_is_recorded_not_raised(monkeypatch):
    def boom(conn, facts):
        raise RuntimeError("GitHub API rate limit reached")

    _all_ok(monkeypatch)
    monkeypatch.setattr(graph, "build_issues", boom)
    out = _run()
    assert out["issues"] == {} and out["path"]["asked"] == (3, 2)
    assert out["errors"] == ["issues: RuntimeError: GitHub API rate limit reached"]


def test_missing_connection_is_an_error():
    out = _run(config={})
    assert out["errors"][0].startswith("load_facts: RuntimeError: no database connection")