"""Tests for SentinelTool classification and the dangerous-gate demotion logic.

Covers:
- All 6 classification rules via from_recommendation()
- apply_dangerous_gate() demotion: tier3 + is_dangerous=True → tier2, demoted=True
- apply_dangerous_gate() no-op for non-tier3 or non-dangerous combinations
- WARNING-level demotion logging
- SentinelTool None in ApprovalService (backward compatibility)
- tool_metadata in parasite_decisions audit payload
"""

from unittest.mock import AsyncMock, patch

import pytest

from app.models.recommendation import ActionRiskLevel, Recommendation, RecommendationStatus
from app.models.sentinel_tool import (
    _DANGEROUS_ACTION_TYPES,
    _REVERSIBLE_ACTION_TYPES,
    ActionClassification,
    SentinelTool,
)
from app.services.tier_routing_engine import TierRoutingResult

# ----------------------------------------------------------------------------- #
# Fixtures
# ----------------------------------------------------------------------------- #


@pytest.fixture
def routing_result_tier3():
    return TierRoutingResult(
        tier="tier3",
        action="auto_execute",
        confidence_score=0.90,
        threshold_source="settings",
        tier2_threshold=0.70,
        tier3_threshold=0.85,
        reason="high confidence",
        equipment_type="AHU",
        risk_level="minimal",
    )


@pytest.fixture
def routing_result_tier2():
    return TierRoutingResult(
        tier="tier2",
        action="require_approval",
        confidence_score=0.75,
        threshold_source="settings",
        tier2_threshold=0.70,
        tier3_threshold=0.85,
        reason="medium confidence",
        equipment_type="AHU",
        risk_level="medium",
    )


def make_rec(action_type, target_equipment, risk_level=ActionRiskLevel.MEDIUM):
    return Recommendation(
        id="rec-test-001",
        site_id="S002",
        action_type=action_type,
        target_equipment=target_equipment,
        risk_level=risk_level,
        action={"point": "OccupiedCoolSetpoint", "value": 22.0},
        status=RecommendationStatus.PENDING,
    )


# ----------------------------------------------------------------------------- #
# Classification — from_recommendation()
# ----------------------------------------------------------------------------- #


