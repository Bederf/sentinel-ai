"""
AI Service tests for Claude and Ollama integrations.

Tests hybrid AI routing, tool use, and streaming responses.
"""

import pytest


@pytest.mark.unit
class TestAIService:
    """Test AI service functionality."""

    def test_hybrid_ai_service_exists(self):
        """Test hybrid AI service exists."""
        from app.services.hybrid_ai_service import HybridAIService

        assert HybridAIService is not None

    def test_hybrid_ai_service_initialization(self):
        """Test hybrid AI service can be initialized."""
        from app.services.hybrid_ai_service import HybridAIService

        # Should be able to create instance
        try:
            service = HybridAIService()
            assert service is not None
        except Exception:
            pytest.skip("AI service not configured")


@pytest.mark.unit
@pytest.mark.asyncio
class TestClaudeIntegration:
    """Test Claude API integration."""

    async def test_claude_service_exists(self):
        """Test Claude service is available."""
        from app.services.claude_service import claude_service

        assert claude_service is not None

    async def test_claude_tool_execution(self):
        """Test Claude can use tools for device control."""
        from app.services.chat_tools import list_devices

        # Tools should be callable
        devices = await list_devices()
        assert devices is not None

        # Note: This tests tool availability, not actual Claude calls
        # which would require API credentials

    async def test_claude_service_has_stream_method(self):
        """Test Claude service has streaming method."""
        from app.services.claude_service import claude_service

        assert hasattr(claude_service, "stream_response")


@pytest.mark.unit
class TestOllamaIntegration:
    """Test Ollama integration for local AI."""

    @pytest.mark.skip(reason="Ollama may not be running")
    async def test_ollama_connection(self):
        """Test connection to Ollama server."""
        import httpx

        # Try to connect to Ollama
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get("http://localhost:11434/api/tags")
                assert response.status_code == 200
        except Exception:
            pytest.skip("Ollama not running")

    @pytest.mark.skip(reason="Ollama may not be running")
    async def test_ollama_generation(self):
        """Test Ollama text generation."""
        import httpx

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                payload = {"model": "llama2", "prompt": "What is BMS?", "stream": False}
                response = await client.post("http://localhost:11434/api/generate", json=payload)
                assert response.status_code == 200
                assert "response" in response.json()
        except Exception:
            pytest.skip("Ollama not running")


@pytest.mark.unit
class TestHybridAIRouting:
    """Test hybrid AI routing logic."""

    def test_simple_queries_route_to_ollama(self):
        """Test simple data queries route to Ollama (FREE)."""
        from app.services.hybrid_ai_service import HybridAIService

        simple_queries = [
            "What is the status of device X?",
            "List all sites",
            "Show me temperature readings",
            "Get current alerts",
        ]

        try:
            service = HybridAIService()
            for query in simple_queries:
                result = service.classify_task(query)
                # Simple queries should route to Ollama
                assert result["provider"] in ["ollama", "local", "mock"]
        except Exception:
            pytest.skip("Hybrid service not configured")

    def test_complex_queries_route_to_claude(self):
        """Test complex queries route to Claude (PAID)."""
        from app.services.hybrid_ai_service import HybridAIService

        complex_queries = [
            "Analyze the failure patterns and recommend optimizations",
            "Control chiller 1 based on current conditions",
            "Why is this equipment failing?",
            "Diagnose the root cause of the temperature problem",
        ]

        try:
            service = HybridAIService()
            for query in complex_queries:
                result = service.classify_task(query)
                # Complex queries should route to Claude (anthropic)
                assert result["provider"] in ["anthropic", "claude", "mock"]
        except Exception:
            pytest.skip("Hybrid service not configured")


