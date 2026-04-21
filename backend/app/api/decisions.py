"""
Decision Moment API (Phase 164).

GET /api/decisions/current/{site_id}
  Returns latest DecisionMomentPayload for site, assembled from live fault state.
  No LLM in critical path. Target latency: < 300ms.

GET /api/decisions/stream/{site_id}
  SSE streaming endpoint — pushes DecisionMomentPayload to kiosk display (Phase 165-02).
"""

from __future__ import annotations

import asyncio
import contextlib
import json as _json
import logging
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, field_validator

from app.services.decision_moment_aggregator import DecisionMomentAggregator

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/decisions", tags=["decisions"])


# ---------------------------------------------------------------------------
# Trigger resolution models and constants (Phase 167-01)
# ---------------------------------------------------------------------------


class TriggerRequest(BaseModel):
    trigger_type: Literal["none", "floor", "alert", "equipment"]
    context: dict[str, Any] = {}

    @field_validator("context")
    @classmethod
    def validate_context(cls, v: dict, info) -> dict:
        """Validate required context keys per trigger type."""
        trigger_type = info.data.get("trigger_type")
        if trigger_type == "alert" and "alert_type" not in v:
            raise ValueError('alert trigger requires context["alert_type"]')
        if trigger_type == "equipment" and "equipment_type" not in v:
            raise ValueError('equipment trigger requires context["equipment_type"]')
        return v


class TriggerResponse(BaseModel):
    module_display: dict[str, str]
    trigger_type: str


_ALL_MODULES = ["hvac", "energy", "lighting", "solar", "occupancy", "fire", "security", "water"]

_TRIGGER_MAP: dict[str, dict[str, str]] = {
    "none": dict.fromkeys(_ALL_MODULES, "hidden"),
    "floor": {
        "hvac": "detailed",
        "occupancy": "summary",
        "energy": "summary",
        **{m: "hidden" for m in _ALL_MODULES if m not in ("hvac", "occupancy", "energy")},
    },
    "alert": {},  # filled dynamically from context["alert_type"]
    "equipment": {},  # filled dynamically from context["equipment_type"]
}


# Module-level cache: site_id → (payload_dict, cached_at)
_payload_cache: dict[str, tuple[dict, datetime]] = {}
_CACHE_TTL_SECONDS = 30  # refresh after 30s to reflect telemetry changes

_aggregator = DecisionMomentAggregator()


def cache_decision_payload(site_id: str, payload_dict: dict) -> None:
    """Called by the event bus subscriber to pre-warm the cache."""
    _payload_cache[site_id] = (payload_dict, datetime.now(UTC))
    logger.info("Decision payload cached for site %s", site_id)


def clear_decision_payload(site_id: str) -> None:
    """
    Invalidate the cache when a fault resolves.
    Called by the event bus subscriber on fault_cleared / low-importance events.
    Without this, the crisis page shows urgency 0.82 until the 30s TTL expires
    even after the fault clears — eroding operator trust.
    """
    if site_id in _payload_cache:
        del _payload_cache[site_id]
        logger.info("Decision payload cache cleared for site %s (fault resolved)", site_id)


def get_cached_payload(site_id: str) -> dict | None:
    """
    Return the cached payload dict for the site, or None if missing/stale.

    Uses the same _payload_cache as cache_decision_payload() — no duplicate state.
    TTL: _CACHE_TTL_SECONDS (30s) — short enough to reflect telemetry changes.
    """
    entry = _payload_cache.get(site_id)
    if not entry:
        return None
    payload_dict, cached_at = entry
    age = (datetime.now(UTC) - cached_at).total_seconds()
    return payload_dict if age < _CACHE_TTL_SECONDS else None


@router.get("/current/{site_id}")
async def get_current_decision(
    site_id: str,
    fault_type: str = Query(default="chiller_fault"),
    severity: str = Query(default="critical"),
    asset_id: str = Query(default=""),
) -> JSONResponse:
    """
    Returns the current DecisionMomentPayload for the given site.

    If a cached payload exists (from event bus trigger) and is fresh, returns it.
    Otherwise assembles on-demand from query params (manual/local trigger path).

    Query params are used for the on-demand assembly path only — when the event bus
    has pre-warmed the cache, those are ignored.

    Returns 422 when no cached payload exists and asset_id is not provided.
    """
    # Return cached payload if fresh
    if site_id in _payload_cache:
        cached_dict, cached_at = _payload_cache[site_id]
        age_seconds = (datetime.now(UTC) - cached_at).total_seconds()
        if age_seconds < _CACHE_TTL_SECONDS:
            return JSONResponse(content={"data": cached_dict, "source": "cache", "age_seconds": int(age_seconds)})

    # On-demand assembly (local path / no active event)
    if not asset_id:
        raise HTTPException(
            status_code=422,
            detail=(
                "asset_id required when no cached decision payload exists. "
                "Provide ?asset_id=S002-CHILLER-B1-001&fault_type=chiller_fault&severity=critical"
            ),
        )

    try:
        current_hour = datetime.now().hour
        payload = _aggregator.assemble(
            building_id=site_id,
            fault_type=fault_type,
            severity=severity,
            asset_id=asset_id,
            current_hour=current_hour,
        )
        payload_dict = payload.to_dict()
        # Cache on-demand result too
        _payload_cache[site_id] = (payload_dict, datetime.now(UTC))
        return JSONResponse(content={"data": payload_dict, "source": "on_demand"})
    except Exception as e:
        logger.error("Decision assembly failed for %s: %s", site_id, e)
        raise HTTPException(status_code=500, detail=f"Decision assembly failed: {e!s}")


