"""Tests for ModelGateway routing logic (Phase 163)."""

import pytest
from unittest.mock import AsyncMock, patch
import os

# Set profile before import so tests use a known profile
os.environ.setdefault("SENTINEL_ROUTING_PROFILE", "api_prod")
os.environ.setdefault("SENTINEL_EXECUTION_MODE", "api")

from app.services.model_gateway import ModelGateway, LocalInferenceUnavailableError
from app.config.routing_profiles import VALID_TASK_CLASSES


class TestProfileResolution:
    def setup_method(self):
        self.gw = ModelGateway()

    def test_heavy_resolves_to_sonnet(self):
        mode, provider, model = self.gw._resolve("heavy")
        assert mode == "api"
        assert provider == "anthropic"
        assert "sonnet" in model or "claude" in model

    def test_light_resolves_to_haiku(self):
        _, _, model = self.gw._resolve("light")
        assert "haiku" in model

    def test_chat_ai_resolves_to_haiku(self):
        _, _, model = self.gw._resolve("chat_ai")
        assert "haiku" in model

    def test_chat_tech_resolves_to_sonnet(self):
        _, _, model = self.gw._resolve("chat_tech")
        assert "sonnet" in model or "claude" in model

    def test_invalid_task_class_raises_value_error(self):
        with pytest.raises(ValueError, match="invalid_class"):
            self.gw._resolve("invalid_class")

    def test_all_task_classes_valid(self):
        for tc in VALID_TASK_CLASSES:
            mode, provider, model = self.gw._resolve(tc)
            assert mode in {"api", "cloud", "local"}
            assert provider
            assert model


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
        with patch(
            "app.services.hybrid_ai_service.hybrid_ai_service.query_ollama",
            side_effect=ConnectionRefusedError("Ollama unreachable"),
        ):
            with pytest.raises(LocalInferenceUnavailableError):
                await gw._call_local(
                    provider="ollama",
                    model="qwen2.5:7b-instruct",
                    messages=[{"role": "user", "content": "test"}],
                    system=None,
                    max_tokens=512,
                    stream=False,
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


class TestProfileSwitching:
    def test_local_full_profile_resolves_to_ollama(self):
        with patch("app.config.settings.SENTINEL_ROUTING_PROFILE", "local_full"):
            with patch("app.services.model_gateway._settings_module.SENTINEL_ROUTING_PROFILE", "local_full"):
                gw = ModelGateway()
                mode, provider, model = gw._resolve("heavy")
                assert mode == "local"
                assert provider == "ollama"
                assert "deepseek" in model

    def test_cloud_dev_profile_resolves_to_ollama_cloud(self):
        with patch("app.services.model_gateway._settings_module.SENTINEL_ROUTING_PROFILE", "cloud_dev"):
            gw = ModelGateway()
            mode, provider, model = gw._resolve("medium")
            assert mode == "cloud"
            assert provider == "ollama_cloud"
