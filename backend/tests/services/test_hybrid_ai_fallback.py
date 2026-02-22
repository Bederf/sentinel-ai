"""
Test cases for Hybrid AI Service fallback mechanism.

Verifies that transient API errors (500, 502, 503, timeouts, connection failures)
automatically trigger fallback to local Ollama AI, ensuring system resilience.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
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
    """Helper to create APIConnectionError with proper signature."""
    mock_request = MagicMock(spec=httpx.Request)
    mock_request.url = "https://api.anthropic.com/v1/messages"
    return APIConnectionError(request=mock_request, message=message)


def _create_timeout_error() -> APITimeoutError:
    """Helper to create APITimeoutError with proper signature."""
    mock_request = MagicMock(spec=httpx.Request)
    mock_request.url = "https://api.anthropic.com/v1/messages"
    return APITimeoutError(request=mock_request)


def _create_rate_limit_error(message: str) -> RateLimitError:
    """Helper to create RateLimitError with proper signature."""
    mock_request = MagicMock(spec=httpx.Request)
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 429
    mock_response.headers = {"request-id": "test_123"}
    return RateLimitError(message=message, response=mock_response, body=None)


class TestHybridAIFallback:
    """Test automatic fallback to Ollama on Claude API failures."""

    @pytest.fixture
    def hybrid_ai(self):
        """Create HybridAIService instance for testing."""
        return HybridAIService()

    @pytest.mark.asyncio
    async def test_fallback_on_api_error_500(self, hybrid_ai):
        """Test fallback to Ollama when Claude returns 500 Internal Server Error."""
        message = "Why is AHU-7 showing bearing degradation?"  # Tier 2 query to ensure Claude routing

        # Mock Claude to raise 500 error
        mock_api_error = _create_api_error("Internal server error")

        with patch("app.services.hybrid_ai_service.claude_service") as mock_claude:
            # Claude raises APIError
            mock_claude.stream_response.side_effect = mock_api_error

            # Mock Ollama to succeed
            with patch.object(hybrid_ai, "query_ollama", new_callable=AsyncMock) as mock_ollama:
                mock_ollama_response = "Here are optimization recommendations from Ollama..."
                mock_ollama.return_value = mock_ollama_response

                # Collect response chunks
                response_chunks = []
                async for chunk in hybrid_ai.stream_response(message, use_tools=False):
                    response_chunks.append(chunk)

                full_response = "".join(response_chunks)

                # Verify Ollama was called as fallback
                mock_ollama.assert_called_once()
                assert "Claude unavailable" in full_response
                assert "Ollama" in full_response or mock_ollama_response in full_response

    @pytest.mark.asyncio
    async def test_fallback_on_api_connection_error(self, hybrid_ai):
        """Test fallback to Ollama when Claude connection fails."""
        message = "Diagnose the chiller refrigerant leak"  # Tier 2 query

        # Mock connection error
        mock_conn_error = _create_connection_error("Connection to api.anthropic.com failed")

        with patch("app.services.hybrid_ai_service.claude_service") as mock_claude:
            mock_claude.stream_response.side_effect = mock_conn_error

            # Mock Ollama to succeed
            with patch.object(hybrid_ai, "query_ollama", new_callable=AsyncMock) as mock_ollama:
                mock_ollama.return_value = "AHU-7 status: Online, 72% health"

                response_chunks = []
                async for chunk in hybrid_ai.stream_response(message, use_tools=False):
                    response_chunks.append(chunk)

                full_response = "".join(response_chunks)

                # Verify fallback occurred
                mock_ollama.assert_called_once()
                assert "Claude unavailable" in full_response
                assert "AHU-7" in full_response

    @pytest.mark.asyncio
    async def test_fallback_on_api_timeout(self, hybrid_ai):
        """Test fallback to Ollama when Claude request times out."""
        message = "Diagnose comfort complaint at Desk 25"

        # Mock timeout error
        mock_timeout = _create_timeout_error()

        with patch("app.services.hybrid_ai_service.claude_service") as mock_claude:
            mock_claude.stream_response.side_effect = mock_timeout

            with patch.object(hybrid_ai, "query_ollama", new_callable=AsyncMock) as mock_ollama:
                mock_ollama.return_value = "Desk 25 is in Zone L1-A with temperature 24°C"

                response_chunks = []
                async for chunk in hybrid_ai.stream_response(message, use_tools=False):
                    response_chunks.append(chunk)

                full_response = "".join(response_chunks)

                mock_ollama.assert_called_once()
                assert "timeout" in full_response.lower() or "unavailable" in full_response.lower()
                assert "Desk 25" in full_response

    @pytest.mark.asyncio
    async def test_fallback_on_rate_limit(self, hybrid_ai):
        """Test fallback to Ollama when rate limit is hit."""
        message = "Analyze why the chiller efficiency is dropping"  # Tier 2 query

        # Mock rate limit error
        mock_rate_limit = _create_rate_limit_error("Rate limit exceeded")

        with patch("app.services.hybrid_ai_service.claude_service") as mock_claude:
            mock_claude.stream_response.side_effect = mock_rate_limit

            with patch.object(hybrid_ai, "query_ollama", new_callable=AsyncMock) as mock_ollama:
                mock_ollama.return_value = "Equipment: CH-1, CH-2, CH-3, AHU-7..."

                response_chunks = []
                async for chunk in hybrid_ai.stream_response(message, use_tools=False):
                    response_chunks.append(chunk)

                full_response = "".join(response_chunks)

                mock_ollama.assert_called_once()
                assert "rate limited" in full_response.lower()

    @pytest.mark.asyncio
    async def test_fallback_with_tools_on_api_error(self, hybrid_ai):
        """Test fallback behavior when tool calling and Claude API fails."""
        message = "Turn off lights in Conference Room A"

        mock_api_error = _create_api_error("Internal server error")

        with patch("app.services.hybrid_ai_service.claude_service") as mock_claude:
            mock_claude.stream_response_with_tools.side_effect = mock_api_error

            response_chunks = []
            async for chunk in hybrid_ai.stream_response(message, use_tools=True):
                response_chunks.append(chunk)

            full_response = "".join(response_chunks)

            # Should show friendly error message (tool-based actions unavailable)
            assert "unavailable" in full_response.lower() or "try again" in full_response.lower()

    @pytest.mark.asyncio
    async def test_fallback_ollama_also_fails(self, hybrid_ai):
        """Test graceful handling when both Claude and Ollama fail."""
        message = "Predict when UPS-1 will fail based on current trends"  # Tier 2 query

        mock_api_error = _create_api_error("Internal server error")

        with patch("app.services.hybrid_ai_service.claude_service") as mock_claude:
            mock_claude.stream_response.side_effect = mock_api_error

            # Mock Ollama to also fail
            with patch.object(hybrid_ai, "query_ollama", new_callable=AsyncMock) as mock_ollama:
                mock_ollama.side_effect = Exception("Ollama service unavailable")

                response_chunks = []
                async for chunk in hybrid_ai.stream_response(message, use_tools=False):
                    response_chunks.append(chunk)

                full_response = "".join(response_chunks)

                # Should show user-friendly error message
                assert "trouble" in full_response.lower()
                assert "try again" in full_response.lower()

    @pytest.mark.asyncio
    async def test_no_fallback_on_programming_error(self, hybrid_ai):
        """Test that programming errors are NOT caught by fallback mechanism."""
        message = "Diagnose the HVAC problem"  # Tier 2 query to ensure Claude routing

        # Mock a ValueError (programming error, not API error)
        with patch("app.services.hybrid_ai_service.claude_service") as mock_claude:
            mock_claude.stream_response.side_effect = ValueError("Invalid input format")

            # Should raise the error, not fall back to Ollama
            with pytest.raises(ValueError, match="Invalid input format"):
                async for _ in hybrid_ai.stream_response(message, use_tools=False):
                    pass

            # Should raise the error, not fall back to Ollama
            with pytest.raises(ValueError, match="Invalid input format"):
                async for _ in hybrid_ai.stream_response(message, use_tools=False):
                    pass

    @pytest.mark.asyncio
    async def test_claude_success_no_fallback(self, hybrid_ai):
        """Test that successful Claude responses don't trigger fallback."""
        message = "What is the building occupancy?"  # This might route to Ollama, so override

        # Mock Claude to succeed
        with patch("app.services.hybrid_ai_service.claude_service") as mock_claude:

            async def mock_stream(*args, **kwargs):
                yield "Building occupancy is 56%"

            mock_claude.stream_response.return_value = mock_stream()

            # Mock Ollama (should NOT be called)
            with patch.object(hybrid_ai, "query_ollama", new_callable=AsyncMock) as mock_ollama:
                response_chunks = []
                async for chunk in hybrid_ai.stream_response(message, use_tools=False):
                    response_chunks.append(chunk)

                full_response = "".join(response_chunks)

                # Verify Claude was used, not Ollama
                mock_ollama.assert_not_called()
                assert "56%" in full_response
                assert "Ollama" not in full_response

    @pytest.mark.asyncio
    async def test_fallback_message_format(self, hybrid_ai):
        """Test that fallback message includes error type and model used."""
        message = "Optimize the HVAC setpoints for energy savings"  # Tier 2 query

        mock_api_error = _create_api_error("Service unavailable")

        with patch("app.services.hybrid_ai_service.claude_service") as mock_claude:
            mock_claude.stream_response.side_effect = mock_api_error

            with patch.object(hybrid_ai, "query_ollama", new_callable=AsyncMock) as mock_ollama:
                mock_ollama.return_value = "Response from local AI"

                response_chunks = []
                async for chunk in hybrid_ai.stream_response(message, use_tools=False):
                    response_chunks.append(chunk)

                full_response = "".join(response_chunks)

                # Verify message format: [Claude unavailable (ErrorType) - using model]
                assert "[Claude unavailable" in full_response
                assert "APIError" in full_response
                assert "using" in full_response
                assert "Response from local AI" in full_response

    @pytest.mark.asyncio
    async def test_fallback_model_selection_tier1(self, hybrid_ai):
        """Test that Tier 1 (simple) queries use fast Ollama model on fallback."""
        message = "What does error code E123 mean?"  # Simple lookup - but we need Tier 2 for Claude routing

        mock_api_error = _create_api_error("Internal server error")

        with patch("app.services.hybrid_ai_service.claude_service") as mock_claude:
            mock_claude.stream_response.side_effect = mock_api_error

            with patch.object(hybrid_ai, "query_ollama", new_callable=AsyncMock) as mock_ollama:
                mock_ollama.return_value = "Error E123: Temperature sensor fault"

                # Override classification to force Tier 2 for this test
                with patch.object(
                    hybrid_ai,
                    "classify_task",
                    return_value={
                        "provider": "anthropic",
                        "model": "claude-sonnet-4-20250514",
                        "reason": "Forced to Claude for test",
                        "estimated_cost": 0.0105,
                        "tier": 2,
                    },
                ):
                    async for _ in hybrid_ai.stream_response(message, use_tools=False):
                        pass

                # Should use balanced model for forced Tier 2
                call_args = mock_ollama.call_args
                assert call_args[1]["model"] == "phi3:mini"  # Balanced model

        with patch("app.services.hybrid_ai_service.claude_service") as mock_claude:
            mock_claude.stream_response.side_effect = mock_api_error

            with patch.object(hybrid_ai, "query_ollama", new_callable=AsyncMock) as mock_ollama:
                mock_ollama.return_value = "Error E123: Temperature sensor fault"

                async for _ in hybrid_ai.stream_response(message, use_tools=False):
                    pass

                # Should use fast model for Tier 1 queries
                call_args = mock_ollama.call_args
                assert call_args[1]["model"] == "llama3.2:1b"  # Fast model

    @pytest.mark.asyncio
    async def test_fallback_model_selection_tier2(self, hybrid_ai):
        """Test that Tier 2 (complex) queries use balanced Ollama model on fallback."""
        message = "Why is AHU-7 showing bearing degradation?"  # Complex reasoning

        mock_api_error = _create_api_error("Internal server error")

        with patch("app.services.hybrid_ai_service.claude_service") as mock_claude:
            mock_claude.stream_response.side_effect = mock_api_error

            with patch.object(hybrid_ai, "query_ollama", new_callable=AsyncMock) as mock_ollama:
                mock_ollama.return_value = "Based on vibration analysis..."

                async for _ in hybrid_ai.stream_response(message, use_tools=False):
                    pass

                # Should use balanced model for Tier 2 queries
                call_args = mock_ollama.call_args
                assert call_args[1]["model"] == "phi3:mini"  # Balanced model

    @pytest.mark.asyncio
    async def test_fallback_prevents_escalation(self, hybrid_ai):
        """Test that Ollama fallback doesn't escalate back to Claude."""
        message = "Show me equipment health"  # This routes to Ollama (Tier 1), so override classification

        mock_api_error = _create_api_error("Internal server error")

        with patch("app.services.hybrid_ai_service.claude_service") as mock_claude:
            mock_claude.stream_response.side_effect = mock_api_error

            with patch.object(hybrid_ai, "query_ollama", new_callable=AsyncMock) as mock_ollama:
                mock_ollama.return_value = "Equipment health data..."

                # Override classification to force Tier 2 for this test
                with patch.object(
                    hybrid_ai,
                    "classify_task",
                    return_value={
                        "provider": "anthropic",
                        "model": "claude-sonnet-4-20250514",
                        "reason": "Forced to Claude for test",
                        "estimated_cost": 0.0105,
                        "tier": 2,
                    },
                ):
                    async for _ in hybrid_ai.stream_response(message, use_tools=False):
                        pass

                # Verify Ollama was called with escalate_on_fail=False
                call_args = mock_ollama.call_args
                assert call_args[1]["escalate_on_fail"] is False

                # Claude should only be called once (the failed attempt)
                assert mock_claude.stream_response.call_count == 1

        with patch("app.services.hybrid_ai_service.claude_service") as mock_claude:
            mock_claude.stream_response.side_effect = mock_api_error

            with patch.object(hybrid_ai, "query_ollama", new_callable=AsyncMock) as mock_ollama:
                mock_ollama.return_value = "Equipment health data..."

                async for _ in hybrid_ai.stream_response(message, use_tools=False):
                    pass

                # Verify Ollama was called with escalate_on_fail=False
                call_args = mock_ollama.call_args
                assert call_args[1]["escalate_on_fail"] is False

                # Claude should only be called once (the failed attempt)
                assert mock_claude.stream_response.call_count == 1


