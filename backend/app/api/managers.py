"""
Manager Registry API
====================
CRUD for site managers who receive infrastructure alerts (e.g. data freshness breaches).
Used by the Settings UI Manager Registry panel and the notification bell system.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.database.repositories.manager_repository import get_manager_repository
from app.middleware.auth_middleware import require_role
from app.models.auth import AuthContext, SentinelRole

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/managers", tags=["managers"])


class ManagerCreate(BaseModel):
    name: str
    email: str
    phone: str | None = None
    telegram_id: str | None = None
    site_id: str | None = None
    role: str = "manager"  # manager | operator | admin
    active: bool = True


class ManagerUpdate(BaseModel):
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    telegram_id: str | None = None
    active: bool | None = None
    role: str | None = None


@router.get("")
async def list_managers(
    site_id: str | None = None,
    auth: AuthContext = Depends(require_role(SentinelRole.ADMIN, SentinelRole.OPERATOR)),
) -> dict:
    """List all managers with their site assignments."""
    repo = get_manager_repository()
    managers = await repo.get_managers(site_id=site_id)
    return {"managers": managers, "count": len(managers)}


@router.post("")
async def create_manager(
    body: ManagerCreate,
    auth: AuthContext = Depends(require_role(SentinelRole.ADMIN)),
) -> dict:
    """Create a new site manager."""
    repo = get_manager_repository()
    try:
        manager = await repo.create_manager(body.model_dump())
        return {"manager": manager, "success": True}
    except Exception as e:
        logger.error(f"Failed to create manager: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@router.patch("/{manager_id}")
async def update_manager(
    manager_id: str,
    body: ManagerUpdate,
    auth: AuthContext = Depends(require_role(SentinelRole.ADMIN)),
) -> dict:
    """Update an existing manager."""
    repo = get_manager_repository()
    try:
        manager = await repo.update_manager(manager_id, body.model_dump(exclude_unset=True))
        if not manager:
            raise HTTPException(status_code=404, detail="Manager not found")
        return {"manager": manager, "success": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update manager {manager_id}: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{manager_id}")
async def delete_manager(
    manager_id: str,
    auth: AuthContext = Depends(require_role(SentinelRole.ADMIN)),
) -> dict:
    """Deactivate a manager (soft delete)."""
    repo = get_manager_repository()
    try:
        success = await repo.deactivate_manager(manager_id)
        if not success:
            raise HTTPException(status_code=404, detail="Manager not found")
        return {"success": True, "message": "Manager deactivated"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to deactivate manager {manager_id}: {e}")
        raise HTTPException(status_code=400, detail=str(e))
