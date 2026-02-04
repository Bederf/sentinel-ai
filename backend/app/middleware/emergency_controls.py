"""
Emergency Controls for SENTINEL BMS Platform.

Enforces emergency system controls during incident response:
- Maintenance mode (blocks new requests, shows maintenance message)
- Read-only mode (blocks write operations - device control, configuration)
- Safety lockdown (blocks ALL device control, BMS-specific emergency)
- API shutdown (returns 503 for all API calls)

Ported from AimTheLaw emergency_controls.py, adapted for BMS context.
Added safety_lockdown mode for building emergency scenarios.

NOT registered as middleware - used as a service that can be called
from admin endpoints to activate/deactivate emergency controls.

FSR Domain: 4.11 - Incident Response (emergency access controls)
"""

import logging
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

logger = logging.getLogger("sentinel.middleware.emergency")


class EmergencyMode(str, Enum):
    """Emergency control modes."""

    NORMAL = "normal"  # Normal operation
    MAINTENANCE = "maintenance"  # Blocks new requests (planned downtime)
    READ_ONLY = "read_only"  # Blocks writes (database maintenance)
    SAFETY_LOCKDOWN = "safety_lockdown"  # Blocks device control (BMS emergency)
    API_SHUTDOWN = "api_shutdown"  # Blocks all API calls (full shutdown)


