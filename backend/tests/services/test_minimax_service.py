from __future__ import annotations

import pytest

from app.services import minimax_service as minimax_module
from app.services.minimax_service import MinimaxService


class _FakeResponse:
    status_code = 200

    def __init__(self, body: dict):
        self._body = body

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._body


class _FakeAsyncClient:
    last_url: str | None = None
    last_headers: dict | None = None
    last_payload: dict | None = None
    response: _FakeResponse = _FakeResponse(
        {
            "choices": [{"message": {"content": "ok"}}],
            "usage": {"prompt_tokens": 12, "completion_tokens": 3},
        }
    )

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def post(self, url: str, headers: dict, json: dict):
        type(self).last_url = url
        type(self).last_headers = headers
        type(self).last_payload = json
        return type(self).response


@pytest.mark.asyncio
async def test_minimax_uses_openai_compatible_chat_completions(monkeypatch):
    monkeypatch.setattr(minimax_module.settings, "minimax_api_key", "test-key")
    monkeypatch.setattr(minimax_module.settings, "minimax_model", "MiniMax-M2.5")
    monkeypatch.setattr(minimax_module.settings, "minimax_base_url", "https://api.minimax.io/v1")
    monkeypatch.setattr(minimax_module.httpx, "AsyncClient", _FakeAsyncClient)
    record_calls = []

    class FakeUsageTracker:
        def record(self, **kwargs):
            record_calls.append(kwargs)

    monkeypatch.setattr("app.services.ai_usage_tracker.usage_tracker", FakeUsageTracker())

    service = MinimaxService()
    result = await service.non_stream_response(
        messages=[{"role": "user", "content": "Say ok."}],
        system_prompt="system",
        source="test",
        site_id="site-002",
    )

    assert result == "ok"
    assert _FakeAsyncClient.last_url == "https://api.minimax.io/v1/chat/completions"
    assert _FakeAsyncClient.last_headers["Authorization"] == "Bearer test-key"
    assert "anthropic-version" not in _FakeAsyncClient.last_headers
    assert _FakeAsyncClient.last_payload["messages"] == [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "Say ok."},
    ]
    assert record_calls[-1]["site_id"] == "site-002"
    assert record_calls[-1]["provider"] == "minimax"


@pytest.mark.asyncio
async def test_minimax_raises_on_401(monkeypatch):
    class UnauthorizedResponse(_FakeResponse):
        status_code = 401

    class UnauthorizedClient(_FakeAsyncClient):
        response = UnauthorizedResponse({"error": {"message": "invalid api key"}})

    monkeypatch.setattr(minimax_module.settings, "minimax_api_key", "test-key")
    monkeypatch.setattr(minimax_module.settings, "minimax_model", "MiniMax-M2.5")
    monkeypatch.setattr(minimax_module.settings, "minimax_base_url", "https://api.minimax.io/v1")
    monkeypatch.setattr(minimax_module.httpx, "AsyncClient", UnauthorizedClient)

    service = MinimaxService()
    with pytest.raises(ValueError, match="Invalid MINIMAX_API_KEY"):
        await service.non_stream_response(messages=[{"role": "user", "content": "Say ok."}])
