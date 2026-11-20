"""Onboarding graph: load_facts -> overview -> path -> issues -> quiz.
Every node is a stub for now; Steps 19-22 replace them one by one."""
import operator
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph


class OnboardState(TypedDict, total=False):
    # inputs
    repo_id: int
    days: int
    hours_per_day: int
    # added by the nodes
    facts: dict
    overview: dict
    path: dict
    issues: list
    quiz: list
    # every node may add problems here; the reducer JOINS lists instead of overwriting
    errors: Annotated[list[str], operator.add]


def load_facts(state: OnboardState) -> dict:
    return {"facts": {"repo_id": state["repo_id"], "files": [], "readme": ""}}


def make_overview(state: OnboardState) -> dict:
    return {"overview": {"text": "TODO: overview", "citations": []}}


def make_path(state: OnboardState) -> dict:
    days = [{"day": d, "title": f"TODO: day {d}", "files": []} for d in range(1, state["days"] + 1)]
    return {"path": {"days": days}}


def find_issues(state: OnboardState) -> dict:
    return {"issues": []}


def make_quiz(state: OnboardState) -> dict:
    return {"quiz": []}


def build_graph():
    builder = StateGraph(OnboardState)
    builder.add_node("load_facts", load_facts)
    builder.add_node("overview", make_overview)
    builder.add_node("path", make_path)
    builder.add_node("issues", find_issues)
    builder.add_node("quiz", make_quiz)
    builder.add_edge(START, "load_facts")
    builder.add_edge("load_facts", "overview")
    builder.add_edge("overview", "path")
    builder.add_edge("path", "issues")
    builder.add_edge("issues", "quiz")
    builder.add_edge("quiz", END)
    return builder.compile()