class EmergencyControlsService:
    """Service for managing emergency system controls.

    Maintains in-memory state of active emergency controls.
    Designed to be checked by middleware or individual endpoints.
    """

    def __init__(self):
        self._mode: EmergencyMode = EmergencyMode.NORMAL
        self._activated_at: Optional[datetime] = None
        self._activated_by: Optional[str] = None
        self._reason: Optional[str] = None
        self._history: List[Dict[str, Any]] = []

        # Paths that are always allowed (even during shutdown)
        self._always_allowed = {
            "/api/health",
            "/docs",
            "/redoc",
            "/openapi.json",
        }

        # Write methods that are blocked in read-only mode
        self._write_methods = {"POST", "PUT", "PATCH", "DELETE"}

        # Device control paths blocked in safety lockdown
        self._device_control_paths = [
            "/api/devices/",
            "/api/hvac/",
            "/api/optimization/analyze",
            "/api/mcp/simbiot/call",
        ]

    @property
    def mode(self) -> EmergencyMode:
        """Current emergency mode."""
        return self._mode

    @property
    def is_active(self) -> bool:
        """Whether any emergency control is active."""
        return self._mode != EmergencyMode.NORMAL

    @property
    def status(self) -> Dict[str, Any]:
        """Current emergency control status."""
        return {
            "mode": self._mode.value,
            "is_active": self.is_active,
            "activated_at": self._activated_at.isoformat() if self._activated_at else None,
            "activated_by": self._activated_by,
            "reason": self._reason,
        }

    def activate(
        self,
        mode: EmergencyMode,
        activated_by: str,
        reason: str,
    ) -> Dict[str, Any]:
        """Activate an emergency control mode.

        Args:
            mode: The emergency mode to activate
            activated_by: Who activated the control (user ID or system)
            reason: Reason for activation

        Returns:
            Status dict with activation details
        """
        old_mode = self._mode
        self._mode = mode
        self._activated_at = datetime.utcnow()
        self._activated_by = activated_by
        self._reason = reason

        # Record in history
        self._history.append({
            "action": "activate",
            "old_mode": old_mode.value,
            "new_mode": mode.value,
            "activated_by": activated_by,
            "reason": reason,
            "timestamp": self._activated_at.isoformat(),
        })

        logger.warning(
            f"Emergency control ACTIVATED: mode={mode.value} "
            f"by={activated_by} reason={reason}"
        )

        return self.status

    def deactivate(self, deactivated_by: str) -> Dict[str, Any]:
        """Deactivate emergency controls and return to normal.

        Args:
            deactivated_by: Who deactivated the control

        Returns:
            Status dict
        """
        old_mode = self._mode
        self._mode = EmergencyMode.NORMAL
        deactivated_at = datetime.utcnow()

        # Record in history
        self._history.append({
            "action": "deactivate",
            "old_mode": old_mode.value,
            "new_mode": EmergencyMode.NORMAL.value,
            "deactivated_by": deactivated_by,
            "timestamp": deactivated_at.isoformat(),
            "duration_seconds": (
                (deactivated_at - self._activated_at).total_seconds()
                if self._activated_at
                else 0
            ),
        })

        logger.info(
            f"Emergency control DEACTIVATED: was={old_mode.value} "
            f"by={deactivated_by}"
        )

        self._activated_at = None
        self._activated_by = None
        self._reason = None

        return self.status

    def get_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get emergency control activation history.

        Args:
            limit: Maximum number of entries to return

        Returns:
            List of history entries (most recent first)
        """
        return list(reversed(self._history[-limit:]))

    def check_request(self, request: Request) -> Optional[JSONResponse]:
        """Check if a request should be blocked by emergency controls.

        Args:
            request: The incoming HTTP request

        Returns:
            JSONResponse if blocked, None if allowed
        """
        path = request.url.path
        method = request.method

        # Always-allowed paths
        if path in self._always_allowed:
            return None

        # Normal mode - allow everything
        if self._mode == EmergencyMode.NORMAL:
            return None

        # API Shutdown - block everything except always-allowed
        if self._mode == EmergencyMode.API_SHUTDOWN:
            return JSONResponse(
                status_code=503,
                content={
                    "error": "Service temporarily unavailable",
                    "mode": "api_shutdown",
                    "reason": self._reason or "System maintenance in progress",
                    "retry_after": 300,
                },
                headers={"Retry-After": "300"},
            )

        # Maintenance mode - block everything except GET and always-allowed
        if self._mode == EmergencyMode.MAINTENANCE:
            if method in self._write_methods:
                return JSONResponse(
                    status_code=503,
                    content={
                        "error": "System is in maintenance mode",
                        "mode": "maintenance",
                        "reason": self._reason or "Planned maintenance in progress",
                        "retry_after": 600,
                    },
                    headers={"Retry-After": "600"},
                )

        # Read-only mode - block write methods
        if self._mode == EmergencyMode.READ_ONLY:
            if method in self._write_methods:
                return JSONResponse(
                    status_code=503,
                    content={
                        "error": "System is in read-only mode",
                        "mode": "read_only",
                        "reason": self._reason or "Write operations temporarily disabled",
                    },
                )

        # Safety lockdown - block device control paths
        if self._mode == EmergencyMode.SAFETY_LOCKDOWN:
            for control_path in self._device_control_paths:
                if path.startswith(control_path) and method in self._write_methods:
                    return JSONResponse(
                        status_code=503,
                        content={
                            "error": "Device control is locked down",
                            "mode": "safety_lockdown",
                            "reason": self._reason or "Safety lockdown active - no device control allowed",
                            "contact": "Contact building operations manager for override",
                        },
                    )

        return None


# =============================================================================
# Singleton Instance
# =============================================================================

_emergency_service: Optional[EmergencyControlsService] = None


def get_emergency_controls() -> EmergencyControlsService:
    """Get the singleton EmergencyControlsService instance."""
    global _emergency_service
    if _emergency_service is None:
        _emergency_service = EmergencyControlsService()
    return _emergency_service


# =============================================================================
# Optional Middleware (can be registered if desired)
# =============================================================================


class EmergencyControlsMiddleware(BaseHTTPMiddleware):
    """Middleware to enforce emergency system controls.

    Checks emergency status on each request and blocks or modifies
    behavior based on active emergency controls.

    Register in main.py if you want automatic enforcement:
        app.add_middleware(EmergencyControlsMiddleware)
    """

    def __init__(self, app: Callable):
        super().__init__(app)
        self.emergency_service = get_emergency_controls()
        logger.info("Emergency Controls Middleware initialized")

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process each request through emergency controls."""
        try:
            emergency_response = self.emergency_service.check_request(request)

            if emergency_response is not None:
                logger.warning(
                    f"Request blocked by emergency controls: "
                    f"{request.method} {request.url.path} "
                    f"from {request.client.host if request.client else 'unknown'} "
                    f"mode={self.emergency_service.mode.value}"
                )
                return emergency_response

            return await call_next(request)

        except Exception as e:
            logger.error(f"Error in emergency controls middleware: {e}")
            # Fail-safe: allow request to proceed on middleware error
            try:
                return await call_next(request)
            except Exception as fallback_error:
                logger.error(f"Fallback request processing failed: {fallback_error}")
                return JSONResponse(
                    status_code=500,
                    content={
                        "error": "Internal Server Error",
                        "message": "An unexpected error occurred.",
                        "timestamp": datetime.utcnow().isoformat(),
                    },
                )
