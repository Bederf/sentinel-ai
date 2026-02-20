"""Endpoint contract tests for Phase 109: Quality Gate Integration.

Tests the quality gate endpoint, approval blocking behavior, monitoring
snapshot integration, and audit trail creation.

Uses DEMO_MODE=true / LIGHTWEIGHT_APP=1 for test isolation. Mocks
QualityGateEvaluator to control gate results deterministically.
"""

import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

# Set env vars before any app imports
os.environ.setdefault("DEMO_MODE", "true")
os.environ.setdefault("LIGHTWEIGHT_APP", "1")

from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.services.quality_gate_policy import (  # noqa: E402
    EnforcementAction,
    GateStatus,
    MetricRuleResult,
    MetricThreshold,
    QualityGateResult,
    ReasonCode,
    RuleState,
)


def _make_gate_result(
    overall: GateStatus = GateStatus.PASS,
    enforcement: EnforcementAction = EnforcementAction.NORMAL,
    failed_rules: list | None = None,
    warn_rules: list | None = None,
    reason_codes: list | None = None,
    mode: str = "simulation",
) -> QualityGateResult:
    """Helper to build a QualityGateResult for mocking."""
    return QualityGateResult(
        overall=overall,
        rule_results=[],
        failed_rules=failed_rules or [],
        warn_rules=warn_rules or [],
        enforcement=enforcement,
        reason_codes=reason_codes or [],
        mode=mode,
        evaluated_at=datetime.utcnow().isoformat(),
    )


def _make_gate_result_with_details(
    overall: GateStatus = GateStatus.PASS,
    enforcement: EnforcementAction = EnforcementAction.NORMAL,
    mode: str = "simulation",
) -> QualityGateResult:
    """Build a QualityGateResult with proper rule_results for the quality-gate endpoint."""
    rule_results = [
        MetricRuleResult(
            metric="freshness_minutes",
            value=60.0,
            state=RuleState.PASS,
            threshold=MetricThreshold(pass_bound=1440, warn_bound=4320, direction="lower_is_better"),
        ),
    ]
    return QualityGateResult(
        overall=overall,
        rule_results=rule_results,
        failed_rules=[],
        warn_rules=[],
        enforcement=enforcement,
        reason_codes=[],
        mode=mode,
        evaluated_at=datetime.utcnow().isoformat(),
    )


@pytest.fixture
def app():
    """Create a minimal FastAPI app with the quality gate router."""
    from fastapi import FastAPI

    from app.api.optimization_quality import router

    test_app = FastAPI()
    test_app.include_router(router, prefix="/api/optimization")
    return test_app


