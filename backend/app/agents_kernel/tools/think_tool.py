"""Bounded reflection helper for the advisory kernel."""

from __future__ import annotations

from app.agents_kernel.state import SentinelAgentState
from app.agents_kernel.trace import record_tool_call


def think_step(state: SentinelAgentState, note: str, *, max_length: int = 240) -> str:
    """Record a short bounded reflection note in tool trace."""

    bounded = note.strip()[:max_length]
    record_tool_call(
        state,
        "think_step",
        arguments_summary=bounded,
        result_summary="reflection recorded",
    )
    return bounded
