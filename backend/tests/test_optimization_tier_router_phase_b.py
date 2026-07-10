"""Tests for Phase B — Trust-level threshold reweighting in OptimizationTierRouter.

Tests that route_recommendation() accepts optional class_readiness and
reweights confidence thresholds based on the class's trust level.

Backward compatibility: all existing tests pass with class_readiness=None.
"""

import pytest
from app.services.optimization_tier_router import (
    OptimizationTierRouter,
    RoutingTier,
)


@pytest.fixture
def router():
    """Fresh OptimizationTierRouter for each test."""
    return OptimizationTierRouter()


# ------------------------------------------------------------------
# _thresholds_for_trust_level
# ------------------------------------------------------------------


class TestThresholdsForTrustLevel:
    """_thresholds_for_trust_level returns correct tuples."""

    def test_level_1(self, router):
        assert router._thresholds_for_trust_level(1) == (0.30, 0.60, 1.00)

    def test_level_2(self, router):
        assert router._thresholds_for_trust_level(2) == (0.30, 0.60, 0.60)

    def test_level_3(self, router):
        assert router._thresholds_for_trust_level(3) == (0.30, 0.60, 0.75)

    def test_unknown_level_fallback(self, router):
        """Unknown level falls back to Level 1 (advisory)."""
        assert router._thresholds_for_trust_level(99) == (0.30, 0.60, 1.00)

    def test_zero_level_fallback(self, router):
        assert router._thresholds_for_trust_level(0) == (0.30, 0.60, 1.00)


# ------------------------------------------------------------------
# _effective_class_level
# ------------------------------------------------------------------


class TestEffectiveClassLevel:
    """_effective_class_level extracts trust level from class_readiness."""

    def test_none_returns_level_1(self, router):
        assert router._effective_class_level(None) == 1

    def test_empty_dict_returns_level_1(self, router):
        assert router._effective_class_level({}) == 1

    def test_with_trust_level(self, router):
        assert router._effective_class_level({"current_trust_level": 2}) == 2

    def test_with_trust_level_3(self, router):
        assert router._effective_class_level({"current_trust_level": 3}) == 3


# ------------------------------------------------------------------
# Backward compatibility — class_readiness=None
# ------------------------------------------------------------------


class TestBackwardCompatibility:
    """All existing behavior preserved when class_readiness is not passed."""

    def test_backward_compatible_no_arg(self, router):
        """route_recommendation() without class_readiness uses default thresholds."""
        decision = router.route_recommendation(
            confidence=0.65,
            system="AHU",
            point_name="supply_temp",
            site_id="site-002",
            control_tier="supervised",
        )
        assert decision.tier == RoutingTier.TIER2_APPROVAL
        assert "class_level" not in decision.reason

    def test_backward_compatible_none(self, router):
        """route_recommendation() with class_readiness=None uses default thresholds."""
        decision = router.route_recommendation(
            confidence=0.65,
            system="AHU",
            point_name="supply_temp",
            site_id="site-002",
            control_tier="supervised",
            class_readiness=None,
        )
        assert decision.tier == RoutingTier.TIER2_APPROVAL

    def test_backward_compatible_low_confidence(self, router):
        """Low confidence 0.20 stays BLOCKED regardless of class_readiness."""
        decision = router.route_recommendation(
            confidence=0.20,
            system="AHU",
            point_name="supply_temp",
            site_id="site-002",
            control_tier="supervised",
        )
        assert decision.tier == RoutingTier.BLOCKED

    def test_backward_compatible_advisory(self, router):
        """0.45 confidence routes to TIER1_ADVISORY."""
        decision = router.route_recommendation(
            confidence=0.45,
            system="CHILLER",
            point_name="chw_supply_temp",
            site_id="site-002",
            control_tier="supervised",
        )
        assert decision.tier == RoutingTier.TIER1_ADVISORY

    def test_backward_compatible_tier3_default_threshold(self, router):
        """0.85 confidence routes to TIER3_AUTO_EXECUTE with default thresholds."""
        decision = router.route_recommendation(
            confidence=0.85,
            system="CHILLER",
            point_name="chw_supply_temp",
            site_id="site-002",
            control_tier="auto_execute",
        )
        assert decision.tier == RoutingTier.TIER3_AUTO_EXECUTE


# ------------------------------------------------------------------
# Level 1 — Advisory (default, no auto-execute)
# ------------------------------------------------------------------


