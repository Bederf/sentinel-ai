"""Tests for tier routing engine.

Tests the confidence-based tier routing engine that routes AI recommendations
to appropriate autonomy tiers (Tier 1/2/3) based on confidence, risk level, and thresholds.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.tier_routing_engine import TierLevel, TierRoutingEngine


@pytest.mark.asyncio
class TestTierRoutingEngine:
    """Test tier routing engine functionality."""

    @pytest.fixture
    async def engine(self, monkeypatch):
        """Create a fresh tier routing engine for each test."""
        engine = TierRoutingEngine()
        # Mock settings to ensure consistent behavior
        engine.settings = MagicMock()
        engine.settings.parasite_enabled = True
        engine.settings.parasite_tier3_enabled = True
        engine.settings.parasite_confidence_tier2_min = 0.70
        engine.settings.parasite_confidence_tier3_min = 0.85
        engine.settings.parasite_max_auto_executions_per_hour = 100
        engine.settings.resolved_ingestion_mode = MagicMock(value="demo")

        # Mock dependencies
        engine.model_registry = AsyncMock()
        engine.model_registry.get_thresholds = AsyncMock(return_value=None)
        engine.parasite_repo = AsyncMock()
        engine.parasite_repo.record_decision = AsyncMock()

        # Mock supabase phase lookup — default to "supervised" so phase gate
        # doesn't override the risk/threshold/rate-limit logic under test.
        # Individual tests can override via _set_site_phase().
        _supabase_state = {"phase": "supervised"}
        _fake_table = MagicMock()
        _fake_table.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[{"onboarding_phase": _supabase_state["phase"]}]
        )
        _fake_sb = MagicMock()
        _fake_sb.table.return_value = _fake_table
        # Patch at the import source — tier_routing_engine does
        # `from app.database.supabase_client import get_supabase_client`,
        # so a local module-level patch would be shadowed.
        monkeypatch.setattr(
            "app.database.supabase_client.get_supabase_client",
            lambda: _fake_sb,
        )

        # Helper to override the mocked phase in a test:
        async def _set_site_phase(phase: str) -> None:
            _supabase_state["phase"] = phase
            _fake_table.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
                data=[{"onboarding_phase": phase}]
            )

        engine._set_site_phase = _set_site_phase  # type: ignore[attr-defined]
        return engine

    @pytest.mark.parametrize(
        "risk_level,confidence,expected_tier",
        [
            ("high", 0.9, TierLevel.TIER2.value),
            ("critical", 0.8, TierLevel.TIER2.value),
            ("limited", 0.9, TierLevel.TIER3.value),
            ("minimal", 0.95, TierLevel.TIER3.value),
        ],
    )
    async def test_tier_2_lock_for_high_critical_risk(self, engine, risk_level, confidence, expected_tier):
        """HIGH and CRITICAL risk must always route to Tier 2, never Tier 3.

        Control: APPROVAL-002 (HIGH/CRITICAL Locked to Human Approval).

        Tests that:
        1. HIGH/CRITICAL risk always caps at Tier 2 regardless of confidence
        2. LIMITED/MINIMAL risk can reach Tier 3 if confidence is high enough
        3. Tier 2 lock is enforced by setting tier3_threshold = 999.0

        This ensures dangerous operations cannot auto-execute even with
        very high confidence scores (0.9-0.95).
        """
        recommendation = {
            "site_id": "S002",
            "target_equipment": "S002-CHILLER-B1-001",
            "confidence_score": confidence,
            "risk_level": risk_level,
            "action_type": "set_setpoint",
            "action": {"point": "setpoint", "value": 25.0},
            "reason": f"Test recommendation with risk={risk_level}, confidence={confidence}",
        }

        result = await engine.route_recommendation(recommendation)

        # Assert tier matches expectation
        assert result.tier == expected_tier, (
            f"Risk={risk_level}, confidence={confidence} should route to {expected_tier}, but got {result.tier}"
        )

        # For HIGH/CRITICAL, verify it never routes to TIER3
        if risk_level in ("high", "critical"):
            assert result.tier != TierLevel.TIER3.value, (
                f"Risk level {risk_level} should be locked at {TierLevel.TIER2.value}, never {TierLevel.TIER3.value}"
            )
            assert result.action in ("advisory", "supervised"), (
                f"HIGH/CRITICAL risk should require approval, got action={result.action}"
            )

    async def test_tier_2_lock_overrides_tier3_enabled(self, engine):
        """Verify that HIGH/CRITICAL lock overrides tier3_enabled setting.

        Even with Tier 3 explicitly enabled in settings, HIGH/CRITICAL
        risk should still cap at Tier 2.
        """
        engine.settings.parasite_tier3_enabled = True

        recommendation = {
            "site_id": "S002",
            "target_equipment": "S002-CHILLER-B1-001",
            "confidence_score": 0.99,  # Very high confidence
            "risk_level": "critical",  # But critical risk
            "action_type": "set_setpoint",
            "action": {"point": "setpoint", "value": 25.0},
            "reason": "High confidence critical action should still be Tier 2",
        }

        result = await engine.route_recommendation(recommendation)

        assert result.tier == TierLevel.TIER2.value, (
            f"Critical risk with Tier 3 enabled should still cap at Tier 2, got {result.tier}"
        )

    async def test_tier_routing_disabled_parasite(self, engine):
        """Verify that disabled PARASITE routes all recommendations to Tier 1."""
        engine.settings.parasite_enabled = False

        recommendation = {
            "site_id": "S002",
            "target_equipment": "S002-CHILLER-B1-001",
            "confidence_score": 0.99,
            "risk_level": "minimal",
            "action_type": "set_setpoint",
            "action": {"point": "setpoint", "value": 25.0},
            "reason": "Test with PARASITE disabled",
        }

        result = await engine.route_recommendation(recommendation)

        assert result.tier == TierLevel.TIER1.value
        assert result.action == "advisory"

    @pytest.mark.parametrize(
        "phase",
        ["commissioning", "shadow_live", "advisory"],
    )
    async def test_phase_caps_tier1_for_no_control_phases(self, engine, phase):
        """Phases that disallow control writes must cap at Tier 1 (advisory only).

        onboarding_phase in {commissioning, shadow_live, advisory} means the
        site is in observe/recommend mode — no control writes, no approvals.
        Even with very high confidence and minimal risk, the phase gate must
        hold the recommendation to Tier 1.
        """
        await engine._set_site_phase(phase)  # type: ignore[attr-defined]

        recommendation = {
            "site_id": "S002",
            "target_equipment": "S002-CHILLER-B1-001",
            "confidence_score": 0.99,  # Would otherwise reach Tier 3
            "risk_level": "minimal",
            "action_type": "set_setpoint",
            "action": {"point": "setpoint", "value": 25.0},
            "reason": f"Phase '{phase}' must cap this at Tier 1 even with high confidence",
        }

        result = await engine.route_recommendation(recommendation)

        assert result.tier == TierLevel.TIER1.value, f"Phase '{phase}' should cap at Tier 1, got {result.tier}"
        assert result.action == "advisory"
        assert result.threshold_source == "phase_gate"

    async def test_advisory_phase_cap_replaces_silent_tier2_promotion(self, engine):
        """Regression: advisory phase used to fall through to Tier 2 with caps_auto_execute.

        Before the phase cap list was extended to include 'advisory', a site in
        advisory phase with high confidence could reach Tier 2 (require_approval)
        even though advisory phase semantically forbids control writes. The fix
        moves advisory into the explicit Tier 1 cap list.
        """
        await engine._set_site_phase("advisory")  # type: ignore[attr-defined]

        recommendation = {
            "site_id": "S002",
            "target_equipment": "S002-CHILLER-B1-001",
            "confidence_score": 0.95,  # Well above tier2 threshold (0.70)
            "risk_level": "minimal",
            "action_type": "set_setpoint",
            "action": {"point": "setpoint", "value": 25.0},
            "reason": "High-confidence minimal-risk rec in advisory phase",
        }

        result = await engine.route_recommendation(recommendation)

        # Must NOT be Tier 2 — that would mean user is being asked to approve
        # a control write in a phase that explicitly forbids control writes.
        assert result.tier == TierLevel.TIER1.value, (
            f"Advisory phase must not reach Tier 2 (no approvals), got {result.tier}"
        )

    async def test_extract_confidence_numeric(self, engine):
        """Test confidence extraction from numeric score."""
        recommendation = {"confidence_score": 0.85}
        confidence = engine._extract_confidence(recommendation)
        assert confidence == 0.85

    async def test_extract_confidence_fallback_string(self, engine):
        """Test confidence extraction from string representation."""
        recommendation = {"confidence": "high"}
        confidence = engine._extract_confidence(recommendation)
        assert confidence == 0.90

    async def test_extract_equipment_type(self, engine):
        """Test equipment type extraction from equipment code."""
        assert engine._extract_equipment_type({"target_equipment": "S002-CHILLER-B1-001"}) == "CHILLER"
        assert engine._extract_equipment_type({"target_equipment": "S002-VAV-101"}) == "VAV"
        assert engine._extract_equipment_type({"target_equipment": "S002-FCU-L1-A"}) == "FCU"

    async def test_hourly_rate_limit_check(self, engine):
        """Test that rate limit capping works correctly."""
        engine.settings.parasite_max_auto_executions_per_hour = 1

        # First recommendation should reach Tier 3
        rec1 = {
            "site_id": "S002",
            "target_equipment": "S002-CHILLER-B1-001",
            "confidence_score": 0.90,
            "risk_level": "minimal",
            "action_type": "set_setpoint",
            "action": {"point": "setpoint", "value": 25.0},
            "reason": "First high-confidence action",
        }
        result1 = await engine.route_recommendation(rec1)
        assert result1.tier == TierLevel.TIER3.value
        assert engine._auto_executions_this_hour == 1

        # Second recommendation should cap at Tier 2 due to rate limit
        rec2 = {
            "site_id": "S002",
            "target_equipment": "S002-CHILLER-B1-002",
            "confidence_score": 0.90,
            "risk_level": "minimal",
            "action_type": "set_setpoint",
            "action": {"point": "setpoint", "value": 26.0},
            "reason": "Second action (rate limited)",
        }
        result2 = await engine.route_recommendation(rec2)
        assert result2.tier == TierLevel.TIER2.value
