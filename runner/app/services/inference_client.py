"""InferenceClient — local-only OpenAI-compatible HTTP client for Ollama.

Calls /v1/chat/completions on a local Ollama instance. No cloud providers.
Spec Section 6.1 mandates OpenAI-compatible HTTP.
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
    """Local-only LLM client via OpenAI-compatible /v1/chat/completions.

    Built-in retry: 1 retry on timeout, no retry on 4xx.
    """

    def __init__(self, base_url: str | None = None, timeout: float | None = None) -> None:
        self.base_url = (base_url or settings.model_base_url).rstrip("/")
        self.timeout = timeout if timeout is not None else settings.inference_timeout_seconds

        # Hard block: base_url must be local
        self._enforce_local_only()

    def _enforce_local_only(self) -> None:
        """Reject any non-local inference URL. No cloud allowed."""
        from urllib.parse import urlparse

        parsed = urlparse(self.base_url)
        hostname = parsed.hostname or ""

        local_hosts = {"127.0.0.1", "localhost", "::1", "0.0.0.0"}
        if hostname not in local_hosts and not hostname.startswith("192.168.") and not hostname.startswith("10."):
            raise ValueError(
                f"Cloud inference blocked by policy. "
                f"base_url must be local, got: {self.base_url}"
            )

    async def chat(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        max_tokens: int | None = None,
    ) -> ChatResult:
        """Send a chat completion request.

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

    async def is_available(self) -> bool:
        """Check if local Ollama is reachable. GET /models with 5s timeout."""
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
        """List available model IDs from local Ollama."""
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