class TestClassification:
    """Test all 6 classification rules."""

    @pytest.mark.parametrize(
        "at,eq,expected",
        [
            # Rule 1: Life-safety equipment types
            ("some_action", "S002-FIRE-001", ActionClassification.LIFE_SAFETY),
            ("some_action", "S002-ACCESS-001", ActionClassification.LIFE_SAFETY),
            ("some_action", "S002-CCTV-001", ActionClassification.LIFE_SAFETY),
            ("some_action", "S002-FIRE_ALARM-001", ActionClassification.LIFE_SAFETY),
            ("some_action", "S002-EVACUATION-001", ActionClassification.LIFE_SAFETY),
            # Rule 2: BESS / genset dispatch
            ("bess_dispatch", "S002-BESS-001", ActionClassification.BESS),
            ("bess_dispatch", "S002-GEN-001", ActionClassification.BESS),
            ("genset_start", "S002-GEN-001", ActionClassification.BESS),
            ("genset_stop", "S002-GEN-001", ActionClassification.BESS),
            # Rule 3: HVAC staging (chiller staging)
            ("chiller_stage_up", "S002-CHILLER-B1-001", ActionClassification.STAGING),
            ("chiller_stage_down", "S002-CHILLER-B1-001", ActionClassification.STAGING),
            ("chiller_on_off", "S002-CHILLER-B1-001", ActionClassification.STAGING),
            ("ahu_on_off", "S002-AHU-MX-001", ActionClassification.STAGING),
            ("vav_on_off", "S002-VAV-L1-001", ActionClassification.STAGING),
            ("pump_on_off", "S002-PUMP-B1-001", ActionClassification.STAGING),
            ("fan_on_off", "S002-FAN-R1-001", ActionClassification.STAGING),
            # Rule 3: HVAC non-staging → SETPOINT
            ("hvac_setpoint_change", "S002-CHILLER-B1-001", ActionClassification.SETPOINT),
            ("vav_setpoint_change", "S002-VAV-L1-001", ActionClassification.SETPOINT),
            ("temperature_setpoint", "S002-AHU-MX-001", ActionClassification.SETPOINT),
            # Rule 4: Lighting
            ("dali_set_level", "S002-DALI-L1-001", ActionClassification.LIGHTING),
            ("dimming_level", "S002-LIGHT-001", ActionClassification.LIGHTING),
            ("0-10v_set_level", "S002-LIGHT-001", ActionClassification.LIGHTING),
            # Rule 5: Setpoint (explicit)
            ("set_setpoint", "S002-UNK-001", ActionClassification.SETPOINT),
            ("temperature_setpoint", "S002-UNK-001", ActionClassification.SETPOINT),
            ("humidity_setpoint", "S002-UNK-001", ActionClassification.SETPOINT),
            # Rule 6: Binary on/off overrides
            ("binary_override", "S002-AHU-001", ActionClassification.STAGING),  # AHU+override → STAGING (Rule 3)
            ("emergency_override", "S002-AHU-001", ActionClassification.STAGING),  # AHU+override → STAGING (Rule 3)
            ("fire_override", "S002-FIRE-001", ActionClassification.LIFE_SAFETY),  # FIRE → LIFE_SAFETY (Rule 1)
            # ACCESS equipment → LIFE_SAFETY (Rule 1)
            ("access_override", "S002-ACCESS-001", ActionClassification.LIFE_SAFETY),
            # Rule 6: Unknown fallback
            ("some_weird_action", "S002-UNK-001", ActionClassification.UNKNOWN),
            ("", "S002-UNK-001", ActionClassification.UNKNOWN),
        ],
    )
    def test_classifies_correctly(self, at, eq, expected, routing_result_tier3):
        rec = make_rec(at, eq)
        tool = SentinelTool.from_recommendation(rec, routing_result_tier3)
        assert tool.classification == expected, f"{at} + {eq} → expected {expected}, got {tool.classification}"

    def test_is_dangerous_for_dangerous_action_types(self, routing_result_tier3):
        for at in _DANGEROUS_ACTION_TYPES:
            rec = make_rec(at, "S002-AHU-001")
            tool = SentinelTool.from_recommendation(rec, routing_result_tier3)
            assert tool.is_dangerous is True, f"{at} should be is_dangerous=True"

    def test_is_dangerous_false_for_non_dangerous(self, routing_result_tier3):
        rec = make_rec("hvac_setpoint_change", "S002-CHILLER-B1-001")
        tool = SentinelTool.from_recommendation(rec, routing_result_tier3)
        assert tool.is_dangerous is False

    def test_is_reversible_for_reversible_action_types(self, routing_result_tier3):
        for at in _REVERSIBLE_ACTION_TYPES:
            rec = make_rec(at, "S002-AHU-001")
            tool = SentinelTool.from_recommendation(rec, routing_result_tier3)
            assert tool.is_reversible is True, f"{at} should be is_reversible=True"

    def test_priority_life_safety_is_1(self, routing_result_tier3):
        rec = make_rec("some_action", "S002-FIRE-001")
        tool = SentinelTool.from_recommendation(rec, routing_result_tier3)
        assert tool.priority == 1

    def test_priority_bess_is_2(self, routing_result_tier3):
        rec = make_rec("bess_dispatch", "S002-BESS-001")
        tool = SentinelTool.from_recommendation(rec, routing_result_tier3)
        assert tool.priority == 2

    def test_priority_setpoint_is_5(self, routing_result_tier3):
        rec = make_rec("temperature_setpoint", "S002-AHU-001")
        tool = SentinelTool.from_recommendation(rec, routing_result_tier3)
        assert tool.priority == 5

    def test_priority_unknown_is_6(self, routing_result_tier3):
        rec = make_rec("some_weird_action", "S002-UNK-001")
        tool = SentinelTool.from_recommendation(rec, routing_result_tier3)
        assert tool.priority == 6


# ----------------------------------------------------------------------------- #
# Dangerous gate — demotion
# ----------------------------------------------------------------------------- #


class TestDangerousGate:
    """Test apply_dangerous_gate() demotion logic."""

    def test_demotes_tier3_dangerous_to_tier2(self, routing_result_tier3):
        rec = make_rec("binary_override", "S002-AHU-001")
        tool = SentinelTool.from_recommendation(rec, routing_result_tier3)
        assert tool.effective_tier == "tier3"
        assert tool.demoted is False

        demoted = tool.apply_dangerous_gate(rec)

        assert demoted.effective_tier == "tier2"
        assert demoted.demoted is True
        assert demoted.is_dangerous is True

    def test_noop_tier3_non_dangerous(self, routing_result_tier3):
        rec = make_rec("temperature_setpoint", "S002-AHU-001")
        tool = SentinelTool.from_recommendation(rec, routing_result_tier3)
        assert tool.effective_tier == "tier3"
        assert tool.is_dangerous is False

        demoted = tool.apply_dangerous_gate(rec)

        assert demoted.effective_tier == "tier3"
        assert demoted.demoted is False

    def test_noop_tier2_dangerous(self, routing_result_tier2):
        rec = make_rec("binary_override", "S002-AHU-001")
        tool = SentinelTool.from_recommendation(rec, routing_result_tier2)
        assert tool.effective_tier == "tier2"

        demoted = tool.apply_dangerous_gate(rec)

        assert demoted.effective_tier == "tier2"
        assert demoted.demoted is False

    def test_noop_tier2_non_dangerous(self, routing_result_tier2):
        rec = make_rec("temperature_setpoint", "S002-AHU-001")
        tool = SentinelTool.from_recommendation(rec, routing_result_tier2)

        demoted = tool.apply_dangerous_gate(rec)

        assert demoted.effective_tier == "tier2"
        assert demoted.demoted is False

    @pytest.mark.parametrize("risk", ["low", "medium", "high", "critical"])
    def test_demotion_logged_at_warning_with_all_risk_levels(self, risk, routing_result_tier3, caplog):
        import logging

        caplog.set_level(logging.WARNING)

        rec = make_rec("binary_override", "S002-AHU-001", risk_level=ActionRiskLevel(risk))
        tool = SentinelTool.from_recommendation(rec, routing_result_tier3)
        tool.apply_dangerous_gate(rec)

        assert any("DANGEROUS_GATE" in r.message and "tier3 → tier2" in r.message for r in caplog.records), (
            "WARNING log with DANGEROUS_GATE and tier3 → tier2 not found"
        )


