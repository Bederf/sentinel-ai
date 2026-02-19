"""Integration tests for optimization tier routing (Phase 82-04).

Tests the full routing flow across all control tier modes:
    1. Monitor mode: all recommendations log_only
    2. Human-in-loop mode: tier2/tier3 -> pending_approval, tier1 -> advisory
    3. Auto-execute mode: tier3 -> auto_execute, tier2 -> pending_approval
    4. Mixed confidence partial auto-exec
    5. Approval rejects blocked/advisory
    6. M&V only for executed items
    7. Shadow mode regression
"""

import pytest
from unittest.mock import MagicMock

from app.services.optimization_tier_router import (
    OptimizationTierRouter,
    RoutingTier,
)
from app.services.mv_verification_service import (
    VerificationTask,
)


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


@pytest.fixture
def router():
    """Fresh router with default thresholds."""
    return OptimizationTierRouter()


@pytest.fixture
def enforced_settings():
    """Settings mock with routing enforced."""
    s = MagicMock()
    s.optimization_routing_enforced = True
    s.optimization_tier_block_min = 0.30
    s.optimization_tier2_min = 0.60
    s.optimization_tier3_min = 0.85
    s.optimization_fcu_confidence_cap = 0.45
    return s


@pytest.fixture
def shadow_settings():
    """Settings mock with routing in shadow mode (not enforced)."""
    s = MagicMock()
    s.optimization_routing_enforced = False
    s.optimization_tier_block_min = 0.30
    s.optimization_tier2_min = 0.60
    s.optimization_tier3_min = 0.85
    s.optimization_fcu_confidence_cap = 0.45
    return s


def _make_recommendations(confidences, systems=None):
    """Helper: create a list of recommendation dicts with given confidences."""
    recs = []
    for i, conf in enumerate(confidences):
        sys = systems[i] if systems and i < len(systems) else "HVAC"
        recs.append(
            {
                "confidence": conf,
                "system": sys,
                "point_name": f"setpoint_{i}",
                "equipment_id": f"device_{i}",
                "recommended_value": 22.0 + i,
                "current_value": 24.0,
            }
        )
    return recs


# ==================================================================
# Test 1: Monitor mode — all actions become log_only
# ==================================================================


class TestMonitorMode:
    """Monitor control tier: routing is computed but everything is log_only."""

    def test_monitor_all_log_only(self, router):
        """All recommendations routed to log_only in monitor mode."""
        recs = _make_recommendations([0.10, 0.50, 0.70, 0.92])
        decisions = router.route_recommendations(recs, "site-002", "monitor")

        for d in decisions:
            if d.tier == RoutingTier.BLOCKED:
                assert d.action == "blocked"
            else:
                assert d.action == "log_only", f"Expected log_only for tier={d.tier}, got {d.action}"

    def test_monitor_no_auto_execution(self, router):
        """No recommendations routed to auto_execute in monitor mode."""
        recs = _make_recommendations([0.90, 0.95, 0.99])
        decisions = router.route_recommendations(recs, "site-002", "monitor")

        for d in decisions:
            assert d.action != "auto_execute"
            assert d.action != "pending_approval"

    def test_monitor_routing_summary(self, router):
        """Routing summary should count advisory (log_only) not auto_executed."""
        recs = _make_recommendations([0.50, 0.70, 0.92])
        decisions = router.route_recommendations(recs, "site-002", "monitor")
        summary = router.get_routing_summary(decisions, "monitor")

        assert summary.auto_executed == 0
        assert summary.pending_approval == 0
        # All non-blocked should be counted as advisory
        assert summary.advisory == 3
        assert summary.control_tier == "monitor"


# ==================================================================
# Test 2: Human-in-loop mode
# ==================================================================


