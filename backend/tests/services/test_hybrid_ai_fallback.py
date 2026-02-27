"""
Test cases for Hybrid AI Service cloud-to-cloud fallback mechanism.

Verifies that transient API errors (500, 502, 503, timeouts, connection failures)
automatically trigger fallback to the next cloud provider, ensuring system resilience.

Provider architecture:
  - anthropic: Claude (tool support)
  - openai: GPT-4.1 nano/mini (tool support, tiered models)
  - zai: Z.ai GLM (advisory only, NO tool support)

Fallback chains:
  - anthropic → openai → zai
  - openai → anthropic → zai
  - zai → openai → anthropic
"""

import pytest
from unittest.mock import MagicMock, patch
from anthropic import APIError, APIConnectionError, APITimeoutError, RateLimitError
import httpx

from app.services.hybrid_ai_service import HybridAIService


def _create_api_error(message: str) -> APIError:
    """Helper to create APIError with proper signature."""
    mock_request = MagicMock(spec=httpx.Request)
    mock_request.method = "POST"
    mock_request.url = "https://api.anthropic.com/v1/messages"
    return APIError(message=message, request=mock_request, body=None)


def _create_connection_error(message: str) -> APIConnectionError:
    """Helper to create APIConnectionError."""
    mock_request = MagicMock(spec=httpx.Request)
    mock_request.url = "https://api.anthropic.com/v1/messages"
    return APIConnectionError(request=mock_request, message=message)


def _create_timeout_error() -> APITimeoutError:
    """Helper to create APITimeoutError."""
    mock_request = MagicMock(spec=httpx.Request)
    mock_request.url = "https://api.anthropic.com/v1/messages"
    return APITimeoutError(request=mock_request)


def _create_rate_limit_error(message: str) -> RateLimitError:
    """Helper to create RateLimitError."""
    mock_request = MagicMock(spec=httpx.Request)
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 429
    mock_response.headers = {"request-id": "test_123"}
    return RateLimitError(message=message, response=mock_response, body=None)


def _mock_async_generator(*chunks):
    """Create a mock async generator that yields given chunks."""

    async def _gen(*args, **kwargs):
        for chunk in chunks:
            yield chunk

    return _gen