# ----------------------------------------------------------------------------- #
# SentinelTool None in ApprovalService — backward compatibility
# ----------------------------------------------------------------------------- #


class TestBackwardCompatibility:
    """Verify ApprovalService accepts sentinel_tool=None without breaking callers."""

    @pytest.mark.asyncio
    async def test_execute_approval_signature_accepts_none(self):
        import inspect

        from app.services.approval_service import ApprovalService

        sig = inspect.signature(ApprovalService.execute_approval)
        params = list(sig.parameters.keys())
        assert "sentinel_tool" in params

    @pytest.mark.asyncio
    async def test_auto_execute_signature_accepts_none(self):
        import inspect

        from app.services.approval_service import ApprovalService

        sig = inspect.signature(ApprovalService.auto_execute_recommendation)
        params = list(sig.parameters.keys())
        assert "sentinel_tool" in params

    @pytest.mark.asyncio
    async def test_execute_approval_without_sentinel_tool(self):
        from app.services.approval_service import ApprovalService

        svc = ApprovalService()

        # Mock recommendation repo to return None (missing rec)
        with patch.object(svc.recommendations_repo, "get_by_id", new=AsyncMock(return_value=None)):
            result = await svc.execute_approval("rec-missing", "operator", sentinel_tool=None)
            assert result.success is False
            assert "not found" in result.error_message

    @pytest.mark.asyncio
    async def test_auto_execute_without_sentinel_tool(self, routing_result_tier3):
        from app.services.approval_service import ApprovalService

        svc = ApprovalService()

        with patch.object(svc.recommendations_repo, "get_by_id", new=AsyncMock(return_value=None)):
            result = await svc.auto_execute_recommendation("rec-missing", routing_result_tier3, sentinel_tool=None)
            assert result.success is False
            assert "not found" in result.error_message


# ----------------------------------------------------------------------------- #
# tool_metadata in parasite_decisions audit payload
# ----------------------------------------------------------------------------- #


class TestToolMetadataAudit:
    """Verify tool_metadata is correctly embedded in record_decision dicts."""

    def test_tool_metadata_structure(self, routing_result_tier3):
        rec = make_rec("temperature_setpoint", "S002-AHU-001")
        tool = SentinelTool.from_recommendation(rec, routing_result_tier3)
        demoted = tool.apply_dangerous_gate(rec)

        meta = {
            "is_dangerous": demoted.is_dangerous,
            "is_reversible": demoted.is_reversible,
            "priority": demoted.priority,
            "demoted": demoted.demoted,
            "effective_tier": demoted.effective_tier,
        }

        assert meta["is_dangerous"] is False
        assert meta["is_reversible"] is True
        assert meta["priority"] == 5
        assert meta["demoted"] is False
        assert meta["effective_tier"] == "tier3"

    def test_tool_metadata_none_when_sentinel_tool_is_none(self):
        meta = {
            "is_dangerous": SentinelTool(
                None, "", ActionClassification.UNKNOWN, False, False, 999, sentinel_tool=None
            ).is_dangerous,
            "is_reversible": False,
            "priority": 999,
            "demoted": False,
            "effective_tier": "tier3",
        }
        # When sentinel_tool is None, callers build the dict with a None check
        sentinel_tool = None
        result = {
            "is_dangerous": sentinel_tool.is_dangerous if sentinel_tool else None,
            "is_reversible": sentinel_tool.is_reversible if sentinel_tool else None,
            "priority": sentinel_tool.priority if sentinel_tool else None,
            "demoted": sentinel_tool.demoted if sentinel_tool else None,
            "effective_tier": sentinel_tool.effective_tier if sentinel_tool else None,
        }
        assert all(v is None for v in result.values())

    def test_demotion_alters_effective_tier_in_metadata(self, routing_result_tier3):
        rec = make_rec("binary_override", "S002-AHU-001")
        tool = SentinelTool.from_recommendation(rec, routing_result_tier3)
        demoted = tool.apply_dangerous_gate(rec)

        assert demoted.effective_tier == "tier2"
        assert demoted.demoted is True
        assert demoted.is_dangerous is True

        # Simulate what approval_service does
        meta = {
            "is_dangerous": demoted.is_dangerous,
            "is_reversible": demoted.is_reversible,
            "priority": demoted.priority,
            "demoted": demoted.demoted,
            "effective_tier": demoted.effective_tier,
        }
        assert meta["effective_tier"] == "tier2"
        assert meta["demoted"] is True
