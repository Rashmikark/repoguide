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
from backend.app.onboarding.issues_service import build_issues
from backend.app.onboarding.overview import make_overview
from backend.app.onboarding.path_service import build_path
from backend.app.onboarding.quiz_service import build_quiz


class OnboardState(TypedDict, total=False):
    repo_id: int
    days: int
    hours_per_day: float
    facts: dict
    overview: dict
    path: dict
    issues: dict
    quiz: dict
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


def make_path(state: OnboardState, config: RunnableConfig) -> dict:
    facts = state.get("facts") or {}
    if not facts:
        return {"path": {}, "errors": ["path: skipped because facts are missing"]}
    try:
        return {"path": build_path(_conn(config), facts,
                                   state.get("days", 5), state.get("hours_per_day", 2.0))}
    except Exception as e:
        return {"path": {}, "errors": [_err("path", e)]}


def find_issues(state: OnboardState, config: RunnableConfig) -> dict:
    facts = state.get("facts") or {}
    if not facts:
        return {"issues": {}, "errors": ["issues: skipped because facts are missing"]}
    try:
        return {"issues": build_issues(_conn(config), facts)}
    except Exception as e:
        return {"issues": {}, "errors": [_err("issues", e)]}


def quiz_node(state: OnboardState, config: RunnableConfig) -> dict:
    facts = state.get("facts") or {}
    if not facts:
        return {"quiz": {}, "errors": ["quiz: skipped because facts are missing"]}
    try:
        return {"quiz": build_quiz(_conn(config), facts)}
    except Exception as e:
        return {"quiz": {}, "errors": [_err("quiz", e)]}


def build_graph():
    g = StateGraph(OnboardState)
    g.add_node("load_facts", load_facts)
    g.add_node("overview", overview)
    g.add_node("path", make_path)
    g.add_node("issues", find_issues)
    g.add_node("quiz", quiz_node)
    g.add_edge(START, "load_facts")
    g.add_edge("load_facts", "overview")
    g.add_edge("overview", "path")
    g.add_edge("path", "issues")
    g.add_edge("issues", "quiz")
    g.add_edge("quiz", END)
    return g.compile()