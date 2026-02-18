"""
WhatsApp notification provider — Meta Cloud API integration.

Phase 102: Direct technician WhatsApp messages.
Currently uses placeholder credentials — will be configured when Meta Business Account is ready.
"""

import os
import logging

import httpx

from .base_provider import BaseNotificationProvider, NotificationResult

logger = logging.getLogger(__name__)


class WhatsAppProvider(BaseNotificationProvider):
    """Send notifications via WhatsApp using Meta Cloud API."""

    def __init__(self):
        self.api_token = os.getenv("WHATSAPP_API_TOKEN", "")
        self.phone_id = os.getenv("WHATSAPP_PHONE_ID", "")
        self.business_id = os.getenv("WHATSAPP_BUSINESS_ID", "")
        self.webhook_token = os.getenv("WHATSAPP_WEBHOOK_TOKEN", "")

    @property
    def channel_name(self) -> str:
        return "whatsapp"

    @property
    def provider_name(self) -> str:
        return "meta"

    def is_enabled(self) -> bool:
        """Check if WhatsApp provider is configured."""
        return bool(self.api_token and self.phone_id)

    async def test_connection(self) -> bool:
        """Test connection to Meta Cloud API."""
        if not self.is_enabled():
            return False

        try:
            async with httpx.AsyncClient() as client:
                headers = {"Authorization": f"Bearer {self.api_token}"}
                response = await client.get(
                    f"https://graph.instagram.com/v18.0/{self.phone_id}",
                    headers=headers,
                    timeout=10
                )
                return response.status_code == 200
        except Exception as e:
            logger.error(f"WhatsApp connection test failed: {e}")
            return False

    async def send(
        self,
        recipient: str,
        title: str,
        body: str,
        **kwargs
    ) -> NotificationResult:
        """Send WhatsApp message via Meta Cloud API.

        Args:
            recipient: Recipient WhatsApp phone number (format: +27XXXXXXXXX)
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
                error_message="WhatsApp provider not configured (missing WHATSAPP_API_TOKEN or WHATSAPP_PHONE_ID)"
            )

        try:
            # Format message (title as bold header)
            message_text = f"*{title}*\n\n{body}"

            # Prepare payload for Meta Cloud API
            payload = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": recipient,
                "type": "text",
                "text": {
                    "preview_url": True,
                    "body": message_text
                }
            }

            headers = {
                "Authorization": f"Bearer {self.api_token}",
                "Content-Type": "application/json"
            }

            # Send via Meta API
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"https://graph.instagram.com/v18.0/{self.phone_id}/messages",
                    json=payload,
                    headers=headers,
                    timeout=10
                )

                if response.status_code == 200:
                    data = response.json()
                    message_id = data.get("messages", [{}])[0].get("id", "unknown")
                    logger.info(f"WhatsApp message sent to {recipient}, ID: {message_id}")
                    return NotificationResult(
                        success=True,
                        message_id=message_id,
                        provider_response=data
                    )
                else:
                    error_data = response.json() if response.text else {}
                    error_msg = error_data.get("error", {}).get("message", "Unknown error")
                    logger.error(f"WhatsApp API error: {error_msg}")
                    return NotificationResult(
                        success=False,
                        error_code=f"http_{response.status_code}",
                        error_message=error_msg,
                        provider_response=error_data
                    )

        except httpx.TimeoutException:
            return NotificationResult(
                success=False,
                error_code="timeout",
                error_message="Meta API request timed out after 10 seconds"
            )
        except Exception as e:
            logger.error(f"WhatsApp provider error: {e}")
            return NotificationResult(
                success=False,
                error_code="exception",
                error_message=str(e)
            )
