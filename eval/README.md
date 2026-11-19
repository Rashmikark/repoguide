# RepoGuide evaluation set

Written BEFORE running any retrieval method on these questions.
Rules below were committed before the first eval run and must not change afterwards.

## Repos (pinned commits recorded at run time)
- pallets/itsdangerous (Python)
- pallets/markupsafe (Python)
- sindresorhus/ky (TypeScript)

## Target: ~50 questions
| Repo | Questions |
|---|---|
| itsdangerous | 18 |
| markupsafe | 14 |
| ky | 18 |

Mix per repo:
- locate:  "Where is X defined / raised / configured?"
- how:     "How does X work?"
- usage:   "Where is X called / used?"  (identifier questions - vector search's weak spot)
- docs:    answered by README/docs
- negative: NOT answerable from the repo (~1 per repo) -> expected found=false

## How to write a question
1. Read the code yourself (data/repos/<owner>__<name>/ in VS Code). Do NOT ask RepoGuide.
2. Write the question as a new developer would ask it. Be precise
   (e.g. "where is base64 encoding implemented" vs "where is it called" - not both).
3. Record gold = the NARROWEST line range(s) that answer it. Several spans allowed
   if more than one place is a correct answer.
4. Record 1-3 key_points: facts a correct answer must contain.
5. Never edit a question after seeing any method's results for it.

## Excluded
The 4 smoke-test questions from Weeks 1-2 (expiry check, timing-safe compare,
base64 encoding, where SignatureExpired is raised): all methods were tuned on them.

## Scoring rules (fixed before any run)
- Retrieval hit: a retrieved chunk is correct if same path AND its line range
  overlaps any gold span.
- Metrics per method: recall@5 (any correct chunk in top 5), MRR (1/rank of the
  first correct chunk, 0 if none in top 5).
- Answer: found must match answerable; citations must be valid; at least one
  citation must overlap a gold span; key_points judged (LLM judge + 10 checked by hand).
- Citation width: number of lines per citation (narrower = more useful).
- Latency p50/p95 and tokens per question from the API response / Langfuse traces.
- Cost: tokens x published price per token, labelled "estimated at list price".

## File format: eval/questions.jsonl (one JSON object per line)
{"id": "itsd-01", "repo": "pallets/itsdangerous", "category": "locate",
 "question": "...", "answerable": true,
 "gold": [{"path": "src/...py", "start": 10, "end": 14}],
 "key_points": ["..."]}