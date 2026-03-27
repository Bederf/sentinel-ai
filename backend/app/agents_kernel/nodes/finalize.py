"""Finalize node for the bounded advisory kernel graph."""

from __future__ import annotations

from app.agents_kernel.state import SentinelAgentState
from app.agents_kernel.tools.file_tools import list_virtual_files


def finalize_node(state: SentinelAgentState) -> dict:
    """Assemble the final advisory payload."""

    output_state = dict(state.get("output_state", {}))
    virtual_files = list_virtual_files(state)
    summary = output_state.get("summary") or "No summary was generated."
    confidence = output_state.get("confidence_score", 0.0)
    evidence_bundle = state.get("evidence_bundle", {})
    notes = evidence_bundle.get("notes", [])

    output_state["status"] = "completed"
    output_state["next_step"] = (
        "Review the bounded evidence bundle and decide whether broader investigation is required."
    )
    output_state["summary"] = (
        f"{summary}\n\n"
        f"Evidence sources: hybrid={len(evidence_bundle.get('hybrid', []))}, "
        f"brick={len(evidence_bundle.get('brick', []))}, docs={len(evidence_bundle.get('docs', []))}, "
        f"memory={len(evidence_bundle.get('memory', []))}. "
        f"Confidence={confidence:.2f}."
        + (f" Notes: {', '.join(notes)}." if notes else "")
        + f" Virtual files={len(virtual_files)}."
    )
    state["output_state"] = output_state
    return {
        "output_state": output_state,
        "tool_calls_trace": state["tool_calls_trace"],
    }
