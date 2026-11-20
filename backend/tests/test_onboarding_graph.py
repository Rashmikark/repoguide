import operator
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph

from backend.app.onboarding.graph import build_graph


def test_graph_runs_every_step():
    result = build_graph().invoke({"repo_id": 1, "days": 3, "hours_per_day": 2, "errors": []})
    for key in ("facts", "overview", "path", "issues", "quiz"):
        assert key in result
    assert len(result["path"]["days"]) == 3
    assert result["errors"] == []


def test_errors_from_several_steps_are_all_kept():
    # The reducer must JOIN error lists from different steps, not overwrite them.
    class S(TypedDict, total=False):
        errors: Annotated[list[str], operator.add]

    b = StateGraph(S)
    b.add_node("a", lambda s: {"errors": ["a failed"]})
    b.add_node("b", lambda s: {"errors": ["b failed"]})
    b.add_edge(START, "a")
    b.add_edge("a", "b")
    b.add_edge("b", END)
    assert b.compile().invoke({"errors": []})["errors"] == ["a failed", "b failed"]