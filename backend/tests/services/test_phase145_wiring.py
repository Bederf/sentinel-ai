"""Tests for Phase 145 wiring: Event Intelligence, Control Policy, Decision Memory.

Validates that the three Phase 145 layers are correctly wired into
the scheduler, tool gating, and hybrid context assembly.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.models.control_policy import ControlMode
from app.models.operational_event import (
    EventSeverity,
    OperationalEvent,
    OperationalEventType,
)
from app.models.decision_memory import DecisionPattern


# -----------------------------------------------------------------
# Step 1: Event Intelligence -> Background Scheduler
# -----------------------------------------------------------------


class TestEventIntelligenceSchedulerWiring:
    """Verify event intelligence is wired into the background scheduler."""

    def test_scheduler_has_event_intelligence_method(self):
        """BackgroundSchedulerService must have the event intelligence job method."""
        from app.services.background_scheduler import BackgroundSchedulerService

        svc = BackgroundSchedulerService.__new__(BackgroundSchedulerService)
        assert hasattr(svc, "add_event_intelligence_job")
        assert hasattr(svc, "_run_event_intelligence")
        assert hasattr(svc, "_run_event_intelligence_async")

    @pytest.mark.asyncio
    async def test_event_intelligence_processes_sites(self):
        """The async handler should call process_site for each registered site."""
        from app.services.background_scheduler import BackgroundSchedulerService

        svc = BackgroundSchedulerService.__new__(BackgroundSchedulerService)

        mock_ei_svc = AsyncMock()
        mock_ei_svc.process_site = AsyncMock(return_value=[])

        with patch(
            "app.core.site_resolver.get_registered_site_ids",
            return_value=["site-002", "site-005"],
        ):
            with patch(
                "app.services.event_intelligence_service.get_event_intelligence_service",
                return_value=mock_ei_svc,
            ):
                await svc._run_event_intelligence_async()

                assert mock_ei_svc.process_site.call_count == 2
                mock_ei_svc.process_site.assert_any_call("site-002")
                mock_ei_svc.process_site.assert_any_call("site-005")

    @pytest.mark.asyncio
    async def test_event_intelligence_handles_no_sites(self):
        """Should not fail when no sites are registered."""
        from app.services.background_scheduler import BackgroundSchedulerService

        svc = BackgroundSchedulerService.__new__(BackgroundSchedulerService)

        with patch(
            "app.core.site_resolver.get_registered_site_ids",
            return_value=[],
        ):
            # Should not raise
            await svc._run_event_intelligence_async()

    @pytest.mark.asyncio
    async def test_event_intelligence_handles_site_failure(self):
        """Failure for one site should not prevent processing other sites."""
        from app.services.background_scheduler import BackgroundSchedulerService

        svc = BackgroundSchedulerService.__new__(BackgroundSchedulerService)

        mock_ei_svc = AsyncMock()
        call_count = 0

        async def side_effect(site_id):
            nonlocal call_count
            call_count += 1
            if site_id == "site-002":
                raise RuntimeError("test error")
            return []

        mock_ei_svc.process_site = AsyncMock(side_effect=side_effect)

        with patch(
            "app.core.site_resolver.get_registered_site_ids",
            return_value=["site-002", "site-005"],
        ):
            with patch(
                "app.services.event_intelligence_service.get_event_intelligence_service",
                return_value=mock_ei_svc,
            ):
                await svc._run_event_intelligence_async()
                # Both sites should have been attempted
                assert call_count == 2


# -----------------------------------------------------------------
# Step 2: Control Policy Engine -> Tool Gating
# -----------------------------------------------------------------


class TestControlPolicyToolGating:
    """Verify control policy engine is wired into simbiot_server.call_tool."""

    @pytest.mark.asyncio
    async def test_recommend_mode_blocks_write_tool(self):
        """In RECOMMEND mode, call_tool should reject write tools."""
        from app.mcp.simbiot_server import SIMBIOTMCPServer

        server = SIMBIOTMCPServer()

        with patch("app.services.control_policy_engine.get_control_policy_engine") as mock_engine_fn:
            mock_engine = MagicMock()
            mock_engine.get_control_mode.return_value = ControlMode.RECOMMEND
            mock_engine_fn.return_value = mock_engine

            result = await server.call_tool(
                "write_device_point", device_id="S002-FCU-101", point_name="setpoint", value=22.0
            )
            assert result.get("code") == "CONTROL_MODE_BLOCKED"
            assert "recommend" in result.get("error", "").lower()

    @pytest.mark.asyncio
    async def test_supervised_mode_passes_control_gate(self):
        """In SUPERVISED mode, write tools should pass the control mode gate.

        They'll then hit auth check (UNAUTHORIZED without auth_ctx), which
        proves the control gate didn't block them.
        """
        from app.mcp.simbiot_server import SIMBIOTMCPServer

        server = SIMBIOTMCPServer()

        with patch("app.services.control_policy_engine.get_control_policy_engine") as mock_engine_fn:
            mock_engine = MagicMock()
            mock_engine.get_control_mode.return_value = ControlMode.SUPERVISED
            mock_engine_fn.return_value = mock_engine

            result = await server.call_tool(
                "write_device_point", device_id="S002-FCU-101", point_name="setpoint", value=22.0
            )
            # Should NOT be CONTROL_MODE_BLOCKED — reaches auth check instead
            assert result.get("code") != "CONTROL_MODE_BLOCKED"
            # Without auth_ctx, the next gate (auth) catches it
            assert result.get("code") == "UNAUTHORIZED"

    @pytest.mark.asyncio
    async def test_read_tools_always_pass_control_gate(self):
        """Read tools should work regardless of control mode."""
        from app.mcp.simbiot_server import SIMBIOTMCPServer

        server = SIMBIOTMCPServer()

        # Don't need to mock policy engine — reads skip the check entirely
        result = await server.call_tool("get_sites")
        assert result.get("code") != "CONTROL_MODE_BLOCKED"

    @pytest.mark.asyncio
    async def test_control_engine_failure_blocks_writes(self):
        """If control policy engine fails to load, writes are BLOCKED (fail-closed)."""
        from app.mcp.simbiot_server import SIMBIOTMCPServer

        server = SIMBIOTMCPServer()

        with patch(
            "app.services.control_policy_engine.get_control_policy_engine",
            side_effect=RuntimeError("engine broken"),
        ):
            result = await server.call_tool(
                "write_device_point", device_id="S002-FCU-101", point_name="setpoint", value=22.0
            )
            assert result.get("code") == "CONTROL_ENGINE_UNAVAILABLE"

    @pytest.mark.asyncio
    async def test_control_engine_failure_does_not_block_reads(self):
        """If control policy engine fails to load, reads should still work."""
        from app.mcp.simbiot_server import SIMBIOTMCPServer

        server = SIMBIOTMCPServer()

        with patch(
            "app.services.control_policy_engine.get_control_policy_engine",
            side_effect=RuntimeError("engine broken"),
        ):
            # Read tool should still work (fail-open for reads)
            result = await server.call_tool("get_sites")
            assert result.get("code") != "CONTROL_ENGINE_UNAVAILABLE"

    @pytest.mark.asyncio
    async def test_policy_check_failed_blocks_write(self):
        """If CommandEnvelope policy check fails, write is blocked.

        Needs auth_ctx to pass the auth gate first.
        """
        from app.mcp.simbiot_server import SIMBIOTMCPServer

        server = SIMBIOTMCPServer()

        # Create a mock auth context to pass the auth gate
        mock_auth = MagicMock()
        mock_auth.user_id = "test-user"
        mock_auth.email = "test@example.com"
        mock_auth.role = "operator"
        mock_auth.auth_method = "jwt"

        with patch("app.services.control_policy_engine.get_control_policy_engine") as mock_engine_fn:
            mock_engine = MagicMock()
            mock_engine.get_control_mode.return_value = ControlMode.FULL_CONTROL
            # Envelope fails policy check (e.g., setpoint out of range)
            mock_envelope = MagicMock()
            mock_envelope.policy_check_passed = False
            mock_envelope.policy_check_details = {"setpoint_violation": "value 99 exceeds max 28"}
            mock_envelope.envelope_id = "CMD-test-456"
            mock_engine.evaluate_action = AsyncMock(return_value=mock_envelope)
            mock_engine_fn.return_value = mock_engine

            # Patch auth checks to pass
            with patch("app.mcp.tool_permissions.check_mcp_tool_access", return_value=(True, "")):
                with patch("app.security.tool_policy.check_mcp_admin_tool_access", return_value=(True, "")):
                    with patch("app.mcp.rate_limiter.check_rate_limit", return_value=(True, "", 0)):
                        result = await server.call_tool(
                            "write_device_point",
                            device_id="S002-FCU-101",
                            point_name="setpoint",
                            value=99.0,
                            _auth_context=mock_auth,
                        )
                        assert result.get("code") == "POLICY_CHECK_FAILED"
                        assert "CMD-test-456" in result.get("envelope_id", "")


# -----------------------------------------------------------------
# Step 3: Decision Memory + Events -> HybridContext
# -----------------------------------------------------------------


class TestHybridContextDecisionMemoryWiring:
    """Verify decision memory and active events are wired into HybridContext."""

    def test_hybrid_context_has_new_fields(self):
        """HybridContext should have decision_memory and active_events fields."""
        from app.services.hybrid_query_service import HybridContext

        ctx = HybridContext()
        assert hasattr(ctx, "decision_memory")
        assert hasattr(ctx, "active_events")
        assert ctx.decision_memory is None
        assert ctx.active_events == []

    def test_to_dict_includes_new_fields(self):
        """to_dict should include decision_memory and active_events."""
        from app.services.hybrid_query_service import HybridContext

        ctx = HybridContext(
            decision_memory="test pattern data",
            active_events=[{"event_type": "temperature_deviation"}],
        )
        d = ctx.to_dict()
        assert d["decision_memory"] == "test pattern data"
        assert len(d["active_events"]) == 1

    def test_format_for_prompt_includes_events(self):
        """format_for_prompt should render active events."""
        from app.services.hybrid_query_service import HybridContext

        ctx = HybridContext(
            equipment_id="S002-CHILLER-B1-001",
            active_events=[
                {
                    "event_type": "temperature_deviation",
                    "severity": "high",
                    "description": "CHW supply 5°C above setpoint",
                    "duration_minutes": 18.5,
                    "trend": "rising",
                }
            ],
        )
        text = ctx.format_for_prompt()
        assert "temperature_deviation" in text
        assert "5°C above" in text
        assert "18 min" in text

    def test_format_for_prompt_includes_decision_memory(self):
        """format_for_prompt should include decision memory text."""
        from app.services.hybrid_query_service import HybridContext

        ctx = HybridContext(
            equipment_id="S002-CHILLER-B1-001",
            decision_memory="Historical Patterns:\n  - condenser fouling -> tube_cleaning (85% confidence)",
        )
        text = ctx.format_for_prompt()
        assert "condenser fouling" in text
        assert "tube_cleaning" in text

    @pytest.mark.asyncio
    async def test_gather_active_events(self):
        """_gather_active_events should pull events from EventIntelligenceService."""
        from app.services.hybrid_query_service import HybridContext, HybridQueryService

        svc = HybridQueryService(site_id="site-002")
        ctx = HybridContext(site_id="site-002")

        from datetime import datetime, timezone
        from app.models.operational_event import _generate_event_id

        mock_event = OperationalEvent(
            event_id=_generate_event_id(),
            event_type=OperationalEventType.TEMPERATURE_DEVIATION,
            equipment_id="S002-CHILLER-B1-001",
            site_id="site-002",
            severity=EventSeverity.HIGH,
            timestamp=datetime.now(timezone.utc),
            signals=[{"point": "chw_supply_temp", "value": 12.0, "setpoint": 7.0}],
            description="CHW supply 5°C above setpoint",
            duration_minutes=18.5,
            trend="rising",
        )

        with patch("app.services.event_intelligence_service.get_event_intelligence_service") as mock_ei:
            mock_svc = AsyncMock()
            mock_svc.get_active_events = AsyncMock(return_value=[mock_event])
            mock_ei.return_value = mock_svc

            await svc._gather_active_events(ctx, "S002-CHILLER-B1-001")
            assert len(ctx.active_events) == 1
            assert ctx.active_events[0]["event_type"] == "temperature_deviation"
            assert "event_intelligence" in ctx.sources_used

    @pytest.mark.asyncio
    async def test_gather_decision_memory(self):
        """_gather_decision_memory should pull patterns and format for prompt."""
        from app.services.hybrid_query_service import HybridContext, HybridQueryService

        svc = HybridQueryService(site_id="site-002")
        ctx = HybridContext(
            site_id="site-002",
            equipment_type="CHILLER",
        )

        mock_pattern = DecisionPattern(
            event_type="temperature_deviation",
            equipment_type="CHILLER",
            likely_diagnosis="condenser fouling",
            diagnosis_confidence=0.85,
            recommended_action="tube_cleaning",
            total_occurrences=10,
            resolved_count=8,
            success_rate=0.80,
        )

        with patch("app.services.decision_memory_service.get_decision_memory_service") as mock_dm:
            mock_svc = AsyncMock()
            mock_svc.get_recommended_action = AsyncMock(
                side_effect=lambda et, eqt: mock_pattern if et == "temperature_deviation" else None
            )
            mock_svc.find_similar_decisions = AsyncMock(return_value=[])
            mock_svc.format_for_prompt = MagicMock(
                return_value="Historical Patterns:\n  - condenser fouling (85% confidence)"
            )
            mock_dm.return_value = mock_svc

            await svc._gather_decision_memory(ctx, "S002-CHILLER-B1-001")
            assert ctx.decision_memory is not None
            assert "condenser fouling" in ctx.decision_memory
            assert "decision_memory" in ctx.sources_used

    @pytest.mark.asyncio
    async def test_query_includes_decision_memory(self):
        """Full query() should include decision memory when enabled."""
        from app.services.hybrid_query_service import HybridQueryService

        svc = HybridQueryService(site_id="site-002")

        with patch.object(svc, "_resolve_equipment", new_callable=AsyncMock, return_value="S002-FCU-101"):
            with patch.object(svc, "_gather_brick_context", new_callable=AsyncMock):
                with patch.object(svc, "_gather_document_context", new_callable=AsyncMock):
                    with patch.object(svc, "_gather_telemetry", new_callable=AsyncMock):
                        with patch.object(svc, "_gather_ml_context", new_callable=AsyncMock):
                            with patch.object(svc, "_gather_active_events", new_callable=AsyncMock) as mock_events:
                                with patch.object(svc, "_gather_decision_memory", new_callable=AsyncMock) as mock_dm:
                                    ctx = await svc.query(equipment_id="S002-FCU-101")
                                    mock_events.assert_called_once()
                                    mock_dm.assert_called_once()

    @pytest.mark.asyncio
    async def test_query_can_disable_decision_memory(self):
        """query() with include_decision_memory=False should skip it."""
        from app.services.hybrid_query_service import HybridQueryService

        svc = HybridQueryService(site_id="site-002")

        with patch.object(svc, "_resolve_equipment", new_callable=AsyncMock, return_value="S002-FCU-101"):
            with patch.object(svc, "_gather_brick_context", new_callable=AsyncMock):
                with patch.object(svc, "_gather_document_context", new_callable=AsyncMock):
                    with patch.object(svc, "_gather_telemetry", new_callable=AsyncMock):
                        with patch.object(svc, "_gather_ml_context", new_callable=AsyncMock):
                            with patch.object(svc, "_gather_active_events", new_callable=AsyncMock):
                                with patch.object(svc, "_gather_decision_memory", new_callable=AsyncMock) as mock_dm:
                                    ctx = await svc.query(
                                        equipment_id="S002-FCU-101",
                                        include_decision_memory=False,
                                        include_active_events=False,
                                    )
                                    mock_dm.assert_not_called()
