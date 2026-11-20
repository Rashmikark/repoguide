"""Retrieval eval: ask every answerable question with each mode, score the ranks.
Usage:
    python -m backend.scripts.eval_retrieval --modes keyword
    python -m backend.scripts.eval_retrieval --modes vector,keyword,hybrid,llm-rerank
"""
import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import psycopg

from backend.app.config import settings
from backend.app.eval_metrics import first_correct_rank, mrr, percentile, recall_at_k
from backend.app.retrieval.pipeline import MODES, retrieve
from backend.app.retrieval.vector_search import embed_query
from backend.app.tracing import langfuse

QUESTIONS = Path("eval/questions.jsonl")
CACHE = Path("eval/cache/query_vectors.json")
RESULTS_DIR = Path("eval/results")
EMBED_MODES = {"vector", "hybrid", "rerank", "llm-rerank"}


def load_questions() -> list[dict]:
    lines = QUESTIONS.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def cache_key(question: str) -> str:
    return f"{settings.embed_model}|{settings.embed_dim}|{question}"


def load_cache() -> dict:
    return json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}


def save_cache(cache: dict) -> None:
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(cache), encoding="utf-8")


def query_vector(cache: dict, question: str) -> tuple[str, float | None]:
    """Cached vector, or embed once and save straight away (keeps progress if quota runs out)."""
    key = cache_key(question)
    if key in cache:
        return cache[key], None
    t = time.perf_counter()
    vec = embed_query(question)
    elapsed_ms = 1000 * (time.perf_counter() - t)
    cache[key] = vec
    save_cache(cache)
    return vec, elapsed_ms


def run_one(state: dict, *args):
    """retrieve() with one reconnect if Neon dropped the connection."""
    for attempt in (1, 2):
        try:
            return retrieve(state["conn"], *args)
        except psycopg.OperationalError:
            if attempt == 2:
                raise
            try:
                state["conn"].close()
            except Exception:
                pass
            state["conn"] = psycopg.connect(settings.database_url, autocommit=True)


def fmt(value) -> str:
    return f"{value:>7.0f}" if value is not None else "      -"


