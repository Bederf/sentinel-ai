"""RLM Runner — FastAPI application entry point."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.runs import router as runs_router
from app.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lifespan (startup / shutdown)
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    # Startup
    logger.info(
        "RLM Runner starting — host=%s port=%d env=%s cases=%s output=%s",
        settings.host,
        settings.port,
        settings.environment,
        settings.cases_dir,
        settings.output_dir,
    )
    # Ensure output directory exists
    Path(settings.output_dir).mkdir(parents=True, exist_ok=True)
    yield
    # Shutdown
    logger.info("RLM Runner shutting down")


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------

app = FastAPI(
    title="RLM Runner",
    version="1.0.0",
    description="Recursive Language Model analysis service for SENTINEL",
    lifespan=lifespan,
)

# CORS — allow only localhost origins (runner is localhost-only)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:9095",
        "http://127.0.0.1:9095",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routes
app.include_router(runs_router)