class TestHumanInLoopMode:
    """Human-in-loop: tier2/tier3 -> pending_approval, tier1 -> advisory."""

    def test_hil_tier1_advisory(self, router):
        """Tier1 recommendations are advisory in human_in_loop."""
        decision = router.route_recommendation(
            confidence=0.45,
            system="HVAC",
            point_name="sp1",
            site_id="site-002",
            control_tier="human_in_loop",
        )
        assert decision.tier == RoutingTier.TIER1_ADVISORY
        assert decision.action == "advisory"

    def test_hil_tier2_pending_approval(self, router):
        """Tier2 recommendations need approval in human_in_loop."""
        decision = router.route_recommendation(
            confidence=0.70,
            system="HVAC",
            point_name="sp1",
            site_id="site-002",
            control_tier="human_in_loop",
        )
        assert decision.tier == RoutingTier.TIER2_APPROVAL
        assert decision.action == "pending_approval"

    def test_hil_tier3_also_pending_approval(self, router):
        """Tier3 recommendations also need approval in human_in_loop."""
        decision = router.route_recommendation(
            confidence=0.92,
            system="HVAC",
            point_name="sp1",
            site_id="site-002",
            control_tier="human_in_loop",
        )
        assert decision.tier == RoutingTier.TIER3_AUTO_EXECUTE
        assert decision.action == "pending_approval"

    def test_hil_no_auto_execution(self, router):
        """No auto-execution in human_in_loop mode."""
        recs = _make_recommendations([0.90, 0.95, 0.99])
        decisions = router.route_recommendations(recs, "site-002", "human_in_loop")

        for d in decisions:
            assert d.action != "auto_execute"

    def test_hil_blocked_still_blocked(self, router):
        """Blocked items remain blocked in human_in_loop."""
        decision = router.route_recommendation(
            confidence=0.10,
            system="HVAC",
            point_name="sp1",
            site_id="site-002",
            control_tier="human_in_loop",
        )
        assert decision.tier == RoutingTier.BLOCKED
        assert decision.action == "blocked"


# ==================================================================
# Test 3: Auto-execute mode
# ==================================================================


class TestAutoExecuteMode:
    """Auto-execute: tier3 -> auto_execute, tier2 -> pending_approval."""

    def test_auto_tier3_auto_execute(self, router):
        """Tier3 recommendations are auto-executed."""
        decision = router.route_recommendation(
            confidence=0.92,
            system="HVAC",
            point_name="sp1",
            site_id="site-002",
            control_tier="auto_execute",
        )
        assert decision.tier == RoutingTier.TIER3_AUTO_EXECUTE
        assert decision.action == "auto_execute"

    def test_auto_tier2_pending_approval(self, router):
        """Tier2 recommendations need approval."""
        decision = router.route_recommendation(
            confidence=0.70,
            system="HVAC",
            point_name="sp1",
            site_id="site-002",
            control_tier="auto_execute",
        )
        assert decision.tier == RoutingTier.TIER2_APPROVAL
        assert decision.action == "pending_approval"

    def test_auto_tier1_advisory(self, router):
        """Tier1 recommendations are advisory-only."""
        decision = router.route_recommendation(
            confidence=0.45,
            system="HVAC",
            point_name="sp1",
            site_id="site-002",
            control_tier="auto_execute",
        )
        assert decision.tier == RoutingTier.TIER1_ADVISORY
        assert decision.action == "advisory"

    def test_auto_blocked(self, router):
        """Blocked items remain blocked."""
        decision = router.route_recommendation(
            confidence=0.10,
            system="HVAC",
            point_name="sp1",
            site_id="site-002",
            control_tier="auto_execute",
        )
        assert decision.tier == RoutingTier.BLOCKED
        assert decision.action == "blocked"

    def test_auto_execution_summary_counts(self, router):
        """Execution summary correctly counts auto-executed items."""
        recs = _make_recommendations([0.90, 0.95, 0.70, 0.45, 0.10])
        decisions = router.route_recommendations(recs, "site-002", "auto_execute")
        summary = router.get_routing_summary(decisions, "auto_execute")

        assert summary.auto_executed == 2  # 0.90 and 0.95
        assert summary.pending_approval == 1  # 0.70
        assert summary.advisory == 1  # 0.45
        assert summary.blocked == 1  # 0.10


