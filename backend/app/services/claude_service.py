"""Claude AI service for building management intelligence."""

import logging
from typing import AsyncGenerator

from anthropic import Anthropic, APIError, AuthenticationError, RateLimitError

from app.config.settings import settings

logger = logging.getLogger(__name__)

# FM-focused system prompt for building management intelligence
FM_SYSTEM_PROMPT = """You are an AI assistant specializing in Facilities Management (FM) and Building Management Systems (BMS). You help building managers, maintenance technicians, and FM professionals monitor and manage their buildings effectively.

Your expertise includes:
- HVAC systems (heating, ventilation, air conditioning)
- UPS (Uninterruptible Power Supply) systems
- Electrical systems and generators
- Building sensors and IoT devices
- Energy efficiency and sustainability
- Preventive maintenance best practices
- Anomaly detection and predictive maintenance
- Regulatory compliance (SANS, OHS Act, SABS standards for South Africa)

When discussing building data:
- Reference specific sites, equipment, and sensors when available
- Provide actionable recommendations based on sensor readings
- Highlight potential issues and suggest maintenance priorities
- Use South African terminology and standards where appropriate
- Be concise but thorough in technical explanations

Always be helpful, professional, and safety-conscious. If you identify a critical issue, emphasize the urgency appropriately."""


class ClaudeService:
    """Service for interacting with Claude AI."""

    def __init__(self):
        """Initialize Claude service with API configuration."""
        self._client: Anthropic | None = None
        self._api_key = settings.anthropic_api_key
        self._model = settings.claude_model
        self._max_tokens = settings.claude_max_tokens

    @property
    def client(self) -> Anthropic:
        """Get or create Anthropic client (lazy initialization)."""
        if self._client is None:
            if not self._api_key:
                raise ValueError(
                    "ANTHROPIC_API_KEY not configured. "
                    "Set it in .env or environment variables."
                )
            self._client = Anthropic(api_key=self._api_key)
        return self._client

    async def stream_response(
        self,
        messages: list[dict],
        system_prompt: str | None = None,
    ) -> AsyncGenerator[str, None]:
        """
        Stream a response from Claude.

        Args:
            messages: List of message dicts with 'role' and 'content'
            system_prompt: Optional custom system prompt (defaults to FM prompt)

        Yields:
            Text chunks as they arrive from Claude

        Raises:
            ValueError: If API key is not configured
            Exception: For API errors with descriptive messages
        """
        system = system_prompt or FM_SYSTEM_PROMPT

        try:
            # Use streaming with the messages API
            with self.client.messages.stream(
                model=self._model,
                max_tokens=self._max_tokens,
                system=system,
                messages=messages,
            ) as stream:
                for text in stream.text_stream:
                    yield text

        except AuthenticationError as e:
            logger.error(f"Claude authentication error: {e}")
            raise ValueError(
                "Invalid ANTHROPIC_API_KEY. Please check your API key configuration."
            ) from e

        except RateLimitError as e:
            logger.warning(f"Claude rate limit hit: {e}")
            raise Exception(
                "Claude API rate limit exceeded. Please try again in a moment."
            ) from e

        except APIError as e:
            logger.error(f"Claude API error: {e}")
            raise Exception(f"Claude API error: {e.message}") from e

        except Exception as e:
            logger.error(f"Unexpected error in Claude service: {e}")
            raise

    def is_configured(self) -> bool:
        """Check if the service is properly configured."""
        return bool(self._api_key)


# Module-level service instance for dependency injection
claude_service = ClaudeService()
