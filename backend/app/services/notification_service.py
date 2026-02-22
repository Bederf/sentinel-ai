"""
NotificationService — orchestrates multi-channel notification delivery.

Phase 102: Routes notifications to technicians via their enabled channels (Telegram, WhatsApp, SMS).
Respects technician preferences: quiet hours, alert level thresholds, emergency override.
"""

import logging
from typing import Optional
from uuid import UUID
from datetime import datetime

from .notification_providers import (
    TelegramProvider,
    WhatsAppProvider,
    BulkSMSProvider,
)
from .notification_providers.base_provider import NotificationResult
from ..models.notification import (
    ChannelType,
    AlertLevel,
    NotificationStatus,
    TechnicianNotificationChannel,
    NotificationDeliveryLog,
)
from ..database.repositories.notification_repository import NotificationRepository

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
        work_order_id: Optional[UUID] = None,
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
        result = {
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

    async def _send_to_channel(
        self,
        channel: TechnicianNotificationChannel,
        technician_id: UUID,
        title: str,
        body: str,
        work_order_id: Optional[UUID],
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
        }


# Singleton instance for module-level imports
notification_service = NotificationService()
