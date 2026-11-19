from backend.app.ingest.indexer import plan_index


def test_partly_embedded_same_commit_resumes():
    # The ky case: 800 of 1944 embedded when the daily quota ran out.
    assert plan_index("abc", 1944, 800, "abc") == "resume"


def test_fully_embedded_same_commit_rebuilds():
    # force re-index of a finished repo -> full rebuild
    assert plan_index("abc", 134, 134, "abc") == "full"


def test_new_commit_rebuilds():
    assert plan_index("abc", 1944, 800, "def") == "full"


def test_never_indexed_builds():
    assert plan_index(None, 0, 0, "abc") == "full"