"""Tests for ModelGateway routing logic (Phase 183 - Fallback Support)."""

import os
from unittest.mock import AsyncMock, patch

import pytest

# Set profile before import so tests use a known profile
os.environ.setdefault("SENTINEL_ROUTING_PROFILE", "api_prod")
os.environ.setdefault("SENTINEL_EXECUTION_MODE", "api")

from app.config.routing_profiles import VALID_TASK_CLASSES
from app.services.model_gateway import LocalInferenceUnavailableError, ModelGateway


class TestProfileResolution:
    def setup_method(self):
        self.gw = ModelGateway()

    def test_heavy_resolves_with_minimax_primary_anthropic_fallback(self):
        mode, fallback_enabled, routes = self.gw._resolve("heavy")
        assert mode == "api"
        assert fallback_enabled is True
        assert len(routes) >= 3
        assert routes[0][0] == "minimax"  # Primary
        assert routes[1][0] == "deepseek"  # Fallback
        assert routes[2][0] == "openai"  # Final fallback

    def test_light_resolves_with_minimax_primary(self):
        mode, fallback_enabled, routes = self.gw._resolve("light")
        assert mode == "api"
        assert fallback_enabled is True
        assert routes[0][0] == "minimax"

    def test_chat_ai_resolves_with_fallback_chain(self):
        mode, fallback_enabled, routes = self.gw._resolve("chat_ai")
        assert mode == "api"
        assert fallback_enabled is True
        assert len(routes) >= 2

    def test_chat_tech_resolves_with_fallback_chain(self):
        mode, fallback_enabled, routes = self.gw._resolve("chat_tech")
        assert mode == "api"
        assert fallback_enabled is True
        assert len(routes) >= 2

    def test_invalid_task_class_raises_value_error(self):
        with pytest.raises(ValueError, match="invalid_class"):
            self.gw._resolve("invalid_class")

    def test_all_task_classes_valid(self):
        for tc in VALID_TASK_CLASSES:
            mode, fallback_enabled, routes = self.gw._resolve(tc)
            assert mode in {"api", "cloud", "local"}
            assert isinstance(fallback_enabled, bool)
            assert isinstance(routes, list)
            assert len(routes) > 0
            for provider, model in routes:
                assert isinstance(provider, str)
                assert isinstance(model, str)


class TestLocalInferenceUnavailableError:
    def test_is_runtime_error(self):
        assert issubclass(LocalInferenceUnavailableError, RuntimeError)

    def test_raises_with_message(self):
        err = LocalInferenceUnavailableError("Ollama down")
        assert "Ollama down" in str(err)

    @pytest.mark.asyncio
    async def test_local_mode_raises_on_failure(self):
        """local_full mode must raise LocalInferenceUnavailableError on Ollama failure."""
        gw = ModelGateway()
        with (
            patch(
                "app.services.hybrid_ai_service.hybrid_ai_service.query_ollama",
                side_effect=ConnectionRefusedError("Ollama unreachable"),
            ),
            pytest.raises(LocalInferenceUnavailableError),
        ):
            await gw._call_local(
                provider="ollama",
                model="qwen2.5:7b-instruct",
                messages=[{"role": "user", "content": "test"}],
                system=None,
                max_tokens=512,
                stream=False,
                source="test",
            )


class TestEscalation:
    @pytest.mark.asyncio
    async def test_escalate_requires_reason(self):
        gw = ModelGateway()
        with pytest.raises(ValueError, match="reason"):
            await gw.escalate(context=[], reason="")

    @pytest.mark.asyncio
    async def test_escalate_requires_nonempty_reason(self):
        gw = ModelGateway()
        with pytest.raises(ValueError, match="reason"):
            await gw.escalate(context=[], reason="   ")

    @pytest.mark.asyncio
    async def test_escalate_calls_heavy_class(self):
        gw = ModelGateway()
        call_mock = AsyncMock(return_value="escalated response")
        gw.call = call_mock
        result = await gw.escalate(
            context=[{"role": "user", "content": "complex question"}],
            reason="multi-system reasoning required",
        )
        call_mock.assert_called_once()
        call_kwargs = call_mock.call_args
        assert call_kwargs.kwargs.get("task_class") == "heavy" or (call_kwargs.args and call_kwargs.args[0] == "heavy")

    @pytest.mark.asyncio
    async def test_escalate_preserves_context(self):
        gw = ModelGateway()
        original_context = [{"role": "user", "content": "original question"}]
        call_mock = AsyncMock(return_value="escalated response")
        gw.call = call_mock
        await gw.escalate(context=original_context, reason="technical depth required")
        call_kwargs = call_mock.call_args
        # Context should be passed through
        passed_messages = call_kwargs.kwargs.get("messages") or (
            call_kwargs.args[1] if len(call_kwargs.args) > 1 else None
        )
        assert passed_messages == original_context


