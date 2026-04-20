"""RLM Orchestration API Router.

Exposes the RLM runner to the Sentinel frontend via /api/rlm/* endpoints.
All endpoints require authentication. Feature-gated behind RLM_RUNNER_ENABLED.

See: docs/02-architecture/SENTINEL-RLM-ARCHITECTURE-SPEC-v1.0.md Section 5
Phase: 113-03
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.config.settings import settings
from app.middleware.auth_middleware import require_auth
from app.models.auth import AuthContext
from app.services.rlm_runner_client import (
    RLMRunnerDisabledError,
    RLMRunnerUnavailableError,
    get_rlm_runner_client,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/rlm", tags=["rlm"])


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class AnalyseRequest(BaseModel):
    """Request body for POST /api/rlm/cases/{case_id}/analyse."""

    question: str = Field(..., min_length=1, max_length=2000)
    model: str | None = Field(default=None, max_length=100)


class AnalyseResponse(BaseModel):
    """Response for a submitted analysis run."""

    run_id: str
    status: str


class HealthResponse(BaseModel):
    """Response for /api/rlm/health."""

    enabled: bool
    runner_available: bool


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/cases/{case_id}/analyse",
    response_model=AnalyseResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit a case for RLM analysis",
)
async def analyse_case(
    case_id: str,
    body: AnalyseRequest,
    auth: AuthContext = Depends(require_auth),
) -> AnalyseResponse:
    """Submit an evidence case to the RLM runner for analysis.

    Returns 202 Accepted with the run_id for polling.
    Returns 409 if RLM_RUNNER_ENABLED is False.
    Returns 503 if the runner cannot be reached.
    """
    client = get_rlm_runner_client()
    try:
        result = await client.submit_run(
            case_id=case_id,
            question=body.question,
            model=body.model,
        )
        return AnalyseResponse(
            run_id=result["run_id"],
            status=result.get("status", "queued"),
        )
    except RLMRunnerDisabledError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="RLM Runner is not enabled. Set RLM_RUNNER_ENABLED=true.",
        )
    except RLMRunnerUnavailableError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="RLM Runner is unavailable.",
        )


@router.get(
    "/runs/{run_id}",
    summary="Get result for an RLM run",
)
async def get_run_result(
    run_id: str,
    auth: AuthContext = Depends(require_auth),
):
    """Proxy to runner GET /runs/{run_id}. Returns full result dict."""
    client = get_rlm_runner_client()
    try:
        result = await client.get_result(run_id)
    except RLMRunnerDisabledError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="RLM Runner is not enabled.",
        )
    except RLMRunnerUnavailableError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="RLM Runner is unavailable.",
        )
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run {run_id} not found.",
        )
    return result


@router.get(
    "/runs/{run_id}/trace",
    summary="Get trace for an RLM run",
)
async def get_run_trace(
    run_id: str,
    auth: AuthContext = Depends(require_auth),
):
    """Proxy to runner GET /runs/{run_id}/trace. Returns trace list."""
    client = get_rlm_runner_client()
    try:
        trace = await client.get_trace(run_id)
    except RLMRunnerDisabledError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="RLM Runner is not enabled.",
        )
    except RLMRunnerUnavailableError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="RLM Runner is unavailable.",
        )
    if trace is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Trace for run {run_id} not found.",
        )
    return trace


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="RLM runner health status",
)
async def rlm_health(
    auth: AuthContext = Depends(require_auth),
) -> HealthResponse:
    """Return runner health status and enabled flag."""
    client = get_rlm_runner_client()
    runner_available = False
    if settings.rlm_runner_enabled:
        runner_available = await client.is_available()
    return HealthResponse(
        enabled=settings.rlm_runner_enabled,
        runner_available=runner_available,
    )
