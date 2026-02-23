"""Hybrid AI service routing between local Ollama and cloud providers."""

import logging
import os
import re
import sys
import time
from typing import Any, AsyncGenerator

from anthropic import RateLimitError

from app.config.settings import settings
from app.services.claude_service import claude_service
from app.services.zai_service import zai_service
from app.services.popia_consent_guard import should_allow_cloud_processing

# Add sentry tools to path for rate limit tracker
sys.path.insert(0, "$SENTRY_HOME/tools")

logger = logging.getLogger(__name__)


# ============================================================================
# SAFETY-CRITICAL LOCK: Control Actions Must Use Claude Only
# ============================================================================
# Building management systems must FAIL SAFE, not FAIL OPEN.
# Tool-based control actions are only enabled on Anthropic/Claude flow.

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


def is_safety_critical_intent(intent: str) -> bool:
    """Check if intent involves equipment control."""
    intent_lower = intent.lower().strip()
    return any(critical in intent_lower for critical in SAFETY_CRITICAL_INTENTS)


class HybridAIService:
    """
    Routes AI requests to local Ollama or configured cloud provider.

    - Tier 1/simple tasks -> Ollama
    - Tier 2/complex tasks -> active cloud provider
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
        return provider if provider in {"anthropic", "zai"} else "anthropic"

    def get_active_cloud_model(self) -> str:
        """Return configured cloud model for active provider."""
        if self.get_active_cloud_provider() == "zai":
            return settings.zai_model
        return settings.claude_model

    def is_cloud_configured(self) -> bool:
        """Check whether active cloud provider credentials are configured."""
        provider = self.get_active_cloud_provider()
        if provider == "zai":
            return zai_service.is_configured()
        return claude_service.is_configured()

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

    def classify_task(self, message: str) -> dict[str, Any]:
        """Classify task complexity and route to provider/model."""
        message_lower = message.lower()
        cloud_provider = self.get_active_cloud_provider()
        cloud_model = self.get_active_cloud_model()
        cloud_cost = 0.0105 if cloud_provider == "anthropic" else 0.0035

        if "equipment health" in message_lower:
            return {
                "provider": cloud_provider,
                "model": cloud_model,
                "reason": "Equipment health analysis",
                "estimated_cost": cloud_cost,
                "tier": 2,
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
            return {
                "provider": "ollama",
                "model": self.ollama_models["fast"],
                "reason": "Simple lookup/retrieval",
                "estimated_cost": 0.0,
                "tier": 1,
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
            return {
                "provider": "ollama",
                "model": self.ollama_models["balanced"],
                "reason": "Data query/retrieval",
                "estimated_cost": 0.0,
                "tier": 1,
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
            return {
                "provider": cloud_provider,
                "model": cloud_model,
                "reason": "Complex reasoning required",
                "estimated_cost": cloud_cost,
                "tier": 2,
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
            return {
                "provider": cloud_provider,
                "model": cloud_model,
                "reason": "Control action (safety critical)",
                "estimated_cost": cloud_cost,
                "tier": 2,
            }

        return {
            "provider": cloud_provider,
            "model": cloud_model,
            "reason": "Default to cloud provider for ambiguous queries",
            "estimated_cost": cloud_cost,
            "tier": 2,
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
            if provider == "zai":
                async for chunk in zai_service.stream_response(
                    [{"role": "user", "content": message}],
                    include_building_context=False,
                ):
                    chunks.append(chunk)
            else:
                async for chunk in claude_service.stream_response(
                    [{"role": "user", "content": message}],
                    include_building_context=False,
                ):
                    chunks.append(chunk)
            return "".join(chunks)
        except Exception as e:
            logger.error("Cloud fallback also failed (%s): %s", provider, e)
            return "I'm sorry, I'm having trouble processing your request right now. Please try again."

    async def _try_cloud_with_fallback(
        self,
        message: str,
        include_building_context: bool = True,
        data_subject_id: str | None = None,
    ) -> AsyncGenerator[str, None]:
        """Try active cloud provider and fallback to Ollama on failure."""
        if self._is_local_ai_only() or not self._is_cloud_allowed_for_subject(data_subject_id):
            model = self.ollama_models["balanced"]
            response = await self.query_ollama(
                message,
                model=model,
                escalate_on_fail=False,
                data_subject_id=data_subject_id,
            )
            yield f"[Local-only mode - using {model}] {response}"
            return

        provider = self.get_active_cloud_provider()

        if provider == "anthropic":
            try:
                if self.rate_tracker:
                    self.rate_tracker.record_request()

                async for chunk in claude_service.stream_response(
                    [{"role": "user", "content": message}],
                    include_building_context=include_building_context,
                ):
                    yield chunk
                return

            except RateLimitError as e:
                logger.warning("Claude rate limit hit: %s", e)
                if self.rate_tracker:
                    self.rate_tracker.record_rate_limit_hit()
                else:
                    self.claude_rate_limited = True
                    self.rate_limit_time = time.time()

                routing = self.classify_task(message)
                model = self.ollama_models["fast"] if routing["tier"] == 1 else self.ollama_models["balanced"]
                response = await self.query_ollama(
                    message,
                    model=model,
                    escalate_on_fail=False,
                    data_subject_id=data_subject_id,
                )
                yield f"[Claude rate limited - using {model}] {response}"
                return

            except Exception as e:
                error_type = type(e).__name__
                logger.error("Claude error (%s): %s", error_type, e)
                routing = self.classify_task(message)
                model = self.ollama_models["fast"] if routing["tier"] == 1 else self.ollama_models["balanced"]
                try:
                    response = await self.query_ollama(
                        message,
                        model=model,
                        escalate_on_fail=False,
                        data_subject_id=data_subject_id,
                    )
                    yield f"[Claude unavailable ({error_type}) - using {model}] {response}"
                    return
                except Exception as ollama_error:
                    logger.error("Ollama fallback also failed: %s", ollama_error)
                    yield "I'm having trouble with both AI services. Please try again in a moment."
                    return

        try:
            async for chunk in zai_service.stream_response(
                [{"role": "user", "content": message}],
                include_building_context=include_building_context,
            ):
                yield chunk
            return
        except Exception as e:
            error_type = type(e).__name__
            logger.error("Z.ai error (%s): %s", error_type, e)
            routing = self.classify_task(message)
            model = self.ollama_models["fast"] if routing["tier"] == 1 else self.ollama_models["balanced"]
            try:
                response = await self.query_ollama(
                    message,
                    model=model,
                    escalate_on_fail=False,
                    data_subject_id=data_subject_id,
                )
                yield f"[Z.ai unavailable ({error_type}) - using {model}] {response}"
                return
            except Exception as ollama_error:
                logger.error("Ollama fallback also failed: %s", ollama_error)
                yield "I'm having trouble with both AI services. Please try again in a moment."
                return

    async def stream_response(
        self,
        message: str,
        use_tools: bool = False,
        data_subject_id: str | None = None,
    ) -> AsyncGenerator[str, None]:
        """Stream response from routed provider."""
        provider = self.get_active_cloud_provider()
        cloud_allowed = self._is_cloud_allowed_for_subject(data_subject_id)

        if use_tools and (self._is_local_ai_only() or not cloud_allowed):
            yield (
                "[Local AI only mode] Tool-based actions require Claude and are unavailable right now. "
                "Please use advisory queries only."
            )
            return
        if use_tools and provider != "anthropic":
            yield (
                f"[{provider} cloud mode] Tool-based actions currently require Claude. "
                "Please use advisory queries only."
            )
            return

        routing = self.classify_task(message)
        if self._is_local_ai_only():
            routing["provider"] = "ollama"
            routing["model"] = (
                self.ollama_models["fast"] if routing.get("tier") == 1 else self.ollama_models["balanced"]
            )
            routing["reason"] = f"{routing['reason']} (local-only mode)"
        elif not cloud_allowed:
            routing["provider"] = "ollama"
            routing["model"] = (
                self.ollama_models["fast"] if routing.get("tier") == 1 else self.ollama_models["balanced"]
            )
            routing["reason"] = f"{routing['reason']} (POPIA cross-border consent not active)"

        logger.info(
            "Routing decision: provider=%s, model=%s, reason=%s, tier=%s",
            routing["provider"],
            routing["model"],
            routing["reason"],
            routing["tier"],
        )

        if use_tools:
            can_use_claude, reason = self._should_use_claude()
            if not can_use_claude:
                logger.warning("Tool calling requested but Claude unavailable: %s", reason)
                yield (
                    f"[Claude unavailable: {reason}] Tool-based actions are "
                    "not available right now. Please try again in a moment."
                )
                return

            logger.info("Tool calling enabled, using Claude")
            try:
                if self.rate_tracker:
                    self.rate_tracker.record_request()
                async for chunk in claude_service.stream_response_with_tools([{"role": "user", "content": message}]):
                    yield chunk
                return
            except RateLimitError as e:
                logger.warning("Claude rate limit hit during tool calling: %s", e)
                if self.rate_tracker:
                    self.rate_tracker.record_rate_limit_hit()
                else:
                    self.claude_rate_limited = True
                    self.rate_limit_time = time.time()
                yield "[Claude rate limited] Cannot perform tool-based actions right now. Please try a simpler query."
                return
            except Exception as e:
                from anthropic import APIConnectionError, APIError, APITimeoutError

                error_type = type(e).__name__
                logger.error("Claude API error during tool calling (%s): %s", error_type, e)
                if isinstance(e, (APIError, APIConnectionError, APITimeoutError)):
                    yield (
                        f"[Claude unavailable ({error_type})] Tool-based actions "
                        "are temporarily unavailable. Please try again in a moment."
                    )
                    return
                raise

        if routing["provider"] == "anthropic":
            can_use_claude, reason = self._should_use_claude()
            if not can_use_claude:
                logger.info("Claude unavailable: %s, forcing Ollama fallback", reason)
                routing["provider"] = "ollama"
                routing["model"] = self.ollama_models["balanced"]
                routing["reason"] += f" ({reason})"
                if self.rate_tracker:
                    self.rate_tracker.record_request()

        if routing["provider"] == "ollama":
            try:
                response = await self.query_ollama(
                    message,
                    model=routing["model"],
                    escalate_on_fail=not self._is_local_ai_only(),
                    data_subject_id=data_subject_id,
                )
                yield response
            except Exception as e:
                logger.error("Ollama routing failed: %s", e)
                yield "I'm having trouble with the local AI. Please try again."
            return

        logger.info("Using cloud provider with fallback: %s", routing["provider"])
        async for chunk in self._try_cloud_with_fallback(
            message,
            include_building_context=True,
            data_subject_id=data_subject_id,
        ):
            yield chunk


hybrid_ai_service = HybridAIService()
