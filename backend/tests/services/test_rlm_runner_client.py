"""Tests for RLMRunnerClient — Sentinel ↔ RLM runner integration.

Phase: 113-03, Task 1
"""

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.services.rlm_runner_client import (
    RLMRunnerClient,
    RLMRunnerDisabledError,
    RLMRunnerUnavailableError,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_client(enabled: bool = True, base_url: str = "http://127.0.0.1:8010") -> RLMRunnerClient:
    """Create a client with explicit settings (avoids global config)."""
    return RLMRunnerClient(base_url=base_url, enabled=enabled, timeout=30)


def _mock_response(status_code: int, json_data: dict) -> httpx.Response:
    """Build an httpx.Response with a request attached (required for raise_for_status)."""
    request = httpx.Request("GET", "http://127.0.0.1:8010/test")
    return httpx.Response(status_code=status_code, json=json_data, request=request)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
class TestRLMRunnerClient:
    """Unit tests for the RLM runner HTTP client."""

    async def test_submit_run_success(self):
        """Mock httpx POST to runner, verify request body and run_id returned."""
        client = _make_client(enabled=True)

        mock_response = _mock_response(
            200,
            {"run_id": "TEST001_20260223_083012_ab12cd34", "status": "queued"},
        )

        with patch("app.services.rlm_runner_client.httpx.AsyncClient") as MockClient:
            mock_instance = AsyncMock()
            mock_instance.post = AsyncMock(return_value=mock_response)
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_instance

            result = await client.submit_run(
                case_id="TEST001",
                question="Summarise key findings",
                model="phi3:mini",
            )

            assert result["run_id"] == "TEST001_20260223_083012_ab12cd34"
            assert result["status"] == "queued"

            # Verify the POST body
            call_args = mock_instance.post.call_args
            assert call_args[1]["json"]["case_id"] == "TEST001"
            assert call_args[1]["json"]["question"] == "Summarise key findings"
            assert call_args[1]["json"]["model"] == "phi3:mini"

    async def test_submit_run_runner_unavailable(self):
        """Mock connection error -> raises RLMRunnerUnavailableError."""
        client = _make_client(enabled=True)

        with patch("app.services.rlm_runner_client.httpx.AsyncClient") as MockClient:
            mock_instance = AsyncMock()
            mock_instance.post = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_instance

            with pytest.raises(RLMRunnerUnavailableError):
                await client.submit_run(case_id="TEST001", question="Test")

    async def test_get_result_found(self):
        """Mock GET returns result dict."""
        client = _make_client(enabled=True)

        result_data = {
            "status": "complete",
            "summary": "Analysis complete.",
            "findings": [{"id": 1, "text": "Finding 1"}],
            "confidence": 0.85,
        }
        mock_response = _mock_response(200, result_data)

        with patch("app.services.rlm_runner_client.httpx.AsyncClient") as MockClient:
            mock_instance = AsyncMock()
            mock_instance.get = AsyncMock(return_value=mock_response)
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_instance

            result = await client.get_result("TEST001_20260223_083012_ab12cd34")
            assert result is not None
            assert result["status"] == "complete"
            assert result["confidence"] == 0.85

    async def test_get_result_not_found(self):
        """Mock 404 -> returns None."""
        client = _make_client(enabled=True)

        mock_response = _mock_response(404, {"detail": "Not found"})

        with patch("app.services.rlm_runner_client.httpx.AsyncClient") as MockClient:
            mock_instance = AsyncMock()
            mock_instance.get = AsyncMock(return_value=mock_response)
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_instance

            result = await client.get_result("NONEXISTENT_run_id")
            assert result is None

    async def test_poll_until_complete(self):
        """Mock first call returns 'running', second returns 'complete'."""
        client = _make_client(enabled=True)

        running_response = _mock_response(
            200,
            {"status": "running", "summary": None},
        )
        complete_response = _mock_response(
            200,
            {"status": "complete", "summary": "Done", "confidence": 0.9},
        )

        call_count = 0

        async def mock_get(url):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return running_response
            return complete_response

        with patch("app.services.rlm_runner_client.httpx.AsyncClient") as MockClient:
            mock_instance = AsyncMock()
            mock_instance.get = mock_get
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_instance

            with patch("app.services.rlm_runner_client.asyncio.sleep", new_callable=AsyncMock):
                result = await client.poll_until_complete(
                    "TEST001_20260223_083012_ab12cd34",
                    interval=0.01,
                    timeout=10.0,
                )
                assert result["status"] == "complete"
                assert call_count == 2

    async def test_disabled_raises(self):
        """Set RLM_RUNNER_ENABLED=False, verify RuntimeError on submit."""
        client = _make_client(enabled=False)

        with pytest.raises(RLMRunnerDisabledError, match="not enabled"):
            await client.submit_run(case_id="TEST001", question="Test")

        with pytest.raises(RLMRunnerDisabledError, match="not enabled"):
            await client.get_result("some_run_id")

        with pytest.raises(RLMRunnerDisabledError, match="not enabled"):
            await client.get_trace("some_run_id")