@pytest.fixture
async def client(app):
    """Create an async HTTP client for testing."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ---------------------------------------------------------------------------
# 1. Quality gate endpoint returns 200 for valid site
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_quality_gate_endpoint_returns_200(client):
    """GET /api/optimization/quality-gate/{site_id} returns 200 for a valid site."""
    mock_metrics = {"freshness_minutes": 60.0, "ingest_error_rate_pct_1h": 0.0}
    mock_result = _make_gate_result_with_details()

    with patch("app.api.optimization_quality.QualityGateEvaluator") as MockEvaluator:
        instance = MockEvaluator.return_value
        instance.collect_metrics = AsyncMock(return_value=mock_metrics)
        instance.evaluate = MagicMock(return_value=mock_result)

        response = await client.get("/api/optimization/quality-gate/site-002")

    assert response.status_code == 200
    data = response.json()
    assert data["site_id"] == "site-002"
    assert data["overall_status"] == "pass"
    assert data["enforcement_action"] == "normal"


# ---------------------------------------------------------------------------
# 2. Quality gate endpoint returns 500 when collect_metrics raises
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_quality_gate_endpoint_returns_500_on_error(client):
    """GET /api/optimization/quality-gate/{site_id} returns 500 on collection failure."""
    with patch("app.api.optimization_quality.QualityGateEvaluator") as MockEvaluator:
        instance = MockEvaluator.return_value
        instance.collect_metrics = AsyncMock(side_effect=Exception("Collection failed"))
        instance.evaluate = MagicMock()

        response = await client.get("/api/optimization/quality-gate/nonexistent-xyz")

    assert response.status_code == 500


# ---------------------------------------------------------------------------
# 3. Quality gate response structure has all required fields
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_quality_gate_response_structure(client):
    """Response includes site_id, ingestion_mode, thresholds_used, metric_values, etc."""
    mock_metrics = {
        "freshness_minutes": 60.0,
        "ingest_error_rate_pct_1h": 1.0,
        "match_coverage_pct": 95.0,
    }
    mock_result = _make_gate_result_with_details()

    with patch("app.api.optimization_quality.QualityGateEvaluator") as MockEvaluator:
        instance = MockEvaluator.return_value
        instance.collect_metrics = AsyncMock(return_value=mock_metrics)
        instance.evaluate = MagicMock(return_value=mock_result)

        response = await client.get("/api/optimization/quality-gate/site-002")

    assert response.status_code == 200
    data = response.json()

    required_fields = [
        "site_id",
        "ingestion_mode",
        "thresholds_used",
        "metric_values",
        "rule_results",
        "overall_status",
        "enforcement_action",
        "reason_codes",
    ]
    for field in required_fields:
        assert field in data, f"Missing field: {field}"

    # rule_results should be a list of metric detail dicts
    assert isinstance(data["rule_results"], list)
    if data["rule_results"]:
        detail = data["rule_results"][0]
        assert "metric" in detail
        assert "value" in detail
        assert "state" in detail


# ---------------------------------------------------------------------------
# 4. Approve blocked in shadow_live mode (409)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_approve_blocked_shadow_live():
    """POST /api/recommendations/{rec_id}/approve returns 409 in shadow_live mode."""
    from fastapi import FastAPI

    from app.api.recommendations import router

    test_app = FastAPI()
    test_app.include_router(router)

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        with patch("app.config.settings.settings") as mock_settings:
            mock_settings.resolved_ingestion_mode.value = "shadow_live"

            response = await ac.post(
                "/api/recommendations/rec-001/approve",
                json={"reason": "test"},
            )

    assert response.status_code == 409
    data = response.json()
    assert data["detail"]["error"] == "SHADOW_MODE_NO_EXEC"


# ---------------------------------------------------------------------------
# 5. Approve blocked in live_control FAIL (409 + reason codes)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_approve_blocked_live_control_fail():
    """POST /api/recommendations/{rec_id}/approve returns 409 when gate FAILs in live_control."""
    from fastapi import FastAPI

    from app.api.recommendations import router

    test_app = FastAPI()
    test_app.include_router(router)

    fail_result = _make_gate_result(
        overall=GateStatus.FAIL,
        enforcement=EnforcementAction.BLOCK_WRITES,
        failed_rules=["freshness_minutes"],
        reason_codes=[ReasonCode.DATA_FRESHNESS_FAIL],
        mode="live_control",
    )

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        with (
            patch("app.config.settings.settings") as mock_settings,
            patch("app.services.quality_gate_evaluator.QualityGateEvaluator") as MockEvaluator,
        ):
            mock_settings.resolved_ingestion_mode.value = "live_control"

            instance = MockEvaluator.return_value
            instance.collect_metrics = AsyncMock(return_value={})
            instance.evaluate = MagicMock(return_value=fail_result)

            # Mock the recommendation repo to return a rec with site_id
            mock_rec = MagicMock()
            mock_rec.site_id = "S002"
            with patch("app.database.repositories.get_recommendation_repository") as mock_repo_fn:
                mock_repo = MagicMock()
                mock_repo.get = AsyncMock(return_value=mock_rec)
                mock_repo_fn.return_value = mock_repo

                response = await ac.post(
                    "/api/recommendations/rec-001/approve",
                    json={"reason": "test"},
                )

    assert response.status_code == 409
    data = response.json()
    assert data["detail"]["error"] == "QUALITY_GATE_BLOCK"
    assert "freshness_minutes" in data["detail"]["failed_rules"]
    assert "data_freshness_fail" in data["detail"]["reason_codes"]


# ---------------------------------------------------------------------------
# 6. Approve allowed in live_control PASS (Tier 2 approval service)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_approve_allowed_live_control_pass():
    """ApprovalService.execute_approval proceeds when gate PASSes in live_control."""
    from app.services.approval_service import ApprovalService
    from app.models.recommendation import RecommendationStatus

    svc = ApprovalService.__new__(ApprovalService)
    svc.safety_engine = MagicMock()
    svc.device_manager = MagicMock()
    svc.recommendations_repo = MagicMock()
    svc.audit_repo = None

    pass_result = _make_gate_result(
        overall=GateStatus.PASS,
        enforcement=EnforcementAction.NORMAL,
        mode="live_control",
    )

    # Mock the recommendation with all needed attributes
    mock_rec = MagicMock()
    mock_rec.status = RecommendationStatus.PENDING
    mock_rec.site_id = "S002"
    mock_rec.target_equipment = "S002-AHU-101"
    mock_rec.action = {"point": "temp_setpoint", "value": 22.0}
    mock_rec.correlation_id = "corr-1"
    mock_rec.expected_impact = {}
    mock_rec.action_type = "hvac_setpoint"
    mock_rec.id = "rec-001"
    mock_rec.approved_by = None
    mock_rec.approval_reason = None
    mock_rec.executed_at = None
    mock_rec.execution_result = None
    mock_rec.get_numeric_confidence = MagicMock(return_value=0.8)

    svc.recommendations_repo.get_by_id = AsyncMock(return_value=mock_rec)
    svc.recommendations_repo.upsert = AsyncMock()

    mock_parasite_repo = MagicMock()
    mock_parasite_repo.record_decision = AsyncMock()

    with (
        patch.object(svc, "_check_quality_gate", new_callable=AsyncMock, return_value=pass_result),
        patch.object(svc, "_validate_safety", new_callable=AsyncMock, return_value={"is_safe": True}),
        patch.object(
            svc,
            "_execute_device_write",
            new_callable=AsyncMock,
            return_value={"success": True, "message": "ok"},
        ),
        patch.object(svc, "_verify_cov_feedback", new_callable=AsyncMock, return_value=True),
        patch.object(svc, "_create_audit_log", new_callable=AsyncMock),
        patch("app.services.approval_service.settings") as mock_settings,
        patch("app.services.approval_service.ParasiteDecisionRepository", return_value=mock_parasite_repo),
        patch("app.services.approval_service.emit_decision_event"),
        patch.object(svc, "_record_module_feedback"),
    ):
        mock_settings.resolved_ingestion_mode.value = "live_control"

        result = await svc.execute_approval("rec-001", "operator", "test approval")

    assert result.success is True
    assert result.status == "executed"


# ---------------------------------------------------------------------------
# 7. Approve WARN blocks Tier 3
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_approve_warn_blocks_tier3():
    """Tier 3 auto-execute is blocked when gate status is WARN in live_control."""
    from app.services.approval_service import ApprovalService
    from app.services.tier_routing_engine import TierRoutingResult

    svc = ApprovalService.__new__(ApprovalService)
    svc.safety_engine = MagicMock()
    svc.device_manager = MagicMock()
    svc.recommendations_repo = MagicMock()
    svc.audit_repo = None

    warn_result = _make_gate_result(
        overall=GateStatus.WARN,
        enforcement=EnforcementAction.SUPPRESS_TIER3,
        warn_rules=["mv_accuracy_7d_pct"],
        mode="live_control",
    )

    mock_rec = MagicMock()
    from app.models.recommendation import RecommendationStatus

    mock_rec.status = RecommendationStatus.PENDING
    mock_rec.site_id = "S002"

    svc.recommendations_repo.get_by_id = AsyncMock(return_value=mock_rec)

    routing_result = MagicMock(spec=TierRoutingResult)
    routing_result.decision_id = "dec-1"
    routing_result.correlation_id = "corr-1"
    routing_result.confidence_score = 0.9

    with (
        patch.object(svc, "_check_quality_gate", new_callable=AsyncMock, return_value=warn_result),
        patch.object(svc, "_audit_gate_block"),
        patch("app.services.approval_service.settings") as mock_settings,
    ):
        mock_settings.resolved_ingestion_mode.value = "live_control"

        result = await svc.auto_execute_recommendation("rec-001", routing_result)

    assert result.success is False
    assert "QUALITY_GATE_WARN_TIER3_BLOCK" in result.error_message


# ---------------------------------------------------------------------------
# 8. Auto-execute blocked on FAIL
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_auto_execute_blocked_on_fail():
    """Tier 3 auto-execute is blocked when gate status is FAIL."""
    from app.services.approval_service import ApprovalService
    from app.services.tier_routing_engine import TierRoutingResult

    svc = ApprovalService.__new__(ApprovalService)
    svc.safety_engine = MagicMock()
    svc.device_manager = MagicMock()
    svc.recommendations_repo = MagicMock()
    svc.audit_repo = None

    fail_result = _make_gate_result(
        overall=GateStatus.FAIL,
        enforcement=EnforcementAction.BLOCK_WRITES,
        failed_rules=["ingest_error_rate_pct_1h"],
        reason_codes=[ReasonCode.INGEST_ERROR_RATE_FAIL],
        mode="live_control",
    )

    mock_rec = MagicMock()
    from app.models.recommendation import RecommendationStatus

    mock_rec.status = RecommendationStatus.PENDING
    mock_rec.site_id = "S002"

    svc.recommendations_repo.get_by_id = AsyncMock(return_value=mock_rec)

    routing_result = MagicMock(spec=TierRoutingResult)
    routing_result.decision_id = "dec-2"
    routing_result.correlation_id = "corr-2"
    routing_result.confidence_score = 0.95

    with (
        patch.object(svc, "_check_quality_gate", new_callable=AsyncMock, return_value=fail_result),
        patch.object(svc, "_audit_gate_block"),
        patch("app.services.approval_service.settings") as mock_settings,
    ):
        mock_settings.resolved_ingestion_mode.value = "live_control"

        result = await svc.auto_execute_recommendation("rec-001", routing_result)

    assert result.success is False
    assert "QUALITY_GATE_BLOCK" in result.error_message


# ---------------------------------------------------------------------------
# 9. Blocked execution creates audit record
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_blocked_execution_creates_audit():
    """When a Tier 3 execution is blocked, an audit record is created."""
    from app.services.approval_service import ApprovalService
    from app.services.tier_routing_engine import TierRoutingResult

    svc = ApprovalService.__new__(ApprovalService)
    svc.safety_engine = MagicMock()
    svc.device_manager = MagicMock()
    svc.recommendations_repo = MagicMock()
    svc.audit_repo = None

    fail_result = _make_gate_result(
        overall=GateStatus.FAIL,
        enforcement=EnforcementAction.BLOCK_WRITES,
        failed_rules=["freshness_minutes"],
        reason_codes=[ReasonCode.DATA_FRESHNESS_FAIL],
        mode="live_control",
    )

    mock_rec = MagicMock()
    from app.models.recommendation import RecommendationStatus

    mock_rec.status = RecommendationStatus.PENDING
    mock_rec.site_id = "S002"

    svc.recommendations_repo.get_by_id = AsyncMock(return_value=mock_rec)

    routing_result = MagicMock(spec=TierRoutingResult)
    routing_result.decision_id = "dec-3"
    routing_result.correlation_id = "corr-3"
    routing_result.confidence_score = 0.85

    with (
        patch.object(svc, "_check_quality_gate", new_callable=AsyncMock, return_value=fail_result),
        patch.object(svc, "_audit_gate_block") as mock_audit,
        patch("app.services.approval_service.settings") as mock_settings,
    ):
        mock_settings.resolved_ingestion_mode.value = "live_control"

        result = await svc.auto_execute_recommendation("rec-001", routing_result)

    assert result.success is False
    mock_audit.assert_called_once_with("rec-001", "QUALITY_GATE_BLOCK", fail_result)


# ---------------------------------------------------------------------------
# 10. Monitoring snapshot includes quality_gate field
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_monitoring_includes_quality_gate():
    """MonitoringSnapshot includes a quality_gate dict when evaluation succeeds."""
    from app.models.monitoring import (
        ControlKPIs,
        IngestionKPIs,
        MonitoringSnapshot,
    )

    snapshot = MonitoringSnapshot(
        ingestion_mode="simulation",
        is_live=False,
        building_id="S002",
        ingestion=IngestionKPIs(
            freshness_hours=1.0,
            error_rate=0.0,
            unmatched_points=0,
            total_points=100,
            match_coverage=95.0,
            provenance_summary={"live_protocol": 5, "file_manual": 0},
        ),
        control=ControlKPIs(
            shadow_writes_24h=0,
            blocked_writes_24h=0,
            approved_writes_24h=0,
            safety_violations_24h=0,
        ),
        commissioning=None,
        alerts=[],
        trend_24h=[],
        checked_at=datetime.utcnow().isoformat(),
        quality_gate={
            "overall_status": "pass",
            "enforcement_action": "normal",
            "mode": "simulation",
            "failed_rules": [],
            "warn_rules": [],
            "reason_codes": [],
        },
    )

    assert snapshot.quality_gate is not None
    assert snapshot.quality_gate["overall_status"] == "pass"
    assert snapshot.quality_gate["enforcement_action"] == "normal"


# ---------------------------------------------------------------------------
# 11. JSON in live triggers FAIL (manual_source_pct > 0 in live_control)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_json_in_live_triggers_fail():
    """When manual_source_pct > 0 in live_control mode, quality gate should FAIL."""
    from app.services.quality_gate_evaluator import QualityGateEvaluator, _LIVE_DEFAULTS

    evaluator = QualityGateEvaluator()

    # Start with live defaults (which already fail), but set manual_source_pct > 0
    metrics = dict(_LIVE_DEFAULTS)
    metrics["manual_source_pct"] = 50.0  # 50% manual sources

    result = evaluator.evaluate("live_control", metrics)

    assert result.overall == GateStatus.FAIL
    assert "manual_source_pct" in result.failed_rules

    # The JSON_IN_LIVE_FAIL reason code should be present
    reason_values = [rc.value for rc in result.reason_codes]
    assert "json_in_live_fail" in reason_values


# ---------------------------------------------------------------------------
# 12. Shadow_live auto-execute blocked
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_shadow_live_auto_execute_blocked():
    """Tier 3 auto-execute in shadow_live mode is always blocked."""
    from app.services.approval_service import ApprovalService
    from app.services.tier_routing_engine import TierRoutingResult

    svc = ApprovalService.__new__(ApprovalService)
    svc.safety_engine = MagicMock()
    svc.device_manager = MagicMock()
    svc.recommendations_repo = MagicMock()
    svc.audit_repo = None

    pass_result = _make_gate_result(
        overall=GateStatus.PASS,
        enforcement=EnforcementAction.NORMAL,
        mode="shadow_live",
    )

    mock_rec = MagicMock()
    from app.models.recommendation import RecommendationStatus

    mock_rec.status = RecommendationStatus.PENDING
    mock_rec.site_id = "S002"

    svc.recommendations_repo.get_by_id = AsyncMock(return_value=mock_rec)

    routing_result = MagicMock(spec=TierRoutingResult)
    routing_result.decision_id = "dec-4"
    routing_result.correlation_id = "corr-4"
    routing_result.confidence_score = 0.99

    with (
        patch.object(svc, "_check_quality_gate", new_callable=AsyncMock, return_value=pass_result),
        patch.object(svc, "_audit_gate_block"),
        patch("app.services.approval_service.settings") as mock_settings,
    ):
        mock_settings.resolved_ingestion_mode.value = "shadow_live"

        result = await svc.auto_execute_recommendation("rec-001", routing_result)

    assert result.success is False
    assert "SHADOW_MODE_NO_EXEC" in result.error_message


# ---------------------------------------------------------------------------
# 13. Simulation mode does not block approvals
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_simulation_mode_does_not_block():
    """In simulation mode, quality gate does not block Tier 2 approvals."""
    from app.services.approval_service import ApprovalService
    from app.models.recommendation import RecommendationStatus

    svc = ApprovalService.__new__(ApprovalService)
    svc.safety_engine = MagicMock()
    svc.device_manager = MagicMock()
    svc.recommendations_repo = MagicMock()
    svc.audit_repo = None

    # Even with FAIL overall, simulation mode does not block
    fail_result = _make_gate_result(
        overall=GateStatus.FAIL,
        enforcement=EnforcementAction.CAP_CONFIDENCE,
        failed_rules=["freshness_minutes"],
        reason_codes=[ReasonCode.DATA_FRESHNESS_FAIL],
        mode="simulation",
    )

    mock_rec = MagicMock()
    mock_rec.status = RecommendationStatus.PENDING
    mock_rec.site_id = "S002"
    mock_rec.target_equipment = "S002-AHU-101"
    mock_rec.action = {"point": "temp_setpoint", "value": 22.0}
    mock_rec.correlation_id = "corr-5"
    mock_rec.expected_impact = {}
    mock_rec.action_type = "hvac_setpoint"
    mock_rec.id = "rec-002"
    mock_rec.approved_by = None
    mock_rec.approval_reason = None
    mock_rec.executed_at = None
    mock_rec.execution_result = None
    mock_rec.get_numeric_confidence = MagicMock(return_value=0.8)

    svc.recommendations_repo.get_by_id = AsyncMock(return_value=mock_rec)
    svc.recommendations_repo.upsert = AsyncMock()

    mock_parasite_repo = MagicMock()
    mock_parasite_repo.record_decision = AsyncMock()

    with (
        patch.object(svc, "_check_quality_gate", new_callable=AsyncMock, return_value=fail_result),
        patch.object(svc, "_validate_safety", new_callable=AsyncMock, return_value={"is_safe": True}),
        patch.object(
            svc,
            "_execute_device_write",
            new_callable=AsyncMock,
            return_value={"success": True, "message": "ok"},
        ),
        patch.object(svc, "_verify_cov_feedback", new_callable=AsyncMock, return_value=True),
        patch.object(svc, "_create_audit_log", new_callable=AsyncMock),
        patch("app.services.approval_service.settings") as mock_settings,
        patch("app.services.approval_service.ParasiteDecisionRepository", return_value=mock_parasite_repo),
        patch("app.services.approval_service.emit_decision_event"),
        patch.object(svc, "_record_module_feedback"),
    ):
        mock_settings.resolved_ingestion_mode.value = "simulation"

        result = await svc.execute_approval("rec-002", "operator", "test simulation")

    # In simulation mode, the gate check does not block (mode != shadow_live/live_control)
    assert result.success is True
    assert result.status == "executed"
