"""Simulation Analytics API - browse runs, events, and optimization profile analysis."""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.models.simulation_analytics import OptimizationProfile
from app.services.simulation_analyzer import SimulationAnalyzer

router = APIRouter(prefix="/api/simulation-analytics")
limiter = Limiter(key_func=get_remote_address)

analyzer = SimulationAnalyzer()


@router.get("/runs")
@limiter.limit("1000/minute")
async def list_runs(request: Request):
    """List all simulation runs (most recent first).

    Rate limit: 1000 requests/minute
    """
    runs = analyzer.list_runs()
    return {"runs": [r.model_dump() for r in runs], "count": len(runs)}


@router.get("/runs/{run_id}")
@limiter.limit("1000/minute")
async def get_run(request: Request, run_id: str):
    """Get metadata for a specific simulation run.

    Rate limit: 1000 requests/minute
    """
    run = analyzer.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    return run.model_dump()


@router.get("/runs/{run_id}/events")
@limiter.limit("1000/minute")
async def get_run_events(
    request: Request,
    run_id: str,
    event_type: Optional[str] = Query(None, description="Filter by event type"),
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
):
    """Read JSONL events for a simulation run with optional filtering.

    Rate limit: 1000 requests/minute (generous for data retrieval)
    """
    run = analyzer.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    events = analyzer.get_events(run_id, event_type=event_type, offset=offset, limit=limit)
    return {
        "run_id": run_id,
        "events": [e.model_dump() for e in events],
        "count": len(events),
        "offset": offset,
        "limit": limit,
    }


@router.get("/runs/{run_id}/analysis")
@limiter.limit("600/minute")
async def get_analysis(request: Request, run_id: str):
    """Get or generate analysis report for a simulation run.

    Rate limit: 600 requests/minute (slightly lower due to report generation)
    """
    run = analyzer.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    report = analyzer.get_analysis(run_id)
    if not report:
        raise HTTPException(status_code=500, detail="Failed to generate analysis")
    return report.model_dump()


@router.get("/runs/{run_id}/analysis/{profile}")
@limiter.limit("600/minute")
async def get_profile_analysis(request: Request, run_id: str, profile: str):
    """Get analysis for a specific optimization profile.

    Rate limit: 600 requests/minute
    """
    report = analyzer.get_analysis(run_id)
    if not report:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    result = report.profile_results.get(profile)
    if not result:
        available = list(report.profile_results.keys())
        raise HTTPException(
            status_code=404,
            detail=f"Profile '{profile}' not found. Available: {available}",
        )
    return result.model_dump()


class CustomProfileWeights(BaseModel):
    """Custom profile weights for re-analysis."""
    name: str = "custom"
    description: str = "Custom analysis profile"
    weights: dict = Field(description="Weight factors: runtime, comfort, cost, maintenance, energy")
    thresholds: dict = Field(default_factory=dict)


@router.post("/runs/{run_id}/analyze")
@limiter.limit("100/minute")
async def reanalyze_run(request: Request, run_id: str, profile: CustomProfileWeights):
    """Trigger re-analysis with custom profile weights.

    Rate limit: 100 requests/minute (lower due to CPU-intensive analysis)
    """
    run = analyzer.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    custom = OptimizationProfile(
        name=profile.name,
        description=profile.description,
        weights=profile.weights,
        thresholds=profile.thresholds,
    )
    report = analyzer.analyze_run(run_id, custom_profiles={"custom": custom})
    if not report:
        raise HTTPException(status_code=500, detail="Failed to generate analysis")
    return report.model_dump()


@router.get("/profiles")
@limiter.limit("1000/minute")
async def list_profiles(request: Request):
    """List available optimization profiles.

    Rate limit: 1000 requests/minute
    """
    profiles = analyzer.get_profiles()
    return {
        "profiles": {k: v.model_dump() for k, v in profiles.items()},
        "count": len(profiles),
    }
