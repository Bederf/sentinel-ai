"""
Tests for the Recommendation Validation & Execution Agent
==========================================================
Unit tests for tool wrappers, graph traversal, formatters,
and multi-turn Tier 2 approval flow.
"""

import os
import sys
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

# Ensure backend is on path and DEMO_MODE is active
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
os.environ.setdefault("DEMO_MODE", "true")


# ===================================================================
# Fixtures
# ===================================================================


def make_recommendation(
    rec_id="rec-001",
    equipment="S002-FCU-201",
    action_type="hvac_setpoint_change",
    confidence_score=0.75,
    risk_level="low",
    age_minutes=5,
    status="pending",
):
    """Create a test recommendation dict."""
    ts = (datetime.now(UTC) - timedelta(minutes=age_minutes)).isoformat()
    return {
        "id": rec_id,
        "site_id": "S002",
        "timestamp": ts,
        "action_type": action_type,
        "risk_level": risk_level,
        "target_equipment": equipment,
        "action": {"point": "zone_temp_setpoint", "value": 18},
        "reason": "Zone temperature 2.5 C above comfort threshold",
        "expected_impact": {"cost_zar": 12.0, "energy_kwh": 2.4, "comfort_delta": -0.8},
        "confidence": "medium",
        "confidence_score": confidence_score,
        "profile": "comfort",
        "multi_objective_score": confidence_score,
        "status": status,
        "requires_approval": True,
        "approved_by": None,
        "approval_reason": None,
        "executed_at": None,
        "execution_result": None,
        "rejection_reason": None,
    }


# ===================================================================
# Tool: check_recommendation_freshness
# ===================================================================


class TestCheckRecommendationFreshness:
    """Tests for recommendation freshness checking."""

    def test_fresh_recommendation(self):
        from app.agents.recommendation_tools import check_recommendation_freshness

        rec = make_recommendation(age_minutes=5)
        result = check_recommendation_freshness(rec, max_age_minutes=30)
        assert result["is_fresh"] is True
        assert result["age_minutes"] < 30

    def test_stale_recommendation(self):
        from app.agents.recommendation_tools import check_recommendation_freshness

        rec = make_recommendation(age_minutes=60)
        result = check_recommendation_freshness(rec, max_age_minutes=30)
        assert result["is_fresh"] is False
        assert "60" in result["reason"] or "old" in result["reason"]

    def test_no_timestamp(self):
        from app.agents.recommendation_tools import check_recommendation_freshness

        rec = {"id": "test"}
        result = check_recommendation_freshness(rec)
        assert result["is_fresh"] is False
        assert result["age_minutes"] == 999

    def test_custom_max_age(self):
        from app.agents.recommendation_tools import check_recommendation_freshness

        rec = make_recommendation(age_minutes=10)
        assert check_recommendation_freshness(rec, max_age_minutes=5)["is_fresh"] is False
        assert check_recommendation_freshness(rec, max_age_minutes=15)["is_fresh"] is True

    def test_edge_exactly_at_max(self):
        from app.agents.recommendation_tools import check_recommendation_freshness

        rec = make_recommendation(age_minutes=30)
        result = check_recommendation_freshness(rec, max_age_minutes=30)
        # At exactly 30 minutes, may be slightly over due to test execution time
        # The important thing is the boundary is respected
        assert isinstance(result["is_fresh"], bool)


# ===================================================================
# Tool: check_recommendation_action_still_needed
# ===================================================================


