import time

import psycopg

from backend.app.retrieval.hybrid_search import CANDIDATES, hybrid_search
from backend.app.retrieval.keyword_search import keyword_search
from backend.app.retrieval.llm_rerank import llm_rerank
from backend.app.retrieval.vector_search import Hit, embed_query, vector_search

MODES = ("vector", "keyword", "hybrid", "rerank", "llm-rerank")


def retrieve(conn: psycopg.Connection, repo_id: int, question: str,
             mode: str = "hybrid", k: int = 5) -> tuple[list[Hit], dict]:
    if mode not in MODES:
        raise ValueError(f"unknown mode {mode!r}")
    info: dict = {"mode": mode, "timings_ms": {}, "llm_usage": []}
    t = time.perf_counter()

    def lap(name: str) -> None:
        nonlocal t
        now = time.perf_counter()
        info["timings_ms"][name] = round(1000 * (now - t))
        t = now

    if mode == "keyword":
        hits = keyword_search(conn, repo_id, question, k)
        lap("search")
        return hits, info

    qvec = embed_query(question)
    lap("embed")
    if mode == "vector":
        hits = vector_search(conn, repo_id, qvec, k)
        lap("search")
        return hits, info

    pool_k = k if mode == "hybrid" else 2 * CANDIDATES
    hits, _ = hybrid_search(conn, repo_id, question, qvec, pool_k)
    lap("search")

    if mode == "rerank":
        from backend.app.retrieval.rerank import rerank   # lazy: importing torch is slow
        hits = rerank(question, hits, k)
        lap("rerank")
    elif mode == "llm-rerank":
        hits, usage = llm_rerank(question, hits, k)
        lap("rerank")
        info["llm_usage"].append(usage)
    return hits, info