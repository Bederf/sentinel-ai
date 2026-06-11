"""Tests for OpenAI MCP connector server — confidence, health, and live cross-reference."""

from unittest.mock import MagicMock, patch

import pytest

from app.mcp.openai_connector_server import OpenAIConnectorMCPServer


@pytest.fixture
def server():
    return OpenAIConnectorMCPServer()


@pytest.mark.asyncio
class TestGetRecommendationsConfidence:
    """Bug 1: confidence_score=0.0 must not be treated as falsy."""

    async def test_confidence_zero_not_falsy(self, server):
        """confidence_score=0.0 returns 0.0, not 0.5."""
        mock_rec = {
            "confidence_score": 0.0,
            "confidence": "medium",
            "expected_impact": {},
            "action": {},
            "risk_level": "medium",
            "status": "pending",
            "target_equipment": "S002-PUMP-B01",
        }
        mock_result = MagicMock()
        mock_result.data = [mock_rec]
        mock_client = MagicMock()
        # get_recommendations chain: table→select→eq(site_id)→eq(shadow_mode)→order→eq(status)→limit→execute
        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.order.return_value.eq.return_value.limit.return_value.execute.return_value = mock_result

        with patch("app.mcp.openai_connector_server._get_supabase_client", return_value=mock_client):
            result = await server.get_recommendations("S002")

        assert "recommendations" in result
        assert len(result["recommendations"]) == 1
        assert result["recommendations"][0]["confidence"] == 0.0

    async def test_confidence_none_falls_back(self, server):
        """confidence_score=None returns 0.5 fallback."""
        mock_rec = {
            "confidence_score": None,
            "confidence": None,
            "expected_impact": {},
            "action": {},
            "risk_level": "medium",
            "status": "pending",
            "target_equipment": "S002-PUMP-B01",
        }
        mock_result = MagicMock()
        mock_result.data = [mock_rec]
        mock_client = MagicMock()
        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.order.return_value.eq.return_value.limit.return_value.execute.return_value = mock_result

        with patch("app.mcp.openai_connector_server._get_supabase_client", return_value=mock_client):
            result = await server.get_recommendations("S002")

        assert result["recommendations"][0]["confidence"] == 0.5

    async def test_confidence_normal_value(self, server):
        """confidence_score=0.78 passes through unchanged."""
        mock_rec = {
            "confidence_score": 0.78,
            "confidence": "medium",
            "expected_impact": {},
            "action": {},
            "risk_level": "medium",
            "status": "pending",
            "target_equipment": "S002-AHU-B01",
        }
        mock_result = MagicMock()
        mock_result.data = [mock_rec]
        mock_client = MagicMock()
        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.order.return_value.eq.return_value.limit.return_value.execute.return_value = mock_result

        with patch("app.mcp.openai_connector_server._get_supabase_client", return_value=mock_client):
            result = await server.get_recommendations("S002")

        assert result["recommendations"][0]["confidence"] == 0.78


