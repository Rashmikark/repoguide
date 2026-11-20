from backend.app.eval_metrics import cites_gold, found_correct, key_point_coverage, mean_citation_width

GOLD = [{"path": "src/a.py", "start": 140, "end": 150}]


def cite(path, start, end, valid=True):
    return {"path": path, "start": start, "end": end, "valid": valid}


def test_found_correct_for_answerable_and_negative():
    assert found_correct(True, True)
    assert found_correct(False, False)       # negative question answered "not found"
    assert not found_correct(True, False)    # invented an answer to a negative question
    assert not found_correct(False, True)


def test_cites_gold_needs_a_valid_overlapping_citation():
    assert cites_gold([cite("src/a.py", 138, 153)], GOLD)
    assert not cites_gold([cite("src/a.py", 1, 20)], GOLD)              # wrong lines
    assert not cites_gold([cite("src/a.py", 140, 150, valid=False)], GOLD)  # invalid never counts
    assert not cites_gold([], GOLD)


def test_mean_citation_width_ignores_invalid():
    cites = [cite("a", 1, 10), cite("a", 5, 5), cite("a", 1, 500, valid=False)]
    assert mean_citation_width(cites) == (10 + 1) / 2
    assert mean_citation_width([]) is None


def test_key_point_coverage():
    assert key_point_coverage([True, False, True, True]) == 0.75
    assert key_point_coverage([]) is None