class TestCloudFallback:
    """Test automatic fallback between cloud providers."""

    @pytest.fixture
    def hybrid_ai(self):
        """Create HybridAIService instance for testing."""
        return HybridAIService()

    @pytest.mark.asyncio
    async def test_primary_success_no_fallback(self, hybrid_ai):
        """Successful primary provider response — no fallback triggered."""
        with patch.object(
            hybrid_ai,
            "_stream_from_provider",
            side_effect=_mock_async_generator("Building occupancy is 56%"),
        ) as mock_stream:
            chunks = []
            async for chunk in hybrid_ai.stream_response("What is the building occupancy?"):
                chunks.append(chunk)

            assert "56%" in "".join(chunks)

    @pytest.mark.asyncio
    async def test_fallback_on_primary_error(self, hybrid_ai):
        """When primary fails, fallback provider responds."""
        call_count = 0

        async def _mock_stream(provider, messages, include_building_context=True, tier=2):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("Primary provider down")
            yield "Fallback response from second provider"

        with patch.object(hybrid_ai, "_stream_from_provider", side_effect=_mock_stream):
            chunks = []
            async for chunk in hybrid_ai._try_cloud_with_fallback("test query"):
                chunks.append(chunk)

            assert "Fallback response" in "".join(chunks)
            assert call_count == 2

    @pytest.mark.asyncio
    async def test_all_providers_fail_graceful_message(self, hybrid_ai):
        """When ALL providers fail, user sees a friendly error."""

        async def _always_fail(provider, messages, include_building_context=True, tier=2):
            raise Exception(f"{provider} unavailable")
            yield  # Make it an async generator  # noqa: E501  (unreachable but needed for type)

        with patch.object(hybrid_ai, "_stream_from_provider", side_effect=_always_fail):
            chunks = []
            async for chunk in hybrid_ai._try_cloud_with_fallback("test"):
                chunks.append(chunk)

            full = "".join(chunks)
            assert "trouble" in full.lower() or "try again" in full.lower()

    @pytest.mark.asyncio
    async def test_tool_request_rejected_for_zai(self, hybrid_ai):
        """Z.ai (no tool support) with tools → routes to tool-capable fallback or rejects."""
        with patch.object(hybrid_ai, "get_active_cloud_provider", return_value="zai"):
            # No tool-capable provider configured
            with (
                patch("app.services.hybrid_ai_service.openai_service") as mock_oai,
                patch("app.services.hybrid_ai_service.claude_service") as mock_claude,
            ):
                mock_oai.is_configured.return_value = False
                mock_claude.is_configured.return_value = False

                chunks = []
                async for chunk in hybrid_ai.stream_response("Turn off AHU-7", use_tools=True):
                    chunks.append(chunk)

                full = "".join(chunks)
                assert "tool-capable" in full.lower() or "advisory" in full.lower()

    @pytest.mark.asyncio
    async def test_tool_request_reroutes_to_openai_when_zai_primary(self, hybrid_ai):
        """Z.ai primary + tools → automatically routes to OpenAI if configured."""
        with (
            patch.object(hybrid_ai, "get_active_cloud_provider", return_value="zai"),
            patch("app.services.hybrid_ai_service.openai_service") as mock_oai,
            patch.object(
                hybrid_ai, "_stream_tools_from_provider", side_effect=_mock_async_generator("Tool response via OpenAI")
            ),
        ):
            mock_oai.is_configured.return_value = True

            chunks = []
            async for chunk in hybrid_ai.stream_response("Turn off lights", use_tools=True):
                chunks.append(chunk)

            full = "".join(chunks)
            assert "Tool response" in full

    @pytest.mark.asyncio
    async def test_tool_fallback_on_claude_api_error(self, hybrid_ai):
        """Claude tool calling fails → falls back to OpenAI tools."""
        call_count = 0

        async def _mock_tools(provider, messages):
            nonlocal call_count
            call_count += 1
            if provider == "anthropic":
                raise _create_api_error("Internal server error")
            yield "OpenAI handled the tool call"

        with (
            patch.object(hybrid_ai, "get_active_cloud_provider", return_value="anthropic"),
            patch.object(hybrid_ai, "_stream_tools_from_provider", side_effect=_mock_tools),
            patch("app.services.hybrid_ai_service.openai_service") as mock_oai,
        ):
            mock_oai.is_configured.return_value = True

            chunks = []
            async for chunk in hybrid_ai.stream_response("Adjust setpoint", use_tools=True):
                chunks.append(chunk)

            full = "".join(chunks)
            assert "OpenAI handled" in full

    @pytest.mark.asyncio
    async def test_rate_limit_on_claude_falls_back(self, hybrid_ai):
        """Claude rate limit during tool call → falls back to OpenAI."""
        call_count = 0

        async def _mock_tools(provider, messages):
            nonlocal call_count
            call_count += 1
            if provider == "anthropic":
                raise _create_rate_limit_error("Rate limit exceeded")
            yield "OpenAI fallback response"

        with (
            patch.object(hybrid_ai, "get_active_cloud_provider", return_value="anthropic"),
            patch.object(hybrid_ai, "_stream_tools_from_provider", side_effect=_mock_tools),
            patch("app.services.hybrid_ai_service.openai_service") as mock_oai,
        ):
            mock_oai.is_configured.return_value = True

            chunks = []
            async for chunk in hybrid_ai.stream_response("Check device", use_tools=True):
                chunks.append(chunk)

            full = "".join(chunks)
            assert "OpenAI fallback" in full

    @pytest.mark.asyncio
    async def test_non_tool_path_uses_cloud_fallback_chain(self, hybrid_ai):
        """Non-tool advisory query uses _try_cloud_with_fallback."""
        with patch.object(
            hybrid_ai,
            "_try_cloud_with_fallback",
            side_effect=_mock_async_generator("Advisory response"),
        ):
            chunks = []
            async for chunk in hybrid_ai.stream_response(
                "Why is AHU-7 showing degradation?",
                use_tools=False,
            ):
                chunks.append(chunk)

            assert "Advisory response" in "".join(chunks)