@pytest.mark.asyncio
class TestTraceRecommendation:
    """Bug 2 & 3: No trust_weight penalty, live health cross-reference."""

    def _make_rec(self, confidence_score=0.9, source_type="rule_based", target_eq="S002-PUMP-B01", **kwargs):
        base = {
            "confidence_score": confidence_score,
            "source_type": source_type,
            "target_equipment": target_eq,
            "source": "ai_optimizer",
            "status": "pending",
            "action_type": "maintenance",
            "reason": "Test reason",
            "expected_impact": None,
            "execution_result": None,
        }
        base.update(kwargs)
        return base

    def _mock_client(self, rec_data, equipment_data=None):
        """Build a mock Supabase client with per-table mock dispatch.

        trace_recommendation queries three tables with different method chains:
          1. recommendations: .select().eq(id).limit(1).execute()
          2. predictions:     .select().eq(eq_id).order(...).limit(5).execute()
          3. equipment:       .select().eq(code).limit(1).execute()

        Using table.side_effect dispatches to dedicated mocks per table.
        """
        mock_client = MagicMock()

        # Recommendation table mock
        rec_mock = MagicMock()
        rec_result = MagicMock()
        rec_result.data = [rec_data]
        rec_mock.select.return_value.eq.return_value.limit.return_value.execute.return_value = rec_result

        # Predictions table mock
        pred_mock = MagicMock()
        pred_result = MagicMock()
        pred_result.data = []
        pred_mock.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = (
            pred_result
        )

        # Equipment table mock (live health)
        eq_mock = MagicMock()
        eq_result = MagicMock()
        eq_result.data = [equipment_data] if equipment_data else []
        eq_mock.select.return_value.eq.return_value.limit.return_value.execute.return_value = eq_result

        mock_client.table.side_effect = lambda table: {
            "recommendations": rec_mock,
            "predictions": pred_mock,
            "equipment": eq_mock,
        }.get(table, MagicMock())

        return mock_client

    async def test_no_trust_weight_penalty(self, server):
        """Rule-based trigger with 0.9 score returns final=0.9 (not 0.45)."""
        rec = self._make_rec(confidence_score=0.9, source_type="rule_based")
        eq = {"health_score": 61.0, "status": "warning"}
        mock_client = self._mock_client(rec, equipment_data=eq)

        with patch("app.mcp.openai_connector_server._get_supabase_client", return_value=mock_client):
            result = await server.trace_recommendation("any-uuid")

        assert result["confidence_breakdown"]["final"] == 0.9
        assert result["confidence_breakdown"]["source_type"] == "rule_based"

    async def test_ml_model_confidence(self, server):
        """ML model trigger with 0.78 score returns final=0.78 (no 0.8 penalty)."""
        rec = self._make_rec(confidence_score=0.78, source_type="ml_model")
        eq = {"health_score": 67.0, "status": "normal"}
        mock_client = self._mock_client(rec, equipment_data=eq)

        with patch("app.mcp.openai_connector_server._get_supabase_client", return_value=mock_client):
            result = await server.trace_recommendation("any-uuid")

        assert result["confidence_breakdown"]["final"] == 0.78
        assert result["confidence_breakdown"]["source_type"] == "ml_model"

    async def test_live_health_cross_reference(self, server):
        """trace_recommendation returns live equipment health alongside recommendation."""
        rec = self._make_rec(target_eq="S002-PUMP-B01")
        eq = {"health_score": 61.0, "status": "warning"}
        mock_client = self._mock_client(rec, equipment_data=eq)

        with patch("app.mcp.openai_connector_server._get_supabase_client", return_value=mock_client):
            result = await server.trace_recommendation("any-uuid")

        assert "live_equipment_health" in result
        assert result["live_equipment_health"]["health_score"] == 61.0
        assert result["live_equipment_health"]["status"] == "warning"

    async def test_live_health_note_present(self, server):
        """Health snapshot difference is explained in the response note."""
        rec = self._make_rec()
        eq = {"health_score": 61.0, "status": "warning"}
        mock_client = self._mock_client(rec, equipment_data=eq)

        with patch("app.mcp.openai_connector_server._get_supabase_client", return_value=mock_client):
            result = await server.trace_recommendation("any-uuid")

        assert "note" in result["live_equipment_health"]
        assert "Current live value" in result["live_equipment_health"]["note"]

    async def test_live_health_missing_equipment(self, server):
        """When recommendation has no target_equipment, live health is None."""
        rec = self._make_rec(target_eq=None)
        mock_client = self._mock_client(rec)

        with patch("app.mcp.openai_connector_server._get_supabase_client", return_value=mock_client):
            result = await server.trace_recommendation("any-uuid")

        assert result["live_equipment_health"]["health_score"] is None
        assert result["live_equipment_health"]["status"] is None

    async def test_live_health_lookup_error_safe(self, server):
        """When equipment lookup throws, live health is None (no crash)."""
        rec = self._make_rec()
        rec_result = MagicMock()
        rec_result.data = [rec]

        pred_result = MagicMock()
        pred_result.data = []

        # Make equipment table raise
        eq_mock = MagicMock()
        eq_mock.select.return_value.eq.return_value.limit.return_value.execute.side_effect = Exception("DB timeout")

        mock_client = MagicMock()
        mock_client.table.side_effect = lambda t: {
            "recommendations": MagicMock(
                **{"select.return_value.eq.return_value.limit.return_value.execute.return_value": rec_result}
            ),
            "predictions": MagicMock(
                **{
                    "select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value": pred_result
                }
            ),
            "equipment": eq_mock,
        }.get(t, MagicMock())

        with patch("app.mcp.openai_connector_server._get_supabase_client", return_value=mock_client):
            result = await server.trace_recommendation("any-uuid")

        assert "error" not in result
        assert result["live_equipment_health"]["health_score"] is None
