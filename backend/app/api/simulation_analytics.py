"""Simulation Analytics API - browse runs, events, and optimization profile analysis."""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.models.simulation_analytics import OptimizationProfile
from app.services.simulation_analyzer import SimulationAnalyzer

router = APIRouter(prefix="/api/simulation-analytics")

analyzer = SimulationAnalyzer()


@router.get("/runs")
async def list_runs():
    """List all simulation runs (most recent first)."""
    runs = analyzer.list_runs()
    return {"runs": [r.model_dump() for r in runs], "count": len(runs)}


@router.get("/runs/{run_id}")
async def get_run(run_id: str):
    """Get metadata for a specific simulation run."""
    run = analyzer.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    return run.model_dump()


@router.get("/runs/{run_id}/events")
async def get_run_events(
    run_id: str,
    event_type: Optional[str] = Query(None, description="Filter by event type"),
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
):
    """Read JSONL events for a simulation run with optional filtering."""
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
async def get_analysis(run_id: str):
    """Get or generate analysis report for a simulation run."""
    run = analyzer.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    report = analyzer.get_analysis(run_id)
    if not report:
        raise HTTPException(status_code=500, detail="Failed to generate analysis")
    return report.model_dump()


@router.get("/runs/{run_id}/analysis/{profile}")
async def get_profile_analysis(run_id: str, profile: str):
    """Get analysis for a specific optimization profile."""
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
async def reanalyze_run(run_id: str, profile: CustomProfileWeights):
    """Trigger re-analysis with custom profile weights."""
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
async def list_profiles():
    """List available optimization profiles."""
    profiles = analyzer.get_profiles()
    return {
        "profiles": {k: v.model_dump() for k, v in profiles.items()},
        "count": len(profiles),
    }
