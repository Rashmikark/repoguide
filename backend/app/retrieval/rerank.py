from dataclasses import replace
from functools import lru_cache

from sentence_transformers import CrossEncoder

from backend.app.retrieval.vector_search import Hit

RERANK_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"
WINDOW_LINES = 40      # fits within the model's ~512-token limit
WINDOW_STEP = 30       # 10 lines of overlap between windows


@lru_cache(maxsize=1)
def _model() -> CrossEncoder:
    return CrossEncoder(RERANK_MODEL)   # loaded once per process


def _windows(h: Hit) -> list[str]:
    lines = h.content.split("\n")
    header = f"{h.path} {h.symbol or ''}"
    starts = range(0, max(len(lines) - WINDOW_LINES, 0) + 1, WINDOW_STEP)
    out = [header + "\n" + "\n".join(lines[s:s + WINDOW_LINES]) for s in starts]
    if len(lines) > WINDOW_LINES and (len(lines) - WINDOW_LINES) % WINDOW_STEP:
        out.append(header + "\n" + "\n".join(lines[-WINDOW_LINES:]))   # cover the tail
    return out


def rerank(question: str, candidates: list[Hit], k: int = 5) -> list[Hit]:
    if not candidates:
        return []
    pairs, owner = [], []
    for i, h in enumerate(candidates):
        for w in _windows(h):
            pairs.append((question, w))
            owner.append(i)
    scores = _model().predict(pairs)

    best = [float("-inf")] * len(candidates)
    for i, s in zip(owner, scores):
        best[i] = max(best[i], float(s))      # MaxP: a chunk is as good as its best window
    ranked = sorted(range(len(candidates)), key=lambda i: (-best[i], candidates[i].chunk_id))
    return [replace(candidates[i], score=best[i]) for i in ranked[:k]]