from backend.app.links import github_line_url


def test_line_range():
    url = github_line_url("https://github.com/o/r", "abc123", "src/a.py", 10, 20)
    assert url == "https://github.com/o/r/blob/abc123/src/a.py#L10-L20"


def test_single_line():
    url = github_line_url("https://github.com/o/r", "abc123", "a.py", 5, 5)
    assert url.endswith("/a.py#L5")


def test_space_in_path_is_escaped():
    url = github_line_url("https://github.com/o/r", "abc123", "docs/my file.py", 1, 2)
    assert "docs/my%20file.py" in url