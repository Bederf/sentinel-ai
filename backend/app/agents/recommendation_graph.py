"""Recommendation Validation & Execution Agent (LangGraph)
==========================================================
System-initiated (proactive) LangGraph agent that processes pending
recommendations through the complete lifecycle:

  fetch_pending -> validate_relevance -> assess_impact -> check_schedule
  -> route_tier -> [log_advisory | request_approval | auto_execute]
  -> submit_feedback -> format_result -> END

Graph architecture:
  START -> fetch_pending
  fetch_pending -> (no recs?) -> format_result -> END
  fetch_pending -> validate_relevance
  validate_relevance -> (stale?) -> mark_expired -> END
  validate_relevance -> assess_impact
  assess_impact -> check_schedule
  check_schedule -> (conflict?) -> defer -> END
  check_schedule -> route_tier
  route_tier -> log_advisory (Tier 1)
  route_tier -> request_approval (Tier 2)  # sets needs_input=True -> END
  route_tier -> auto_execute (Tier 3)
  log_advisory -> submit_feedback -> format_result -> END
  auto_execute -> submit_feedback -> format_result -> END
  request_approval -> END  (wait for WhatsApp/Telegram reply)

  Resume after Tier 2 reply:
  handle_approval_response -> submit_feedback -> format_result -> END

All nodes are thin wrappers around existing services.
LLM usage: Zero. The graph is entirely deterministic Python.
"""

import logging
from typing import Annotated, TypedDict

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages

from app.agents.recommendation_formatters import (
    format_advisory_for_chat,
    format_advisory_for_system,
    format_approval_request_telegram,
    format_approval_request_whatsapp,
    format_execution_result,
)
from app.agents.recommendation_tools import (
    check_recommendation_action_still_needed,
    check_equipment_health,
    check_maintenance_calendar,
    check_recommendation_freshness,
    estimate_cost_impact,
    execute_approved_recommendation,
    execute_tier3_auto,
    get_pending_recommendations,
    reject_recommendation,
    route_through_tier_engine,
    submit_feedback_to_model,
    update_recommendation_status,
)

logger = logging.getLogger(__name__)


MAINTENANCE_ACTION_TYPES = {
    "health_maintenance",
    "maintenance",
    "maintenance_schedule",
    "inspect",
    "repair",
    "replace",
    "schedule_maintenance",
}


# ---------------------------------------------------------------------------
# State Schema
# ---------------------------------------------------------------------------


class RecommendationAgentState(TypedDict):
    """State for the recommendation validation & execution agent."""

    messages: Annotated[list, add_messages]  # LangGraph message history

    # Input
    site_id: str
    channel: str  # "system" | "whatsapp" | "telegram" | "chat"
    trigger: str  # "scheduled" | "manual" | "health_alert"

    # Recommendation being processed
    recommendation_id: str | None
    recommendation: dict | None  # Full Recommendation.to_dict()

    # Validation
    is_relevant: bool
    relevance_reason: str

    # Impact assessment
    impact: dict | None  # cost_zar, energy_kwh, comfort_delta, risk
    similar_faults: list  # Cross-referenced similar past faults

    # Schedule check
    schedule_conflict: bool
    conflict_details: str | None

    # Tier routing
    tier_result: dict | None  # TierRoutingResult fields
    tier: str | None  # "tier1" | "tier2" | "tier3"

    # Execution
    execution_result: dict | None  # ApprovalResult fields
    approval_status: str | None  # "pending" | "approved" | "rejected"

    # Feedback
    feedback_submitted: bool

    # Output
    response: str  # Final formatted result
    needs_input: bool  # True = waiting for Tier 2 approval
    processing_complete: bool  # True = all done


# ---------------------------------------------------------------------------
# Node: fetch_pending
# ---------------------------------------------------------------------------


