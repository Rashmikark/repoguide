from backend.app.onboarding.facts import (
    entry_point_guesses,
    find_readme,
    is_test_path,
    reconstruct_text,
    top_level_summary,
)

PATHS = [
    "README.md", "setup.py", "src/pkg/__init__.py", "src/pkg/core.py",
    "src/pkg/sub/main.py", "tests/test_core.py", "test/index.ts", "source/index.ts",
]


def test_is_test_path():
    assert is_test_path("tests/test_core.py")
    assert is_test_path("test/index.ts")
    assert is_test_path("src/a.spec.ts")
    assert not is_test_path("src/pkg/core.py")


def test_top_level_summary_biggest_first():
    assert list(top_level_summary(PATHS).items())[0] == ("src", 3)


def test_entry_points_skip_tests_and_prefer_shallow():
    assert entry_point_guesses(PATHS) == ["source/index.ts", "src/pkg/__init__.py", "src/pkg/sub/main.py"]


def test_find_readme_only_at_root():
    assert find_readme(PATHS) == "README.md"
    assert find_readme(["docs/README.md"]) is None


def test_reconstruct_text_handles_overlap_and_gaps():
    chunks = [(1, "a\nb\nc"), (3, "c\nd"), (6, "f")]   # overlap at line 3, gap at line 5
    assert reconstruct_text(chunks) == "a\nb\nc\nd\n\nf"