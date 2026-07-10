"""Unit tests for OptimizationTierRouter.

Tests cover:
    - Threshold boundary routing (7 tests)
    - FCU confidence cap (4 tests)
    - Control tier execution matrix (9 tests)
    - resolve_control_tier fallback logic (4 tests)
    - Routing summary aggregation (1 test)
    - Batch routing (1 test)
    - Settings integration (1 test)
    - Singleton accessor (1 test)

Total: 28 tests
"""

import pytest

from app.services.optimization_tier_router import (
    OptimizationTierRouter,
    RoutingTier,
    get_tier_router,
)

# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


@pytest.fixture
def router():
    """Create a fresh router with default thresholds."""
    return OptimizationTierRouter()


@pytest.fixture
def auto_execute_tier():
    return "auto_execute"


@pytest.fixture
def human_in_loop_tier():
    return "human_in_loop"


@pytest.fixture
def monitor_tier():
    return "monitor"


# ------------------------------------------------------------------
# 1. Threshold boundary tests
# ------------------------------------------------------------------


class TestThresholdBoundaries:
    """Test that confidence values map to the correct routing tier."""

    def test_confidence_029_is_blocked(self, router, auto_execute_tier):
        d = router.route_recommendation(0.29, "HVAC", "AHU-SP", "S002", auto_execute_tier)
        assert d.tier == RoutingTier.BLOCKED

    def test_confidence_030_is_tier1(self, router, auto_execute_tier):
        d = router.route_recommendation(0.30, "HVAC", "AHU-SP", "S002", auto_execute_tier)
        assert d.tier == RoutingTier.TIER1_ADVISORY

    def test_confidence_059_is_tier1(self, router, auto_execute_tier):
        d = router.route_recommendation(0.59, "HVAC", "AHU-SP", "S002", auto_execute_tier)
        assert d.tier == RoutingTier.TIER1_ADVISORY

    def test_confidence_060_is_tier2(self, router, auto_execute_tier):
        d = router.route_recommendation(0.60, "HVAC", "AHU-SP", "S002", auto_execute_tier)
        assert d.tier == RoutingTier.TIER2_APPROVAL

    def test_confidence_084_is_tier2(self, router, auto_execute_tier):
        d = router.route_recommendation(0.84, "HVAC", "AHU-SP", "S002", auto_execute_tier)
        assert d.tier == RoutingTier.TIER2_APPROVAL

    def test_confidence_085_is_tier3(self, router, auto_execute_tier):
        d = router.route_recommendation(0.85, "HVAC", "AHU-SP", "S002", auto_execute_tier)
        assert d.tier == RoutingTier.TIER3_AUTO_EXECUTE

    def test_confidence_100_is_tier3(self, router, auto_execute_tier):
        d = router.route_recommendation(1.0, "HVAC", "AHU-SP", "S002", auto_execute_tier)
        assert d.tier == RoutingTier.TIER3_AUTO_EXECUTE


# ------------------------------------------------------------------
# 2. FCU cap tests
# ------------------------------------------------------------------


class TestFCUCap:
    """Test that FCU system actions have confidence capped at 0.45."""

    def test_fcu_090_capped_to_advisory(self, router, auto_execute_tier):
        d = router.route_recommendation(0.90, "FCU", "FCU-SP", "S002", auto_execute_tier)
        assert d.effective_confidence == 0.45
        assert d.original_confidence == 0.90
        assert d.tier == RoutingTier.TIER1_ADVISORY

    def test_fcu_045_stays_advisory(self, router, auto_execute_tier):
        d = router.route_recommendation(0.45, "FCU", "FCU-SP", "S002", auto_execute_tier)
        assert d.effective_confidence == 0.45
        assert d.tier == RoutingTier.TIER1_ADVISORY

    def test_fcu_020_is_blocked(self, router, auto_execute_tier):
        d = router.route_recommendation(0.20, "FCU", "FCU-SP", "S002", auto_execute_tier)
        assert d.effective_confidence == 0.20
        assert d.tier == RoutingTier.BLOCKED

    def test_non_fcu_090_is_tier3(self, router, auto_execute_tier):
        d = router.route_recommendation(0.90, "HVAC", "AHU-SP", "S002", auto_execute_tier)
        assert d.effective_confidence == 0.90
        assert d.tier == RoutingTier.TIER3_AUTO_EXECUTE


