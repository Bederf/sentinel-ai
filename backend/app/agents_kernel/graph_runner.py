"""Graph runner for the advisory kernel scaffold."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from time import perf_counter
from typing import Any

from langgraph.graph import END, START, StateGraph

from app.agents_kernel.checkpointer import get_default_checkpointer, get_thread_config
from app.agents_kernel.nodes import draft_summary_node, finalize_node, intake_node, retrieve_context_node
from app.agents_kernel.state import SentinelAgentState, get_request_id, new_kernel_state
from app.agents_kernel.trace import record_error, record_node_end, record_node_start
from app.config.settings import settings
from app.services.model_gateway import model_gateway

NodeCallable = Callable[[SentinelAgentState], SentinelAgentState | dict[str, Any]]
_runtime_checkpointer = get_default_checkpointer()
_compiled_graph = None


def _summarize_state(state: SentinelAgentState) -> str:
    return (
        f"messages={len(state.get('messages', []))}, "
        f"evidence={sum(len((state.get('evidence_bundle') or {}).get(key, [])) for key in ('hybrid', 'brick', 'docs', 'memory'))}, "
        f"todos={len(state.get('todos', []))}, "
        f"files={len(state.get('files', {}))}, "
        f"errors={len(state.get('errors', []))}"
    )


def _summarize_updates(updates: dict[str, Any]) -> str:
    return ", ".join(sorted(updates.keys())) if updates else "no state changes"


def _resolve_model_metadata(state: SentinelAgentState) -> dict[str, Any]:
    router_name = settings.sentinel_advisory_model_router
    selected_class = "light"
    routing_reason = "default_lightweight_local_path"
    escalation_trigger = ""
    hitl_required = bool(state.get("pending_approval"))
    _mode, provider, model = model_gateway._resolve(selected_class)
    evidence_bundle = state.get("evidence_bundle") or {}
    evidence_present = {key: len(evidence_bundle.get(key, [])) for key in ("hybrid", "brick", "docs", "memory")}
    return {
        "selected_model": model,
        "selected_provider": provider,
        "selected_task_class": selected_class,
        "routing_reason": routing_reason,
        "confidence_score": (state.get("output_state") or {}).get("confidence_score", 0.0),
        "evidence_present": evidence_present,
        "evidence_missing": list(evidence_bundle.get("notes", [])),
        "escalation_trigger": escalation_trigger,
        "hitl_required": hitl_required,
        "router_name": router_name,
    }


def _wrap_node(node_name: str, node_fn: NodeCallable):
    async def _wrapped(state: SentinelAgentState) -> dict[str, Any]:
        start_time = perf_counter()
        metadata = _resolve_model_metadata(state)
        record_node_start(
            state,
            node_name,
            input_summary=_summarize_state(state),
            metadata=metadata,
        )
        try:
            result = node_fn(state)
            if inspect.isawaitable(result):
                updates = await result
            else:
                updates = result
            if updates is None:
                updates = {}
        except Exception as exc:
            record_error(state, str(exc), node_name=node_name, code="node_failure")
            failure_metadata = dict(metadata)
            failure_metadata["latency_ms"] = round((perf_counter() - start_time) * 1000, 2)
            record_node_end(
                state,
                node_name,
                output_summary="node failed",
                metadata=failure_metadata,
            )
            raise

        merged_state = dict(state)
        merged_state.update(updates)
        final_metadata = _resolve_model_metadata(merged_state)
        final_metadata["latency_ms"] = round((perf_counter() - start_time) * 1000, 2)
        record_node_end(
            merged_state,
            node_name,
            output_summary=_summarize_updates(updates),
            metadata=final_metadata,
        )
        updates["node_trace"] = merged_state["node_trace"]
        if "errors" in merged_state:
            updates["errors"] = merged_state["errors"]
        return updates

    return _wrapped


def build_smoke_graph() -> StateGraph:
    """Build the bounded advisory kernel graph."""

    graph = StateGraph(SentinelAgentState)
    graph.add_node("intake_node", _wrap_node("intake_node", intake_node))
    graph.add_node("retrieve_context_node", _wrap_node("retrieve_context_node", retrieve_context_node))
    graph.add_node("draft_summary_node", _wrap_node("draft_summary_node", draft_summary_node))
    graph.add_node("finalize_node", _wrap_node("finalize_node", finalize_node))
    graph.add_edge(START, "intake_node")
    graph.add_edge("intake_node", "retrieve_context_node")
    graph.add_edge("retrieve_context_node", "draft_summary_node")
    graph.add_edge("draft_summary_node", "finalize_node")
    graph.add_edge("finalize_node", END)
    return graph


def compile_graph(checkpointer=None):
    """Compile the smoke graph with the supplied checkpointer."""

    global _compiled_graph
    graph = build_smoke_graph()
    if checkpointer is not None:
        return graph.compile(checkpointer=checkpointer)
    if _compiled_graph is None:
        _compiled_graph = graph.compile(checkpointer=_runtime_checkpointer)
    return _compiled_graph


def reset_runtime_graph() -> None:
    """Reset the cached runtime graph and checkpointer for tests."""

    global _compiled_graph, _runtime_checkpointer
    _runtime_checkpointer = get_default_checkpointer()
    _compiled_graph = None


async def run_smoke_graph(
    *,
    message: str,
    conversation_id: str | None = None,
    mode: str = "investigation",
    site_id: str | None = None,
    equipment_id: str | None = None,
    zone: str | None = None,
    time_range: dict[str, str] | None = None,
):
    """Run the smoke graph and return final state."""

    compiled = compile_graph()
    initial_state = new_kernel_state(
        message=message,
        conversation_id=conversation_id,
        mode=mode,
        site_id=site_id,
        equipment_id=equipment_id,
        zone=zone,
        time_range=time_range,
    )
    final_state = await compiled.ainvoke(initial_state, config=get_thread_config(conversation_id))
    output_state = dict(final_state.get("output_state", {}))
    output_state.setdefault("request_id", get_request_id(final_state))
    final_state["output_state"] = output_state
    return final_state
