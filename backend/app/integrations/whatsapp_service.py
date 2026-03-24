"""
WhatsApp Business API integration for SENTRY bot.
Supports both Meta Cloud API and Twilio providers.
"""

import hmac
import httpx
import os
from datetime import datetime
from typing import Any, Dict, Optional
import logging

logger = logging.getLogger(__name__)


class WhatsAppService:
    """WhatsApp Business API integration."""

    def __init__(self, provider: str = "meta"):
        """
        Initialize WhatsApp service.

        Args:
            provider: "meta" (Cloud API) or "twilio"
        """
        self.provider = provider
        self.enabled = False

        from app.config.settings import settings

        if provider == "meta":
            self.phone_id = os.getenv("WHATSAPP_PHONE_ID", "")
            self.api_token = os.getenv("WHATSAPP_API_TOKEN", "")
            self.business_id = os.getenv("WHATSAPP_BUSINESS_ID", "")
            self.webhook_token = os.getenv("WHATSAPP_WEBHOOK_TOKEN", "")
            if self.webhook_token in ("", "secret"):
                logger.warning(
                    "WHATSAPP_WEBHOOK_TOKEN not set or uses insecure default — webhook verification disabled"
                )

            if self.phone_id and self.api_token:
                self.api_url = f"https://graph.instagram.com/v18.0/{self.phone_id}/messages"
                self.enabled = True
                logger.info(f"WhatsApp service initialized (Meta API, phone_id={self.phone_id[:20]}...)")
            else:
                logger.warning("WhatsApp Meta credentials not fully configured")

        elif provider == "twilio":
            self.account_sid = os.getenv("TWILIO_ACCOUNT_SID", "") or settings.twilio_account_sid
            self.auth_token = os.getenv("TWILIO_AUTH_TOKEN", "") or settings.twilio_auth_token
            self.twilio_whatsapp = (
                os.getenv("TWILIO_WHATSAPP_FROM", "")
                or settings.twilio_whatsapp_from
                or os.getenv("TWILIO_WHATSAPP_NUMBER", "")
            )
            self.webhook_token = os.getenv("WHATSAPP_WEBHOOK_TOKEN", "")
            if self.webhook_token in ("", "secret"):
                logger.warning(
                    "WHATSAPP_WEBHOOK_TOKEN not set or uses insecure default — webhook verification disabled"
                )

            if self.account_sid and self.auth_token and self.twilio_whatsapp:
                self.api_url = f"https://api.twilio.com/2010-04-01/Accounts/{self.account_sid}/Messages.json"
                self.enabled = True
                logger.info(f"WhatsApp service initialized (Twilio, number={self.twilio_whatsapp})")
            else:
                logger.warning("WhatsApp Twilio credentials not fully configured")

    async def send_text_message(self, to_number: str, message: str, context_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Send text message via WhatsApp.

        Args:
            to_number: Recipient phone (format: +27XXXXXXXXX for SA)
            message: Message text (max 1024 chars)
            context_id: Optional context message ID for threading

        Returns:
            Response with message ID and status
        """
        if not self.enabled:
            logger.warning("WhatsApp service not enabled, skipping message send")
            return {"success": False, "error": "WhatsApp service not configured"}

        try:
            if self.provider == "meta":
                return await self._send_meta_text(to_number, message, context_id)
            else:
                return await self._send_twilio_text(to_number, message)
        except Exception as e:
            logger.error(f"Error sending WhatsApp message: {e}")
            return {"success": False, "error": str(e)}

    async def _send_meta_text(self, to_number: str, message: str, context_id: Optional[str] = None) -> Dict[str, Any]:
        """Send via Meta Cloud API."""
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to_number,
            "type": "text",
            "text": {"preview_url": True, "body": message},
        }

        if context_id:
            payload["context"] = {"message_id": context_id}

        headers = {"Authorization": f"Bearer {self.api_token}", "Content-Type": "application/json"}

        logger.debug(f"Sending Meta WhatsApp to {to_number}: {message[:50]}...")

        async with httpx.AsyncClient() as client:
            response = await client.post(self.api_url, json=payload, headers=headers, timeout=10.0)
            response.raise_for_status()
            data = response.json()

            message_id = data.get("messages", [{}])[0].get("id", "unknown")
            logger.info(f"WhatsApp message sent to {to_number}, ID: {message_id}")

            try:
                from app.services.ai_usage_tracker import usage_tracker

                usage_tracker.record_message("whatsapp_meta", source="alert")
            except Exception:
                pass

            return {
                "success": True,
                "message_id": message_id,
                "timestamp": datetime.utcnow().isoformat(),
                "provider": "meta",
                "to": to_number,
            }

    async def _send_twilio_text(self, to_number: str, message: str) -> Dict[str, Any]:
        """Send via Twilio."""
        # Ensure whatsapp: prefix is present but not duplicated
        to_wa = to_number if to_number.startswith("whatsapp:") else f"whatsapp:{to_number}"
        payload = {"From": self.twilio_whatsapp, "To": to_wa, "Body": message}

        auth = (self.account_sid, self.auth_token)

        logger.debug(f"Sending Twilio WhatsApp to {to_number}: {message[:50]}...")

        async with httpx.AsyncClient() as client:
            response = await client.post(self.api_url, data=payload, auth=auth, timeout=10.0)
            response.raise_for_status()
            data = response.json()

            message_id = data.get("sid", "unknown")
            logger.info(f"WhatsApp message sent to {to_number}, ID: {message_id}")

            try:
                from app.services.ai_usage_tracker import usage_tracker

                usage_tracker.record_message("whatsapp_twilio", source="alert")
            except Exception:
                pass

            return {
                "success": True,
                "message_id": message_id,
                "timestamp": datetime.utcnow().isoformat(),
                "provider": "twilio",
                "to": to_number,
            }

    def verify_webhook_token(self, token: str) -> bool:
        """Verify webhook token for security using constant-time comparison."""
        if not token or not self.webhook_token:
            return False
        is_valid = hmac.compare_digest(token, self.webhook_token)
        if not is_valid:
            logger.warning(f"Invalid webhook token attempted: {token[:10]}...")
        return is_valid

    def get_status(self) -> Dict[str, Any]:
        """Get WhatsApp service status."""
        return {
            "enabled": self.enabled,
            "provider": self.provider,
            "phone_id": self.phone_id if self.provider == "meta" else None,
            "twilio_number": self.twilio_whatsapp if self.provider == "twilio" else None,
        }


# Singleton instance
_whatsapp_service: Optional[WhatsAppService] = None


def get_whatsapp_service(provider: Optional[str] = None) -> WhatsAppService:
    """Get or create WhatsApp service singleton.

    Auto-detects provider: explicit arg > WHATSAPP_PROVIDER env > Twilio if SID set > meta fallback.
    """
    global _whatsapp_service
    if _whatsapp_service is None:
        from app.config.settings import settings

        if provider:
            resolved = provider
        else:
            resolved = os.getenv("WHATSAPP_PROVIDER", "")
            if not resolved:
                if os.getenv("TWILIO_ACCOUNT_SID") or settings.twilio_account_sid:
                    resolved = "twilio"
                else:
                    resolved = "meta"
        _whatsapp_service = WhatsAppService(resolved)
    return _whatsapp_service
