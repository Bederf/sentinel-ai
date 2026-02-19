"""
Integration Tests for Recommendation Agent Routing
====================================================
Tests for the full graph traversal paths including WhatsApp/Telegram
approval flows, chat tool registration, and tier routing with
different confidence levels.
"""

import os
import sys
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Ensure backend is on path and DEMO_MODE is active
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
os.environ.setdefault("DEMO_MODE", "true")


# ===================================================================
# Helpers
# ===================================================================


def make_recommendation(
    rec_id="rec-int-001",
    equipment="S002-FCU-201",
    confidence_score=0.75,
    risk_level="low",
    age_minutes=5,
):
    """Create a test recommendation dict."""
    ts = (datetime.utcnow() - timedelta(minutes=age_minutes)).isoformat()
    return {
        "id": rec_id,
        "site_id": "S002",
        "timestamp": ts,
        "action_type": "hvac_setpoint_change",
        "risk_level": risk_level,
        "target_equipment": equipment,
        "action": {"point": "zone_temp_setpoint", "value": 18},
        "reason": "Zone above comfort threshold",
        "expected_impact": {"cost_zar": 12.0, "energy_kwh": 2.4, "comfort_delta": -0.8},
        "confidence": "medium",
        "confidence_score": confidence_score,
        "profile": "comfort",
        "multi_objective_score": confidence_score,
        "status": "pending",
        "requires_approval": True,
        "approved_by": None,
        "approval_reason": None,
        "executed_at": None,
        "execution_result": None,
        "rejection_reason": None,
    }


def mock_tier_routing(tier, confidence):
    """Create a mock tier routing result."""
    actions = {"tier1": "advisory", "tier2": "require_approval", "tier3": "auto_execute"}
    return {
        "tier": tier,
        "action": actions.get(tier, "advisory"),
        "confidence_score": confidence,
        "threshold_source": "settings",
        "tier2_threshold": 0.70,
        "tier3_threshold": 0.85,
        "reason": f"Confidence {confidence} routed to {tier}",
        "equipment_type": "FCU",
        "risk_level": "low",
    }


# ===================================================================
# Full Graph Path: Tier 1 Advisory
# ===================================================================


