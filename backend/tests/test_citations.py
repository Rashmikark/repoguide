from backend.app.answer.explainer import check_citations
from backend.app.retrieval.vector_search import Hit

HITS = [
    Hit(1, "a.py", 10, 20, "function", "f", "", 0.0),
    Hit(2, "b.py", 100, 150, "function", "g", "", 0.0),
]


def test_valid_range():
    (c,) = check_citations("Done here [2:110-120].", HITS)
    assert c.valid and c.path == "b.py"


def test_single_line():
    (c,) = check_citations("See [1:15].", HITS)
    assert c.valid and c.start == c.end == 15


def test_line_outside_chunk_is_invalid():
    (c,) = check_citations("Wrong [1:25].", HITS)
    assert not c.valid and "outside" in c.reason


def test_unknown_source_is_invalid():
    (c,) = check_citations("Ghost [3:1].", HITS)
    assert not c.valid and c.reason == "no such source"


def test_no_citations():
    assert check_citations("No brackets here.", HITS) == []