class TestTieredModelSelection:
    """Test that OpenAI uses different models for different tiers."""

    @pytest.fixture
    def hybrid_ai(self):
        return HybridAIService()

    def test_tier1_uses_nano(self, hybrid_ai):
        """Tier 1 simple queries use gpt-4.1-nano."""
        with patch.object(hybrid_ai, "get_active_cloud_provider", return_value="openai"):
            routing = hybrid_ai.classify_task("What does error code E123 mean?")
            assert routing["tier"] == 1
            assert "nano" in routing["model"]

    def test_tier2_uses_mini(self, hybrid_ai):
        """Tier 2 complex queries use gpt-4.1-mini."""
        with patch.object(hybrid_ai, "get_active_cloud_provider", return_value="openai"):
            routing = hybrid_ai.classify_task("Why is AHU-7 showing bearing degradation?")
            assert routing["tier"] == 2
            assert "mini" in routing["model"]

    def test_control_action_is_tier2(self, hybrid_ai):
        """Control actions always classify as Tier 2 (needs capable model)."""
        routing = hybrid_ai.classify_task("Turn off AHU-7")
        assert routing["tier"] == 2
        assert "safety critical" in routing["reason"].lower()


class TestProviderConfiguration:
    """Test provider configuration and capability detection."""

    @pytest.fixture
    def hybrid_ai(self):
        return HybridAIService()

    def test_tool_capable_providers(self, hybrid_ai):
        """anthropic and openai support tools; zai does not."""
        assert hybrid_ai.provider_supports_tools("anthropic") is True
        assert hybrid_ai.provider_supports_tools("openai") is True
        assert hybrid_ai.provider_supports_tools("zai") is False

    def test_get_active_provider_reads_settings(self, hybrid_ai):
        """Provider comes from settings.ai_cloud_provider."""
        provider = hybrid_ai.get_active_cloud_provider()
        assert provider in {"anthropic", "openai", "zai"}

    def test_fallback_order_excludes_primary(self, hybrid_ai):
        """Fallback list never includes the primary provider."""
        for primary in ["anthropic", "openai", "zai"]:
            fallbacks = hybrid_ai._get_fallback_providers(primary)
            assert primary not in fallbacks
            assert len(fallbacks) == 2


class TestRateLimitTracking:
    """Test rate limit tracking and cooldown behavior."""

    @pytest.fixture
    def hybrid_ai(self):
        service = HybridAIService()
        service.claude_rate_limited = False
        service.rate_limit_time = 0
        return service

    @pytest.mark.asyncio
    async def test_rate_limit_triggers_cooldown(self, hybrid_ai):
        """Rate limit error on Claude sets cooldown flag."""
        # Simulate Claude rate limit via _try_cloud_with_fallback
        call_count = 0

        async def _mock_stream(provider, messages, include_building_context=True, tier=2):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # Primary = anthropic, raise rate limit
                raise _create_rate_limit_error("Rate limit exceeded")
            yield "Fallback response"

        with (
            patch.object(hybrid_ai, "get_active_cloud_provider", return_value="anthropic"),
            patch.object(hybrid_ai, "_stream_from_provider", side_effect=_mock_stream),
        ):
            chunks = []
            async for chunk in hybrid_ai._try_cloud_with_fallback("test"):
                chunks.append(chunk)

            assert hybrid_ai.claude_rate_limited is True
            assert hybrid_ai.rate_limit_time > 0


class TestErrorClassification:
    """Test error classification and routing decisions."""

    @pytest.fixture
    def hybrid_ai(self):
        return HybridAIService()

    def test_classify_tier1_simple_lookup(self, hybrid_ai):
        """Tier 1 for simple queries, routed to active provider."""
        routing = hybrid_ai.classify_task("What does error code E123 mean?")
        assert routing["tier"] == 1
        assert routing["provider"] == hybrid_ai.get_active_cloud_provider()
        assert routing["estimated_cost"] >= 0

    def test_classify_tier2_complex_reasoning(self, hybrid_ai):
        """Tier 2 for complex queries."""
        routing = hybrid_ai.classify_task("Why is AHU-7 showing bearing degradation?")
        assert routing["tier"] == 2
        assert routing["provider"] == hybrid_ai.get_active_cloud_provider()
        assert routing["estimated_cost"] > 0

    def test_classify_tier2_control_action(self, hybrid_ai):
        """Control actions always Tier 2 (safety critical)."""
        routing = hybrid_ai.classify_task("Turn off AHU-7")
        assert routing["tier"] == 2
        assert routing["provider"] == hybrid_ai.get_active_cloud_provider()
        assert "safety critical" in routing["reason"].lower()
