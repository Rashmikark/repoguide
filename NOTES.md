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