"""
ML Retraining API

Endpoints for model retraining, performance monitoring, and A/B testing.
Phase 45-01: Online Learning & Automated Retraining.
"""

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from typing import Optional

router = APIRouter(prefix="/api/ml-retraining", tags=["ml-retraining"])


@router.get("/status")
async def get_model_status():
    """Check all models for staleness and performance issues."""
    from ml.training.retraining_scheduler import get_retraining_scheduler
    scheduler = get_retraining_scheduler()
    checks = scheduler.check_all_models()

    needs_retrain = [c for c in checks if c["needs_retrain"]]
    return {
        "total_models_checked": len(checks),
        "needs_retrain": len(needs_retrain),
        "models": checks,
    }


@router.post("/trigger")
async def trigger_retraining(
    background_tasks: BackgroundTasks,
    model_type: str = Query(..., description="Model type: lstm or autoencoder"),
    equipment_type: str = Query(..., description="Equipment type: chiller, ahu, etc."),
    reason: str = Query("manual", description="Reason for retraining"),
):
    """Trigger model retraining (runs in background)."""
    from ml.training.retraining_scheduler import get_retraining_scheduler
    scheduler = get_retraining_scheduler()

    result = scheduler.trigger_retraining(model_type, equipment_type, reason)

    return {
        "triggered": result.success,
        "model_type": model_type,
        "equipment_type": equipment_type,
        "reason": reason,
        "new_model_id": result.new_model_id,
        "error": result.error,
    }


@router.get("/history")
async def get_retrain_history():
    """Get history of retraining operations."""
    from ml.training.retraining_scheduler import get_retraining_scheduler
    scheduler = get_retraining_scheduler()
    return {"history": scheduler.get_retrain_history()}


@router.get("/performance")
async def evaluate_performance(
    days_back: int = Query(7, description="Number of days to evaluate"),
    building_code: str = Query("site-002", description="Building to evaluate"),
):
    """Evaluate prediction accuracy against actual outcomes."""
    from ml.monitoring.performance_monitor import get_performance_monitor
    monitor = get_performance_monitor()
    return monitor.evaluate_predictions(days_back=days_back, building_code=building_code)


@router.get("/performance/health")
async def get_model_health():
    """Get health summary of all active models."""
    from ml.monitoring.performance_monitor import get_performance_monitor
    monitor = get_performance_monitor()
    return monitor.get_model_health_summary()


@router.get("/performance/trend")
async def get_performance_trend(
    limit: int = Query(10, description="Number of recent evaluations"),
):
    """Get recent performance evaluation history."""
    from ml.monitoring.performance_monitor import get_performance_monitor
    monitor = get_performance_monitor()
    return {"evaluations": monitor.get_performance_trend(limit=limit)}


@router.post("/ab-test/create")
async def create_ab_test(
    model_type: str = Query(..., description="Model type"),
    equipment_type: str = Query(..., description="Equipment type"),
    candidate_model_id: str = Query(..., description="Candidate model ID to test"),
):
    """Create a new A/B test between current active and candidate model."""
    from ml.ab_testing.ab_test_manager import get_ab_test_manager
    manager = get_ab_test_manager()
    result = manager.create_test(model_type, equipment_type, candidate_model_id)

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Failed to create test"))

    return result


@router.get("/ab-test/{test_id}")
async def evaluate_ab_test(test_id: str):
    """Evaluate A/B test results."""
    from ml.ab_testing.ab_test_manager import get_ab_test_manager
    manager = get_ab_test_manager()
    result = manager.evaluate_test(test_id)

    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])

    return result


@router.post("/ab-test/{test_id}/promote")
async def promote_ab_test(test_id: str):
    """Promote the candidate model from an A/B test to active."""
    from ml.ab_testing.ab_test_manager import get_ab_test_manager
    manager = get_ab_test_manager()
    result = manager.promote_candidate(test_id)

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Promotion failed"))

    return result


@router.get("/ab-tests")
async def list_ab_tests(
    status: Optional[str] = Query(None, description="Filter by status: running, completed, promoted, cancelled"),
):
    """List all A/B tests."""
    from ml.ab_testing.ab_test_manager import get_ab_test_manager
    manager = get_ab_test_manager()
    return {"tests": manager.list_tests(status=status)}
