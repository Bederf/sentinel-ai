"""Hybrid AI Service - Routes between Ollama (local) and Claude (cloud)."""

import logging
import os
import re
import sys
import time
from typing import AsyncGenerator, Dict, Any

# Add clawd tools to path for rate limit tracker
sys.path.insert(0, '/home/bederf/clawd/tools')

from app.services.claude_service import claude_service
from app.config.settings import settings
from anthropic import RateLimitError

logger = logging.getLogger(__name__)


class HybridAIService:
    """
    Routes AI requests to Ollama (local) or Claude (cloud) based on task complexity.

    Simple tasks → Ollama (FREE, fast)
    Complex tasks → Claude (paid, smart)
    """

    def __init__(self):
        """Initialize hybrid AI service."""
        self.ollama_url = "http://localhost:11434/api/generate"
        self.ollama_models = {
            "fast": "llama3.2:1b",
            "balanced": "phi3:mini"
        }
        self.claude_rate_limited = False
        self.rate_limit_time = 0
        self.cooldown_period = 60
        # Import shared rate limit tracker
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

    def classify_task(self, message: str) -> Dict[str, Any]:
        """
        Classify task complexity and route to appropriate model.

        Returns:
            Dict with 'provider', 'model', 'reason', 'estimated_cost'
        """
        message_lower = message.lower()

        # Special-case: equipment health analysis should use Claude
        if "equipment health" in message_lower:
            return {
                "provider": "anthropic",
                "model": settings.claude_model,
                "reason": "Equipment health analysis",
                "estimated_cost": 0.0105,
                "tier": 2
            }

        # Tier 1: Simple lookups (Ollama - FREE)
        simple_patterns = [
            r'^what does error code',
            r'^what\'?s? the status of',
            r'^who stocks',
            r'^list (all )?equipment',
            r'^show me',
            r'^get (me )?(the )?health',
            r'^how many',
            r'^(all|every) equipment',
        ]

        if any(re.match(pattern, message_lower) for pattern in simple_patterns):
            return {
                "provider": "ollama",
                "model": self.ollama_models["fast"],
                "reason": "Simple lookup/retrieval",
                "estimated_cost": 0.0,
                "tier": 1
            }

        # Tier 1: Data queries (Ollama - FREE)
        data_patterns = [
            r'^get ',
            r'^show ',
            r'^list ',
            r'^check ',
            r'^(all|every) (equipment|devices|alerts)',
            r'^health (score|status)',
            r'^temperature',
            r'^alarm'
        ]

        if any(re.search(pattern, message_lower) for pattern in data_patterns):
            return {
                "provider": "ollama",
                "model": self.ollama_models["balanced"],
                "reason": "Data query/retrieval",
                "estimated_cost": 0.0,
                "tier": 1
            }

        # Tier 2: Complex reasoning (Claude - paid)
        complex_patterns = [
            r'^why (is|does|are)',
            r'^diagnose',
            r'^analyze',
            r'^recommend',
            r'^optimize',
            r'^predict',
            r'^troubleshoot',
            r'root cause',
            r'^too hot',
            r'^too cold',
            r'^unusual',
            r'what should i do',
            r'help me (understand|decide)',
            r'occupancy',
        ]

        if any(re.search(pattern, message_lower) for pattern in complex_patterns):
            return {
                "provider": "anthropic",
                "model": settings.claude_model,
                "reason": "Complex reasoning required",
                "estimated_cost": 0.0105,  # Average cost per query
                "tier": 2
            }

        # Tier 2: Control actions (Claude - paid, safety critical)
        control_patterns = [
            r'^turn (on|off)',
            r'^set .* to',
            r'^adjust ',
            r'^change ',
            r'^control ',
            r'^boost',
            r'^lower',
            r'^raise',
        ]

        if any(re.search(pattern, message_lower) for pattern in control_patterns):
            return {
                "provider": "anthropic",
                "model": settings.claude_model,
                "reason": "Control action (safety critical)",
                "estimated_cost": 0.0105,
                "tier": 2
            }

        # Default: Try Ollama first (can escalate if needed)
        return {
            "provider": "anthropic",
            "model": settings.claude_model,
            "reason": "Default to Claude for ambiguous queries",
            "estimated_cost": 0.0105,
            "tier": 2
        }

    def _should_use_claude(self) -> tuple[bool, str]:
        """
        Check if Claude is available (not in cooldown from rate limit).

        Returns:
            (should_use: bool, reason: str)
        """
        # Use shared tracker if available
        if self.rate_tracker:
            return self.rate_tracker.should_use_claude()

        # Fallback to local tracking
        if not self.claude_rate_limited:
            return True, "Claude available"

        time_since_limit = time.time() - self.rate_limit_time
        if time_since_limit > self.cooldown_period:
            logger.info("Rate limit cooldown expired, attempting Claude again")
            self.claude_rate_limited = False
            return True, "Cooldown expired"

        remaining = int(self.cooldown_period - time_since_limit)
        logger.info(f"Claude in cooldown for {remaining}s more")
        return False, f"Claude in cooldown for {remaining}s"

    async def query_ollama(self, message: str, model: str = "llama3.2:1b", escalate_on_fail: bool = True) -> str:
        """
        Query local Ollama model.

        Args:
            message: User message
            model: Ollama model name
            escalate_on_fail: Whether to escalate to Claude if Ollama fails

        Returns:
            AI response text
        """
        import httpx

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    self.ollama_url,
                    json={
                        "model": model,
                        "prompt": message,
                        "stream": False,
                        "options": {
                            "num_predict": 500,  # Limit response length
                            "temperature": 0.5,
                        }
                    }
                )
                response.raise_for_status()
                result = response.json()
                return result.get("response", "")

        except Exception as e:
            logger.error(f"Ollama query failed: {e}")
            if escalate_on_fail:
                # Escalate to Claude
                logger.info("Escalating to Claude due to Ollama failure")
                return await self._query_claude_fallback(message)
            else:
                # Don't escalate, just re-raise
                raise

    async def _query_claude_fallback(self, message: str) -> str:
        """Fallback to Claude when Ollama fails."""
        try:
            response_chunks = []
            async for chunk in claude_service.stream_response(
                [{"role": "user", "content": message}],
                include_building_context=False
            ):
                response_chunks.append(chunk)
            return "".join(response_chunks)
        except Exception as e:
            logger.error(f"Claude fallback also failed: {e}")
            return "I'm sorry, I'm having trouble processing your request right now. Please try again."

    async def _try_claude_with_fallback(
        self,
        message: str,
        include_building_context: bool = True
    ) -> AsyncGenerator[str, None]:
        """
        Try Claude with automatic fallback to Ollama on rate limit.

        Args:
            message: User message
            include_building_context: Whether to include building context

        Yields:
            Response text chunks
        """
        try:
            # Record the request before calling Claude
            if self.rate_tracker:
                self.rate_tracker.record_request()

            # Try Claude first
            async for chunk in claude_service.stream_response(
                [{"role": "user", "content": message}],
                include_building_context=include_building_context
            ):
                yield chunk

        except RateLimitError as e:
            # Handle rate limit - fallback to Ollama
            logger.warning(f"Claude rate limit hit: {e}")

            # Record rate limit hit in shared tracker
            if self.rate_tracker:
                self.rate_tracker.record_rate_limit_hit()
            else:
                # Fallback to local tracking
                self.claude_rate_limited = True
                self.rate_limit_time = time.time()

            logger.info("Falling back to Ollama due to rate limit")
            routing = self.classify_task(message)

            # Use Ollama instead
            if routing["tier"] == 1:
                # Use the fast model for simple queries
                model = self.ollama_models["fast"]
            else:
                # Use balanced model for complex queries
                model = self.ollama_models["balanced"]

            response = await self.query_ollama(
                message,
                model=model,
                escalate_on_fail=False  # Don't escalate back to Claude
            )

            # Prefix with rate limit notice
            yield f"[Claude rate limited - using {model}] {response}"

        except Exception as e:
            # Handle all other Claude API errors with Ollama fallback
            # This includes: 500 Internal Server Error, 502 Bad Gateway, 503 Service Unavailable, etc.
            error_type = type(e).__name__
            logger.error(f"Claude API error ({error_type}): {e}")

            # Check if this is a transient API error that warrants fallback
            # APIError, APIConnectionError, and similar should trigger fallback
            from anthropic import APIError, APIConnectionError, APITimeoutError

            if isinstance(e, (APIError, APIConnectionError, APITimeoutError)):
                logger.info("Claude API unavailable - falling back to Ollama")
                routing = self.classify_task(message)

                # Use Ollama instead
                if routing["tier"] == 1:
                    model = self.ollama_models["fast"]
                else:
                    model = self.ollama_models["balanced"]

                try:
                    response = await self.query_ollama(
                        message,
                        model=model,
                        escalate_on_fail=False
                    )
                    # Prefix with fallback notice
                    yield f"[Claude unavailable ({error_type}) - using {model}] {response}"
                    return
                except Exception as ollama_error:
                    logger.error(f"Ollama fallback also failed: {ollama_error}")
                    yield "I'm having trouble with both AI services. Please try again in a moment."
                    return
            else:
                # For non-API errors (programming errors, etc.), re-raise
                logger.error(f"Claude error (not transient API error): {e}")
                raise

    async def stream_response(
        self,
        message: str,
        use_tools: bool = False
    ) -> AsyncGenerator[str, None]:
        """
        Stream response from appropriate AI model.

        Args:
            message: User message
            use_tools: Whether to enable tool calling (Claude only)

        Yields:
            Response text chunks
        """
        # Classify task
        routing = self.classify_task(message)

        logger.info(
            f"Routing decision: provider={routing['provider']}, "
            f"model={routing['model']}, "
            f"reason={routing['reason']}, "
            f"tier={routing['tier']}"
        )

        # Force Claude for tool calling (bypasses rate limit check for safety)
        if use_tools:
            can_use_claude, reason = self._should_use_claude()

            if not can_use_claude:
                logger.warning(f"Tool calling requested but Claude unavailable: {reason}")
                yield f"[Claude unavailable: {reason}] Tool-based actions are not available right now. Please try again in a moment."
                return

            logger.info("Tool calling enabled, using Claude")
            try:
                # Record the request
                if self.rate_tracker:
                    self.rate_tracker.record_request()

                async for chunk in claude_service.stream_response_with_tools(
                    [{"role": "user", "content": message}]
                ):
                    yield chunk
                return
            except RateLimitError as e:
                logger.warning(f"Claude rate limit hit during tool calling: {e}")

                # Record rate limit hit
                if self.rate_tracker:
                    self.rate_tracker.record_rate_limit_hit()
                else:
                    self.claude_rate_limited = True
                    self.rate_limit_time = time.time()

                yield "[Claude rate limited] Cannot perform tool-based actions right now. Please try a simpler query."
                return

            except Exception as e:
                # Handle all other Claude API errors during tool calling
                from anthropic import APIError, APIConnectionError, APITimeoutError

                error_type = type(e).__name__
                logger.error(f"Claude API error during tool calling ({error_type}): {e}")

                if isinstance(e, (APIError, APIConnectionError, APITimeoutError)):
                    yield f"[Claude unavailable ({error_type})] Tool-based actions are temporarily unavailable. Please try again in a moment."
                    return
                else:
                    # For non-API errors, re-raise
                    raise

        # Check if Claude is in cooldown period
        if routing["provider"] == "anthropic":
            can_use_claude, reason = self._should_use_claude()
            if not can_use_claude:
                logger.info(f"Claude unavailable: {reason}, forcing Ollama fallback")
                routing["provider"] = "ollama"
                routing["model"] = self.ollama_models["balanced"]
                routing["reason"] += f" ({reason})"

                # Record that we checked/used the rate limiter
                if self.rate_tracker:
                    self.rate_tracker.record_request()

        # Route to appropriate provider
        if routing["provider"] == "ollama":
            # Use local Ollama
            try:
                response = await self.query_ollama(
                    message,
                    model=routing["model"],
                    escalate_on_fail=True  # Can escalate to Claude if Ollama fails
                )
                yield response
            except Exception as e:
                logger.error(f"Ollama routing failed: {e}")
                yield "I'm having trouble with the local AI. Please try again."

        else:
            # Use Claude (cloud) with rate limit fallback
            logger.info("Using Claude with rate limit fallback")
            async for chunk in self._try_claude_with_fallback(
                message,
                include_building_context=True
            ):
                yield chunk


# Singleton instance
hybrid_ai_service = HybridAIService()
hybrid_ai_service = HybridAIService()
