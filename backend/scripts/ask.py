import argparse
import sys
import time

import psycopg

from backend.app.config import settings
from backend.app.ingest.repo_loader import parse_github_url
from backend.app.retrieval.hybrid_search import CANDIDATES, hybrid_search
from backend.app.retrieval.keyword_search import keyword_search, keyword_terms
from backend.app.retrieval.llm_rerank import llm_rerank
from backend.app.retrieval.rerank import rerank
from backend.app.retrieval.vector_search import embed_query, vector_search

MODES = ["vector", "keyword", "hybrid", "rerank", "llm-rerank"]

parser = argparse.ArgumentParser(description="Search an indexed repo")
parser.add_argument("url")
parser.add_argument("question")
parser.add_argument("--k", type=int, default=5)
parser.add_argument("--mode", choices=MODES, default="vector")
args = parser.parse_args()

owner, name = parse_github_url(args.url)

with psycopg.connect(settings.database_url) as conn:
    row = conn.execute(
        "SELECT id, status FROM repos WHERE url = %s",
        (f"https://github.com/{owner}/{name}",),
    ).fetchone()
    if row is None or row[1] != "ready":
        sys.exit(f"{owner}/{name} is not indexed (status: {row[1] if row else 'missing'})")

    sources = {}
    t0 = time.perf_counter()
    if args.mode == "keyword":
        t1 = t0
        hits = keyword_search(conn, row[0], args.question, args.k)
    else:
        qvec = embed_query(args.question)
        t1 = time.perf_counter()
        if args.mode == "vector":
            hits = vector_search(conn, row[0], qvec, args.k)
        elif args.mode == "hybrid":
            hits, sources = hybrid_search(conn, row[0], args.question, qvec, args.k)
        else:
            # Both rerankers see the whole fused candidate pool, not just the top k.
            hits, sources = hybrid_search(conn, row[0], args.question, qvec, 2 * CANDIDATES)
    t2 = time.perf_counter()

t3, usage, pool = t2, None, len(hits)
if args.mode == "rerank":
    hits = rerank(args.question, hits, args.k)
    t3 = time.perf_counter()
elif args.mode == "llm-rerank":
    hits, usage = llm_rerank(args.question, hits, args.k)
    t3 = time.perf_counter()

print(f"Q: {args.question}   [mode: {args.mode}]")
if args.mode != "vector":
    print(f"terms: {keyword_terms(args.question)}")
timing = f"embed {1000 * (t1 - t0):.0f} ms | search {1000 * (t2 - t1):.0f} ms"
if args.mode in ("rerank", "llm-rerank"):
    timing += f" | rerank {1000 * (t3 - t2):.0f} ms over {pool} candidates"
print(timing)
if usage:
    print(f"llm usage: {usage}")
print()

for i, h in enumerate(hits, start=1):
    src = ""
    if h.chunk_id in sources:
        v, kw = sources[h.chunk_id]
        src = f"   (vector #{v or '-'}, keyword #{kw or '-'})"
    print(f"{i}. {h.score:.4f}  {h.path}:L{h.start_line}-{h.end_line}  [{h.kind}] {h.symbol or ''}{src}")
    for line in h.content.strip().split("\n")[:2]:
        print(f"      {line[:100]}")