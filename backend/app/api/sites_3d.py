"""Building 3D Configuration API Endpoints.

REST endpoints for creating, retrieving, and managing building 3D configurations
(structure + equipment placement).
"""

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.middleware.auth_middleware import require_site_access
from app.models.auth import AuthContext
from app.database.repositories.site_repository import SiteRepository
from app.services.site_3d_config_service import get_site_3d_config_service

logger = logging.getLogger(__name__)

# ============= Request/Response Models =============


class FloorDefinition(BaseModel):
    """Floor definition model."""

    level: str = Field(..., description="Floor level (e.g., B1, G, L1)")
    height: float = Field(..., ge=2.0, le=20.0, description="Floor height in meters")
    width: float = Field(..., ge=5.0, le=1000.0, description="Floor width in meters")
    depth: float = Field(..., ge=5.0, le=1000.0, description="Floor depth in meters")
    label: str = Field(..., description="Floor label (e.g., Ground Floor)")


class EquipmentPosition(BaseModel):
    """Equipment position model."""

    equipment_id: str = Field(..., description="Equipment identifier")
    floor: str = Field(..., description="Floor level")
    x: float = Field(..., description="X coordinate in meters")
    y: float = Field(..., description="Y coordinate in meters")


class BuildingStructure(BaseModel):
    """Building structure model."""

    name: str = Field(..., description="Building name")
    code: Optional[str] = Field(None, description="Building code")
    numberOfFloors: int = Field(..., ge=1, le=50, description="Number of floors")
    floors: list[FloorDefinition] = Field(..., description="Floor definitions")


class Site3DConfigRequest(BaseModel):
    """Request to create/update building 3D configuration."""

    site_structure: BuildingStructure = Field(..., description="Building structure")
    equipment_positions: list[EquipmentPosition] = Field(
        default_factory=list,
        description="Equipment positions on floors",
    )


class Site3DConfigResponse(BaseModel):
    """Response with building 3D configuration."""

    id: str = Field(..., description="Config ID")
    site_id: str = Field(..., description="Site UUID")
    site_code: str = Field(..., description="Site code")
    name: str = Field(..., description="Building name")
    code: Optional[str] = Field(None, description="Building code")
    floors: list[Dict[str, Any]] = Field(..., description="Floor definitions")
    equipment_positions: list[Dict[str, Any]] = Field(..., description="Equipment positions")
    zones: list[Dict[str, Any]] = Field(..., description="Zone definitions")
    created_at: str = Field(..., description="Creation timestamp")
    updated_at: str = Field(..., description="Update timestamp")


class Building3DViewerDataResponse(BaseModel):
    """Response with data formatted for 3D viewer."""

    site_id: str = Field(..., description="Building ID")
    site_name: str = Field(..., description="Building name")
    floors: list[Dict[str, Any]] = Field(..., description="Floor data with equipment")
    metadata: Dict[str, Any] = Field(..., description="Metadata")


# ============= Router =============

router = APIRouter(prefix="/buildings", tags=["buildings-3d"])