class TestLevel1Advisory:
    """Level 1 class: tier3 unreachable (1.00), all >=0.60 goes to approval."""

    def test_level_1_high_confidence_no_auto_execute(self, router):
        """0.90 confidence with level 1 class → tier2_approval, not auto_execute."""
        decision = router.route_recommendation(
            confidence=0.90,
            system="AHU",
            point_name="supply_temp",
            site_id="site-002",
            control_tier="auto_execute",
            class_readiness={"current_trust_level": 1},
        )
        assert decision.tier == RoutingTier.TIER2_APPROVAL

    def test_level_1_advisory_band(self, router):
        """0.45 confidence with level 1 class → tier1_advisory."""
        decision = router.route_recommendation(
            confidence=0.45,
            system="AHU",
            point_name="supply_temp",
            site_id="site-002",
            control_tier="supervised",
            class_readiness={"current_trust_level": 1},
        )
        assert decision.tier == RoutingTier.TIER1_ADVISORY

    def test_level_1_approval_band(self, router):
        """0.75 confidence with level 1 class → tier2_approval."""
        decision = router.route_recommendation(
            confidence=0.75,
            system="AHU",
            point_name="supply_temp",
            site_id="site-002",
            control_tier="supervised",
            class_readiness={"current_trust_level": 1},
        )
        assert decision.tier == RoutingTier.TIER2_APPROVAL


# ------------------------------------------------------------------
# Level 2 — Supervised proven class (tier3 reachable at 0.60)
# ------------------------------------------------------------------


class TestLevel2Supervised:
    """Level 2 class: tier3 = tier2_min, proven classes can auto-execute."""

    def test_level_2_auto_execute_at_0_65(self, router):
        """0.65 confidence with level 2 class → tier3_auto_execute."""
        decision = router.route_recommendation(
            confidence=0.65,
            system="AHU",
            point_name="supply_temp",
            site_id="site-002",
            control_tier="auto_execute",
            class_readiness={"current_trust_level": 2},
        )
        assert decision.tier == RoutingTier.TIER3_AUTO_EXECUTE

    def test_level_2_approval_at_0_50(self, router):
        """0.50 confidence with level 2 class → tier1_advisory (below tier2_min)."""
        decision = router.route_recommendation(
            confidence=0.50,
            system="AHU",
            point_name="supply_temp",
            site_id="site-002",
            control_tier="supervised",
            class_readiness={"current_trust_level": 2},
        )
        assert decision.tier == RoutingTier.TIER1_ADVISORY

    def test_level_2_reason_includes_class_level(self, router):
        """Routing reason includes class_level=2."""
        decision = router.route_recommendation(
            confidence=0.65,
            system="AHU",
            point_name="supply_temp",
            site_id="site-002",
            control_tier="auto_execute",
            class_readiness={"current_trust_level": 2},
        )
        assert "class_level=2" in decision.reason


# ------------------------------------------------------------------
# Level 3 — Autonomous (tier3 at 0.75)
# ------------------------------------------------------------------


class TestLevel3Autonomous:
    """Level 3 class: tier3 requires 0.75, 0.60-0.75 goes to approval."""

    def test_level_3_confidence_0_70_needs_approval(self, router):
        """0.70 confidence with level 3 class → tier2_approval (below 0.75)."""
        decision = router.route_recommendation(
            confidence=0.70,
            system="AHU",
            point_name="supply_temp",
            site_id="site-002",
            control_tier="autonomous",
            class_readiness={"current_trust_level": 3},
        )
        assert decision.tier == RoutingTier.TIER2_APPROVAL

    def test_level_3_confidence_0_80_auto_execute(self, router):
        """0.80 confidence with level 3 class → tier3_auto_execute."""
        decision = router.route_recommendation(
            confidence=0.80,
            system="AHU",
            point_name="supply_temp",
            site_id="site-002",
            control_tier="autonomous",
            class_readiness={"current_trust_level": 3},
        )
        assert decision.tier == RoutingTier.TIER3_AUTO_EXECUTE

    def test_level_3_reason_includes_class_level(self, router):
        """Routing reason includes class_level=3."""
        decision = router.route_recommendation(
            confidence=0.80,
            system="AHU",
            point_name="supply_temp",
            site_id="site-002",
            control_tier="autonomous",
            class_readiness={"current_trust_level": 3},
        )
        assert "class_level=3" in decision.reason


# ------------------------------------------------------------------
# FCU cap is unchanged by trust level
# ------------------------------------------------------------------


