"""Practice: a 2-step LangGraph graph with no AI, to learn state, nodes and edges."""
from typing import TypedDict

from langgraph.graph import END, START, StateGraph


# 1. STATE: the shared dictionary every step can read and add to.
class State(TypedDict, total=False):
    repo: str
    files: list[str]
    summary: str


# 2. NODES: plain functions. Each receives the state and returns ONLY what it adds.
def list_files(state: State) -> dict:
    return {"files": ["README.md", "src/main.py", "tests/test_main.py"]}


def summarize(state: State) -> dict:
    code_files = [f for f in state["files"] if f.endswith(".py")]
    return {"summary": f"{state['repo']} has {len(state['files'])} files, {len(code_files)} in Python"}


# 3. EDGES: the order the steps run in.
builder = StateGraph(State)
builder.add_node("list_files", list_files)
builder.add_node("summarize", summarize)
builder.add_edge(START, "list_files")
builder.add_edge("list_files", "summarize")
builder.add_edge("summarize", END)
graph = builder.compile()

result = graph.invoke({"repo": "demo/repo"})
print(result)