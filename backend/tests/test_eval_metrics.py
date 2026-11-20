from backend.app.eval_metrics import first_correct_rank, mrr, overlaps, percentile, recall_at_k

GOLD = {"path": "src/a.py", "start": 10, "end": 12}


def test_overlap_inside_and_touching():
    assert overlaps("src/a.py", 1, 10, GOLD)        # touches the first gold line
    assert overlaps("src/a.py", 12, 40, GOLD)       # touches the last gold line
    assert overlaps("src/a.py", 5, 50, GOLD)        # contains the gold span


def test_no_overlap():
    assert not overlaps("src/a.py", 1, 9, GOLD)     # ends just before
    assert not overlaps("src/a.py", 13, 20, GOLD)   # starts just after
    assert not overlaps("src/b.py", 10, 12, GOLD)   # same lines, different file


def test_first_correct_rank():
    hits = [
        {"path": "src/b.py", "start": 1, "end": 50},
        {"path": "src/a.py", "start": 11, "end": 11},
    ]
    assert first_correct_rank(hits, [GOLD]) == 2
    assert first_correct_rank(hits[:1], [GOLD]) is None


def test_recall_and_mrr():
    ranks = [1, 2, None, 5]
    assert recall_at_k(ranks, 5) == 0.75
    assert recall_at_k(ranks, 1) == 0.25
    assert abs(mrr(ranks) - (1 + 0.5 + 0 + 0.2) / 4) < 1e-9


def test_percentile_nearest_rank():
    values = [100, 200, 300, 400, 1000]
    assert percentile(values, 50) == 300
    assert percentile(values, 95) == 1000
    assert percentile([], 50) is None