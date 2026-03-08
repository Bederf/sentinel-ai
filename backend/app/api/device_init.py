"""Device initialization endpoints.

Initialize device status from simulation data so the dashboard
shows real-time metrics instead of all devices offline.
"""

import logging
from fastapi import APIRouter, Depends, Request, HTTPException
from app.middleware.auth_middleware import require_auth, AuthLevel
from app.models.auth import AuthContext
from app.services.device_status_initializer import initialize_demo_devices
from app.core.site_resolver import get_primary_site_code
from app.database.repositories.user_site_access_repository import (
    get_user_site_access_repository,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/devices", tags=["device-init"])


@router.post("/init/{site_id}")
async def init_site_devices(
    site_id: str,
    auth: AuthContext = Depends(require_auth(AuthLevel.OPERATOR)),
):
    """Initialize device status for a site from simulation data.

    Called on dashboard load to populate real-time metrics from
    the 365-day simulation so devices show as online with current data.

    Args:
        site_id: Site identifier (e.g., 'site-002')
        auth: Authentication context (OPERATOR role required)

    Returns:
        Initialization status and device counts

    Raises:
        HTTPException: 403 if user lacks access to the site
    """
    try:
        # Verify user has access to this site (Security: Authorization check)
        site_access_repo = get_user_site_access_repository()
        has_access = site_access_repo.has_access_to_site_code(
            user_email=auth.email,
            user_role=auth.role,
            site_code=site_id,
        )

        if not has_access:
            logger.warning(f"User {auth.email} attempted to initialize devices for unauthorized site {site_id}")
            # Return consistent 403 for all unauthorized access (prevents enumeration)
            raise HTTPException(
                status_code=403,
                detail="Access denied to this site",
            )

        result = await initialize_demo_devices(site_id)
        return {
            "status": "initialized",
            "site_id": site_id,
            "result": result,
        }
    except HTTPException:
        raise  # Re-raise HTTP exceptions (403, etc.)
    except Exception as e:
        logger.error(f"Error initializing devices for {site_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail="Error initializing devices",
        )


@router.post("/init")
async def init_default_devices(
    request: Request,
    auth: AuthContext = Depends(require_auth(AuthLevel.OPERATOR)),
):
    """Initialize devices for the default site (site-002).

    Convenience endpoint called on app launch or dashboard load.

    Raises:
        HTTPException: 403 if user lacks access to the default site
    """
    try:
        site_id = get_primary_site_code() or "unknown"

        # Verify user has access to default site (Security: Authorization check)
        site_access_repo = get_user_site_access_repository()
        has_access = site_access_repo.has_access_to_site_code(
            user_email=auth.email,
            user_role=auth.role,
            site_code=site_id,
        )

        if not has_access:
            logger.warning(f"User {auth.email} attempted to initialize devices for unauthorized default site")
            # Return consistent 403 for all unauthorized access (prevents enumeration)
            raise HTTPException(
                status_code=403,
                detail="Access denied to this site",
            )

        result = await initialize_demo_devices(site_id)
        return {
            "status": "initialized",
            "site_id": site_id,
            "result": result,
        }
    except HTTPException:
        raise  # Re-raise HTTP exceptions (403, etc.)
    except Exception as e:
        logger.error(f"Error initializing default devices: {e}")
        raise HTTPException(
            status_code=500,
            detail="Error initializing devices",
        )
