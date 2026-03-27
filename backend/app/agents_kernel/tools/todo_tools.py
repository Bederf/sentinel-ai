"""State-backed todo helpers for the advisory kernel."""

from __future__ import annotations

from app.agents_kernel.state import SentinelAgentState
from app.agents_kernel.trace import record_tool_call


def write_todos(state: SentinelAgentState, todos: list[str], *, replace: bool = True) -> list[str]:
    """Write or extend todos in graph state."""

    current = list(state.get("todos", []))
    next_todos = list(todos) if replace else current + [todo for todo in todos if todo not in current]
    state["todos"] = next_todos
    record_tool_call(
        state,
        "write_todos",
        arguments_summary=f"{len(todos)} todos",
        result_summary=f"{len(next_todos)} todos stored",
    )
    return next_todos


def read_todos(state: SentinelAgentState) -> list[str]:
    """Read todos from graph state."""

    todos = list(state.get("todos", []))
    record_tool_call(
        state,
        "read_todos",
        arguments_summary="current todos",
        result_summary=f"{len(todos)} todos returned",
    )
    return todos
