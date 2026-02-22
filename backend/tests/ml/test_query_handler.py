"""Tests for the query handler service (Phase 44-03)."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.query_handler import QueryHandler


@pytest.fixture
def mock_equipment_repo():
    repo = MagicMock()
    repo.get_by_id.return_value = {
        "id": "uuid-001",
        "code": "S002-CHILLER-B1-001",
        "name": "Chiller 1",
        "type": "chiller",
        "health_score": 72,
        "status": "running",
        "risk_level": "medium",
        "last_maintenance": "2025-12-15",
        "rul_days": 45,
    }
    return repo


@pytest.fixture
def mock_alert_repo():
    repo = MagicMock()
    repo.get_active_by_equipment.return_value = [
        {
            "id": "alert-001",
            "severity": "WARNING",
            "message": "Vibration levels elevated",
            "equipment_code": "S002-CHILLER-B1-001",
        }
    ]
    return repo


@pytest.fixture
def handler(mock_equipment_repo, mock_alert_repo):
    h = QueryHandler()
    h.equipment_repo = mock_equipment_repo
    h.alert_repo = mock_alert_repo
    return h


class TestQueryHandlerClassification:
    """Test that queries are correctly classified and routed."""

    @pytest.mark.asyncio
    async def test_prediction_query_classification(self, handler):
        with patch.object(handler.ollama, "is_available", new_callable=AsyncMock, return_value=False):
            with patch("app.services.query_handler.get_rag_service", return_value=None):
                result = await handler.handle_query("Why is S002-CHILLER-B1-001 predicted to fail?")
        assert result["intent"] == "why_prediction"
        assert "S002-CHILLER-B1-001" in result["equipment_ids"]

    @pytest.mark.asyncio
    async def test_maintenance_query_classification(self, handler):
        with patch.object(handler.ollama, "is_available", new_callable=AsyncMock, return_value=False):
            with patch("app.services.query_handler.get_rag_service", return_value=None):
                result = await handler.handle_query("When is maintenance due for S002-CHILLER-B1-001?")
        assert result["intent"] == "maintenance_due"

    @pytest.mark.asyncio
    async def test_status_query_classification(self, handler):
        with patch.object(handler.ollama, "is_available", new_callable=AsyncMock, return_value=False):
            with patch("app.services.query_handler.get_rag_service", return_value=None):
                result = await handler.handle_query("What's the status of S002-CHILLER-B1-001?")
        assert result["intent"] == "equipment_status"

    @pytest.mark.asyncio
    async def test_anomaly_query_classification(self, handler):
        with patch.object(handler.ollama, "is_available", new_callable=AsyncMock, return_value=False):
            with patch("app.services.query_handler.get_rag_service", return_value=None):
                result = await handler.handle_query("Explain the anomaly on S002-CHILLER-B1-001")
        assert result["intent"] == "explain_anomaly"


class TestQueryHandlerOfflineResponse:
    """Test responses when Ollama is not available."""

    @pytest.mark.asyncio
    async def test_offline_status_response(self, handler):
        with patch.object(handler.ollama, "is_available", new_callable=AsyncMock, return_value=False):
            with patch("app.services.query_handler.get_rag_service", return_value=None):
                result = await handler.handle_query("What's the status of S002-CHILLER-B1-001?")
        assert result["llm_available"] is False
        assert result["model_used"] is None
        assert "72%" in result["response"]  # Health score should appear

    @pytest.mark.asyncio
    async def test_offline_maintenance_response(self, handler):
        with patch.object(handler.ollama, "is_available", new_callable=AsyncMock, return_value=False):
            with patch("app.services.query_handler.get_rag_service", return_value=None):
                result = await handler.handle_query("When is maintenance due for S002-CHILLER-B1-001?")
        assert result["llm_available"] is False
        assert "45" in result["response"]  # RUL days

    @pytest.mark.asyncio
    async def test_offline_general_response(self, handler):
        with patch.object(handler.ollama, "is_available", new_callable=AsyncMock, return_value=False):
            with patch("app.services.query_handler.get_rag_service", return_value=None):
                result = await handler.handle_query("Tell me about the building")
        assert result["llm_available"] is False
        assert "general_query" in result["response"]


class TestQueryHandlerWithOllama:
    """Test response generation with Ollama available."""

    @pytest.mark.asyncio
    async def test_ollama_generates_response(self, handler):
        with patch.object(handler.ollama, "is_available", new_callable=AsyncMock, return_value=True):
            with patch.object(
                handler.ollama,
                "generate",
                new_callable=AsyncMock,
                return_value="The chiller health is at 72% due to elevated vibration.",
            ):
                with patch("app.services.query_handler.get_rag_service", return_value=None):
                    result = await handler.handle_query("What's the status of S002-CHILLER-B1-001?")
        assert result["llm_available"] is True
        assert "72%" in result["response"]
        assert result["model_used"] is not None


class TestQueryHandlerContextGathering:
    """Test that context is correctly gathered from repositories."""

    @pytest.mark.asyncio
    async def test_equipment_lookup(self, handler, mock_equipment_repo):
        with patch.object(handler.ollama, "is_available", new_callable=AsyncMock, return_value=False):
            with patch("app.services.query_handler.get_rag_service", return_value=None):
                await handler.handle_query("Status of S002-CHILLER-B1-001")
        mock_equipment_repo.get_by_id.assert_called_with("S002-CHILLER-B1-001")

    @pytest.mark.asyncio
    async def test_alerts_lookup(self, handler, mock_alert_repo):
        with patch.object(handler.ollama, "is_available", new_callable=AsyncMock, return_value=False):
            with patch("app.services.query_handler.get_rag_service", return_value=None):
                await handler.handle_query("Status of S002-CHILLER-B1-001")
        mock_alert_repo.get_active_by_equipment.assert_called()

    @pytest.mark.asyncio
    async def test_comparison_fetches_both(self, handler, mock_equipment_repo):
        with patch.object(handler.ollama, "is_available", new_callable=AsyncMock, return_value=False):
            with patch("app.services.query_handler.get_rag_service", return_value=None):
                await handler.handle_query("Compare S002-CHILLER-B1-001 vs S002-CHILLER-B1-002")
        assert mock_equipment_repo.get_by_id.call_count >= 2

    @pytest.mark.asyncio
    async def test_no_equipment_id_no_lookup(self, handler, mock_equipment_repo):
        with patch.object(handler.ollama, "is_available", new_callable=AsyncMock, return_value=False):
            with patch("app.services.query_handler.get_rag_service", return_value=None):
                await handler.handle_query("Tell me about the building")
        # get_by_id should not be called for general queries without equipment IDs
        mock_equipment_repo.get_by_id.assert_not_called()
