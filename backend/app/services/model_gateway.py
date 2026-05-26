"""
SENTINEL Model Gateway (Phase 163).

Single entry point for all LLM calls in the SENTINEL backend.
Services pass a task_class. The gateway resolves provider + model from the
active routing profile and dispatches to the correct provider client.

Usage:
    from app.services.model_gateway import model_gateway

    response = await model_gateway.call(
        task_class="medium",
        messages=[{"role": "user", "content": "..."}],
        system="You are a BMS assistant.",
    )

Services must NOT import provider clients directly.
Services must NOT contain hardcoded model strings.
"""

from __future__ import annotations

import contextlib
import logging
from collections.abc import AsyncGenerator

from app.config import settings as _settings_module
from app.config.routing_profiles import VALID_TASK_CLASSES, get_profile

logger = logging.getLogger(__name__)


class LocalInferenceUnavailableError(RuntimeError):
    """
    Raised when local_full mode is active and the local Ollama service is unreachable.
    Never silently falls back to cloud or api mode.
    """

    pass


class ModelGateway:
    """
    Resolves task_class → provider + model → dispatches to provider client.
    Encapsulates all provider-specific behaviour (caching, retry, tracking).
    """

    def _get_active_profile(self) -> dict:
        profile_name = _settings_module.SENTINEL_ROUTING_PROFILE
        return get_profile(profile_name)

    def _resolve(self, task_class: str) -> tuple[str, bool, list[tuple[str, str]]]:
        """
        Returns (mode, fallback_enabled, routes) for the given task_class.
        routes is a list of (provider, model) tuples in priority order.
        """
        if task_class not in VALID_TASK_CLASSES:
            valid = ", ".join(sorted(VALID_TASK_CLASSES))
            raise ValueError(f"Unknown task_class '{task_class}'. Valid: {valid}")
        profile = self._get_active_profile()
        mode = profile["mode"]
        fallback_enabled = profile.get("fallback_enabled", False)
        route_list = profile["routing"][task_class]

        # route_list is always a list of dicts now
        routes = [(r["provider"], r["model"]) for r in route_list]
        return mode, fallback_enabled, routes

    async def call(
        self,
        task_class: str,
        messages: list[dict],
        system: str | None = None,
        max_tokens: int = 1536,
        stream: bool = False,
        tools: list | None = None,
        source: str = "gateway",
        site_id: str | None = None,
    ) -> str | AsyncGenerator:
        """
        Route an LLM call based on task_class and active profile.
        Implements fallback chain retry logic for api/cloud modes.

        Args:
            task_class: One of heavy | medium | light | chat_ai | chat_tech
            messages:   Standard messages list [{"role": ..., "content": ...}]
            system:     Optional system prompt
            max_tokens: Max output tokens (default 1536)
            stream:     If True, return async generator instead of string
            tools:      Optional tool definitions (only supported in api mode)

        Returns:
            str if stream=False, AsyncGenerator if stream=True

        Raises:
            LocalInferenceUnavailableError if local_full mode and Ollama unavailable
            ValueError if all fallback routes exhausted in api/cloud mode
        """
        mode, fallback_enabled, routes = self._resolve(task_class)
        logger.debug(
            "model_gateway.call task_class=%s mode=%s fallback_enabled=%s routes=%s",
            task_class,
            mode,
            fallback_enabled,
            routes,
        )

        if mode == "api":
            return await self._try_routes(
                routes=routes,
                fallback_enabled=fallback_enabled,
                mode="api",
                messages=messages,
                system=system,
                max_tokens=max_tokens,
                stream=stream,
                tools=tools,
                source=source,
            )
        elif mode == "cloud":
            return await self._try_routes(
                routes=routes,
                fallback_enabled=fallback_enabled,
                mode="cloud",
                messages=messages,
                system=system,
                max_tokens=max_tokens,
                stream=stream,
                tools=tools,
                source=source,
            )
        elif mode == "local":
            # local mode: no fallback to cloud, strict enforcement
            return await self._call_local(
                provider=routes[0][0],
                model=routes[0][1],
                messages=messages,
                system=system,
                max_tokens=max_tokens,
                stream=stream,
                source=source,
            )
        else:
            raise ValueError(f"Unknown execution mode '{mode}'")

    async def _try_routes(
        self,
        routes: list[tuple[str, str]],
        fallback_enabled: bool,
        mode: str,
        messages: list[dict],
        system: str | None,
        max_tokens: int,
        stream: bool,
        tools: list | None,
        source: str,
    ) -> str | AsyncGenerator:
        """
        Try a list of (provider, model) routes in priority order.
        If fallback_enabled=False, only tries the first route.
        If fallback_enabled=True, falls back to next route on failure.

        Returns on first success; raises only after all routes exhausted.
        """
        if not routes:
            raise ValueError("No routes available for call")

        last_error = None
        for attempt, (provider, model) in enumerate(routes, 1):
            try:
                if attempt > 1:
                    logger.info(
                        "model_gateway fallback attempt=%d provider=%s model=%s mode=%s",
                        attempt,
                        provider,
                        model,
                        mode,
                    )

                if mode == "api":
                    return await self._call_api(
                        provider=provider,
                        model=model,
                        messages=messages,
                        system=system,
                        max_tokens=max_tokens,
                        stream=stream,
                        tools=tools,
                        source=source,
                    )
                elif mode == "cloud":
                    return await self._call_cloud(
                        provider=provider,
                        model=model,
                        messages=messages,
                        system=system,
                        max_tokens=max_tokens,
                        stream=stream,
                        source=source,
                    )
                else:
                    raise ValueError(f"_try_routes: unsupported mode '{mode}'")

            except Exception as exc:
                last_error = exc
                logger.warning(
                    "model_gateway route failed attempt=%d provider=%s model=%s error=%s",
                    attempt,
                    provider,
                    model,
                    exc,
                )

                # If fallback disabled, don't try next route
                if not fallback_enabled:
                    raise

                # If this is the last route, raise after loop
                if attempt == len(routes):
                    break

                # Otherwise, continue to next route
                logger.info("model_gateway trying next fallback route (attempt=%d of %d)", attempt + 1, len(routes))

        # All routes exhausted
        if last_error:
            raise ValueError(
                f"All {len(routes)} routes exhausted for mode={mode}. Last error: {last_error}"
            ) from last_error
        else:
            raise ValueError(f"All {len(routes)} routes exhausted for mode={mode} (no error info)")

    async def _call_api(
        self,
        provider: str,
        model: str,
        messages: list[dict],
        system: str | None,
        max_tokens: int,
        stream: bool,
        tools: list | None,
        source: str,
    ) -> str | AsyncGenerator:
        """
        api mode: direct provider API.
        - prompt caching enabled (handled by claude_service internally for streaming)
        - usage tracking via usage_tracker.record()
        - retry on 429/500 (handled by claude_service internally)
        - For non-streaming calls: uses Anthropic SDK directly (only gateway may do this)
        """
        if provider == "anthropic":
            from app.services.claude_service import claude_service

            if stream:
                # claude_service.stream_response returns an AsyncGenerator
                return claude_service.stream_response(
                    messages=messages,
                    system_prompt=system or "",
                    model_override=model,
                    source=source,
                )
            else:
                # Non-streaming: call Anthropic SDK directly (gateway is the only importer)
                from anthropic import Anthropic

                from app.config.settings import settings
                from app.services.ai_usage_tracker import usage_tracker

                client = Anthropic(api_key=settings.anthropic_api_key)

                # Build system blocks with prompt caching
                system_blocks = None
                if system:
                    system_blocks = [
                        {
                            "type": "text",
                            "text": system,
                            "cache_control": {"type": "ephemeral"},
                        }
                    ]

                kwargs: dict = {
                    "model": model,
                    "max_tokens": max_tokens,
                    "messages": messages,
                }
                if system_blocks:
                    kwargs["system"] = system_blocks
                if tools:
                    kwargs["tools"] = tools

                response = client.messages.create(**kwargs)

                # Track usage
                try:
                    u = response.usage
                    usage_tracker.record(
                        provider="anthropic",
                        model=model,
                        input_tokens=getattr(u, "input_tokens", 0),
                        output_tokens=getattr(u, "output_tokens", 0),
                        source=source,
                        site_id=site_id or "unknown",
                        cache_read_tokens=getattr(u, "cache_read_input_tokens", 0),
                        cache_creation_tokens=getattr(u, "cache_creation_input_tokens", 0),
                    )
                except Exception:
                    pass

                # Extract text from response content
                text = ""
                for block in response.content:
                    if hasattr(block, "text"):
                        text += block.text
                return text

        elif provider == "openai":
            from app.services.openai_service import openai_service

            if stream:
                return openai_service.stream_response(
                    messages=messages,
                    include_site_context=False,
                    source=source,
                )
            else:
                # Non-streaming OpenAI call via httpx (gateway is the provider boundary)
                import httpx

                from app.config.settings import settings
                from app.services.ai_usage_tracker import usage_tracker

                url = f"{settings.openai_base_url.rstrip('/')}/chat/completions"
                headers = {
                    "Authorization": f"Bearer {settings.openai_api_key}",
                    "Content-Type": "application/json",
                }
                payload: dict = {
                    "model": model,
                    "messages": messages,
                    "max_tokens": max_tokens,
                }
                if system:
                    payload["messages"] = [{"role": "system", "content": system}, *list(messages)]
                if tools:
                    payload["tools"] = tools

                async with httpx.AsyncClient(timeout=60.0) as client:
                    resp = await client.post(url, headers=headers, json=payload)
                    resp.raise_for_status()

                body = resp.json()
                try:
                    usage = body.get("usage", {})
                    usage_tracker.record(
                        provider="openai",
                        model=model,
                        input_tokens=usage.get("prompt_tokens", 0),
                        output_tokens=usage.get("completion_tokens", 0),
                        source=source,
                        site_id=site_id or "unknown",
                    )
                except Exception:
                    pass

                choices = body.get("choices", [])
                if not choices:
                    return ""
                return choices[0].get("message", {}).get("content", "")

        elif provider == "azure_openai":
            import os

            import httpx

            from app.services.ai_usage_tracker import usage_tracker

            api_key = os.environ.get("AZURE_OPENAI_API_KEY", "")
            endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT", "").rstrip("/")
            deployment = os.environ.get("AZURE_OPENAI_DEPLOYMENT", "")
            api_version = "2024-02-01"
            url = f"{endpoint}/openai/deployments/{deployment}/chat/completions?api-version={api_version}"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            payload: dict = {
                "messages": messages,
                "max_tokens": max_tokens,
            }
            if system:
                payload["messages"] = [{"role": "system", "content": system}, *list(messages)]
            if tools:
                payload["tools"] = tools

            if stream:

                async def stream_gen():
                    async with httpx.AsyncClient(timeout=120.0) as client:
                        async with client.stream("POST", url, headers=headers, json=payload) as resp:
                            resp.raise_for_status()
                            async for line in resp.aiter_lines():
                                if not line.startswith("data: "):
                                    continue
                                data = line[6:].strip()
                                if data == "[DONE]":
                                    break
                                import json as _json

                                try:
                                    chunk = _json.loads(data)
                                except Exception:
                                    continue
                                delta = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
                                if delta:
                                    yield delta
                    usage_tracker.record(
                                            provider="azure_openai",
                                            model=model,
                                            input_tokens=usage.get("prompt_tokens", 0),
                                            output_tokens=usage.get("completion_tokens", 0),
                                            source=source,
                                            feature="gsd_orchestrator",
                                            site_id=site_id or "unknown",
                                        )

                return stream_gen()
            else:
                async with httpx.AsyncClient(timeout=60.0) as client:
                    resp = await client.post(url, headers=headers, json=payload)
                    resp.raise_for_status()

                body = resp.json()
                try:
                    usage = body.get("usage", {})
                    usage_tracker.record(
                        provider="azure_openai",
                        model=model,
                        input_tokens=usage.get("prompt_tokens", 0),
                        output_tokens=usage.get("completion_tokens", 0),
                        source=source,
                        feature="gsd_orchestrator",
                        site_id=site_id or "unknown",
                    )
                except Exception:
                    pass

                choices = body.get("choices", [])
                if not choices:
                    return ""
                return choices[0].get("message", {}).get("content", "")

        elif provider == "minimax":
            from app.services.minimax_service import minimax_service

            if stream:
                # await here so the eager connection + status check runs before
                # returning — allows _try_routes to catch 429 and fall through
                return await minimax_service.stream_response(
                    messages=messages,
                    system_prompt=system,
                    source=source,
                )
            else:
                return await minimax_service.non_stream_response(
                    messages=messages,
                    system_prompt=system,
                    source=source,
                )

        elif provider == "deepseek":
            # DeepSeek uses OpenAI-compatible /chat/completions format
            import httpx

            from app.config.settings import settings
            from app.services.ai_usage_tracker import usage_tracker

            if not settings.deepseek_api_key:
                raise ValueError("DEEPSEEK_API_KEY not configured.")

            url = f"{settings.deepseek_base_url.rstrip('/')}/chat/completions"
            headers = {
                "Authorization": f"Bearer {settings.deepseek_api_key}",
                "Content-Type": "application/json",
            }
            payload: dict = {
                "model": model,
                "messages": messages,
                "max_tokens": max_tokens,
            }
            if system:
                payload["messages"] = [{"role": "system", "content": system}, *list(messages)]
            if tools:
                payload["tools"] = tools

            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(url, headers=headers, json=payload)
                resp.raise_for_status()

            body = resp.json()
            try:
                usage = body.get("usage", {})
                usage_tracker.record(
                    provider="deepseek",
                    model=model,
                    input_tokens=usage.get("prompt_tokens", 0),
                    output_tokens=usage.get("completion_tokens", 0),
                    source=source,
                    site_id=site_id or "unknown",
                    feature="ai_optimizer",
                )
            except Exception:
                pass

            choices = body.get("choices", [])
            if not choices:
                return ""
            return choices[0].get("message", {}).get("content", "")

        else:
            raise ValueError(f"api mode: unknown provider '{provider}'")

    async def _call_cloud(
        self,
        provider: str,
        model: str,
        messages: list[dict],
        system: str | None,
        max_tokens: int,
        stream: bool,
        source: str,
    ) -> str | AsyncGenerator:
        """
        cloud mode: externally hosted models through an abstraction layer.
        - No prompt caching (not supported through abstraction layer)
        - Aggregate usage tracking with provider="cloud"
        - Single retry on timeout
        - No fallback — cloud endpoint is the endpoint
        """
        if provider == "ollama_cloud":
            # Convert messages list to a single prompt string for Ollama API
            from app.services.hybrid_ai_service import hybrid_ai_service

            # Flatten messages to a single prompt
            prompt_parts = []
            if system:
                prompt_parts.append(f"System: {system}")
            for msg in messages:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if isinstance(content, list):
                    # Handle content blocks
                    text_parts = [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]
                    content = " ".join(text_parts)
                prompt_parts.append(f"{role.capitalize()}: {content}")
            prompt = "\n".join(prompt_parts)

            return await hybrid_ai_service.query_ollama(
                message=prompt,
                model=model,
                escalate_on_fail=False,
            )
        else:
            raise ValueError(f"cloud mode: unknown provider '{provider}'")

    async def _call_local(
        self,
        provider: str,
        model: str,
        messages: list[dict],
        system: str | None,
        max_tokens: int,
        stream: bool,
        source: str,
    ) -> str | AsyncGenerator:
        """
        local mode: local-only inference. No external calls permitted.
        - No prompt caching (inference is local)
        - Local token counting only
        - Single retry on Ollama timeout
        - On failure: raise LocalInferenceUnavailableError — NEVER fall back to cloud/api
        """
        if provider != "ollama":
            raise ValueError(f"local mode: only 'ollama' provider supported, got '{provider}'")
        try:
            from app.services.hybrid_ai_service import hybrid_ai_service

            # Flatten messages to prompt string
            prompt_parts = []
            if system:
                prompt_parts.append(f"System: {system}")
            for msg in messages:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if isinstance(content, list):
                    text_parts = [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]
                    content = " ".join(text_parts)
                prompt_parts.append(f"{role.capitalize()}: {content}")
            prompt = "\n".join(prompt_parts)

            return await hybrid_ai_service.query_ollama(
                message=prompt,
                model=model,
                escalate_on_fail=False,
            )
        except Exception as exc:
            logger.error(
                "LocalInferenceUnavailableError: Ollama unreachable in local_full mode. "
                "model=%s error=%s. NOT falling back to cloud/api.",
                model,
                exc,
            )
            raise LocalInferenceUnavailableError(
                f"Local inference unavailable (model={model}). "
                f"SENTINEL is in local_full mode — no fallback permitted. "
                f"Original error: {exc}"
            ) from exc

    async def escalate(
        self,
        context: list[dict],
        reason: str,
        system: str | None = None,
        max_tokens: int = 2048,
        session_id: str = "",
    ) -> str:
        """
        Escalate to the heavy task class with preserved context.

        This is a distinct routing action — not a retry, not a fallback.
        The reason string is mandatory and must describe why escalation is needed.

        Escalation is logged before the heavy call is dispatched.
        In local_full mode, escalation resolves to the local heavy model.
        On failure in local_full, raises LocalInferenceUnavailableError — no outbound attempt.

        Args:
            context:    Original messages to preserve through escalation
            reason:     Explicit reason string (required — no silent escalations)
            system:     Optional system prompt to pass to the heavy model
            max_tokens: Max output tokens for the heavy call
            session_id: Optional session identifier for logging

        Returns:
            str — response from heavy model
        """
        if not reason or not reason.strip():
            raise ValueError("escalate() requires an explicit non-empty reason string")

        from_class_active = _settings_module.SENTINEL_BOT_DEFAULT_CLASS  # log as generic default
        to_class = _settings_module.SENTINEL_BOT_ESCALATION_CLASS  # "heavy"

        _mode, _fallback_enabled, _routes = self._resolve(to_class)
        _primary_provider = _routes[0][0] if _routes else None
        _primary_model = _routes[0][1] if _routes else None

        # Log the escalation BEFORE dispatching the call
        try:
            from app.services.ai_usage_tracker import usage_tracker

            usage_tracker.record_escalation(
                from_class=from_class_active,
                to_class=to_class,
                reason=reason.strip(),
                mode=_mode,
                resolved_model=_primary_model,
                session_id=session_id,
                provider=_primary_provider,
            )
        except Exception as log_exc:
            # Never let logging failure block the escalated call
            logger.warning("escalation logging failed: %s", log_exc)

        logger.info(
            "model_gateway.escalate reason='%s' to_class=%s mode=%s model=%s", reason.strip(), to_class, _mode, _primary_model
        )

        # Dispatch as a new routed call — not a retry
        # stream=False guarantees a str return; cast to satisfy type checker
        result = await self.call(
            task_class=to_class,
            messages=context,
            system=system,
            max_tokens=max_tokens,
            stream=False,  # escalation always returns full response
        )
        return str(result)


# Module-level singleton
model_gateway = ModelGateway()
