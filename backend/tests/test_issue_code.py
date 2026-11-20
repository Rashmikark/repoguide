from backend.app.onboarding.issue_code import attach_related, related_code
from backend.app.retrieval.vector_search import Hit

URL, SHA = "https://github.com/x/y", "abc123"


def _search_returning(hits):
    def search(conn, repo_id, question, k=5):
        search.asked = (repo_id, question, k)
        return hits
    return search


def _hit(n, path):
    return Hit(n, path, 1, 10, "function", "f", "", 1.0 - n / 100)


def _paths(hits):
    return [r["path"] for r in related_code(None, 7, "t", URL, SHA, search=_search_returning(hits))]


def test_top_three_different_files_with_pinned_links():
    hits = [Hit(1, "a.py", 1, 10, "function", "f", "", 0.9),
            Hit(2, "a.py", 20, 30, "function", "g", "", 0.8),   # same file -> skipped
            Hit(3, "b.py", 5, 9, "class", "B", "", 0.7),
            Hit(4, "c.py", 1, 2, "module", None, "", 0.6),
            Hit(5, "d.py", 1, 2, "module", None, "", 0.5)]      # 4th file -> over the limit
    search = _search_returning(hits)
    out = related_code(None, 7, "loads ignores max_age", URL, SHA, search=search)
    assert [r["path"] for r in out] == ["a.py", "b.py", "c.py"]
    assert out[0]["start"] == 1 and out[0]["end"] == 10
    assert SHA in out[0]["url"] and out[0]["url"].endswith("#L1-L10")
    assert search.asked == (7, "loads ignores max_age", 20)


def test_noise_files_skipped():
    hits = [_hit(1, "CHANGES.rst"), _hit(2, "setup.py"), _hit(3, ".github/x.md"),
            _hit(4, "docs/conf.py"), _hit(5, "vite.config.ts"), _hit(6, "src/a.py")]
    assert _paths(hits) == ["src/a.py"]


def test_code_ranked_before_docs_keeping_search_order():
    hits = [_hit(1, "readme.md"), _hit(2, "src/a.py"), _hit(3, "docs/x.rst"), _hit(4, "src/b.py")]
    assert _paths(hits) == ["src/a.py", "src/b.py", "readme.md"]


def test_no_match_is_empty_not_a_guess():
    assert related_code(None, 7, "zzz", URL, SHA, search=_search_returning([])) == []


def test_attach_related_covers_both_tiers():
    picked = {"issues": [{"title": "t1"}], "other_open_issues": [{"title": "t2"}], "checks": {}}
    hits = [Hit(1, "a.py", 1, 10, "function", "f", "", 0.9)]
    out = attach_related(None, 7, URL, SHA, picked, search=_search_returning(hits))
    assert out["issues"][0]["related"][0]["path"] == "a.py"
    assert out["other_open_issues"][0]["related"][0]["path"] == "a.py"
    assert "keyword" in out["related_note"] and out["checks"] == {}
    assert "related" not in picked["issues"][0]          # the input is not modified