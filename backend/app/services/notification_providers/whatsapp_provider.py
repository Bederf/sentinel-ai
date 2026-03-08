"""WhatsApp notification provider — delegates to WhatsAppService (Meta or Twilio)."""

import logging

from .base_provider import BaseNotificationProvider, NotificationResult

logger = logging.getLogger(__name__)


class WhatsAppProvider(BaseNotificationProvider):
    """Send notifications via WhatsApp (Meta Cloud API or Twilio)."""

    def __init__(self):
        from app.integrations.whatsapp_service import get_whatsapp_service

        self._service = get_whatsapp_service()

    @property
    def channel_name(self) -> str:
        return "whatsapp"

    @property
    def provider_name(self) -> str:
        return self._service.provider

    def is_enabled(self) -> bool:
        return self._service.enabled

    async def test_connection(self) -> bool:
        return self._service.enabled

    async def send(self, recipient: str, title: str, body: str, **kwargs) -> NotificationResult:
        if not self.is_enabled():
            return NotificationResult(
                success=False,
                error_code="not_configured",
                error_message=f"WhatsApp provider not configured ({self._service.provider})",
            )
        try:
            message_text = f"*{title}*\n\n{body}"
            result = await self._service.send_text_message(recipient, message_text)
            if result.get("success"):
                return NotificationResult(
                    success=True,
                    message_id=result.get("message_id"),
                    provider_response=result,
                )
            else:
                return NotificationResult(
                    success=False,
                    error_code="send_failed",
                    error_message=result.get("error", "Unknown error"),
                    provider_response=result,
                )
        except Exception as e:
            logger.error(f"WhatsApp provider error: {e}")
            return NotificationResult(success=False, error_code="exception", error_message=str(e))
