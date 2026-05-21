"""
Site Profiles API — Phase 191 Wave 1.

POST /api/site-profiles/{site_id}         — create/update profile (201)
GET  /api/site-profiles/{site_id}          — get profile (404 if absent)
GET  /api/site-profiles/{site_id}/status  — lightweight gate check
"""

import logging

from fastapi import APIRouter, Depends, HTTPException

from app.middleware.auth_middleware import require_auth
from app.models.auth import AuthContext, AuthLevel
from app.models.site_profile import SiteProfileCreate, SiteProfileResponse, SiteProfileStatus
from app.services.site_profile_service import SiteProfileService

logger = logging.getLogger("sentinel.site_profiles_api")

router = APIRouter(prefix="/api/site-profiles", tags=["site-profiles"])


def _get_service() -> SiteProfileService:
    return SiteProfileService()


@router.post("/{site_id}", response_model=SiteProfileResponse, status_code=201)
async def create_or_update_profile(
    site_id: str,
    payload: SiteProfileCreate,
    auth: AuthContext = Depends(require_auth(AuthLevel.AUTHENTICATED)),
) -> SiteProfileResponse:
    """Create or update a building profile for a site.

    Idempotent — re-submission updates the existing profile.
    confirmed_at and confirmed_by are set on every call.
    """
    service = _get_service()
    try:
        row = service.create_profile(
            site_id=site_id,
            payload=payload,
            confirmed_by=auth.email or "system",
        )
        return SiteProfileResponse(**row)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Profile create/update failed for {site_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{site_id}", response_model=SiteProfileResponse)
async def get_profile(
    site_id: str,
    auth: AuthContext = Depends(require_auth(AuthLevel.AUTHENTICATED)),
) -> SiteProfileResponse:
    """Retrieve the building profile for a site. Returns 404 if not yet profiled."""
    service = _get_service()
    row = service.get_profile(site_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"No profile found for site {site_id}")
    return SiteProfileResponse(**row)


@router.get("/{site_id}/status", response_model=SiteProfileStatus)
async def get_profile_status(
    site_id: str,
    auth: AuthContext = Depends(require_auth(AuthLevel.AUTHENTICATED)),
) -> SiteProfileStatus:
    """Lightweight endpoint to check if a site has a confirmed profile.

    Used by the phase transition gate in sites.py to determine whether
    a site can advance to shadow or advisory mode.
    """
    service = _get_service()
    has_confirmed = service.has_confirmed_profile(site_id)
    profile = service.get_profile(site_id) if has_confirmed else None
    return SiteProfileStatus(
        site_id=site_id,
        has_profile=has_confirmed,
        confirmed_at=profile.get("confirmed_at") if profile else None,
    )
