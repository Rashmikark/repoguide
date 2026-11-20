from collections import Counter

from backend.app.onboarding.quiz_sources import doc_freq, pick_quiz_sources, ref_name


def _c(path, start, end, kind="function", symbol="f"):
    return {"chunk_id": 0, "path": path, "start": start, "end": end,
            "kind": kind, "symbol": symbol, "content": ""}


def _picked(cands, preferred=(), n=5, refs=None):
    return [(c["path"], c["symbol"]) for c in pick_quiz_sources(cands, list(preferred), n, refs)]


def test_unusable_chunks_filtered_out():
    cands = [
        _c("tests/test_a.py", 1, 20),                  # test file
        _c("docs/guide.md", 1, 20),                    # doc
        _c("setup.py", 1, 20),                         # noise
        _c("src/a.py", 1, 5),                          # too small (5 lines)
        _c("src/b.py", 1, 200),                        # too big
        _c("src/c.py", 1, 20, kind="module"),          # module chunk
        _c("src/ok.py", 1, 20, symbol="good"),
    ]
    assert _picked(cands) == [("src/ok.py", "good")]


def test_one_per_file_in_reading_plan_order():
    # a1 = 30 lines, a2 = 11 lines -> a1 is the bigger one, so it is a.py's first pick
    cands = [_c("a.py", 1, 30, symbol="a1"), _c("a.py", 40, 50, symbol="a2"),
             _c("b.py", 1, 20, symbol="b1"), _c("c.py", 1, 20, symbol="c1")]
    assert _picked(cands, preferred=["b.py", "a.py"], n=3) == [
        ("b.py", "b1"), ("a.py", "a1"), ("c.py", "c1")]


def test_second_round_only_when_files_run_out():
    # a2 = 21 lines, a1 = 20 lines -> a2 is bigger, so a2 comes in round 1, a1 in round 2
    cands = [_c("a.py", 1, 20, symbol="a1"), _c("a.py", 30, 50, symbol="a2"),
             _c("b.py", 1, 20, symbol="b1")]
    assert _picked(cands, n=4) == [("a.py", "a2"), ("b.py", "b1"), ("a.py", "a1")]


def test_public_before_private_then_bigger_first():
    cands = [_c("a.py", 1, 40, symbol="_helper"),          # private, 40 lines
             _c("a.py", 50, 59, symbol="Small"),            # public, 10 lines
             _c("a.py", 60, 109, symbol="Big"),             # public, 50 lines
             _c("a.py", 120, 139, symbol="Ky.#retry")]      # TS private, 20 lines
    assert _picked(cands, n=4) == [("a.py", "Big"), ("a.py", "Small"),
                                   ("a.py", "_helper"), ("a.py", "Ky.#retry")]


def test_nothing_usable_is_empty():
    assert _picked([_c("tests/t.py", 1, 20)]) == []


def test_doc_freq_counts_chunks_not_occurrences():
    freq = doc_freq(["escape(x) + escape(y)", "Markup escape", "other"])
    assert freq["escape"] == 2 and freq["Markup"] == 1 and freq["missing"] == 0


def test_most_referenced_beats_bigger():
    cands = [_c("a.py", 1, 50, symbol="rare"), _c("a.py", 60, 79, symbol="popular")]
    refs = Counter({"popular": 9, "rare": 1})
    assert _picked(cands, n=2, refs=refs) == [("a.py", "popular"), ("a.py", "rare")]


def test_private_module_goes_after_public_files():
    cands = [_c("src/_json.py", 1, 20, symbol="Compact"), _c("src/enc.py", 1, 20, symbol="encode")]
    assert _picked(cands, preferred=["src/_json.py", "src/enc.py"], n=2) == [
        ("src/enc.py", "encode"), ("src/_json.py", "Compact")]


def test_ref_name_uses_class_for_generic_methods():
    assert ref_name("Markup.striptags") == "striptags"
    assert ref_name("Ky.constructor") == "Ky"
    assert ref_name("Ky.#retryFromError") == "retryFromError"
    assert ref_name("escape") == "escape" and ref_name(None) == ""


def test_private_module_only_after_all_public_rounds():
    # The markupsafe case: _native.py must not take a slot while __init__.py still has picks.
    cands = [_c("src/pkg/__init__.py", 1, 30, symbol="Markup"),
             _c("src/pkg/__init__.py", 40, 60, symbol="escape_silent"),
             _c("src/pkg/_native.py", 1, 10, symbol="_escape_inner")]
    assert _picked(cands, n=3) == [("src/pkg/__init__.py", "Markup"),
                                   ("src/pkg/__init__.py", "escape_silent"),
                                   ("src/pkg/_native.py", "_escape_inner")]


def test_same_name_never_picked_twice():
    # The markupsafe case: escape() and Markup.escape() are one concept for a quiz.
    cands = [_c("a.py", 1, 20, symbol="escape"),
             _c("b.py", 1, 20, symbol="Markup.escape"),
             _c("c.py", 1, 20, symbol="other")]
    assert _picked(cands, n=3) == [("a.py", "escape"), ("c.py", "other")]