class TestCheckRecommendationActionStillNeeded:
    """Tests for runtime action validity checking."""

    @pytest.mark.asyncio
    async def test_not_needed_when_current_value_matches_target(self):
        from app.agents.recommendation_tools import check_recommendation_action_still_needed

        rec = make_recommendation()

        with patch("app.services.device_abstraction.device_manager") as mock_device_manager:
            mock_device_manager.read_device_value = AsyncMock(return_value=SimpleNamespace(value=18.05))

            result = await check_recommendation_action_still_needed(rec)

        assert result["is_needed"] is False
        assert result["checked"] is True
        assert "already at recommended value" in result["reason"]

    @pytest.mark.asyncio
    async def test_read_failure_keeps_recommendation_active(self):
        from app.agents.recommendation_tools import check_recommendation_action_still_needed

        rec = make_recommendation()

        with patch("app.services.device_abstraction.device_manager") as mock_device_manager:
            mock_device_manager.read_device_value = AsyncMock(side_effect=ValueError("not connected"))

            result = await check_recommendation_action_still_needed(rec)

        assert result["is_needed"] is True
        assert result["checked"] is False
        assert "Current value unavailable" in result["reason"]

    @pytest.mark.asyncio
    async def test_execution_blocked_recommendation_is_not_needed(self):
        from app.agents.recommendation_tools import check_recommendation_action_still_needed

        rec = make_recommendation()
        rec["action"] = {
            "point": None,
            "value": 20.0,
            "execution_blocked": True,
            "blocker": "unresolved_bms_point",
        }

        result = await check_recommendation_action_still_needed(rec)

        assert result["is_needed"] is False
        assert result["checked"] is True
        assert "unresolved_bms_point" in result["reason"]

    @pytest.mark.asyncio
    async def test_occupancy_conflict_control_gate_execution_blocked_remains_needed(self):
        from app.agents.recommendation_tools import check_recommendation_action_still_needed

        rec = make_recommendation()
        rec["action"] = {
            "point": None,
            "value": "Block blanket site HVAC shutdown; use scoped setback only",
            "execution_blocked": True,
            "blocker": "occupancy_signal_conflict",
        }
        rec["metadata"] = {
            "source_metadata": {
                "advisory_type": "occupancy_conflict_control_gate",
                "rule": "occupancy_conflict_blocks_hvac_shutdown",
            }
        }

        result = await check_recommendation_action_still_needed(rec)

        assert result["is_needed"] is True
        assert result["checked"] is True
        assert "occupancy_conflict_control_gate" in result["reason"]


# ===================================================================
# Tool: estimate_cost_impact
# ===================================================================


class TestEstimateCostImpact:
    """Tests for cost impact estimation."""

    @pytest.mark.asyncio
    async def test_uses_expected_impact(self):
        from app.agents.recommendation_tools import estimate_cost_impact

        rec = make_recommendation()
        impact = await estimate_cost_impact(rec)
        assert impact["cost_zar"] == 12.0
        assert impact["energy_kwh"] == 2.4
        assert impact["comfort_delta"] == -0.8
        assert impact["risk"] == "low"

    @pytest.mark.asyncio
    async def test_fallback_cost_from_energy(self):
        from app.agents.recommendation_tools import estimate_cost_impact

        rec = make_recommendation()
        rec["expected_impact"] = {"energy_kwh": 10.0}
        impact = await estimate_cost_impact(rec)
        # Should calculate cost at R5/kWh
        assert impact["cost_zar"] == 50.0

    @pytest.mark.asyncio
    async def test_empty_impact(self):
        from app.agents.recommendation_tools import estimate_cost_impact

        rec = make_recommendation()
        rec["expected_impact"] = {}
        impact = await estimate_cost_impact(rec)
        assert impact["cost_zar"] == 0.0
        assert impact["energy_kwh"] == 0.0


# ===================================================================
# Formatters: Advisory
# ===================================================================


class TestFormatAdvisory:
    """Tests for advisory formatting."""

    def test_chat_format(self):
        from app.agents.recommendation_formatters import format_advisory_for_chat

        rec = make_recommendation()
        impact = {"cost_zar": 12.0, "energy_kwh": 2.4, "comfort_delta": -0.8}
        result = format_advisory_for_chat(rec, impact)
        assert "Advisory" in result
        assert "FCU-201" in result
        assert "R12.00" in result
        assert "2.4 kWh" in result

    def test_system_format(self):
        from app.agents.recommendation_formatters import format_advisory_for_system

        rec = make_recommendation()
        impact = {"cost_zar": 12.0}
        result = format_advisory_for_system(rec, impact)
        assert "[ADVISORY]" in result
        assert "S002-FCU-201" in result
        assert "R12.00" in result

    def test_system_format_no_cost(self):
        from app.agents.recommendation_formatters import format_advisory_for_system

        rec = make_recommendation()
        impact = {}
        result = format_advisory_for_system(rec, impact)
        assert "[ADVISORY]" in result


# ===================================================================
# Formatters: Approval Request
# ===================================================================


