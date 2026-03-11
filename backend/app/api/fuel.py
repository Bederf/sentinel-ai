"""Fuel monitoring API endpoints (Phase 150).

Exposes fuel tank telemetry, events, generator runtime, and refill log
for dashboard consumption. All data sourced from FuelStore and
FuelEventProcessor.

Endpoints:
    GET /api/fuel/tanks              — list tanks for site
    GET /api/fuel/tanks/{tank_id}    — single tank + latest telemetry
    GET /api/fuel/tanks/{tank_id}/history — time-series telemetry
    GET /api/fuel/events             — fuel events list
    GET /api/fuel/generator-runtime  — generator runtime sessions
    GET /api/fuel/refill-log         — refill events
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/api/fuel", tags=["fuel"])
logger = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).parent.parent / "data" / "fuel"
_TELEMETRY_FILE = _DATA_DIR / "telemetry.json"
_EVENTS_FILE = _DATA_DIR / "events.json"


def _get_fuel_store():
    """Lazy import to avoid circular imports."""
    from app.services.fuel_store import get_fuel_store

    return get_fuel_store()


def _serialise_datetime(obj):
    """JSON-safe datetime conversion."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    return obj


def _tank_config_to_dict(cfg) -> dict:
    """Convert FuelTankConfig dataclass to dict."""
    return asdict(cfg)


def _telemetry_to_dict(t) -> dict:
    """Convert FuelTelemetry dataclass to JSON-safe dict."""
    d = asdict(t)
    if isinstance(d.get("received_at"), datetime):
        d["received_at"] = d["received_at"].isoformat()
    return d


@router.get("/tanks")
async def list_tanks(site_id: Optional[str] = Query(None, description="Filter by site ID")):
    """List all fuel tanks, optionally filtered by site_id."""
    store = _get_fuel_store()
    tanks = store.get_all_tanks(site_id=site_id)
    result = []
    for cfg in tanks:
        tank_dict = _tank_config_to_dict(cfg)
        # Attach latest telemetry if available
        latest = await store.get_latest_telemetry(cfg.tank_id)
        if latest:
            tank_dict["latest_telemetry"] = _telemetry_to_dict(latest)
        else:
            tank_dict["latest_telemetry"] = None
        result.append(tank_dict)
    return {"tanks": result, "count": len(result)}


@router.get("/tanks/{tank_id}")
async def get_tank(tank_id: str):
    """Get a single tank with latest telemetry and derived fields."""
    store = _get_fuel_store()
    cfg = store.get_tank_config(tank_id)
    if cfg is None:
        raise HTTPException(status_code=404, detail=f"Tank {tank_id} not found")

    tank_dict = _tank_config_to_dict(cfg)
    latest = await store.get_latest_telemetry(tank_id)
    if latest:
        tank_dict["latest_telemetry"] = _telemetry_to_dict(latest)
    else:
        tank_dict["latest_telemetry"] = None
    return tank_dict


@router.get("/tanks/{tank_id}/history")
async def get_tank_history(
    tank_id: str,
    hours: int = Query(24, description="Hours of history to return", ge=1, le=720),
):
    """Get time-series telemetry for a tank."""
    store = _get_fuel_store()
    cfg = store.get_tank_config(tank_id)
    if cfg is None:
        raise HTTPException(status_code=404, detail=f"Tank {tank_id} not found")

    # Read from JSON telemetry file (append-only JSONL)
    records: list[dict] = []
    cutoff_ts = int((datetime.now(tz=timezone.utc).timestamp() - hours * 3600))
    if _TELEMETRY_FILE.exists():
        try:
            with open(_TELEMETRY_FILE) as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                        if rec.get("tank_id") == tank_id and rec.get("ts", 0) >= cutoff_ts:
                            records.append(rec)
                    except json.JSONDecodeError:
                        continue
        except Exception as exc:
            logger.warning("Failed to read telemetry history: %s", exc)

    return {"tank_id": tank_id, "hours": hours, "readings": records, "count": len(records)}


@router.get("/events")
async def list_events(
    site_id: Optional[str] = Query(None, description="Filter by site ID"),
    event_type: Optional[str] = Query(None, description="Filter by event type"),
    limit: int = Query(50, description="Max events to return", ge=1, le=500),
):
    """List fuel events, optionally filtered by site_id and event_type."""
    events: list[dict] = []

    # Read from events JSONL file
    if _EVENTS_FILE.exists():
        try:
            with open(_EVENTS_FILE) as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                        if site_id and rec.get("site_id") != site_id:
                            continue
                        if event_type and rec.get("event_type") != event_type:
                            continue
                        events.append(rec)
                    except json.JSONDecodeError:
                        continue
        except Exception as exc:
            logger.warning("Failed to read fuel events: %s", exc)

    # Return most recent first, limited
    events.sort(key=lambda e: e.get("ts", 0), reverse=True)
    events = events[:limit]

    return {"events": events, "count": len(events)}


@router.get("/generator-runtime")
async def get_generator_runtime(
    site_id: Optional[str] = Query(None, description="Filter by site ID"),
    limit: int = Query(50, description="Max sessions to return", ge=1, le=500),
):
    """Get generator runtime sessions from fuel events."""
    sessions: list[dict] = []

    if _EVENTS_FILE.exists():
        try:
            with open(_EVENTS_FILE) as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                        if rec.get("event_type") != "runtime_complete":
                            continue
                        if site_id and rec.get("site_id") != site_id:
                            continue
                        sessions.append(rec)
                    except json.JSONDecodeError:
                        continue
        except Exception as exc:
            logger.warning("Failed to read runtime sessions: %s", exc)

    sessions.sort(key=lambda s: s.get("ts", 0), reverse=True)
    sessions = sessions[:limit]

    return {"sessions": sessions, "count": len(sessions)}


@router.get("/refill-log")
async def get_refill_log(
    site_id: Optional[str] = Query(None, description="Filter by site ID"),
    limit: int = Query(50, description="Max refills to return", ge=1, le=500),
):
    """Get refill events from fuel events store."""
    refills: list[dict] = []

    if _EVENTS_FILE.exists():
        try:
            with open(_EVENTS_FILE) as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                        if rec.get("event_type") != "refill_detected":
                            continue
                        if site_id and rec.get("site_id") != site_id:
                            continue
                        refills.append(rec)
                    except json.JSONDecodeError:
                        continue
        except Exception as exc:
            logger.warning("Failed to read refill log: %s", exc)

    refills.sort(key=lambda r: r.get("ts", 0), reverse=True)
    refills = refills[:limit]

    return {"refills": refills, "count": len(refills)}
