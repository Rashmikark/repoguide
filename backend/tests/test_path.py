import pytest

from backend.app.onboarding.path import plan_reading

FILES = [
    "README.md", "CHANGES.rst", ".github/x.md", "pyproject.toml",
    "docs/conf.py", "vite.config.ts", "tests/__init__.py",
    "src/pkg/__init__.py", "src/pkg/core.py", "src/pkg/sub/util.py",
    "tests/test_core.py", "docs/index.rst",
]
SIZES = {
    "README.md": 40,              # doc  -> 1 min  -> 5 (minimum)
    "docs/conf.py": 56,           # config -> left out
    "vite.config.ts": 20,         # config -> left out
    "tests/__init__.py": 0,       # empty  -> left out
    "src/pkg/__init__.py": 20,    # code -> 1 min  -> 5
    "src/pkg/core.py": 200,       # code -> 10 min
    "src/pkg/sub/util.py": 60,    # code -> 3 min  -> 5
    "tests/test_core.py": 100,    # code -> 5 min
    "docs/index.rst": 80,         # doc  -> 2 min  -> 5
}
ENTRY = ["src/pkg/__init__.py"]


def _plan(days=5, hours=2.0, sizes=SIZES):
    return plan_reading(FILES, sizes, ENTRY, "README.md", days, hours)


def _paths(plan):
    return [[it["path"] for it in d["items"]] for d in plan["days"]]


def test_reading_order():
    flat = [p for day in _paths(_plan()) for p in day]
    assert flat == ["README.md", "src/pkg/__init__.py", "src/pkg/core.py",
                    "src/pkg/sub/util.py", "tests/test_core.py", "docs/index.rst"]


def test_noise_files_left_out():
    plan = _plan()
    everything = [p for day in _paths(plan) for p in day] + plan["skipped"]
    for noise in ("CHANGES.rst", ".github/x.md", "pyproject.toml",
                  "docs/conf.py", "vite.config.ts", "tests/__init__.py"):
        assert noise not in everything


def test_one_short_day_skips_the_rest():
    plan = _plan(days=1, hours=0.5)          # 30 min: first five files are exactly 30
    assert len(plan["days"]) == 1 and plan["days"][0]["minutes"] == 30
    assert plan["skipped"] == ["docs/index.rst"]


def test_two_days_fill_in_order():
    plan = _plan(days=2, hours=0.25)         # 15 min per day
    assert _paths(plan) == [["README.md", "src/pkg/__init__.py"],
                            ["src/pkg/core.py", "src/pkg/sub/util.py"]]
    assert plan["skipped"] == ["tests/test_core.py", "docs/index.rst"]


def test_file_bigger_than_a_day_gets_own_day():
    big = dict(SIZES, **{"src/pkg/core.py": 2000})   # capped at 30 min, day is 15 min
    plan = _plan(days=3, hours=0.25, sizes=big)
    assert _paths(plan)[1] == ["src/pkg/core.py"]
    assert plan["days"][1]["over_budget"] is True
    assert plan["days"][0]["over_budget"] is False


def test_long_file_is_capped_and_marked_skim():
    big = dict(SIZES, **{"src/pkg/core.py": 2000})   # 100 min if read fully
    items = {it["path"]: it for d in _plan(sizes=big)["days"] for it in d["items"]}
    assert items["src/pkg/core.py"]["minutes"] == 30 and items["src/pkg/core.py"]["skim"] is True
    assert items["src/pkg/sub/util.py"]["skim"] is False


def test_empty_entry_point_is_kept():
    sizes = dict(SIZES, **{"src/pkg/__init__.py": 0})
    second = _plan(sizes=sizes)["days"][0]["items"][1]
    assert second["path"] == "src/pkg/__init__.py" and second["lines"] == 0


def test_missing_size_uses_minimum():
    plan = _plan(sizes={})
    first = plan["days"][0]["items"][0]
    assert first["lines"] == 0 and first["minutes"] == 5


@pytest.mark.parametrize("days,hours", [(0, 2), (31, 2), (5, 0.1), (5, 20)])
def test_bad_inputs_rejected(days, hours):
    with pytest.raises(ValueError):
        _plan(days=days, hours=hours)