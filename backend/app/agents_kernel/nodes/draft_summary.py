"""Summary node for the bounded advisory kernel graph."""

from __future__ import annotations

from typing import cast

from app.agents_kernel.state import OutputState, SentinelAgentState
from app.services.model_gateway import model_gateway


async def draft_summary_node(state: SentinelAgentState) -> dict:
    """Generate a short operator-facing summary from structured evidence."""

    evidence_bundle = state.get("evidence_bundle", {})
    output_state = cast(OutputState, dict(state.get("output_state", {})))
    raw_confidence = output_state.get("confidence_score", 0.0)
    confidence = float(raw_confidence) if isinstance(raw_confidence, (int, float)) else 0.0
    evidence_notes = evidence_bundle.get("notes", [])
    evidence_counts = {
        "hybrid": len(evidence_bundle.get("hybrid", [])),
        "brick": len(evidence_bundle.get("brick", [])),
        "docs": len(evidence_bundle.get("docs", [])),
        "memory": len(evidence_bundle.get("memory", [])),
    }

    prompt = (
        "You are SENTINEL's advisory kernel. Produce a short operator-facing summary using only the "
        "structured evidence provided. State uncertainty explicitly. Do not recommend actions, do not "
        "invent missing facts, and keep the response under 120 words.\n\n"
        f"Evidence counts: {evidence_counts}\n"
        f"Evidence notes: {evidence_notes}\n"
        f"Requested output: {(state.get('domain_context') or {}).get('requested_output', 'investigation')}\n"
        f"Structured evidence: {evidence_bundle}"
    )

    summary = await model_gateway.call(
        task_class="light",
        messages=[{"role": "user", "content": prompt}],
        system="Produce concise operational summaries grounded only in supplied evidence.",
        stream=False,
    )

    output_state["summary"] = str(summary).strip()
    if confidence < 0.5 and not output_state.get("escalation_reason"):
        output_state["escalation_reason"] = "summary_generated_from_limited_evidence"
    state["output_state"] = output_state

    return {"output_state": output_state}
