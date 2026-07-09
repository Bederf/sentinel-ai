"""Tests for site AI policy readiness gating."""

from types import SimpleNamespace

import pytest

from app.services.quality_gate_policy import GateStatus
from app.services.site_ai_policy_service import get_ml_training_readiness


@pytest.mark.asyncio
async def test_ml_training_readiness_requires_pass_not_warn(monkeypatch):
    """ML readiness must stay blocked until the overall gate is PASS."""

    class _Rule:
        def __init__(self, metric: str, state: GateStatus):
            self.metric = metric
            self.value = 1.0
            self.state = state
            self.threshold = SimpleNamespace(pass_bound=1.0, warn_bound=0.5, direction="higher_is_better")

    async def _fake_evaluate_site(_site_id):
        return SimpleNamespace(
            overall=GateStatus.WARN,
            evaluated_at=None,
            rule_results=[
                _Rule("freshness_minutes", GateStatus.PASS),
                _Rule("ingest_error_rate_pct_1h", GateStatus.PASS),
                _Rule("match_coverage_pct", GateStatus.PASS),
                _Rule("manual_source_pct", GateStatus.PASS),
                _Rule("unmatched_points_pct", GateStatus.PASS),
                _Rule("commissioning_all_gates_passed", GateStatus.PASS),
                _Rule("consecutive_pass_days", GateStatus.PASS),
            ],
        )

    monkeypatch.setattr(
        "app.services.quality_gate_evaluator.QualityGateEvaluator",
        lambda: SimpleNamespace(evaluate_site=_fake_evaluate_site),
    )

    readiness = await get_ml_training_readiness("site-005")

    assert readiness["ready"] is False
    assert readiness["overall"] == "warn"
