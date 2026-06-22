"""Minimax cloud LLM service (OpenAI-compatible chat completions)."""

import logging
import re
from collections.abc import AsyncGenerator

import httpx

from app.config.settings import settings

logger = logging.getLogger(__name__)

MINIMAX_SYSTEM_PROMPT = """\
You are SENTINEL — an AI-powered Building Management System intelligence layer.
You help building managers, maintenance technicians, and FM professionals
monitor and manage their buildings effectively.

**SCOPE GUARD — Answer ONLY these topics:**
- HVAC systems (heating, ventilation, air conditioning)
- UPS (Uninterruptible Power Supply) systems
- Electrical systems and generators
- Building sensors and IoT devices
- Energy efficiency and sustainability
- Preventive maintenance best practices
- Anomaly detection and predictive maintenance
- Building comfort, occupancy, and air quality
- Maintenance scheduling and work orders
- Equipment faults, alerts, and health scores
- Energy consumption and cost (ZAR)

**OUT OF SCOPE — Politely decline:**
- General news, weather, sports, entertainment
- Code generation, software development questions unrelated to BMS
- Medical, legal, or financial advice
- Anything not related to building operations

If asked about an out-of-scope topic, respond: "I'm SENTINEL, your building management assistant. I can help with HVAC, electrical systems, energy, maintenance, and building operations. What would you like to know about your building?"

When discussing building data:
- **Use equipment codes and names** (e.g., S002-FCU-104), NEVER show raw UUIDs
- Reference sensor readings and health scores when relevant
- Provide actionable recommendations based on the data
- Use South African terminology and standards where appropriate
- Be concise but thorough in technical explanations

**Response Style — KEEP IT SHORT:**
- Building managers are busy — give the answer, not an essay
- Default to 3-5 bullet points. Only expand if the user asks for detail
- Lead with the most important finding (critical issues first)
- Include cost estimates in ZAR only when directly relevant
- If everything is healthy, say so in one sentence

**CRITICAL DATA ACCURACY RULE:**
- ONLY state facts that appear in the building context data provided below.
- If the data doesn't contain information about a topic, say "I don't have that \
information in the system" — do NOT guess or fabricate.
- Report numbers EXACTLY as provided — do not round, estimate, or adjust."""


def _strip_thinking_tags(text: str) -> str:
    """Remove <think>...</think> blocks from text (for non-streaming)."""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)