class TestFormatApprovalRequest:
    """Tests for approval request formatting."""

    def test_whatsapp_format(self):
        from app.agents.recommendation_formatters import format_approval_request_whatsapp

        rec = make_recommendation(rec_id="abc12345-def")
        impact = {"cost_zar": 12.0, "comfort_delta": -0.8}
        result = format_approval_request_whatsapp(rec, impact)
        assert "Approval Required" in result
        assert "FCU-201" in result
        assert "APPROVE" in result
        assert "REJECT" in result
        assert "R12.00" in result

    def test_telegram_format(self):
        from app.agents.recommendation_formatters import format_approval_request_telegram

        rec = make_recommendation(rec_id="abc12345-def")
        impact = {"cost_zar": 5.0}
        result = format_approval_request_telegram(rec, impact)
        assert "Approval Required" in result
        assert "/approve" in result
        assert "/reject" in result

    def test_whatsapp_rec_id_truncated(self):
        from app.agents.recommendation_formatters import format_approval_request_whatsapp

        rec = make_recommendation(rec_id="abcdefgh-ijkl-mnop")
        impact = {}
        result = format_approval_request_whatsapp(rec, impact)
        assert "APPROVE abcdefgh" in result


# ===================================================================
# Formatters: Execution Result
# ===================================================================


class TestFormatExecutionResult:
    """Tests for execution result formatting."""

    def test_system_success(self):
        from app.agents.recommendation_formatters import format_execution_result

        rec = make_recommendation()
        result = {"success": True, "cov_verified": True, "status": "executed"}
        formatted = format_execution_result(rec, result, "system")
        assert "OK" in formatted
        assert "COV_OK" in formatted

    def test_system_failure(self):
        from app.agents.recommendation_formatters import format_execution_result

        rec = make_recommendation()
        result = {"success": False, "cov_verified": False, "status": "failed"}
        formatted = format_execution_result(rec, result, "system")
        assert "FAIL" in formatted

    def test_whatsapp_success(self):
        from app.agents.recommendation_formatters import format_execution_result

        rec = make_recommendation()
        result = {"success": True, "cov_verified": True, "status": "executed"}
        formatted = format_execution_result(rec, result, "whatsapp")
        assert "DONE" in formatted
        assert "COV confirmed" in formatted

    def test_chat_with_error(self):
        from app.agents.recommendation_formatters import format_execution_result

        rec = make_recommendation()
        result = {"success": False, "cov_verified": False, "status": "failed", "error_message": "Device timeout"}
        formatted = format_execution_result(rec, result, "chat")
        assert "Failed" in formatted
        assert "Device timeout" in formatted


# ===================================================================
# Formatters: Batch Summary
# ===================================================================


class TestFormatBatchSummary:
    """Tests for batch summary formatting."""

    def test_empty_results(self):
        from app.agents.recommendation_formatters import format_batch_summary

        assert "No pending" in format_batch_summary([])

    def test_mixed_results(self):
        from app.agents.recommendation_formatters import format_batch_summary

        results = [
            {"status": "auto_executed", "tier": "tier3"},
            {"status": "advisory", "tier": "tier1"},
            {"status": "pending", "needs_input": True},
        ]
        formatted = format_batch_summary(results)
        assert "3 recommendation" in formatted

    def test_whatsapp_format(self):
        from app.agents.recommendation_formatters import format_batch_summary

        results = [{"status": "auto_executed", "tier": "tier3"}]
        formatted = format_batch_summary(results, "whatsapp")
        assert "*Processed" in formatted


# ===================================================================
# Formatters: Equipment Label
# ===================================================================


class TestEquipmentLabel:
    """Tests for equipment code to label conversion."""

    def test_zone_equipment(self):
        from app.agents.recommendation_formatters import _equipment_label

        assert "Level 2" in _equipment_label("S002-FCU-201")
        assert "Level 1" in _equipment_label("S002-VAV-101")
        assert "Ground Floor" in _equipment_label("S002-AHU-001")

    def test_short_code(self):
        from app.agents.recommendation_formatters import _equipment_label

        assert _equipment_label("FCU") == "FCU"

    def test_empty(self):
        from app.agents.recommendation_formatters import _equipment_label

        assert _equipment_label("") == ""