# ------------------------------------------------------------------
# 3. Control tier execution matrix
# ------------------------------------------------------------------


class TestControlTierMatrix:
    """Test the control tier execution matrix determines the correct action."""

    def test_monitor_tier3_logs_only(self, router, monitor_tier):
        d = router.route_recommendation(0.90, "HVAC", "AHU-SP", "S002", monitor_tier)
        assert d.action == "log_only"

    def test_monitor_tier2_logs_only(self, router, monitor_tier):
        d = router.route_recommendation(0.70, "HVAC", "AHU-SP", "S002", monitor_tier)
        assert d.action == "log_only"

    def test_human_in_loop_tier3_pending_approval(self, router, human_in_loop_tier):
        d = router.route_recommendation(0.90, "HVAC", "AHU-SP", "S002", human_in_loop_tier)
        assert d.action == "pending_approval"

    def test_human_in_loop_tier2_pending_approval(self, router, human_in_loop_tier):
        d = router.route_recommendation(0.70, "HVAC", "AHU-SP", "S002", human_in_loop_tier)
        assert d.action == "pending_approval"

    def test_human_in_loop_tier1_advisory(self, router, human_in_loop_tier):
        d = router.route_recommendation(0.40, "HVAC", "AHU-SP", "S002", human_in_loop_tier)
        assert d.action == "advisory"

    def test_auto_execute_tier3_auto_execute(self, router, auto_execute_tier):
        d = router.route_recommendation(0.90, "HVAC", "AHU-SP", "S002", auto_execute_tier)
        assert d.action == "auto_execute"

    def test_auto_execute_tier2_pending_approval(self, router, auto_execute_tier):
        d = router.route_recommendation(0.70, "HVAC", "AHU-SP", "S002", auto_execute_tier)
        assert d.action == "pending_approval"

    def test_auto_execute_tier1_advisory(self, router, auto_execute_tier):
        d = router.route_recommendation(0.40, "HVAC", "AHU-SP", "S002", auto_execute_tier)
        assert d.action == "advisory"

    def test_any_control_tier_blocked_is_blocked(self, router):
        for ct in ["monitor", "human_in_loop", "auto_execute"]:
            d = router.route_recommendation(0.10, "HVAC", "AHU-SP", "S002", ct)
            assert d.action == "blocked", f"Expected blocked for control_tier={ct}"


# ------------------------------------------------------------------
# 4. resolve_control_tier tests
# ------------------------------------------------------------------


class TestResolveControlTier:
    """Test control tier resolution from site profile and optimization settings."""

    def test_site_profile_auto_execute(self):
        result = OptimizationTierRouter.resolve_control_tier({"control_tier": "auto_execute"})
        assert result == "auto_execute"

    def test_fallback_supervised(self):
        from app.models.optimization import OptimizationSettings

        settings = OptimizationSettings(mode="supervised")
        result = OptimizationTierRouter.resolve_control_tier(None, settings)
        assert result == "supervised"

    def test_fallback_automatic_to_auto_execute(self):
        from app.models.optimization import OptimizationSettings

        settings = OptimizationSettings(mode="automatic")
        result = OptimizationTierRouter.resolve_control_tier(None, settings)
        assert result == "auto_execute"

    def test_default_supervised(self):
        result = OptimizationTierRouter.resolve_control_tier(None)
        assert result == "supervised"


# ------------------------------------------------------------------
# 5. Routing summary tests
# ------------------------------------------------------------------


