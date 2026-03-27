"""Read-only retrieval node for the advisory kernel."""

from __future__ import annotations

import json
import logging

from langchain_core.messages import HumanMessage

from app.agents_kernel.state import EvidenceBundle, SentinelAgentState
from app.agents_kernel.tools.file_tools import write_virtual_file
from app.database.repositories.agent_memory_repository import get_agent_memory_repository
from app.services.brick_service import get_brick_service
from app.services.doc_rag_service import search_documentation
from app.services.hybrid_query_service import get_hybrid_query_service

logger = logging.getLogger(__name__)


def _latest_message_text(state: SentinelAgentState) -> str:
    for message in reversed(state.get("messages", [])):
        if isinstance(message, HumanMessage):
            return str(message.content)
    return ""


async def retrieve_context_node(state: SentinelAgentState) -> dict:
    """Gather a bounded evidence bundle from approved read-only services."""

    domain_context = dict(state.get("domain_context", {}))
    evidence_bundle: EvidenceBundle = dict(state.get("evidence_bundle", {}))
    evidence_bundle.setdefault("hybrid", [])
    evidence_bundle.setdefault("brick", [])
    evidence_bundle.setdefault("docs", [])
    evidence_bundle.setdefault("memory", [])
    evidence_bundle.setdefault("notes", [])

    site_id = domain_context.get("site_id") or "site-002"
    equipment_id = domain_context.get("equipment_id")
    question = _latest_message_text(state) or equipment_id or site_id

    try:
        hybrid_service = get_hybrid_query_service(site_id)
        hybrid_context = await hybrid_service.query(
            equipment_id=equipment_id,
            question=question,
            include_decision_memory=False,
        )
        hybrid_dict = hybrid_context.to_dict()
        evidence_bundle["hybrid"] = [hybrid_dict]
    except Exception as exc:
        logger.warning("Kernel hybrid retrieval failed: %s", exc)
        evidence_bundle["notes"].append("hybrid_context_unavailable")

    try:
        if equipment_id:
            brick_service = get_brick_service(site_id)
            if brick_service:
                brick_context = brick_service.get_context(equipment_id, include_points=True)
                if brick_context:
                    evidence_bundle["brick"] = [brick_context.to_dict()]
                else:
                    evidence_bundle["notes"].append("brick_context_not_found")
            else:
                evidence_bundle["notes"].append("brick_service_unavailable")
        else:
            evidence_bundle["notes"].append("equipment_id_missing_for_brick_lookup")
    except Exception as exc:
        logger.warning("Kernel brick retrieval failed: %s", exc)
        evidence_bundle["notes"].append("brick_lookup_failed")

    try:
        docs = await search_documentation(query=question, n_results=3, site_id=site_id)
        evidence_bundle["docs"] = docs
        if not docs:
            evidence_bundle["notes"].append("documentation_context_empty")
    except Exception as exc:
        logger.warning("Kernel doc retrieval failed: %s", exc)
        evidence_bundle["notes"].append("documentation_lookup_failed")

    try:
        memory_repo = get_agent_memory_repository()
        if equipment_id:
            memories = memory_repo.get_by_equipment(equipment_id, limit=5)
        else:
            memories = memory_repo.get_by_site(site_id, limit=5)
        evidence_bundle["memory"] = memories
        if not memories:
            evidence_bundle["notes"].append("long_term_memory_empty")
    except Exception as exc:
        logger.warning("Kernel memory retrieval failed: %s", exc)
        evidence_bundle["notes"].append("long_term_memory_unavailable")

    files = dict(state.get("files", {}))
    files["evidence_bundle.json"] = json.dumps(evidence_bundle, default=str, indent=2, sort_keys=True)
    state["files"] = files
    state["evidence_bundle"] = evidence_bundle

    output_state = dict(state.get("output_state", {}))
    evidence_count = sum(len(evidence_bundle.get(key, [])) for key in ("hybrid", "brick", "docs", "memory"))
    confidence = 0.15
    if evidence_count >= 4:
        confidence = 0.7
    elif evidence_count >= 2:
        confidence = 0.45
    output_state["confidence_score"] = confidence
    output_state["status"] = "context_retrieved"
    output_state["escalation_reason"] = None if evidence_count >= 2 else "bounded_retrieval_returned_limited_evidence"
    state["output_state"] = output_state

    write_virtual_file(
        state,
        "retrieval_notes.md",
        "\n".join(evidence_bundle["notes"])
        if evidence_bundle["notes"]
        else "All bounded retrieval sources returned context.",
    )

    return {
        "evidence_bundle": evidence_bundle,
        "files": state["files"],
        "output_state": output_state,
        "tool_calls_trace": state["tool_calls_trace"],
    }