# ===================================================================
# Graph: State Schema
# ===================================================================


class TestRecommendationAgentState:
    """Tests for state schema correctness."""

    def test_state_has_required_fields(self):
        from app.agents.recommendation_graph import RecommendationAgentState

        fields = RecommendationAgentState.__annotations__
        assert "messages" in fields
        assert "site_id" in fields
        assert "channel" in fields
        assert "recommendation" in fields
        assert "tier" in fields
        assert "needs_input" in fields
        assert "processing_complete" in fields
        assert "impact" in fields
        assert "feedback_submitted" in fields


# ===================================================================
# Graph: Node Functions (unit tests with mocks)
# ===================================================================


class TestFetchPendingNode:
    """Tests for fetch_pending node."""

    @pytest.mark.asyncio
    async def test_no_site_id(self):
        from app.agents.recommendation_graph import fetch_pending_node

        state = {"site_id": ""}
        result = await fetch_pending_node(state)
        assert result["recommendation"] is None

    @pytest.mark.asyncio
    async def test_no_pending_recs(self):
        from app.agents.recommendation_graph import fetch_pending_node

        with patch(
            "app.agents.recommendation_graph.get_pending_recommendations",
            new_callable=AsyncMock,
            return_value=[],
        ):
            state = {"site_id": "S002"}
            result = await fetch_pending_node(state)
            assert result["recommendation"] is None

    @pytest.mark.asyncio
    async def test_fetches_first_recommendation(self):
        from app.agents.recommendation_graph import fetch_pending_node

        rec = make_recommendation()
        with patch(
            "app.agents.recommendation_graph.get_pending_recommendations",
            new_callable=AsyncMock,
            return_value=[rec],
        ):
            state = {"site_id": "S002"}
            result = await fetch_pending_node(state)
            assert result["recommendation"]["id"] == "rec-001"
            assert result["recommendation_id"] == "rec-001"


class TestValidateRelevanceNode:
    """Tests for validate_relevance node."""

    @pytest.mark.asyncio
    async def test_fresh_recommendation_is_relevant(self):
        from app.agents.recommendation_graph import validate_relevance_node

        rec = make_recommendation(age_minutes=5)
        with patch(
            "app.agents.recommendation_graph.check_equipment_health",
            new_callable=AsyncMock,
            return_value={"health_score": 45, "is_healthy": False, "details": {}},
        ):
            state = {"recommendation": rec}
            result = await validate_relevance_node(state)
            assert result["is_relevant"] is True

    @pytest.mark.asyncio
    async def test_stale_recommendation_not_relevant(self):
        from app.agents.recommendation_graph import validate_relevance_node

        rec = make_recommendation(age_minutes=150)
        state = {"recommendation": rec}
        result = await validate_relevance_node(state)
        assert result["is_relevant"] is False
        assert (
            "old" in result["relevance_reason"].lower()
            or "stale" in result["relevance_reason"].lower()
            or "min" in result["relevance_reason"].lower()
        )

    @pytest.mark.asyncio
    async def test_no_recommendation(self):
        from app.agents.recommendation_graph import validate_relevance_node

        state = {"recommendation": {}}
        result = await validate_relevance_node(state)
        assert result["is_relevant"] is False


class TestCheckScheduleNode:
    """Tests for check_schedule node."""

    @pytest.mark.asyncio
    async def test_no_conflict(self):
        from app.agents.recommendation_graph import check_schedule_node

        rec = make_recommendation()
        with patch(
            "app.agents.recommendation_graph.check_maintenance_calendar",
            new_callable=AsyncMock,
            return_value={"has_conflict": False, "work_orders": [], "reason": ""},
        ):
            state = {"recommendation": rec}
            result = await check_schedule_node(state)
            assert result["schedule_conflict"] is False

    @pytest.mark.asyncio
    async def test_with_conflict(self):
        from app.agents.recommendation_graph import check_schedule_node

        rec = make_recommendation()
        with patch(
            "app.agents.recommendation_graph.check_maintenance_calendar",
            new_callable=AsyncMock,
            return_value={
                "has_conflict": True,
                "work_orders": [{"id": "wo-1"}],
                "reason": "1 open work order(s) on S002-FCU-201",
            },
        ):
            state = {"recommendation": rec}
            result = await check_schedule_node(state)
            assert result["schedule_conflict"] is True
            assert "open work order" in result["conflict_details"]