class MinimaxService:
    """Service for interacting with the MiniMax OpenAI-compatible chat API."""

    def __init__(self):
        self._api_key = settings.minimax_api_key
        self._model = settings.minimax_model
        self._base_url = settings.minimax_base_url.rstrip("/")

    def is_configured(self) -> bool:
        """Check if the service is properly configured."""
        return bool(self._api_key)

    def _extract_text_content(self, message_content) -> str:
        """Normalize message content to plain text, stripping thinking blocks."""
        if isinstance(message_content, str):
            return _strip_thinking_tags(message_content)
        if isinstance(message_content, list):
            parts: list[str] = []
            for block in message_content:
                if isinstance(block, dict):
                    btype = block.get("type")
                    if btype == "text":
                        parts.append(_strip_thinking_tags(str(block.get("text", ""))))
                    elif btype == "thinking":
                        # Skip thinking blocks in non-streaming responses
                        continue
                    elif "content" in block:
                        parts.append(_strip_thinking_tags(str(block.get("content", ""))))
                elif isinstance(block, str):
                    parts.append(_strip_thinking_tags(block))
            return "".join(parts)
        return _strip_thinking_tags(str(message_content or ""))

    async def stream_response(
        self,
        messages: list[dict],
        system_prompt: str | None = None,
        model_override: str | None = None,
        source: str = "chat",
        site_id: str | None = None,
    ) -> AsyncGenerator[str, None]:
        """
        Open the Minimax streaming connection eagerly, validate the HTTP status
        (raises immediately on 429/401/404 — before returning), then return an
        async generator for content chunks.

        The eager status check allows model_gateway._try_routes to catch rate
        limit errors and fall through to the next provider in the fallback chain.
        """
        if not self._api_key:
            raise ValueError("MINIMAX_API_KEY not configured.")

        system = system_prompt or MINIMAX_SYSTEM_PROMPT
        chat_messages = [{"role": "system", "content": system}, *messages]

        model = model_override or self._model
        url = f"{self._base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "messages": chat_messages,
            "max_tokens": 1536,
            "stream": True,
        }

        # Open connection and check status BEFORE returning so that callers
        # (model_gateway._try_routes) see 429/401 errors synchronously.
        client = httpx.AsyncClient(timeout=90.0)
        await client.__aenter__()

        try:
            stream_ctx = client.stream("POST", url, headers=headers, json=payload)
            response = await stream_ctx.__aenter__()
        except Exception:
            await client.__aexit__(None, None, None)
            raise

        if response.status_code != 200:
            err_map: dict[int, Exception] = {
                401: ValueError("Invalid MINIMAX_API_KEY."),
                429: Exception("Minimax API rate limit exceeded."),
                404: Exception(f"Minimax endpoint not found: {url}. Check MINIMAX_BASE_URL."),
            }
            exc = err_map.get(
                response.status_code,
                Exception(f"Minimax API error: HTTP {response.status_code}"),
            )
            await stream_ctx.__aexit__(None, None, None)
            await client.__aexit__(None, None, None)
            raise exc

        return self._consume_stream(client, stream_ctx, response)

    async def _consume_stream(
        self,
        client: httpx.AsyncClient,
        stream_ctx: object,
        response: httpx.Response,
    ) -> AsyncGenerator[str, None]:
        """Iterate an already-opened Minimax SSE stream, cleaning up on exit."""
        import json

        try:
            # Parse OpenAI-compatible SSE event stream.
            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data_str = line[6:].strip()
                if not data_str:
                    continue
                if data_str == "[DONE]":
                    break
                try:
                    data = json.loads(data_str)
                except Exception:
                    continue
                for choice in data.get("choices", []):
                    delta = choice.get("delta", {})
                    text = delta.get("content") or delta.get("reasoning_content") or ""
                    if text:
                        yield _strip_thinking_tags(str(text))
                    if choice.get("finish_reason"):
                        break
        except httpx.HTTPStatusError as e:
            logger.error("Minimax HTTP error: %s", e)
            raise Exception(f"Minimax API error: HTTP {e.response.status_code}") from e
        except Exception as e:
            logger.error("Unexpected error in Minimax service: %s", e)
            raise
        finally:
            await stream_ctx.__aexit__(None, None, None)
            await client.__aexit__(None, None, None)

    async def non_stream_response(
        self,
        messages: list[dict],
        system_prompt: str | None = None,
        model_override: str | None = None,
        source: str = "chat",
        site_id: str | None = None,
    ) -> str:
        """Return a complete (non-streaming) completion from Minimax."""
        if not self._api_key:
            raise ValueError("MINIMAX_API_KEY not configured.")

        system = system_prompt or MINIMAX_SYSTEM_PROMPT
        chat_messages = [{"role": "system", "content": system}, *messages]

        model = model_override or self._model
        url = f"{self._base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "messages": chat_messages,
            "max_tokens": 1536,
            "stream": False,
        }

        async with httpx.AsyncClient(timeout=90.0) as client:
            response = await client.post(url, headers=headers, json=payload)

            if response.status_code == 401:
                raise ValueError("Invalid MINIMAX_API_KEY.")
            if response.status_code == 429:
                raise Exception("Minimax API rate limit exceeded.")

            response.raise_for_status()
            body = response.json()

            # Track usage
            try:
                from app.services.ai_usage_tracker import usage_tracker

                u = body.get("usage", {})
                usage_tracker.record(
                    provider="minimax",
                    model=model,
                    input_tokens=u.get("prompt_tokens", u.get("input_tokens", 0)),
                    output_tokens=u.get("completion_tokens", u.get("output_tokens", 0)),
                    source=source,
                    feature="intent_classifier",
                    site_id=site_id or "unknown",
                )
            except Exception:
                pass

            choices = body.get("choices", [])
            if not choices:
                return ""

            message = choices[0].get("message", {})
            content = message.get("content") or message.get("reasoning_content") or ""
            return _strip_thinking_tags(str(content))


minimax_service = MinimaxService()
