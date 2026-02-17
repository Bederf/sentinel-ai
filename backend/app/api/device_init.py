"""Device initialization endpoints.

Initialize device status from simulation data so the dashboard
shows real-time metrics instead of all devices offline.
"""

import logging
from fastapi import APIRouter, Depends, Request
from app.middleware.auth_middleware import require_auth, AuthLevel
from app.models.auth import AuthContext
from app.services.device_status_initializer import initialize_demo_devices

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/devices", tags=["device-init"])


@router.post("/init/{site_id}")
async def init_site_devices(
    site_id: str,
    auth: AuthContext = Depends(require_auth(AuthLevel.AUTHENTICATED)),
):
    """Initialize device status for a site from simulation data.

    Called on dashboard load to populate real-time metrics from
    the 365-day simulation so devices show as online with current data.

    Args:
        site_id: Site identifier (e.g., 'site-002')
        auth: Authentication context

    Returns:
        Initialization status and device counts
    """
    try:
        result = await initialize_demo_devices(site_id)
        return {
            "status": "initialized",
            "site_id": site_id,
            "result": result,
            "user_email": auth.email,
        }
    except Exception as e:
        logger.error(f"Error initializing devices: {e}")
        return {
            "status": "error",
            "error": str(e),
            "site_id": site_id,
        }


@router.post("/init")
async def init_default_devices(
    request: Request,
    auth: AuthContext = Depends(require_auth(AuthLevel.AUTHENTICATED)),
):
    """Initialize devices for the default site (site-002).

    Convenience endpoint called on app launch or dashboard load.
    """
    try:
        result = await initialize_demo_devices("site-002")
        return {
            "status": "initialized",
            "site_id": "site-002",
            "result": result,
            "user_email": auth.email,
        }
    except Exception as e:
        logger.error(f"Error initializing default devices: {e}")
        return {
            "status": "error",
            "error": str(e),
        }