async def fetch_pending_node(state: RecommendationAgentState) -> dict:
    """Fetch the next pending recommendation for the site."""
    site_id = state.get("site_id", "")
    if not site_id:
        return {
            "recommendation": None,
            "recommendation_id": None,
            "messages": [AIMessage(content="No site_id provided")],
        }

    recs = await get_pending_recommendations(site_id, limit=1)

    if not recs:
        return {
            "recommendation": None,
            "recommendation_id": None,
            "messages": [AIMessage(content=f"No pending recommendations for {site_id}")],
        }

    rec = recs[0]
    rec_id = rec.get("id", "")
    equipment = rec.get("target_equipment", "")

    logger.info(f"[RecAgent] Fetched pending recommendation {rec_id} for {equipment}")

    return {
        "recommendation": rec,
        "recommendation_id": rec_id,
        "messages": [AIMessage(content=f"Processing recommendation {rec_id} for {equipment}")],
    }


# ---------------------------------------------------------------------------
# Conditional edge: has_recommendation
# ---------------------------------------------------------------------------


def has_recommendation(state: RecommendationAgentState) -> str:
    """Check if we fetched a recommendation to process."""
    if state.get("recommendation"):
        return "has_rec"
    return "no_rec"


# ---------------------------------------------------------------------------
# Node: validate_relevance
# ---------------------------------------------------------------------------


async def validate_relevance_node(state: RecommendationAgentState) -> dict:
    """Check if recommendation is still relevant (not stale, equipment still unhealthy)."""
    rec = state.get("recommendation", {})
    if not rec:
        return {"is_relevant": False, "relevance_reason": "No recommendation"}

    # Advisory-type recs represent persistent operational conditions (e.g., HVAC-SCHEDULE
    # runs after-hours for 8-12h). Use a 24h freshness window so they don't get cycled
    # out before the underlying condition resolves.
    rec_metadata = rec.get("metadata") or {}
    rec_source_meta = rec_metadata.get("source_metadata") or {}
    _advisory_type = rec_source_meta.get("advisory_type") or rec_metadata.get("advisory_type")
    _is_advisory_rec = _advisory_type in {
        "site_profile_hvac_state_correction",
        "fault_safety_gate",
        "zone_scope_concrete_hvac_action",
    }
    freshness_max_minutes = 24 * 60 if _is_advisory_rec else 120
    freshness = check_recommendation_freshness(rec, max_age_minutes=freshness_max_minutes)
    if not freshness["is_fresh"]:
        logger.info(f"[RecAgent] Recommendation {rec.get('id')} is stale: {freshness['reason']}")
        return {
            "is_relevant": False,
            "relevance_reason": freshness["reason"],
        }

    # Check equipment health — only proceed if equipment is still unhealthy
    equipment_code = rec.get("target_equipment", "")
    if equipment_code:
        health = await check_equipment_health(equipment_code)
        health_score = health.get("health_score")
        health_checked = health.get("checked", True) is not False
        action_type = str(rec.get("action_type") or "")
        if (
            health_checked
            and health_score is not None
            and health_score >= 80
            and action_type in MAINTENANCE_ACTION_TYPES
        ):
            reason = f"Equipment {equipment_code} health recovered to {health_score}%; maintenance recommendation no longer valid"
            logger.info("[RecAgent] Recommendation %s is moot: %s", rec.get("id"), reason)
            return {
                "is_relevant": False,
                "relevance_reason": reason,
            }
        # Non-maintenance optimization can still be useful after health recovery.
        if health_checked and health_score is not None and health_score >= 80:
            logger.info(
                f"[RecAgent] Equipment {equipment_code} health recovered to {health_score}%, recommendation may be moot"
            )

    action_check = await check_recommendation_action_still_needed(rec)
    if not action_check["is_needed"]:
        reason = action_check["reason"]
        logger.info("[RecAgent] Recommendation %s is no longer needed: %s", rec.get("id"), reason)
        return {
            "is_relevant": False,
            "relevance_reason": reason,
        }

    return {
        "is_relevant": True,
        "relevance_reason": "Valid and fresh",
    }


# ---------------------------------------------------------------------------
# Conditional edge: check_relevance
# ---------------------------------------------------------------------------


