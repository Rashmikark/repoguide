import argparse
import sys
import time

import psycopg

from backend.app.answer.explainer import explain
from backend.app.config import settings
from backend.app.ingest.repo_loader import parse_github_url
from backend.app.retrieval.pipeline import MODES, retrieve

parser = argparse.ArgumentParser(description="Answer a question about an indexed repo")
parser.add_argument("url")
parser.add_argument("question")
parser.add_argument("--mode", choices=MODES, default="hybrid")
parser.add_argument("--k", type=int, default=5)
args = parser.parse_args()

owner, name = parse_github_url(args.url)

with psycopg.connect(settings.database_url) as conn:
    row = conn.execute(
        "SELECT id, status FROM repos WHERE url = %s",
        (f"https://github.com/{owner}/{name}",),
    ).fetchone()
    if row is None or row[1] != "ready":
        sys.exit(f"{owner}/{name} is not indexed (status: {row[1] if row else 'missing'})")
    hits, info = retrieve(conn, row[0], args.question, args.mode, args.k)

t = time.perf_counter()
exp = explain(args.question, hits)
info["timings_ms"]["answer"] = round(1000 * (time.perf_counter() - t))
info["llm_usage"].append(exp.usage)

print(f"Q: {args.question}   [mode: {args.mode}]\n")
print(f"found: {exp.found}")
print(exp.answer, "\n")

bad = [c for c in exp.citations if not c.valid]
print(f"citations: {len(exp.citations)} total, {len(bad)} invalid")
for c in exp.citations:
    status = "OK " if c.valid else "BAD"
    where = f"{c.path}:L{c.start}-{c.end}" if c.path else f"source {c.source}"
    print(f"  {status} [{c.source}:{c.start}-{c.end}] -> {where} {c.reason}")
if exp.found and not exp.citations:
    print("  WARNING: answer claims found=true but cites nothing")

print("\nsources given to the model:")
for i, h in enumerate(hits, start=1):
    print(f"  [{i}] {h.path}:L{h.start_line}-{h.end_line} {h.symbol or ''}")
print(f"\ntimings_ms: {info['timings_ms']}")
print(f"llm_usage: {info['llm_usage']}")