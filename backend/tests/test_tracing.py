from backend.app.tracing import _safe, current_trace_id, trace_request


def test_missing_method_never_raises():
    # The exact bug we hit: a method that doesn't exist in this SDK version.
    assert _safe("this_method_does_not_exist", foo=1) is None


def test_trace_helpers_never_raise_outside_a_trace():
    trace_request(name="x", tags=["y"], input={"q": 1}, output={"a": 2})
    assert current_trace_id() is None or isinstance(current_trace_id(), str)