@router.post(
    "/{site_id}/config",
    response_model=Site3DConfigResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create or update building 3D configuration",
    responses={
        404: {"description": "Building not found"},
        400: {"description": "Validation error"},
    },
)
async def create_or_update_config(
    site_id: str,
    request: Site3DConfigRequest,
    auth: AuthContext = Depends(require_site_access("site_id")),
) -> Site3DConfigResponse:
    """Create or update 3D configuration for a building.

    Stores building structure (floors) and equipment placement data.
    Automatically infers zones from equipment positions.

    Args:
        site_id: Building UUID
        request: Configuration request with structure and positions

    Returns:
        Created/updated configuration

    Raises:
        404: If building not found
        400: If validation fails
    """
    try:
        # Verify building exists
        building_repo = SiteRepository()
        building = building_repo.get_by_uuid(site_id)
        if not building:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Building {site_id} not found",
            )

        service = get_site_3d_config_service()

        # Validate structure
        is_valid, error = service.validate_building_structure(
            {
                "name": request.site_structure.name,
                "code": request.site_structure.code,
                "numberOfFloors": request.site_structure.numberOfFloors,
                "floors": [f.model_dump() for f in request.site_structure.floors],
            }
        )
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Building structure validation failed: {error}",
            )

        # Validate equipment positions
        positions = [p.model_dump() for p in request.equipment_positions]
        is_valid, error = service.validate_equipment_positions(
            positions,
            {
                "floors": [f.model_dump() for f in request.site_structure.floors],
            },
        )
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Equipment position validation failed: {error}",
            )

        # Create or update config
        config_repo = service.repository
        existing = config_repo.get_by_site_id(site_id)

        if existing:
            # Update existing
            config = config_repo.update(
                site_id=site_id,
                floors=[f.model_dump() for f in request.site_structure.floors],
                equipment_positions=positions,
            )
            logger.info(f"✓ Updated 3D config for building {site_id}")
        else:
            # Create new
            config = config_repo.create(
                site_id=site_id,
                site_code=building.get("code", site_id),
                name=request.site_structure.name,
                code=request.site_structure.code,
                floors=[f.model_dump() for f in request.site_structure.floors],
                equipment_positions=positions,
            )
            logger.info(f"✓ Created 3D config for building {site_id}")

        if not config:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to save configuration",
            )

        return Site3DConfigResponse(
            id=str(config.get("id", "")),
            site_id=str(config.get("site_id", "")),
            site_code=config.get("site_code", ""),
            name=config.get("name", ""),
            code=config.get("code"),
            floors=config.get("floors", []),
            equipment_positions=config.get("equipment_positions", []),
            zones=config.get("zones", []),
            created_at=config.get("created_at", "").isoformat() if config.get("created_at") else "",
            updated_at=config.get("updated_at", "").isoformat() if config.get("updated_at") else "",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating 3D config: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create configuration: {str(e)}",
        )


@router.get(
    "/{site_id}/config",
    response_model=Site3DConfigResponse,
    summary="Get building 3D configuration",
    responses={404: {"description": "Configuration not found"}},
)
async def get_config(site_id: str, auth: AuthContext = Depends(require_site_access("site_id"))) -> Site3DConfigResponse:
    """Retrieve 3D configuration for a building.

    Args:
        site_id: Building UUID

    Returns:
        Configuration data

    Raises:
        404: If configuration not found
    """
    try:
        config_repo = get_site_3d_config_service().repository
        config = config_repo.get_by_site_id(site_id)

        if not config:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Configuration for building {site_id} not found",
            )

        return Site3DConfigResponse(
            id=str(config.get("id", "")),
            site_id=str(config.get("site_id", "")),
            site_code=config.get("site_code", ""),
            name=config.get("name", ""),
            code=config.get("code"),
            floors=config.get("floors", []),
            equipment_positions=config.get("equipment_positions", []),
            zones=config.get("zones", []),
            created_at=config.get("created_at", "").isoformat() if config.get("created_at") else "",
            updated_at=config.get("updated_at", "").isoformat() if config.get("updated_at") else "",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving 3D config: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve configuration: {str(e)}",
        )


@router.get(
    "/{site_id}/viewer-data",
    response_model=Building3DViewerDataResponse,
    summary="Get building 3D viewer data",
    responses={404: {"description": "Configuration not found"}},
)
async def get_viewer_data(
    site_id: str, auth: AuthContext = Depends(require_site_access("site_id"))
) -> Building3DViewerDataResponse:
    """Retrieve 3D viewer-formatted data for a building.

    Data includes floors, equipment positions, and metadata
    formatted for 3D visualization rendering.

    Args:
        site_id: Building UUID

    Returns:
        Viewer-ready data

    Raises:
        404: If configuration not found
    """
    try:
        service = get_site_3d_config_service()
        config = service.repository.get_by_site_id(site_id)

        if not config:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Configuration for building {site_id} not found",
            )

        # Generate viewer data
        viewer_data = service.generate_viewer_data(
            site_id=site_id,
            structure={
                "name": config.get("name"),
                "code": config.get("code"),
                "numberOfFloors": len(config.get("floors", [])),
                "floors": config.get("floors", []),
            },
            positions=config.get("equipment_positions", []),
            equipment_map={},  # TODO: Load from equipment repository if needed
        )

        return Building3DViewerDataResponse(
            site_id=viewer_data.get("site_id", ""),
            site_name=viewer_data.get("site_name", ""),
            floors=viewer_data.get("floors", []),
            metadata=viewer_data.get("metadata", {}),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving viewer data: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve viewer data: {str(e)}",
        )


