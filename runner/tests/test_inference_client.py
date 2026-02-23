"""Tests for InferenceClient — mock Ollama, never call real."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.services.inference_client import InferenceClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _openai_response(content: str = "Hello", model: str = "phi3:mini",
                     prompt_tokens: int = 10, completion_tokens: int = 20) -> dict:
    """Build a minimal OpenAI-compatible chat completions response."""
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    }


def _make_response(status_code: int = 200, json_data: dict | None = None) -> httpx.Response:
    """Create an httpx.Response with a proper request set (needed for raise_for_status)."""
    body = json.dumps(json_data or {}).encode()
    resp = httpx.Response(
        status_code=status_code,
        content=body,
        headers={"content-type": "application/json"},
        request=httpx.Request("POST", "http://fake:11434/v1/chat/completions"),
    )
    return resp


def _models_response(model_ids: list[str] | None = None) -> dict:
    """Build an OpenAI-compatible /models response."""
    ids = model_ids or ["phi3:mini", "llama3.2:1b"]
    return {
        "object": "list",
        "data": [{"id": mid, "object": "model"} for mid in ids],
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_chat_returns_text():
    """Mock httpx response with OpenAI-format JSON, verify text extracted."""
    client = InferenceClient(base_url="http://fake:11434/v1")

    mock_resp = _make_response(200, _openai_response(content="Analysis complete"))

    with patch("app.services.inference_client.httpx.AsyncClient") as MockAsyncClient:
        instance = AsyncMock()
        instance.post.return_value = mock_resp
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        MockAsyncClient.return_value = instance

        result = await client.chat(
            messages=[{"role": "user", "content": "Analyze this"}],
            model="phi3:mini",
        )

    assert result.text == "Analysis complete"
    assert result.model == "phi3:mini"


@pytest.mark.asyncio
async def test_chat_retry_on_timeout():
    """First call raises TimeoutException, second succeeds."""
    client = InferenceClient(base_url="http://fake:11434/v1")

    mock_resp = _make_response(200, _openai_response(content="Retry success"))

    call_count = 0

    async def mock_post(url, json=None, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise httpx.TimeoutException("timed out")
        return mock_resp

    with patch("app.services.inference_client.httpx.AsyncClient") as MockAsyncClient:
        instance = AsyncMock()
        instance.post = mock_post
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        MockAsyncClient.return_value = instance

        result = await client.chat(
            messages=[{"role": "user", "content": "Retry test"}],
        )

    assert result.text == "Retry success"
    assert call_count == 2


@pytest.mark.asyncio
async def test_is_available_true():
    """Mock 200 from /models."""
    client = InferenceClient(base_url="http://fake:11434/v1")

    mock_resp = _make_response(200, _models_response())

    with patch("app.services.inference_client.httpx.AsyncClient") as MockAsyncClient:
        instance = AsyncMock()
        instance.get.return_value = mock_resp
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        MockAsyncClient.return_value = instance

        available = await client.is_available()

    assert available is True


@pytest.mark.asyncio
async def test_is_available_false():
    """Mock connection error -> returns False."""
    client = InferenceClient(base_url="http://fake:11434/v1")

    with patch("app.services.inference_client.httpx.AsyncClient") as MockAsyncClient:
        instance = AsyncMock()
        instance.get.side_effect = httpx.ConnectError("connection refused")
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        MockAsyncClient.return_value = instance

        available = await client.is_available()

    assert available is False


@pytest.mark.asyncio
async def test_token_tracking():
    """Verify usage tokens captured from response."""
    client = InferenceClient(base_url="http://fake:11434/v1")

    mock_resp = _make_response(
        200,
        _openai_response(
            content="Token test",
            prompt_tokens=42,
            completion_tokens=99,
        ),
    )

    with patch("app.services.inference_client.httpx.AsyncClient") as MockAsyncClient:
        instance = AsyncMock()
        instance.post.return_value = mock_resp
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        MockAsyncClient.return_value = instance

        result = await client.chat(
            messages=[{"role": "user", "content": "count tokens"}],
        )

    assert result.input_tokens == 42
    assert result.output_tokens == 99
