"""LLM client — routes through Anthropic Claude (primary) with Z.ai fallback.

Originally this was the Ollama client for local LLM inference.
On this VPS (CPU-only, no GPU), Ollama generates ~0.1 tok/s — unusable.
All services that previously called Ollama now route through this module,
which uses Anthropic Claude for generation.

The OllamaClient class is preserved for future GPU-equipped deployments.
"""

import json
import logging
import os
from collections.abc import AsyncIterator

import httpx

from app.config.settings import settings

logger = logging.getLogger(__name__)


class CloudLLMClient:
    """Drop-in replacement for OllamaClient that routes through Anthropic Claude.

    Same interface as OllamaClient (generate, is_available, chat) so all
    existing services work without modification.  Falls back to Z.ai if
    Claude is unavailable.
    """

    def __init__(self):
        self.model = settings.claude_model
        self.default_model = self.model  # compat with OllamaClient attribute
        self._client = None

    def _get_client(self):
        """Lazy-init Anthropic client."""
        if self._client is None:
            from anthropic import Anthropic

            self._client = Anthropic(api_key=settings.anthropic_api_key)
        return self._client

    async def generate(
        self, prompt: str, model: str | None = None, temperature: float = 0.7, max_tokens: int = 1024
    ) -> str:
        """Generate completion via Claude (non-streaming)."""
        try:
            client = self._get_client()
            response = client.messages.create(
                model=model or self.model,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
            )
            return response.content[0].text
        except Exception as e:
            logger.warning(f"Claude generate failed: {e}, trying Z.ai fallback")
            return await self._zai_fallback(prompt, temperature, max_tokens)

    async def _zai_fallback(self, prompt: str, temperature: float, max_tokens: int) -> str:
        """Fallback to Z.ai when Claude is unavailable."""
        if not settings.zai_api_key:
            raise RuntimeError("Both Claude and Z.ai are unavailable")
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.post(
                    f"{settings.zai_base_url.rstrip('/')}/chat/completions",
                    headers={"Authorization": f"Bearer {settings.zai_api_key}"},
                    json={
                        "model": settings.zai_model,
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                    },
                )
                response.raise_for_status()
                return response.json()["choices"][0]["message"]["content"]
        except Exception as zai_err:
            logger.error(f"Z.ai fallback also failed: {zai_err}")
            raise RuntimeError("Both Claude and Z.ai are unavailable") from zai_err

    async def generate_stream(
        self, prompt: str, model: str | None = None, temperature: float = 0.7
    ) -> AsyncIterator[str]:
        """Generate completion with streaming via Claude."""
        client = self._get_client()
        with client.messages.stream(
            model=model or self.model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
        ) as stream:
            for text in stream.text_stream:
                yield text

    async def chat(self, messages: list, model: str | None = None, temperature: float = 0.7) -> str:
        """Chat completion with message history via Claude."""
        client = self._get_client()
        # Convert from OpenAI-style messages to Anthropic format
        anthropic_messages = []
        for msg in messages:
            if msg.get("role") in ("user", "assistant"):
                anthropic_messages.append({"role": msg["role"], "content": msg["content"]})
        response = client.messages.create(
            model=model or self.model,
            max_tokens=1024,
            messages=anthropic_messages,
            temperature=temperature,
        )
        return response.content[0].text

    async def is_available(self) -> bool:
        """Check if Claude API is reachable."""
        return bool(settings.anthropic_api_key)

    async def list_models(self) -> list:
        """List available models (not applicable for cloud)."""
        return [{"name": self.model, "provider": "anthropic"}]

    async def pull_model(self, model: str) -> bool:
        """No-op for cloud provider."""
        return True


class OllamaClient:
    """Client for local Ollama API — preserved for future GPU deployments."""

    def __init__(self, base_url: str | None = None):
        self.base_url = base_url or os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
        self.default_model = os.getenv("OLLAMA_MODEL", "phi3:mini")

    async def generate(
        self, prompt: str, model: str | None = None, temperature: float = 0.7, max_tokens: int = 2048
    ) -> str:
        """Generate completion (non-streaming)."""
        model = model or self.default_model
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": temperature, "num_predict": max_tokens},
                },
            )
            response.raise_for_status()
            return response.json()["response"]

    async def generate_stream(
        self, prompt: str, model: str | None = None, temperature: float = 0.7
    ) -> AsyncIterator[str]:
        """Generate completion with streaming."""
        model = model or self.default_model
        async with (
            httpx.AsyncClient(timeout=120) as client,
            client.stream(
                "POST",
                f"{self.base_url}/api/generate",
                json={"model": model, "prompt": prompt, "stream": True, "options": {"temperature": temperature}},
            ) as response,
        ):
            async for line in response.aiter_lines():
                if line:
                    data = json.loads(line)
                    if "response" in data:
                        yield data["response"]

    async def chat(self, messages: list, model: str | None = None, temperature: float = 0.7) -> str:
        """Chat completion with message history."""
        model = model or self.default_model
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                f"{self.base_url}/api/chat",
                json={"model": model, "messages": messages, "stream": False, "options": {"temperature": temperature}},
            )
            response.raise_for_status()
            return response.json()["message"]["content"]

    async def is_available(self) -> bool:
        """Check if Ollama is available."""
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(f"{self.base_url}/api/version")
                return response.status_code == 200
        except Exception as e:
            logger.warning(f"Ollama not available: {e}")
            return False

    async def list_models(self) -> list:
        """List available models."""
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(f"{self.base_url}/api/tags")
                return response.json().get("models", [])
        except Exception as e:
            logger.error(f"Failed to list Ollama models: {e}")
            return []

    async def pull_model(self, model: str) -> bool:
        """Pull a model from Ollama library."""
        try:
            async with httpx.AsyncClient(timeout=600) as client:
                response = await client.post(f"{self.base_url}/api/pull", json={"name": model, "stream": False})
                return response.status_code == 200
        except Exception as e:
            logger.error(f"Failed to pull model {model}: {e}")
            return False


# Singleton — CloudLLMClient by default (Anthropic → Z.ai fallback).
# Set USE_OLLAMA=true to use local Ollama (requires GPU for usable speed).
_llm_client = None


def get_ollama_client():
    """Get the active LLM client (CloudLLMClient or OllamaClient).

    Returns CloudLLMClient by default — all callers get Anthropic routing
    without any code changes.  Set USE_OLLAMA=true for local inference.
    """
    global _llm_client
    if _llm_client is None:
        if os.getenv("USE_OLLAMA", "").lower() == "true":
            logger.info("Using local Ollama client (USE_OLLAMA=true)")
            _llm_client = OllamaClient()
        else:
            logger.info("Using CloudLLMClient (Anthropic → Z.ai fallback)")
            _llm_client = CloudLLMClient()
    return _llm_client
