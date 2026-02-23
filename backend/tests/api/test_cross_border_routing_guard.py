"""Tests for POPIA cross-border routing guard in chat APIs."""

from unittest.mock import AsyncMock
import uuid

import pytest


@pytest.mark.asyncio
async def test_chat_uses_local_fallback_when_cross_border_consent_missing(client, monkeypatch):
    """Cloud routing should be blocked without cross-border consent."""

    async def _local_stream(_message, use_tools=False, data_subject_id=None):  # noqa: ARG001
        yield "LOCAL_FALLBACK_RESPONSE"

    monkeypatch.setattr("app.api.chat.should_allow_cloud_processing", lambda _subject: False)
    monkeypatch.setattr("app.api.chat.hybrid_ai_service.stream_response", _local_stream)
    monkeypatch.setattr(
        "app.api.chat.claude_service.stream_response",
        AsyncMock(side_effect=AssertionError("Cloud stream should not be called")),
    )
    monkeypatch.setattr(
        "app.api.chat.claude_service.stream_response_with_tools",
        AsyncMock(side_effect=AssertionError("Cloud tools stream should not be called")),
    )

    payload = {
        "message": f"Summarize equipment status {uuid.uuid4()}",
        "search_docs": False,
    }
    response = await client.post("/api/chat", json=payload)
    assert response.status_code == 200
    assert "LOCAL_FALLBACK_RESPONSE" in response.text
