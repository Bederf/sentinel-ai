"""Shared state contract for the advisory kernel scaffold."""

from __future__ import annotations

from typing import Annotated, Any, TypedDict
from uuid import uuid4

from langchain_core.messages import BaseMessage, HumanMessage
from langgraph.graph.message import add_messages


class DomainContext(TypedDict, total=False):
    """Explicit domain context for a kernel thread."""

    conversation_id: str
    site_id: str
    equipment_id: str
    zone: str
    time_range: dict[str, str]
    requested_output: str


class PendingApproval(TypedDict, total=False):
    """Stub approval payload for future HITL work."""

    status: str
    reason: str
    review_payload: dict[str, Any]
    resume_payload: dict[str, Any] | None


class OutputState(TypedDict, total=False):
    """Final user-facing output for the current kernel run."""

    request_id: str
    status: str
    summary: str
    next_step: str
    confidence_score: float
    escalation_reason: str | None


class EvidenceBundle(TypedDict, total=False):
    """Structured retrieval outputs shared across nodes."""

    hybrid: list[dict[str, Any]]
    brick: list[dict[str, Any]]
    docs: list[dict[str, Any]]
    memory: list[dict[str, Any]]
    notes: list[str]


class NodeTraceEntry(TypedDict, total=False):
    """Structured node execution event."""

    event: str
    node_name: str
    timestamp: str
    request_id: str
    input_summary: str
    output_summary: str
    metadata: dict[str, Any]


class ToolCallTraceEntry(TypedDict, total=False):
    """Structured tool execution event."""

    tool_name: str
    timestamp: str
    arguments_summary: str
    result_summary: str
    metadata: dict[str, Any]


class KernelErrorEntry(TypedDict, total=False):
    """Structured error payload."""

    code: str
    message: str
    timestamp: str
    node_name: str | None


class SentinelAgentState(TypedDict, total=False):
    """Trimmed state for the Phase 176 scaffold."""

    messages: Annotated[list[BaseMessage], add_messages]
    domain_context: DomainContext
    evidence_bundle: EvidenceBundle
    todos: list[str]
    files: dict[str, str]
    retrieval_iteration: int
    pending_approval: PendingApproval | None
    node_trace: list[NodeTraceEntry]
    tool_calls_trace: list[ToolCallTraceEntry]
    output_state: OutputState
    errors: list[KernelErrorEntry]


def new_kernel_state(
    *,
    message: str | None = None,
    conversation_id: str | None = None,
    mode: str = "investigation",
    site_id: str | None = None,
    equipment_id: str | None = None,
    zone: str | None = None,
    time_range: dict[str, str] | None = None,
) -> SentinelAgentState:
    """Create a stable initial state for a new kernel thread."""

    request_id = f"kernel-{uuid4().hex[:12]}"
    state: SentinelAgentState = {
        "messages": [HumanMessage(content=message)] if message else [],
        "domain_context": {
            "conversation_id": conversation_id or request_id,
            "requested_output": mode,
        },
        "evidence_bundle": {
            "hybrid": [],
            "brick": [],
            "docs": [],
            "memory": [],
            "notes": [],
        },
        "todos": [],
        "files": {},
        "retrieval_iteration": 0,
        "pending_approval": None,
        "node_trace": [],
        "tool_calls_trace": [],
        "output_state": {
            "request_id": request_id,
            "status": "initialized",
            "summary": "",
            "next_step": "",
            "confidence_score": 0.0,
            "escalation_reason": None,
        },
        "errors": [],
    }
    if site_id:
        state["domain_context"]["site_id"] = site_id
    if equipment_id:
        state["domain_context"]["equipment_id"] = equipment_id
    if zone:
        state["domain_context"]["zone"] = zone
    if time_range:
        state["domain_context"]["time_range"] = time_range
    return state


def get_request_id(state: SentinelAgentState) -> str:
    """Return the generated request identifier for a kernel run."""

    output_state = state.get("output_state") or {}
    request_id = output_state.get("request_id")
    if request_id:
        return request_id
    return "kernel-unknown"
