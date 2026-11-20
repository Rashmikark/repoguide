"""Scoring rules from eval/README.md. Fixed before the first eval run."""
import math


# ---------- retrieval ----------

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


# ---------- answers ----------

def found_correct(found: bool, answerable: bool) -> bool:
    """found must be True for answerable questions and False for negative ones."""
    return found == answerable


def cites_gold(citations: list[dict], gold: list[dict]) -> bool:
    """At least one VALID citation overlaps a gold span. Invalid citations never count."""
    return any(
        c["valid"] and c["path"] and any(overlaps(c["path"], c["start"], c["end"], g) for g in gold)
        for c in citations
    )


def mean_citation_width(citations: list[dict]) -> float | None:
    """Average number of lines per valid citation (narrower = more useful)."""
    widths = [c["end"] - c["start"] + 1 for c in citations if c["valid"]]
    return sum(widths) / len(widths) if widths else None


def key_point_coverage(covered: list[bool]) -> float | None:
    """Share of key points the judge marked as covered. None if there are no key points."""
    return sum(covered) / len(covered) if covered else None