def check_relevance(state: RecommendationAgentState) -> str:
    """Route based on relevance check."""
    if state.get("is_relevant"):
        return "valid"
    return "expired"


# ---------------------------------------------------------------------------
# Node: mark_expired
# ---------------------------------------------------------------------------


async def mark_expired_node(state: RecommendationAgentState) -> dict:
    """Mark stale recommendation as expired."""
    rec_id = state.get("recommendation_id", "")
    reason = state.get("relevance_reason", "Expired")

    if rec_id:
        await update_recommendation_status(rec_id, "expired")
        logger.info(f"[RecAgent] Marked recommendation {rec_id} as expired: {reason}")

    return {
        "response": f"Recommendation {rec_id} expired: {reason}",
        "processing_complete": True,
        "messages": [AIMessage(content=f"Expired: {reason}")],
    }


# ---------------------------------------------------------------------------
# Node: assess_impact
# ---------------------------------------------------------------------------


async def assess_impact_node(state: RecommendationAgentState) -> dict:
    """Calculate cost/energy/comfort impact and find similar past faults."""
    rec = state.get("recommendation", {})

    impact = await estimate_cost_impact(rec)

    # Cross-reference similar faults
    equipment_code = rec.get("target_equipment", "")
    action_type = rec.get("action_type", "")
    similar = []
    if equipment_code:
        from app.agents.recommendation_tools import cross_reference_similar_faults

        similar = await cross_reference_similar_faults(equipment_code, action_type)

    logger.info(
        f"[RecAgent] Impact for {rec.get('id')}: "
        f"cost=R{impact.get('cost_zar', 0):.2f}, "
        f"energy={impact.get('energy_kwh', 0):.1f}kWh, "
        f"similar_faults={len(similar)}"
    )

    return {
        "impact": impact,
        "similar_faults": similar,
    }


# ---------------------------------------------------------------------------
# Node: check_schedule
# ---------------------------------------------------------------------------


async def check_schedule_node(state: RecommendationAgentState) -> dict:
    """Check for maintenance schedule conflicts."""
    rec = state.get("recommendation", {})
    equipment_code = rec.get("target_equipment", "")

    if not equipment_code:
        return {"schedule_conflict": False, "conflict_details": None}

    calendar = await check_maintenance_calendar(equipment_code)

    if calendar["has_conflict"]:
        logger.info(f"[RecAgent] Schedule conflict for {equipment_code}: {calendar['reason']}")
        return {
            "schedule_conflict": True,
            "conflict_details": calendar["reason"],
        }

    return {"schedule_conflict": False, "conflict_details": None}


# ---------------------------------------------------------------------------
# Conditional edge: check_schedule_conflict
# ---------------------------------------------------------------------------


def check_schedule_conflict(state: RecommendationAgentState) -> str:
    """Route based on schedule conflict."""
    if state.get("schedule_conflict"):
        return "conflict"
    return "clear"


# ---------------------------------------------------------------------------
# Node: defer
# ---------------------------------------------------------------------------


async def defer_node(state: RecommendationAgentState) -> dict:
    """Expire recommendation when an active schedule conflict makes it invalid."""
    rec_id = state.get("recommendation_id", "")
    conflict = state.get("conflict_details", "Schedule conflict")

    if rec_id:
        await update_recommendation_status(rec_id, "expired")
        logger.info(f"[RecAgent] Expired recommendation {rec_id} due to schedule conflict: {conflict}")

    return {
        "response": f"Recommendation {rec_id} expired: {conflict}",
        "processing_complete": True,
        "messages": [AIMessage(content=f"Expired: {conflict}")],
    }


# ---------------------------------------------------------------------------
# Node: route_tier
# ---------------------------------------------------------------------------


