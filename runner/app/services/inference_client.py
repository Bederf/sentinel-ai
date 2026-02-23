"""InferenceClient — multi-backend LLM client (Ollama + Anthropic).

Supports two backends:
- "ollama": OpenAI-compatible HTTP (local Ollama /v1/chat/completions)
- "anthropic": Anthropic Messages API (cloud)

Backend selected by settings.inference_provider.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass
class ChatResult:
    """Result from a chat completion call."""

    text: str
    input_tokens: int
    output_tokens: int
    model: str


class InferenceClient:
    """Multi-backend LLM client.

    Ollama: POST to /v1/chat/completions (OpenAI-compatible).
    Anthropic: POST to https://api.anthropic.com/v1/messages (Messages API).

    Built-in retry: 1 retry on timeout, no retry on 4xx.
    """

    def __init__(
        self,
        base_url: str | None = None,
        timeout: float | None = None,
        provider: str | None = None,
    ) -> None:
        self.provider = provider or settings.inference_provider
        self.base_url = (base_url or settings.model_base_url).rstrip("/")
        self.timeout = timeout if timeout is not None else settings.inference_timeout_seconds

    async def chat(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        max_tokens: int | None = None,
    ) -> ChatResult:
        """Send a chat completion request to the configured backend.

        Returns ChatResult with extracted text and token counts.
        """
        if self.provider == "anthropic":
            return await self._chat_anthropic(messages, model, max_tokens)
        return await self._chat_ollama(messages, model, max_tokens)

    async def _chat_ollama(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        max_tokens: int | None = None,
    ) -> ChatResult:
        """OpenAI-compatible chat completion (Ollama).

        POST to /chat/completions with OpenAI-format payload.
        Retries once on timeout. No retry on 4xx errors.
        """
        resolved_model = model or settings.model_name
        resolved_max_tokens = max_tokens or settings.max_tokens_per_call

        payload: dict[str, Any] = {
            "model": resolved_model,
            "messages": messages,
            "temperature": settings.temperature,
            "max_tokens": resolved_max_tokens,
        }

        url = f"{self.base_url}/chat/completions"
        last_error: Exception | None = None

        for attempt in range(2):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    resp = await client.post(url, json=payload)
                    resp.raise_for_status()
                    data = resp.json()

                    text = data["choices"][0]["message"]["content"]

                    usage = data.get("usage", {})
                    input_tokens = usage.get("prompt_tokens", 0)
                    output_tokens = usage.get("completion_tokens", 0)

                    return ChatResult(
                        text=text,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        model=resolved_model,
                    )

            except httpx.TimeoutException as exc:
                last_error = exc
                if attempt == 0:
                    logger.warning(
                        "Timeout on chat attempt %d, retrying once", attempt + 1
                    )
                    continue
                raise

            except httpx.HTTPStatusError as exc:
                logger.error("HTTP %d from %s: %s", exc.response.status_code, url, exc)
                raise

        raise last_error  # type: ignore[misc]

    async def _chat_anthropic(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        max_tokens: int | None = None,
    ) -> ChatResult:
        """Anthropic Messages API chat completion.

        POST to https://api.anthropic.com/v1/messages.
        Separates system prompt from user messages.
        Retries once on timeout. No retry on 4xx errors.
        """
        api_key = settings.anthropic_api_key
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not configured")

        resolved_model = model if model and not model.startswith(("phi", "llama", "tiny")) else settings.anthropic_model
        resolved_max_tokens = max_tokens or settings.max_tokens_per_call

        # Separate system prompt from conversation messages
        system_text = ""
        conversation: list[dict[str, str]] = []
        for msg in messages:
            if msg["role"] == "system":
                system_text += msg["content"] + "\n"
            else:
                conversation.append({"role": msg["role"], "content": msg["content"]})

        # Ensure at least one user message
        if not conversation:
            conversation = [{"role": "user", "content": "Analyze the evidence."}]

        payload: dict[str, Any] = {
            "model": resolved_model,
            "max_tokens": resolved_max_tokens,
            "temperature": settings.temperature,
            "messages": conversation,
        }
        if system_text.strip():
            payload["system"] = system_text.strip()

        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        last_error: Exception | None = None

        for attempt in range(2):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    resp = await client.post(url, json=payload, headers=headers)
                    resp.raise_for_status()
                    data = resp.json()

                    # Extract text from content blocks
                    content_blocks = data.get("content", [])
                    text = ""
                    for block in content_blocks:
                        if block.get("type") == "text":
                            text += block.get("text", "")

                    usage = data.get("usage", {})
                    input_tokens = usage.get("input_tokens", 0)
                    output_tokens = usage.get("output_tokens", 0)

                    return ChatResult(
                        text=text,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        model=resolved_model,
                    )

            except httpx.TimeoutException as exc:
                last_error = exc
                if attempt == 0:
                    logger.warning(
                        "Anthropic timeout on attempt %d, retrying once", attempt + 1
                    )
                    continue
                raise

            except httpx.HTTPStatusError as exc:
                logger.error(
                    "Anthropic HTTP %d: %s", exc.response.status_code, exc.response.text[:500]
                )
                raise

        raise last_error  # type: ignore[misc]

    async def is_available(self) -> bool:
        """Check if the inference backend is reachable.

        Ollama: GET /models with 5s timeout.
        Anthropic: always True if API key is configured.
        """
        if self.provider == "anthropic":
            return bool(settings.anthropic_api_key)

        url = f"{self.base_url}/models"
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(url)
                return resp.status_code == 200
        except (httpx.ConnectError, httpx.TimeoutException):
            return False
        except Exception:
            logger.warning("Unexpected error checking inference availability", exc_info=True)
            return False

    async def list_models(self) -> list[str]:
        """List available model IDs from the inference backend.

        Ollama: GET /models, extract model IDs.
        Anthropic: returns configured model name.
        """
        if self.provider == "anthropic":
            return [settings.anthropic_model] if settings.anthropic_api_key else []

        url = f"{self.base_url}/models"
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                data = resp.json()

                models = data.get("data", [])
                return [m["id"] for m in models if "id" in m]
        except Exception:
            logger.warning("Failed to list models", exc_info=True)
            return []


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_client: InferenceClient | None = None


def get_inference_client() -> InferenceClient:
    """Get or create the module-level InferenceClient singleton."""
    global _client
    if _client is None:
        _client = InferenceClient()
    return _client
