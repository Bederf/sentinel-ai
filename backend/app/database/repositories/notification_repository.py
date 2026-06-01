"""
Notification Repository — Database operations for multi-channel notifications.

Phase 102: Manages technician notification channels, preferences, and delivery logs
in the canonical DB store.
"""

import logging
from datetime import datetime
from typing import Any
from uuid import UUID

from app.database.supabase_client import get_supabase_client
from app.models.notification import (
    ChannelType,
    NotificationDeliveryLog,
    NotificationStatus,
    TechnicianNotificationChannel,
    TechnicianNotificationPreferences,
)

logger = logging.getLogger(__name__)
SYSTEM_NOTIFIER_TECHNICIAN_ID = UUID("00000000-0000-0000-0000-000000000001")
SYSTEM_NOTIFIER_TECHNICIAN_CODE = "TECH-SYSTEM-NOTIFIER"


class NotificationRepository:
    """Repository for notification database operations.

    Handles technician notification channels, preferences, and delivery logs.
    """

    def __init__(self):
        """Initialize the repository."""
        try:
            self.client = get_supabase_client()
        except Exception as e:
            logger.error("Supabase client initialization failed for notifications: %s", e)
            self.client = None

    # ========== Alert Subscribers ==========

    async def get_alert_subscribers(
        self,
        alert_level: str = "critical",
        notification_type: str = "plant_alert",
    ) -> list[UUID]:
        """Get technician IDs subscribed to alerts at this level."""
        try:
            result = self.client.table("technician_notification_preferences").select("technician_id").execute()
            return [UUID(r["technician_id"]) for r in (result.data or [])]
        except Exception as e:
            logger.error(f"Error fetching alert subscribers: {e}")
            return []

    @staticmethod
    def _level_includes(level: str) -> list:
        """Return alert levels that would receive a notification at the given level."""
        hierarchy = ["info", "warning", "critical"]
        idx = hierarchy.index(level) if level in hierarchy else 0
        return hierarchy[: idx + 1]

    # ========== Notification Channels ==========

    async def get_notification_channels(
        self,
        technician_id: UUID,
        channel_types: list[ChannelType] | None = None,
    ) -> list[TechnicianNotificationChannel]:
        """Get notification channels for a technician.

        Args:
            technician_id: UUID of the technician
            channel_types: Optional filter by channel types

        Returns:
            List of TechnicianNotificationChannel objects
        """
        try:
            query = (
                self.client.table("technician_notification_channels")
                .select("*")
                .eq("technician_id", str(technician_id))
            )

            if channel_types:
                query = query.in_("channel_type", [ct.value for ct in channel_types])

            result = query.execute()
            return [self._channel_dict_to_model(c) for c in result.data or []]
        except Exception as e:
            logger.error(f"Error retrieving notification channels for {technician_id}: {e}")
            return []

    async def get_notification_channel(
        self, technician_id: UUID, channel_id: UUID
    ) -> TechnicianNotificationChannel | None:
        """Get a specific notification channel.

        Args:
            technician_id: UUID of the technician
            channel_id: UUID of the channel

        Returns:
            TechnicianNotificationChannel or None if not found
        """
        try:
            result = (
                self.client.table("technician_notification_channels")
                .select("*")
                .eq("id", str(channel_id))
                .eq("technician_id", str(technician_id))
                .execute()
            )
            if result.data and len(result.data) > 0:
                return self._channel_dict_to_model(result.data[0])
            return None
        except Exception as e:
            logger.error(f"Error retrieving notification channel {channel_id}: {e}")
            return None

    async def create_notification_channel(
        self, channel: TechnicianNotificationChannel
    ) -> TechnicianNotificationChannel:
        """Create a new notification channel for a technician.

        Args:
            channel: TechnicianNotificationChannel to create

        Returns:
            Created channel with ID populated
        """
        try:
            result = (
                self.client.table("technician_notification_channels")
                .insert(self._channel_model_to_dict(channel))
                .execute()
            )
            if result.data and len(result.data) > 0:
                return self._channel_dict_to_model(result.data[0])
            return channel
        except Exception as e:
            logger.error(f"Error creating notification channel: {e}")
            return channel

    async def update_notification_channel(
        self, channel: TechnicianNotificationChannel
    ) -> TechnicianNotificationChannel:
        """Update an existing notification channel.

        Args:
            channel: TechnicianNotificationChannel to update

        Returns:
            Updated channel
        """
        try:
            result = (
                self.client.table("technician_notification_channels")
                .update(self._channel_model_to_dict(channel))
                .eq("id", str(channel.id))
                .execute()
            )
            if result.data and len(result.data) > 0:
                return self._channel_dict_to_model(result.data[0])
            return channel
        except Exception as e:
            logger.error(f"Error updating notification channel {channel.id}: {e}")
            return channel

    # ========== Notification Preferences ==========

    async def get_notification_preferences(self, technician_id: UUID) -> TechnicianNotificationPreferences | None:
        """Get notification preferences for a technician.

        Args:
            technician_id: UUID of the technician

        Returns:
            TechnicianNotificationPreferences or None if not found
        """
        try:
            result = (
                self.client.table("technician_notification_preferences")
                .select("*")
                .eq("technician_id", str(technician_id))
                .execute()
            )
            if result.data and len(result.data) > 0:
                return self._preferences_dict_to_model(result.data[0])
            return None
        except Exception as e:
            logger.error(f"Error retrieving notification preferences for {technician_id}: {e}")
            return None

    async def create_notification_preferences(
        self, preferences: TechnicianNotificationPreferences
    ) -> TechnicianNotificationPreferences:
        """Create notification preferences for a technician.

        Args:
            preferences: TechnicianNotificationPreferences to create

        Returns:
            Created preferences
        """
        try:
            result = (
                self.client.table("technician_notification_preferences")
                .insert(self._preferences_model_to_dict(preferences))
                .execute()
            )
            if result.data and len(result.data) > 0:
                return self._preferences_dict_to_model(result.data[0])
            return preferences
        except Exception as e:
            logger.error(f"Error creating notification preferences: {e}")
            return preferences

    async def update_notification_preferences(
        self, preferences: TechnicianNotificationPreferences
    ) -> TechnicianNotificationPreferences:
        """Update notification preferences for a technician.

        Args:
            preferences: TechnicianNotificationPreferences to update

        Returns:
            Updated preferences
        """
        try:
            result = (
                self.client.table("technician_notification_preferences")
                .update(self._preferences_model_to_dict(preferences))
                .eq("technician_id", str(preferences.technician_id))
                .execute()
            )
            if result.data and len(result.data) > 0:
                return self._preferences_dict_to_model(result.data[0])
            return preferences
        except Exception as e:
            logger.error(f"Error updating notification preferences: {e}")
            return preferences

    # ========== Notification Delivery Logs ==========

    def _resolve_delivery_log_technician_id(self, technician_id: UUID) -> UUID:
        """Resolve delivery-log technician ID with FK-safe system notifier fallback."""
        if technician_id not in (UUID(int=0), SYSTEM_NOTIFIER_TECHNICIAN_ID):
            return technician_id

        try:
            existing = (
                self.client.table("technicians")
                .select("id")
                .eq("code", SYSTEM_NOTIFIER_TECHNICIAN_CODE)
                .limit(1)
                .execute()
            )
            if existing.data:
                return UUID(existing.data[0]["id"])

            self.client.table("technicians").insert(
                {
                    "id": str(SYSTEM_NOTIFIER_TECHNICIAN_ID),
                    "code": SYSTEM_NOTIFIER_TECHNICIAN_CODE,
                    "name": "System Notifier",
                    "email": "system-notifier@sentinel.local",
                    "phone": None,
                    "active": True,
                }
            ).execute()
            return SYSTEM_NOTIFIER_TECHNICIAN_ID
        except Exception as e:
            logger.warning("Failed to ensure system notifier technician row: %s", e)
            return technician_id

    async def create_delivery_log(self, log: NotificationDeliveryLog) -> NotificationDeliveryLog:
        """Create a notification delivery log entry.

        Args:
            log: NotificationDeliveryLog to create

        Returns:
            Created log entry
        """
        try:
            payload = self._delivery_log_model_to_dict(log)
            payload["technician_id"] = str(self._resolve_delivery_log_technician_id(log.technician_id))

            result = self.client.table("notification_delivery_log").insert(payload).execute()
            if result.data and len(result.data) > 0:
                return self._delivery_log_dict_to_model(result.data[0])
            return log
        except Exception as e:
            logger.error(f"Error creating delivery log: {e}")
            return log

    async def get_delivery_logs(
        self,
        technician_id: UUID | None = None,
        status: NotificationStatus | None = None,
        limit: int = 100,
    ) -> list[NotificationDeliveryLog]:
        """Get notification delivery logs.

        Args:
            technician_id: Optional filter by technician
            status: Optional filter by delivery status
            limit: Maximum number of logs to return

        Returns:
            List of NotificationDeliveryLog objects
        """
        try:
            query = (
                self.client.table("notification_delivery_log").select("*").order("created_at", desc=True).limit(limit)
            )

            if technician_id:
                query = query.eq("technician_id", str(technician_id))

            if status:
                query = query.eq("status", status.value)

            result = query.execute()
            return [self._delivery_log_dict_to_model(log) for log in result.data or []]
        except Exception as e:
            logger.error(f"Error retrieving delivery logs: {e}")
            return []

    async def update_delivery_log_acknowledged(
        self,
        notification_id: str,
        acknowledged_by: str,
        acknowledged_at: datetime,
    ) -> None:
        """Mark a certified notification as acknowledged."""
        try:
            self.client.table("notification_delivery_log").update(
                {
                    "acknowledged_at": acknowledged_at.isoformat(),
                    "acknowledged_by": acknowledged_by,
                }
            ).eq("notification_id", notification_id).execute()
        except Exception as e:
            logger.error(f"Error updating acknowledgement for {notification_id}: {e}")
            raise

    async def update_delivery_log_escalated(
        self,
        notification_id: str,
        escalated_at: datetime,
    ) -> None:
        """Mark a certified notification as escalated."""
        try:
            self.client.table("notification_delivery_log").update(
                {
                    "escalated": True,
                    "escalated_at": escalated_at.isoformat(),
                }
            ).eq("notification_id", notification_id).execute()
        except Exception as e:
            logger.error(f"Error updating escalated for {notification_id}: {e}")
            raise

    # ========== Conversion Helpers ==========

    @staticmethod
    def _channel_dict_to_model(data: dict[str, Any]) -> TechnicianNotificationChannel:
        """Convert dictionary to TechnicianNotificationChannel model."""
        return TechnicianNotificationChannel(
            id=UUID(data.get("id")) if data.get("id") else UUID(int=0),
            technician_id=UUID(data.get("technician_id")) if data.get("technician_id") else UUID(int=0),
            channel_type=ChannelType(data.get("channel_type", "telegram")),
            telegram_id=data.get("telegram_id"),
            whatsapp_number=data.get("whatsapp_number"),
            sms_number=data.get("sms_number"),
            is_verified=data.get("is_verified", False),
            verified_at=datetime.fromisoformat(data["verified_at"]) if data.get("verified_at") else None,
            verification_attempts=data.get("verification_attempts", 0),
            settings=data.get("settings", {}),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.utcnow(),
            updated_at=datetime.fromisoformat(data["updated_at"]) if data.get("updated_at") else datetime.utcnow(),
        )

    @staticmethod
    def _channel_model_to_dict(model: TechnicianNotificationChannel) -> dict[str, Any]:
        """Convert TechnicianNotificationChannel model to dictionary."""
        return {
            "id": str(model.id),
            "technician_id": str(model.technician_id),
            "channel_type": model.channel_type.value,
            "telegram_id": model.telegram_id,
            "whatsapp_number": model.whatsapp_number,
            "sms_number": model.sms_number,
            "is_verified": model.is_verified,
            "verified_at": model.verified_at.isoformat() if model.verified_at else None,
            "verification_attempts": model.verification_attempts,
            "settings": model.settings,
            "created_at": model.created_at.isoformat(),
            "updated_at": model.updated_at.isoformat(),
        }

    @staticmethod
    def _preferences_dict_to_model(data: dict[str, Any]) -> TechnicianNotificationPreferences:
        """Convert dictionary to TechnicianNotificationPreferences model."""
        from datetime import time

        return TechnicianNotificationPreferences(
            id=UUID(data.get("id")) if data.get("id") else UUID(int=0),
            technician_id=UUID(data.get("technician_id")) if data.get("technician_id") else UUID(int=0),
            preferred_channel=ChannelType(data.get("preferred_channel", "telegram")),
            enabled_channels=[ChannelType(ch) for ch in data.get("enabled_channels", ["telegram"])],
            alert_level_min=data.get("alert_level_min", "warning"),
            quiet_hours_enabled=data.get("quiet_hours_enabled", True),
            quiet_hours_start=time.fromisoformat(data["quiet_hours_start"])
            if data.get("quiet_hours_start")
            else time(22, 0),
            quiet_hours_end=time.fromisoformat(data["quiet_hours_end"]) if data.get("quiet_hours_end") else time(6, 0),
            emergency_override_enabled=data.get("emergency_override_enabled", True),
            batch_low_priority=data.get("batch_low_priority", False),
            batch_interval_minutes=data.get("batch_interval_minutes", 60),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.utcnow(),
            updated_at=datetime.fromisoformat(data["updated_at"]) if data.get("updated_at") else datetime.utcnow(),
        )

    @staticmethod
    def _preferences_model_to_dict(model: TechnicianNotificationPreferences) -> dict[str, Any]:
        """Convert TechnicianNotificationPreferences model to dictionary."""
        return {
            "id": str(model.id),
            "technician_id": str(model.technician_id),
            "preferred_channel": model.preferred_channel.value,
            "enabled_channels": [ch.value for ch in model.enabled_channels],
            "alert_level_min": model.alert_level_min,
            "quiet_hours_enabled": model.quiet_hours_enabled,
            "quiet_hours_start": model.quiet_hours_start.isoformat(),
            "quiet_hours_end": model.quiet_hours_end.isoformat(),
            "emergency_override_enabled": model.emergency_override_enabled,
            "batch_low_priority": model.batch_low_priority,
            "batch_interval_minutes": model.batch_interval_minutes,
            "created_at": model.created_at.isoformat(),
            "updated_at": model.updated_at.isoformat(),
        }

    @staticmethod
    def _delivery_log_dict_to_model(data: dict[str, Any]) -> NotificationDeliveryLog:
        """Convert dictionary to NotificationDeliveryLog model."""
        return NotificationDeliveryLog(
            id=UUID(data.get("id")) if data.get("id") else UUID(int=0),
            work_order_id=UUID(data.get("work_order_id")) if data.get("work_order_id") else None,
            technician_id=UUID(data.get("technician_id")) if data.get("technician_id") else UUID(int=0),
            notification_type=data.get("notification_type", ""),
            title=data.get("title", ""),
            body=data.get("body", ""),
            channel_type=ChannelType(data.get("channel_type", "telegram")),
            recipient_identifier=data.get("recipient_identifier", ""),
            status=NotificationStatus(data.get("status", "pending")),
            error_message=data.get("error_message"),
            error_code=data.get("error_code"),
            external_message_id=data.get("external_message_id"),
            sent_at=datetime.fromisoformat(data["sent_at"]) if data.get("sent_at") else None,
            delivered_at=datetime.fromisoformat(data["delivered_at"]) if data.get("delivered_at") else None,
            provider=data.get("provider", ""),
            provider_response=data.get("provider_response", {}),
            retry_count=data.get("retry_count", 0),
            last_retry_at=datetime.fromisoformat(data["last_retry_at"]) if data.get("last_retry_at") else None,
            max_retries=data.get("max_retries", 3),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.utcnow(),
            updated_at=datetime.fromisoformat(data["updated_at"]) if data.get("updated_at") else datetime.utcnow(),
            acknowledged_at=datetime.fromisoformat(data["acknowledged_at"]) if data.get("acknowledged_at") else None,
            acknowledged_by=data.get("acknowledged_by"),
            escalated=data.get("escalated", False),
            escalated_at=datetime.fromisoformat(data["escalated_at"]) if data.get("escalated_at") else None,
            timeout_minutes=data.get("timeout_minutes", 15),
            notification_id=data.get("notification_id"),
        )

    @staticmethod
    def _delivery_log_model_to_dict(model: NotificationDeliveryLog) -> dict[str, Any]:
        """Convert NotificationDeliveryLog model to dictionary."""
        # Columns that actually exist in notification_delivery_log
        valid_cols = {
            "notification_type",
            "channel_type",
            "status",
            "recipient_identifier",
            "error_message",
            "provider",
            "external_message_id",
        }
        payload: dict[str, Any] = {
            "notification_type": model.notification_type,
            "channel_type": model.channel_type.value,
            "recipient_identifier": model.recipient_identifier,
            "status": model.status.value,
            "provider": model.provider,
            "external_message_id": model.external_message_id,
        }
        # Only add optional fields if they have values
        if model.error_message:
            payload["error_message"] = model.error_message
        if model.id:
            payload["id"] = str(model.id)
        if model.technician_id:
            payload["technician_id"] = str(model.technician_id)
        return payload
