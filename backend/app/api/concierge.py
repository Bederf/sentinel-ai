"""
Concierge Intelligence Dashboard API — Phase 161-03.

Provides room-centric signal views for the concierge persona (Thandi Dineka).
Surfaces booking conflicts, ghost bookings, saturation, and complaint signals
aggregated per room with urgency scoring.

Endpoints:
    GET /api/concierge/rooms/{site_id}
    GET /api/concierge/rooms/{site_id}/{room_id}/signals
    GET /api/concierge/rooms/{site_id}/{room_id}/signals/{signal_id}
    GET /api/concierge/dashboard/{person_email}
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.database.repositories.room_registry_repository import get_room_registry_repository
from app.services.concierge_urgency import compute_urgency_score, normalise_urgency_scores
from app.services.room_signal_mapper import extract_room_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/concierge", tags=["concierge"])

_FIXTURE_PATH = Path(__file__).resolve().parents[1] / "data" / "space" / "concierge_signals_fixture.json"

ADVISORY_LABEL = "For awareness only. Act at your discretion."

SEVERITY_ORDER = {"critical": 4, "high": 3, "medium": 2, "low": 1}


class SignalResolutionRequest(BaseModel):
    resolution_state: str = "acknowledged"
    resolved_by: str | None = "concierge_ui"
    resolution_note: str | None = "Noted from concierge room map"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_fixture_signals() -> list[dict]:
    """Load local signal fixtures from JSON file."""
    try:
        with open(_FIXTURE_PATH) as f:
            return json.load(f)
    except Exception as e:
        logger.warning("Failed to load concierge signal fixtures: %s", e)
        return []


def _signal_room_id(signal: dict) -> str | None:
    """Extract room_id from a signal using location_ref, summary, or metadata."""
    # Check metadata.room_id first (most explicit)
    meta = signal.get("metadata") or {}
    if isinstance(meta, dict) and meta.get("room_id"):
        canonical = extract_room_id(str(meta["room_id"]))
        return canonical or str(meta["room_id"]).upper()

    # Check location_ref
    location_ref = signal.get("location_ref", "")
    if location_ref:
        room_id = extract_room_id(location_ref)
        if room_id:
            return room_id

    # Check summary
    summary = signal.get("summary", "")
    if summary:
        room_id = extract_room_id(summary)
        if room_id:
            return room_id

    return None


def _highest_severity(signals: list[dict]) -> str:
    """Return the highest severity string from a list of signals."""
    if not signals:
        return "low"
    best = "low"
    best_weight = 0
    for s in signals:
        sev = s.get("severity", "low")
        weight = SEVERITY_ORDER.get(sev, 0)
        if weight > best_weight:
            best_weight = weight
            best = sev
    return best


def _oldest_created_at(signals: list[dict]) -> datetime | None:
    """Return the oldest created_at datetime from a list of signals."""
    oldest = None
    for s in signals:
        created = s.get("created_at")
        if created:
            try:
                dt = datetime.fromisoformat(created.replace("Z", "+00:00")) if isinstance(created, str) else created
                if oldest is None or dt < oldest:
                    oldest = dt
            except (ValueError, TypeError):
                continue
    return oldest


def _domains_from_signals(signals: list[dict]) -> list[str]:
    """Extract unique source_module domains from signals."""
    domains: list[str] = []
    for s in signals:
        mod = s.get("source_module", "")
        if mod and mod not in domains:
            domains.append(mod)
    return domains


def _signal_summary(signal: dict) -> dict:
    """Return a compact signal summary for room listing."""
    return {
        "id": signal.get("id"),
        "signal_type": signal.get("signal_type"),
        "severity": signal.get("severity"),
        "summary": signal.get("summary"),
        "created_at": signal.get("created_at"),
    }


async def _resolve_site_uuid(client, site_id: str) -> str | None:
    """Resolve a site code (S001, site-001) to its Supabase UUID."""
    # Try exact match first, then with 'site-' prefix normalisation
    normalized_prefixed = f"site-{site_id[1:]}" if site_id.upper().startswith("S") and site_id[1:].isdigit() else None
    for code in (site_id, site_id.lower(), normalized_prefixed):
        if not code:
            continue
        try:
            r = client.table("sites").select("id").eq("code", code).limit(1).execute()
            if r.data:
                return r.data[0]["id"]
        except Exception:
            pass
    return None


async def _get_signals_for_site(site_id: str) -> list[dict]:
    """Fetch active signals for a specific site. Supabase first, fixture fallback."""
    from app.database.supabase_client import get_supabase_client

    client = get_supabase_client()
    if client:
        try:
            site_uuid = await _resolve_site_uuid(client, site_id)
            if site_uuid:
                result = (
                    client.table("signal")
                    .select("*")
                    .eq("resolution_state", "active")
                    .eq("site_id", site_uuid)
                    .execute()
                )
                if result.data:
                    return result.data
        except Exception as e:
            logger.warning("Supabase signal query failed, falling back to fixtures: %s", e)

    # Demo mode / fallback: fixture is keyed to S001 Fairlands rooms
    return _load_fixture_signals()


async def _get_signal_by_id(signal_id: str) -> dict | None:
    """Fetch a single signal by ID. Supabase first, fixture fallback."""
    from app.database.supabase_client import get_supabase_client

    client = get_supabase_client()
    if client:
        try:
            result = client.table("signal").select("*").eq("id", signal_id).execute()
            if result.data and len(result.data) > 0:
                return result.data[0]
        except Exception as e:
            logger.warning("Supabase signal lookup failed, falling back to fixtures: %s", e)

    # Fixture fallback
    for s in _load_fixture_signals():
        if s.get("id") == signal_id:
            return s
    return None


# ---------------------------------------------------------------------------
# Endpoint 1: GET /api/concierge/rooms/{site_id}
# ---------------------------------------------------------------------------


@router.get("/rooms/{site_id}")
async def get_concierge_rooms(site_id: str) -> dict[str, Any]:
    """Return all rooms for a site with signal summary and urgency scores."""
    repo = get_room_registry_repository()
    rooms = await repo.get_rooms_by_site(site_id)

    if not rooms:
        return {"rooms": []}

    # Fetch all active signals
    all_signals = await _get_signals_for_site(site_id)

    # Group signals by room
    room_signals: dict[str, list[dict]] = {}
    for signal in all_signals:
        room_id = _signal_room_id(signal)
        if room_id:
            room_signals.setdefault(room_id, []).append(signal)

    # Build room response
    result_rooms: list[dict] = []
    for room in rooms:
        room_id = room.get("room_id", "")
        signals = room_signals.get(room_id, [])
        highest_sev = _highest_severity(signals)
        oldest_at = _oldest_created_at(signals)

        # Count repeat signals (same signal_type for this room)
        type_counts: dict[str, int] = {}
        for s in signals:
            st = s.get("signal_type", "")
            type_counts[st] = type_counts.get(st, 0) + 1
        repeat_count = sum(c - 1 for c in type_counts.values() if c > 1)

        raw_urgency = compute_urgency_score(
            signal_count=len(signals),
            highest_severity=highest_sev,
            oldest_unresolved_at=oldest_at,
            repeat_count=repeat_count,
        )

        # Latest signal timestamp
        latest_at = None
        for s in signals:
            cat = s.get("created_at")
            if cat and (latest_at is None or cat > latest_at):
                latest_at = cat

        result_rooms.append(
            {
                "room_id": room_id,
                "building": room.get("building"),
                "quadrant": room.get("quadrant"),
                "room_type": room.get("room_type"),
                "floor": room.get("floor"),
                "friendly_name": room.get("friendly_name"),
                "capacity": room.get("capacity"),
                "signal_count": len(signals),
                "domains": _domains_from_signals(signals),
                "highest_severity": highest_sev,
                "latest_signal_at": latest_at,
                "urgency_score": raw_urgency,
                "signals": [_signal_summary(s) for s in signals],
            }
        )

    # Normalise urgency scores across all rooms
    normalise_urgency_scores(result_rooms)

    # Sort by urgency descending
    result_rooms.sort(key=lambda r: r.get("urgency_score", 0), reverse=True)

    return {"rooms": result_rooms}


# ---------------------------------------------------------------------------
# Endpoint 2: GET /api/concierge/rooms/{site_id}/{room_id}/signals
# ---------------------------------------------------------------------------


@router.get("/rooms/{site_id}/{room_id}/signals")
async def get_room_signals(site_id: str, room_id: str) -> list[dict[str, Any]]:
    """Return all active signals for a specific room, ordered by created_at DESC."""
    all_signals = await _get_signals_for_site(site_id)

    room_signals = [s for s in all_signals if _signal_room_id(s) == room_id.upper()]
    room_signals.sort(key=lambda s: s.get("created_at", ""), reverse=True)

    return room_signals


# ---------------------------------------------------------------------------
# Endpoint 3: GET /api/concierge/rooms/{site_id}/{room_id}/signals/{signal_id}
# ---------------------------------------------------------------------------


@router.get("/rooms/{site_id}/{room_id}/signals/{signal_id}")
async def get_signal_detail(site_id: str, room_id: str, signal_id: str) -> dict[str, Any]:
    """Full signal detail with related signals, evidence, and advisory label."""
    signal = await _get_signal_by_id(signal_id)
    if not signal:
        raise HTTPException(status_code=404, detail="Signal not found")

    # Find related signals (same signal_type, same room)
    all_signals = await _get_signals_for_site(site_id)
    related = [
        _signal_summary(s)
        for s in all_signals
        if (
            s.get("signal_type") == signal.get("signal_type")
            and _signal_room_id(s) == room_id.upper()
            and s.get("id") != signal_id
        )
    ]
    related.sort(key=lambda s: s.get("created_at", ""), reverse=True)

    # Suggested actions from card template
    from app.services.correlation.card_generator import CARD_TEMPLATES

    concierge_template = CARD_TEMPLATES.get("concierge", {})

    return {
        **signal,
        "related_signals": related,
        "advisory_label": ADVISORY_LABEL,
        "suggested_actions": concierge_template.get("actions", []),
        "card_focus_fields": concierge_template.get("card_focus_fields", []),
    }


@router.post("/rooms/{site_id}/{room_id}/signals/{signal_id}/resolve")
async def resolve_signal(
    site_id: str,
    room_id: str,
    signal_id: str,
    body: SignalResolutionRequest,
) -> dict[str, Any]:
    """Mark a room signal as acknowledged or resolved so it drops from the active concierge view."""
    from app.database.supabase_client import get_supabase_client

    client = get_supabase_client()
    if not client:
        raise HTTPException(status_code=503, detail="Supabase client unavailable")

    signal = await _get_signal_by_id(signal_id)
    if not signal:
        raise HTTPException(status_code=404, detail="Signal not found")

    signal_room_id = _signal_room_id(signal)
    if signal_room_id and signal_room_id != room_id.upper():
        raise HTTPException(status_code=400, detail="Signal does not belong to this room")

    state = (body.resolution_state or "acknowledged").strip().lower()
    if state not in {"acknowledged", "resolved"}:
        raise HTTPException(status_code=400, detail="resolution_state must be acknowledged or resolved")

    try:
        metadata = signal.get("metadata") if isinstance(signal.get("metadata"), dict) else {}
        updated_metadata = {
            **metadata,
            "concierge_resolution": {
                "state": state,
                "resolved_by": body.resolved_by or "concierge_ui",
                "resolution_note": body.resolution_note or "",
                "room_id": room_id.upper(),
                "site_id": site_id,
                "recorded_at": datetime.utcnow().isoformat() + "Z",
            },
        }

        result = (
            client.table("signal")
            .update(
                {
                    "resolution_state": state,
                    "updated_at": datetime.utcnow().isoformat() + "Z",
                    "metadata": updated_metadata,
                }
            )
            .eq("id", signal_id)
            .execute()
        )
    except Exception as exc:
        logger.error("Failed to resolve concierge signal %s: %s", signal_id, exc)
        raise HTTPException(status_code=500, detail="Failed to resolve signal") from exc

    updated = result.data[0] if getattr(result, "data", None) else None
    return {
        "signal_id": signal_id,
        "room_id": room_id.upper(),
        "site_id": site_id,
        "resolution_state": state,
        "updated": updated,
    }


# ---------------------------------------------------------------------------
# Endpoint 4: GET /api/concierge/dashboard/{person_email}
# ---------------------------------------------------------------------------


@router.get("/dashboard/{person_email:path}")
async def get_dashboard_by_email(person_email: str) -> dict[str, Any]:
    """Return dashboard cards for a concierge by email lookup.

    Falls back to fixture-based rooms view if no Supabase connection.
    """
    from app.database.supabase_client import get_supabase_client

    client = get_supabase_client()

    if client:
        try:
            # Look up role_assignment by person_email
            result = client.table("role_assignment").select("*").eq("person_email", person_email).execute()
            if result.data and len(result.data) > 0:
                role = result.data[0]
                role_id = role.get("id")

                # Fetch dashboard cards

                # get_cards_for_person requires a psycopg2 connection — skip
                # in local fallback mode and use the rooms endpoint instead
                cards_result = (
                    client.table("dashboard_card")
                    .select("*")
                    .eq("recipient_role_assignment_id", role_id)
                    .is_("dismissed_at", "null")
                    .order("surfaced_at", desc=True)
                    .execute()
                )
                if cards_result.data is not None:
                    return {
                        "person_email": person_email,
                        "role_type": role.get("role_type", "concierge"),
                        "cards": cards_result.data,
                    }
        except Exception as e:
            logger.warning(
                "Supabase dashboard lookup failed for %s, using fallback: %s",
                person_email,
                e,
            )

    # Demo mode fallback — return fixture-based cards from rooms data
    from app.services.correlation.card_generator import CARD_TEMPLATES

    concierge_template = CARD_TEMPLATES.get("concierge", {})
    fixture_signals = _load_fixture_signals()

    # Group by signal_type to build summary cards
    type_groups: dict[str, list[dict]] = {}
    for s in fixture_signals:
        st = s.get("signal_type", "unknown")
        type_groups.setdefault(st, []).append(s)

    cards = []
    for signal_type, signals in type_groups.items():
        rooms_affected = list({_signal_room_id(s) for s in signals if _signal_room_id(s)})
        cards.append(
            {
                "card_id": f"local-card-{signal_type}",
                "signal_type": signal_type,
                "title": f"{signal_type.replace('_', ' ').title()} ({len(signals)} signals)",
                "severity": _highest_severity(signals),
                "signal_count": len(signals),
                "card_content": {
                    "summary": signals[0].get("summary", ""),
                    "affected_rooms": rooms_affected,
                    "recommended_actions": concierge_template.get("actions", []),
                },
                "advisory_label": ADVISORY_LABEL,
                "acknowledged_at": None,
            }
        )

    return {
        "person_email": person_email,
        "role_type": "concierge",
        "cards": cards,
    }
