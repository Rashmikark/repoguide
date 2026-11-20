"""Reading-order planner. Code decides WHICH files and in WHAT order; no LLM here.

Reading speeds and the per-file cap are ASSUMPTIONS (not measurements) and are
returned in the result so the README can state them honestly.
"""
import math
from dataclasses import asdict, dataclass
from pathlib import PurePosixPath

from backend.app.onboarding.facts import is_test_path

CODE_LINES_PER_MINUTE = 20
DOC_LINES_PER_MINUTE = 40
MIN_MINUTES_PER_FILE = 5
MAX_MINUTES_PER_FILE = 30          # longer files are planned as "skim"

CODE_SUFFIXES = {".py", ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx"}
DOC_SUFFIXES = {".md", ".rst"}
SKIP_STEMS = {"changes", "changelog", "history", "license", "licence",
              "contributing", "code_of_conduct", "security"}
CONFIG_NAMES = {"conf.py", "setup.py", "noxfile.py", "fabfile.py", "gulpfile.js", "gruntfile.js"}
CONFIG_ENDINGS = (".config.js", ".config.ts", ".config.mjs", ".config.cjs")
GROUP_ORDER = ("readme", "entry", "core", "tests", "docs")

MAX_DAYS = 30
MIN_HOURS, MAX_HOURS = 0.25, 12


@dataclass
class PlanItem:
    path: str
    group: str
    lines: int
    minutes: int
    skim: bool = False


def _skip(path: str) -> bool:
    p = PurePosixPath(path)
    if any(part.startswith(".") for part in p.parts):
        return True
    name = p.name.lower()
    if name in CONFIG_NAMES or name.endswith(CONFIG_ENDINGS):
        return True
    return p.stem.lower() in SKIP_STEMS


def _group(path: str, readme_path: str | None, entry_points: list[str]) -> str | None:
    if path == readme_path:
        return "readme"
    if path in entry_points:
        return "entry"
    if _skip(path):
        return None
    suffix = PurePosixPath(path).suffix.lower()
    if suffix in CODE_SUFFIXES:
        return "tests" if is_test_path(path) else "core"
    if suffix in DOC_SUFFIXES:
        return "docs"
    return None


def _minutes(path: str, lines: int) -> tuple[int, bool]:
    """Returns (planned minutes, skim). Files longer than the cap are skimmed."""
    rate = DOC_LINES_PER_MINUTE if PurePosixPath(path).suffix.lower() in DOC_SUFFIXES else CODE_LINES_PER_MINUTE
    full = max(MIN_MINUTES_PER_FILE, math.ceil(lines / rate))
    return min(full, MAX_MINUTES_PER_FILE), full > MAX_MINUTES_PER_FILE


def order_files(files, sizes, entry_points, readme_path) -> list[PlanItem]:
    entry_dirs = {str(PurePosixPath(e).parent) for e in entry_points}

    def key(path: str):
        p = PurePosixPath(path)
        return (0 if str(p.parent) in entry_dirs else 1, len(p.parts), path)

    groups: dict[str, list[PlanItem]] = {g: [] for g in GROUP_ORDER}
    for path in files:
        g = _group(path, readme_path, entry_points)
        if g is None:
            continue
        lines = int(sizes.get(path, 0))
        if lines == 0 and g not in ("readme", "entry"):
            continue                 # empty file: nothing to read
        minutes, skim = _minutes(path, lines)
        groups[g].append(PlanItem(path, g, lines, minutes, skim))

    groups["entry"].sort(key=lambda it: entry_points.index(it.path))
    for g in ("core", "tests", "docs"):
        groups[g].sort(key=lambda it: key(it.path))
    return [it for g in GROUP_ORDER for it in groups[g]]


def plan_reading(files, sizes, entry_points, readme_path, days: int, hours_per_day: float) -> dict:
    if not 1 <= days <= MAX_DAYS:
        raise ValueError(f"days must be 1-{MAX_DAYS}")
    if not MIN_HOURS <= hours_per_day <= MAX_HOURS:
        raise ValueError(f"hours_per_day must be {MIN_HOURS}-{MAX_HOURS}")

    cap = hours_per_day * 60
    days_out: list[dict] = []
    skipped: list[str] = []
    full = False
    for it in order_files(files, sizes, entry_points, readme_path):
        if full:
            skipped.append(it.path)
            continue
        need_new_day = not days_out or (
            days_out[-1]["items"] and days_out[-1]["minutes"] + it.minutes > cap)
        if need_new_day:
            if len(days_out) >= days:
                full = True          # out of days: this and every later file is skipped, order kept
                skipped.append(it.path)
                continue
            days_out.append({"day": len(days_out) + 1, "minutes": 0, "items": []})
        d = days_out[-1]
        d["items"].append(asdict(it))
        d["minutes"] += it.minutes

    for d in days_out:
        d["over_budget"] = d["minutes"] > cap
    return {
        "days": days_out,
        "skipped": skipped,
        "planned_minutes": sum(d["minutes"] for d in days_out),
        "budget_minutes": days * cap,
        "assumptions": {
            "code_lines_per_minute": CODE_LINES_PER_MINUTE,
            "doc_lines_per_minute": DOC_LINES_PER_MINUTE,
            "min_minutes_per_file": MIN_MINUTES_PER_FILE,
            "max_minutes_per_file": MAX_MINUTES_PER_FILE,
        },
    }