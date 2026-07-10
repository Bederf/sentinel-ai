"""PLS lifecycle service for site_onboarding state machine.

Wraps the site_onboarding_transition Postgres RPC in clean Python functions.
Every PLS transition goes through this service — never call the RPC directly.
"""

from __future__ import annotations

import logging
from typing import Any

from app.database.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)


class LifecycleError(Exception):
    """Base for PLS lifecycle errors."""


class TransitionDenied(LifecycleError):
    """Transition rejected by the PLS machine (actor, guard, or edge)."""


class VersionConflict(LifecycleError):
    """Concurrent modification — retry with fresh version."""


class EntityNotFound(LifecycleError):
    """No onboarding state exists for this site."""


def _classify_error(detail: str) -> str:
    if "PSMS_ACTOR_DENIED" in detail:
        return "actor_denied"
    if "PSMS_VERSION_CONFLICT" in detail:
        return "version_conflict"
    if "PSMS_ILLEGAL_TRANSITION" in detail:
        return "illegal_transition"
    if "PSMS_TERMINAL_STATE" in detail:
        return "terminal_state"
    if "PSMS_ENTITY_NOT_FOUND" in detail:
        return "entity_not_found"
    if "PSMS_GUARD_DENIED" in detail:
        return "guard_denied"
    return "unknown"


async def transition(
    site_id: str,
    transition_name: str,
    actor: str,
    actor_type: str,
    reason: str,
    expected_version: int | None = None,
    intent_id: str | None = None,
    evidence_ref: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute a PLS state transition.

    Returns ``{state, version, intent_id}``.

    Raises ``TransitionDenied``, ``VersionConflict``, ``EntityNotFound``,
    or ``LifecycleError`` on unexpected failures.
    """
    client = get_supabase_client()
    params: dict[str, Any] = {
        "p_site_id": site_id,
        "p_transition": transition_name,
        "p_actor": actor,
        "p_actor_type": actor_type,
        "p_reason": reason,
    }
    if expected_version is not None:
        params["p_expected_version"] = expected_version
    if intent_id is not None:
        params["p_intent_id"] = intent_id
    if evidence_ref is not None:
        params["p_evidence_ref"] = evidence_ref

    try:
        result = client.rpc("site_onboarding_transition", params).execute()
    except Exception as exc:
        detail = str(exc)
        code = _classify_error(detail)
        if code == "actor_denied":
            raise TransitionDenied(f"Actor '{actor}' ({actor_type}) denied for {transition_name}: {detail}") from exc
        if code == "version_conflict":
            raise VersionConflict(f"Version conflict on {transition_name}: {detail}") from exc
        if code == "entity_not_found":
            raise EntityNotFound(f"Site {site_id} has no onboarding state: {detail}") from exc
        if code in ("illegal_transition", "terminal_state", "guard_denied"):
            raise TransitionDenied(f"Transition {transition_name} rejected: {detail}") from exc
        raise LifecycleError(f"Transition {transition_name} failed: {detail}") from exc

    if not result.data:
        raise LifecycleError(f"Transition {transition_name} returned no data")

    return result.data if isinstance(result.data, dict) else result.data[0]


# ── Named helpers (each maps one PLS machine edge) ─────────────


async def begin_discovery(
    site_id: str,
    actor: str,
    actor_type: str = "operator",
    reason: str = "Starting equipment discovery",
    expected_version: int | None = None,
) -> dict[str, Any]:
    """created → discovering (external_effect=true).

    Returns ``intent_id`` — pass to ``discovery_completed`` / ``discovery_failed``.
    """
    return await transition(
        site_id,
        "begin_discovery",
        actor=actor,
        actor_type=actor_type,
        reason=reason,
        expected_version=expected_version,
    )


async def discovery_completed(
    site_id: str,
    intent_id: str,
    actor: str = "onboarding_service",
    actor_type: str = "service",
    reason: str = "Discovery completed successfully",
    evidence_ref: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """discovering → discovered (outcome for begin_discovery)."""
    return await transition(
        site_id,
        "discovery_completed",
        actor=actor,
        actor_type=actor_type,
        reason=reason,
        intent_id=intent_id,
        evidence_ref=evidence_ref,
    )


async def discovery_failed(
    site_id: str,
    intent_id: str,
    reason: str,
    actor: str = "onboarding_service",
    actor_type: str = "service",
) -> dict[str, Any]:
    """discovering → discovery_failed (outcome for begin_discovery)."""
    return await transition(
        site_id,
        "discovery_failed",
        actor=actor,
        actor_type=actor_type,
        reason=reason,
        intent_id=intent_id,
    )


async def capability_sync(
    site_id: str,
    actor: str = "onboarding_service",
    actor_type: str = "service",
    reason: str = "Capability sync complete",
) -> dict[str, Any]:
    """discovered → synced."""
    return await transition(
        site_id,
        "capability_sync",
        actor=actor,
        actor_type=actor_type,
        reason=reason,
    )


async def canonicalize(
    site_id: str,
    actor: str,
    actor_type: str = "operator",
    reason: str = "Wizard commit",
    evidence_ref: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """synced → canonical.

    Called from ``commit_bridge_review`` RPC — exposed here for
    direct use in non-RPC paths.
    """
    return await transition(
        site_id,
        "canonicalize",
        actor=actor,
        actor_type=actor_type,
        reason=reason,
        evidence_ref=evidence_ref,
    )


async def discovery_timeout(
    site_id: str,
    actor: str = "scheduler",
    actor_type: str = "system",
    reason: str = "Discovery timed out after 900s",
) -> dict[str, Any]:
    """discovering → discovery_timed_out (system timeout, no external effect)."""
    return await transition(
        site_id,
        "discovery_timeout",
        actor=actor,
        actor_type=actor_type,
        reason=reason,
    )


async def activate(
    site_id: str,
    actor: str,
    actor_type: str = "operator",
    reason: str = "Site activated",
) -> dict[str, Any]:
    """canonical → live (operator-only per INV-7)."""
    return await transition(
        site_id,
        "activate",
        actor=actor,
        actor_type=actor_type,
        reason=reason,
    )
