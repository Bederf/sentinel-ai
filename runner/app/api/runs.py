"""RLM Runner API endpoints — 4 routes matching the locked contract."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException

from app.config import settings
from app.models.schemas import (
    HealthResponse,
    ResultSchema,
    RunRequest,
    RunResponse,
    TraceEntry,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Background analysis task
# ---------------------------------------------------------------------------

async def _execute_run(run_id: str, case_id: str, question: str, model: str) -> None:
    """Execute analysis in background — launched by POST /run via asyncio.create_task()."""
    from app.services.recursive_analyzer import RecursiveAnalyzer
    from app.services.run_manager import run_manager

    run_manager.update_status(run_id, "running")
    try:
        analyzer = RecursiveAnalyzer()
        result = await analyzer.analyze(case_id, question, model, run_id)
        run_manager.update_status(run_id, result.status, result.model_dump())
    except Exception as exc:
        logger.error("Run %s failed: %s", run_id, exc, exc_info=True)
        run_manager.update_status(run_id, "error", {"summary": str(exc)})
    finally:
        run_manager.unregister_task(run_id)


# ---------------------------------------------------------------------------
# POST /run — submit analysis job
# ---------------------------------------------------------------------------

@router.post("/run", response_model=RunResponse)
async def submit_run(request: RunRequest) -> RunResponse:
    """Submit a new analysis run.

    Validates model against allowlist, checks case folder exists, creates run
    via RunManager, launches analysis as background task, returns immediately.
    """
    # Lazy import to avoid circular dependency at module level
    from app.services.run_manager import run_manager

    # Validate model against allowlist
    model = request.model or settings.model_name
    if model not in settings.model_allowlist:
        raise HTTPException(
            status_code=400,
            detail=f"Model '{model}' is not in the allowlist. Allowed: {settings.model_allowlist}",
        )

    # Validate case folder exists
    case_dir = Path(settings.cases_dir) / request.case_id
    if not case_dir.is_dir():
        raise HTTPException(
            status_code=404,
            detail=f"Case '{request.case_id}' not found at {case_dir}",
        )

    # Create the run
    run_id = await run_manager.create_run(
        case_id=request.case_id,
        question=request.question,
        model=model,
    )

    # Launch analysis as background task (POST /run returns immediately)
    task = asyncio.create_task(_execute_run(run_id, request.case_id, request.question, model))
    run_manager.register_task(run_id, task)

    return RunResponse(run_id=run_id, status="queued")


# ---------------------------------------------------------------------------
# GET /runs/{run_id} — full result JSON
# ---------------------------------------------------------------------------

@router.get("/runs/{run_id}", response_model=ResultSchema)
async def get_result(run_id: str) -> ResultSchema:
    """Return the full result for a completed (or in-progress) run."""
    from app.services.run_manager import run_manager

    result = run_manager.get_result(run_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")

    return ResultSchema(**result)


# ---------------------------------------------------------------------------
# GET /runs/{run_id}/trace — trace entries
# ---------------------------------------------------------------------------

@router.get("/runs/{run_id}/trace", response_model=list[TraceEntry])
async def get_trace(run_id: str) -> list[TraceEntry]:
    """Return the trace log for a run."""
    from app.services.run_manager import run_manager

    trace = run_manager.get_trace(run_id)
    if trace is None:
        raise HTTPException(status_code=404, detail=f"Trace for run '{run_id}' not found")

    return [TraceEntry(**entry) for entry in trace]


# ---------------------------------------------------------------------------
# GET /health — health check
# ---------------------------------------------------------------------------

@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Return service health including Ollama availability.

    Checks Ollama via the OpenAI-compatible /v1 endpoint (not native /api/generate).
    """
    ollama_available = False
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{settings.model_base_url}/models")
            ollama_available = resp.status_code == 200
    except (httpx.ConnectError, httpx.TimeoutException):
        ollama_available = False
    except Exception:
        logger.warning("Unexpected error checking Ollama health", exc_info=True)
        ollama_available = False

    return HealthResponse(
        status="ok",
        version="1.0.0",
        ollama_available=ollama_available,
    )