class TestFallbackChainRetry:
    @pytest.mark.asyncio
    async def test_fallback_tries_next_provider_on_primary_failure(self):
        """When primary provider fails and fallback_enabled=True, try next provider."""
        gw = ModelGateway()

        # Mock first provider (minimax) to fail, second (anthropic) to succeed
        with patch("app.services.model_gateway.ModelGateway._call_api") as mock_call:
            # First call (minimax) raises, second call (anthropic) succeeds
            mock_call.side_effect = [
                Exception("MiniMax unavailable"),
                "Anthropic response",
            ]

            result = await gw._try_routes(
                routes=[("minimax", "MiniMax-M2.7"), ("anthropic", "claude-opus-4-6")],
                fallback_enabled=True,
                mode="api",
                messages=[{"role": "user", "content": "test"}],
                system=None,
                max_tokens=1536,
                stream=False,
                tools=None,
                source="test",
                site_id="site-002",
            )

            assert result == "Anthropic response"
            assert mock_call.call_count == 2  # First failed, second succeeded
            assert mock_call.call_args_list[0].kwargs["site_id"] == "site-002"
            assert mock_call.call_args_list[1].kwargs["site_id"] == "site-002"

    @pytest.mark.asyncio
    async def test_fallback_disabled_raises_on_first_failure(self):
        """When fallback_enabled=False, propagate original exception without trying fallbacks."""
        gw = ModelGateway()

        with patch("app.services.model_gateway.ModelGateway._call_api") as mock_call:
            mock_call.side_effect = Exception("Provider failed")

            # When fallback disabled, original exception is re-raised, not wrapped
            with pytest.raises(Exception, match="Provider failed"):
                await gw._try_routes(
                    routes=[("ollama", "deepseek-r1:14b")],
                    fallback_enabled=False,
                    mode="api",
                    messages=[{"role": "user", "content": "test"}],
                    system=None,
                    max_tokens=1536,
                    stream=False,
                    tools=None,
                    source="test",
                    site_id="site-002",
                )

            assert mock_call.call_count == 1  # Only tried first, no fallback
            assert mock_call.call_args.kwargs["site_id"] == "site-002"

    @pytest.mark.asyncio
    async def test_all_routes_exhausted_raises_error(self):
        """When all fallback routes fail, raise ValueError."""
        gw = ModelGateway()

        with patch("app.services.model_gateway.ModelGateway._call_api") as mock_call:
            mock_call.side_effect = Exception("All providers failed")

            with pytest.raises(ValueError, match="All 2 routes exhausted"):
                await gw._try_routes(
                    routes=[("minimax", "MiniMax-M2.7"), ("anthropic", "claude-opus-4-6")],
                    fallback_enabled=True,
                    mode="api",
                    messages=[{"role": "user", "content": "test"}],
                    system=None,
                    max_tokens=1536,
                    stream=False,
                    tools=None,
                    source="test",
                    site_id="site-002",
                )

            assert mock_call.call_count == 2  # Tried both routes
            assert mock_call.call_args_list[0].kwargs["site_id"] == "site-002"
            assert mock_call.call_args_list[1].kwargs["site_id"] == "site-002"

    @pytest.mark.asyncio
    async def test_call_passes_site_id_to_try_routes(self):
        """Public call() must preserve site_id for usage tracking and budget enforcement."""
        gw = ModelGateway()

        with patch("app.services.model_gateway.ModelGateway._resolve") as mock_resolve:
            with patch("app.services.model_gateway.ModelGateway._try_routes", new_callable=AsyncMock) as mock_try:
                mock_resolve.return_value = ("api", True, [("minimax", "MiniMax-M2.7")])
                mock_try.return_value = "ok"

                result = await gw.call(
                    task_class="heavy",
                    messages=[{"role": "user", "content": "test"}],
                    source="ai_optimizer",
                    site_id="site-002",
                )

        assert result == "ok"
        mock_try.assert_called_once()
        assert mock_try.call_args.kwargs["site_id"] == "site-002"


class TestLocalFullHardFail:
    @pytest.mark.asyncio
    async def test_local_full_profile_raises_on_ollama_failure(self):
        """In local_full mode, model_gateway must raise LocalInferenceUnavailableError
        when Ollama is unreachable — no silent cloud fallback."""
        import app.config.settings as settings_mod
        from app.services.model_gateway import LocalInferenceUnavailableError, ModelGateway

        original = settings_mod.SENTINEL_ROUTING_PROFILE
        try:
            settings_mod.SENTINEL_ROUTING_PROFILE = "local_full"
            with (
                patch(
                    "app.services.hybrid_ai_service.hybrid_ai_service.query_ollama",
                    side_effect=Exception("Connection refused"),
                ),
                pytest.raises(LocalInferenceUnavailableError),
            ):
                await ModelGateway().call(
                    task_class="medium",
                    messages=[{"role": "user", "content": "test"}],
                )
        finally:
            settings_mod.SENTINEL_ROUTING_PROFILE = original


class TestProfileSwitching:
    def test_local_full_profile_resolves_to_ollama_no_fallback(self):
        with patch("app.config.settings.SENTINEL_ROUTING_PROFILE", "local_full"):
            with patch("app.services.model_gateway._settings_module.SENTINEL_ROUTING_PROFILE", "local_full"):
                gw = ModelGateway()
                mode, fallback_enabled, routes = gw._resolve("heavy")
                assert mode == "local"
                assert fallback_enabled is False  # Strict: no fallback
                assert routes[0][0] == "ollama"
                assert "deepseek" in routes[0][1]

    def test_cloud_dev_profile_resolves_to_minimax_with_fallback(self):
        with patch("app.services.model_gateway._settings_module.SENTINEL_ROUTING_PROFILE", "cloud_dev"):
            gw = ModelGateway()
            mode, fallback_enabled, routes = gw._resolve("medium")
            assert mode == "api"
            assert fallback_enabled is True  # Fallback enabled
            assert routes[0][0] == "deepseek"  # Primary
            assert routes[1][0] == "minimax"  # Fallback