class TestTier1AdvisoryPath:
    """Tests for complete Tier 1 advisory traversal."""

    @pytest.mark.asyncio
    async def test_tier1_full_path(self):
        """Rec with low confidence → advisory logged, no execution."""
        from langchain_core.messages import HumanMessage
        from langgraph.checkpoint.memory import MemorySaver

        from app.agents.recommendation_graph import build_recommendation_graph

        rec = make_recommendation(confidence_score=0.50)

        with (
            patch(
                "app.agents.recommendation_graph.get_pending_recommendations",
                new_callable=AsyncMock,
                return_value=[rec],
            ),
            patch(
                "app.agents.recommendation_graph.check_equipment_health",
                new_callable=AsyncMock,
                return_value={"health_score": 45, "is_healthy": False, "details": {}},
            ),
            patch(
                "app.agents.recommendation_graph.check_maintenance_calendar",
                new_callable=AsyncMock,
                return_value={"has_conflict": False, "work_orders": [], "reason": ""},
            ),
            patch(
                "app.agents.recommendation_graph.route_through_tier_engine",
                new_callable=AsyncMock,
                return_value=mock_tier_routing("tier1", 0.50),
            ),
            patch(
                "app.agents.recommendation_graph.submit_feedback_to_model",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "app.agents.recommendation_tools.cross_reference_similar_faults",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            graph = build_recommendation_graph()
            compiled = graph.compile(checkpointer=MemorySaver())
            config = {"configurable": {"thread_id": "test_tier1"}}

            result = await compiled.ainvoke(
                {
                    "messages": [HumanMessage(content="process")],
                    "site_id": "S002",
                    "channel": "system",
                    "trigger": "manual",
                },
                config=config,
            )

            assert result["processing_complete"] is True
            assert result["tier"] == "tier1"
            assert "[ADVISORY]" in result["response"]


# ===================================================================
# Full Graph Path: Tier 3 Auto-Execute
# ===================================================================


class TestTier3AutoExecutePath:
    """Tests for complete Tier 3 auto-execution traversal."""

    @pytest.mark.asyncio
    async def test_tier3_full_path(self):
        """Rec with high confidence → auto-executed."""
        from langchain_core.messages import HumanMessage
        from langgraph.checkpoint.memory import MemorySaver

        from app.agents.recommendation_graph import build_recommendation_graph

        rec = make_recommendation(confidence_score=0.92)

        with (
            patch(
                "app.agents.recommendation_graph.get_pending_recommendations",
                new_callable=AsyncMock,
                return_value=[rec],
            ),
            patch(
                "app.agents.recommendation_graph.check_equipment_health",
                new_callable=AsyncMock,
                return_value={"health_score": 35, "is_healthy": False, "details": {}},
            ),
            patch(
                "app.agents.recommendation_graph.check_maintenance_calendar",
                new_callable=AsyncMock,
                return_value={"has_conflict": False, "work_orders": [], "reason": ""},
            ),
            patch(
                "app.agents.recommendation_graph.route_through_tier_engine",
                new_callable=AsyncMock,
                return_value=mock_tier_routing("tier3", 0.92),
            ),
            patch(
                "app.agents.recommendation_graph.execute_tier3_auto",
                new_callable=AsyncMock,
                return_value={
                    "success": True,
                    "recommendation_id": "rec-int-001",
                    "status": "auto_executed",
                    "executed_at": datetime.utcnow().isoformat(),
                    "error_message": None,
                    "cov_verified": True,
                    "execution_result": {},
                },
            ),
            patch(
                "app.agents.recommendation_graph.submit_feedback_to_model",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "app.agents.recommendation_tools.cross_reference_similar_faults",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            graph = build_recommendation_graph()
            compiled = graph.compile(checkpointer=MemorySaver())
            config = {"configurable": {"thread_id": "test_tier3"}}

            result = await compiled.ainvoke(
                {
                    "messages": [HumanMessage(content="process")],
                    "site_id": "S002",
                    "channel": "system",
                    "trigger": "manual",
                },
                config=config,
            )

            assert result["processing_complete"] is True
            assert result["tier"] == "tier3"
            assert result["feedback_submitted"] is True


# ===================================================================
# Full Graph Path: Tier 2 Approval Request
# ===================================================================


class TestTier2ApprovalPath:
    """Tests for Tier 2 approval request and resume."""

    @pytest.mark.asyncio
    async def test_tier2_pauses_for_approval(self):
        """Rec with medium confidence → approval request, pauses."""
        from langchain_core.messages import HumanMessage
        from langgraph.checkpoint.memory import MemorySaver

        from app.agents.recommendation_graph import build_recommendation_graph

        rec = make_recommendation(confidence_score=0.75)

        with (
            patch(
                "app.agents.recommendation_graph.get_pending_recommendations",
                new_callable=AsyncMock,
                return_value=[rec],
            ),
            patch(
                "app.agents.recommendation_graph.check_equipment_health",
                new_callable=AsyncMock,
                return_value={"health_score": 45, "is_healthy": False, "details": {}},
            ),
            patch(
                "app.agents.recommendation_graph.check_maintenance_calendar",
                new_callable=AsyncMock,
                return_value={"has_conflict": False, "work_orders": [], "reason": ""},
            ),
            patch(
                "app.agents.recommendation_graph.route_through_tier_engine",
                new_callable=AsyncMock,
                return_value=mock_tier_routing("tier2", 0.75),
            ),
            patch(
                "app.agents.recommendation_tools.cross_reference_similar_faults",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            graph = build_recommendation_graph()
            compiled = graph.compile(checkpointer=MemorySaver())
            config = {"configurable": {"thread_id": "test_tier2"}}

            result = await compiled.ainvoke(
                {
                    "messages": [HumanMessage(content="process")],
                    "site_id": "S002",
                    "channel": "whatsapp",
                    "trigger": "manual",
                },
                config=config,
            )

            assert result["needs_input"] is True
            assert result["tier"] == "tier2"
            assert "APPROVE" in result["response"]


# ===================================================================
# Expired Recommendation Path
# ===================================================================


class TestExpiredPath:
    """Tests for expired recommendation handling."""

    @pytest.mark.asyncio
    async def test_stale_rec_expires(self):
        """Old recommendation → marked expired."""
        from langchain_core.messages import HumanMessage
        from langgraph.checkpoint.memory import MemorySaver

        from app.agents.recommendation_graph import build_recommendation_graph

        rec = make_recommendation(age_minutes=60)

        with (
            patch(
                "app.agents.recommendation_graph.get_pending_recommendations",
                new_callable=AsyncMock,
                return_value=[rec],
            ),
            patch(
                "app.agents.recommendation_graph.update_recommendation_status",
                new_callable=AsyncMock,
                return_value=True,
            ),
        ):
            graph = build_recommendation_graph()
            compiled = graph.compile(checkpointer=MemorySaver())
            config = {"configurable": {"thread_id": "test_expired"}}

            result = await compiled.ainvoke(
                {
                    "messages": [HumanMessage(content="process")],
                    "site_id": "S002",
                    "channel": "system",
                    "trigger": "scheduled",
                },
                config=config,
            )

            assert "expired" in result["response"].lower()


# ===================================================================
# Schedule Conflict Path
# ===================================================================


class TestScheduleConflictPath:
    """Tests for schedule conflict handling."""

    @pytest.mark.asyncio
    async def test_defers_on_conflict(self):
        """Active WO on equipment → deferred."""
        from langchain_core.messages import HumanMessage
        from langgraph.checkpoint.memory import MemorySaver

        from app.agents.recommendation_graph import build_recommendation_graph

        rec = make_recommendation()

        with (
            patch(
                "app.agents.recommendation_graph.get_pending_recommendations",
                new_callable=AsyncMock,
                return_value=[rec],
            ),
            patch(
                "app.agents.recommendation_graph.check_equipment_health",
                new_callable=AsyncMock,
                return_value={"health_score": 45, "is_healthy": False, "details": {}},
            ),
            patch(
                "app.agents.recommendation_graph.check_maintenance_calendar",
                new_callable=AsyncMock,
                return_value={
                    "has_conflict": True,
                    "work_orders": [{"id": "wo-1"}],
                    "reason": "Active maintenance on FCU-201",
                },
            ),
            patch(
                "app.agents.recommendation_tools.cross_reference_similar_faults",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            graph = build_recommendation_graph()
            compiled = graph.compile(checkpointer=MemorySaver())
            config = {"configurable": {"thread_id": "test_conflict"}}

            result = await compiled.ainvoke(
                {
                    "messages": [HumanMessage(content="process")],
                    "site_id": "S002",
                    "channel": "system",
                    "trigger": "manual",
                },
                config=config,
            )

            assert "deferred" in result["response"].lower() or "conflict" in result["response"].lower()


# ===================================================================
# No Pending Recommendations
# ===================================================================


class TestNoPendingPath:
    """Tests for empty queue handling."""

    @pytest.mark.asyncio
    async def test_no_recs_available(self):
        """No pending recs → processing complete with no-op message."""
        from langchain_core.messages import HumanMessage
        from langgraph.checkpoint.memory import MemorySaver

        from app.agents.recommendation_graph import build_recommendation_graph

        with patch(
            "app.agents.recommendation_graph.get_pending_recommendations",
            new_callable=AsyncMock,
            return_value=[],
        ):
            graph = build_recommendation_graph()
            compiled = graph.compile(checkpointer=MemorySaver())
            config = {"configurable": {"thread_id": "test_empty"}}

            result = await compiled.ainvoke(
                {
                    "messages": [HumanMessage(content="process")],
                    "site_id": "S002",
                    "channel": "system",
                    "trigger": "scheduled",
                },
                config=config,
            )

            assert result["processing_complete"] is True


# ===================================================================
# Chat Tool Registration
# ===================================================================


class TestChatToolRegistration:
    """Tests for process_recommendation chat tool."""

    def test_tool_registered(self):
        from app.services.chat_tools import TOOL_HANDLERS

        assert "process_recommendation" in TOOL_HANDLERS

    @pytest.mark.asyncio
    async def test_tool_invocation(self):
        from app.services.chat_tools import process_recommendation

        with patch("app.agents.get_recommendation_graph") as mock_graph:
            mock_compiled = MagicMock()
            mock_compiled.ainvoke = AsyncMock(
                return_value={
                    "response": "Advisory logged",
                    "tier": "tier1",
                    "needs_input": False,
                    "processing_complete": True,
                }
            )
            mock_graph.return_value = mock_compiled

            result = await process_recommendation(site_id="S002", channel="chat")
            assert result["success"] is True
            assert result["response"] == "Advisory logged"


# ===================================================================
# API Endpoint: process-pending
# ===================================================================


class TestProcessPendingEndpoint:
    """Tests for the recommendations API trigger endpoint."""

    def test_endpoint_model(self):
        from app.api.recommendations import ProcessPendingRequest

        req = ProcessPendingRequest()
        assert req.channel == "system"
        assert req.trigger == "manual"

    def test_endpoint_custom_channel(self):
        from app.api.recommendations import ProcessPendingRequest

        req = ProcessPendingRequest(channel="whatsapp", trigger="scheduled")
        assert req.channel == "whatsapp"
        assert req.trigger == "scheduled"


# ===================================================================
# Telegram Approval Handler
# ===================================================================


class TestTelegramApprovalHandler:
    """Tests for Telegram-based recommendation approvals."""

    @pytest.mark.asyncio
    async def test_non_approval_returns_none(self):
        from app.services.sentry_integration.work_order_notifier import (
            handle_telegram_recommendation_approval,
        )

        result = await handle_telegram_recommendation_approval("user123", "hello")
        assert result is None

    @pytest.mark.asyncio
    async def test_approve_command_fallback_not_found(self):
        from app.services.sentry_integration.work_order_notifier import (
            handle_telegram_recommendation_approval,
        )

        # Without an active session, fallback resolves rec ID directly.
        # When rec ID can't be found, returns a "not found" message.
        with patch("app.agents.get_recommendation_graph") as mock_graph:
            mock_compiled = MagicMock()
            mock_state = MagicMock()
            mock_state.values = {}  # No active session
            mock_compiled.aget_state = AsyncMock(return_value=mock_state)
            mock_graph.return_value = mock_compiled

            result = await handle_telegram_recommendation_approval("user123", "/approve abc123")
            assert result is not None
            assert "not found" in result.lower()

    @pytest.mark.asyncio
    async def test_reject_with_slash_prefix(self):
        from app.services.sentry_integration.work_order_notifier import (
            handle_telegram_recommendation_approval,
        )

        with patch("app.agents.get_recommendation_graph") as mock_graph:
            mock_compiled = MagicMock()
            mock_state = MagicMock()
            mock_state.values = {"needs_input": True}
            mock_compiled.aget_state = AsyncMock(return_value=mock_state)
            mock_compiled.ainvoke = AsyncMock(return_value={"response": "Rejected."})
            mock_graph.return_value = mock_compiled

            result = await handle_telegram_recommendation_approval("user123", "/reject abc123 too risky")
            assert result == "Rejected."