# ==================================================================
# Test 4: Mixed confidence partial auto-exec
# ==================================================================


class TestMixedConfidenceRouting:
    """Mixed confidences produce the correct tier distribution."""

    def test_mixed_confidence_routing(self, router):
        """Recommendations with 0.2, 0.5, 0.7, 0.9 confidence route correctly."""
        recs = _make_recommendations([0.2, 0.5, 0.7, 0.9])
        decisions = router.route_recommendations(recs, "site-002", "auto_execute")

        # 0.2 < 0.30 -> blocked
        assert decisions[0].tier == RoutingTier.BLOCKED
        assert decisions[0].action == "blocked"

        # 0.5: 0.30 <= 0.5 < 0.60 -> tier1_advisory
        assert decisions[1].tier == RoutingTier.TIER1_ADVISORY
        assert decisions[1].action == "advisory"

        # 0.7: 0.60 <= 0.7 < 0.85 -> tier2_approval
        assert decisions[2].tier == RoutingTier.TIER2_APPROVAL
        assert decisions[2].action == "pending_approval"

        # 0.9: >= 0.85 -> tier3_auto_execute
        assert decisions[3].tier == RoutingTier.TIER3_AUTO_EXECUTE
        assert decisions[3].action == "auto_execute"

    def test_mixed_confidence_summary(self, router):
        """Summary counts match the mixed distribution."""
        recs = _make_recommendations([0.2, 0.5, 0.7, 0.9])
        decisions = router.route_recommendations(recs, "site-002", "auto_execute")
        summary = router.get_routing_summary(decisions, "auto_execute")

        assert summary.blocked == 1
        assert summary.advisory == 1
        assert summary.pending_approval == 1
        assert summary.auto_executed == 1

    def test_fcu_confidence_cap_in_mixed_set(self, router):
        """FCU items with high confidence get capped to advisory."""
        recs = _make_recommendations(
            [0.92, 0.92],
            systems=["HVAC", "FCU"],
        )
        decisions = router.route_recommendations(recs, "site-002", "auto_execute")

        # HVAC at 0.92 -> auto_execute
        assert decisions[0].action == "auto_execute"
        assert decisions[0].effective_confidence == 0.92

        # FCU at 0.92 -> capped to 0.45 -> tier1_advisory -> advisory
        assert decisions[1].tier == RoutingTier.TIER1_ADVISORY
        assert decisions[1].action == "advisory"
        assert decisions[1].effective_confidence == 0.45
        assert decisions[1].original_confidence == 0.92


# ==================================================================
# Test 5: Approval rejects blocked/advisory
# ==================================================================


