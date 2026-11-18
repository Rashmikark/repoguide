from backend.app.retrieval.hybrid_search import rrf_fuse
from backend.app.retrieval.vector_search import Hit


def hit(cid: int) -> Hit:
    return Hit(cid, f"f{cid}.py", 1, 2, "function", None, "", 0.0)


def test_chunk_found_by_both_beats_single_list_winner():
    vec = [hit(1), hit(2)]          # 1 is vector's top result
    kw = [hit(3), hit(2)]           # 2 is found by both, rank 2 each
    assert rrf_fuse([vec, kw], k=3)[0].chunk_id == 2


def test_ties_broken_by_chunk_id():
    fused = rrf_fuse([[hit(5)], [hit(4)]], k=2)
    assert [h.chunk_id for h in fused] == [4, 5]


def test_k_limits_results():
    assert len(rrf_fuse([[hit(i) for i in range(10)]], k=3)) == 3


def test_empty_lists():
    assert rrf_fuse([[], []], k=5) == []