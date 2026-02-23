"""Ingress consent enforcement tests for WhatsApp and Telegram paths."""

from unittest.mock import AsyncMock
import uuid

import pytest

from app.config.settings import settings


def _whatsapp_payload(sender: str, text: str) -> dict:
    return {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [
                                {
                                    "from": sender,
                                    "id": f"msg-{uuid.uuid4()}",
                                    "type": "text",
                                    "text": {"body": text},
                                }
                            ]
                        }
                    }
                ]
            }
        ]
    }


@pytest.mark.asyncio
async def test_whatsapp_blocks_until_processing_consent(client, monkeypatch):
    """WhatsApp ingress should gate processing until consent is granted."""
    sender = f"+2782{uuid.uuid4().hex[:8]}"
    route_mock = AsyncMock()
    send_mock = AsyncMock()

    monkeypatch.setattr("app.api.whatsapp_webhooks.route_incoming_message", route_mock)
    monkeypatch.setattr("app.api.whatsapp_webhooks.whatsapp_service.send_text_message", send_mock)

    # No consent yet: route handler should not be called
    first = await client.post("/api/whatsapp/webhooks", json=_whatsapp_payload(sender, "help"))
    assert first.status_code == 200
    assert route_mock.await_count == 0

    # Grant consent
    consent = await client.post("/api/whatsapp/webhooks", json=_whatsapp_payload(sender, "YES"))
    assert consent.status_code == 200
    assert route_mock.await_count == 0

    # Normal processing now allowed
    allowed = await client.post("/api/whatsapp/webhooks", json=_whatsapp_payload(sender, "status"))
    assert allowed.status_code == 200
    assert route_mock.await_count == 1


@pytest.mark.asyncio
async def test_sentry_work_order_response_requires_telegram_consent(client, monkeypatch):
    """Telegram response endpoint should require pi_processing consent."""
    user_id = f"tg-{uuid.uuid4()}"
    handler_mock = AsyncMock(return_value={"success": True, "next_prompt": "ok"})
    monkeypatch.setattr("app.api.sentry_webhooks.work_order_notifier.handle_technician_reply", handler_mock)

    payload = {
        "service_record_code": "SR-2026-TEST01",
        "telegram_user_id": user_id,
        "message_type": "text",
        "content": "done",
    }

    headers = {}
    if settings.sentry_bot_api_key:
        headers["X-Sentry-API-Key"] = settings.sentry_bot_api_key
    if settings.sentry_webhook_secret:
        headers["X-Sentry-Secret"] = settings.sentry_webhook_secret

    blocked = await client.post("/api/sentry/work-order/response", json=payload, headers=headers)
    assert blocked.status_code == 200
    assert blocked.json()["requires_consent"] is True
    assert handler_mock.await_count == 0

    consent_payload = {
        "service_record_code": "SR-2026-TEST01",
        "telegram_user_id": user_id,
        "message_type": "text",
        "content": "YES",
    }
    granted = await client.post("/api/sentry/work-order/response", json=consent_payload, headers=headers)
    assert granted.status_code == 200
    assert granted.json()["consent_status"] == "consent_granted"
    assert handler_mock.await_count == 0

    allowed = await client.post("/api/sentry/work-order/response", json=payload, headers=headers)
    assert allowed.status_code == 200
    assert allowed.json()["success"] is True
    assert handler_mock.await_count == 1
