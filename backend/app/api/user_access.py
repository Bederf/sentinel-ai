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
from app.database.repositories import BuildingRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/user-access", tags=["user-access"])


# =====================================================
# Request/Response Models
# =====================================================


class GrantAccessRequest(BaseModel):
    """Request to grant building access."""
    user_email: EmailStr
    building_code: str  # e.g., 'site-002'


class RevokeAccessRequest(BaseModel):
    """Request to revoke building access."""
    user_email: EmailStr
    building_code: str


class BuildingAccessInfo(BaseModel):
    """Building access info for a user."""
    building_id: str
    building_code: str
    building_name: str
    region: Optional[str] = None
    granted_by: Optional[str] = None
    granted_at: Optional[str] = None


class UserAccessResponse(BaseModel):
    """Response with user's building access list."""
    user_email: str
    buildings: List[BuildingAccessInfo]


class BuildingUsersResponse(BaseModel):
    """Response with users who have access to a building."""
    building_code: str
    users: List[dict]


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
        building = access.get("buildings", {})
        buildings.append(BuildingAccessInfo(
            building_id=building.get("id", ""),
            building_code=building.get("code", ""),
            building_name=building.get("name", ""),
            region=building.get("region"),
            granted_by=access.get("granted_by"),
            granted_at=access.get("granted_at"),
        ))

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
        request: Grant access request with user_email and building_code

    Returns:
        Success message
    """
    # Look up building by code
    building_repo = BuildingRepository()
    building = building_repo.get_by_id(request.building_code)

    if not building:
        raise HTTPException(
            status_code=404,
            detail=f"Building '{request.building_code}' not found"
        )

    building_id = building.get("id")

    # Grant access
    access_repo = get_user_site_access_repository()
    result = access_repo.grant_access(
        user_email=request.user_email,
        building_id=building_id,
        granted_by=auth.email or auth.user_id,
    )

    if result:
        logger.info(
            f"Admin {auth.email} granted {request.user_email} "
            f"access to {request.building_code}"
        )
        return {
            "success": True,
            "message": f"Granted {request.user_email} access to {request.building_code}",
        }
    else:
        raise HTTPException(
            status_code=500,
            detail="Failed to grant access"
        )


@router.delete("/revoke")
async def revoke_access(
    request: RevokeAccessRequest,
    auth: AuthContext = Depends(require_auth(AuthLevel.ADMIN)),
):
    """Revoke a user's access to a building.

    Args:
        request: Revoke access request with user_email and building_code

    Returns:
        Success message
    """
    # Look up building by code
    building_repo = BuildingRepository()
    building = building_repo.get_by_id(request.building_code)

    if not building:
        raise HTTPException(
            status_code=404,
            detail=f"Building '{request.building_code}' not found"
        )

    building_id = building.get("id")

    # Revoke access
    access_repo = get_user_site_access_repository()
    success = access_repo.revoke_access(
        user_email=request.user_email,
        building_id=building_id,
    )

    if success:
        logger.info(
            f"Admin {auth.email} revoked {request.user_email} "
            f"access to {request.building_code}"
        )
        return {
            "success": True,
            "message": f"Revoked {request.user_email} access to {request.building_code}",
        }
    else:
        raise HTTPException(
            status_code=404,
            detail=f"No access record found for {request.user_email} to {request.building_code}"
        )


@router.get("/building/{building_code}/users", response_model=BuildingUsersResponse)
async def get_building_users(
    building_code: str,
    auth: AuthContext = Depends(require_auth(AuthLevel.ADMIN)),
):
    """Get all users with access to a building.

    Args:
        building_code: Building code (e.g., 'site-002')

    Returns:
        List of users with access
    """
    # Look up building by code
    building_repo = BuildingRepository()
    building = building_repo.get_by_id(building_code)

    if not building:
        raise HTTPException(
            status_code=404,
            detail=f"Building '{building_code}' not found"
        )

    building_id = building.get("id")

    # Get users
    access_repo = get_user_site_access_repository()
    users = access_repo.get_building_users(building_id)

    return BuildingUsersResponse(
        building_code=building_code,
        users=users,
    )
