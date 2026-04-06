"""Text-to-Speech service using ElevenLabs API.

Provides voice output for chat responses:
1. Summarizes long AI responses to 1-2 sentences via Claude
2. Synthesizes speech audio via ElevenLabs
3. Caches audio in Redis to avoid duplicate API calls

Usage:
    from app.services.tts_service import get_tts_service

    tts = get_tts_service()
    if tts.is_configured():
        audio_bytes = await tts.text_to_speech("Full AI response text here...")
        # Returns MP3 bytes or None on failure
"""

import hashlib
import logging
import re
from base64 import b64decode, b64encode

import httpx

from app.config.settings import settings
from app.services.cache_service import cache

logger = logging.getLogger(__name__)

# Cache TTL for synthesized audio (1 hour)
TTS_CACHE_TTL = 3600


class TTSService:
    """ElevenLabs text-to-speech with Claude summarization."""

    ELEVENLABS_BASE_URL = "https://api.elevenlabs.io"

    def is_configured(self) -> bool:
        """Check if TTS is enabled and has required credentials."""
        return bool(settings.elevenlabs_tts_enabled and settings.elevenlabs_api_key)

    async def summarize_for_speech(self, text: str) -> str:
        """Summarize text to 1-2 sentences suitable for speech.

        Short texts (<200 chars after markdown stripping) are passed through directly.
        Longer texts are summarized via Claude to keep audio brief and natural.

        Args:
            text: Full AI response text (may contain markdown)

        Returns:
            1-2 sentence summary suitable for TTS
        """
        # Strip markdown formatting for length check
        plain = re.sub(r"[#*_`\[\]()>~|]", "", text).strip()
        plain = re.sub(r"\n{2,}", " ", plain)
        plain = re.sub(r"\n", " ", plain)
        plain = re.sub(r"\s{2,}", " ", plain)

        if len(plain) < 200:
            return plain

        # Use Claude to summarize
        try:
            from anthropic import AsyncAnthropic

            client = AsyncAnthropic(api_key=settings.anthropic_api_key)
            response = await client.messages.create(
                model=settings.claude_model,
                max_tokens=150,
                system="You are a concise summarizer. Summarize the following text into exactly 1-2 spoken sentences. "
                "The summary will be read aloud, so make it natural and conversational. "
                "Do not use markdown, bullet points, or special formatting. "
                "Focus on the most important actionable information.",
                messages=[{"role": "user", "content": text}],
            )
            summary = response.content[0].text.strip()
            return summary
        except Exception as e:
            logger.warning(f"Claude summarization failed, using truncated text: {e}")
            # Fallback: first 2 sentences
            sentences = re.split(r"(?<=[.!?])\s+", plain)
            return " ".join(sentences[:2])

    async def synthesize(self, text: str) -> bytes | None:
        """Synthesize speech audio from text via ElevenLabs.

        Args:
            text: Text to convert to speech (should be short, 1-2 sentences)

        Returns:
            MP3 audio bytes or None on failure
        """
        if not self.is_configured():
            return None

        url = f"{self.ELEVENLABS_BASE_URL}/v1/text-to-speech/{settings.elevenlabs_voice_id}"

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    url,
                    headers={
                        "xi-api-key": settings.elevenlabs_api_key,
                        "Content-Type": "application/json",
                        "Accept": "audio/mpeg",
                    },
                    json={
                        "text": text,
                        "model_id": settings.elevenlabs_model_id,
                        "voice_settings": {
                            "stability": 0.5,
                            "similarity_boost": 0.75,
                        },
                    },
                )
                response.raise_for_status()

                try:
                    from app.services.ai_usage_tracker import usage_tracker

                    usage_tracker.record_service("elevenlabs", units=len(text), unit_type="chars", source="tts")
                except Exception:
                    pass

                return response.content
        except httpx.HTTPStatusError as e:
            logger.error(f"ElevenLabs API error {e.response.status_code}: {e.response.text[:200]}")
            return None
        except Exception as e:
            logger.error(f"ElevenLabs synthesis failed: {e}")
            return None

    async def text_to_speech(self, full_response: str) -> bytes | None:
        """Full pipeline: summarize text, check cache, synthesize audio.

        Args:
            full_response: Full AI response text

        Returns:
            MP3 audio bytes or None on failure
        """
        if not self.is_configured():
            return None

        # Check cache first (keyed by content hash)
        content_hash = hashlib.sha256(full_response.encode()).hexdigest()[:16]
        cache_key = f"tts:audio:{content_hash}"

        cached = cache.get(cache_key)
        if cached:
            logger.debug(f"TTS cache hit for {cache_key}")
            try:
                return b64decode(cached)
            except Exception:
                logger.warning("Failed to decode cached TTS audio, regenerating")

        # Summarize then synthesize
        summary = await self.summarize_for_speech(full_response)
        if not summary:
            return None

        audio = await self.synthesize(summary)
        if not audio:
            return None

        # Cache the audio as base64
        try:
            cache.set(cache_key, b64encode(audio).decode(), ttl=TTS_CACHE_TTL)
        except Exception as e:
            logger.debug(f"Failed to cache TTS audio: {e}")

        return audio


# Singleton
_tts_service: TTSService | None = None


def get_tts_service() -> TTSService:
    """Get or create singleton TTSService instance."""
    global _tts_service
    if _tts_service is None:
        _tts_service = TTSService()
    return _tts_service
