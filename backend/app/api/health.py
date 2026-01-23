"""Health check endpoint."""

from fastapi import APIRouter
from pydantic import BaseModel

from app.config.settings import settings

router = APIRouter()


class HealthResponse(BaseModel):
    """Health check response model."""

    status: str
    version: str


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """
    Health check endpoint.

    Returns:
        HealthResponse with status and version information.
    """
    return HealthResponse(status="ok", version=settings.app_version)
