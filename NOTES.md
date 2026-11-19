## Week 1 — indexing & vector search
- Chunking: 0 non-blank lines missed on itsdangerous and ky. ky test-aware rule: module chunks 445 -> 376, avg chunk 49.8 -> 19.1 lines.
- Remaining ky module chunks in test/: for-loops wrapping tests + setup code. Left for eval to judge.
- itsdangerous indexing: ~25 s work vs ~116 s rate-limit waiting (50 texts/min).
- Indexed .github templates and CHANGES.rst; may be noise for where/how questions.
- Vector search timing varied 274 ms - 6.4 s on a 134-row table -> network/Neon wake-up, not query cost.
- Vector scores squeezed into 0.63-0.78 -> scores only useful for ordering.




## Week 2 — retrieval comparison (smoke test, itsdangerous @ 672971d66a, k=5)

> 4 questions chosen by me/mentor, results seen by all methods. NOT an evaluation.

| Question | vector | keyword | hybrid (RRF) | rerank MiniLM | llm-rerank |
|---|---|---|---|---|---|
| Q1 expiry (unsign) | 3 | 5 | 2 | MISS | 1 |
| Q2 timing-safe (SigningAlgorithm L28) | 1 | 3 | 1 | MISS | 1 |
| Q3 base64 (base64_encode) | 1 | 1 | 1 | 1 | 1 |
| Q4 SignatureExpired raised (unsign L142/149) | MISS | 1 | MISS | 5 | 1 |

### Observations
- Vector and keyword fail on different questions; most correct chunks appear in at least one top 5.
- Q4 hybrid miss: unsign was vector #18 + keyword #1 -> RRF 0.0292 vs 5th place 0.0298. RRF rewards agreement and lost a single-method hit.
- MiniLM (ms-marco) reranker: worse on 2/4, all scores negative on Q2, ~7-11 s per query on CPU. REJECTED, kept for eval.
- llm-rerank: 4/4 rank 1, ~3.7k-6.9k input tokens, 1.9-10.4 s. CAVEAT: prompt written after seeing Q4 fail -> possible tuning to the test. Prompt is now frozen.
- Q3 is ambiguous (the function vs the places that call it) -> eval questions must be precise.
- Re-export files (__init__.py) and tests take up result slots in keyword search.
- Idea to test in eval: weight keyword higher when the question contains a code name.

## Week 2 — explainer runs
- Q4 llm-rerank: cites timed.py L138-153 (contains raise lines 142/149). Correct.
- Q4 hybrid: unsign not retrieved; answered truthfully from docstrings (exc.py L61, timed.py L25). Valid citations but weaker evidence than the raise line.
- Q2 llm-rerank: valid citation L24-28, but answer wrote "hmc.compare_digest" (typo). Citation check does not catch copying errors.
  Idea: every code name in the answer must appear in its cited lines.
- PostgreSQL question (no answer in repo): found=False, no invented answer. Correct.
- Cost: hybrid+answer = 1 LLM call, ~2.6k-4.3k input tokens; llm-rerank+answer = 2 calls, ~8.5k-10.5k.
- Latency outliers seen: search 3.8 s, answer 7.5 s -> report p50/p95, never single runs.

## Reliability log
- Gemini: SSL EOF once, one silent hang (fixed with 60 s timeout + retries), 503 on 3.8/3.5-flash.
- Embeddings: 429 at ~100 texts/min; 50/min proven safe; 80 test inconclusive (batch size 50).
- Neon: SSL connection closed on first query after idle (fix planned in Step 11: pool + retry).

## Week 2 — API (Step 11)
- POST /repos: 400 bad URL, 404 missing repo, 200 already indexed, 202 started,
  200 "already in progress" on a second request 1 s later (atomic claim works).
- markupsafe indexed via API: 23 files, 111 chunks, ~74 s.
- itsdangerous re-index via API: 81.9 s total, 54.4 s rate-limit waiting (~27.5 s work).
- 80 texts/min: one run with 40+40 batches, no 429 -> works so far (keep watching).
- Bug found: every git failure was reported as 404 "not found". A network failure
  told the user a real repo didn't exist. Fixed: classify git's error -> 404 vs 503.
- Root cause seen: GitHub unreachable for ~3 min -> ls-remote failed and a clone hung.
- Ctrl+C on the server also kills a running git clone (exit 130); job correctly marked failed.
- --reload restart waits for background tasks to finish (graceful).
- Weakness: a failed RE-index marks the repo failed even though the old index is intact.
  Better: keep serving the last good index until the new one succeeds.
- UI note: right after a claim, counts still show the OLD index (134/134) while status
  is pending -> only show the progress bar when status == "indexing".

  ## Week 2 — Ask endpoint (Step 11c)
- POST /repos/{id}/ask works end to end. Q4 (llm-rerank): found=true, cites
  timed.py L138-153 (contains raise lines 142/149), 0 invalid citations.
- Citation links are pinned to the indexed commit (blob/<sha>/path#Lx-Ly).
- No-answer question (PostgreSQL): found=false, no citations, nothing invented.
- Input checks: 404 unknown repo, 422 invalid mode, 422 question < 3 chars.
- Latency (single runs, NOT p50): Q4 llm-rerank total 16.5 s (answer 9.3 s,
  search 2.9 s, rerank 2.7 s, embed 1.3 s); no-answer hybrid 9.0 s (search 4.9 s).
  -> too slow for a blank screen; UI must show progress steps. Measure p50/p95 in eval.
- Known limit: a DB connection is held while Gemini runs (pool max 5).

## Week 2 — Tracing (Step 12)
- Langfuse (US region, Hobby plan). First 401 was the wrong host (EU vs US).
- Bug: my "never break" tracing helper evaluated the method BEFORE the try,
  so a method missing in the SDK (update_current_trace) crashed /ask with 500.
  Fixed: look up the method by name inside the try + unit test for it.
- One question = one trace tree: ask -> retrieve -> gemini.generate (rerank)
  and ask -> explain -> gemini.generate (answer). /ask returns trace_id.
- Trace f73a1c25: total 77 s, of which 70 s was the answer gemini.generate.
  Retrieval 7.7 s. Tracing showed the cause in one look.
- Citation [1:72-146] was valid but 75 lines wide (earlier run: 138-153).
  -> eval must also measure citation WIDTH, not just validity.