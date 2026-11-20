"""Scoring rules from eval/README.md. Fixed before the first eval run."""
import math


def overlaps(path: str, start: int, end: int, gold: dict) -> bool:
    """A hit is correct if it is in the same file and its line range overlaps a gold span."""
    return path == gold["path"] and start <= gold["end"] and gold["start"] <= end


def first_correct_rank(hits: list[dict], gold: list[dict]) -> int | None:
    """1-based rank of the first hit that overlaps any gold span, or None."""
    for rank, h in enumerate(hits, start=1):
        if any(overlaps(h["path"], h["start"], h["end"], g) for g in gold):
            return rank
    return None


def recall_at_k(ranks: list[int | None], k: int) -> float:
    """Share of questions with a correct hit in the top k."""
    if not ranks:
        return 0.0
    return sum(1 for r in ranks if r is not None and r <= k) / len(ranks)


def mrr(ranks: list[int | None]) -> float:
    """Mean reciprocal rank: 1/rank of the first correct hit, 0 if none."""
    if not ranks:
        return 0.0
    return sum(1 / r for r in ranks if r is not None) / len(ranks)


def percentile(values: list[float], p: float) -> float | None:
    """Nearest-rank percentile (p in 0-100). None for an empty list."""
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, math.ceil(p / 100 * len(ordered)) - 1)
    return ordered[index]