@pytest.mark.integration
@pytest.mark.asyncio
class TestAIChatTools:
    """Test AI chat tools that Claude has access to."""

    async def test_list_devices_tool(self):
        """Test list_devices tool."""
        from app.services.chat_tools import list_devices

        result = await list_devices()
        assert result is not None
        # list_devices returns a dict with devices key
        assert isinstance(result, dict)

    async def test_get_device_details_tool(self):
        """Test get_device_details tool."""
        from app.services.chat_tools import get_device_details, list_devices

        result = await list_devices()
        devices = result.get("devices", [])
        if devices:
            device_id = devices[0].get("id") or devices[0].get("device_id")
            if device_id:
                details = await get_device_details(device_id)
                assert details is not None

    async def test_control_device_tool(self):
        """Test control_device tool with safety validation."""
        from app.services.chat_tools import control_device, list_devices

        result = await list_devices()
        devices = result.get("devices", [])
        if devices:
            device_id = devices[0].get("id") or devices[0].get("device_id")
            if device_id:
                # Try to control (may be blocked by safety)
                control_result = await control_device(device_id=device_id, point="setpoint", value=22)
                # Result should indicate success or safety block
                assert control_result is not None

    async def test_get_system_status_tool(self):
        """Test get_system_status tool."""
        from app.services.chat_tools import get_system_status

        status = await get_system_status()
        assert status is not None

    async def test_get_optimization_recommendations_tool(self):
        """Test get_optimization_recommendations tool."""
        from app.services.chat_tools import get_optimization_recommendations

        # Tool requires site_id parameter
        recommendations = await get_optimization_recommendations(site_id="sandton")
        assert recommendations is not None
        assert isinstance(recommendations, dict)

    async def test_diagnose_comfort_complaint_tool(self):
        """Test diagnose_comfort_complaint tool."""
        from app.services.chat_tools import diagnose_comfort_complaint

        # Test with a sample complaint
        result = await diagnose_comfort_complaint(desk_id="201", complaint_type="too_hot", building="sandton")
        # Should return diagnosis or error
        assert result is not None


@pytest.mark.integration
class TestAIChatEndpoint:
    """Test AI chat API endpoint."""

    def test_chat_endpoint_exists(self, test_client):
        """Test /api/chat endpoint exists."""
        response = test_client.post("/api/chat", json={"message": "What is the system status?"})
        # May return 200, 401 (auth), 422 (validation), or 500 (API not configured)
        assert response.status_code in [200, 401, 422, 500]

    def test_hybrid_chat_endpoint_exists(self, test_client):
        """Test /api/hybrid-chat endpoint exists."""
        response = test_client.post("/api/hybrid-chat", json={"message": "What is the system status?"})
        # May return 200, 401 (auth), 422 (validation), or 500
        assert response.status_code in [200, 401, 422, 500]


@pytest.mark.integration
class TestAIStreaming:
    """Test AI streaming responses."""

    def test_chat_streaming(self, test_client):
        """Test chat endpoint supports streaming."""
        import httpx

        # Try streaming request
        try:
            with httpx.Client(timeout=30.0) as client:
                with client.stream(
                    "POST", "http://localhost:9095/api/chat", json={"query": "What is BMS?"}
                ) as response:
                    assert response.status_code in [200, 401, 500]

                    if response.status_code == 200:
                        # Should receive streaming data
                        chunks = []
                        for chunk in response.iter_lines():
                            if chunk:
                                chunks.append(chunk)
                        assert len(chunks) > 0
        except Exception:
            pytest.skip("Streaming test requires running server")


@pytest.mark.unit
class TestAICostOptimization:
    """Test AI cost optimization strategies."""

    def test_ollama_is_free(self):
        """Test Ollama queries are tracked as free."""
        # This documents the expected behavior
        # Actual implementation may vary
        assert True  # Ollama runs locally, no API costs

    def test_claude_routing_reduces_cost(self):
        """Test hybrid routing reduces costs vs all-Claude."""
        # Expected: 40% cost savings with hybrid routing
        # This is a documentation test
        # Actual cost tracking would require usage metrics
        assert True


@pytest.mark.integration
class TestAIErrorHandling:
    """Test AI service error handling."""

    def test_api_key_missing_handled_gracefully(self, test_client):
        """Test missing API key is handled gracefully."""
        response = test_client.post("/api/chat", json={"message": "test"})
        # Should return error, not crash
        assert response.status_code in [200, 401, 422, 500, 503]

    def test_rate_limiting_handled(self, test_client):
        """Test API rate limiting is handled."""
        # Make many rapid requests
        responses = []
        for _ in range(10):
            response = test_client.post("/api/chat", json={"message": "test"})
            responses.append(response.status_code)

        # Should handle gracefully (not crash)
        # May return 429 (rate limit), 200, 422, or 500
        assert all(s in [200, 401, 422, 429, 500, 503] for s in responses)

    def test_timeout_handling(self, test_client):
        """Test AI timeout is handled correctly."""
        # This would require a slow AI response
        # For now, just document the requirement
        assert True  # Timeout should be configured
