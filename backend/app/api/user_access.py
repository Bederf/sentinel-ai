"""
User Access Management API - Admin endpoints for managing building access.

ADMIN-only endpoints to grant/revoke user access to buildings.
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr

from app.middleware.auth_middleware import require_auth
from app.models.auth import AuthContext, AuthLevel, SentinelRole
from app.database.repositories.user_site_access_repository import (
    get_user_site_access_repository,
)
from app.database.repositories.module_access_repository import get_module_access_repository
from app.database.repositories import SiteRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/user-access", tags=["user-access"])
self_service_router = APIRouter(prefix="/api/user-access", tags=["user-access"])


# =====================================================
# Request/Response Models
# =====================================================


class GrantAccessRequest(BaseModel):
    """Request to grant building access."""

    user_email: EmailStr
    site_code: str  # e.g., 'site-002'


class RevokeAccessRequest(BaseModel):
    """Request to revoke building access."""

    user_email: EmailStr
    site_code: str


class BuildingAccessInfo(BaseModel):
    """Building access info for a user."""

    site_id: str
    site_code: str
    site_name: str
    region: Optional[str] = None
    granted_by: Optional[str] = None
    granted_at: Optional[str] = None


class UserAccessResponse(BaseModel):
    """Response with user's building access list."""

    user_email: str
    buildings: List[BuildingAccessInfo]


class BuildingUsersResponse(BaseModel):
    """Response with users who have access to a building."""

    site_code: str
    users: List[dict]


class ModuleGrantRequest(BaseModel):
    """Admin request to set module grants for a user and site."""

    user_email: EmailStr
    site_code: str
    modules: List[str]


class AccessRequestDecisionRequest(BaseModel):
    """Admin approval/rejection decision for a pending access request."""

    approve: bool = True
    granted_modules: Optional[List[str]] = None
    review_notes: Optional[str] = None


# =====================================================
# Endpoints
# =====================================================


@router.get("/users/{email}", response_model=UserAccessResponse)
async def get_user_buildings(
    email: str,
    auth: AuthContext = Depends(require_auth(AuthLevel.ADMIN)),
):
    """Get all buildings a user has access to.

    Args:
        email: User's email address

    Returns:
        List of buildings the user can access
    """
    repo = get_user_site_access_repository()
    access_list = repo.get_user_access_list(email)

    buildings = []
    for access in access_list:
        building = access.get("sites", {})
        buildings.append(
            BuildingAccessInfo(
                site_id=building.get("id", ""),
                site_code=building.get("code", ""),
                site_name=building.get("name", ""),
                region=building.get("region"),
                granted_by=access.get("granted_by"),
                granted_at=access.get("granted_at"),
            )
        )

    return UserAccessResponse(
        user_email=email.lower(),
        buildings=buildings,
    )


@router.post("/grant")
async def grant_access(
    request: GrantAccessRequest,
    auth: AuthContext = Depends(require_auth(AuthLevel.ADMIN)),
):
    """Grant a user access to a building.

    Args:
        request: Grant access request with user_email and site_code

    Returns:
        Success message
    """
    # Look up building by code
    building_repo = SiteRepository()
    building = building_repo.get_by_id(request.site_code)

    if not building:
        raise HTTPException(status_code=404, detail=f"Building '{request.site_code}' not found")

    site_id = building.get("id")

    # Grant access
    access_repo = get_user_site_access_repository()
    result = access_repo.grant_access(
        user_email=request.user_email,
        site_id=site_id,
        granted_by=auth.email or auth.user_id,
    )

    if result:
        logger.info(f"Admin {auth.email} granted {request.user_email} access to {request.site_code}")
        return {
            "success": True,
            "message": f"Granted {request.user_email} access to {request.site_code}",
        }
    else:
        raise HTTPException(status_code=500, detail="Failed to grant access")


@router.delete("/revoke")
async def revoke_access(
    request: RevokeAccessRequest,
    auth: AuthContext = Depends(require_auth(AuthLevel.ADMIN)),
):
    """Revoke a user's access to a building.

    Args:
        request: Revoke access request with user_email and site_code

    Returns:
        Success message
    """
    # Look up building by code
    building_repo = SiteRepository()
    building = building_repo.get_by_id(request.site_code)

    if not building:
        raise HTTPException(status_code=404, detail=f"Building '{request.site_code}' not found")

    site_id = building.get("id")

    # Revoke access
    access_repo = get_user_site_access_repository()
    success = access_repo.revoke_access(
        user_email=request.user_email,
        site_id=site_id,
    )

    if success:
        logger.info(f"Admin {auth.email} revoked {request.user_email} access to {request.site_code}")
        return {
            "success": True,
            "message": f"Revoked {request.user_email} access to {request.site_code}",
        }
    else:
        raise HTTPException(
            status_code=404, detail=f"No access record found for {request.user_email} to {request.site_code}"
        )


@router.get("/building/{site_code}/users", response_model=BuildingUsersResponse)
async def get_building_users(
    site_code: str,
    auth: AuthContext = Depends(require_auth(AuthLevel.ADMIN)),
):
    """Get all users with access to a building.

    Args:
        site_code: Building code (e.g., 'site-002')

    Returns:
        List of users with access
    """
    # Look up building by code
    building_repo = SiteRepository()
    building = building_repo.get_by_id(site_code)

    if not building:
        raise HTTPException(status_code=404, detail=f"Building '{site_code}' not found")

    site_id = building.get("id")

    # Get users
    access_repo = get_user_site_access_repository()
    users = access_repo.get_building_users(site_id)

    return BuildingUsersResponse(
        site_code=site_code,
        users=users,
    )


