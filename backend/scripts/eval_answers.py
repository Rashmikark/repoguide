"""Answer eval: retrieve -> explain -> score each answer. Usage:
    python -m backend.scripts.eval_answers --mode hybrid
    python -m backend.scripts.eval_answers --mode keyword --ids itsd-01,itsd-05   (test run)
"""
import argparse
import json
import random
import time
from datetime import datetime, timezone
from pathlib import Path

import psycopg
from google.genai import errors as genai_errors

from backend.app.answer.explainer import explain
from backend.app.answer.judge import judge_key_points
from backend.app.config import settings
from backend.app.eval_metrics import (
    cites_gold,
    found_correct,
    key_point_coverage,
    mean_citation_width,
    percentile,
)
from backend.app.quota import is_daily_quota
from backend.app.retrieval.pipeline import MODES
from backend.app.tracing import langfuse
from backend.scripts.eval_retrieval import (
    EMBED_MODES,
    RESULTS_DIR,
    cache_key,
    load_cache,
    load_questions,
    query_vector,
    run_one,
)

REVIEW_SAMPLE = 10
REVIEW_SEED = 42


def mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def main() -> int:
    parser = argparse.ArgumentParser(description="Answer eval")
    parser.add_argument("--mode", default="hybrid", choices=MODES)
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--ids", default="", help="comma-separated question ids (test run)")
    parser.add_argument("--limit", type=int, default=0, help="only the first N questions (test run)")
    parser.add_argument("--yes", action="store_true")
    args = parser.parse_args()

    questions = load_questions()
    if args.ids:
        wanted = {i.strip() for i in args.ids.split(",")}
        questions = [q for q in questions if q["id"] in wanted]
    if args.limit:
        questions = questions[: args.limit]
    partial = bool(args.ids or args.limit)
    needs_embed = args.mode in EMBED_MODES

    state = {"conn": psycopg.connect(settings.database_url, autocommit=True)}
    repos: dict = {}
    for repo in sorted({q["repo"] for q in questions}):
        row = state["conn"].execute(
            """
            SELECT r.id, r.commit_sha,
                   (SELECT count(*)           FROM chunks c WHERE c.repo_id = r.id),
                   (SELECT count(c.embedding) FROM chunks c WHERE c.repo_id = r.id)
            FROM repos r WHERE r.url = %s
            """,
            (f"https://github.com/{repo}",),
        ).fetchone()
        if row is None or row[2] == 0:
            print(f"{repo} is not indexed")
            return 1
        if needs_embed and row[3] < row[2]:
            print(f"{repo}: only {row[3]}/{row[2]} chunks embedded - finish indexing first")
            return 1
        repos[repo] = {"id": row[0], "commit_sha": row[1]}

    cache = load_cache()
    answerable = sum(1 for q in questions if q["answerable"])
    new_embeddings = sum(1 for q in questions if cache_key(q["question"]) not in cache) if needs_embed else 0
    llm_calls = len(questions) + answerable + (len(questions) if args.mode == "llm-rerank" else 0)
    print(f"{len(questions)} questions ({answerable} answerable, {len(questions) - answerable} negative), "
          f"mode: {args.mode}{'  [PARTIAL TEST RUN]' if partial else ''}")
    print(f"quota this run: {new_embeddings} new embeddings, up to {llm_calls} LLM calls")
    if not args.yes and input("continue? [y/N] ").strip().lower() != "y":
        print("cancelled")
        return 1

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    tag = f"answers_{args.mode}_{run_id}{'_partial' if partial else ''}"
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    rows_path = RESULTS_DIR / f"{tag}.jsonl"
    rows: list[dict] = []
    stopped_early = None

    with rows_path.open("w", encoding="utf-8") as out:
        for i, q in enumerate(questions, start=1):
            row = {"run_id": run_id, "mode": args.mode, "id": q["id"], "repo": q["repo"],
                   "category": q["category"], "answerable": q["answerable"], "error": None}
            try:
                vec = query_vector(cache, q["question"])[0] if needs_embed else None
                hits, info = run_one(state, repos[q["repo"]]["id"], q["question"], args.mode,
                                     args.k, vec)
                t = time.perf_counter()
                exp = explain(q["question"], hits)
                answer_ms = round(1000 * (time.perf_counter() - t))

                cites = [{"path": c.path, "start": c.start, "end": c.end, "valid": c.valid}
                         for c in exp.citations]
                usages = info["llm_usage"] + [exp.usage]
                row.update(
                    found=exp.found,
                    found_correct=found_correct(exp.found, q["answerable"]),
                    answer=exp.answer,
                    citations=cites,
                    invalid_citations=sum(1 for c in cites if not c["valid"]),
                    citation_width=mean_citation_width(cites),
                    latency_ms=info["timings_ms"].get("search", 0)
                    + info["timings_ms"].get("rerank", 0) + answer_ms,
                )
                if q["answerable"]:
                    row["cites_gold"] = cites_gold(cites, q["gold"])
                    if exp.found:
                        covered, judge_usage = judge_key_points(q["question"], q["key_points"], exp.answer)
                        usages.append(judge_usage)
                    else:
                        covered = [False] * len(q["key_points"])   # nothing to judge
                    row["key_points_covered"] = covered
                    row["key_point_coverage"] = key_point_coverage(covered)
                row["tokens"] = sum(u.get("input_tokens", 0) + u.get("output_tokens", 0) for u in usages)
            except Exception as e:
                row["error"] = f"{type(e).__name__}: {e}"[:300]
                code = e.code if isinstance(e, genai_errors.APIError) else None
                if is_daily_quota(code, str(e)):
                    stopped_early = "daily LLM or embedding quota used up"
            rows.append(row)
            out.write(json.dumps(row) + "\n")
            out.flush()

            if row["error"]:
                status = "ERROR " + row["error"][:60]
            else:
                status = (f"found={row['found']!s:<5} ok={row['found_correct']!s:<5} "
                          f"gold={row.get('cites_gold', '-')!s:<5} kp={row.get('key_point_coverage', '-')} "
                          f"bad_cites={row['invalid_citations']}")
            print(f"  [{i:>2}/{len(questions)}] {q['id']:<12} {status}")
            if stopped_early:
                print(f"\nSTOPPED: {stopped_early}. Rows so far are saved in {rows_path}")
                break

    ok = [r for r in rows if not r["error"]]
    ans = [r for r in ok if r["answerable"]]
    neg = [r for r in ok if not r["answerable"]]
    summary = {
        "run_id": run_id, "mode": args.mode, "k": args.k, "partial": partial,
        "stopped_early": stopped_early,
        "embed_model": settings.embed_model, "llm_model": settings.gemini_model,
        "judge_model": settings.gemini_model,
        "repos": repos,
        "questions": len(rows), "errors": len(rows) - len(ok),
        "found_accuracy": mean([1.0 if r["found_correct"] else 0.0 for r in ok]),
        "negatives_correct": f"{sum(1 for r in neg if r['found_correct'])}/{len(neg)}",
        "cites_gold_rate": mean([1.0 if r["cites_gold"] else 0.0 for r in ans]),
        "key_point_coverage_mean": mean([r["key_point_coverage"] for r in ans]),
        "invalid_citations_total": sum(r["invalid_citations"] for r in ok),
        "citations_total": sum(len(r["citations"]) for r in ok),
        "citation_width_p50": percentile([r["citation_width"] for r in ok if r["citation_width"]], 50),
        "latency_ms_p50": percentile([r["latency_ms"] for r in ok], 50),
        "latency_ms_p95": percentile([r["latency_ms"] for r in ok], 95),
        "tokens_mean": mean([r["tokens"] for r in ok]),
        "latency_note": "search (+ rerank) + answer; query embedding excluded (cached)",
    }
    (RESULTS_DIR / f"{tag}_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    # Hand-check sheet: the same 10 answerable questions every run (fixed seed).
    sample = sorted(random.Random(REVIEW_SEED).sample(ans, min(REVIEW_SAMPLE, len(ans))),
                    key=lambda r: r["id"])
    by_id = {q["id"]: q for q in questions}
    lines = [f"# Hand check - {tag}", "",
             "For each key point: do YOU think the answer states it? Fill in Y/N, then compare with the judge.", ""]
    for r in sample:
        q = by_id[r["id"]]
        lines += [f"## {r['id']}: {q['question']}", "", f"**Answer:** {r['answer']}", "",
                  "| key point | judge | you (Y/N) |", "|---|---|---|"]
        for point, verdict in zip(q["key_points"], r["key_points_covered"]):
            lines.append(f"| {point} | {'Y' if verdict else 'N'} |  |")
        lines.append("")
    (RESULTS_DIR / f"{tag}_handcheck.md").write_text("\n".join(lines), encoding="utf-8")

    print(f"\nfound correct: {summary['found_accuracy']}  (negatives: {summary['negatives_correct']})")
    print(f"cites gold:    {summary['cites_gold_rate']}")
    print(f"key points:    {summary['key_point_coverage_mean']}")
    print(f"citations:     {summary['invalid_citations_total']} invalid of {summary['citations_total']}, "
          f"width p50 = {summary['citation_width_p50']} lines")
    print(f"latency:       p50 {summary['latency_ms_p50']} ms, p95 {summary['latency_ms_p95']} ms")
    print(f"tokens/q:      {summary['tokens_mean']}   errors: {summary['errors']}")
    print(f"\nfiles: {tag}.jsonl, _summary.json, _handcheck.md in {RESULTS_DIR}")

    try:
        langfuse.flush()
    except Exception:
        pass
    state["conn"].close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())