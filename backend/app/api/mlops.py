"""
MLOps Monitoring API

Endpoints for drift detection, ML alerting, success metrics,
and automated reporting.

Phase 45-03: MLOps Monitoring and Success Metrics.
"""

from fastapi import APIRouter, HTTPException, Query, Request
from typing import Optional
from app.middleware.rate_limiter import limiter

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
async def record_prediction_outcome(
    prediction_id: str = Query(..., description="Prediction ID"),
    equipment_id: str = Query(..., description="Equipment ID"),
    predicted_failure: bool = Query(..., description="Was failure predicted?"),
    actual_failure: bool = Query(..., description="Did failure actually occur?"),
    prediction_date: str = Query(..., description="Prediction date (ISO format)"),
    outcome_date: str = Query(..., description="Outcome date (ISO format)"),
):
    """Record a prediction outcome for metrics tracking."""
    from ml.metrics.calculator import get_metrics_calculator
    calc = get_metrics_calculator()
    return calc.record_prediction_outcome(
        prediction_id=prediction_id,
        equipment_id=equipment_id,
        predicted_failure=predicted_failure,
        actual_failure=actual_failure,
        prediction_date=prediction_date,
        outcome_date=outcome_date,
    )


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
        raise HTTPException(
            status_code=400, detail="Period must be 'weekly' or 'monthly'"
        )

    from ml.metrics.calculator import get_metrics_calculator
    calc = get_metrics_calculator()
    return calc.generate_report(period=period, report_date=report_date)


# --- Composite Health ---


@router.get("/health")
async def get_mlops_health():
    """Get comprehensive MLOps health status.

    Combines drift status, alerts, metrics, and model health
    into a single health check response.
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

    return {
        "status": health_status,
        "checked_at": metrics["calculated_at"],
        "overall_score": metrics["overall_score"],
        "targets_met": targets_met,
        "total_targets": total_targets,
        "critical_alerts": critical_alerts,
        "drift_detected": any_drift,
        "metrics_summary": {
            k: {"current": v["current"], "target": v["target"], "met": v["met"]}
            for k, v in metrics["metrics"].items()
        },
        "alert_summary": alert_summary,
    }
