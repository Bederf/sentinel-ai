"""Health check endpoint."""

from fastapi import APIRouter
from pydantic import BaseModel
from typing import Dict, Any

from app.config.settings import settings

router = APIRouter()


class HealthResponse(BaseModel):
    """Health check response model."""

    status: str
    version: str


class ControlHealthResponse(BaseModel):
    """Control services health check response model."""

    status: str
    version: str
    services: Dict[str, Any]


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """
    Health check endpoint.

    Returns:
        HealthResponse with status and version information.
    """
    return HealthResponse(status="ok", version=settings.app_version)


@router.get("/health/control", response_model=ControlHealthResponse)
async def control_health_check() -> ControlHealthResponse:
    """
    Control services health check endpoint.

    Checks health of device abstraction, safety interlocks, and audit logging services.

    Returns:
        ControlHealthResponse with detailed service status.
    """
    from app.services.device_abstraction import device_manager
    from app.services.safety_interlocks import safety_engine
    from app.services.audit_logger import AuditLogger

    services = {}

    # Check device manager
    try:
        devices = await device_manager.list_devices()
        services["device_abstraction"] = {
            "status": "healthy",
            "initialized": device_manager._initialized,
            "device_count": len(devices),
            "online_count": len([d for d in devices if d.status.value == "online"]),
        }
    except Exception as e:
        services["device_abstraction"] = {
            "status": "unhealthy",
            "error": str(e),
        }

    # Check safety engine
    try:
        if not safety_engine._initialized:
            await safety_engine.initialize()
        rules = await safety_engine.list_rules()
        services["safety_interlocks"] = {
            "status": "healthy",
            "initialized": safety_engine._initialized,
            "rule_count": len(rules),
            "enabled_rules": len([r for r in rules if r.enabled]),
        }
    except Exception as e:
        services["safety_interlocks"] = {
            "status": "unhealthy",
            "error": str(e),
        }

    # Check audit logger
    try:
        audit_logger = AuditLogger()
        stats = audit_logger.get_stats()
        services["audit_logging"] = {
            "status": "healthy",
            "total_entries": stats.get("total_entries", 0),
            "recent_entries": stats.get("recent_entries", 0),
        }
    except Exception as e:
        services["audit_logging"] = {
            "status": "unhealthy",
            "error": str(e),
        }

    # Determine overall status
    all_healthy = all(s.get("status") == "healthy" for s in services.values())
    overall_status = "ok" if all_healthy else "degraded"

    return ControlHealthResponse(
        status=overall_status,
        version=settings.app_version,
        services=services,
    )