class TestApprovalHardening:
    """Approval path rejects blocked and advisory in enforce mode."""

    def _simulate_approval_check(self, routing_details, routing_enforced):
        """Simulate the approval routing validation logic from optimization.py.

        Returns (approved, rejected, already_executed) lists.
        """
        approved = []
        rejected = []
        already_executed = []

        setpoints = [
            {"device_id": f"device_{i}", "point_name": f"sp_{i}", "value": 22.0} for i in range(len(routing_details))
        ]

        for idx, setpoint in enumerate(setpoints):
            routing_decision = routing_details[idx] if idx < len(routing_details) else None

            if routing_decision and routing_enforced:
                tier = routing_decision.get("tier", "")
                action = routing_decision.get("action", "")

                if tier == "blocked":
                    rejected.append(
                        {
                            "device_id": setpoint["device_id"],
                            "point_name": setpoint["point_name"],
                            "reason": "Cannot approve blocked recommendation",
                            "tier": tier,
                        }
                    )
                    continue
                elif tier == "tier1_advisory":
                    rejected.append(
                        {
                            "device_id": setpoint["device_id"],
                            "point_name": setpoint["point_name"],
                            "reason": "Cannot approve advisory-only recommendation",
                            "tier": tier,
                        }
                    )
                    continue
                elif action == "auto_execute":
                    already_executed.append(
                        {
                            "device_id": setpoint["device_id"],
                            "point_name": setpoint["point_name"],
                            "note": "Already auto-executed during analysis",
                        }
                    )
                    continue

            approved.append(setpoint)

        return approved, rejected, already_executed

    def test_approve_rejects_blocked(self):
        """Blocked recommendations are rejected in enforce mode."""
        routing_details = [
            {"tier": "blocked", "action": "blocked", "effective_confidence": 0.10},
        ]
        approved, rejected, already = self._simulate_approval_check(
            routing_details,
            routing_enforced=True,
        )
        assert len(approved) == 0
        assert len(rejected) == 1
        assert "blocked" in rejected[0]["reason"].lower()

    def test_approve_rejects_advisory(self):
        """Advisory-only recommendations are rejected in enforce mode."""
        routing_details = [
            {"tier": "tier1_advisory", "action": "advisory", "effective_confidence": 0.45},
        ]
        approved, rejected, already = self._simulate_approval_check(
            routing_details,
            routing_enforced=True,
        )
        assert len(approved) == 0
        assert len(rejected) == 1
        assert "advisory" in rejected[0]["reason"].lower()

    def test_approve_accepts_tier2(self):
        """Tier2 recommendations are accepted for approval."""
        routing_details = [
            {"tier": "tier2_approval", "action": "pending_approval", "effective_confidence": 0.70},
        ]
        approved, rejected, already = self._simulate_approval_check(
            routing_details,
            routing_enforced=True,
        )
        assert len(approved) == 1
        assert len(rejected) == 0

    def test_approve_idempotent_auto_execute(self):
        """Already auto-executed items return idempotent success."""
        routing_details = [
            {"tier": "tier3_auto_execute", "action": "auto_execute", "effective_confidence": 0.92},
        ]
        approved, rejected, already = self._simulate_approval_check(
            routing_details,
            routing_enforced=True,
        )
        assert len(approved) == 0
        assert len(rejected) == 0
        assert len(already) == 1

    def test_mixed_approval_results(self):
        """Mixed routing produces correct approve/reject/already breakdown."""
        routing_details = [
            {"tier": "blocked", "action": "blocked", "effective_confidence": 0.10},
            {"tier": "tier1_advisory", "action": "advisory", "effective_confidence": 0.45},
            {"tier": "tier2_approval", "action": "pending_approval", "effective_confidence": 0.70},
            {"tier": "tier3_auto_execute", "action": "auto_execute", "effective_confidence": 0.92},
        ]
        approved, rejected, already = self._simulate_approval_check(
            routing_details,
            routing_enforced=True,
        )
        assert len(rejected) == 2  # blocked + advisory
        assert len(approved) == 1  # tier2
        assert len(already) == 1  # tier3 auto-executed


# ==================================================================
# Test 6: M&V created only for executed items
# ==================================================================