def main() -> int:
    parser = argparse.ArgumentParser(description="Retrieval eval")
    parser.add_argument("--modes", default="keyword", help="comma-separated: " + ",".join(MODES))
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    args = parser.parse_args()

    modes = [m.strip() for m in args.modes.split(",") if m.strip()]
    unknown = [m for m in modes if m not in MODES]
    if unknown:
        print(f"unknown modes {unknown}; choose from {MODES}")
        return 1

    questions = load_questions()
    scored = [q for q in questions if q["answerable"]]
    negatives = len(questions) - len(scored)
    needs_embed = any(m in EMBED_MODES for m in modes)

    # Autocommit: the eval only reads, and one failed query must not poison the next.
    state = {"conn": psycopg.connect(settings.database_url, autocommit=True)}
    repos: dict = {}
    for repo in sorted({q["repo"] for q in scored}):
        row = state["conn"].execute(
            """
            SELECT r.id, r.status, r.commit_sha,
                   (SELECT count(*)           FROM chunks c WHERE c.repo_id = r.id),
                   (SELECT count(c.embedding) FROM chunks c WHERE c.repo_id = r.id)
            FROM repos r WHERE r.url = %s
            """,
            (f"https://github.com/{repo}",),
        ).fetchone()
        if row is None or row[3] == 0:
            print(f"{repo} is not indexed - index it first")
            return 1
        repos[repo] = {"id": row[0], "status": row[1], "commit_sha": row[2],
                       "chunks": row[3], "embedded": row[4]}
        if needs_embed and row[4] < row[3]:
            print(f"{repo}: only {row[4]}/{row[3]} chunks embedded. Vector-based modes would be "
                  "unfairly blind to the rest - finish indexing first (keyword mode is fine).")
            return 1

    cache = load_cache()
    new_embeddings = sum(1 for q in scored if cache_key(q["question"]) not in cache) if needs_embed else 0
    llm_calls = len(scored) if "llm-rerank" in modes else 0
    print(f"{len(scored)} answerable questions x {len(modes)} mode(s): {', '.join(modes)}")
    print(f"({negatives} negative questions are scored in the answer eval, not here)")
    print(f"quota this run: {new_embeddings} new embeddings, {llm_calls} LLM calls")
    if not args.yes and input("continue? [y/N] ").strip().lower() != "y":
        print("cancelled")
        return 1

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    rows_path = RESULTS_DIR / f"retrieval_{run_id}.jsonl"
    rows: list[dict] = []
    embed_ms: list[float] = []

    with rows_path.open("w", encoding="utf-8") as out:
        for i, q in enumerate(scored, start=1):
            vec = None
            if needs_embed:
                vec, ms = query_vector(cache, q["question"])
                if ms is not None:
                    embed_ms.append(ms)
            line = []
            for mode in modes:
                row = {"run_id": run_id, "mode": mode, "id": q["id"],
                       "repo": q["repo"], "category": q["category"]}
                try:
                    hits, info = run_one(state, repos[q["repo"]]["id"], q["question"], mode,
                                         args.k, vec if mode in EMBED_MODES else None)
                    found = [{"path": h.path, "start": h.start_line, "end": h.end_line} for h in hits]
                    row.update(rank=first_correct_rank(found, q["gold"]),
                               hits=[f"{f['path']}:L{f['start']}-{f['end']}" for f in found],
                               timings_ms=info["timings_ms"], llm_usage=info["llm_usage"], error=None)
                except Exception as e:
                    row.update(rank=None, hits=[], timings_ms={}, llm_usage=[],
                               error=f"{type(e).__name__}: {e}"[:300])
                rows.append(row)
                out.write(json.dumps(row) + "\n")
                out.flush()
                line.append(f"{mode}={'ERR' if row['error'] else (row['rank'] or '-')}")
            print(f"  [{i:>2}/{len(scored)}] {q['id']:<12} " + "  ".join(line))

    summary = {
        "run_id": run_id,
        "k": args.k,
        "embed_model": settings.embed_model,
        "llm_model": settings.gemini_model,
        "repos": {r: {"commit_sha": v["commit_sha"], "chunks": v["chunks"]} for r, v in repos.items()},
        "questions_scored": len(scored),
        "negatives_not_scored_here": negatives,
        "latency_note": "latency = search (+ rerank); query embedding excluded (cached), see embed_ms_new",
        "embed_ms_new": {"n": len(embed_ms), "p50": percentile(embed_ms, 50), "p95": percentile(embed_ms, 95)},
        "modes": {},
    }
    for mode in modes:
        mrows = [r for r in rows if r["mode"] == mode]
        ranks = [r["rank"] for r in mrows]
        latency = [r["timings_ms"].get("search", 0) + r["timings_ms"].get("rerank", 0)
                   for r in mrows if not r["error"]]
        summary["modes"][mode] = {
            "n": len(mrows),
            "errors": sum(1 for r in mrows if r["error"]),
            "recall_at_1": recall_at_k(ranks, 1),
            f"recall_at_{args.k}": recall_at_k(ranks, args.k),
            "mrr": mrr(ranks),
            "latency_ms_p50": percentile(latency, 50),
            "latency_ms_p95": percentile(latency, 95),
            "llm_tokens": sum(u.get("input_tokens", 0) + u.get("output_tokens", 0)
                              for r in mrows for u in r["llm_usage"]),
            "by_category": {c: recall_at_k([r["rank"] for r in mrows if r["category"] == c], args.k)
                            for c in sorted({r["category"] for r in mrows})},
            "by_repo": {p: recall_at_k([r["rank"] for r in mrows if r["repo"] == p], args.k)
                        for p in sorted({r["repo"] for r in mrows})},
        }
    summary_path = RESULTS_DIR / f"retrieval_{run_id}_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    k = args.k
    print(f"\n{'mode':<11} {'n':>3} {'R@1':>6} {'R@' + str(k):>6} {'MRR':>6} {'p50ms':>7} {'p95ms':>7} {'err':>4}")
    for mode, s in summary["modes"].items():
        print(f"{mode:<11} {s['n']:>3} {s['recall_at_1']:>6.2f} {s[f'recall_at_{k}']:>6.2f} "
              f"{s['mrr']:>6.3f} {fmt(s['latency_ms_p50'])} {fmt(s['latency_ms_p95'])} {s['errors']:>4}")
    print(f"\nrecall@{k} by category:")
    for mode, s in summary["modes"].items():
        print(f"  {mode:<11} " + "  ".join(f"{c}={v:.2f}" for c, v in s["by_category"].items()))
    print(f"\nrecall@{k} by repo:")
    for mode, s in summary["modes"].items():
        print(f"  {mode:<11} " + "  ".join(f"{p.split('/')[1]}={v:.2f}" for p, v in s["by_repo"].items()))
    print(f"\nrows:    {rows_path}\nsummary: {summary_path}")

    try:
        langfuse.flush()
    except Exception:
        pass
    state["conn"].close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())