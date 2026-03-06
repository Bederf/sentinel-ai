"""Tests for the Control Policy Engine.

Phase 145: Control Policy Engine.
"""

import pytest
from unittest.mock import AsyncMock, patch

from app.models.control_policy import (
    AssetControlPolicy,
    CommandEnvelope,
    ControlMode,
)
from app.services.control_policy_engine import (
    ControlPolicyEngine,
    reset_control_policy_engine,
    WRITE_TOOL_NAMES,
    READONLY_TOOL_NAMES,
)


@pytest.fixture
def engine():
    """Create a fresh engine for each test."""
    reset_control_policy_engine()
    e = ControlPolicyEngine()
    return e


# -----------------------------------------------------------------
# Control Mode
# -----------------------------------------------------------------


class TestControlMode:
    def test_simulation_maps_to_recommend(self, engine):
        with patch("app.services.control_policy_engine.settings") as mock_settings:
            mock_settings.resolved_ingestion_mode = "simulation"
            mode = engine.get_control_mode()
            assert mode == ControlMode.RECOMMEND

    def test_shadow_live_maps_to_supervised(self, engine):
        with patch("app.services.control_policy_engine.settings") as mock_settings:
            mock_settings.resolved_ingestion_mode = "shadow_live"
            mode = engine.get_control_mode()
            assert mode == ControlMode.SUPERVISED

    def test_live_control_auto_execute_maps_to_full(self, engine):
        with patch("app.services.control_policy_engine.settings") as mock_settings:
            mock_settings.resolved_ingestion_mode = "live_control"
            mock_settings.control_tier = "auto_execute"
            mode = engine.get_control_mode()
            assert mode == ControlMode.FULL_CONTROL

    def test_live_control_monitor_maps_to_recommend(self, engine):
        with patch("app.services.control_policy_engine.settings") as mock_settings:
            mock_settings.resolved_ingestion_mode = "live_control"
            mock_settings.control_tier = "monitor"
            mode = engine.get_control_mode()
            assert mode == ControlMode.RECOMMEND


# -----------------------------------------------------------------
# Tool Gating
# -----------------------------------------------------------------


class TestToolGating:
    def test_recommend_mode_no_write_tools(self, engine):
        with patch.object(engine, "get_control_mode", return_value=ControlMode.RECOMMEND):
            tools = engine.get_available_tools()
            for write_tool in WRITE_TOOL_NAMES:
                assert write_tool not in tools

    def test_supervised_mode_has_write_tools(self, engine):
        with patch.object(engine, "get_control_mode", return_value=ControlMode.SUPERVISED):
            tools = engine.get_available_tools()
            for write_tool in WRITE_TOOL_NAMES:
                assert write_tool in tools

    def test_full_control_has_write_tools(self, engine):
        with patch.object(engine, "get_control_mode", return_value=ControlMode.FULL_CONTROL):
            tools = engine.get_available_tools()
            for write_tool in WRITE_TOOL_NAMES:
                assert write_tool in tools

    def test_readonly_tools_always_available(self, engine):
        for mode in ControlMode:
            with patch.object(engine, "get_control_mode", return_value=mode):
                tools = engine.get_available_tools()
                for read_tool in READONLY_TOOL_NAMES:
                    assert read_tool in tools


# -----------------------------------------------------------------
# Policy Management
# -----------------------------------------------------------------


class TestPolicyManagement:
    def test_default_policies_loaded(self, engine):
        assert engine.get_policy("CHILLER") is not None
        assert engine.get_policy("AHU") is not None
        assert engine.get_policy("BESS") is not None

    def test_get_policy_case_insensitive(self, engine):
        assert engine.get_policy("chiller") is not None

    def test_register_custom_policy(self, engine):
        policy = AssetControlPolicy(
            equipment_type="CUSTOM",
            setpoint_limits={"temp": {"min": 0, "max": 50}},
            max_auto_per_hour=2,
        )
        engine.register_policy(policy)
        assert engine.get_policy("CUSTOM") is not None


# -----------------------------------------------------------------
# Action Evaluation
# -----------------------------------------------------------------


