import pytest

from backend.app.ingest.repo_loader import GitHubUnavailable, RepoNotFound, classify_ls_remote


def test_success_returns_sha():
    assert classify_ls_remote(0, "abc123\tHEAD\n", "") == "abc123"


def test_empty_repo_returns_none():
    assert classify_ls_remote(0, "", "") is None


def test_missing_repo_is_not_found():
    err = "fatal: could not read Username for 'https://github.com': terminal prompts disabled"
    with pytest.raises(RepoNotFound):
        classify_ls_remote(128, "", err)


def test_network_error_is_unavailable():
    err = "fatal: unable to access 'https://github.com/x/y.git/': Could not resolve host: github.com"
    with pytest.raises(GitHubUnavailable):
        classify_ls_remote(128, "", err)


def test_unknown_error_is_unavailable_not_404():
    with pytest.raises(GitHubUnavailable):
        classify_ls_remote(128, "", "")