@router.post("/trigger/{site_id}", response_model=TriggerResponse)
async def resolve_trigger(site_id: str, req: TriggerRequest) -> TriggerResponse:
    """
    Resolve which modules to show given a trigger.

    POST /api/decisions/trigger/{site_id}
    Body: { "trigger_type": "floor"|"alert"|"equipment"|"none", "context": {...} }
    Returns: { "module_display": { "hvac": "hidden"|"summary"|"detailed", ... } }

    Reads buildings.profile.module_display for persistent admin overrides,
    then applies the trigger map on top.
    If profile has no module_display, all modules default to "hidden".
    No auth required — returns display state only, no sensitive data.
    """
    # Base: all hidden
    result: dict[str, str] = dict.fromkeys(_ALL_MODULES, "hidden")

    # Apply trigger map
    if req.trigger_type == "none":
        pass  # all hidden — base is already all hidden

    elif req.trigger_type == "floor":
        result["hvac"] = "detailed"
        result["occupancy"] = "summary"
        result["energy"] = "summary"

    elif req.trigger_type == "alert":
        alert_type = req.context["alert_type"]
        if alert_type in _ALL_MODULES:
            result[alert_type] = "detailed"

    elif req.trigger_type == "equipment":
        equipment_type = req.context["equipment_type"].lower()
        # Map equipment type codes to module names
        _type_to_module: dict[str, str] = {
            "chiller": "hvac",
            "ahu": "hvac",
            "fcu": "hvac",
            "vav": "hvac",
            "pump": "hvac",
            "mtr": "energy",
            "gen": "energy",
            "ups": "energy",
            "dali": "lighting",
            "lum": "lighting",
            "mtr-r-sol": "solar",
        }
        module = _type_to_module.get(equipment_type, "")
        if module:
            result[module] = "detailed"

    # Load persistent admin overrides from buildings.profile.module_display
    # 3-tier fallback: Supabase → graceful skip (admin overrides are optional)
    try:
        from app.database.supabase_client import get_supabase_client

        client = get_supabase_client()
        resp = client.table("buildings").select("profile").eq("id", site_id).single().execute()
        if resp.data:
            profile = resp.data.get("profile") or {}
            persistent = profile.get("module_display", {})
            # Only apply persistent override if admin forced a module open (detailed).
            # Never let admin-hidden override a trigger-opened state.
            for m, state in persistent.items():
                if state == "detailed" and m in result:
                    result[m] = "detailed"
    except Exception:
        pass  # graceful — Supabase may be unavailable; admin overrides are optional

    return TriggerResponse(module_display=result, trigger_type=req.trigger_type)


@router.get("/stream/{site_id}")
async def stream_decisions(site_id: str):
    """
    SSE endpoint — pushes DecisionMomentPayload to the kiosk display.

    Data flow:
      Event bus CRITICAL/INFO event fires
        → event_bus_subscribers assembles payload and calls cache_decision_payload()
        → SSE handler reads from _payload_cache via get_cached_payload()
        → pushes as SSE 'data:' line to all connected kiosk clients

    Transport: text/event-stream (Server-Sent Events).
    Pattern: plain StreamingResponse + async generator (same as mcp_sse.py).
    Heartbeat: SSE comment every 15s keeps Nginx/proxy from closing idle connection.

    Kiosk behaviour:
      - Connects on load
      - Re-renders on every 'message' event
      - Falls back to REST polling (/api/decisions/current/{site_id}) if EventSource errors
    """
    from app.services.event_bus import Importance, get_event_bus

    async def event_generator():
        # Send current cached payload immediately on connect (instant first render)
        cached = get_cached_payload(site_id)
        if cached:
            yield f"data: {_json.dumps(cached)}\n\n"
        else:
            # No active fault — push a quiet-state sentinel so kiosk knows it connected
            yield f"data: {_json.dumps({'renderer_hint': 'quiet', 'building_id': site_id, '_connected': True})}\n\n"

        last_heartbeat = asyncio.get_event_loop().time()
        queue: asyncio.Queue = asyncio.Queue(maxsize=10)

        # stopped flag: set in finally block; checked in handler before queuing
        # prevents dead-queue leaks if client disconnects before the finally block runs
        stopped = False

        async def _on_event(event):
            """Push updated payload to this connection's queue."""
            if stopped:
                return
            payload = get_cached_payload(site_id)
            if payload:
                try:
                    queue.put_nowait(payload)
                except asyncio.QueueFull:
                    # Drop oldest and insert latest — kiosk always gets freshest state
                    with contextlib.suppress(asyncio.QueueEmpty):
                        queue.get_nowait()
                    with contextlib.suppress(asyncio.QueueFull):
                        queue.put_nowait(payload)

        # Subscribe to all event types for this site
        bus = get_event_bus()
        sub_id = bus.subscribe(
            pattern="*",
            handler=_on_event,
            min_importance=Importance.INFO,
            filter=lambda e: (e.site_id or "") == site_id,
        )

        try:
            while True:
                now = asyncio.get_event_loop().time()
                # Heartbeat comment every 15s — keeps proxy from closing idle connection
                if now - last_heartbeat >= 15:
                    yield ": keep-alive\n\n"
                    last_heartbeat = now

                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=1.0)
                    yield f"data: {_json.dumps(payload)}\n\n"
                except TimeoutError:
                    pass  # Loop back — check heartbeat, wait again

        except asyncio.CancelledError:
            pass
        finally:
            stopped = True
            # Unsubscribe when client disconnects — prevents dead-queue leaks
            with contextlib.suppress(Exception):
                bus.unsubscribe(sub_id)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Disable Nginx buffering
            "Connection": "keep-alive",
        },
    )