async def route_tier_node(state: RecommendationAgentState) -> dict:
    """Route recommendation through PARASITE tier engine."""
    rec = state.get("recommendation", {})
    rec_id = state.get("recommendation_id", "")

    # Stamp IDs so TierRoutingEngine emits them to Loki events
    if rec_id:
        rec["recommendation_id"] = rec_id
        if "correlation_id" not in rec:
            rec["correlation_id"] = rec_id  # rec_id IS the correlation_id (set at creation)

    tier_result = await route_through_tier_engine(rec)
    tier = tier_result.get("tier", "tier1")

    logger.info(
        f"[RecAgent] Routed {rec.get('id')} to {tier} (confidence={tier_result.get('confidence_score', 0):.2f})"
    )

    # Propagate IDs from recommendation into tier_result for Loki traceability
    if rec_id:
        tier_result["recommendation_id"] = rec_id
        tier_result["correlation_id"] = rec.get("correlation_id") or rec_id
        tier_result["decision_id"] = tier_result.get("decision_id", "")

    return {
        "tier_result": tier_result,
        "tier": tier,
        "messages": [AIMessage(content=f"Routed to {tier}: {tier_result.get('reason', '')}")],
    }


# ---------------------------------------------------------------------------
# Conditional edge: tier_route
# ---------------------------------------------------------------------------


def tier_route(state: RecommendationAgentState) -> str:
    """Route to tier-specific handler."""
    tier = state.get("tier", "tier1")
    if tier == "tier3":
        return "tier3"
    elif tier == "tier2":
        return "tier2"
    return "tier1"


# ---------------------------------------------------------------------------
# Node: log_advisory (Tier 1)
# ---------------------------------------------------------------------------


async def log_advisory_node(state: RecommendationAgentState) -> dict:
    """Log Tier 1 advisory recommendation."""
    rec = state.get("recommendation", {})
    impact = state.get("impact", {})
    tier_result = state.get("tier_result", {})
    channel = state.get("channel", "system")

    if channel == "whatsapp":
        response = format_advisory_for_chat(rec, impact, tier_result)
    elif channel == "system":
        response = format_advisory_for_system(rec, impact, tier_result)
    else:
        response = format_advisory_for_chat(rec, impact, tier_result)

    logger.info(f"[RecAgent] Advisory logged for {rec.get('id')}")

    return {
        "approval_status": "advisory",
        "execution_result": {"status": "advisory", "success": True},
        "response": response,
        "messages": [AIMessage(content=response)],
    }


# ---------------------------------------------------------------------------
# Node: request_approval (Tier 2)
# ---------------------------------------------------------------------------


async def request_approval_node(state: RecommendationAgentState) -> dict:
    """Send Tier 2 approval request and wait for response."""
    rec = state.get("recommendation", {})
    impact = state.get("impact", {})
    tier_result = state.get("tier_result", {})
    channel = state.get("channel", "system")

    # Format approval request for appropriate channel
    if channel == "whatsapp":
        response = format_approval_request_whatsapp(rec, impact, tier_result)
    elif channel in ("telegram", "system"):
        response = format_approval_request_telegram(rec, impact, tier_result)
    else:
        response = format_approval_request_whatsapp(rec, impact, tier_result)

    # Send via WhatsApp if available
    try:
        if channel == "whatsapp":
            from app.integrations.whatsapp_service import get_whatsapp_service

            wa_service = get_whatsapp_service()
            if wa_service.enabled:
                # In a real deployment, we'd look up the technician's number
                # based on equipment type → specialty mapping
                logger.info(f"[RecAgent] WhatsApp approval request queued for {rec.get('id')}")
    except Exception as e:
        logger.warning(f"[RecAgent] Could not send WhatsApp approval: {e}")

    logger.info(f"[RecAgent] Approval requested for {rec.get('id')}, waiting for response")

    return {
        "approval_status": "pending",
        "needs_input": True,
        "response": response,
        "messages": [AIMessage(content=response)],
    }


# ---------------------------------------------------------------------------
# Node: auto_execute (Tier 3)
# ---------------------------------------------------------------------------


