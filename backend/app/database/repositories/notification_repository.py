"""
Notification Repository — Database operations for multi-channel notifications.

Phase 102: Manages technician notification channels, preferences, and delivery logs.

Implements fallback pattern:
- Primary: Supabase (if available)
- Fallback: JSON file (if USE_JSON_STORAGE=true or Supabase unavailable)
"""

import json
import logging
import os
from pathlib import Path
from typing import Optional, List, Dict, Any
from uuid import UUID
from datetime import datetime

from app.database.supabase_client import get_supabase_client
from app.models.notification import (
    ChannelType,
    TechnicianNotificationChannel,
    TechnicianNotificationPreferences,
    NotificationDeliveryLog,
    NotificationStatus,
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
        self.use_json = os.getenv("USE_JSON_STORAGE", "false").lower() == "true"
        self.json_dir = Path(__file__).parent.parent / "data"
        self.channels_file = self.json_dir / "notification_channels.json"
        self.preferences_file = self.json_dir / "notification_preferences.json"
        self.delivery_log_file = self.json_dir / "notification_delivery_log.json"
        self.client = None

        # Force JSON in DEMO_MODE
        if os.getenv("DEMO_MODE", "false").lower() == "true":
            self.use_json = True

        if not self.use_json:
            try:
                self.client = get_supabase_client()
            except Exception as e:
                logger.warning(f"Supabase client initialization failed, falling back to JSON: {e}")
                self.use_json = True

        # Ensure JSON files exist
        if self.use_json:
            self._ensure_json_files_exist()

    def _ensure_json_files_exist(self) -> None:
        """Ensure all JSON storage files exist."""
        self.json_dir.mkdir(parents=True, exist_ok=True)

        for json_file in [self.channels_file, self.preferences_file, self.delivery_log_file]:
            if not json_file.exists():
                with open(json_file, "w") as f:
                    json.dump({}, f, indent=2)
                logger.info(f"Created JSON notification file: {json_file}")

    def _load_json_data(self, json_file: Path) -> Dict[str, Any]:
        """Load data from JSON file."""
        try:
            with open(json_file, "r") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading JSON from {json_file}: {e}")
            return {}

    def _save_json_data(self, json_file: Path, data: Dict[str, Any]) -> None:
        """Save data to JSON file."""
        try:
            with open(json_file, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving JSON to {json_file}: {e}")

    # ========== Notification Channels ==========

    async def get_notification_channels(
        self,
        technician_id: UUID,
        channel_types: Optional[List[ChannelType]] = None,
    ) -> List[TechnicianNotificationChannel]:
        """Get notification channels for a technician.

        Args:
            technician_id: UUID of the technician
            channel_types: Optional filter by channel types

        Returns:
            List of TechnicianNotificationChannel objects
        """
        if self.use_json:
            data = self._load_json_data(self.channels_file)
            tech_id_str = str(technician_id)
            channels = data.get(tech_id_str, [])
            if channel_types:
                channels = [c for c in channels if c.get("channel_type") in [ct.value for ct in channel_types]]
            return [self._channel_dict_to_model(c) for c in channels]

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
    ) -> Optional[TechnicianNotificationChannel]:
        """Get a specific notification channel.

        Args:
            technician_id: UUID of the technician
            channel_id: UUID of the channel

        Returns:
            TechnicianNotificationChannel or None if not found
        """
        if self.use_json:
            data = self._load_json_data(self.channels_file)
            tech_id_str = str(technician_id)
            for channel in data.get(tech_id_str, []):
                if channel.get("id") == str(channel_id):
                    return self._channel_dict_to_model(channel)
            return None

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
        if self.use_json:
            data = self._load_json_data(self.channels_file)
            tech_id_str = str(channel.technician_id)
            if tech_id_str not in data:
                data[tech_id_str] = []
            data[tech_id_str].append(self._channel_model_to_dict(channel))
            self._save_json_data(self.channels_file, data)
            return channel

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
        if self.use_json:
            data = self._load_json_data(self.channels_file)
            tech_id_str = str(channel.technician_id)
            for i, c in enumerate(data.get(tech_id_str, [])):
                if c.get("id") == str(channel.id):
                    data[tech_id_str][i] = self._channel_model_to_dict(channel)
                    self._save_json_data(self.channels_file, data)
                    return channel
            return channel

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

    async def get_notification_preferences(self, technician_id: UUID) -> Optional[TechnicianNotificationPreferences]:
        """Get notification preferences for a technician.

        Args:
            technician_id: UUID of the technician

        Returns:
            TechnicianNotificationPreferences or None if not found
        """
        if self.use_json:
            data = self._load_json_data(self.preferences_file)
            pref_data = data.get(str(technician_id))
            if pref_data:
                return self._preferences_dict_to_model(pref_data)
            return None

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
        if self.use_json:
            data = self._load_json_data(self.preferences_file)
            data[str(preferences.technician_id)] = self._preferences_model_to_dict(preferences)
            self._save_json_data(self.preferences_file, data)
            return preferences

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
        if self.use_json:
            data = self._load_json_data(self.preferences_file)
            data[str(preferences.technician_id)] = self._preferences_model_to_dict(preferences)
            self._save_json_data(self.preferences_file, data)
            return preferences

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
        if self.use_json:
            return technician_id

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
        if self.use_json:
            data = self._load_json_data(self.delivery_log_file)
            log_id = str(log.technician_id)
            if log_id not in data:
                data[log_id] = []
            data[log_id].append(self._delivery_log_model_to_dict(log))
            self._save_json_data(self.delivery_log_file, data)
            return log

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
        technician_id: Optional[UUID] = None,
        status: Optional[NotificationStatus] = None,
        limit: int = 100,
    ) -> List[NotificationDeliveryLog]:
        """Get notification delivery logs.

        Args:
            technician_id: Optional filter by technician
            status: Optional filter by delivery status
            limit: Maximum number of logs to return

        Returns:
            List of NotificationDeliveryLog objects
        """
        if self.use_json:
            data = self._load_json_data(self.delivery_log_file)
            all_logs = []
            for logs in data.values():
                all_logs.extend(logs)

            if technician_id:
                all_logs = [log for log in all_logs if log.get("technician_id") == str(technician_id)]

            if status:
                all_logs = [log for log in all_logs if log.get("status") == status.value]

            return [self._delivery_log_dict_to_model(log) for log in all_logs[-limit:]]

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

    # ========== Conversion Helpers ==========

    @staticmethod
    def _channel_dict_to_model(data: Dict[str, Any]) -> TechnicianNotificationChannel:
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
    def _channel_model_to_dict(model: TechnicianNotificationChannel) -> Dict[str, Any]:
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
    def _preferences_dict_to_model(data: Dict[str, Any]) -> TechnicianNotificationPreferences:
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
    def _preferences_model_to_dict(model: TechnicianNotificationPreferences) -> Dict[str, Any]:
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
    def _delivery_log_dict_to_model(data: Dict[str, Any]) -> NotificationDeliveryLog:
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
        )

    @staticmethod
    def _delivery_log_model_to_dict(model: NotificationDeliveryLog) -> Dict[str, Any]:
        """Convert NotificationDeliveryLog model to dictionary."""
        return {
            "id": str(model.id),
            "work_order_id": str(model.work_order_id) if model.work_order_id else None,
            "technician_id": str(model.technician_id),
            "notification_type": model.notification_type,
            "title": model.title,
            "body": model.body,
            "channel_type": model.channel_type.value,
            "recipient_identifier": model.recipient_identifier,
            "status": model.status.value,
            "error_message": model.error_message,
            "error_code": model.error_code,
            "external_message_id": model.external_message_id,
            "sent_at": model.sent_at.isoformat() if model.sent_at else None,
            "delivered_at": model.delivered_at.isoformat() if model.delivered_at else None,
            "provider": model.provider,
            "provider_response": model.provider_response,
            "retry_count": model.retry_count,
            "last_retry_at": model.last_retry_at.isoformat() if model.last_retry_at else None,
            "max_retries": model.max_retries,
            "created_at": model.created_at.isoformat(),
            "updated_at": model.updated_at.isoformat(),
        }
