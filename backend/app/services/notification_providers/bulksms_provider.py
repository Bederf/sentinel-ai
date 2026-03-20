"""
BulkSMS notification provider — REST API integration.

Phase 102: Direct technician SMS messages.
Currently uses placeholder credentials — will be configured when BulkSMS account is ready.
"""

import os
import logging

import httpx

from .base_provider import BaseNotificationProvider, NotificationResult

logger = logging.getLogger(__name__)


class BulkSMSProvider(BaseNotificationProvider):
    """Send notifications via SMS using BulkSMS REST API."""

    def __init__(self):
        self.api_key = os.getenv("BULKSMS_API_KEY", "")
        self.api_secret = os.getenv("BULKSMS_API_SECRET", "")
        self.base_url = "https://api.bulksms.com/v1"

    @property
    def channel_name(self) -> str:
        return "sms"

    @property
    def provider_name(self) -> str:
        return "bulksms"

    def is_enabled(self) -> bool:
        """Check if BulkSMS provider is configured."""
        return bool(self.api_key and self.api_secret)

    async def test_connection(self) -> bool:
        """Test connection to BulkSMS API."""
        if not self.is_enabled():
            return False

        try:
            async with httpx.AsyncClient(auth=(self.api_key, self.api_secret)) as client:
                response = await client.get(f"{self.base_url}/account", timeout=10)
                return response.status_code == 200
        except Exception as e:
            logger.error(f"BulkSMS connection test failed: {e}")
            return False

    async def send(self, recipient: str, title: str, body: str, **kwargs) -> NotificationResult:
        """Send SMS message via BulkSMS REST API.

        Args:
            recipient: Recipient phone number (format: +27XXXXXXXXX)
            title: Message title
            body: Message body
            **kwargs: Additional parameters (unused for now)

        Returns:
            NotificationResult with success status
        """
        if not self.is_enabled():
            return NotificationResult(
                success=False,
                error_code="not_configured",
                error_message="BulkSMS provider not configured (missing BULKSMS_API_KEY or BULKSMS_API_SECRET)",
            )

        try:
            # Format message (title as first line, body as second)
            message_text = f"{title}\n{body}"

            # Prepare payload for BulkSMS API
            payload = {"to": recipient, "body": message_text}

            headers = {"Content-Type": "application/json"}

            # Send via BulkSMS API
            async with httpx.AsyncClient(auth=(self.api_key, self.api_secret)) as client:
                response = await client.post(f"{self.base_url}/messages", json=payload, headers=headers, timeout=10)

                if response.status_code == 201:
                    data = response.json()
                    message_id = data.get("id", "unknown")
                    logger.info(f"SMS message sent to {recipient}, ID: {message_id}")

                    try:
                        from app.services.ai_usage_tracker import usage_tracker

                        usage_tracker.record_message("bulksms", source="alert")
                    except Exception:
                        pass

                    return NotificationResult(success=True, message_id=message_id, provider_response=data)
                else:
                    error_data = response.json() if response.text else {}
                    error_msg = error_data.get("error", "Unknown error")
                    logger.error(f"BulkSMS API error: {error_msg}")
                    return NotificationResult(
                        success=False,
                        error_code=f"http_{response.status_code}",
                        error_message=error_msg,
                        provider_response=error_data,
                    )

        except httpx.TimeoutException:
            return NotificationResult(
                success=False, error_code="timeout", error_message="BulkSMS API request timed out after 10 seconds"
            )
        except Exception as e:
            logger.error(f"BulkSMS provider error: {e}")
            return NotificationResult(success=False, error_code="exception", error_message=str(e))