class TestFCUCapWithTrustLevels:
    """FCU confidence cap (0.45) applies BEFORE trust-level logic."""

    def test_fcu_cap_at_level_2(self, router):
        """FCU 0.80 with level 2 → capped to 0.45 → tier1_advisory."""
        decision = router.route_recommendation(
            confidence=0.80,
            system="FCU",
            point_name="valve_position",
            site_id="site-002",
            control_tier="auto_execute",
            class_readiness={"current_trust_level": 2},
        )
        # 0.45 < 0.60, so tier1_advisory regardless of class level
        assert decision.tier == RoutingTier.TIER1_ADVISORY

    def test_fcu_cap_at_level_3(self, router):
        """FCU 0.90 with level 3 → capped to 0.45 → tier1_advisory."""
        decision = router.route_recommendation(
            confidence=0.90,
            system="FCU",
            point_name="valve_position",
            site_id="site-002",
            control_tier="autonomous",
            class_readiness={"current_trust_level": 3},
        )
        assert decision.tier == RoutingTier.TIER1_ADVISORY

    def test_fcu_cap_level_2_below_tier2(self, router):
        """FCU 0.35 with level 2 → tier1_advisory (same as default)."""
        decision = router.route_recommendation(
            confidence=0.35,
            system="FCU",
            point_name="valve_position",
            site_id="site-002",
            control_tier="supervised",
            class_readiness={"current_trust_level": 2},
        )
        assert decision.tier == RoutingTier.TIER1_ADVISORY

    def test_fcu_cap_reason_includes_cap(self, router):
        """FCU cap reason mentions confidence capping even at level 2."""
        decision = router.route_recommendation(
            confidence=0.80,
            system="FCU",
            point_name="valve_position",
            site_id="site-002",
            control_tier="auto_execute",
            class_readiness={"current_trust_level": 2},
        )
        assert "FCU cap" in decision.reason


# ------------------------------------------------------------------
# Control tier matrix interaction
# ------------------------------------------------------------------


class TestControlTierMatrixWithClassReadiness:
    """Control tier matrix still determines action from tier + control_tier."""

    def test_monitor_logs_all_class_levels(self, router):
        """control_tier=monitor → all tiers become log_only."""
        for level, conf, t3_min in [(1, 0.90, 0.60), (2, 0.90, 1.00), (3, 0.90, 0.75)]:
            class_readiness = {"current_trust_level": level}
            decision = router.route_recommendation(
                confidence=conf,
                system="AHU",
                point_name="supply_temp",
                site_id="site-002",
                control_tier="monitor",
                class_readiness=class_readiness,
            )
            assert decision.action == "log_only"

    def test_supervised_action_for_level_2_tier3(self, router):
        """Level 2, supervised control_tier, tier3 route → still pending_approval from matrix."""
        decision = router.route_recommendation(
            confidence=0.65,
            system="AHU",
            point_name="supply_temp",
            site_id="site-002",
            control_tier="supervised",  # supervised matrix maps tier3 → pending_approval
            class_readiness={"current_trust_level": 2},
        )
        assert decision.tier == RoutingTier.TIER3_AUTO_EXECUTE
        assert decision.action == "pending_approval"  # matrix says so

    def test_auto_execute_action_for_level_2_tier3(self, router):
        """Level 2, auto_execute control_tier, tier3 route → auto_execute."""
        decision = router.route_recommendation(
            confidence=0.65,
            system="AHU",
            point_name="supply_temp",
            site_id="site-002",
            control_tier="auto_execute",
            class_readiness={"current_trust_level": 2},
        )
        assert decision.tier == RoutingTier.TIER3_AUTO_EXECUTE
        assert decision.action == "auto_execute"


# ------------------------------------------------------------------
# Batch routing — route_recommendations passes class_readiness per-rec
# ------------------------------------------------------------------


class TestBatchRouting:
    """route_recommendations passes class_readiness per dict item."""

    def test_batch_with_mixed_levels(self, router):
        """Different class levels in batch produce different tiers."""
        recs = [
            {"confidence": 0.70, "system": "AHU", "point_name": "s1", "class_readiness": {"current_trust_level": 1}},
            {"confidence": 0.70, "system": "AHU", "point_name": "s2", "class_readiness": {"current_trust_level": 2}},
            {"confidence": 0.80, "system": "AHU", "point_name": "s3", "class_readiness": {"current_trust_level": 3}},
        ]
        decisions = router.route_recommendations(recs, "site-002", "auto_execute")

        assert len(decisions) == 3
        assert decisions[0].tier == RoutingTier.TIER2_APPROVAL  # level 1, 0.70 → tier2
        assert decisions[1].tier == RoutingTier.TIER3_AUTO_EXECUTE  # level 2, 0.70 → tier3
        assert decisions[2].tier == RoutingTier.TIER3_AUTO_EXECUTE  # level 3, 0.80 → tier3

    def test_batch_without_class_readiness(self, router):
        """Batch without class_readiness uses instance defaults (backward compatible)."""
        recs = [
            {"confidence": 0.70, "system": "AHU", "point_name": "s1"},
            {"confidence": 0.90, "system": "AHU", "point_name": "s2"},
        ]
        decisions = router.route_recommendations(recs, "site-002", "supervised")

        assert len(decisions) == 2
        assert decisions[0].tier == RoutingTier.TIER2_APPROVAL  # 0.70 → tier2 (instance default 0.60-0.85)
        assert decisions[1].tier == RoutingTier.TIER3_AUTO_EXECUTE  # 0.90 → tier3 (instance default >=0.85)
