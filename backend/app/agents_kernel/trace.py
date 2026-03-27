"""Structured trace helpers for advisory kernel state."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.agents_kernel.state import (
    KernelErrorEntry,
    NodeTraceEntry,
    SentinelAgentState,
    ToolCallTraceEntry,
    get_request_id,
)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def record_node_start(
    state: SentinelAgentState,
    node_name: str,
    *,
    input_summary: str = "",
    metadata: dict[str, Any] | None = None,
) -> NodeTraceEntry:
    """Append a node-start trace entry to state."""

    entry: NodeTraceEntry = {
        "event": "node_start",
        "node_name": node_name,
        "timestamp": _utc_now(),
        "request_id": get_request_id(state),
        "input_summary": input_summary,
        "output_summary": "",
        "metadata": metadata or {},
    }
    node_trace = state.get("node_trace")
    if node_trace is None:
        node_trace = []
        state["node_trace"] = node_trace
    node_trace.append(entry)
    return entry


def record_node_end(
    state: SentinelAgentState,
    node_name: str,
    *,
    output_summary: str = "",
    metadata: dict[str, Any] | None = None,
) -> NodeTraceEntry:
    """Append a node-end trace entry to state."""

    entry: NodeTraceEntry = {
        "event": "node_end",
        "node_name": node_name,
        "timestamp": _utc_now(),
        "request_id": get_request_id(state),
        "input_summary": "",
        "output_summary": output_summary,
        "metadata": metadata or {},
    }
    node_trace = state.get("node_trace")
    if node_trace is None:
        node_trace = []
        state["node_trace"] = node_trace
    node_trace.append(entry)
    return entry


def record_tool_call(
    state: SentinelAgentState,
    tool_name: str,
    *,
    arguments_summary: str = "",
    result_summary: str = "",
    metadata: dict[str, Any] | None = None,
) -> ToolCallTraceEntry:
    """Append a tool-call trace entry to state."""

    entry: ToolCallTraceEntry = {
        "tool_name": tool_name,
        "timestamp": _utc_now(),
        "arguments_summary": arguments_summary,
        "result_summary": result_summary,
        "metadata": metadata or {},
    }
    tool_calls_trace = state.get("tool_calls_trace")
    if tool_calls_trace is None:
        tool_calls_trace = []
        state["tool_calls_trace"] = tool_calls_trace
    tool_calls_trace.append(entry)
    return entry


def record_error(
    state: SentinelAgentState,
    message: str,
    *,
    code: str = "kernel_error",
    node_name: str | None = None,
) -> KernelErrorEntry:
    """Append an error entry to state."""

    entry: KernelErrorEntry = {
        "code": code,
        "message": message,
        "timestamp": _utc_now(),
        "node_name": node_name,
    }
    errors = state.get("errors")
    if errors is None:
        errors = []
        state["errors"] = errors
    errors.append(entry)
    return entry