class TestRateLimitTracking:
    """Test rate limit tracking and cooldown behavior."""

    @pytest.fixture
    def hybrid_ai(self):
        """Create HybridAIService instance."""
        service = HybridAIService()
        # Reset rate limit state
        service.claude_rate_limited = False
        service.rate_limit_time = 0
        return service

    @pytest.mark.asyncio
    async def test_rate_limit_triggers_cooldown(self, hybrid_ai):
        """Test that rate limit error sets cooldown flag."""
        mock_rate_limit = _create_rate_limit_error("Rate limit exceeded")

        with patch("app.services.hybrid_ai_service.claude_service") as mock_claude:
            mock_claude.stream_response.side_effect = mock_rate_limit

            with patch.object(hybrid_ai, "query_ollama", new_callable=AsyncMock) as mock_ollama:
                mock_ollama.return_value = "Fallback response"

                async for _ in hybrid_ai.stream_response("test", use_tools=False):
                    pass

                # Verify rate limit state was set
                assert hybrid_ai.claude_rate_limited is True
                assert hybrid_ai.rate_limit_time > 0


class TestErrorClassification:
    """Test error classification and routing decisions."""

    @pytest.fixture
    def hybrid_ai(self):
        """Create HybridAIService instance."""
        return HybridAIService()

    def test_classify_tier1_simple_lookup(self, hybrid_ai):
        """Test classification of Tier 1 (simple) queries."""
        routing = hybrid_ai.classify_task("What does error code E123 mean?")
        assert routing["tier"] == 1
        assert routing["provider"] == "ollama"
        assert routing["estimated_cost"] == 0.0

    def test_classify_tier2_complex_reasoning(self, hybrid_ai):
        """Test classification of Tier 2 (complex) queries."""
        routing = hybrid_ai.classify_task("Why is AHU-7 showing bearing degradation?")
        assert routing["tier"] == 2
        assert routing["provider"] == "anthropic"
        assert routing["estimated_cost"] > 0

    def test_classify_tier2_control_action(self, hybrid_ai):
        """Test classification of control actions."""
        routing = hybrid_ai.classify_task("Turn off AHU-7")
        assert routing["tier"] == 2
        assert routing["provider"] == "anthropic"
        assert "safety critical" in routing["reason"]
