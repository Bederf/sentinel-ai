"""Z.ai cloud LLM service (OpenAI-compatible chat completions)."""

import logging
import re
from collections.abc import AsyncGenerator

import httpx

from app.config.settings import settings
from app.services.claude_service import build_system_prompt_with_context

logger = logging.getLogger(__name__)

# Z.ai-specific system prompt — no tool-calling instructions.
# Z.ai models don't support native tool calling, so the prompt instructs
# the model to answer directly from the embedded building context data.
ZAI_SYSTEM_PROMPT_BASE = """\
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


def _build_zai_system_prompt(include_site_context: bool = True) -> str:
    """Build a Z.ai-compatible system prompt with building context.

    Takes the full context from build_system_prompt_with_context() but replaces
    the Claude-specific FM_SYSTEM_PROMPT_BASE (which contains tool instructions)
    with ZAI_SYSTEM_PROMPT_BASE (which tells the model to answer directly).
    """
    if not include_site_context:
        return ZAI_SYSTEM_PROMPT_BASE

    try:
        full_context = build_system_prompt_with_context()

        # The context prompt is structured as:
        #   FM_SYSTEM_PROMPT_BASE + "---" + context_data + "---" + citations
        # We want to keep the context data but replace the base prompt.
        # Split on the first "---" separator to extract context sections.
        parts = full_context.split("---", 1)
        if len(parts) > 1:
            context_and_rest = parts[1]
            # Strip any remaining tool-call references from context
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
            return f"{ZAI_SYSTEM_PROMPT_BASE}\n\n---\n{context_and_rest}"
        else:
            return ZAI_SYSTEM_PROMPT_BASE
    except Exception as e:
        logger.warning(f"Could not build Z.ai context prompt: {e}")
        return ZAI_SYSTEM_PROMPT_BASE


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
        include_site_context: bool = True,
        model_override: str | None = None,
        source: str = "chat",
        site_id: str | None = None,
    ) -> AsyncGenerator[str, None]:
        """Return a completion from Z.ai as a single streamed chunk."""
        if not self._api_key:
            raise ValueError("ZAI_API_KEY not configured. Set it in .env or environment variables.")

        if system_prompt:
            system = system_prompt
        else:
            system = _build_zai_system_prompt(include_site_context)

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

            # Track Z.ai token usage
            try:
                from app.services.ai_usage_tracker import usage_tracker

                u = body.get("usage", {})
                usage_tracker.record(
                    provider="zhipuai",
                    model=self._model,
                    input_tokens=u.get("prompt_tokens", 0),
                    output_tokens=u.get("completion_tokens", 0),
                    source=source,
                    site_id=site_id or "unknown",
                )
            except Exception:
                pass  # Never let tracking break chat

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
