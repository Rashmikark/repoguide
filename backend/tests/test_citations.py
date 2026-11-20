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


def test_list_citation_is_split_and_each_part_checked():
    # The exact shape Gemini produced in the ky overview: [1:23-26,34]
    cites = check_citations("Retries and types [2:110-120,140].", HITS)
    assert [(c.start, c.end, c.valid) for c in cites] == [(110, 120, True), (140, 140, True)]


def test_list_citation_with_one_bad_part():
    cites = check_citations("Mixed [1:12,25].", HITS)
    assert [c.valid for c in cites] == [True, False]


def test_malformed_citation_is_invalid_not_skipped():
    (c,) = check_citations("Weird [2:abc].", HITS)
    assert not c.valid and c.reason.startswith("malformed")