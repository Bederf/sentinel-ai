"""Xiaomi MiMo cloud LLM service (OpenAI-compatible chat completions)."""

import logging
import re
from collections.abc import AsyncGenerator

import httpx

from app.config.settings import settings
from app.services.claude_service import build_system_prompt_with_context

logger = logging.getLogger(__name__)

# MiMo-specific system prompt — no tool-calling instructions.
# MiMo models don't support native tool calling, so the prompt instructs
# the model to answer directly from the embedded building context data.
XIAOMI_SYSTEM_PROMPT_BASE = """\
You are SENTINEL — an AI-powered Building Management System intelligence layer.
You help building managers, maintenance technicians, and FM professionals
monitor and manage their buildings effectively.

Your expertise includes:
- HVAC systems (heating, ventilation, air conditioning)
- UPS (Uninterruptible Power Supply) systems
- Electrical systems and generators
- Building sensors and IoT devices
- Energy efficiency and sustainability
- Preventive maintenance best practices
- Anomaly detection and predictive maintenance

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
- Report numbers EXACTLY as provided — do not round, estimate, or adjust.
- NEVER generate tool calls, function calls, or code blocks pretending to call tools.
  You do NOT have tools. Answer directly from the context data below."""


def _build_xiaomi_system_prompt(include_site_context: bool = True) -> str:
    """Build a MiMo-compatible system prompt with building context."""
    if not include_site_context:
        return XIAOMI_SYSTEM_PROMPT_BASE

    try:
        full_context = build_system_prompt_with_context()

        parts = full_context.split("---", 1)
        if len(parts) > 1:
            context_and_rest = parts[1]
            context_and_rest = re.sub(
                r"(?:Use your tools|use tools|tool calls?|get_system_status|"
                r"get_equipment_health|get_alerts_and_anomalies|get_energy_analysis|"
                r"get_optimization_recommendations|list_devices|get_device_details|"
                r"control_device|search_documents|adjust_setpoint|create_work_order|"
                r"approve_recommendation|reject_recommendation|reset_equipment_fault)"
                r"[^.]*\.",
                "",
                context_and_rest,
                flags=re.IGNORECASE,
            )
            return f"{XIAOMI_SYSTEM_PROMPT_BASE}\n\n---\n{context_and_rest}"
        else:
            return XIAOMI_SYSTEM_PROMPT_BASE
    except Exception as e:
        logger.warning(f"Could not build MiMo context prompt: {e}")
        return XIAOMI_SYSTEM_PROMPT_BASE


class XiaomiService:
    """Service for interacting with Xiaomi MiMo chat completion API."""

    def __init__(self):
        self._api_key = settings.xiaomi_api_key
        self._model = settings.xiaomi_model
        self._base_url = settings.xiaomi_base_url.rstrip("/")

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
        include_site_context: bool = True,
        model_override: str | None = None,
        source: str = "chat",
    ) -> AsyncGenerator[str, None]:
        """Return a completion from Xiaomi MiMo as a single streamed chunk."""
        if not self._api_key:
            raise ValueError("XIAOMI_API_KEY not configured. Set it in .env or environment variables.")

        if system_prompt:
            system = system_prompt
        else:
            system = _build_xiaomi_system_prompt(include_site_context)

        openai_messages = [{"role": "system", "content": system}]
        openai_messages.extend(messages)

        model = model_override or self._model
        url = f"{self._base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "messages": openai_messages,
            "temperature": 0.3,
            "stream": False,
        }

        try:
            async with httpx.AsyncClient(timeout=90.0) as client:
                response = await client.post(url, headers=headers, json=payload)

            if response.status_code == 401:
                raise ValueError("Invalid XIAOMI_API_KEY. Please check your API key configuration.")
            if response.status_code == 429:
                raise Exception("Xiaomi MiMo API rate limit exceeded. Please try again in a moment.")

            response.raise_for_status()
            body = response.json()
            choices = body.get("choices", [])
            if not choices:
                raise Exception("Xiaomi MiMo response did not include any choices.")

            # Track MiMo token usage
            try:
                from app.services.ai_usage_tracker import usage_tracker

                u = body.get("usage", {})
                usage_tracker.record(
                    provider="xiaomi",
                    model=model,
                    input_tokens=u.get("prompt_tokens", 0),
                    output_tokens=u.get("completion_tokens", 0),
                    source=source,
                )
            except Exception:
                pass  # Never let tracking break chat

            message = choices[0].get("message", {})
            content = self._extract_text_content(message.get("content"))
            yield content or "I could not generate a response from Xiaomi MiMo."

        except ValueError:
            raise
        except httpx.HTTPStatusError as e:
            logger.error("Xiaomi MiMo HTTP error: %s", e)
            raise Exception(f"Xiaomi MiMo API error: HTTP {e.response.status_code}") from e
        except Exception as e:
            logger.error("Unexpected error in Xiaomi MiMo service: %s", e)
            raise


xiaomi_service = XiaomiService()
