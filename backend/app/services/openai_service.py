"""OpenAI cloud LLM service with tool calling support.

Provides tiered model routing:
  - Tier 1 (routine queries): gpt-4.1-nano (fast, cheap)
  - Tier 2 (complex reasoning): gpt-4.1-mini (capable, tools)

Unlike Z.ai, OpenAI natively supports function/tool calling, making it
suitable for safety-critical BMS control actions.
"""

import json
import logging
import re
from collections.abc import AsyncGenerator
from typing import Any

import httpx

from app.config.settings import settings
from app.services.claude_service import build_system_prompt_with_context

logger = logging.getLogger(__name__)

# OpenAI system prompt — tool-aware, same BMS domain expertise as Claude.
OPENAI_SYSTEM_PROMPT_BASE = """\
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
- Report numbers EXACTLY as provided — do not round, estimate, or adjust."""


def _build_openai_system_prompt(include_site_context: bool = True) -> str:
    """Build an OpenAI-compatible system prompt with building context."""
    if not include_site_context:
        return OPENAI_SYSTEM_PROMPT_BASE

    try:
        full_context = build_system_prompt_with_context()
        parts = full_context.split("---", 1)
        if len(parts) > 1:
            context_and_rest = parts[1]
            # Strip Claude-specific tool references from context
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
            return f"{OPENAI_SYSTEM_PROMPT_BASE}\n\n---\n{context_and_rest}"
        else:
            return OPENAI_SYSTEM_PROMPT_BASE
    except Exception as e:
        logger.warning("Could not build OpenAI context prompt: %s", e)
        return OPENAI_SYSTEM_PROMPT_BASE


def _convert_tools_to_openai_format(anthropic_tools: list[dict]) -> list[dict]:
    """Convert Anthropic tool definitions to OpenAI function calling format.

    Anthropic format:
        {"name": "foo", "description": "...", "input_schema": {...}}
    OpenAI format:
        {"type": "function", "function": {"name": "foo", "description": "...", "parameters": {...}}}
    """
    openai_tools = []
    for tool in anthropic_tools:
        openai_tool = {
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool.get("description", ""),
                "parameters": tool.get("input_schema", {"type": "object", "properties": {}}),
            },
        }
        # Remove cache_control if present (Anthropic-specific)
        openai_tool["function"].pop("cache_control", None)
        openai_tools.append(openai_tool)
    return openai_tools


