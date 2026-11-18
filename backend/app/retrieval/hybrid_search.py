from dataclasses import replace

import psycopg

from backend.app.retrieval.keyword_search import keyword_search
from backend.app.retrieval.vector_search import Hit, vector_search

RRF_K = 60          # standard constant from the original RRF paper
CANDIDATES = 20     # how many results each method contributes


def rrf_fuse(rankings: list[list[Hit]], k: int) -> list[Hit]:
    """Merge ranked lists by Reciprocal Rank Fusion. Score = sum of 1/(RRF_K + rank)."""
    scores: dict[int, float] = {}
    first_seen: dict[int, Hit] = {}
    for hits in rankings:
        for rank, hit in enumerate(hits, start=1):
            scores[hit.chunk_id] = scores.get(hit.chunk_id, 0.0) + 1.0 / (RRF_K + rank)
            first_seen.setdefault(hit.chunk_id, hit)
    ordered = sorted(scores, key=lambda cid: (-scores[cid], cid))
    return [replace(first_seen[cid], score=scores[cid]) for cid in ordered[:k]]


def hybrid_search(conn: psycopg.Connection, repo_id: int, question: str,
                  query_vec: str, k: int = 5) -> tuple[list[Hit], dict[int, tuple]]:
    vec = vector_search(conn, repo_id, query_vec, CANDIDATES)
    kw = keyword_search(conn, repo_id, question, CANDIDATES)
    # Where did each chunk come from? Used for debugging and the eval report.
    sources = {}
    for rank, h in enumerate(vec, start=1):
        sources[h.chunk_id] = (rank, None)
    for rank, h in enumerate(kw, start=1):
        v_rank = sources.get(h.chunk_id, (None, None))[0]
        sources[h.chunk_id] = (v_rank, rank)
    return rrf_fuse([vec, kw], k), sources