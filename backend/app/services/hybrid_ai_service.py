"""Hybrid AI service routing between cloud providers.

Provider hierarchy (configured via AI_CLOUD_PROVIDER):
  - anthropic: Claude (tool support via native API)
  - openai:    GPT-4.1 (tool support, tiered: nano for Tier 1, mini for Tier 2)
  - zai:       Z.ai GLM (NO tool support — advisory only)
  - xiaomi:    Xiaomi MiMo (NO tool support — advisory only)

Fallback chain: primary → next available cloud provider.
Ollama local inference retained but disabled on CPU-only VPS.
Set USE_OLLAMA=true to re-enable (requires GPU hardware).
"""

import logging
import os
import re
import sys
import time
from collections.abc import AsyncGenerator
from typing import Any

from anthropic import RateLimitError

from app.config.settings import settings
from app.services.claude_service import claude_service
from app.services.openai_service import openai_service
from app.services.popia_consent_guard import should_allow_cloud_processing
from app.services.xiaomi_service import xiaomi_service
from app.services.zai_service import zai_service

# Add sentry tools to path for rate limit tracker
sys.path.insert(0, "$SENTRY_HOME/tools")

logger = logging.getLogger(__name__)


# ============================================================================
# SAFETY-CRITICAL LOCK: Control Actions Require Tool-Capable Provider
# ============================================================================
# Building management systems must FAIL SAFE, not FAIL OPEN.
# Tool-based control actions require Anthropic or OpenAI (NOT Z.ai).

SAFETY_CRITICAL_INTENTS = {
    "control_action",
    "setpoint_change",
    "equipment_override",
    "emergency_stop",
    "reset_fault",
    "valve_control",
    "motor_control",
    "damper_adjustment",
}

# Providers that support function/tool calling
TOOL_CAPABLE_PROVIDERS = {"anthropic", "openai"}


def is_safety_critical_intent(intent: str) -> bool:
    """Check if intent involves equipment control."""
    intent_lower = intent.lower().strip()
    return any(critical in intent_lower for critical in SAFETY_CRITICAL_INTENTS)


