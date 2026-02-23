"""InferenceClient — OpenAI-compatible HTTP client for Ollama /v1/chat/completions."""

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
    """Calls OpenAI-compatible /v1/chat/completions endpoint (NOT Ollama native /api/generate).

    Spec Section 6.1 mandates OpenAI-compatible HTTP.
    Built-in retry: 1 retry on timeout, no retry on 4xx.
    """

    def __init__(self, base_url: str | None = None, timeout: float = 60.0) -> None:
        self.base_url = (base_url or settings.model_base_url).rstrip("/")
        self.timeout = timeout

    async def chat(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        max_tokens: int | None = None,
    ) -> ChatResult:
        """Send a chat completion request.

        POST to /chat/completions with OpenAI-format payload.
        Retries once on timeout. No retry on 4xx errors.

        Returns ChatResult with extracted text and token counts.
        Raises httpx.HTTPStatusError on non-2xx responses (after retry logic).
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

        # 1 retry on timeout (2 attempts total)
        for attempt in range(2):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    resp = await client.post(url, json=payload)
                    resp.raise_for_status()
                    data = resp.json()

                    text = data["choices"][0]["message"]["content"]

                    # Extract token usage if present
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
                # No retry on 4xx/5xx — raise immediately
                logger.error("HTTP %d from %s: %s", exc.response.status_code, url, exc)
                raise

        # Should not reach here, but satisfy type checker
        raise last_error  # type: ignore[misc]

    async def is_available(self) -> bool:
        """Check if the inference backend is reachable.

        GET /models with 5s timeout. Returns True if 200, False otherwise.
        """
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

        GET /models, extract model IDs from response.
        Returns empty list on error.
        """
        url = f"{self.base_url}/models"
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                data = resp.json()

                # OpenAI format: {"data": [{"id": "model-name", ...}, ...]}
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