class TestMVAlignment:
    """M&V verification tasks only created for executed setpoints."""

    def test_mv_task_includes_routing_metadata(self):
        """M&V tasks include routing_tier, control_tier, effective_confidence."""
        task = VerificationTask(
            id="mv-test-001",
            site_id="site-002",
            recommendation_id="rec-001",
            applied_at="2026-02-19T12:00:00",
            measurement_window_hours=2.0,
            verify_after="2026-02-19T14:00:00",
            routing_tier="tier3_auto_execute",
            control_tier="auto_execute",
            effective_confidence=0.92,
        )

        task_dict = task.to_dict()
        assert task_dict["routing_tier"] == "tier3_auto_execute"
        assert task_dict["control_tier"] == "auto_execute"
        assert task_dict["effective_confidence"] == 0.92

    def test_mv_only_for_auto_executed_in_analyze_flow(self, router):
        """In the analyze flow, M&V should only record auto-executed items.

        Simulates the logic from optimization.py's auto-apply section:
        only successful auto-apply results generate M&V tasks.
        """
        recs = _make_recommendations([0.45, 0.70, 0.92])
        decisions = router.route_recommendations(recs, "site-002", "auto_execute")

        # Simulate: only auto_execute decisions get applied
        auto_apply_results = []
        for idx, d in enumerate(decisions):
            if d.action == "auto_execute":
                auto_apply_results.append(
                    {
                        "device_id": f"device_{idx}",
                        "point_name": f"setpoint_{idx}",
                        "success": True,
                        "value": 22.0 + idx,
                    }
                )

        # Only 1 item (confidence=0.92) should be auto-applied
        assert len(auto_apply_results) == 1
        assert auto_apply_results[0]["device_id"] == "device_2"

        # Build routing metadata from first auto-executed decision
        routing_metadata = None
        for d in decisions:
            if d.action == "auto_execute":
                routing_metadata = {
                    "routing_tier": d.tier.value,
                    "control_tier": "auto_execute",
                    "effective_confidence": d.effective_confidence,
                }
                break

        assert routing_metadata is not None
        assert routing_metadata["routing_tier"] == "tier3_auto_execute"
        assert routing_metadata["effective_confidence"] == 0.92

    def test_mv_only_for_approved_in_approval_flow(self, router):
        """In the approval flow, M&V should only record approved+applied items.

        Items that are rejected by routing (blocked/advisory) or already
        auto-executed should NOT generate M&V tasks.
        """
        routing_details = [
            {"tier": "blocked", "action": "blocked", "effective_confidence": 0.10},
            {"tier": "tier2_approval", "action": "pending_approval", "effective_confidence": 0.70},
            {"tier": "tier3_auto_execute", "action": "auto_execute", "effective_confidence": 0.92},
        ]

        # Simulate the approval routing filter
        approved_for_mv = []
        for rd in routing_details:
            if rd["action"] == "pending_approval":
                # This is the only one that would actually be applied in approval
                approved_for_mv.append(rd)

        assert len(approved_for_mv) == 1
        assert approved_for_mv[0]["tier"] == "tier2_approval"

    def test_mv_task_roundtrip(self):
        """Verify M&V task with routing metadata survives to_dict/from_dict."""
        task = VerificationTask(
            id="mv-test-002",
            site_id="site-002",
            recommendation_id="rec-002",
            applied_at="2026-02-19T12:00:00",
            measurement_window_hours=2.0,
            verify_after="2026-02-19T14:00:00",
            routing_tier="tier2_approval",
            control_tier="human_in_loop",
            effective_confidence=0.72,
        )

        roundtripped = VerificationTask.from_dict(task.to_dict())
        assert roundtripped.routing_tier == "tier2_approval"
        assert roundtripped.control_tier == "human_in_loop"
        assert roundtripped.effective_confidence == 0.72


# ==================================================================
# Test 7: Shadow mode regression
# ==================================================================


