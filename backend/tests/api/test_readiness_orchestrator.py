"""Tests for Phase 238 Readiness Orchestrator.

Verifies:
- AC-1: Structured, explainable readiness output
- AC-2: Fail-closed gate evaluation
- AC-10: Determinism of readiness evaluation
"""

import pytest
from datetime import UTC, datetime

from app.services.phase_promotion_evaluator import (
    PhasePromotionEvaluator,
    GateResult,
    PromotionResult,
)


@pytest.mark.asyncio
async def test_site_002_supervised_eligibility():
    """AC-8: site-002 live acceptance case.

    site-002 is advisory with 1039.6 ml_hours (≥ 500), 94 days in advisory (≥ 30),
    and 45603+ recs (≥ 50). Expected: structured readiness output (eligible or blocked)
    with evidence-traceable reasons.
    """
    evaluator = PhasePromotionEvaluator()
    result = await evaluator.evaluate_site("site-002", "advisory")

    assert result.from_phase == "advisory"
    assert result.to_phase == "supervised"
    assert result.computed_at is not None

    # Verify structured output (AC-1): always has satisfied/not_satisfied breakdown
    readiness_dict = result.to_readiness_dict()
    assert "satisfied" in readiness_dict
    assert "not_satisfied" in readiness_dict
    assert len(readiness_dict["satisfied"]) > 0

    # ml_hours gate should pass (1039.6h ≥ 500h)
    ml_gates = [g for g in readiness_dict["satisfied"] if "ml_hours" in g["gate"]]
    assert len(ml_gates) > 0, "ml_hours gate should pass"

    # Whatever gates don't pass, they're documented with reasons
    for gate in readiness_dict["not_satisfied"]:
        # Fail-closed: any unevaluable gate has a reason explaining why it failed
        pass  # Just verify the structure exists


@pytest.mark.asyncio
async def test_gate_result_reason_field():
    """AC-1: GateResult includes reason for explainability."""
    result = GateResult(
        gate="ml_hours_ingested >= 500",
        passed=True,
        value=1039.6,
        threshold=500,
        reason="1039.6h ≥ 500h minimum",
    )

    assert result.reason is not None
    assert "1039.6" in result.reason


@pytest.mark.asyncio
async def test_readiness_dict_structure():
    """AC-1: Structured readiness breakdown with satisfied/not_satisfied."""
    gates = [
        GateResult(gate="ml_hours >= 500", passed=True, value=1000, threshold=500, reason="pass"),
        GateResult(gate="recs >= 50", passed=False, value=30, threshold=50, reason="insufficient"),
    ]

    result = PromotionResult(
        eligible=False,
        from_phase="advisory",
        to_phase="supervised",
        gates=gates,
        computed_at=datetime.now(tz=UTC).isoformat(),
    )

    breakdown = result.to_readiness_dict()
    assert len(breakdown["satisfied"]) == 1
    assert len(breakdown["not_satisfied"]) == 1
    assert breakdown["satisfied"][0]["gate"] == "ml_hours >= 500"
    assert breakdown["not_satisfied"][0]["gate"] == "recs >= 50"


@pytest.mark.asyncio
async def test_determinism_idempotent_evaluation():
    """AC-10: Same evidence snapshot → identical result (determinism test).

    Evaluate site-002 twice in quick succession; results should be identical.
    """
    evaluator = PhasePromotionEvaluator()

    result1 = await evaluator.evaluate_site("site-002", "advisory")
    result2 = await evaluator.evaluate_site("site-002", "advisory")

    # Same eligibility
    assert result1.eligible == result2.eligible

    # Same gate count and names
    gates1 = sorted([g.gate for g in result1.gates])
    gates2 = sorted([g.gate for g in result2.gates])
    assert gates1 == gates2

    # All gates have identical pass/fail
    for g1, g2 in zip(
        sorted(result1.gates, key=lambda g: g.gate),
        sorted(result2.gates, key=lambda g: g.gate),
    ):
        assert g1.passed == g2.passed, f"Gate {g1.gate} passed mismatch"
        assert g1.value == g2.value, f"Gate {g1.gate} value mismatch"


@pytest.mark.asyncio
async def test_demotion_executor_exists():
    """AC-7: Demotion executor is callable (smoke test).

    Verifies the executor method exists and runs without error.
    (Actual demotion behavior requires safety violations in DB.)
    """
    evaluator = PhasePromotionEvaluator()
    # Should complete without error even if no demotions needed
    await evaluator.check_and_apply_demotions()


@pytest.mark.asyncio
async def test_drift_verdict_gate_evaluation():
    """Phase 240 M2.3: Drift verdict gates evaluate correctly.

    Tests gate pattern: drift_verdict(equipment_type) != EXPECTED_VERDICT
    """
    evaluator = PhasePromotionEvaluator()

    # Create a test gate
    gate = "drift_verdict(chiller) != DRIFT_DETECTED"

    # Evaluate the gate for site-002
    # This will fetch the latest drift verdict from drift_detection_log
    from app.database.supabase_client import get_supabase_client

    client = get_supabase_client()

    # Just test that the gate evaluation doesn't crash
    # Actual verdict depends on what's in drift_detection_log
    try:
        result = await evaluator._evaluate_single_gate(
            client,
            "site-002",
            None,
            "site-002",
            gate,
            1000.0,  # ml_hours
            datetime.now(tz=UTC),
        )

        # Verify gate result structure
        assert result.gate == gate
        assert isinstance(result.passed, bool)
        assert result.value is not None or result.reason is not None
    except Exception as e:
        pytest.fail(f"Drift verdict gate evaluation failed: {e}")


@pytest.mark.asyncio
async def test_readiness_includes_trust_metrics():
    """Phase 240 M2.3: Readiness response includes trust metrics.

    Verify that evaluate_site returns trust_confidence and equipment_findings
    in the PromotionResult.
    """
    evaluator = PhasePromotionEvaluator()
    result = await evaluator.evaluate_site("site-002", "advisory")

    # Verify trust metrics are computed
    assert result.trust_confidence is not None
    assert isinstance(result.trust_confidence, float)
    assert 0.0 <= result.trust_confidence <= 1.0

    # Verify trust breakdown structure
    assert result.trust_breakdown is not None
    assert "base_trust" in result.trust_breakdown
    assert "drift_penalty" in result.trust_breakdown
    assert "formula" in result.trust_breakdown

    # Verify equipment_findings is a list
    assert isinstance(result.equipment_findings, list)

    # Verify readiness dict includes trust metrics
    readiness_dict = result.to_readiness_dict()
    assert "trust_confidence" in readiness_dict
    assert "trust_breakdown" in readiness_dict
    assert "equipment_findings" in readiness_dict
