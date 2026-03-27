"""Deterministic intake node for the advisory kernel."""

from __future__ import annotations

import re

from langchain_core.messages import HumanMessage

from app.agents_kernel.state import SentinelAgentState
from app.agents_kernel.tools.file_tools import write_virtual_file
from app.agents_kernel.tools.todo_tools import write_todos

_SITE_ID_RE = re.compile(r"\bsite-\d{3}\b", re.IGNORECASE)
_EQUIPMENT_ID_RE = re.compile(r"\bS\d{3}-[A-Z0-9]+(?:-[A-Z0-9]+)+\b")
_SHORT_EQUIPMENT_RE = re.compile(r"\b[A-Z]{2,5}-\d+\b")
_LAST_RANGE_RE = re.compile(r"\blast\s+(\d+)\s+(hour|hours|day|days)\b", re.IGNORECASE)


def _latest_message_text(state: SentinelAgentState) -> str:
    for message in reversed(state.get("messages", [])):
        if isinstance(message, HumanMessage):
            return str(message.content)
    return ""


def intake_node(state: SentinelAgentState) -> dict:
    """Normalize the request and initialize domain context."""

    message = _latest_message_text(state)
    domain_context = dict(state.get("domain_context", {}))
    requested_output = domain_context.get("requested_output", "investigation")
    if requested_output not in {"investigation", "reporting"}:
        requested_output = "investigation"
    domain_context["requested_output"] = requested_output

    site_match = _SITE_ID_RE.search(message)
    if site_match and not domain_context.get("site_id"):
        domain_context["site_id"] = site_match.group(0).lower()

    equipment_match = _EQUIPMENT_ID_RE.search(message) or _SHORT_EQUIPMENT_RE.search(message)
    if equipment_match and not domain_context.get("equipment_id"):
        domain_context["equipment_id"] = equipment_match.group(0)

    time_range_match = _LAST_RANGE_RE.search(message)
    if time_range_match:
        domain_context["time_range"] = {"relative": f"last {time_range_match.group(1)} {time_range_match.group(2)}"}

    write_todos(
        state,
        [
            "Gather allowed context sources",
            "Draft a bounded operator-facing summary",
        ],
    )
    write_virtual_file(
        state,
        "intake_request.txt",
        message or "No user message was present in the kernel state.",
    )

    output_state = dict(state.get("output_state", {}))
    output_state["status"] = "running"
    state["domain_context"] = domain_context
    state["output_state"] = output_state

    return {
        "domain_context": domain_context,
        "todos": state["todos"],
        "files": state["files"],
        "output_state": output_state,
        "tool_calls_trace": state["tool_calls_trace"],
    }