class OpenAIService:
    """Service for interacting with OpenAI chat completion API.

    Supports both standard chat completions and function/tool calling.
    Uses tiered models: nano for routine, mini for complex.
    """

    def __init__(self):
        self._api_key = settings.openai_api_key
        self._model = settings.openai_model  # Tier 1: gpt-4.1-nano
        self._model_heavy = settings.openai_model_heavy  # Tier 2: gpt-4.1-mini
        self._base_url = settings.openai_base_url.rstrip("/")

    def is_configured(self) -> bool:
        """Check if the service is properly configured."""
        return bool(self._api_key)

    def get_model_for_tier(self, tier: int) -> str:
        """Return appropriate model for the given routing tier."""
        if tier >= 2:
            return self._model_heavy
        return self._model

    @staticmethod
    def _extract_text_content(message_content) -> str:
        """Normalize OpenAI message content to plain text."""
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
        tier: int = 1,
        model_override: str | None = None,
        source: str = "chat",
        site_id: str | None = None,
    ) -> AsyncGenerator[str, None]:
        """Return a chat completion from OpenAI as a single yielded chunk.

        Args:
            messages: Conversation messages.
            system_prompt: Optional override for system prompt.
            include_site_context: Include BMS data in system prompt.
            tier: Routing tier (1=nano, 2=mini).
        """
        if not self._api_key:
            raise ValueError("OPENAI_API_KEY not configured. Set it in .env or environment variables.")

        system = system_prompt or _build_openai_system_prompt(include_site_context)
        model = self.get_model_for_tier(tier)

        openai_messages = [{"role": "system", "content": system}]
        openai_messages.extend(messages)

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
                raise ValueError("Invalid OPENAI_API_KEY. Please check your API key configuration.")
            if response.status_code == 429:
                raise Exception("OpenAI API rate limit exceeded. Please try again in a moment.")

            response.raise_for_status()
            body = response.json()

            # Track token usage (simple path)
            try:
                from app.services.ai_usage_tracker import usage_tracker

                u = body.get("usage", {})
                usage_tracker.record(
                    provider="openai",
                    model=model,
                    input_tokens=u.get("prompt_tokens", 0),
                    output_tokens=u.get("completion_tokens", 0),
                    source=source,
                    feature="tool_dispatcher",
                    site_id=site_id or "unknown",
                )
            except Exception:
                pass

            choices = body.get("choices", [])
            if not choices:
                raise Exception("OpenAI response did not include any choices.")

            message = choices[0].get("message", {})
            content = self._extract_text_content(message.get("content"))
            yield content or "I could not generate a response from OpenAI."

        except ValueError:
            raise
        except httpx.HTTPStatusError as e:
            logger.error("OpenAI HTTP error: %s", e)
            raise Exception(f"OpenAI API error: HTTP {e.response.status_code}") from e
        except Exception as e:
            logger.error("Unexpected error in OpenAI service: %s", e)
            raise

    async def stream_response_with_tools(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        tool_executor: Any = None,
        system_prompt: str | None = None,
        include_site_context: bool = True,
        tier: int = 2,
        source: str = "tools",
        site_id: str | None = None,
    ) -> AsyncGenerator[str, None]:
        """Chat completion with iterative tool calling.

        Mirrors Claude's tool loop: call model → execute tools → feed results back → repeat.

        Args:
            messages: Conversation messages.
            tools: Anthropic-format tool definitions (auto-converted to OpenAI format).
            tool_executor: Async callable(name, args) -> result.
            system_prompt: Optional override.
            include_site_context: Include BMS data in prompt.
            tier: Routing tier (uses heavy model for tool calls).
        """
        if not self._api_key:
            raise ValueError("OPENAI_API_KEY not configured.")

        system = system_prompt or _build_openai_system_prompt(include_site_context)
        model = self.get_model_for_tier(tier)

        openai_messages = [{"role": "system", "content": system}]
        openai_messages.extend(messages)

        openai_tools = _convert_tools_to_openai_format(tools) if tools else []

        url = f"{self._base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        max_iterations = 10
        for _iteration in range(max_iterations):
            payload: dict[str, Any] = {
                "model": model,
                "messages": openai_messages,
                "temperature": 0.3,
                "stream": False,
            }
            if openai_tools:
                payload["tools"] = openai_tools

            async with httpx.AsyncClient(timeout=90.0) as client:
                response = await client.post(url, headers=headers, json=payload)

            if response.status_code == 429:
                raise Exception("OpenAI API rate limit exceeded.")
            response.raise_for_status()

            body = response.json()

            # Track token usage (tool-calling path)
            try:
                from app.services.ai_usage_tracker import usage_tracker

                u = body.get("usage", {})
                usage_tracker.record(
                    provider="openai",
                    model=model,
                    input_tokens=u.get("prompt_tokens", 0),
                    output_tokens=u.get("completion_tokens", 0),
                    source=source,
                    feature="tool_dispatcher",
                    site_id=site_id or "unknown",
                )
            except Exception:
                pass

            choices = body.get("choices", [])
            if not choices:
                yield "No response from OpenAI."
                return

            choice = choices[0]
            message = choice.get("message", {})
            finish_reason = choice.get("finish_reason", "stop")

            # Yield any text content
            text_content = self._extract_text_content(message.get("content"))
            if text_content:
                yield text_content

            # Check for tool calls
            tool_calls = message.get("tool_calls", [])
            if finish_reason == "tool_calls" or tool_calls:
                if not tool_executor:
                    logger.warning("Tool calls requested but no executor provided")
                    yield "\n[Tool calling requested but not available in this context]"
                    return

                # Append assistant message with tool calls
                openai_messages.append(message)

                # Execute each tool call and append results
                for tc in tool_calls:
                    func = tc.get("function", {})
                    tool_name = func.get("name", "")
                    try:
                        tool_args = json.loads(func.get("arguments", "{}"))
                    except json.JSONDecodeError:
                        tool_args = {}

                    logger.info("Executing tool: %s with args: %s", tool_name, tool_args)
                    try:
                        result = await tool_executor(tool_name, tool_args)
                        result_str = json.dumps(result) if not isinstance(result, str) else result
                    except Exception as e:
                        logger.error("Tool %s failed: %s", tool_name, e)
                        result_str = json.dumps({"error": str(e)})

                    openai_messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.get("id", ""),
                            "content": result_str,
                        }
                    )

                # Continue the loop to get the model's response after tool execution
                continue

            # No tool calls — done
            return

        yield "\n[Max tool iterations reached]"


openai_service = OpenAIService()
