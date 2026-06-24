"""IPMVP M&V API — Measurement & Verification reporting endpoints.

Implements IPMVP 2022 Edition Volume III Chapter 5 Option C (Whole Facility)
and Option A (Retrofit Isolation) methodology.

Endpoints:
    GET  /api/ipmvp/{site_id}/report          — Full M&V report
    GET  /api/ipmvp/{site_id}/baseline         — Train baseline models only
    GET  /api/ipmvp/{site_id}/events           — Equipment events in period
    POST /api/ipmvp/{site_id}/report/option-a  — Option A for specific event
"""

import logging
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

from app.services.ipmvp import (
    BaselineModel,
    IPMVPEngine,
)
from app.services.ipmvp.site002_fetcher import Site002DataFetcher

router = APIRouter(prefix="/api/ipmvp", tags=["ipmvp"])

# ─────────────────────────────────────────────────────────────────────────────
# Request/Response models
# ─────────────────────────────────────────────────────────────────────────────


class IPMVPReportRequest(BaseModel):
    site_id: str = Field(..., description="Site identifier (e.g. site-002)")
    reporting_start: str = Field(..., description="ISO date start of reporting period")
    reporting_end: str = Field(..., description="ISO date end of reporting period")
    option: str = Field(default="C", description="C = Whole Facility, A = Retrofit Isolation")
    recommendation_id: str | None = Field(None, description="For Option A: link to specific event")
    hourly_detail: bool = Field(default=True, description="Include per-interval savings breakdown")


class BaselineRequest(BaseModel):
    site_id: str
    baseline_start: str
    baseline_end: str


class OptionARequest(BaseModel):
    site_id: str
    event_id: str
    reporting_start: str
    reporting_end: str


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _parse_dt(s: str) -> datetime:
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(400, f"Invalid date format: {s}. Use ISO format (2026-01-01)")


def _build_engine(site_id: str) -> IPMVPEngine:
    fetcher = Site002DataFetcher(site_id=site_id)
    return IPMVPEngine(site_id=site_id, fetcher=fetcher)


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/{site_id}/report")
async def get_ipmvp_report(
    site_id: str,
    reporting_start: str = Query(..., description="ISO date: 2026-01-01"),
    reporting_end: str = Query(..., description="ISO date: 2026-02-28"),
    option: str = Query("C", description="C = Whole Facility, A = Retrofit Isolation"),
    recommendation_id: str | None = Query(None),
    hourly_detail: bool = Query(True),
    baseline_cutoff: str | None = Query(
        None, description="ISO date: baseline/reporting boundary. Auto-detected from phase promotion if omitted."
    ),
):
    """Generate an IPMVP M&V report for the given site and reporting period.

    Option C: Whole Facility — uses OLS baseline regression to compute savings.
    Option A: Retrofit Isolation — compares pre/post metered periods for one event.

    baseline_cutoff: When a site enters advisory phase, this date marks the
    boundary between baseline (training) and reporting (savings measurement).
    If omitted, auto-detected from phase_transition_log where the site
    promoted from shadow_live to advisory.

    Returns uncertainty metrics (CV(RMSE)%) and flags high-uncertainty results.
    """
    start_dt = _parse_dt(reporting_start)
    end_dt = _parse_dt(reporting_end)

    if start_dt >= end_dt:
        raise HTTPException(400, "reporting_start must be before reporting_end")
    if option not in ("C", "A"):
        raise HTTPException(400, "option must be 'C' or 'A'")

    # Auto-detect baseline cutoff from phase transition log if not provided
    cutoff_dt: datetime | None = None
    if baseline_cutoff:
        cutoff_dt = _parse_dt(baseline_cutoff)
    elif option == "C":
        try:
            from app.database.supabase_client import get_supabase_client

            sb = get_supabase_client()
            phase_log = (
                sb.table("phase_transition_log")
                .select("created_at")
                .eq("site_id", site_id)
                .eq("to_phase", "advisory")
                .order("created_at", desc=True)
                .limit(1)
                .execute()
            )
            if phase_log.data:
                cutoff_dt = datetime.fromisoformat(
                    phase_log.data[0]["created_at"].isoformat()
                    if hasattr(phase_log.data[0]["created_at"], "isoformat")
                    else str(phase_log.data[0]["created_at"])
                ).replace(tzinfo=None)
                logger.info("Auto-detected baseline cutoff from advisory promotion: %s", cutoff_dt.date())
        except Exception as e:
            logger.warning("Could not auto-detect baseline cutoff for %s: %s", site_id, e)

    engine = _build_engine(site_id)

    try:
        report = await engine.run_report(
            reporting_start=start_dt,
            reporting_end=end_dt,
            option=option,
            recommendation_id=recommendation_id,
            hourly_detail=hourly_detail,
            baseline_cutoff=cutoff_dt,
        )
    except NotImplementedError as e:
        raise HTTPException(503, str(e))
    except Exception as e:
        raise HTTPException(500, f"IPMVP calculation failed: {e}")

    return report.to_dict()


@router.get("/{site_id}/baseline")
async def train_baseline_models(
    site_id: str,
    baseline_start: str = Query(..., description="ISO date start"),
    baseline_end: str = Query(..., description="ISO date end"),
):
    """Train OLS baseline models (occupied + unoccupied) without computing savings.

    Use this to validate baseline quality before running a full report.
    Returns R², CV(RMSE)%, and the baseline equation per period.
    """
    start_dt = _parse_dt(baseline_start)
    end_dt = _parse_dt(baseline_end)

    if start_dt >= end_dt:
        raise HTTPException(400, "baseline_start must be before baseline_end")

    engine = _build_engine(site_id)

    try:
        models = await engine.run_baseline_only(start_dt, end_dt)
    except NotImplementedError as e:
        raise HTTPException(503, str(e))
    except Exception as e:
        raise HTTPException(500, f"Baseline training failed: {e}")

    return {
        "site_id": site_id,
        "baseline_start": baseline_start,
        "baseline_end": baseline_end,
        "occupied": _model_to_dict(models["occupied"]),
        "unoccupied": _model_to_dict(models["unoccupied"]),
    }


@router.get("/{site_id}/events")
async def get_equipment_events(
    site_id: str,
    start: str = Query(..., description="ISO date start"),
    end: str = Query(..., description="ISO date end"),
    system_types: str | None = Query(None, description="Comma-separated: hvac,lighting,bess"),
):
    """Get equipment change events in a period for Option A isolation."""
    start_dt = _parse_dt(start)
    end_dt = _parse_dt(end)

    fetcher = Site002DataFetcher(site_id=site_id)
    types = system_types.split(",") if system_types else None

    try:
        events = await fetcher.fetch_equipment_events(start_dt, end_dt, types)
    except NotImplementedError as e:
        raise HTTPException(503, str(e))
    except Exception as e:
        raise HTTPException(500, f"Failed to fetch events: {e}")

    return {
        "site_id": site_id,
        "period_start": start,
        "period_end": end,
        "events": [e.to_dict() for e in events],
        "count": len(events),
    }


def _model_to_dict(model: BaselineModel | None) -> dict | None:
    if model is None:
        return None
    return {
        "period": model.period,
        "equation": model.equation,
        "coefficients": model.coefficients,
        "intercept": model.intercept,
        "r_squared": round(model.r_squared, 3),
        "cv_rmse_pct": model.cv_rmse_pct,
        "n_samples": model.n_samples,
    }
