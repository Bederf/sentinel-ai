"""REST API endpoints for Block Booking Detection.

Provides endpoints to list alerts, dismiss alerts, list ingested bookings,
view/update config, trigger manual scans, and ingest booking emails.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.config.settings import settings
from app.core.site_resolver import require_any_site
from app.models.booking_record import BlockBookingConfig

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/block-bookings", tags=["block-bookings"])


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class BookingEmailRequest(BaseModel):
    """Inbound booking confirmation email for parsing."""

    raw_email: str = Field(..., description="Raw email content (RFC 822)")
    site_id: str = Field(..., description="Site code")


class DismissRequest(BaseModel):
    """Dismiss an alert."""

    dismissed_by: str = Field(..., description="Who dismissed the alert")


class ConfigUpdateRequest(BaseModel):
    """Update block booking config."""

    min_rooms_for_alert: Optional[int] = None
    full_day_threshold_hours: Optional[float] = None
    lookahead_days: Optional[int] = None
    enabled: Optional[bool] = None
    concierge_email: Optional[str] = None
    concierge_whatsapp: Optional[str] = None
    concierge_telegram_chat_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

# In-memory config per site, seeded from JSON then env vars as fallback
_site_configs: dict[str, BlockBookingConfig] = {}
_site_configs_loaded: bool = False


def _load_site_configs() -> None:
    """Load per-site concierge config from block_booking_sites.json."""
    global _site_configs_loaded
    if _site_configs_loaded:
        return
    _site_configs_loaded = True

    import json
    from pathlib import Path

    config_path = Path(__file__).parent.parent / "data" / "block_booking_sites.json"
    if not config_path.exists():
        return

    try:
        data = json.loads(config_path.read_text())
        for site_id, cfg in data.items():
            _site_configs[site_id] = BlockBookingConfig(
                site_id=site_id,
                min_rooms_for_alert=cfg.get("min_rooms_for_alert", 3),
                enabled=cfg.get("enabled", settings.block_booking_enabled),
                concierge_email=cfg.get("concierge_email") or None,
                concierge_whatsapp=cfg.get("concierge_whatsapp") or None,
                concierge_telegram_chat_id=cfg.get("concierge_telegram_chat_id") or None,
            )
        logger.info("Loaded block booking config for %d sites", len(data))
    except Exception as exc:
        logger.warning("Failed to load block_booking_sites.json: %s", exc)


def _get_config(site_id: str) -> BlockBookingConfig:
    """Get or create config for a site, seeded from JSON file then env vars."""
    _load_site_configs()
    if site_id not in _site_configs:
        _site_configs[site_id] = BlockBookingConfig(
            site_id=site_id,
            min_rooms_for_alert=settings.block_booking_min_rooms,
            enabled=settings.block_booking_enabled,
            concierge_email=settings.block_booking_concierge_email or None,
            concierge_whatsapp=settings.block_booking_concierge_whatsapp or None,
            concierge_telegram_chat_id=(settings.block_booking_concierge_telegram_id or None),
        )
    return _site_configs[site_id]


def get_block_booking_config(site_id: str) -> BlockBookingConfig:
    """Public accessor for per-site concierge and threshold configuration."""
    return _get_config(site_id)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/ingest")
async def ingest_booking_email(
    request: Request,
    body: BookingEmailRequest,
) -> dict[str, Any]:
    """Ingest a booking confirmation email and check for overlaps.

    Called by n8n or directly when SENTINEL receives a BCC'd booking email.
    """
    from app.services.block_booking_detector.booking_store import get_booking_store
    from app.services.block_booking_detector.email_parser import (
        extract_cancelled_room,
        is_cancellation,
        parse_booking_confirmation,
    )
    from app.services.block_booking_detector.notifier import (
        send_block_booking_alert,
    )
    from app.services.block_booking_detector.overlap_detector import detect_overlaps

    config = _get_config(body.site_id)
    if not config.enabled:
        return {"success": False, "reason": "Block booking detection disabled"}

    store = get_booking_store()

    # Handle cancellations
    if is_cancellation(body.raw_email):
        info = extract_cancelled_room(body.raw_email, body.site_id)
        if info:
            removed = store.remove_booking(
                site_id=body.site_id,
                organiser_email=info["organiser_email"],
                room_name=info["room_name"],
                start_time=info.get("start_time"),
            )
            return {
                "success": True,
                "action": "cancellation_processed",
                "removed": removed,
            }
        return {"success": True, "action": "cancellation_unparseable"}

    # Parse booking
    record = parse_booking_confirmation(body.raw_email, body.site_id)
    if not record:
        return {"success": False, "reason": "Could not parse booking email"}

    # Dedup
    if store.booking_exists(record.raw_email_hash):
        return {"success": True, "action": "duplicate_skipped"}

    # Save
    saved = store.save_booking(record)

    # Scan for overlaps on this booking's date
    day_bookings = store.get_bookings_for_site(body.site_id, record.booking_date)
    new_alerts = detect_overlaps(body.site_id, day_bookings, config, store)

    # Persist and notify
    alerts_sent = 0
    for alert in new_alerts:
        stored_alert = store.save_alert(alert)
        sent = await send_block_booking_alert(stored_alert, config)
        if sent:
            alerts_sent += 1

    return {
        "success": True,
        "action": "booking_ingested",
        "booking_id": saved.id,
        "organiser": saved.organiser_email,
        "room": saved.room_name,
        "date": saved.booking_date.isoformat(),
        "alerts_generated": len(new_alerts),
        "alerts_notified": alerts_sent,
    }


@router.get("/alerts")
async def list_alerts(
    site_id: str = Depends(require_any_site),
) -> dict[str, Any]:
    """List open (undismissed) block booking alerts for a site."""
    from app.services.block_booking_detector.booking_store import get_booking_store

    store = get_booking_store()
    alerts = store.get_open_alerts(site_id)
    return {
        "alerts": [
            {
                "id": a.id,
                "organiser_email": a.organiser_email,
                "organiser_name": a.organiser_name,
                "rooms": a.rooms,
                "room_count": a.room_count,
                "overlap_window_start": a.overlap_window_start.isoformat(),
                "overlap_window_end": a.overlap_window_end.isoformat(),
                "detected_at": a.detected_at.isoformat(),
                "notification_sent": a.notification_sent,
                "dismissed": a.dismissed,
            }
            for a in alerts
        ],
        "count": len(alerts),
    }


@router.get("/alerts/{alert_id}")
async def get_alert(alert_id: str) -> dict[str, Any]:
    """Get a single alert by ID."""
    from app.services.block_booking_detector.booking_store import get_booking_store

    store = get_booking_store()
    alert = store.get_alert_by_id(alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    return {
        "id": alert.id,
        "site_id": alert.site_id,
        "organiser_email": alert.organiser_email,
        "organiser_name": alert.organiser_name,
        "rooms": alert.rooms,
        "room_count": alert.room_count,
        "booking_ids": alert.booking_ids,
        "overlap_window_start": alert.overlap_window_start.isoformat(),
        "overlap_window_end": alert.overlap_window_end.isoformat(),
        "detected_at": alert.detected_at.isoformat(),
        "notification_sent": alert.notification_sent,
        "notification_sent_at": (alert.notification_sent_at.isoformat() if alert.notification_sent_at else None),
        "dismissed": alert.dismissed,
        "dismissed_at": (alert.dismissed_at.isoformat() if alert.dismissed_at else None),
        "dismissed_by": alert.dismissed_by,
    }


@router.post("/alerts/{alert_id}/dismiss")
async def dismiss_alert(
    alert_id: str,
    body: DismissRequest,
) -> dict[str, Any]:
    """Concierge dismisses an alert after handling it."""
    from app.services.block_booking_detector.booking_store import get_booking_store

    store = get_booking_store()
    alert = store.dismiss_alert(alert_id, body.dismissed_by)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    return {
        "success": True,
        "alert_id": alert.id,
        "dismissed": True,
        "dismissed_by": alert.dismissed_by,
    }


@router.get("/bookings")
async def list_bookings(
    site_id: str = Depends(require_any_site),
    from_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    to_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
) -> dict[str, Any]:
    """List ingested bookings for a site within a date range."""
    from app.services.block_booking_detector.booking_store import get_booking_store

    store = get_booking_store()
    today = date.today()
    start = date.fromisoformat(from_date) if from_date else today
    end = date.fromisoformat(to_date) if to_date else today + timedelta(days=14)

    all_bookings = []
    current = start
    while current <= end:
        day_bookings = store.get_bookings_for_site(site_id, current)
        all_bookings.extend(day_bookings)
        current += timedelta(days=1)

    return {
        "bookings": [
            {
                "id": b.id,
                "organiser_email": b.organiser_email,
                "organiser_name": b.organiser_name,
                "room_name": b.room_name,
                "booking_date": b.booking_date.isoformat(),
                "start_time": b.start_time.isoformat(),
                "end_time": b.end_time.isoformat(),
                "flagged": b.flagged,
            }
            for b in all_bookings
        ],
        "count": len(all_bookings),
        "from_date": start.isoformat(),
        "to_date": end.isoformat(),
    }


@router.get("/config")
async def get_config(
    site_id: str = Depends(require_any_site),
) -> dict[str, Any]:
    """Get block booking detection config for a site."""
    config = _get_config(site_id)
    return {
        "site_id": config.site_id,
        "min_rooms_for_alert": config.min_rooms_for_alert,
        "full_day_threshold_hours": config.full_day_threshold_hours,
        "lookahead_days": config.lookahead_days,
        "enabled": config.enabled,
        "concierge_email": config.concierge_email,
        "concierge_whatsapp": config.concierge_whatsapp,
        "concierge_telegram_chat_id": config.concierge_telegram_chat_id,
    }


@router.put("/config")
async def update_config(
    body: ConfigUpdateRequest,
    site_id: str = Depends(require_any_site),
) -> dict[str, Any]:
    """Update block booking detection config for a site."""
    config = _get_config(site_id)
    if body.min_rooms_for_alert is not None:
        config.min_rooms_for_alert = body.min_rooms_for_alert
    if body.full_day_threshold_hours is not None:
        config.full_day_threshold_hours = body.full_day_threshold_hours
    if body.lookahead_days is not None:
        config.lookahead_days = body.lookahead_days
    if body.enabled is not None:
        config.enabled = body.enabled
    if body.concierge_email is not None:
        config.concierge_email = body.concierge_email
    if body.concierge_whatsapp is not None:
        config.concierge_whatsapp = body.concierge_whatsapp
    if body.concierge_telegram_chat_id is not None:
        config.concierge_telegram_chat_id = body.concierge_telegram_chat_id
    return {
        "success": True,
        "config": {
            "site_id": config.site_id,
            "min_rooms_for_alert": config.min_rooms_for_alert,
            "full_day_threshold_hours": config.full_day_threshold_hours,
            "lookahead_days": config.lookahead_days,
            "enabled": config.enabled,
            "concierge_email": config.concierge_email,
            "concierge_whatsapp": config.concierge_whatsapp,
            "concierge_telegram_chat_id": config.concierge_telegram_chat_id,
        },
    }


@router.post("/scan")
async def trigger_scan(
    site_id: str = Depends(require_any_site),
) -> dict[str, Any]:
    """Manually trigger an overlap scan for the next N days."""
    from app.services.block_booking_detector.booking_store import get_booking_store
    from app.services.block_booking_detector.notifier import send_block_booking_alert
    from app.services.block_booking_detector.overlap_detector import detect_overlaps

    config = _get_config(site_id)
    if not config.enabled:
        return {"success": False, "reason": "Block booking detection disabled"}

    store = get_booking_store()
    today = date.today()
    total_alerts = 0

    for day_offset in range(config.lookahead_days):
        target_date = today + timedelta(days=day_offset)
        bookings = store.get_bookings_for_site(site_id, target_date)
        new_alerts = detect_overlaps(site_id, bookings, config, store)

        for alert in new_alerts:
            stored_alert = store.save_alert(alert)
            await send_block_booking_alert(stored_alert, config)
            total_alerts += 1

    return {
        "success": True,
        "days_scanned": config.lookahead_days,
        "alerts_generated": total_alerts,
    }