@router.get("/requests")
async def list_access_requests(
    status: Optional[str] = None,
    auth: AuthContext = Depends(require_auth(AuthLevel.ADMIN)),
):
    """List module access requests submitted from the frontend."""
    repo = get_module_access_repository()
    requests = repo.list_access_requests(status=status)
    return {
        "count": len(requests),
        "requests": requests,
    }


@router.post("/requests/{request_id}/decision")
async def decide_access_request(
    request_id: str,
    decision: AccessRequestDecisionRequest,
    auth: AuthContext = Depends(require_auth(AuthLevel.ADMIN)),
):
    """Approve or reject a pending access request and assign modules."""
    module_repo = get_module_access_repository()
    access_request = module_repo.get_access_request(request_id)
    if not access_request:
        raise HTTPException(status_code=404, detail="Access request not found")

    user_email = access_request.get("user_email", "").strip().lower()
    site_code = access_request.get("site_code", "").strip().lower()
    if not user_email or not site_code:
        raise HTTPException(status_code=400, detail="Access request is missing required fields")

    reviewer = auth.email or auth.user_id
    if decision.approve:
        granted_modules = decision.granted_modules or access_request.get("requested_modules", [])

        # Ensure user can access the site itself
        building_repo = SiteRepository()
        building = building_repo.get_by_id(site_code)
        if not building:
            raise HTTPException(status_code=404, detail=f"Building '{site_code}' not found")

        access_repo = get_user_site_access_repository()
        access_repo.grant_access(
            user_email=user_email,
            site_id=building.get("id"),
            granted_by=reviewer,
        )

        if not module_repo.set_user_modules(
            user_email=user_email,
            site_code=site_code,
            module_types=granted_modules,
            granted_by=reviewer,
            replace_existing=False,
        ):
            raise HTTPException(status_code=500, detail="Failed to grant module access")

        updated = module_repo.set_access_request_decision(
            request_id=request_id,
            status="approved",
            reviewed_by=reviewer,
            review_notes=decision.review_notes,
            granted_modules=granted_modules,
        )
        if not updated:
            raise HTTPException(status_code=500, detail="Failed to update access request status")

        return {
            "success": True,
            "status": "approved",
            "request_id": request_id,
            "user_email": user_email,
            "site_code": site_code,
            "granted_modules": granted_modules,
        }

    updated = module_repo.set_access_request_decision(
        request_id=request_id,
        status="rejected",
        reviewed_by=reviewer,
        review_notes=decision.review_notes,
        granted_modules=[],
    )
    if not updated:
        raise HTTPException(status_code=500, detail="Failed to update access request status")
    return {
        "success": True,
        "status": "rejected",
        "request_id": request_id,
        "user_email": user_email,
        "site_code": site_code,
    }


@router.post("/module-grants")
async def set_user_module_grants(
    request: ModuleGrantRequest,
    auth: AuthContext = Depends(require_auth(AuthLevel.ADMIN)),
):
    """Set module grants for a user at a given site."""
    reviewer = auth.email or auth.user_id
    site_code = request.site_code.strip().lower()
    user_email = request.user_email.strip().lower()

    # Ensure building access exists
    building_repo = SiteRepository()
    building = building_repo.get_by_id(site_code)
    if not building:
        raise HTTPException(status_code=404, detail=f"Building '{site_code}' not found")

    access_repo = get_user_site_access_repository()
    access_repo.grant_access(
        user_email=user_email,
        site_id=building.get("id"),
        granted_by=reviewer,
    )

    module_repo = get_module_access_repository()
    ok = module_repo.set_user_modules(
        user_email=user_email,
        site_code=site_code,
        module_types=request.modules,
        granted_by=reviewer,
        replace_existing=True,
    )
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to save module grants")

    effective = module_repo.get_effective_modules(
        user_email=user_email,
        user_role=SentinelRole.AUDITOR,
        site_code=site_code,
    )
    return {
        "success": True,
        "user_email": user_email,
        "site_code": site_code,
        "effective_modules": effective,
    }


@router.get("/module-grants/{email}")
async def get_user_module_grants(
    email: str,
    site_code: str,
    auth: AuthContext = Depends(require_auth(AuthLevel.ADMIN)),
):
    """Get explicit and effective module grants for a user/site."""
    user_email = email.strip().lower()
    normalized_site = site_code.strip().lower()
    module_repo = get_module_access_repository()
    explicit = module_repo.get_user_modules(user_email=user_email, site_code=normalized_site)
    effective = module_repo.get_effective_modules(
        user_email=user_email,
        user_role=SentinelRole.AUDITOR,
        site_code=normalized_site,
    )
    return {
        "user_email": user_email,
        "site_code": normalized_site,
        "explicit_modules": explicit,
        "effective_modules": effective,
    }


@self_service_router.get("/me/modules")
async def get_my_effective_modules(
    site_code: str,
    auth: AuthContext = Depends(require_auth(AuthLevel.AUTHENTICATED)),
):
    """Get effective module access for the current user/site."""
    module_repo = get_module_access_repository()
    effective = module_repo.get_effective_modules(
        user_email=auth.email,
        user_role=auth.role,
        site_code=site_code.strip().lower(),
    )
    return {
        "user_email": auth.email,
        "site_code": site_code.strip().lower(),
        "role": auth.role.value,
        "effective_modules": effective,
    }
