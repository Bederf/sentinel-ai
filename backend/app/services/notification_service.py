"""
NotificationService — orchestrates multi-channel notification delivery.

Phase 102: Routes notifications to technicians via their enabled channels (Telegram, WhatsApp, SMS).
Respects technician preferences: quiet hours, alert level thresholds, emergency override.
"""

import asyncio
import logging
from datetime import datetime
from uuid import UUID

from ..database.repositories.notification_repository import NotificationRepository
from ..models.notification import (
    AlertLevel,
    ChannelType,
    NotificationDeliveryLog,
    NotificationStatus,
    TechnicianNotificationChannel,
)
from .notification_providers import (
    BulkSMSProvider,
    TelegramProvider,
    WhatsAppProvider,
)
from .notification_providers.base_provider import NotificationResult

logger = logging.getLogger(__name__)


class NotificationService:
    """Orchestrates multi-channel technician notification delivery."""

    def __init__(self):
        """Initialize the notification service."""
        # Initialize repository for database access
        self.notification_repo = NotificationRepository()

        # Initialize providers
        self.providers = {
            ChannelType.TELEGRAM: TelegramProvider(),
            ChannelType.WHATSAPP: WhatsAppProvider(),
            ChannelType.SMS: BulkSMSProvider(),
        }

    async def initialize(self):
        """Initialize notification service (no-op, providers ready from __init__)."""
        pass

    async def notify_technician(
        self,
        technician_id: UUID,
        title: str,
        body: str,
        alert_level: AlertLevel = AlertLevel.WARNING,
        work_order_id: UUID | None = None,
        notification_type: str = "work_order_assigned",
    ) -> dict:
        """Send notification to technician via enabled channels.

        Respects technician preferences: quiet hours, alert thresholds, emergency override.
        Sends simultaneously to ALL enabled channels (not cascade/fallback).

        Args:
            technician_id: UUID of technician to notify
            title: Notification title
            body: Notification body/message
            alert_level: Severity level (info, warning, critical)
            work_order_id: Associated work order ID (optional)
            notification_type: Type of notification (work_order_assigned, alert, update, test)

        Returns:
            {
                "success": bool,
                "channels_sent": [ChannelType],
                "channels_failed": [ChannelType],
                "deliveries": [NotificationDeliveryLog],
                "errors": {ChannelType: error_message},
            }
        """
        result: dict = {
            "success": True,
            "channels_sent": [],
            "channels_failed": [],
            "deliveries": [],
            "errors": {},
        }

        try:
            # Fetch technician preferences
            preferences = await self.notification_repo.get_notification_preferences(technician_id)
            if not preferences:
                logger.warning(f"No notification preferences found for technician {technician_id}")
                result["success"] = False
                result["errors"]["system"] = "No preferences configured"
                return result

            # Check if notification should be sent (respects quiet hours, alert levels)
            if not preferences.should_notify_now(alert_level):
                logger.info(
                    f"Notification suppressed for technician {technician_id} "
                    f"(quiet hours active, alert_level={alert_level})"
                )
                result["success"] = False
                result["errors"]["system"] = "Notification suppressed by quiet hours"
                return result

            # Fetch enabled channels
            enabled_channels = await self.notification_repo.get_notification_channels(
                technician_id,
                channel_types=preferences.enabled_channels,
            )
            if not enabled_channels:
                logger.warning(f"No notification channels configured for technician {technician_id}")
                result["success"] = False
                result["errors"]["system"] = "No channels configured"
                return result

            # Send to all enabled channels simultaneously (not cascade)
            delivery_tasks = []
            for channel in enabled_channels:
                task = self._send_to_channel(
                    channel=channel,
                    technician_id=technician_id,
                    title=title,
                    body=body,
                    work_order_id=work_order_id,
                    notification_type=notification_type,
                )
                delivery_tasks.append(task)

            # Execute all sends concurrently
            deliveries = []
            for channel_delivery in delivery_tasks:
                channel_type, delivery_log, error = await channel_delivery
                deliveries.append((channel_type, delivery_log, error))

            # Collect results
            for channel_type, delivery_log, error in deliveries:
                if error:
                    result["channels_failed"].append(channel_type)
                    result["errors"][channel_type] = error
                else:
                    result["channels_sent"].append(channel_type)
                    result["deliveries"].append(delivery_log)

            # Overall success: at least one channel succeeded
            result["success"] = bool(result["channels_sent"])
            return result

        except Exception as e:
            logger.error(f"NotificationService error for technician {technician_id}: {e}")
            result["success"] = False
            result["errors"]["system"] = str(e)
            return result

    async def broadcast_alert(
        self,
        title: str,
        body: str,
        alert_level: AlertLevel = AlertLevel.CRITICAL,
        notification_type: str = "plant_alert",
    ) -> dict:
        """Broadcast alert to all technicians with plant alert preferences.

        For deployments without technician DB configured, falls back to
        sending directly via each enabled provider to the default chat/number.

        Returns:
            {"success": bool, "recipients_notified": int, "errors": [...]}
        """
        result: dict = {"success": False, "recipients_notified": 0, "errors": []}

        # Try per-technician routing first
        try:
            tech_ids = await self.notification_repo.get_alert_subscribers(
                alert_level=alert_level,
                notification_type=notification_type,
            )
            if tech_ids:
                for tech_id in tech_ids:
                    tech_result = await self.notify_technician(
                        technician_id=tech_id,
                        title=title,
                        body=body,
                        alert_level=alert_level,
                        notification_type=notification_type,
                    )
                    if tech_result["success"]:
                        result["recipients_notified"] += 1
                    else:
                        result["errors"].extend(tech_result.get("errors", {}).values())
                # If no per-technician channel succeeded, fall through to
                # default provider routing (telegram_alert_chat_id /
                # twilio_whatsapp_to) instead of returning hard-fail.
                if result["recipients_notified"] > 0:
                    result["success"] = True
                    return result
        except Exception as e:
            logger.warning(f"Technician lookup failed, falling back to direct send: {e}")

        # Fallback: send directly via each enabled provider to default recipient
        for channel_type, provider in self.providers.items():
            if not provider.is_enabled():
                continue
            try:
                default_recipient = self._get_default_recipient(channel_type)
                if not default_recipient:
                    continue
                send_result = await provider.send(default_recipient, title, body)
                if send_result.success:
                    result["recipients_notified"] += 1
            except Exception as e:
                result["errors"].append(f"{channel_type}: {e}")

        result["success"] = result["recipients_notified"] > 0
        return result

    async def send_alert_direct(
        self,
        title: str,
        body: str,
        alert_level: AlertLevel = AlertLevel.WARNING,
    ) -> dict:
        """Send an alert directly via TelegramProvider (bypasses technician lookup).

        For infrastructure alerts (sensor offline, data freshness) where no
        technician_id is available. Sends to the default FM chat ID.

        Returns:
            {"success": bool, "error": str|None}
        """
        from app.config.settings import settings

        telegram_to = (
            str(getattr(settings, "sentry_fm_chat_id", "") or "").strip()
            or str(getattr(settings, "telegram_alert_chat_id", "") or "").strip()
        )
        if not telegram_to:
            return {"success": False, "error": "no_telegram_chat_id_configured"}

        provider = self.providers.get(ChannelType.TELEGRAM)
        if not provider or not provider.is_enabled():
            return {"success": False, "error": "telegram_not_enabled"}

        try:
            send_result = await provider.send(telegram_to, title, body)
            return {"success": bool(send_result.success), "error": getattr(send_result, "error_message", None)}
        except Exception as e:
            logger.warning(f"[NOTIFY] send_alert_direct failed: {e}")
            return {"success": False, "error": str(e)}

    def _get_default_recipient(self, channel_type: ChannelType) -> str:
        """Get default recipient for a channel when no technician DB available."""
        from app.config.settings import settings

        if channel_type == ChannelType.TELEGRAM:
            return settings.telegram_alert_chat_id
        elif channel_type == ChannelType.WHATSAPP:
            return settings.twilio_whatsapp_to.replace("whatsapp:", "") if settings.twilio_whatsapp_to else ""
        return ""

    async def _send_to_channel(
        self,
        channel: TechnicianNotificationChannel,
        technician_id: UUID,
        title: str,
        body: str,
        work_order_id: UUID | None,
        notification_type: str,
    ) -> tuple:
        """Send notification to single channel and log delivery.

        Returns:
            (channel_type, delivery_log, error_message)
        """
        channel_type = channel.channel_type
        recipient_identifier = channel.get_contact_identifier()

        # Get provider for this channel
        provider = self.providers.get(channel_type)
        if not provider:
            error_msg = f"Provider not found for channel {channel_type}"
            logger.error(error_msg)
            return (channel_type, None, error_msg)

        # Check if provider is enabled
        if not provider.is_enabled():
            error_msg = f"Provider {provider.provider_name} not configured"
            logger.warning(error_msg)
            return (channel_type, None, error_msg)

        # Create delivery log entry (initial state: PENDING)
        delivery_log = NotificationDeliveryLog(
            id=UUID(int=0),  # Will be set by repository
            work_order_id=work_order_id,
            technician_id=technician_id,
            notification_type=notification_type,
            title=title,
            body=body,
            channel_type=channel_type,
            recipient_identifier=recipient_identifier,
            status=NotificationStatus.PENDING,
            provider=provider.provider_name,
        )

        try:
            # Send via provider
            notification_result: NotificationResult = await provider.send(
                recipient=recipient_identifier,
                title=title,
                body=body,
            )

            # Update delivery log with result
            if notification_result.success:
                delivery_log.status = NotificationStatus.SENT
                delivery_log.external_message_id = notification_result.message_id
                delivery_log.sent_at = datetime.utcnow()
                delivery_log.provider_response = notification_result.provider_response or {}
                logger.info(
                    f"Notification sent to {channel_type} for technician {technician_id} "
                    f"(provider: {provider.provider_name})"
                )
                error = None
            else:
                delivery_log.status = NotificationStatus.FAILED
                delivery_log.error_code = notification_result.error_code
                delivery_log.error_message = notification_result.error_message
                delivery_log.provider_response = notification_result.provider_response or {}
                error = notification_result.error_message
                logger.warning(f"Notification send failed for {channel_type} to technician {technician_id}: {error}")

            # Persist delivery log
            created_log = await self.notification_repo.create_delivery_log(delivery_log)
            return (channel_type, created_log, error)

        except Exception as e:
            delivery_log.status = NotificationStatus.FAILED
            delivery_log.error_code = "exception"
            delivery_log.error_message = str(e)
            logger.error(f"Error sending notification to {channel_type} for technician {technician_id}: {e}")
            created_log = await self.notification_repo.create_delivery_log(delivery_log)
            return (channel_type, created_log, str(e))

    async def test_provider_connection(self, channel_type: ChannelType) -> bool:
        """Test if a provider is configured and reachable.

        Args:
            channel_type: Channel to test (TELEGRAM, WHATSAPP, SMS)

        Returns:
            True if provider is ready, False otherwise
        """
        provider = self.providers.get(channel_type)
        if not provider:
            logger.error(f"No provider found for channel {channel_type}")
            return False

        try:
            return await provider.test_connection()
        except Exception as e:
            logger.error(f"Provider test failed for {channel_type}: {e}")
            return False

    def get_provider_status(self) -> dict:
        """Get configuration and readiness status of all providers.

        Returns:
            {
                "telegram": {"enabled": bool, "name": str},
                "whatsapp": {"enabled": bool, "name": str},
                "sms": {"enabled": bool, "name": str},
            }
        """
        return {
            channel.value: {
                "enabled": self.providers[channel].is_enabled(),
                "name": self.providers[channel].provider_name,
            }
            for channel in ChannelType
            if channel in self.providers
        }

    async def send_certified(
        self,
        *,
        site_id: str,
        recipient_telegram_id: str,
        title: str,
        message: str,
        alert_level: AlertLevel = AlertLevel.WARNING,
        reference_id: str | None = None,
        acknowledgement_timeout_minutes: int = 15,
    ) -> dict:
        """Send a certified notification requiring Telegram acknowledgement.

        Flow:
        1. Send message with inline [✅ Acknowledged] keyboard via TelegramProvider
        2. Log delivery to notification_delivery_log
        3. Schedule escalation if no acknowledgement within timeout
        4. Return notification_id for tracking

        Args:
            site_id: Site context
            recipient_telegram_id: Telegram chat ID
            title: Notification title
            message: Notification body
            alert_level: Severity
            reference_id: Optional reference (work_order_id, alert_id, etc.)
            acknowledgement_timeout_minutes: Minutes before escalation

        Returns:
            {"success": bool, "notification_id": str, "error": str|None}
        """
        from uuid import uuid4

        notification_id = str(uuid4())
        provider = self.providers[ChannelType.TELEGRAM]

        if not provider.is_enabled():
            return {"success": False, "notification_id": notification_id, "error": "telegram_not_enabled"}

        # Build inline keyboard with acknowledgement button
        from app.services.telegram_message_sender import InlineButton, InlineKeyboard, get_telegram_sender

        keyboard = InlineKeyboard(
            rows=[[InlineButton(label="✅ Acknowledged", callback_data=f"ack:{notification_id}:{reference_id or ''}")]]
        )

        # Send via Telegram sender (supports inline keyboard)
        sender = get_telegram_sender()
        try:
            result = await sender.send_text(
                chat_id=recipient_telegram_id,
                text=f"*{title}*\n\n{message}",
                keyboard=keyboard,
            )
            msg_id = result.get("result", {}).get("message_id") if result.get("ok") else None
        except Exception as e:
            logger.warning(f"[CERTIFIED] Telegram send failed for {recipient_telegram_id}: {e}")
            msg_id = None
            telegram_error = str(e)
        else:
            telegram_error = None

        # Log delivery
        try:
            delivery_log = NotificationDeliveryLog(
                id=uuid4(),
                technician_id=UUID("00000000-0000-0000-0000-000000000000"),  # system notifier
                notification_type="certified",
                channel_type=ChannelType.TELEGRAM,
                recipient_identifier=recipient_telegram_id,
                status=NotificationStatus.SENT if msg_id else NotificationStatus.FAILED,
                provider="telegram",
                external_message_id=msg_id,
                sent_at=datetime.utcnow(),
                error_message=telegram_error,
            )
            await self.notification_repo.create_delivery_log(delivery_log)
        except Exception as log_err:
            logger.warning(f"[CERTIFIED] Failed to log delivery: {log_err}")

        # Schedule escalation check (fire-and-forget, no reference needed)
        if msg_id:
            asyncio.create_task(  # noqa: RUF006
                self._check_acknowledgement(
                    notification_id=notification_id,
                    recipient_telegram_id=recipient_telegram_id,
                    title=title,
                    message=message,
                    timeout_minutes=acknowledgement_timeout_minutes,
                    reference_id=reference_id,
                )
            )

        return {
            "success": bool(msg_id),
            "notification_id": notification_id,
            "error": None if msg_id else "send_failed",
        }

    async def handle_acknowledgement(
        self,
        callback_data: str,
        acknowledged_by_telegram_id: str,
    ) -> dict:
        """Handle [✅ Acknowledged] button press from Telegram.

        Called by the Telegram gateway when FM taps the inline button.
        Updates delivery log and cancels pending escalation.
        """
        parts = callback_data.split(":")
        if len(parts) < 2 or parts[0] != "ack":
            return {"success": False, "error": "invalid_callback_data"}

        notification_id = parts[1]
        reference_id = parts[2] if len(parts) > 2 else None

        try:
            await self.notification_repo.update_delivery_log_acknowledged(
                notification_id=notification_id,
                acknowledged_by=acknowledged_by_telegram_id,
                acknowledged_at=datetime.utcnow(),
            )
            logger.info(f"[CERTIFIED] Notification {notification_id} acknowledged by {acknowledged_by_telegram_id}")
            return {"success": True, "notification_id": notification_id, "reference_id": reference_id}
        except Exception as e:
            logger.warning(f"[CERTIFIED] Failed to record acknowledgement for {notification_id}: {e}")
            return {"success": False, "error": str(e)}

    async def _check_acknowledgement(
        self,
        notification_id: str,
        recipient_telegram_id: str,
        title: str,
        message: str,
        timeout_minutes: int,
        reference_id: str | None,
    ) -> None:
        """Wait for acknowledgement timeout, then escalate if not acknowledged."""

        await asyncio.sleep(timeout_minutes * 60)

        try:
            # Check if already acknowledged via notification_id lookup
            result = (
                self.notification_repo.client.table("notification_delivery_log")
                .select("id, acknowledged_at, escalated")
                .eq("notification_id", notification_id)
                .limit(1)
                .execute()
            )

            if not result.data:
                logger.warning(f"[CERTIFIED] Delivery log not found for {notification_id}")
                return

            row = result.data[0]
            if row.get("acknowledged_at") or row.get("escalated"):
                # Already acknowledged or escalated — nothing to do
                return

            logger.warning(
                f"[CERTIFIED] Notification {notification_id} unacknowledged after {timeout_minutes}min — escalating"
            )
            await self._escalate(
                notification_id=notification_id,
                recipient_telegram_id=recipient_telegram_id,
                title=title,
                message=message,
                reference_id=reference_id,
            )
        except Exception as e:
            logger.warning(f"[CERTIFIED] Escalation check failed for {notification_id}: {e}")

    async def _escalate(
        self,
        notification_id: str,
        recipient_telegram_id: str,
        title: str,
        message: str,
        reference_id: str | None,
    ) -> None:
        """Send escalation message to FM and secondary contacts."""
        from app.config.settings import settings
        from app.services.telegram_message_sender import get_telegram_sender

        sender = get_telegram_sender()

        escalation_msg = (
            f"⚠️ *ESCALATION*\n"
            f"No acknowledgement received for:\n"
            f"*{title}*\n"
            f"{message[:200]}\n"
            f"Reference: {reference_id or 'N/A'}"
        )

        # Send to original recipient
        await sender.send_text(chat_id=recipient_telegram_id, text=escalation_msg)

        # Also notify secondary FM chat from settings
        secondary = getattr(settings, "sentry_fm_chat_id", None)
        if secondary and secondary != recipient_telegram_id:
            await sender.send_text(chat_id=secondary, text=f"[ESCALATION COPY]\n{escalation_msg}")

        # Update escalated flag
        try:
            await self.notification_repo.update_delivery_log_escalated(
                notification_id=notification_id,
                escalated_at=datetime.utcnow(),
            )
        except Exception as e:
            logger.warning(f"[CERTIFIED] Failed to mark escalated: {e}")


# Singleton instance for module-level imports
notification_service = NotificationService()
