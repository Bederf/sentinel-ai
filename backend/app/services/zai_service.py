"""Z.ai cloud LLM service (OpenAI-compatible chat completions)."""

import logging
from typing import AsyncGenerator

import httpx

from app.config.settings import settings
from app.services.claude_service import FM_SYSTEM_PROMPT_BASE, build_system_prompt_with_context

logger = logging.getLogger(__name__)


class ZAIService:
    """Service for interacting with Z.ai chat completion API."""

    def __init__(self):
        self._api_key = settings.zai_api_key
        self._model = settings.zai_model
        self._base_url = settings.zai_base_url.rstrip("/")

    def is_configured(self) -> bool:
        """Check if the service is properly configured."""
        return bool(self._api_key)

    @staticmethod
    def _extract_text_content(message_content) -> str:
        """Normalize OpenAI-compatible message content to plain text."""
        if isinstance(message_content, str):
            return message_content
        if isinstance(message_content, list):
            parts: list[str] = []
            for block in message_content:
                if isinstance(block, dict):
                    if block.get("type") == "text":
                        parts.append(str(block.get("text", "")))
                    elif "content" in block:
                        parts.append(str(block.get("content", "")))
                elif isinstance(block, str):
                    parts.append(block)
            return "".join(parts)
        return str(message_content or "")

    async def stream_response(
        self,
        messages: list[dict],
        system_prompt: str | None = None,
        include_building_context: bool = True,
    ) -> AsyncGenerator[str, None]:
        """Return a completion from Z.ai as a single streamed chunk."""
        if not self._api_key:
            raise ValueError("ZAI_API_KEY not configured. Set it in .env or environment variables.")

        if system_prompt:
            system = system_prompt
        elif include_building_context:
            system = build_system_prompt_with_context()
        else:
            system = FM_SYSTEM_PROMPT_BASE

        openai_messages = [{"role": "system", "content": system}]
        openai_messages.extend(messages)

        url = f"{self._base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self._model,
            "messages": openai_messages,
            "temperature": 0.3,
            "stream": False,
        }

        try:
            async with httpx.AsyncClient(timeout=90.0) as client:
                response = await client.post(url, headers=headers, json=payload)

            if response.status_code == 401:
                raise ValueError("Invalid ZAI_API_KEY. Please check your API key configuration.")
            if response.status_code == 429:
                raise Exception("Z.ai API rate limit exceeded. Please try again in a moment.")

            response.raise_for_status()
            body = response.json()
            choices = body.get("choices", [])
            if not choices:
                raise Exception("Z.ai response did not include any choices.")

            message = choices[0].get("message", {})
            content = self._extract_text_content(message.get("content"))
            yield content or "I could not generate a response from Z.ai."

        except ValueError:
            raise
        except httpx.HTTPStatusError as e:
            logger.error("Z.ai HTTP error: %s", e)
            raise Exception(f"Z.ai API error: HTTP {e.response.status_code}") from e
        except Exception as e:
            logger.error("Unexpected error in Z.ai service: %s", e)
            raise


zai_service = ZAIService()
