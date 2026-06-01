"""
Desk Complaint LangGraph Subgraph
===================================
Stateful, multi-turn, channel-agnostic agent for comfort complaints.

Graph architecture:
  parse_input -> check_complete -> [ask_desk | ask_type | check_history]
  check_history -> resolve_zone -> diagnose -> format_response -> END
  ask_desk -> END (wait for user reply)
  ask_type -> END (wait for user reply)

All nodes are thin wrappers around existing services:
  - ComfortComplaintHandler (complaint_handler.py)
  - CrossSystemAnalyzer (cross_system_analyzer.py)
  - Channel formatters (formatters.py)

LLM usage: Zero. The graph is entirely deterministic Python.
"""

import logging
from typing import Annotated, TypedDict

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages

from app.agents.complaint_nlp import (
    detect_comfort_complaint,
    extract_complaint_types,
    extract_desk_id,
    extract_duration,
)
from app.agents.formatters import (
    format_for_chat,
    format_for_telegram,
    format_for_whatsapp,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# State Schema
# ---------------------------------------------------------------------------


class ComplaintState(TypedDict):
    """State for the desk complaint subgraph."""

    messages: Annotated[list, add_messages]  # LangGraph message history
    user_id: str
    user_name: str | None
    channel: str  # "chat" | "whatsapp" | "telegram"

    # Extracted info
    desk_id: str | None
    complaint_types: list[str]  # supports compound: ["too_cold", "noise"]
    complaint_text: str | None  # raw text for escalation record
    description: str | None

    # Classification gate: did NLP detect a comfort complaint?
    is_comfort_complaint: bool  # False = route to escalation

    # Resolved context (from existing handlers)
    desk: dict | None
    zone: dict | None
    bms_context: dict | None

    # History & diagnosis
    history_summary: dict | None
    diagnosis: dict | None
    response: str  # Final formatted response for channel
    needs_input: bool  # True = waiting for user reply
    escalation_sent: bool  # True = helpdesk email was sent


# ---------------------------------------------------------------------------
# Node: parse_input
# ---------------------------------------------------------------------------


def parse_input_node(state: ComplaintState) -> dict:
    """
    Extract desk_id and complaint type(s) from the latest user message.

    Uses regex/keyword matching (zero LLM).
    Merges newly extracted info with any existing state (for multi-turn).
    Also classifies whether the message is a comfort complaint at all —
    if not, it will be routed to the escalation path instead of diagnosis.
    """
    messages = state.get("messages", [])
    if not messages:
        return {}

    # Get the latest human message
    latest_text = ""
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            latest_text = msg.content
            break

    if not latest_text:
        return {}

    updates: dict = {
        "complaint_text": latest_text,
        # Classifier gate: did NLP detect a comfort complaint?
        "is_comfort_complaint": detect_comfort_complaint(latest_text),
    }

    # If we previously asked for desk, accept bare numbers
    waiting_for_desk = state.get("needs_input") and not state.get("desk_id")

    # Extract desk_id (new extraction overrides previous if present)
    new_desk_id = extract_desk_id(latest_text, bare_number_ok=waiting_for_desk)
    if new_desk_id:
        updates["desk_id"] = new_desk_id
    elif not state.get("desk_id"):
        updates["desk_id"] = None

    # Extract complaint types (merge with existing if this is a continuation)
    new_types = extract_complaint_types(latest_text)
    existing_types = state.get("complaint_types") or []
    if new_types:
        # Merge: keep existing + add new (dedup)
        merged = list(existing_types)
        for t in new_types:
            if t not in merged:
                merged.append(t)
        updates["complaint_types"] = merged
    elif not existing_types:
        updates["complaint_types"] = []

    # Extract duration as description context
    duration = extract_duration(latest_text)
    if duration and not state.get("description"):
        updates["description"] = duration

    return updates


# ---------------------------------------------------------------------------
# Conditional edge: check_complete
# ---------------------------------------------------------------------------


def check_complete(state: ComplaintState) -> str:
    """
    Route based on what info we have.

    Returns:
      "need_desk"         - missing desk_id, ask user
      "need_type"         - missing complaint type, ask user
      "complete"           - have both, proceed to diagnosis
      "escalate"          - not a comfort complaint, send to helpdesk
    """
    # Classifier gate: if message is not a comfort complaint at all, escalate
    if not state.get("is_comfort_complaint"):
        return "escalate"

    desk_id = state.get("desk_id")
    complaint_types = state.get("complaint_types") or []

    if not desk_id:
        return "need_desk"
    if not complaint_types:
        return "need_type"
    return "complete"


# ---------------------------------------------------------------------------
# Node: ask_desk
# ---------------------------------------------------------------------------


def ask_desk_node(state: ComplaintState) -> dict:
    """Ask user for their desk location."""
    complaint_types = state.get("complaint_types") or []

    if complaint_types:
        type_str = ", ".join(t.replace("_", " ") for t in complaint_types)
        prompt = f"I can help with your {type_str} issue! Which desk are you at? (e.g. 'desk 203' or just '25')"
    else:
        prompt = "I can help with that! Which desk are you at? (e.g. 'desk 203' or just '25')"

    return {
        "messages": [AIMessage(content=prompt)],
        "response": prompt,
        "needs_input": True,
    }


# ---------------------------------------------------------------------------
# Node: ask_type
# ---------------------------------------------------------------------------


def ask_type_node(state: ComplaintState) -> dict:
    """Ask user what kind of comfort issue they're experiencing."""
    desk_id = state.get("desk_id", "your desk")

    prompt = (
        f"Got it, desk {desk_id}. What's the issue?\n"
        "- Too hot\n"
        "- Too cold\n"
        "- Stuffy/no fresh air\n"
        "- Drafty\n"
        "- Noisy equipment\n"
        "- Lighting (too dark/bright)"
    )

    return {
        "messages": [AIMessage(content=prompt)],
        "response": prompt,
        "needs_input": True,
    }


# ---------------------------------------------------------------------------
# Node: check_history
# ---------------------------------------------------------------------------


def check_history_node(state: ComplaintState) -> dict:
    """Get repeat complaint context for this desk."""
    desk_id = state.get("desk_id")
    if not desk_id:
        return {"history_summary": None}

    try:
        from app.services.complaint_handler import get_complaint_handler

        handler = get_complaint_handler()
        summary = handler.get_complaint_history_summary(
            desk_id=desk_id,
            complaint_types=state.get("complaint_types"),
        )
        return {"history_summary": summary}
    except Exception as e:
        logger.warning(f"Failed to get complaint history: {e}")
        return {"history_summary": None}


# ---------------------------------------------------------------------------
# Node: resolve_zone
# ---------------------------------------------------------------------------


def resolve_zone_node(state: ComplaintState) -> dict:
    """Desk -> zone -> equipment -> BMS readings."""
    desk_id = state.get("desk_id")
    if not desk_id:
        return {}

    try:
        from app.services.complaint_handler import get_complaint_handler

        handler = get_complaint_handler()
        bms_data = handler.lookup_desk_bms(desk_id)

        if not bms_data.get("success"):
            return {
                "desk": None,
                "zone": None,
                "bms_context": None,
            }

        return {
            "desk": bms_data.get("desk"),
            "zone": bms_data.get("zone"),
            "bms_context": bms_data.get("bms_context"),
        }
    except Exception as e:
        logger.error(f"Failed to resolve zone for desk {desk_id}: {e}")
        return {"desk": None, "zone": None, "bms_context": None}


# ---------------------------------------------------------------------------
# Node: diagnose
# ---------------------------------------------------------------------------


def diagnose_node(state: ComplaintState) -> dict:
    """Full diagnosis with desk-context enhancement."""
    desk_id = state.get("desk_id")
    complaint_types = state.get("complaint_types") or []

    if not desk_id or not complaint_types:
        return {"diagnosis": None}

    try:
        from app.services.complaint_handler import get_complaint_handler

        handler = get_complaint_handler()

        # Use the primary complaint type for diagnosis
        primary_type = complaint_types[0]
        diagnosis = handler.handle_complaint(
            desk_id=desk_id,
            complaint_type=primary_type,
            user_name=state.get("user_id"),
            description=state.get("description"),
        )

        return {"diagnosis": diagnosis.to_dict()}
    except Exception as e:
        logger.error(f"Diagnosis failed for desk {desk_id}: {e}")
        return {"diagnosis": None}


# ---------------------------------------------------------------------------
# Node: format_response
# ---------------------------------------------------------------------------


def format_response_node(state: ComplaintState) -> dict:
    """Format diagnosis for the target channel."""
    from app.models.complaint import ComplaintDiagnosis

    diagnosis_data = state.get("diagnosis")
    if not diagnosis_data:
        fallback = "Sorry, I couldn't complete the diagnosis. Please try again or contact facilities."
        return {
            "messages": [AIMessage(content=fallback)],
            "response": fallback,
            "needs_input": False,
        }

    diagnosis = ComplaintDiagnosis.from_dict(diagnosis_data)
    history = state.get("history_summary")
    channel = state.get("channel", "chat")

    formatters = {
        "chat": format_for_chat,
        "whatsapp": format_for_whatsapp,
        "telegram": format_for_telegram,
    }
    formatter = formatters.get(channel, format_for_chat)
    response = formatter(diagnosis, history)

    return {
        "messages": [AIMessage(content=response)],
        "response": response,
        "needs_input": False,
    }


# ---------------------------------------------------------------------------
# Node: escalate_unclassified
# ---------------------------------------------------------------------------


def _send_escalation_email(state: ComplaintState) -> None:
    """Send escalation email to helpdesk in a fire-and-forget thread."""
    import threading
    from datetime import UTC, datetime

    # Defer import to avoid circular / import-time issues
    from app.services.email_reply_service import get_email_reply_service

    escalation_record = {
        "reporter_name": state.get("user_name") or state.get("user_id"),
        "reporter_telegram_id": state.get("user_id"),
        "original_message": state.get("complaint_text") or "",
        "reason": "No matching comfort-complaint pattern in call log taxonomy",
        "timestamp": datetime.now(UTC).isoformat(),
        "status": "pending_helpdesk_review",
    }

    email_service = get_email_reply_service()

    subject = (
        f"Unclassified complaint from {escalation_record['reporter_name']} "
        f"(Telegram ID: {escalation_record['reporter_telegram_id']})"
    )

    body = f"""Unclassified Facilities Complaint

User: {escalation_record["reporter_name"]}
Telegram ID: {escalation_record["reporter_telegram_id"]}
Timestamp: {escalation_record["timestamp"]}

Complaint:
{escalation_record["original_message"]}

---
Action Required:
Review the complaint and create a work order if applicable.

Status: {escalation_record["status"]}
"""

    def _send():
        import asyncio

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(
                email_service.send_reply(
                    to_email="helpdesk@sentinel-ai.co.za",
                    to_name=None,
                    subject=subject,
                    body_plain=body,
                    body_html=None,
                )
            )
            if result.sent:
                logger.info("Escalation email sent for user %s", state.get("user_id"))
            else:
                logger.error("Escalation email failed: %s", result.error)
        finally:
            loop.close()

    thread = threading.Thread(target=_send, daemon=True)
    thread.start()

    # Persist to local escalation tracker (non-blocking)
    _append_escalation_record(escalation_record)


def _append_escalation_record(record: dict) -> None:
    """Append to call_log_escalations.json (fire-and-forget)."""
    import json
    import os

    # Resolve path relative to backend/app — go up to project root
    backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    escalations_path = os.path.join(backend_dir, "app", "data", "call_log_escalations.json")

    try:
        if os.path.exists(escalations_path):
            with open(escalations_path) as f:
                data = json.load(f)
        else:
            data = []

        data.append(record)

        with open(escalations_path, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.warning("Failed to persist escalation record: %s", e)


def escalate_node(state: ComplaintState) -> dict:
    """
    Route for unclassified messages that are not comfort complaints.
    Sends an email to helpdesk and returns a user-facing message.
    """
    _send_escalation_email(state)

    escalation_message = (
        "I've flagged this for the helpdesk team. "
        "They'll review and create a work order if needed. "
        "You should hear back within 2 hours."
    )

    return {
        "messages": [AIMessage(content=escalation_message)],
        "response": escalation_message,
        "needs_input": False,
        "escalation_sent": True,
    }


# ---------------------------------------------------------------------------
# Graph definition
# ---------------------------------------------------------------------------


def build_desk_complaint_graph() -> StateGraph:
    """Build the desk complaint StateGraph (uncompiled)."""
    graph = StateGraph(ComplaintState)

    # Add nodes
    graph.add_node("parse_input", parse_input_node)
    graph.add_node("ask_desk", ask_desk_node)
    graph.add_node("ask_type", ask_type_node)
    graph.add_node("check_history", check_history_node)
    graph.add_node("resolve_zone", resolve_zone_node)
    graph.add_node("diagnose", diagnose_node)
    graph.add_node("format_response", format_response_node)
    graph.add_node("escalate", escalate_node)

    # Entry point
    graph.set_entry_point("parse_input")

    # Conditional routing after parsing
    graph.add_conditional_edges(
        "parse_input",
        check_complete,
        {
            "need_desk": "ask_desk",
            "need_type": "ask_type",
            "complete": "check_history",
            "escalate": "escalate",
        },
    )

    # Ask nodes terminate (wait for user reply)
    graph.add_edge("ask_desk", END)
    graph.add_edge("ask_type", END)

    # Linear flow: history -> zone -> diagnose -> format -> END
    graph.add_edge("check_history", "resolve_zone")
    graph.add_edge("resolve_zone", "diagnose")
    graph.add_edge("diagnose", "format_response")
    graph.add_edge("format_response", END)

    # Escalation path terminates directly
    graph.add_edge("escalate", END)

    return graph


# ---------------------------------------------------------------------------
# Compiled graph with checkpointer (singleton)
# ---------------------------------------------------------------------------

_checkpointer = MemorySaver()
_compiled_graph = None


def get_desk_complaint_graph():
    """Get the compiled desk complaint graph with checkpointing."""
    global _compiled_graph
    if _compiled_graph is None:
        graph = build_desk_complaint_graph()
        _compiled_graph = graph.compile(checkpointer=_checkpointer)
    return _compiled_graph
