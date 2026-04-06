"""Fuel Alert Service — routes critical fuel events to notification channels (Phase 150).

Subscribes to fuel.* events on the event bus and broadcasts CRITICAL/WARNING
alerts via NotificationService (Telegram, WhatsApp, SMS). INFO-level events
(refill_detected, runtime_complete) are logged but not pushed.

Usage:
    # Registered automatically at startup in events.py when fuel_monitoring_enabled
    from app.services.fuel_alert_service import get_fuel_alert_service

    service = get_fuel_alert_service()
    await service.handle_fuel_event(sentinel_event)
"""

from __future__ import annotations

import logging

from app.models.fuel import FuelEventType

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Severity mapping: FuelEventType -> alert level string
# ---------------------------------------------------------------------------

# Maps each fuel event type to a severity level for notification routing.
# CRITICAL/WARNING events trigger broadcast_alert; INFO events are logged only.
SEVERITY_MAP: dict[str, str] = {
    FuelEventType.THEFT_ALERT: "CRITICAL",
    FuelEventType.LEAK_DETECTED: "CRITICAL",
    FuelEventType.LOW_FUEL: "WARNING",  # Escalated to CRITICAL inside if pct_2
    FuelEventType.TEMP_ALERT: "WARNING",
    FuelEventType.SENSOR_FAULT: "WARNING",
    FuelEventType.REFILL_DETECTED: "INFO",
    FuelEventType.RUNTIME_COMPLETE: "INFO",
}


def _classify_severity(event_type: str, payload: dict) -> str:
    """Return the alert severity for a fuel event.

    Low fuel events are escalated to CRITICAL when the severity field in
    the payload says "CRITICAL" (below pct_2 threshold).
    """
    base = SEVERITY_MAP.get(event_type, "INFO")

    # Low fuel escalation: the FuelEventProcessor sets severity in the payload
    if event_type == FuelEventType.LOW_FUEL:
        payload_severity = payload.get("severity", "")
        if payload_severity == "CRITICAL":
            return "CRITICAL"
        return "WARNING"

    return base


def _build_alert_title(event_type: str, tank_id: str) -> str:
    """Build a human-readable alert title."""
    label = event_type.upper().replace("_", " ")
    return f"FUEL {label} - {tank_id}"


def _build_alert_body(event_type: str, payload: dict) -> str:
    """Build a descriptive alert body with key metrics."""
    parts: list[str] = []

    if event_type == FuelEventType.THEFT_ALERT:
        parts.append("Suspected fuel theft detected.")
        parts.append(f"Loss rate: {payload.get('loss_rate_lpm', '?')} L/min")
        parts.append(f"Volume lost: {payload.get('loss_litres', '?')} L")
        parts.append(f"Duration: {payload.get('time_delta_min', '?')} min")

    elif event_type == FuelEventType.LEAK_DETECTED:
        parts.append("Sustained fuel leak detected.")
        parts.append(f"Duration: {payload.get('sustained_minutes', '?')} min")
        parts.append(f"Readings: {payload.get('readings_count', '?')}")

    elif event_type == FuelEventType.LOW_FUEL:
        level = payload.get("fuel_level_pct", "?")
        threshold = payload.get("threshold_pct", "?")
        severity = payload.get("severity", "WARNING")
        parts.append(f"Fuel level {severity}: {level}% (threshold: {threshold}%)")

    elif event_type == FuelEventType.TEMP_ALERT:
        temp = payload.get("fuel_temp_c", "?")
        if "threshold_min_c" in payload:
            parts.append(f"Fuel temperature too low: {temp}C (min: {payload['threshold_min_c']}C)")
        elif "threshold_max_c" in payload:
            parts.append(f"Fuel temperature too high: {temp}C (max: {payload['threshold_max_c']}C)")
        else:
            parts.append(f"Fuel temperature alert: {temp}C")

    elif event_type == FuelEventType.SENSOR_FAULT:
        parts.append("Fuel sensor fault detected.")
        parts.append(f"Sensor reading: {payload.get('sensor_ma', '?')} mA")

    else:
        parts.append(f"Fuel event: {event_type}")

    return " | ".join(parts)


class FuelAlertService:
    """Routes critical fuel events to the notification pipeline."""

    async def handle_fuel_event(self, event) -> None:
        """Handle a fuel.* SentinelEvent from the event bus.

        Classifies severity and broadcasts CRITICAL/WARNING alerts.
        INFO-level events are logged but not pushed to notification channels.
        """
        payload = event.payload if hasattr(event, "payload") else {}
        event_subtype = payload.get("event_subtype", "")
        tank_id = payload.get("tank_id", "unknown")

        if not event_subtype:
            logger.debug("Fuel alert service: no event_subtype in payload, skipping")
            return

        severity = _classify_severity(event_subtype, payload)

        if severity == "INFO":
            logger.info("Fuel event %s for %s (INFO, no notification)", event_subtype, tank_id)
            return

        title = _build_alert_title(event_subtype, tank_id)
        body = _build_alert_body(event_subtype, payload)

        logger.warning("Fuel alert [%s]: %s — %s", severity, title, body)

        # Map severity to AlertLevel enum
        try:
            from app.models.notification import AlertLevel
            from app.services.notification_service import NotificationService

            alert_level = AlertLevel.CRITICAL if severity == "CRITICAL" else AlertLevel.WARNING
            notification_service = NotificationService()
            result = await notification_service.broadcast_alert(
                title=title,
                body=body,
                alert_level=alert_level,
                notification_type="fuel_alert",
            )
            if result.get("success"):
                logger.info("Fuel alert broadcast sent to %d recipient(s)", result.get("recipients_notified", 0))
            else:
                logger.warning("Fuel alert broadcast failed: %s", result.get("errors", []))
        except Exception as exc:
            logger.warning("NotificationService unavailable for fuel alert (non-fatal): %s", exc)


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_instance: FuelAlertService | None = None


def get_fuel_alert_service() -> FuelAlertService:
    """Return the singleton FuelAlertService instance."""
    global _instance
    if _instance is None:
        _instance = FuelAlertService()
    return _instance
