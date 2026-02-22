"""
Fleet Learning API

Endpoints for fleet-wide pattern aggregation, global model training,
local fine-tuning, benchmarking, and cross-site insights.

Phase 45-02: Fleet Learning and Cross-Site Insights.
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional

router = APIRouter(prefix="/api/fleet", tags=["fleet-learning"])


# --- Fleet Aggregation ---


@router.get("/summary")
async def get_fleet_summary():
    """Get fleet-wide summary statistics."""
    from ml.fleet.aggregator import get_fleet_aggregator

    aggregator = get_fleet_aggregator()
    return aggregator.get_fleet_summary()


@router.get("/failure-patterns")
async def get_failure_patterns(
    equipment_type: Optional[str] = Query(None, description="Filter by equipment type (CHILLER, AHU, etc.)"),
):
    """Get anonymized failure patterns across fleet."""
    from ml.fleet.aggregator import get_fleet_aggregator

    aggregator = get_fleet_aggregator()
    patterns = aggregator.aggregate_failure_patterns(equipment_type=equipment_type)
    return {"patterns": patterns, "total": len(patterns)}


@router.get("/similar-failures")
async def get_similar_failures(
    equipment_type: str = Query(..., description="Equipment type to match"),
    failure_type: Optional[str] = Query(None, description="Specific failure type"),
    exclude_site: Optional[str] = Query(None, description="Site to exclude from results (privacy)"),
):
    """Find similar equipment failures across fleet."""
    from ml.fleet.aggregator import get_fleet_aggregator

    aggregator = get_fleet_aggregator()
    failures = aggregator.get_similar_failures(
        equipment_type=equipment_type,
        failure_type=failure_type,
        exclude_site=exclude_site,
    )
    return {"similar_failures": failures, "total": len(failures)}


@router.get("/risk-distribution")
async def get_risk_distribution():
    """Get fleet-wide equipment risk distribution."""
    from ml.fleet.aggregator import get_fleet_aggregator

    aggregator = get_fleet_aggregator()
    return aggregator.get_risk_distribution()


# --- Benchmarking ---


@router.get("/benchmarks")
async def get_benchmarks(
    equipment_type: Optional[str] = Query(None, description="Filter by equipment type"),
):
    """Get fleet benchmarking data for equipment types."""
    from ml.fleet.aggregator import get_fleet_aggregator

    aggregator = get_fleet_aggregator()
    benchmarks = aggregator.get_benchmarks(equipment_type=equipment_type)
    return {"benchmarks": benchmarks, "total": len(benchmarks)}


@router.get("/benchmark-site")
async def benchmark_site(
    site_code: str = Query(..., description="Site to benchmark"),
    site_health: float = Query(..., description="Current site health score (0-100)"),
    equipment_type: Optional[str] = Query(None, description="Filter by equipment type"),
):
    """Compare a site's performance against fleet average."""
    from ml.fleet.aggregator import get_fleet_aggregator

    aggregator = get_fleet_aggregator()
    return aggregator.benchmark_site(
        site_code=site_code,
        site_health=site_health,
        equipment_type=equipment_type,
    )


# --- Global Models ---


@router.get("/global-models")
async def list_global_models(
    model_type: Optional[str] = Query(None, description="Filter: lstm, autoencoder"),
    equipment_type: Optional[str] = Query(None, description="Filter: chiller, ahu, etc."),
):
    """List all trained global fleet models."""
    from ml.fleet.global_model import get_global_model_trainer

    trainer = get_global_model_trainer()
    models = trainer.list_global_models(model_type=model_type, equipment_type=equipment_type)
    return {"models": models, "total": len(models)}


@router.post("/global-models/train")
async def train_global_model(
    model_type: str = Query(..., description="Model type: lstm or autoencoder"),
    equipment_type: str = Query(..., description="Equipment type: chiller, ahu, etc."),
):
    """Train a global model on aggregated fleet data."""
    from ml.fleet.global_model import get_global_model_trainer

    trainer = get_global_model_trainer()
    result = trainer.train_global_model(model_type, equipment_type)

    if not result.success:
        raise HTTPException(status_code=400, detail=result.error or "Training failed")

    return {
        "success": True,
        "model_id": result.global_model_id,
        "model_type": result.model_type,
        "equipment_type": result.equipment_type,
        "sites_included": result.sites_included,
        "samples_used": result.samples_used,
        "metrics": result.metrics,
    }


@router.get("/global-models/compare")
async def compare_global_vs_local(
    model_type: str = Query(..., description="Model type"),
    equipment_type: str = Query(..., description="Equipment type"),
    local_r2: float = Query(..., description="Local model R2 score"),
):
    """Compare global model vs local model performance."""
    from ml.fleet.global_model import get_global_model_trainer

    trainer = get_global_model_trainer()
    return trainer.compare_global_vs_local(
        model_type=model_type,
        equipment_type=equipment_type,
        local_metrics={"r2_score": local_r2},
    )


@router.get("/global-models/history")
async def get_global_training_history():
    """Get global model training history."""
    from ml.fleet.global_model import get_global_model_trainer

    trainer = get_global_model_trainer()
    return {"history": trainer.get_training_history()}


# --- Fine-Tuning ---


@router.get("/fine-tuned")
async def list_fine_tuned_models(
    site_code: Optional[str] = Query(None, description="Filter by site"),
    model_type: Optional[str] = Query(None, description="Filter: lstm, autoencoder"),
    equipment_type: Optional[str] = Query(None, description="Filter: chiller, ahu, etc."),
):
    """List all fine-tuned models."""
    from ml.fleet.fine_tuning import get_local_fine_tuner

    tuner = get_local_fine_tuner()
    models = tuner.list_fine_tuned_models(
        site_code=site_code,
        model_type=model_type,
        equipment_type=equipment_type,
    )
    return {"models": models, "total": len(models)}


@router.post("/fine-tune")
async def fine_tune_model(
    site_code: str = Query(..., description="Target site (e.g., site-002)"),
    model_type: str = Query(..., description="Model type: lstm or autoencoder"),
    equipment_type: str = Query(..., description="Equipment type: chiller, ahu, etc."),
):
    """Fine-tune a global model for a specific site."""
    from ml.fleet.fine_tuning import get_local_fine_tuner

    tuner = get_local_fine_tuner()
    result = tuner.fine_tune(
        site_code=site_code,
        model_type=model_type,
        equipment_type=equipment_type,
    )

    if not result.success:
        raise HTTPException(status_code=400, detail=result.error or "Fine-tuning failed")

    return {
        "success": True,
        "model_id": result.fine_tuned_model_id,
        "site_code": result.site_code,
        "global_metrics": result.global_metrics,
        "fine_tuned_metrics": result.fine_tuned_metrics,
        "improvement": result.improvement,
        "samples_used": result.samples_used,
    }


@router.get("/fine-tuned/improvement")
async def get_improvement_summary(
    site_code: Optional[str] = Query(None, description="Filter by site"),
):
    """Get summary of fine-tuning improvements."""
    from ml.fleet.fine_tuning import get_local_fine_tuner

    tuner = get_local_fine_tuner()
    return tuner.get_improvement_summary(site_code=site_code)


@router.get("/fine-tuned/history")
async def get_fine_tune_history(
    site_code: Optional[str] = Query(None, description="Filter by site"),
):
    """Get history of fine-tuning operations."""
    from ml.fleet.fine_tuning import get_local_fine_tuner

    tuner = get_local_fine_tuner()
    return {"history": tuner.get_fine_tune_history(site_code=site_code)}
