"""Persistence layer for Desigo building alarms.

3-tier fallback: Supabase -> JSON file.
JSON fallback at backend/app/data/plant/building_alarms.json.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.plant.models import DesigoBuildingAlarm

logger = logging.getLogger(__name__)

_JSON_PATH = Path(__file__).parent.parent / "data" / "plant" / "building_alarms.json"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _ensure_json_dir() -> None:
    """Create the data/plant directory if it does not exist."""
    _JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not _JSON_PATH.exists():
        _JSON_PATH.write_text("[]", encoding="utf-8")


def _read_json() -> list[dict]:
    """Read alarms from JSON fallback file."""
    _ensure_json_dir()
    try:
        raw = _JSON_PATH.read_text(encoding="utf-8")
        return json.loads(raw) if raw.strip() else []
    except Exception:
        logger.exception("Failed to read alarm JSON fallback")
        return []


def _write_json(records: list[dict]) -> None:
    """Write alarms to JSON fallback file."""
    _ensure_json_dir()
    _JSON_PATH.write_text(json.dumps(records, indent=2, default=str), encoding="utf-8")


def _get_supabase():
    """Return Supabase client or None when unavailable."""
    try:
        from app.database.supabase_client import get_supabase_client

        client = get_supabase_client()
        # Quick sanity: if it's a dummy/testing client, treat as unavailable
        if type(client).__name__ == "_DummySupabaseClient":
            return None
        return client
    except Exception:
        return None


def _alarm_to_dict(alarm: DesigoBuildingAlarm) -> dict:
    """Serialize an alarm to a plain dict suitable for storage."""
    data = alarm.model_dump()
    data["severity"] = alarm.severity.value
    data["received_at"] = alarm.received_at.isoformat()
    data["notified_at"] = alarm.notified_at.isoformat() if alarm.notified_at else None
    data["cleared_at"] = alarm.cleared_at.isoformat() if alarm.cleared_at else None
    return data


def _dict_to_alarm(data: dict) -> DesigoBuildingAlarm:
    """Deserialize a dict back to a DesigoBuildingAlarm."""
    return DesigoBuildingAlarm(**data)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def save_alarm(alarm: DesigoBuildingAlarm) -> bool:
    """Persist a building alarm.

    Tries Supabase first; falls back to JSON on failure.
    Returns True on success.
    """
    record = _alarm_to_dict(alarm)

    # Tier 1: Supabase
    client = _get_supabase()
    if client is not None:
        try:
            client.table("building_alarms").insert(record).execute()
            logger.info("Alarm %s saved to Supabase", alarm.id)
            return True
        except Exception:
            logger.warning("Supabase insert failed for alarm %s, falling back to JSON", alarm.id)

    # Tier 2: JSON fallback
    try:
        records = _read_json()
        records.append(record)
        _write_json(records)
        logger.info("Alarm %s saved to JSON fallback", alarm.id)
        return True
    except Exception:
        logger.exception("Failed to save alarm %s", alarm.id)
        return False


async def get_recent_alarms(site_id: str, limit: int = 50) -> list[DesigoBuildingAlarm]:
    """Return the most recent alarms for a site.

    Tries Supabase first; falls back to JSON.
    """
    # Tier 1: Supabase
    client = _get_supabase()
    if client is not None:
        try:
            resp = (
                client.table("building_alarms")
                .select("*")
                .eq("site_id", site_id)
                .order("received_at", desc=True)
                .limit(limit)
                .execute()
            )
            return [_dict_to_alarm(r) for r in resp.data]
        except Exception:
            logger.warning("Supabase query failed for site %s, falling back to JSON", site_id)

    # Tier 2: JSON fallback
    records = _read_json()
    filtered = [r for r in records if r.get("site_id") == site_id]
    filtered.sort(key=lambda r: r.get("received_at", ""), reverse=True)
    return [_dict_to_alarm(r) for r in filtered[:limit]]


async def mark_notified(alarm_id: str) -> bool:
    """Set notified=True and notified_at=now for the given alarm.

    Returns True on success.
    """
    now = datetime.now(UTC).isoformat()

    # Tier 1: Supabase
    client = _get_supabase()
    if client is not None:
        try:
            client.table("building_alarms").update({"notified": True, "notified_at": now}).eq("id", alarm_id).execute()
            return True
        except Exception:
            logger.warning("Supabase update failed for alarm %s, falling back to JSON", alarm_id)

    # Tier 2: JSON fallback
    try:
        records = _read_json()
        for r in records:
            if r.get("id") == alarm_id:
                r["notified"] = True
                r["notified_at"] = now
                break
        _write_json(records)
        return True
    except Exception:
        logger.exception("Failed to mark alarm %s as notified", alarm_id)
        return False


async def mark_cleared(alarm_id: str) -> bool:
    """Set cleared=True and cleared_at=now for the given alarm.

    Returns True on success.
    """
    now = datetime.now(UTC).isoformat()

    # Tier 1: Supabase
    client = _get_supabase()
    if client is not None:
        try:
            client.table("building_alarms").update({"cleared": True, "cleared_at": now}).eq("id", alarm_id).execute()
            return True
        except Exception:
            logger.warning("Supabase update failed for alarm %s, falling back to JSON", alarm_id)

    # Tier 2: JSON fallback
    try:
        records = _read_json()
        for r in records:
            if r.get("id") == alarm_id:
                r["cleared"] = True
                r["cleared_at"] = now
                break
        _write_json(records)
        return True
    except Exception:
        logger.exception("Failed to mark alarm %s as cleared", alarm_id)
        return False


async def check_duplicate(subject: str, window_hours: int = 1) -> bool:
    """Check if an alarm with the same subject exists within the time window.

    Returns True if a duplicate is found.
    """
    cutoff = datetime.now(UTC) - timedelta(hours=window_hours)

    # Tier 1: Supabase
    client = _get_supabase()
    if client is not None:
        try:
            resp = (
                client.table("building_alarms")
                .select("id")
                .eq("raw_subject", subject)
                .gte("received_at", cutoff.isoformat())
                .limit(1)
                .execute()
            )
            return len(resp.data) > 0
        except Exception:
            logger.warning("Supabase duplicate check failed, falling back to JSON")

    # Tier 2: JSON fallback
    records = _read_json()
    for r in records:
        if r.get("raw_subject") == subject:
            try:
                received = datetime.fromisoformat(r["received_at"])
                # Ensure timezone-aware comparison
                if received.tzinfo is None:
                    received = received.replace(tzinfo=UTC)
                if received >= cutoff:
                    return True
            except (ValueError, KeyError):
                continue
    return False
