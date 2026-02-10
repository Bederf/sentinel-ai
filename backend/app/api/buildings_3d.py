"""Building 3D Configuration API Endpoints.

REST endpoints for creating, retrieving, and managing building 3D configurations
(structure + equipment placement).
"""

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.database.repositories.building_repository import BuildingRepository
from app.services.building_3d_config_service import get_building_3d_config_service

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


class Building3DConfigRequest(BaseModel):
    """Request to create/update building 3D configuration."""

    building_structure: BuildingStructure = Field(..., description="Building structure")
    equipment_positions: list[EquipmentPosition] = Field(
        default_factory=list,
        description="Equipment positions on floors",
    )


class Building3DConfigResponse(BaseModel):
    """Response with building 3D configuration."""

    id: str = Field(..., description="Config ID")
    building_id: str = Field(..., description="Building ID")
    site_id: str = Field(..., description="Site ID")
    name: str = Field(..., description="Building name")
    code: Optional[str] = Field(None, description="Building code")
    floors: list[Dict[str, Any]] = Field(..., description="Floor definitions")
    equipment_positions: list[Dict[str, Any]] = Field(..., description="Equipment positions")
    zones: list[Dict[str, Any]] = Field(..., description="Zone definitions")
    created_at: str = Field(..., description="Creation timestamp")
    updated_at: str = Field(..., description="Update timestamp")


class Building3DViewerDataResponse(BaseModel):
    """Response with data formatted for 3D viewer."""

    building_id: str = Field(..., description="Building ID")
    building_name: str = Field(..., description="Building name")
    floors: list[Dict[str, Any]] = Field(..., description="Floor data with equipment")
    metadata: Dict[str, Any] = Field(..., description="Metadata")


# ============= Router =============

router = APIRouter(prefix="/buildings", tags=["buildings-3d"])


@router.post(
    "/{building_id}/config",
    response_model=Building3DConfigResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create or update building 3D configuration",
    responses={
        404: {"description": "Building not found"},
        400: {"description": "Validation error"},
    },
)
async def create_or_update_config(
    building_id: str,
    request: Building3DConfigRequest,
) -> Building3DConfigResponse:
    """Create or update 3D configuration for a building.

    Stores building structure (floors) and equipment placement data.
    Automatically infers zones from equipment positions.

    Args:
        building_id: Building UUID
        request: Configuration request with structure and positions

    Returns:
        Created/updated configuration

    Raises:
        404: If building not found
        400: If validation fails
    """
    try:
        # Verify building exists
        building_repo = BuildingRepository()
        building = building_repo.get_by_uuid(building_id)
        if not building:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Building {building_id} not found",
            )

        service = get_building_3d_config_service()

        # Validate structure
        is_valid, error = service.validate_building_structure(
            {
                "name": request.building_structure.name,
                "code": request.building_structure.code,
                "numberOfFloors": request.building_structure.numberOfFloors,
                "floors": [f.model_dump() for f in request.building_structure.floors],
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
                "floors": [f.model_dump() for f in request.building_structure.floors],
            },
        )
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Equipment position validation failed: {error}",
            )

        # Create or update config
        config_repo = service.repository
        existing = config_repo.get_by_building_id(building_id)

        if existing:
            # Update existing
            config = config_repo.update(
                building_id=building_id,
                floors=[f.model_dump() for f in request.building_structure.floors],
                equipment_positions=positions,
            )
            logger.info(f"✓ Updated 3D config for building {building_id}")
        else:
            # Create new
            config = config_repo.create(
                building_id=building_id,
                site_id=building.get("code", building_id),
                name=request.building_structure.name,
                code=request.building_structure.code,
                floors=[f.model_dump() for f in request.building_structure.floors],
                equipment_positions=positions,
            )
            logger.info(f"✓ Created 3D config for building {building_id}")

        if not config:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to save configuration",
            )

        return Building3DConfigResponse(
            id=str(config.get("id", "")),
            building_id=str(config.get("building_id", "")),
            site_id=config.get("site_id", ""),
            name=config.get("name", ""),
            code=config.get("code"),
            floors=config.get("floors", []),
            equipment_positions=config.get("equipment_positions", []),
            zones=config.get("zones", []),
            created_at=config.get("created_at", "").isoformat()
            if config.get("created_at")
            else "",
            updated_at=config.get("updated_at", "").isoformat()
            if config.get("updated_at")
            else "",
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
    "/{building_id}/config",
    response_model=Building3DConfigResponse,
    summary="Get building 3D configuration",
    responses={404: {"description": "Configuration not found"}},
)
async def get_config(building_id: str) -> Building3DConfigResponse:
    """Retrieve 3D configuration for a building.

    Args:
        building_id: Building UUID

    Returns:
        Configuration data

    Raises:
        404: If configuration not found
    """
    try:
        config_repo = get_building_3d_config_service().repository
        config = config_repo.get_by_building_id(building_id)

        if not config:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Configuration for building {building_id} not found",
            )

        return Building3DConfigResponse(
            id=str(config.get("id", "")),
            building_id=str(config.get("building_id", "")),
            site_id=config.get("site_id", ""),
            name=config.get("name", ""),
            code=config.get("code"),
            floors=config.get("floors", []),
            equipment_positions=config.get("equipment_positions", []),
            zones=config.get("zones", []),
            created_at=config.get("created_at", "").isoformat()
            if config.get("created_at")
            else "",
            updated_at=config.get("updated_at", "").isoformat()
            if config.get("updated_at")
            else "",
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
    "/{building_id}/viewer-data",
    response_model=Building3DViewerDataResponse,
    summary="Get building 3D viewer data",
    responses={404: {"description": "Configuration not found"}},
)
async def get_viewer_data(building_id: str) -> Building3DViewerDataResponse:
    """Retrieve 3D viewer-formatted data for a building.

    Data includes floors, equipment positions, and metadata
    formatted for 3D visualization rendering.

    Args:
        building_id: Building UUID

    Returns:
        Viewer-ready data

    Raises:
        404: If configuration not found
    """
    try:
        service = get_building_3d_config_service()
        config = service.repository.get_by_building_id(building_id)

        if not config:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Configuration for building {building_id} not found",
            )

        # Generate viewer data
        viewer_data = service.generate_viewer_data(
            building_id=building_id,
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
            building_id=viewer_data.get("building_id", ""),
            building_name=viewer_data.get("building_name", ""),
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


@router.delete(
    "/{building_id}/config",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete building 3D configuration",
)
async def delete_config(building_id: str) -> None:
    """Delete 3D configuration for a building.

    Args:
        building_id: Building UUID
    """
    try:
        config_repo = get_building_3d_config_service().repository
        config_repo.delete(building_id)
        logger.info(f"✓ Deleted 3D config for building {building_id}")

    except Exception as e:
        logger.error(f"Error deleting 3D config: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete configuration: {str(e)}",
        )
