"""Ollama client for local LLM inference."""

import httpx
import os
import json
import logging
from typing import Optional, AsyncIterator

logger = logging.getLogger(__name__)


class OllamaClient:
    """Client for Ollama API."""

    def __init__(self, base_url: Optional[str] = None):
        self.base_url = base_url or os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
        self.default_model = os.getenv("OLLAMA_MODEL", "phi3:mini")

    async def generate(
        self, prompt: str, model: Optional[str] = None, temperature: float = 0.7, max_tokens: int = 2048
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
        self, prompt: str, model: Optional[str] = None, temperature: float = 0.7
    ) -> AsyncIterator[str]:
        """Generate completion with streaming."""
        model = model or self.default_model

        async with httpx.AsyncClient(timeout=120) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/api/generate",
                json={"model": model, "prompt": prompt, "stream": True, "options": {"temperature": temperature}},
            ) as response:
                async for line in response.aiter_lines():
                    if line:
                        data = json.loads(line)
                        if "response" in data:
                            yield data["response"]

    async def chat(self, messages: list, model: Optional[str] = None, temperature: float = 0.7) -> str:
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


# Singleton
_ollama_client = None


def get_ollama_client() -> OllamaClient:
    """Get singleton Ollama client instance."""
    global _ollama_client
    if _ollama_client is None:
        _ollama_client = OllamaClient()
    return _ollama_client