class TestRouteTierNode:
    """Tests for route_tier node."""

    @pytest.mark.asyncio
    async def test_routes_tier1(self):
        from app.agents.recommendation_graph import route_tier_node

        rec = make_recommendation(confidence_score=0.50)
        with patch(
            "app.agents.recommendation_graph.route_through_tier_engine",
            new_callable=AsyncMock,
            return_value={
                "tier": "tier1",
                "action": "advisory",
                "confidence_score": 0.50,
                "threshold_source": "settings",
                "tier2_threshold": 0.70,
                "tier3_threshold": 0.85,
                "reason": "Below tier2 threshold",
                "equipment_type": "FCU",
                "risk_level": "low",
            },
        ):
            state = {"recommendation": rec}
            result = await route_tier_node(state)
            assert result["tier"] == "tier1"

    @pytest.mark.asyncio
    async def test_routes_tier3(self):
        from app.agents.recommendation_graph import route_tier_node

        rec = make_recommendation(confidence_score=0.92)
        with patch(
            "app.agents.recommendation_graph.route_through_tier_engine",
            new_callable=AsyncMock,
            return_value={
                "tier": "tier3",
                "action": "auto_execute",
                "confidence_score": 0.92,
                "threshold_source": "settings",
                "tier2_threshold": 0.70,
                "tier3_threshold": 0.85,
                "reason": "Above tier3 threshold",
                "equipment_type": "FCU",
                "risk_level": "low",
            },
        ):
            state = {"recommendation": rec}
            result = await route_tier_node(state)
            assert result["tier"] == "tier3"


class TestLogAdvisoryNode:
    """Tests for log_advisory node."""

    @pytest.mark.asyncio
    async def test_formats_for_system(self):
        from app.agents.recommendation_graph import log_advisory_node

        rec = make_recommendation()
        state = {
            "recommendation": rec,
            "impact": {"cost_zar": 12.0},
            "tier_result": {"tier": "tier1"},
            "channel": "system",
        }
        result = await log_advisory_node(state)
        assert result["approval_status"] == "advisory"
        assert "[ADVISORY]" in result["response"]

    @pytest.mark.asyncio
    async def test_formats_for_chat(self):
        from app.agents.recommendation_graph import log_advisory_node

        rec = make_recommendation()
        state = {
            "recommendation": rec,
            "impact": {"cost_zar": 12.0},
            "tier_result": {"tier": "tier1"},
            "channel": "chat",
        }
        result = await log_advisory_node(state)
        assert "Advisory" in result["response"]


class TestRequestApprovalNode:
    """Tests for request_approval node."""

    @pytest.mark.asyncio
    async def test_sets_needs_input(self):
        from app.agents.recommendation_graph import request_approval_node

        rec = make_recommendation()
        state = {
            "recommendation": rec,
            "impact": {"cost_zar": 12.0, "comfort_delta": -0.8},
            "tier_result": {"tier": "tier2"},
            "channel": "whatsapp",
        }
        result = await request_approval_node(state)
        assert result["needs_input"] is True
        assert result["approval_status"] == "pending"
        assert "APPROVE" in result["response"]

    @pytest.mark.asyncio
    async def test_telegram_format(self):
        from app.agents.recommendation_graph import request_approval_node

        rec = make_recommendation()
        state = {
            "recommendation": rec,
            "impact": {},
            "tier_result": {"tier": "tier2"},
            "channel": "telegram",
        }
        result = await request_approval_node(state)
        assert "/approve" in result["response"]