async def auto_execute_node(state: RecommendationAgentState) -> dict:
    """Auto-execute Tier 3 recommendation."""
    rec_id = state.get("recommendation_id", "")
    tier_result = state.get("tier_result", {})

    result = await execute_tier3_auto(rec_id, tier_result)

    success = result.get("success", False)
    status = result.get("status", "failed")

    rec = state.get("recommendation", {})
    channel = state.get("channel", "system")
    response = format_execution_result(rec, result, channel)

    logger.info(f"[RecAgent] Auto-executed {rec_id}: success={success}, status={status}")

    return {
        "execution_result": result,
        "approval_status": "auto_executed" if success else "failed",
        "response": response,
        "messages": [AIMessage(content=response)],
    }


# ---------------------------------------------------------------------------
# Node: handle_approval_response (resume after Tier 2 reply)
# ---------------------------------------------------------------------------


async def handle_approval_response_node(state: RecommendationAgentState) -> dict:
    """Handle Tier 2 approval/rejection response (called on resume)."""
    messages = state.get("messages", [])
    rec_id = state.get("recommendation_id", "")

    # Get the latest human message (the approval response)
    reply_text = ""
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            reply_text = msg.content.strip().upper()
            break

    if not reply_text:
        return {
            "response": "No response received.",
            "needs_input": True,
        }

    # Parse approval response
    if reply_text.startswith("APPROVE"):
        # Extract approver info from context
        result = await execute_approved_recommendation(
            recommendation_id=rec_id,
            approved_by="technician",  # In production, resolve from WhatsApp number
            notes="Approved via WhatsApp",
        )

        rec = state.get("recommendation", {})
        channel = state.get("channel", "system")
        response = format_execution_result(rec, result, channel)

        return {
            "execution_result": result,
            "approval_status": "approved",
            "needs_input": False,
            "response": response,
            "messages": [AIMessage(content=response)],
        }

    elif reply_text.startswith("REJECT"):
        # Extract reason (everything after "REJECT" or "REJECT REC-xxx")
        parts = reply_text.split(maxsplit=2)
        reason = parts[2] if len(parts) > 2 else parts[1] if len(parts) > 1 else "Rejected by technician"
        # Clean up: remove rec ID prefix if present
        if reason.startswith("REC-") or reason.startswith(rec_id[:8].upper()):
            parts2 = reason.split(maxsplit=1)
            reason = parts2[1] if len(parts2) > 1 else "Rejected by technician"

        result = await reject_recommendation(
            recommendation_id=rec_id,
            rejected_by="technician",
            reason=reason,
        )

        return {
            "execution_result": result,
            "approval_status": "rejected",
            "needs_input": False,
            "response": f"Recommendation {rec_id[:8]} rejected: {reason}",
            "messages": [AIMessage(content=f"Rejected: {reason}")],
        }

    else:
        return {
            "response": "Please reply with APPROVE or REJECT (with reason).",
            "needs_input": True,
            "messages": [AIMessage(content="Please reply with APPROVE or REJECT (with reason).")],
        }


# ---------------------------------------------------------------------------
# Node: submit_feedback
# ---------------------------------------------------------------------------


async def submit_feedback_node(state: RecommendationAgentState) -> dict:
    """Submit recommendation outcome to ML feedback loop."""
    rec = state.get("recommendation", {})
    rec_id = state.get("recommendation_id", "")
    approval_status = state.get("approval_status", "")
    execution_result = state.get("execution_result", {})

    # ApprovalService/RecommendationService already records module feedback for
    # approved/rejected/auto-executed outcomes. Avoid duplicate ML rows here.
    service_owned_statuses = {"approved", "rejected", "auto_executed"}
    if approval_status in service_owned_statuses:
        submitted = True
    else:
        successful = execution_result.get("success", False) if execution_result else False
        equipment_id = rec.get("target_equipment", "")
        confidence = rec.get("confidence_score", 0.0)

        submitted = await submit_feedback_to_model(
            recommendation_id=rec_id,
            equipment_id=equipment_id,
            successful=successful,
            outcome_status=approval_status,
            confidence_score=confidence,
        )

    return {
        "feedback_submitted": submitted,
    }


# ---------------------------------------------------------------------------
# Node: format_result
# ---------------------------------------------------------------------------


