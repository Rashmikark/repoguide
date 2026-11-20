"""Onboarding graph: load_facts -> overview -> path -> issues -> quiz.

The DB connection is passed in config["configurable"]["conn"], never in the state:
the state holds only plain data. A failing node records a message in `errors`
(merged by the operator.add reducer) instead of crashing the whole graph.
"""
import operator
from typing import Annotated, TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph

from backend.app.onboarding.facts import load_repo_facts
from backend.app.onboarding.overview import make_overview


class OnboardState(TypedDict, total=False):
    repo_id: int
    days: int
    hours_per_day: float
    facts: dict
    overview: dict
    path: list
    issues: list
    quiz: list
    errors: Annotated[list[str], operator.add]


def _conn(config: RunnableConfig | None):
    conn = ((config or {}).get("configurable") or {}).get("conn")
    if conn is None:
        raise RuntimeError("no database connection in config['configurable']['conn']")
    return conn


def _err(node: str, e: Exception) -> str:
    return f"{node}: {type(e).__name__}: {e}"


def load_facts(state: OnboardState, config: RunnableConfig) -> dict:
    try:
        return {"facts": load_repo_facts(_conn(config), state["repo_id"])}
    except Exception as e:
        return {"facts": {}, "errors": [_err("load_facts", e)]}


def overview(state: OnboardState, config: RunnableConfig) -> dict:
    facts = state.get("facts") or {}
    if not facts:
        return {"overview": {}, "errors": ["overview: skipped because facts are missing"]}
    try:
        return {"overview": make_overview(_conn(config), facts)}
    except Exception as e:
        return {"overview": {}, "errors": [_err("overview", e)]}


# Still stubs - replaced in Steps 20, 21 and 22.
def make_path(state: OnboardState) -> dict:
    return {"path": []}


def find_issues(state: OnboardState) -> dict:
    return {"issues": []}


def make_quiz(state: OnboardState) -> dict:
    return {"quiz": []}


def build_graph():
    g = StateGraph(OnboardState)
    g.add_node("load_facts", load_facts)
    g.add_node("overview", overview)
    g.add_node("path", make_path)
    g.add_node("issues", find_issues)
    g.add_node("quiz", make_quiz)
    g.add_edge(START, "load_facts")
    g.add_edge("load_facts", "overview")
    g.add_edge("overview", "path")
    g.add_edge("path", "issues")
    g.add_edge("issues", "quiz")
    g.add_edge("quiz", END)
    return g.compile()