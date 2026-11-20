from backend.app.onboarding.overview import known_path

FILES = ["README.md", "src/pkg/__init__.py", "src/pkg/core.py", "tests/test_core.py"]
TOP = {"src": 2, "tests": 1, "(root)": 1}


def test_real_files_and_folders_are_known():
    assert known_path("README.md", FILES, TOP)
    assert known_path("src", FILES, TOP)
    assert known_path("src/pkg/", FILES, TOP)        # trailing slash allowed
    assert known_path("src/pkg/core.py", FILES, TOP)


def test_invented_paths_are_flagged():
    assert not known_path("lib", FILES, TOP)
    assert not known_path("src/pkg/utils.py", FILES, TOP)
    assert not known_path("src/pk", FILES, TOP)       # a prefix of a real folder is not a folder