def format_result_node(state: RecommendationAgentState) -> dict:
    """Final formatting — ensure response and processing_complete are set."""
    response = state.get("response", "")
    if not response:
        response = "Processing complete."

    return {
        "processing_complete": True,
        "needs_input": False,
        "response": response,
    }


# ---------------------------------------------------------------------------
# Conditional edge: check_needs_input (after approval request)
# ---------------------------------------------------------------------------


def check_needs_input(state: RecommendationAgentState) -> str:
    """After handle_approval_response, check if we still need input."""
    if state.get("needs_input"):
        return "still_waiting"
    return "resolved"


# ---------------------------------------------------------------------------
# Graph definition
# ---------------------------------------------------------------------------


def build_recommendation_graph() -> StateGraph:
    """Build the recommendation agent StateGraph (uncompiled)."""
    graph = StateGraph(RecommendationAgentState)

    # Add nodes
    graph.add_node("fetch_pending", fetch_pending_node)
    graph.add_node("validate_relevance", validate_relevance_node)
    graph.add_node("mark_expired", mark_expired_node)
    graph.add_node("assess_impact", assess_impact_node)
    graph.add_node("check_schedule", check_schedule_node)
    graph.add_node("defer", defer_node)
    graph.add_node("route_tier", route_tier_node)
    graph.add_node("log_advisory", log_advisory_node)
    graph.add_node("request_approval", request_approval_node)
    graph.add_node("auto_execute", auto_execute_node)
    graph.add_node("handle_approval_response", handle_approval_response_node)
    graph.add_node("submit_feedback", submit_feedback_node)
    graph.add_node("format_result", format_result_node)

    # Entry point
    graph.set_entry_point("fetch_pending")

    # fetch_pending -> has_recommendation?
    graph.add_conditional_edges(
        "fetch_pending",
        has_recommendation,
        {
            "has_rec": "validate_relevance",
            "no_rec": "format_result",
        },
    )

    # validate_relevance -> relevant?
    graph.add_conditional_edges(
        "validate_relevance",
        check_relevance,
        {
            "valid": "assess_impact",
            "expired": "mark_expired",
        },
    )

    # mark_expired -> END
    graph.add_edge("mark_expired", END)

    # assess_impact -> check_schedule
    graph.add_edge("assess_impact", "check_schedule")

    # check_schedule -> conflict?
    graph.add_conditional_edges(
        "check_schedule",
        check_schedule_conflict,
        {
            "clear": "route_tier",
            "conflict": "defer",
        },
    )

    # defer -> END
    graph.add_edge("defer", END)

    # route_tier -> tier-specific handler
    graph.add_conditional_edges(
        "route_tier",
        tier_route,
        {
            "tier1": "log_advisory",
            "tier2": "request_approval",
            "tier3": "auto_execute",
        },
    )

    # Tier 1: log_advisory -> submit_feedback -> format_result -> END
    graph.add_edge("log_advisory", "submit_feedback")

    # Tier 2: request_approval -> END (wait for reply, needs_input=True)
    graph.add_edge("request_approval", END)

    # Tier 3: auto_execute -> submit_feedback
    graph.add_edge("auto_execute", "submit_feedback")

    # Approval response handling (entered via resume after WhatsApp reply)
    graph.add_conditional_edges(
        "handle_approval_response",
        check_needs_input,
        {
            "still_waiting": END,
            "resolved": "submit_feedback",
        },
    )

    # submit_feedback -> format_result -> END
    graph.add_edge("submit_feedback", "format_result")
    graph.add_edge("format_result", END)

    return graph


# ---------------------------------------------------------------------------
# Compiled graph with checkpointer (singleton)
# ---------------------------------------------------------------------------

_checkpointer = MemorySaver()
_compiled_graph = None


def get_recommendation_graph():
    """Get the compiled recommendation graph with checkpointing.

    Returns:
        Compiled StateGraph with MemorySaver checkpointer
    """
    global _compiled_graph
    if _compiled_graph is None:
        graph = build_recommendation_graph()
        _compiled_graph = graph.compile(checkpointer=_checkpointer)
    return _compiled_graph
