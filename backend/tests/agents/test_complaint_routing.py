"""
Integration tests for complaint routing
=========================================
Tests that the desk complaint agent is properly wired into
chat tools, WhatsApp webhooks, and Telegram.
"""

import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
os.environ.setdefault("DEMO_MODE", "true")

from app.services.popia_consent_guard import IngressConsentDecision

_CONSENT_GRANTED = IngressConsentDecision(allow_processing=True, status="active")


class TestChatToolRegistration:
    """Verify handle_comfort_complaint is registered as a chat tool."""

    def test_tool_in_chat_tools_list(self):
        from app.services.chat_tools import CHAT_TOOLS

        names = [t["name"] for t in CHAT_TOOLS]
        assert "handle_comfort_complaint" in names

    def test_tool_in_handlers(self):
        from app.services.chat_tools import TOOL_HANDLERS

        assert "handle_comfort_complaint" in TOOL_HANDLERS

    def test_tool_schema_correct(self):
        from app.services.chat_tools import CHAT_TOOLS

        tool = next(t for t in CHAT_TOOLS if t["name"] == "handle_comfort_complaint")
        schema = tool["input_schema"]
        assert "user_message" in schema["properties"]
        assert "user_message" in schema["required"]

    @pytest.mark.asyncio
    async def test_handler_invocation(self):
        from app.services.chat_tools import handle_comfort_complaint

        result = await handle_comfort_complaint(
            user_message="Too hot at desk 25",
            user_id="test_chat",
            channel="chat",
        )
        assert result.get("success") is True
        assert "response" in result
        assert isinstance(result["needs_input"], bool)

    @pytest.mark.asyncio
    async def test_handler_asks_for_desk(self):
        from app.services.chat_tools import handle_comfort_complaint

        result = await handle_comfort_complaint(
            user_message="it's too hot here",
            user_id="test_chat_nodsk",
            channel="chat",
        )
        assert result.get("success") is True
        assert result["needs_input"] is True
        assert "desk" in result["response"].lower()


class TestWhatsAppRouting:
    """Verify comfort complaint detection in WhatsApp webhook routing."""

    def test_complaint_detected_before_existing_routing(self):
        """Comfort complaints should be detected before the fallback 'unrecognized' handler."""
        from app.agents.complaint_nlp import detect_comfort_complaint

        # These should be caught by the agent
        assert detect_comfort_complaint("it's freezing") is True
        assert detect_comfort_complaint("too hot here") is True

        # These should fall through to existing handlers
        assert detect_comfort_complaint("WO-2026-0042") is False
        assert detect_comfort_complaint("status") is False
        assert detect_comfort_complaint("help") is False


class TestTelegramRouting:
    """Verify Telegram comfort complaint handler is available."""

    @pytest.mark.asyncio
    @patch(
        "app.services.sentry_integration.work_order_notifier.evaluate_ingress_processing_consent",
        return_value=_CONSENT_GRANTED,
    )
    async def test_telegram_handler_exists(self, _mock_consent):
        from app.services.sentry_integration.work_order_notifier import (
            handle_telegram_comfort_complaint,
        )

        # Non-complaint message should return None
        result = await handle_telegram_comfort_complaint("123456", "status")
        assert result is None

    @pytest.mark.asyncio
    @patch(
        "app.services.sentry_integration.work_order_notifier.evaluate_ingress_processing_consent",
        return_value=_CONSENT_GRANTED,
    )
    async def test_telegram_handler_processes_complaint(self, _mock_consent):
        from app.services.sentry_integration.work_order_notifier import (
            handle_telegram_comfort_complaint,
        )

        result = await handle_telegram_comfort_complaint("123456", "too hot at desk 25")
        assert result is not None
        assert isinstance(result, str)
        assert len(result) > 0
