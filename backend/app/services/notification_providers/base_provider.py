"""
Base class for all notification providers.

Defines the interface that all channel implementations (Telegram, WhatsApp, SMS) must follow.
"""

from abc import ABC, abstractmethod
from typing import Optional
from dataclasses import dataclass


@dataclass
class NotificationResult:
    """Result of a notification send attempt."""
    success: bool
    message_id: Optional[str] = None          # Provider's message ID for tracking
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    provider_response: dict = None             # Full response from provider


class BaseNotificationProvider(ABC):
    """Abstract base class for notification providers."""

    @property
    @abstractmethod
    def channel_name(self) -> str:
        """Name of this channel (e.g., 'telegram', 'whatsapp', 'sms')."""
        pass

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Name of the provider/service (e.g., 'sentrybot', 'meta', 'bulksms')."""
        pass

    @abstractmethod
    async def send(
        self,
        recipient: str,
        title: str,
        body: str,
        **kwargs
    ) -> NotificationResult:
        """Send a notification.

        Args:
            recipient: Recipient identifier (phone number, Telegram ID, etc.)
            title: Notification title
            body: Notification body/message
            **kwargs: Provider-specific parameters

        Returns:
            NotificationResult with success status and details
        """
        pass

    @abstractmethod
    async def test_connection(self) -> bool:
        """Test if this provider is configured and can connect.

        Returns:
            True if provider is ready, False otherwise
        """
        pass

    @abstractmethod
    def is_enabled(self) -> bool:
        """Check if this provider is enabled (has required config).

        Returns:
            True if provider has required environment variables set
        """
        pass
