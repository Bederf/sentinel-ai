"""Minimal HITL scaffold for advisory kernel threads."""

from __future__ import annotations

from typing import Any, TypedDict

from app.agents_kernel.state import PendingApproval, SentinelAgentState


class ReviewRequestPayload(TypedDict, total=False):
    """Future review request payload."""

    type: str
    reason: str
    draft_summary: str
    allowed_actions: list[str]


class ReviewResumePayload(TypedDict, total=False):
    """Future review resume payload."""

    action: str
    edited_text: str | None
    notes: str | None


def build_review_request(
    *,
    reason: str,
    draft_summary: str,
    allowed_actions: list[str] | None = None,
) -> ReviewRequestPayload:
    """Create a JSON-safe review request payload."""

    return {
        "type": "review_required",
        "reason": reason,
        "draft_summary": draft_summary,
        "allowed_actions": allowed_actions or ["approve", "edit", "reject", "request_more_analysis"],
    }


def build_resume_payload(
    action: str, *, edited_text: str | None = None, notes: str | None = None
) -> ReviewResumePayload:
    """Create a JSON-safe resume payload."""

    return {"action": action, "edited_text": edited_text, "notes": notes}


def mark_approval_pending(state: SentinelAgentState, payload: ReviewRequestPayload) -> PendingApproval:
    """Store pending approval state."""

    pending: PendingApproval = {
        "status": "pending",
        "reason": payload.get("reason", ""),
        "review_payload": dict(payload),
        "resume_payload": None,
    }
    state["pending_approval"] = pending
    return pending


def resolve_approval(
    state: SentinelAgentState, payload: ReviewResumePayload | dict[str, Any]
) -> PendingApproval | None:
    """Update pending approval state with a resume payload."""

    pending = state.get("pending_approval")
    if not pending:
        return None
    pending["status"] = "resolved"
    pending["resume_payload"] = dict(payload)
    state["pending_approval"] = pending
    return pending