@router.get(
    "/{site_id}/equipment-positions",
    summary="Get stored equipment positions for a building",
    responses={404: {"description": "No stored positions"}},
)
async def get_equipment_positions(
    site_id: str, auth: AuthContext = Depends(require_site_access("site_id"))
) -> Dict[str, Any]:
    """Retrieve stored equipment positions for frontend rendering.

    Returns a map of equipment_id -> {floor, x, y} for all stored positions.
    Frontend uses this to override algorithmic placement.

    Args:
        site_id: Building UUID or site code (e.g., "site-002")
    """
    try:
        config_repo = get_site_3d_config_service().repository
        config = config_repo.get_by_site_id(site_id)

        if not config or not config.get("equipment_positions"):
            return {"site_id": site_id, "positions": {}, "count": 0}

        # Convert list to map keyed by equipment_id for fast frontend lookup
        positions_map = {}
        for pos in config.get("equipment_positions", []):
            eq_id = pos.get("equipment_id")
            if eq_id:
                positions_map[eq_id] = {
                    "floor": pos.get("floor"),
                    "x": pos.get("x"),
                    "y": pos.get("y"),
                }

        return {
            "site_id": site_id,
            "positions": positions_map,
            "count": len(positions_map),
        }

    except Exception as e:
        logger.error(f"Error retrieving equipment positions: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve equipment positions: {str(e)}",
        )


@router.patch(
    "/{site_id}/equipment-positions/{equipment_id}",
    summary="Update a single equipment position",
)
async def update_equipment_position(
    site_id: str,
    equipment_id: str,
    position: EquipmentPosition,
    auth: AuthContext = Depends(require_site_access("site_id")),
) -> Dict[str, Any]:
    """Update or add a single equipment position within the 3D config.

    If no 3D config exists for the site, creates one with this position.
    If the equipment already has a stored position, updates it.

    Args:
        site_id: Building UUID or site code
        equipment_id: Equipment identifier
        position: New position (floor, x, y)
    """
    try:
        service = get_site_3d_config_service()
        config_repo = service.repository
        existing = config_repo.get_by_site_id(site_id)

        new_pos = {
            "equipment_id": equipment_id,
            "floor": position.floor,
            "x": position.x,
            "y": position.y,
        }

        if existing:
            # Update existing config — replace or append position
            positions = existing.get("equipment_positions", [])
            updated = False
            for i, pos in enumerate(positions):
                if pos.get("equipment_id") == equipment_id:
                    positions[i] = new_pos
                    updated = True
                    break
            if not updated:
                positions.append(new_pos)

            config_repo.update(
                site_id=site_id,
                equipment_positions=positions,
            )
        else:
            # Create new config with just this position
            config_repo.create(
                site_id=site_id,
                site_code=site_id,
                name=site_id,
                floors=[],
                equipment_positions=[new_pos],
            )

        logger.info(
            f"Updated position for {equipment_id} on {site_id}: floor={position.floor}, x={position.x}, y={position.y}"
        )

        return {
            "equipment_id": equipment_id,
            "floor": position.floor,
            "x": position.x,
            "y": position.y,
            "status": "saved",
        }

    except Exception as e:
        logger.error(f"Error updating equipment position: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update equipment position: {str(e)}",
        )


@router.delete(
    "/{site_id}/config",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete building 3D configuration",
)
async def delete_config(site_id: str, auth: AuthContext = Depends(require_site_access("site_id"))) -> None:
    """Delete 3D configuration for a building.

    Args:
        site_id: Building UUID
    """
    try:
        config_repo = get_site_3d_config_service().repository
        config_repo.delete(site_id)
        logger.info(f"✓ Deleted 3D config for building {site_id}")

    except Exception as e:
        logger.error(f"Error deleting 3D config: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete configuration: {str(e)}",
        )
