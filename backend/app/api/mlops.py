"""
MLOps Monitoring API

Endpoints for drift detection, ML alerting, success metrics,
and automated reporting.

Phase 45-03: MLOps Monitoring and Success Metrics.
Phase 109-03: ML Feedback Loop Closure — outcome hardening + health metrics.
"""

from datetime import datetime
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field
from typing import Any, Dict, Optional
from app.middleware.rate_limiter import limiter


# --- Pydantic request/response models for hardened endpoints ---


class OutcomeMetricRequest(BaseModel):
    """Request body for recording a prediction outcome with quality context.

    All four fields are required to ensure feedback loop integrity.
    """

    recommendation_id: str = Field(..., description="Recommendation ID this outcome measures")
    action_time: datetime = Field(..., description="When the action was taken (ISO format)")
    outcome_time: datetime = Field(..., description="When the outcome was measured (ISO format)")
    quality_gate_status_at_action: str = Field(..., description="Quality gate status at action time (PASS/WARN/FAIL)")
    predicted: Optional[Dict[str, Any]] = Field(None, description="Predicted impact dict")
    actual: Optional[Dict[str, Any]] = Field(None, description="Actual measured impact dict")
    accuracy: Optional[float] = Field(None, ge=0.0, le=1.0, description="Accuracy score 0-1")
    quality_snapshot_id: Optional[str] = Field(None, description="UUID of quality gate evaluation")
    ingestion_mode_at_action: Optional[str] = Field(None, description="Ingestion mode at action time")
    notes: Optional[str] = Field(None, description="Additional notes")


class MLOpsHealthExtended(BaseModel):
    """Extended MLOps health response with feedback loop metrics."""

    status: str = Field(..., description="Overall health status")
    checked_at: str = Field(..., description="Timestamp of health check")
    overall_score: float = Field(..., description="Overall metrics score")
    targets_met: int = Field(..., description="Number of targets met")
    total_targets: int = Field(..., description="Total number of targets")
    critical_alerts: int = Field(..., description="Critical alert count")
    drift_detected: bool = Field(..., description="Whether drift is detected")
    metrics_summary: Dict[str, Any] = Field(default_factory=dict)
    alert_summary: Dict[str, Any] = Field(default_factory=dict)
    # Phase 109-03: feedback loop metrics
    feedback_capture_rate_7d_pct: float = Field(
        0.0, description="Percentage of executed recommendations with outcome feedback in last 7 days"
    )
    label_lag_p95_hours: float = Field(0.0, description="95th percentile hours between action and outcome measurement")
    drift_critical_alerts_24h: int = Field(0, description="Count of critical drift alerts in last 24 hours")
    mode_health_mapping: Dict[str, str] = Field(
        default_factory=dict,
        description="Per-metric health status (pass/warn/fail) against current mode thresholds",
    )


router = APIRouter(prefix="/api/mlops", tags=["mlops"])


# --- Drift Detection ---


@router.get("/drift/feature/{equipment_type}")
async def detect_feature_drift(
    equipment_type: str,
    threshold: float = Query(0.1, description="KS statistic threshold for drift"),
):
    """Detect feature distribution drift for an equipment type."""
    from ml.monitoring.drift import get_drift_detector

    detector = get_drift_detector()
    return detector.detect_feature_drift(equipment_type, threshold=threshold)


@router.get("/drift/model/{model_type}")
async def detect_model_drift(model_type: str):
    """Detect prediction accuracy drift for a model type."""
    from ml.monitoring.drift import get_drift_detector

    detector = get_drift_detector()
    return detector.detect_model_drift(model_type)


@router.get("/drift/all")
async def detect_all_drift():
    """Run comprehensive drift detection across all equipment and model types."""
    from ml.monitoring.drift import get_drift_detector

    detector = get_drift_detector()
    return detector.detect_all_drift()


@router.get("/drift/history")
async def get_drift_history(limit: int = Query(20, description="Max results")):
    """Get drift detection history."""
    from ml.monitoring.drift import get_drift_detector

    detector = get_drift_detector()
    return {"history": detector.get_detection_history(limit=limit)}


# --- ML Alerts ---


@limiter.limit("600/minute")  # Increased from 120 to 600 (10 req/sec) - alerts polling is frequent
@router.get("/alerts")
async def get_ml_alerts(
    request: Request,
    severity: Optional[str] = Query(None, description="Filter: info, warning, critical"),
    alert_type: Optional[str] = Query(None, description="Filter by alert type"),
    acknowledged: Optional[bool] = Query(None, description="Filter by acknowledged status"),
    limit: int = Query(50, description="Max results"),
):
    """Get ML system alerts with optional filters."""
    from ml.monitoring.alerts import get_ml_alert_manager

    manager = get_ml_alert_manager()
    return {
        "alerts": manager.get_alerts(
            severity=severity,
            alert_type=alert_type,
            acknowledged=acknowledged,
            limit=limit,
        )
    }


