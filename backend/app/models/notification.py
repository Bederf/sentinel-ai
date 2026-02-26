"""
Notification domain models — ORM dataclasses for Phase 102 multi-channel notifications.

Three tables:
- technician_notification_channels: Contact info (Telegram ID, WhatsApp #, SMS #)
- technician_notification_preferences: Routing rules, quiet hours, emergency override
- notification_delivery_log: Audit trail for every notification sent
"""

from dataclasses import dataclass, field
from datetime import datetime, time
from typing import Optional
from uuid import UUID
from enum import Enum


class ChannelType(str, Enum):
    """Supported notification channels."""

    TELEGRAM = "telegram"
    WHATSAPP = "whatsapp"
    SMS = "sms"


class NotificationStatus(str, Enum):
    """Delivery status for a notification."""

    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"


class AlertLevel(str, Enum):
    """Alert severity levels."""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class TechnicianNotificationChannel:
    """Contact information for a technician on a specific channel.

    One row per technician per channel (e.g., Tech A has Telegram + SMS, Tech B has WhatsApp only).
    """

    id: UUID
    technician_id: UUID
    channel_type: ChannelType

    # Contact details (one populated based on channel_type)
    telegram_id: Optional[str] = None  # Telegram user ID (e.g., "123456789")
    whatsapp_number: Optional[str] = None  # WhatsApp phone (e.g., "+27123456789")
    sms_number: Optional[str] = None  # SMS phone (e.g., "+27123456789")

    # Verification
    is_verified: bool = False  # Has technician confirmed this channel works?
    verified_at: Optional[datetime] = None
    verification_attempts: int = 0

    # Channel-specific settings (future: do_not_disturb, preferences, etc.)
    settings: dict = field(default_factory=dict)

    # Metadata
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def get_contact_identifier(self) -> str:
        """Get the contact identifier (phone/ID) for this channel."""
        if self.channel_type == ChannelType.TELEGRAM:
            return self.telegram_id or ""
        elif self.channel_type == ChannelType.WHATSAPP:
            return self.whatsapp_number or ""
        elif self.channel_type == ChannelType.SMS:
            return self.sms_number or ""
        return ""


@dataclass
class TechnicianNotificationPreferences:
    """Per-technician notification routing and rules.

    One row per technician (unique technician_id).
    Stores: which channels to use, preferred channel, alert thresholds, quiet hours, etc.
    """

    id: UUID
    technician_id: UUID

    # Channel selection
    preferred_channel: ChannelType = ChannelType.TELEGRAM  # Primary choice
    enabled_channels: list[ChannelType] = field(default_factory=lambda: [ChannelType.TELEGRAM])  # Send to all of these

    # Alert severity threshold
    alert_level_min: AlertLevel = AlertLevel.WARNING  # Only notify on warning+

    # Quiet hours (do not disturb: 22:00-06:00 default)
    quiet_hours_enabled: bool = True
    quiet_hours_start: time = field(default_factory=lambda: time(22, 0))
    quiet_hours_end: time = field(default_factory=lambda: time(6, 0))

    # Emergency override (critical alerts bypass quiet hours)
    emergency_override_enabled: bool = True

    # Low-priority batching (group non-urgent alerts)
    batch_low_priority: bool = False
    batch_interval_minutes: int = 60

    # Metadata
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def should_notify_now(self, alert_level: AlertLevel) -> bool:
        """Check if we should send a notification now (respecting quiet hours, thresholds).

        Args:
            alert_level: Severity level of the alert

        Returns:
            True if notification should be sent, False if suppressed
        """
        # Check alert level threshold
        level_order = [AlertLevel.INFO, AlertLevel.WARNING, AlertLevel.CRITICAL]
        if level_order.index(alert_level) < level_order.index(self.alert_level_min):
            return False  # Alert below minimum threshold

        # Check quiet hours (unless emergency override)
        if self.quiet_hours_enabled and not (alert_level == AlertLevel.CRITICAL and self.emergency_override_enabled):
            now = datetime.now().time()
            # Quiet hours wrap around midnight (22:00 → 06:00)
            if self.quiet_hours_start > self.quiet_hours_end:  # Wraps midnight
                if now >= self.quiet_hours_start or now < self.quiet_hours_end:
                    return False
            else:  # Doesn't wrap
                if self.quiet_hours_start <= now < self.quiet_hours_end:
                    return False

        return True


@dataclass
class NotificationDeliveryLog:
    """Audit trail — one row per notification send attempt.

    Used for: debugging, compliance, delivery statistics, retry logic.
    """

    id: UUID

    # References (optional for orphan handling)
    work_order_id: Optional[UUID] = None
    technician_id: UUID = field(default_factory=UUID)

    # Notification content
    notification_type: str = ""  # 'work_order_assigned', 'alert', 'update', 'test'
    title: str = ""
    body: str = ""

    # Delivery method
    channel_type: ChannelType = ChannelType.TELEGRAM
    recipient_identifier: str = ""  # Phone number, Telegram ID, etc.

    # Delivery status
    status: NotificationStatus = NotificationStatus.PENDING
    error_message: Optional[str] = None
    error_code: Optional[str] = None  # 'invalid_number', 'rate_limit', 'auth_failed', etc.

    # Tracking
    external_message_id: Optional[str] = None  # Provider's message ID
    sent_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None

    # Provider details
    provider: str = ""  # 'sentry', 'meta', 'bulksms'
    provider_response: dict = field(default_factory=dict)

    # Retry tracking
    retry_count: int = 0
    last_retry_at: Optional[datetime] = None
    max_retries: int = 3

    # Metadata
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