class TestRoutingSummary:
    """Test routing summary aggregation."""

    def test_mixed_recommendations_correct_counts(self, router, auto_execute_tier):
        decisions = [
            router.route_recommendation(0.10, "HVAC", "P1", "S002", auto_execute_tier),  # blocked
            router.route_recommendation(0.40, "HVAC", "P2", "S002", auto_execute_tier),  # advisory
            router.route_recommendation(0.70, "HVAC", "P3", "S002", auto_execute_tier),  # pending_approval
            router.route_recommendation(0.90, "HVAC", "P4", "S002", auto_execute_tier),  # auto_execute
            router.route_recommendation(0.90, "FCU", "P5", "S002", auto_execute_tier),  # advisory (FCU cap)
        ]

        summary = router.get_routing_summary(decisions, auto_execute_tier)

        assert summary.blocked == 1
        assert summary.advisory == 2  # tier1 advisory + FCU capped
        assert summary.pending_approval == 1
        assert summary.auto_executed == 1
        assert summary.control_tier == auto_execute_tier
        assert summary.thresholds_used["block_min"] == 0.30
        assert summary.thresholds_used["tier3_min"] == 0.85


# ------------------------------------------------------------------
# 6. Batch routing tests
# ------------------------------------------------------------------


class TestBatchRouting:
    """Test batch routing of multiple recommendations."""

    def test_route_recommendations_batch(self, router, auto_execute_tier):
        recs = [
            {"confidence": 0.90, "system": "HVAC", "point_name": "AHU-SP"},
            {"confidence": 0.50, "system": "DALI", "point_name": "LIGHT-SP"},
            {"confidence": 0.10, "system": "FCU", "point_name": "FCU-SP"},
        ]
        decisions = router.route_recommendations(recs, "S002", auto_execute_tier)

        assert len(decisions) == 3
        assert decisions[0].tier == RoutingTier.TIER3_AUTO_EXECUTE
        assert decisions[1].tier == RoutingTier.TIER1_ADVISORY
        assert decisions[2].tier == RoutingTier.BLOCKED


# ------------------------------------------------------------------
# 7. Settings integration tests
# ------------------------------------------------------------------


class TestSettingsIntegration:
    """Test that router correctly reads from settings."""

    def test_custom_thresholds_from_settings(self):
        class MockSettings:
            optimization_tier_block_min = 0.20
            optimization_tier2_min = 0.50
            optimization_tier3_min = 0.80
            optimization_fcu_confidence_cap = 0.40

        router = OptimizationTierRouter(settings=MockSettings())

        # 0.19 should be blocked with custom threshold
        d = router.route_recommendation(0.19, "HVAC", "AHU-SP", "S002", "auto_execute")
        assert d.tier == RoutingTier.BLOCKED

        # 0.20 should be tier1 with custom threshold
        d = router.route_recommendation(0.20, "HVAC", "AHU-SP", "S002", "auto_execute")
        assert d.tier == RoutingTier.TIER1_ADVISORY

        # 0.50 should be tier2 with custom threshold
        d = router.route_recommendation(0.50, "HVAC", "AHU-SP", "S002", "auto_execute")
        assert d.tier == RoutingTier.TIER2_APPROVAL

        # 0.80 should be tier3 with custom threshold
        d = router.route_recommendation(0.80, "HVAC", "AHU-SP", "S002", "auto_execute")
        assert d.tier == RoutingTier.TIER3_AUTO_EXECUTE


# ------------------------------------------------------------------
# 8. Singleton accessor tests
# ------------------------------------------------------------------


class TestSingleton:
    """Test the module-level singleton accessor."""

    def test_get_tier_router_returns_instance(self):
        import app.services.optimization_tier_router as mod

        mod._router_instance = None  # Reset
        router = get_tier_router()
        assert isinstance(router, OptimizationTierRouter)

    def test_get_tier_router_returns_same_instance(self):
        import app.services.optimization_tier_router as mod

        mod._router_instance = None  # Reset
        r1 = get_tier_router()
        r2 = get_tier_router()
        assert r1 is r2
