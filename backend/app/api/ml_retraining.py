"""
ML Retraining API

Endpoints for model retraining and A/B testing.
Phase 45-01: Online Learning & Automated Retraining.
"""

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

router = APIRouter(prefix="/api/ml-retraining", tags=["ml-retraining"])
limiter = Limiter(key_func=get_remote_address)


@router.get("/status")
@limiter.limit("1000/minute")
async def get_model_status(
    request: Request,
    site_id: str | None = Query(None, description="Site ID for site-scoped model status"),
):
    """Check all models for staleness and performance issues.

    Rate limit: 1000 requests/minute
    """
    from ml.training.retraining_scheduler import get_retraining_scheduler

    scheduler = get_retraining_scheduler()
    checks = scheduler.check_all_models(site_id=site_id)

    needs_retrain = [c for c in checks if c["needs_retrain"]]
    return {
        "total_models_checked": len(checks),
        "site_id": site_id,
        "needs_retrain": len(needs_retrain),
        "models": checks,
    }


@router.get("/training-data")
@limiter.limit("1000/minute")
async def get_training_data_status(
    request: Request,
    site_id: str | None = Query(None, description="Filter by site ID"),
):
    """Check available training data per equipment type.

    Shows hours of real sensor data available in Supabase, and whether
    each equipment type has enough data for LSTM (500h) or autoencoder (200h) training.
    """
    from ml.data.supabase_loader import SupabaseTrainingDataLoader

    loader = SupabaseTrainingDataLoader(site_id=site_id)
    summary = loader.get_data_summary()

    ready_lstm = sum(1 for v in summary.values() if v["ready_for_lstm"])
    ready_ae = sum(1 for v in summary.values() if v["ready_for_autoencoder"])

    return {
        "site_id": site_id or "all",
        "equipment_types": summary,
        "ready_for_lstm_training": ready_lstm,
        "ready_for_autoencoder_training": ready_ae,
        "total_types": len(summary),
    }


@router.post("/trigger")
@limiter.limit("100/minute")
async def trigger_retraining(
    request: Request,
    background_tasks: BackgroundTasks,
    model_type: str = Query(..., description="Model type: lstm or autoencoder"),
    equipment_type: str = Query(..., description="Equipment type: chiller, ahu, etc."),
    site_id: str = Query(..., description="Site ID for site-scoped retraining"),
    reason: str = Query("manual", description="Reason for retraining"),
):
    """Trigger model retraining (runs in background).

    Rate limit: 100 requests/minute (CPU-intensive)
    """
    from ml.training.retraining_scheduler import get_retraining_scheduler

    scheduler = get_retraining_scheduler()

    result = scheduler.trigger_retraining(model_type, equipment_type, reason, site_id=site_id)

    return {
        "triggered": result.success,
        "model_type": model_type,
        "equipment_type": equipment_type,
        "site_id": site_id,
        "reason": reason,
        "new_model_id": result.new_model_id,
        "error": result.error,
    }


@router.get("/history")
@limiter.limit("1000/minute")
async def get_retrain_history(request: Request):
    """Get history of retraining operations.

    Rate limit: 1000 requests/minute
    """
    from ml.training.retraining_scheduler import get_retraining_scheduler

    scheduler = get_retraining_scheduler()
    return {"history": scheduler.get_retrain_history()}


@router.post("/ab-test/create")
@limiter.limit("100/minute")
async def create_ab_test(
    request: Request,
    model_type: str = Query(..., description="Model type"),
    equipment_type: str = Query(..., description="Equipment type"),
    candidate_model_id: str = Query(..., description="Candidate model ID to test"),
):
    """Create a new A/B test between current active and candidate model.

    Rate limit: 100 requests/minute (CPU-intensive)
    """
    from ml.ab_testing.ab_test_manager import get_ab_test_manager

    manager = get_ab_test_manager()
    result = manager.create_test(model_type, equipment_type, candidate_model_id)

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Failed to create test"))

    return result


@router.get("/ab-test/{test_id}")
@limiter.limit("600/minute")
async def evaluate_ab_test(request: Request, test_id: str):
    """Evaluate A/B test results.

    Rate limit: 600 requests/minute
    """
    from ml.ab_testing.ab_test_manager import get_ab_test_manager

    manager = get_ab_test_manager()
    result = manager.evaluate_test(test_id)

    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])

    return result


@router.post("/ab-test/{test_id}/promote")
@limiter.limit("100/minute")
async def promote_ab_test(request: Request, test_id: str):
    """Promote the candidate model from an A/B test to active.

    Rate limit: 100 requests/minute (CPU-intensive)
    """
    from ml.ab_testing.ab_test_manager import get_ab_test_manager

    manager = get_ab_test_manager()
    result = manager.promote_candidate(test_id)

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Promotion failed"))

    return result


@router.get("/ab-tests")
@limiter.limit("1000/minute")
async def list_ab_tests(
    request: Request,
    status: str | None = Query(None, description="Filter by status: running, completed, promoted, cancelled"),
):
    """List all A/B tests.

    Rate limit: 1000 requests/minute
    """
    from ml.ab_testing.ab_test_manager import get_ab_test_manager

    manager = get_ab_test_manager()
    return {"tests": manager.list_tests(status=status)}