class TestActionEvaluation:
    @pytest.mark.asyncio
    async def test_recommend_mode_blocks_writes(self, engine):
        with patch.object(engine, "get_control_mode", return_value=ControlMode.RECOMMEND):
            envelope = await engine.evaluate_action(
                target_equipment="S002-CHILLER-B1-001",
                site_id="site-002",
                proposed_action={"point": "chw_supply_temp", "value": 7.5},
                reason="test",
            )
            assert not envelope.policy_check_passed
            assert "recommend_mode" in envelope.policy_check_details.get("blocked_by", "")

    @pytest.mark.asyncio
    async def test_setpoint_limits_enforced(self, engine):
        with patch.object(engine, "get_control_mode", return_value=ControlMode.SUPERVISED):
            envelope = await engine.evaluate_action(
                target_equipment="S002-CHILLER-B1-001",
                site_id="site-002",
                proposed_action={"point": "chw_supply_temp", "value": 15.0},  # Max is 12.0
                reason="test",
            )
            assert not envelope.policy_check_passed
            assert "setpoint_violation" in envelope.policy_check_details

    @pytest.mark.asyncio
    async def test_setpoint_within_limits_passes(self, engine):
        with patch.object(engine, "get_control_mode", return_value=ControlMode.SUPERVISED):
            with patch.object(engine, "_capture_previous_state", new_callable=AsyncMock, return_value=None):
                envelope = await engine.evaluate_action(
                    target_equipment="S002-CHILLER-B1-001",
                    site_id="site-002",
                    proposed_action={"point": "chw_supply_temp", "value": 7.5},
                    reason="test",
                )
                assert envelope.policy_check_passed

    @pytest.mark.asyncio
    async def test_supervised_requires_approval(self, engine):
        with patch.object(engine, "get_control_mode", return_value=ControlMode.SUPERVISED):
            with patch.object(engine, "_capture_previous_state", new_callable=AsyncMock, return_value=None):
                envelope = await engine.evaluate_action(
                    target_equipment="S002-FCU-101",
                    site_id="site-002",
                    proposed_action={"point": "zone_temp_setpoint", "value": 22.0},
                )
                assert envelope.requires_approval

    @pytest.mark.asyncio
    async def test_full_control_no_approval(self, engine):
        with patch.object(engine, "get_control_mode", return_value=ControlMode.FULL_CONTROL):
            with patch.object(engine, "_capture_previous_state", new_callable=AsyncMock, return_value=None):
                envelope = await engine.evaluate_action(
                    target_equipment="S002-FCU-101",
                    site_id="site-002",
                    proposed_action={"point": "zone_temp_setpoint", "value": 22.0},
                )
                assert not envelope.requires_approval

    @pytest.mark.asyncio
    async def test_rate_limiting(self, engine):
        """Exceeding max_auto_per_hour should be rejected."""
        with patch.object(engine, "get_control_mode", return_value=ControlMode.FULL_CONTROL):
            with patch.object(engine, "_capture_previous_state", new_callable=AsyncMock, return_value=None):
                # BESS has max_auto_per_hour=3
                for _ in range(3):
                    engine._record_execution("S002-BESS-B1-001")

                envelope = await engine.evaluate_action(
                    target_equipment="S002-BESS-B1-001",
                    site_id="site-002",
                    proposed_action={"point": "charge_power_kw", "value": 10.0},
                )
                assert not envelope.policy_check_passed
                assert "rate_limit_violation" in envelope.policy_check_details


# -----------------------------------------------------------------
# Execution
# -----------------------------------------------------------------


class TestExecution:
    @pytest.mark.asyncio
    async def test_execute_requires_approval_in_supervised(self, engine):
        envelope = CommandEnvelope(
            control_mode=ControlMode.SUPERVISED,
            policy_check_passed=True,
            requires_approval=True,
        )
        engine._active_envelopes[envelope.envelope_id] = envelope

        with pytest.raises(ValueError, match="Approval required"):
            await engine.execute_envelope(envelope.envelope_id)

    @pytest.mark.asyncio
    async def test_execute_with_approval(self, engine):
        envelope = CommandEnvelope(
            control_mode=ControlMode.SUPERVISED,
            policy_check_passed=True,
            requires_approval=True,
            target_equipment="S002-FCU-101",
        )
        engine._active_envelopes[envelope.envelope_id] = envelope

        result = await engine.execute_envelope(envelope.envelope_id, approved_by="operator@test.com")
        assert result.executed
        assert result.approved_by == "operator@test.com"

    @pytest.mark.asyncio
    async def test_rollback(self, engine):
        envelope = CommandEnvelope(
            control_mode=ControlMode.FULL_CONTROL,
            policy_check_passed=True,
            executed=True,
            target_equipment="S002-FCU-101",
        )
        engine._active_envelopes[envelope.envelope_id] = envelope

        result = await engine.rollback_envelope(envelope.envelope_id, "test rollback")
        assert result.rolled_back


# -----------------------------------------------------------------
# Equipment type extraction
# -----------------------------------------------------------------


class TestHelpers:
    def test_extract_equipment_type(self, engine):
        assert engine._extract_equipment_type("S002-CHILLER-B1-001") == "CHILLER"
        assert engine._extract_equipment_type("S002-FCU-101") == "FCU"
        assert engine._extract_equipment_type("S002-BESS-B1-001") == "BESS"

    def test_command_envelope_to_dict(self):
        envelope = CommandEnvelope(
            target_equipment="S002-FCU-101",
            site_id="site-002",
        )
        d = envelope.to_dict()
        assert d["target_equipment"] == "S002-FCU-101"
        assert d["control_mode"] == "recommend"