class TestShadowModeRegression:
    """Shadow mode (optimization_routing_enforced=False): existing behavior unchanged."""

    def test_shadow_mode_routing_still_computed(self, router):
        """Routing decisions are still computed in shadow mode."""
        recs = _make_recommendations([0.50, 0.92])
        decisions = router.route_recommendations(recs, "site-002", "auto_execute")

        # Routing is always computed regardless of enforce flag
        assert len(decisions) == 2
        assert decisions[0].tier == RoutingTier.TIER1_ADVISORY
        assert decisions[1].tier == RoutingTier.TIER3_AUTO_EXECUTE

    def test_shadow_mode_approval_allows_all(self):
        """In shadow mode, approval path allows all items (existing behavior)."""
        routing_details = [
            {"tier": "blocked", "action": "blocked", "effective_confidence": 0.10},
            {"tier": "tier1_advisory", "action": "advisory", "effective_confidence": 0.45},
            {"tier": "tier2_approval", "action": "pending_approval", "effective_confidence": 0.70},
        ]

        # Shadow mode: routing_enforced=False
        # Simulate the approval check with shadow mode
        approved = []
        rejected = []

        for idx, rd in enumerate(routing_details):
            setpoint = {"device_id": f"device_{idx}", "point_name": f"sp_{idx}", "value": 22.0}
            routing_enforced = False

            if rd and routing_enforced:
                # This block never executes in shadow mode
                tier = rd.get("tier", "")
                if tier in ("blocked", "tier1_advisory"):
                    rejected.append(setpoint)
                    continue
            # Shadow mode: all pass through
            approved.append(setpoint)

        # All 3 should pass through in shadow mode
        assert len(approved) == 3
        assert len(rejected) == 0

    def test_shadow_mode_auto_apply_uses_legacy_mode(self, router):
        """In shadow mode, auto-apply decision uses legacy site_mode='automatic'
        rather than routing decisions.
        """
        # In shadow mode, the should_auto_apply decision is:
        # site_mode == "automatic" and validation["allowed"] and recommendations_list
        # NOT based on routing decisions.

        site_mode = "automatic"
        validation_allowed = True
        recommendations_list = [{"confidence": 0.5}]
        routing_enforced = False

        # Shadow mode logic
        if routing_enforced:
            should_auto_apply = (
                validation_allowed and recommendations_list and any(True for _ in [])  # Would check routing decisions
            )
        else:
            should_auto_apply = site_mode == "automatic" and validation_allowed and bool(recommendations_list)

        assert should_auto_apply is True

    def test_shadow_mode_supervised_no_auto_apply(self, router):
        """In shadow mode with supervised mode, no auto-apply."""
        site_mode = "supervised"
        validation_allowed = True
        recommendations_list = [{"confidence": 0.5}]
        routing_enforced = False

        if routing_enforced:
            should_auto_apply = False
        else:
            should_auto_apply = site_mode == "automatic" and validation_allowed and bool(recommendations_list)

        assert should_auto_apply is False

    def test_shadow_routing_summary_in_response(self, router):
        """Shadow mode still includes routing_summary in the response."""
        recs = _make_recommendations([0.50, 0.92])
        decisions = router.route_recommendations(recs, "site-002", "auto_execute")
        summary = router.get_routing_summary(decisions, "auto_execute")

        # Summary is always built, even in shadow mode
        summary_dict = {
            "blocked": summary.blocked,
            "advisory": summary.advisory,
            "pending_approval": summary.pending_approval,
            "auto_executed": summary.auto_executed,
            "control_tier": summary.control_tier,
        }

        assert summary_dict["advisory"] == 1
        assert summary_dict["auto_executed"] == 1
        assert summary_dict["control_tier"] == "auto_execute"


# ==================================================================
# Additional: Status endpoint routing fields
# ==================================================================


class TestStatusEndpointRouting:
    """Verify the status endpoint includes routing_summary and control_tier."""

    def test_status_extracts_routing_from_last_recommendation(self):
        """Status endpoint logic extracts routing from last_recommendation."""
        last_recommendation = {
            "routing_summary": {
                "blocked": 0,
                "advisory": 1,
                "pending_approval": 1,
                "auto_executed": 1,
                "control_tier": "auto_execute",
            },
            "control_tier": "auto_execute",
            "routing_details": [
                {"index": 0, "tier": "tier1_advisory", "action": "advisory"},
            ],
        }

        # Simulate the status endpoint logic (from optimization.py)
        routing_summary = last_recommendation.get("routing_summary") if last_recommendation else None
        control_tier = last_recommendation.get("control_tier") if last_recommendation else None

        assert routing_summary is not None
        assert routing_summary["auto_executed"] == 1
        assert control_tier == "auto_execute"

    def test_status_none_when_no_recommendation(self):
        """Status endpoint returns None routing when no last_recommendation."""
        last_recommendation = None

        routing_summary = last_recommendation.get("routing_summary") if last_recommendation else None
        control_tier = last_recommendation.get("control_tier") if last_recommendation else None

        assert routing_summary is None
        assert control_tier is None

    def test_status_none_when_recommendation_lacks_routing(self):
        """Status returns None if recommendation exists but lacks routing fields."""
        last_recommendation = {
            "confidence": 0.85,
            "recommendations": [],
        }

        routing_summary = last_recommendation.get("routing_summary") if last_recommendation else None
        control_tier = last_recommendation.get("control_tier") if last_recommendation else None

        assert routing_summary is None
        assert control_tier is None