class HybridAIService:
    """
    Routes AI requests through cloud providers with automatic fallback.

    Provider support:
      - anthropic: Full tool calling via native Anthropic SDK
      - openai: Full tool calling via OpenAI API (tiered: nano/mini)
      - zai: Advisory only — no tool support

    Fallback chains:
      - anthropic primary → openai → zai
      - openai primary → anthropic → zai
      - zai primary → openai → anthropic
    """

    def __init__(self):
        self.ollama_url = "http://localhost:11434/api/generate"
        self.ollama_models = {"fast": "llama3.2:1b", "balanced": "phi3:mini"}
        self.claude_rate_limited = False
        self.rate_limit_time = 0
        self.cooldown_period = 60

        if os.getenv("TESTING", "").lower() == "true":
            self.rate_tracker = None
        else:
            try:
                from rate_limit_tracker import rate_limit_tracker

                self.rate_tracker = rate_limit_tracker
                logger.info("Using shared rate limit tracker")
            except ImportError:
                logger.warning("Shared rate limit tracker not available, using local tracking")
                self.rate_tracker = None

    def get_active_cloud_provider(self) -> str:
        """Return configured cloud provider."""
        provider = (settings.ai_cloud_provider or "anthropic").strip().lower()
        return provider if provider in {"anthropic", "openai", "zai", "xiaomi"} else "anthropic"

    def get_active_cloud_model(self, tier: int = 2) -> str:
        """Return configured cloud model for active provider.

        For OpenAI, returns tiered model (nano for Tier 1, mini for Tier 2).
        """
        provider = self.get_active_cloud_provider()
        if provider == "openai":
            return openai_service.get_model_for_tier(tier)
        if provider == "zai":
            return settings.zai_model
        if provider == "xiaomi":
            return settings.xiaomi_model
        return settings.claude_model

    def is_cloud_configured(self) -> bool:
        """Check whether active cloud provider credentials are configured."""
        provider = self.get_active_cloud_provider()
        if provider == "openai":
            return openai_service.is_configured()
        if provider == "zai":
            return zai_service.is_configured()
        if provider == "xiaomi":
            return xiaomi_service.is_configured()
        return claude_service.is_configured()

    def provider_supports_tools(self, provider: str | None = None) -> bool:
        """Check if provider supports function/tool calling."""
        return (provider or self.get_active_cloud_provider()) in TOOL_CAPABLE_PROVIDERS

    def is_local_ai_only_mode(self) -> bool:
        """Public helper for endpoints to check local-only effective mode."""
        return self._is_local_ai_only()

    def _is_local_ai_only(self) -> bool:
        """True when cloud LLM usage is disabled or unavailable."""
        return bool(settings.local_ai_only) or not self.is_cloud_configured()

    @staticmethod
    def _is_cloud_allowed_for_subject(data_subject_id: str | None) -> bool:
        """POPIA cross-border gate for cloud provider usage."""
        return should_allow_cloud_processing(data_subject_id)

    def _get_fallback_providers(self, primary: str) -> list[str]:
        """Return ordered fallback providers (excluding the primary)."""
        # Prefer tool-capable providers first, then advisory-only
        all_providers = ["openai", "anthropic", "zai", "xiaomi"]
        return [p for p in all_providers if p != primary]

    def classify_task(self, message: str) -> dict[str, Any]:
        """Classify task complexity and route to cloud provider.

        All tiers route through cloud providers. Tier classification
        is preserved for model selection (OpenAI nano vs mini) and
        cost tracking.
        """
        message_lower = message.lower()
        cloud_provider = self.get_active_cloud_provider()

        # Cost estimates per provider per request
        cost_map = {"anthropic": 0.0105, "openai": 0.002, "zai": 0.0035, "xiaomi": 0.002}
        cloud_cost = cost_map.get(cloud_provider, 0.005)

        if "equipment health" in message_lower:
            tier = 2
            return {
                "provider": cloud_provider,
                "model": self.get_active_cloud_model(tier),
                "reason": "Equipment health analysis",
                "estimated_cost": cloud_cost,
                "tier": tier,
            }

        simple_patterns = [
            r"^what does error code",
            r"^what\'?s? the status of",
            r"^who stocks",
            r"^list (all )?equipment",
            r"^show me",
            r"^get (me )?(the )?health",
            r"^how many",
            r"^(all|every) equipment",
        ]
        if any(re.match(pattern, message_lower) for pattern in simple_patterns):
            tier = 1
            return {
                "provider": cloud_provider,
                "model": self.get_active_cloud_model(tier),
                "reason": "Simple lookup/retrieval",
                "estimated_cost": cloud_cost,
                "tier": tier,
            }

        data_patterns = [
            r"^get ",
            r"^show ",
            r"^list ",
            r"^check ",
            r"^(all|every) (equipment|devices|alerts)",
            r"^health (score|status)",
            r"^temperature",
            r"^alarm",
        ]
        if any(re.search(pattern, message_lower) for pattern in data_patterns):
            tier = 1
            return {
                "provider": cloud_provider,
                "model": self.get_active_cloud_model(tier),
                "reason": "Data query/retrieval",
                "estimated_cost": cloud_cost,
                "tier": tier,
            }

        complex_patterns = [
            r"^why (is|does|are)",
            r"^diagnose",
            r"^analyze",
            r"^recommend",
            r"^optimize",
            r"^predict",
            r"^troubleshoot",
            r"root cause",
            r"^too hot",
            r"^too cold",
            r"^unusual",
            r"what should i do",
            r"help me (understand|decide)",
            r"occupancy",
        ]
        if any(re.search(pattern, message_lower) for pattern in complex_patterns):
            tier = 2
            return {
                "provider": cloud_provider,
                "model": self.get_active_cloud_model(tier),
                "reason": "Complex reasoning required",
                "estimated_cost": cloud_cost,
                "tier": tier,
            }

        control_patterns = [
            r"^turn (on|off)",
            r"^set .* to",
            r"^adjust ",
            r"^change ",
            r"^control ",
            r"^boost",
            r"^lower",
            r"^raise",
        ]
        if any(re.search(pattern, message_lower) for pattern in control_patterns):
            tier = 2
            return {
                "provider": cloud_provider,
                "model": self.get_active_cloud_model(tier),
                "reason": "Control action (safety critical)",
                "estimated_cost": cloud_cost,
                "tier": tier,
            }

        tier = 2
        return {
            "provider": cloud_provider,
            "model": self.get_active_cloud_model(tier),
            "reason": "Default to cloud provider for ambiguous queries",
            "estimated_cost": cloud_cost,
            "tier": tier,
        }

    def _should_use_claude(self) -> tuple[bool, str]:
        """Check if Claude is available (not in cooldown from rate limit)."""
        if self.rate_tracker:
            return self.rate_tracker.should_use_claude()

        if not self.claude_rate_limited:
            return True, "Claude available"

        time_since_limit = time.time() - self.rate_limit_time
        if time_since_limit > self.cooldown_period:
            logger.info("Rate limit cooldown expired, attempting Claude again")
            self.claude_rate_limited = False
            return True, "Cooldown expired"

        remaining = int(self.cooldown_period - time_since_limit)
        logger.info("Claude in cooldown for %ss more", remaining)
        return False, f"Claude in cooldown for {remaining}s"

    async def query_ollama(
        self,
        message: str,
        model: str = "llama3.2:1b",
        escalate_on_fail: bool = True,
        data_subject_id: str | None = None,
    ) -> str:
        """Query local Ollama model."""
        import httpx

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    self.ollama_url,
                    json={
                        "model": model,
                        "prompt": message,
                        "stream": False,
                        "options": {"num_predict": 500, "temperature": 0.5},
                    },
                )
                response.raise_for_status()
                result = response.json()
                return result.get("response", "")
        except Exception as e:
            logger.error("Ollama query failed: %s", e)
            if (
                escalate_on_fail
                and not self._is_local_ai_only()
                and self._is_cloud_allowed_for_subject(data_subject_id)
            ):
                logger.info("Escalating to cloud provider due to Ollama failure")
                return await self._query_cloud_fallback(message, data_subject_id=data_subject_id)
            raise

    async def _query_cloud_fallback(self, message: str, data_subject_id: str | None = None) -> str:
        """Fallback from Ollama to active cloud provider."""
        if self._is_local_ai_only() or not self._is_cloud_allowed_for_subject(data_subject_id):
            return "Local AI only mode is active. Cloud fallback is disabled."

        provider = self.get_active_cloud_provider()
        try:
            chunks: list[str] = []
            async for chunk in self._stream_from_provider(
                provider,
                [{"role": "user", "content": message}],
                include_site_context=False,
            ):
                chunks.append(chunk)
            return "".join(chunks)
        except Exception as e:
            logger.error("Cloud fallback also failed (%s): %s", provider, e)
            return "I'm sorry, I'm having trouble processing your request right now. Please try again."

    async def _stream_from_provider(
        self,
        provider: str,
        messages: list[dict],
        include_site_context: bool = True,
        tier: int = 2,
        source: str = "chat",
    ) -> AsyncGenerator[str, None]:
        """Stream response from a specific provider."""
        if provider == "openai":
            async for chunk in openai_service.stream_response(
                messages,
                include_site_context=include_site_context,
                tier=tier,
                source=source,
            ):
                yield chunk
        elif provider == "zai":
            async for chunk in zai_service.stream_response(
                messages,
                include_site_context=include_site_context,
                source=source,
            ):
                yield chunk
        elif provider == "xiaomi":
            async for chunk in xiaomi_service.stream_response(
                messages,
                include_site_context=include_site_context,
                source=source,
            ):
                yield chunk
        else:  # anthropic
            async for chunk in claude_service.stream_response(
                messages,
                include_site_context=include_site_context,
                source=source,
            ):
                yield chunk

    async def _try_cloud_with_fallback(
        self,
        message: str,
        include_site_context: bool = True,
        data_subject_id: str | None = None,
        tier: int = 2,
        source: str = "chat",
    ) -> AsyncGenerator[str, None]:
        """Try primary provider, fallback to alternatives on failure."""
        provider = self.get_active_cloud_provider()
        messages = [{"role": "user", "content": message}]

        # Try primary
        try:
            if provider == "anthropic" and self.rate_tracker:
                self.rate_tracker.record_request()
            async for chunk in self._stream_from_provider(
                provider,
                messages,
                include_site_context,
                tier,
                source,
            ):
                yield chunk
            return
        except RateLimitError as e:
            logger.warning("%s rate limited: %s — trying fallback", provider, e)
            if provider == "anthropic":
                if self.rate_tracker:
                    self.rate_tracker.record_rate_limit_hit()
                else:
                    self.claude_rate_limited = True
                    self.rate_limit_time = time.time()
        except Exception as e:
            logger.error("%s error (%s): %s — trying fallback", provider, type(e).__name__, e)

        # Try fallbacks in order
        for fallback in self._get_fallback_providers(provider):
            try:
                async for chunk in self._stream_from_provider(
                    fallback,
                    messages,
                    include_site_context,
                    tier,
                    source,
                ):
                    yield chunk
                return
            except Exception as fb_err:
                logger.error("%s fallback also failed: %s", fallback, fb_err)

        yield "I'm having trouble with all AI services. Please try again in a moment."

    async def _stream_tools_from_provider(
        self,
        provider: str,
        messages: list[dict],
    ) -> AsyncGenerator[str, None]:
        """Stream tool-calling response from a tool-capable provider."""
        if provider == "openai":
            from app.services.chat_tools import execute_tool, get_chat_tools

            tools = get_chat_tools()

            async def _executor(name: str, args: dict) -> Any:
                return await execute_tool(name, args)

            async for chunk in openai_service.stream_response_with_tools(
                messages,
                tools=tools,
                tool_executor=_executor,
            ):
                yield chunk
        else:  # anthropic
            async for chunk in claude_service.stream_response_with_tools(messages):
                yield chunk

    async def stream_response(
        self,
        message: str,
        use_tools: bool = False,
        data_subject_id: str | None = None,
        source: str = "chat",
    ) -> AsyncGenerator[str, None]:
        """Stream response from configured cloud provider with fallback.

        For tool-calling requests, routes to a tool-capable provider
        (anthropic or openai). Z.ai does not support tools.
        """
        provider = self.get_active_cloud_provider()

        # Tool requests need a tool-capable provider
        if use_tools and not self.provider_supports_tools(provider):
            # Try to find a tool-capable fallback
            tool_provider = None
            for p in TOOL_CAPABLE_PROVIDERS:
                if p == "openai" and openai_service.is_configured():
                    tool_provider = p
                    break
                if p == "anthropic" and claude_service.is_configured():
                    tool_provider = p
                    break

            if not tool_provider:
                yield (
                    f"[{provider} cloud mode] Tool-based actions require a tool-capable "
                    "provider (OpenAI or Claude). Please configure one or use advisory queries only."
                )
                return

            logger.info(
                "Primary provider %s lacks tool support, routing tools to %s",
                provider,
                tool_provider,
            )
            provider = tool_provider

        routing = self.classify_task(message)

        logger.info(
            "Routing decision: provider=%s, model=%s, reason=%s, tier=%s",
            routing["provider"],
            routing["model"],
            routing["reason"],
            routing["tier"],
        )

        if use_tools:
            # For Claude, check rate limit cooldown
            if provider == "anthropic":
                can_use_claude, reason = self._should_use_claude()
                if not can_use_claude:
                    # Try OpenAI as tool-capable fallback
                    if openai_service.is_configured():
                        logger.info("Claude unavailable (%s), using OpenAI for tools", reason)
                        provider = "openai"
                    else:
                        yield (
                            f"[Claude unavailable: {reason}] Tool-based actions are "
                            "not available right now. Please try again in a moment."
                        )
                        return

            logger.info("Tool calling enabled, using %s", provider)
            try:
                if provider == "anthropic" and self.rate_tracker:
                    self.rate_tracker.record_request()
                async for chunk in self._stream_tools_from_provider(
                    provider,
                    [{"role": "user", "content": message}],
                ):
                    yield chunk
                return
            except RateLimitError as e:
                logger.warning("Rate limit hit during tool calling: %s", e)
                if provider == "anthropic":
                    if self.rate_tracker:
                        self.rate_tracker.record_rate_limit_hit()
                    else:
                        self.claude_rate_limited = True
                        self.rate_limit_time = time.time()
                    # Try OpenAI as fallback for tools
                    if openai_service.is_configured():
                        try:
                            async for chunk in self._stream_tools_from_provider(
                                "openai",
                                [{"role": "user", "content": message}],
                            ):
                                yield chunk
                            return
                        except Exception as oai_err:
                            logger.error("OpenAI tool fallback also failed: %s", oai_err)
                yield "[Rate limited] Cannot perform tool-based actions right now. Please try a simpler query."
                return
            except Exception as e:
                from anthropic import APIConnectionError, APIError, APITimeoutError

                error_type = type(e).__name__
                logger.error("API error during tool calling (%s): %s", error_type, e)
                if isinstance(e, (APIError, APIConnectionError, APITimeoutError)):
                    # Try other tool-capable provider
                    alt_provider = "openai" if provider == "anthropic" else "anthropic"
                    alt_configured = (
                        openai_service.is_configured() if alt_provider == "openai" else claude_service.is_configured()
                    )
                    if alt_configured:
                        try:
                            async for chunk in self._stream_tools_from_provider(
                                alt_provider,
                                [{"role": "user", "content": message}],
                            ):
                                yield chunk
                            return
                        except Exception as alt_err:
                            logger.error("%s tool fallback also failed: %s", alt_provider, alt_err)
                    yield (
                        f"[AI unavailable ({error_type})] Tool-based actions "
                        "are temporarily unavailable. Please try again in a moment."
                    )
                    return
                raise

        # Non-tool path: primary → fallback chain
        logger.info("Using cloud provider with fallback: %s", routing["provider"])
        async for chunk in self._try_cloud_with_fallback(
            message,
            include_site_context=True,
            data_subject_id=data_subject_id,
            tier=routing.get("tier", 2),
                    source=source,
        ):
            yield chunk


hybrid_ai_service = HybridAIService()