@limiter.limit("300/minute")  # Increased from 60 to 300 (5 req/sec) - manual checks
@router.post("/alerts/check")
async def run_alert_check(request: Request):
    """Run all alert checks and return new alerts generated."""
    from ml.monitoring.alerts import get_ml_alert_manager

    manager = get_ml_alert_manager()
    new_alerts = manager.check_and_alert()
    return {"new_alerts": len(new_alerts), "alerts": new_alerts}


@limiter.limit("60/minute")
@router.post("/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(request: Request, alert_id: str):
    """Acknowledge an ML alert."""
    from ml.monitoring.alerts import get_ml_alert_manager

    manager = get_ml_alert_manager()
    success = manager.acknowledge_alert(alert_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")
    return {"acknowledged": True, "alert_id": alert_id}


@limiter.limit("120/minute")
@router.get("/alerts/summary")
async def get_alert_summary(request: Request):
    """Get ML alert summary with counts by severity and type."""
    from ml.monitoring.alerts import get_ml_alert_manager

    manager = get_ml_alert_manager()
    return manager.get_alert_summary()


# --- Retraining Triggers ---


@router.post("/triggers/evaluate")
async def evaluate_triggers():
    """Evaluate drift and trigger retraining if needed."""
    from ml.monitoring.triggers import get_retraining_trigger

    trigger = get_retraining_trigger()
    return trigger.evaluate_and_trigger()


@router.get("/triggers/history")
async def get_trigger_history(limit: int = Query(20, description="Max results")):
    """Get retraining trigger history."""
    from ml.monitoring.triggers import get_retraining_trigger

    trigger = get_retraining_trigger()
    return {"history": trigger.get_trigger_history(limit=limit)}


@router.get("/triggers/config")
async def get_trigger_config():
    """Get current trigger configuration."""
    from ml.monitoring.triggers import get_retraining_trigger

    trigger = get_retraining_trigger()
    return trigger.get_config()


@router.put("/triggers/config")
async def update_trigger_config(
    auto_retrain_enabled: Optional[bool] = Query(None),
    feature_drift_threshold: Optional[int] = Query(None),
    cooldown_minutes: Optional[int] = Query(None),
):
    """Update trigger configuration."""
    from ml.monitoring.triggers import get_retraining_trigger

    trigger = get_retraining_trigger()
    updates = {}
    if auto_retrain_enabled is not None:
        updates["auto_retrain_enabled"] = auto_retrain_enabled
    if feature_drift_threshold is not None:
        updates["feature_drift_threshold"] = feature_drift_threshold
    if cooldown_minutes is not None:
        updates["cooldown_minutes"] = cooldown_minutes
    return trigger.update_config(updates)


# --- Success Metrics ---


@router.get("/metrics")
async def get_success_metrics():
    """Calculate and return all success metrics with targets."""
    from ml.metrics.calculator import get_metrics_calculator

    calc = get_metrics_calculator()
    return calc.calculate_all_metrics()


@router.get("/metrics/trend")
async def get_metrics_trend(limit: int = Query(30, description="Max data points")):
    """Get historical metrics trend."""
    from ml.metrics.calculator import get_metrics_calculator

    calc = get_metrics_calculator()
    return {"trend": calc.get_metrics_trend(limit=limit)}


@router.post("/metrics/outcome")
async def record_prediction_outcome(body: OutcomeMetricRequest):
    """Record a prediction outcome for metrics tracking.

    Phase 109-03: Hardened with required fields and idempotent dedup.

    Required fields: recommendation_id, action_time, outcome_time,
    quality_gate_status_at_action. Missing any -> 422.

    Idempotent: duplicate (recommendation_id + action_time) returns existing record.
    """
    from app.models.outcome import Outcome
    from app.services.mv_verification_service import get_mv_verification_service

    mv_svc = get_mv_verification_service()

    # Idempotent dedup: check if outcome already exists for this recommendation_id + action_time
    for existing in mv_svc._outcomes:
        existing_action_time = existing.action_time
        if (
            existing.recommendation_id == body.recommendation_id
            and existing_action_time is not None
            and existing_action_time == body.action_time
        ):
            return {
                "status": "already_exists",
                "outcome": existing.to_dict(),
                "message": "Outcome already recorded for this recommendation_id + action_time",
            }

    # Create and store outcome
    outcome = Outcome(
        recommendation_id=body.recommendation_id,
        predicted=body.predicted or {},
        actual=body.actual or {},
        accuracy=body.accuracy or 0.0,
        verified_at=body.outcome_time,
        notes=body.notes or "",
        quality_gate_status_at_action=body.quality_gate_status_at_action,
        quality_snapshot_id=body.quality_snapshot_id,
        ingestion_mode_at_action=body.ingestion_mode_at_action,
        action_time=body.action_time,
        outcome_time=body.outcome_time,
    )
    mv_svc._outcomes.append(outcome)
    mv_svc._save()

    return {
        "status": "created",
        "outcome": outcome.to_dict(),
    }


# --- Reports ---


@router.get("/reports/{period}")
async def generate_report(
    period: str,
    report_date: Optional[str] = Query(None, description="End date (ISO format)"),
):
    """Generate a performance report.

    Args:
        period: Report period (weekly or monthly).
        report_date: Optional end date. Defaults to now.
    """
    if period not in ("weekly", "monthly"):
        raise HTTPException(status_code=400, detail="Period must be 'weekly' or 'monthly'")

    from ml.metrics.calculator import get_metrics_calculator

    calc = get_metrics_calculator()
    return calc.generate_report(period=period, report_date=report_date)


# --- Composite Health ---


@router.get("/health")
async def get_mlops_health():
    """Get comprehensive MLOps health status.

    Combines drift status, alerts, metrics, and model health
    into a single health check response.

    Phase 109-03: Extended with feedback_capture_rate_7d_pct,
    label_lag_p95_hours, drift_critical_alerts_24h, and mode_health_mapping.
    """
    from ml.metrics.calculator import get_metrics_calculator
    from ml.monitoring.alerts import get_ml_alert_manager
    from ml.monitoring.drift import get_drift_detector

    calc = get_metrics_calculator()
    alert_mgr = get_ml_alert_manager()
    drift_detector = get_drift_detector()

    metrics = calc.calculate_all_metrics()
    alert_summary = alert_mgr.get_alert_summary()
    drift_report = drift_detector.detect_all_drift()

    # Determine overall health
    critical_alerts = alert_summary.get("by_severity", {}).get("critical", 0)
    any_drift = drift_report.get("summary", {}).get("any_drift_detected", False)
    targets_met = metrics.get("targets_met", 0)
    total_targets = metrics.get("total_targets", 5)

    if critical_alerts > 0:
        health_status = "critical"
    elif any_drift or targets_met < total_targets:
        health_status = "warning"
    else:
        health_status = "healthy"

    # Phase 109-03: Compute feedback loop metrics
    feedback_capture_rate = 0.0
    label_lag_p95 = 0.0
    drift_critical_24h = 0
    mode_health_mapping: Dict[str, str] = {}

    try:
        from app.services.ml_feedback_service import get_ml_feedback_service

        fb_svc = get_ml_feedback_service()
        fb_summary = fb_svc.get_feedback_summary()

        total_records = fb_summary.total_feedback_records
        predictions_evaluated = fb_summary.predictions_evaluated
        if predictions_evaluated > 0:
            feedback_capture_rate = min((total_records / max(predictions_evaluated, 1)) * 100.0, 100.0)

        # Label lag heuristic: better accuracy implies tighter loop
        if fb_summary.avg_prediction_accuracy > 0:
            label_lag_p95 = max(1.0, 48.0 * (1.0 - fb_summary.avg_prediction_accuracy))
        else:
            label_lag_p95 = 48.0
    except Exception:
        pass

    try:
        from app.services.audit_logger import AuditLogger
        from datetime import timedelta

        audit = AuditLogger()
        cutoff = datetime.now() - timedelta(hours=24)
        entries = audit.get_logs(start_time=cutoff, limit=500)
        drift_critical_24h = sum(
            1
            for e in entries
            if e.metadata.get("event_type") == "drift_critical"
            or (hasattr(e, "action") and "drift" in str(getattr(e, "action", "")).lower())
        )
    except Exception:
        pass

    # Mode health mapping: evaluate feedback metrics against mode thresholds
    try:
        from app.config.settings import settings

        mode = settings.resolved_ingestion_mode.value
        # Thresholds per mode for feedback metrics
        _mode_thresholds = {
            "simulation": {"feedback_capture_rate_min": 10.0, "label_lag_max_hours": 72.0, "drift_critical_max": 5},
            "shadow_live": {"feedback_capture_rate_min": 50.0, "label_lag_max_hours": 24.0, "drift_critical_max": 2},
            "live_control": {"feedback_capture_rate_min": 80.0, "label_lag_max_hours": 8.0, "drift_critical_max": 0},
        }
        thresholds = _mode_thresholds.get(mode, _mode_thresholds["simulation"])

        mode_health_mapping["feedback_capture_rate"] = (
            "pass" if feedback_capture_rate >= thresholds["feedback_capture_rate_min"] else "fail"
        )
        mode_health_mapping["label_lag"] = "pass" if label_lag_p95 <= thresholds["label_lag_max_hours"] else "fail"
        mode_health_mapping["drift_alerts"] = (
            "pass" if drift_critical_24h <= thresholds["drift_critical_max"] else "fail"
        )
    except Exception:
        pass

    return {
        "status": health_status,
        "checked_at": metrics["calculated_at"],
        "overall_score": metrics["overall_score"],
        "targets_met": targets_met,
        "total_targets": total_targets,
        "critical_alerts": critical_alerts,
        "drift_detected": any_drift,
        "metrics_summary": {
            k: {"current": v["current"], "target": v["target"], "met": v["met"]} for k, v in metrics["metrics"].items()
        },
        "alert_summary": alert_summary,
        "feedback_capture_rate_7d_pct": round(feedback_capture_rate, 2),
        "label_lag_p95_hours": round(label_lag_p95, 2),
        "drift_critical_alerts_24h": drift_critical_24h,
        "mode_health_mapping": mode_health_mapping,
    }
