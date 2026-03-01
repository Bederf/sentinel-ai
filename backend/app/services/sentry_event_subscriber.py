"""
Sentry Notification Event Subscriber.

Connects the event bus to the SentryNotificationRouter. Single '*' subscriber
routes every event through the router, which decides push vs digest vs log-only.

Replaces the stub push/digest subscribers (#2, #3) from event_subscribers.py.

Register at startup:
    from app.services.sentry_event_subscriber import register_sentry_subscribers
    register_sentry_subscribers()
"""

import logging

from app.services.event_bus import Importance, SentinelEvent, get_event_bus
from app.services.sentry_notification_router import (
    DeliveryChannel,
    NotificationRecipient,
    get_sentry_router,
)

logger = logging.getLogger("sentinel.sentry_events")


def register_sentry_subscribers():
    """Register the Sentry notification router on the event bus.

    Call at startup AFTER register_default_subscribers().
    """
    bus = get_event_bus()
    router = get_sentry_router()

    # ---------------------------------------------------------------
    # Register default recipients
    # TODO: Load from database/config instead of hardcoding
    # ---------------------------------------------------------------

    router.add_recipient(
        NotificationRecipient(
            name="Peter Marshall",
            role="manager",
            channels=[DeliveryChannel.WHATSAPP, DeliveryChannel.EMAIL],
            min_importance=Importance.MEDIUM,
            # whatsapp="+27...",
            # email="peter@fnbrems.co.za",
        )
    )

    router.add_recipient(
        NotificationRecipient(
            name="Ken Pillay",
            role="manager",
            channels=[DeliveryChannel.EMAIL, DeliveryChannel.WHATSAPP],
            min_importance=Importance.MEDIUM,
            # email="ken@fnbrems.co.za",
        )
    )

    router.add_recipient(
        NotificationRecipient(
            name="Admin",
            role="admin",
            channels=[DeliveryChannel.TELEGRAM, DeliveryChannel.WHATSAPP],
            min_importance=Importance.HIGH,
            # telegram_chat_id="...",
        )
    )

    # ---------------------------------------------------------------
    # Main notification subscriber — routes ALL events through router
    # ---------------------------------------------------------------

    @bus.on("*")
    async def route_to_sentry(event: SentinelEvent):
        """Route every event through the notification router.

        The router decides push/digest/log based on importance.
        Skips sentry.* events to avoid infinite loops.
        """
        if event.domain == "sentry":
            return
        await router.route(event)

    # ---------------------------------------------------------------
    # Acknowledgement handler — inbound from Sentry bot
    # ---------------------------------------------------------------

    @bus.on("sentry.notification_acknowledged")
    async def handle_acknowledgement(event: SentinelEvent):
        """Mark notification as acknowledged to prevent escalation."""
        original_event_id = event.payload.get("original_event_id")
        if original_event_id:
            acked = router.acknowledge(original_event_id)
            if acked:
                logger.info(
                    "[ACK] %s acknowledged %s",
                    event.payload.get("technician", "unknown"),
                    original_event_id,
                )

    logger.info(
        "Sentry notification router registered with %d recipients",
        len(router._recipients),
    )
