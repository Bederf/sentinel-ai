"""
n8n Event Bus Subscriber for SENTINEL.

Connects the SENTINEL event bus to n8n workflow webhooks. When events fire on the
bus, this subscriber triggers the corresponding n8n workflows via their webhook URLs.

Webhook path convention:
    Event type "maintenance.work_order_created" -> webhook path "work-order-created"
    Or use explicit mappings for custom webhook paths.

Register at startup after register_default_subscribers():
    from app.services.n8n_event_subscriber import register_n8n_subscribers
    register_n8n_subscribers()
"""

import logging
from typing import Dict

from app.services.event_bus import Importance, SentinelEvent, get_event_bus
from app.services.n8n_service import get_n8n_service

logger = logging.getLogger("sentinel.n8n_events")


# ---------------------------------------------------------------------------
# Webhook Path Mappings
# ---------------------------------------------------------------------------

# Explicit mappings: event_type -> n8n webhook path.
# Unmapped events auto-convert: dots->hyphens, underscores->hyphens.
WEBHOOK_MAPPINGS: Dict[str, str] = {
    "maintenance.work_order_created": "work-order-created",
    "maintenance.work_order_completed": "work-order-completed",
    "sentry.escalation_triggered": "escalation",
    "sensor.anomaly_detected": "anomaly-detected",
    "ai.diagnosis_complete": "diagnosis-complete",
    "energy.load_shedding_started": "load-shedding",
    "system.health_check_failed": "system-alert",
}


def _event_to_webhook_path(event_type: str) -> str:
    """Convert event type to webhook path."""
    if event_type in WEBHOOK_MAPPINGS:
        return WEBHOOK_MAPPINGS[event_type]
    return event_type.replace(".", "-").replace("_", "-")


# ---------------------------------------------------------------------------
# Subscriber Registration
# ---------------------------------------------------------------------------


def register_n8n_subscribers() -> None:
    """Register n8n webhook subscribers on the event bus.

    Call at startup after register_default_subscribers().
    Gracefully skips all triggers if n8n is not configured.
    """
    bus = get_event_bus()

    # ------------------------------------------------------------------
    # Work Order Dispatch -> n8n
    # ------------------------------------------------------------------

    @bus.on("maintenance.work_order_created")
    async def dispatch_work_order(event: SentinelEvent) -> None:
        """Trigger n8n workflow for contractor/technician dispatch."""
        service = get_n8n_service()
        if not service.is_configured:
            return

        result = await service.trigger_webhook(
            webhook_path=_event_to_webhook_path(event.event_type),
            payload={
                "event_id": event.event_id,
                "event_type": event.event_type,
                "work_order_id": event.payload.get("work_order_id"),
                "site_id": event.site_id,
                "building_name": event.building_name,
                "equipment_id": event.equipment_id,
                "priority": event.payload.get("priority"),
                "description": event.payload.get("description"),
                "importance": event.importance.name,
                "correlation_id": event.correlation_id,
                "timestamp": event.timestamp,
            },
        )

        if result.get("success"):
            logger.info(
                "[N8N] Work order dispatch triggered: %s",
                event.payload.get("work_order_id", "unknown"),
            )
        else:
            logger.error(
                "[N8N] Work order dispatch failed: %s",
                result.get("reason", "unknown"),
            )

    # ------------------------------------------------------------------
    # Escalation -> n8n
    # ------------------------------------------------------------------

    @bus.on("sentry.escalation_triggered")
    async def handle_escalation(event: SentinelEvent) -> None:
        """Trigger n8n escalation workflow when notification goes unacknowledged."""
        service = get_n8n_service()
        if not service.is_configured:
            return

        await service.trigger_webhook(
            webhook_path="escalation",
            payload={
                "event_id": event.event_id,
                "original_event": event.payload.get("original_event"),
                "site_id": event.site_id,
                "building_name": event.building_name,
                "escalation_reason": event.payload.get("reason", "No acknowledgement"),
                "importance": event.importance.name,
                "timestamp": event.timestamp,
            },
        )

    # ------------------------------------------------------------------
    # System Alerts -> n8n
    # ------------------------------------------------------------------

    @bus.on("system.*", min_importance=Importance.HIGH)
    async def handle_system_alert(event: SentinelEvent) -> None:
        """System-level alerts trigger n8n for admin notification."""
        service = get_n8n_service()
        if not service.is_configured:
            return

        await service.trigger_webhook(
            webhook_path="system-alert",
            payload={
                "event_type": event.event_type,
                "message": event.payload.get("message", "System alert"),
                "severity": event.importance.name,
                "site_id": event.site_id,
                "timestamp": event.timestamp,
            },
        )

    logger.info("n8n event subscribers registered")