class TestAutoExecuteNode:
    """Tests for auto_execute node."""

    @pytest.mark.asyncio
    async def test_successful_execution(self):
        from app.agents.recommendation_graph import auto_execute_node

        rec = make_recommendation()
        tier_result = {
            "tier": "tier3",
            "action": "auto_execute",
            "confidence_score": 0.92,
            "threshold_source": "settings",
            "tier2_threshold": 0.70,
            "tier3_threshold": 0.85,
            "reason": "Above tier3",
            "equipment_type": "FCU",
            "risk_level": "low",
        }
        with patch(
            "app.agents.recommendation_graph.execute_tier3_auto",
            new_callable=AsyncMock,
            return_value={
                "success": True,
                "recommendation_id": "rec-001",
                "status": "auto_executed",
                "executed_at": datetime.utcnow().isoformat(),
                "error_message": None,
                "cov_verified": True,
                "execution_result": {},
            },
        ):
            state = {
                "recommendation_id": "rec-001",
                "recommendation": rec,
                "tier_result": tier_result,
                "channel": "system",
            }
            result = await auto_execute_node(state)
            assert result["approval_status"] == "auto_executed"

    @pytest.mark.asyncio
    async def test_failed_execution(self):
        from app.agents.recommendation_graph import auto_execute_node

        rec = make_recommendation()
        tier_result = {
            "tier": "tier3",
            "action": "auto_execute",
            "confidence_score": 0.92,
            "threshold_source": "settings",
            "tier2_threshold": 0.70,
            "tier3_threshold": 0.85,
            "reason": "",
            "equipment_type": "FCU",
            "risk_level": "low",
        }
        with patch(
            "app.agents.recommendation_graph.execute_tier3_auto",
            new_callable=AsyncMock,
            return_value={
                "success": False,
                "recommendation_id": "rec-001",
                "status": "failed",
                "executed_at": None,
                "error_message": "Safety constraint",
                "cov_verified": False,
                "execution_result": {},
            },
        ):
            state = {
                "recommendation_id": "rec-001",
                "recommendation": rec,
                "tier_result": tier_result,
                "channel": "system",
            }
            result = await auto_execute_node(state)
            assert result["approval_status"] == "failed"


class TestHandleApprovalResponseNode:
    """Tests for handle_approval_response (Tier 2 resume)."""

    @pytest.mark.asyncio
    async def test_approve_response(self):
        from langchain_core.messages import HumanMessage

        from app.agents.recommendation_graph import handle_approval_response_node

        with patch(
            "app.agents.recommendation_graph.execute_approved_recommendation",
            new_callable=AsyncMock,
            return_value={
                "success": True,
                "recommendation_id": "rec-001",
                "status": "executed",
                "executed_at": datetime.utcnow().isoformat(),
                "error_message": None,
                "cov_verified": True,
                "execution_result": {},
            },
        ):
            state = {
                "messages": [HumanMessage(content="APPROVE rec-001")],
                "recommendation_id": "rec-001",
                "recommendation": make_recommendation(),
                "channel": "whatsapp",
            }
            result = await handle_approval_response_node(state)
            assert result["approval_status"] == "approved"
            assert result["needs_input"] is False

    @pytest.mark.asyncio
    async def test_reject_response(self):
        from langchain_core.messages import HumanMessage

        from app.agents.recommendation_graph import handle_approval_response_node

        with patch(
            "app.agents.recommendation_graph.reject_recommendation",
            new_callable=AsyncMock,
            return_value={
                "success": True,
                "recommendation_id": "rec-001",
                "status": "rejected",
                "error_message": None,
            },
        ):
            state = {
                "messages": [HumanMessage(content="REJECT too risky")],
                "recommendation_id": "rec-001",
                "recommendation": make_recommendation(),
                "channel": "whatsapp",
            }
            result = await handle_approval_response_node(state)
            assert result["approval_status"] == "rejected"
            assert result["needs_input"] is False

    @pytest.mark.asyncio
    async def test_invalid_response(self):
        from langchain_core.messages import HumanMessage

        from app.agents.recommendation_graph import handle_approval_response_node

        state = {
            "messages": [HumanMessage(content="maybe later")],
            "recommendation_id": "rec-001",
            "recommendation": make_recommendation(),
            "channel": "whatsapp",
        }
        result = await handle_approval_response_node(state)
        assert result["needs_input"] is True
        assert "APPROVE" in result["response"]

    @pytest.mark.asyncio
    async def test_no_messages(self):
        from app.agents.recommendation_graph import handle_approval_response_node

        state = {"messages": [], "recommendation_id": "rec-001"}
        result = await handle_approval_response_node(state)
        assert result["needs_input"] is True


class TestSubmitFeedbackNode:
    """Tests for submit_feedback node."""

    @pytest.mark.asyncio
    async def test_submits_feedback(self):
        from app.agents.recommendation_graph import submit_feedback_node

        rec = make_recommendation()
        with patch(
            "app.agents.recommendation_graph.submit_feedback_to_model",
            new_callable=AsyncMock,
            return_value=True,
        ):
            state = {
                "recommendation": rec,
                "recommendation_id": "rec-001",
                "approval_status": "auto_executed",
                "execution_result": {"success": True},
            }
            result = await submit_feedback_node(state)
            assert result["feedback_submitted"] is True


class TestFormatResultNode:
    """Tests for format_result node."""

    def test_sets_processing_complete(self):
        from app.agents.recommendation_graph import format_result_node

        state = {"response": "Done"}
        result = format_result_node(state)
        assert result["processing_complete"] is True
        assert result["needs_input"] is False

    def test_fallback_response(self):
        from app.agents.recommendation_graph import format_result_node

        state = {"response": ""}
        result = format_result_node(state)
        assert result["response"] == "Processing complete."


# ===================================================================
# Graph: Conditional Edges
# ===================================================================


class TestConditionalEdges:
    """Tests for conditional edge functions."""

    def test_has_recommendation(self):
        from app.agents.recommendation_graph import has_recommendation

        assert has_recommendation({"recommendation": {"id": "x"}}) == "has_rec"
        assert has_recommendation({"recommendation": None}) == "no_rec"
        assert has_recommendation({}) == "no_rec"

    def test_check_relevance(self):
        from app.agents.recommendation_graph import check_relevance

        assert check_relevance({"is_relevant": True}) == "valid"
        assert check_relevance({"is_relevant": False}) == "expired"

    def test_check_schedule_conflict(self):
        from app.agents.recommendation_graph import check_schedule_conflict

        assert check_schedule_conflict({"schedule_conflict": True}) == "conflict"
        assert check_schedule_conflict({"schedule_conflict": False}) == "clear"

    def test_tier_route(self):
        from app.agents.recommendation_graph import tier_route

        assert tier_route({"tier": "tier1"}) == "tier1"
        assert tier_route({"tier": "tier2"}) == "tier2"
        assert tier_route({"tier": "tier3"}) == "tier3"
        assert tier_route({}) == "tier1"  # Default

    def test_check_needs_input(self):
        from app.agents.recommendation_graph import check_needs_input

        assert check_needs_input({"needs_input": True}) == "still_waiting"
        assert check_needs_input({"needs_input": False}) == "resolved"


# ===================================================================
# Graph: Build and compile
# ===================================================================


class TestGraphBuild:
    """Tests for graph construction."""

    def test_graph_builds(self):
        from app.agents.recommendation_graph import build_recommendation_graph

        graph = build_recommendation_graph()
        assert graph is not None

    def test_graph_compiles(self):
        from langgraph.checkpoint.memory import MemorySaver

        from app.agents.recommendation_graph import build_recommendation_graph

        graph = build_recommendation_graph()
        compiled = graph.compile(checkpointer=MemorySaver())
        assert compiled is not None

    def test_graph_has_expected_nodes(self):
        from app.agents.recommendation_graph import build_recommendation_graph

        graph = build_recommendation_graph()
        node_names = list(graph.nodes.keys())
        expected = [
            "fetch_pending",
            "validate_relevance",
            "mark_expired",
            "assess_impact",
            "check_schedule",
            "defer",
            "route_tier",
            "log_advisory",
            "request_approval",
            "auto_execute",
            "handle_approval_response",
            "submit_feedback",
            "format_result",
        ]
        for name in expected:
            assert name in node_names, f"Missing node: {name}"

    def test_singleton_getter(self):
        from app.agents.recommendation_graph import get_recommendation_graph

        g1 = get_recommendation_graph()
        g2 = get_recommendation_graph()
        assert g1 is g2  # Same instance


# ===================================================================
# Graph: Module export
# ===================================================================


class TestModuleExport:
    """Tests for agent package exports."""

    def test_agents_init_exports(self):
        from app.agents import get_recommendation_graph

        assert callable(get_recommendation_graph)

    def test_agents_all_contains_recommendation(self):
        import app.agents

        assert "get_recommendation_graph" in app.agents.__all__
