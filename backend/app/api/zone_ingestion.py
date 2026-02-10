"""API endpoints for building zone ingestion.

Provides endpoints for:
- Ingesting zone configurations per building
- Ingesting desk configurations per building
- Calculating and querying zone centroids
- Validating zone and desk data
"""

import logging
from typing import List, Dict, Any
from fastapi import APIRouter, HTTPException, Path
from pydantic import BaseModel, Field

from app.services.zone_ingestion_service import ZoneIngestionService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/buildings", tags=["zone-ingestion"])


# ============================================================================
# Request/Response Models
# ============================================================================


class ZoneConfig(BaseModel):
    """Zone configuration for ingestion."""

    zone_id: str = Field(..., description="Unique zone ID e.g. Zone-L1-A")
    zone_name: str = Field(..., description="Human-readable zone name")
    floor: str = Field(..., description="Floor code (L0, L1, L2, B1, G, R)")
    zone_letter: str | None = Field(None, description="Zone letter (A-E)")
    zone_type: str = Field(..., description="Type: open_office, meeting_room, plant_room, etc.")
    typical_occupancy: int | None = Field(None, description="Average occupants")
    area_sqm: float | None = Field(None, description="Area in square meters")


class ZoneIngestionRequest(BaseModel):
    """Request body for zone ingestion."""

    zones: List[ZoneConfig] = Field(..., description="List of zone configurations")


class Coordinates(BaseModel):
    """3D coordinates."""

    x: float = Field(..., description="X coordinate (horizontal)")
    y: float = Field(..., description="Y coordinate (height/floor)")
    z: float = Field(..., description="Z coordinate (depth)")


class DeskConfig(BaseModel):
    """Desk configuration for ingestion."""

    desk_id: str = Field(..., description="Unique desk ID")
    zone_id: str = Field(..., description="Zone ID this desk belongs to")
    floor: str = Field(..., description="Floor code")
    context: str = Field(
        default="open_plan",
        description="Desk context: near_diffuser, near_window, near_printer, corner, open_plan",
    )
    coordinates: Coordinates = Field(..., description="3D position of desk")


class DeskIngestionRequest(BaseModel):
    """Request body for desk ingestion."""

    desks: List[DeskConfig] = Field(..., description="List of desk configurations")


class IngestionResponse(BaseModel):
    """Response from ingestion operations."""

    status: str = Field(..., description="Operation status: success, error")
    message: str | None = Field(None, description="Optional status message")
    items_created: int | None = Field(None, description="Number of items created")


class ZoneCentroid(BaseModel):
    """Zone centroid coordinates."""

    x: float = Field(..., description="X coordinate (horizontal)")
    z: float = Field(..., description="Z coordinate (depth)")


class ZoneCentroidResponse(BaseModel):
    """Response with zone centroid."""

    zone_id: str = Field(..., description="Zone ID")
    centroid: ZoneCentroid = Field(..., description="Centroid coordinates")
    desk_count: int | None = Field(None, description="Number of desks in zone")


class AllCentroidsResponse(BaseModel):
    """Response with all zone centroids for a building."""

    building_id: str = Field(..., description="Building UUID")
    centroid_count: int = Field(..., description="Number of zones with centroids")
    centroids: Dict[str, ZoneCentroid] = Field(..., description="Map of zone_id → centroid")


# ============================================================================
# Endpoints
# ============================================================================


@router.post("/{building_id}/zone-ingestion/zones", response_model=IngestionResponse)
async def ingest_zones(
    building_id: str = Path(..., description="Building UUID"),
    request: ZoneIngestionRequest = None,
) -> IngestionResponse:
    """Ingest zone configuration for a building.

    Each building can have a unique zone structure. This endpoint validates
    and stores zone definitions for a specific building.

    **Validation:**
    - Zone IDs must be unique within building
    - Floor codes must be valid (B#, G, L#, R)
    - Zone types must be from predefined list
    - Zone letters should be A-Z or numeric

    **Example:**
    ```json
    {
      "zones": [
        {
          "zone_id": "Zone-L1-A",
          "zone_name": "Level 1 Zone A",
          "floor": "L1",
          "zone_letter": "A",
          "zone_type": "open_office",
          "typical_occupancy": 20,
          "area_sqm": 200
        }
      ]
    }
    ```

    Args:
        building_id: Building UUID
        request: Zone ingestion request with list of zones

    Returns:
        IngestionResponse with number of zones created

    Raises:
        HTTPException 400: Validation failed
        HTTPException 500: Database error
    """
    service = ZoneIngestionService()

    try:
        result = await service.ingest_zones(building_id, request.zones)
        return IngestionResponse(
            status="success",
            message=f"Ingested {result['zones_created']} zones",
            items_created=result["zones_created"],
        )
    except ValueError as e:
        logger.warning(f"Zone ingestion validation failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Zone ingestion failed: {e}")
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {e}")


@router.post("/{building_id}/zone-ingestion/desks", response_model=IngestionResponse)
async def ingest_desks(
    building_id: str = Path(..., description="Building UUID"),
    request: DeskIngestionRequest = None,
) -> IngestionResponse:
    """Ingest desk configuration for a building.

    Validates and stores desk positions with context information.
    Desks must reference zones that have already been ingested.

    **Validation:**
    - Desk IDs must be unique within building
    - Zone_id must reference existing zone
    - Floor must match zone floor
    - Coordinates must be numeric
    - Context must be valid

    **Example:**
    ```json
    {
      "desks": [
        {
          "desk_id": "1001",
          "zone_id": "Zone-L1-A",
          "floor": "L1",
          "context": "near_window",
          "coordinates": {"x": 3.5, "y": 3.5, "z": 10.5}
        }
      ]
    }
    ```

    Args:
        building_id: Building UUID
        request: Desk ingestion request with list of desks

    Returns:
        IngestionResponse with number of desks created

    Raises:
        HTTPException 400: Validation failed
        HTTPException 500: Database error
    """
    service = ZoneIngestionService()

    try:
        result = await service.ingest_desks(building_id, request.desks)
        return IngestionResponse(
            status="success",
            message=f"Ingested {result['desks_created']} desks",
            items_created=result["desks_created"],
        )
    except ValueError as e:
        logger.warning(f"Desk ingestion validation failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Desk ingestion failed: {e}")
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {e}")


@router.get(
    "/{building_id}/zone-ingestion/zones/{zone_id}/centroid",
    response_model=ZoneCentroidResponse,
)
async def get_zone_centroid(
    building_id: str = Path(..., description="Building UUID"),
    zone_id: str = Path(..., description="Zone ID (e.g., Zone-L1-A)"),
) -> ZoneCentroidResponse:
    """Get zone centroid calculated from desk positions.

    The centroid is used by the Digital Twin for accurate equipment
    positioning without loading all individual desk data.

    Args:
        building_id: Building UUID
        zone_id: Zone ID

    Returns:
        ZoneCentroidResponse with centroid coordinates

    Raises:
        HTTPException 404: Zone or desks not found
    """
    service = ZoneIngestionService()

    try:
        centroid = await service.calculate_zone_centroid(building_id, zone_id)

        if not centroid:
            raise HTTPException(
                status_code=404, detail=f"Zone {zone_id} or desks not found"
            )

        return ZoneCentroidResponse(
            zone_id=zone_id,
            centroid=ZoneCentroid(x=centroid["x"], z=centroid["z"]),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to calculate centroid for zone {zone_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Centroid calculation failed: {e}")


@router.get("/{building_id}/zone-ingestion/centroids", response_model=AllCentroidsResponse)
async def get_all_zone_centroids(
    building_id: str = Path(..., description="Building UUID"),
) -> AllCentroidsResponse:
    """Get centroids for all zones in a building.

    Efficient operation: returns pre-calculated centroids for all zones
    in a single response. Used by Digital Twin for equipment positioning.

    Args:
        building_id: Building UUID

    Returns:
        AllCentroidsResponse with map of zone_id → centroid coordinates

    Raises:
        HTTPException 500: Database error
    """
    service = ZoneIngestionService()

    try:
        centroids = await service.get_all_zone_centroids(building_id)

        return AllCentroidsResponse(
            building_id=building_id,
            centroid_count=len(centroids),
            centroids={zone_id: ZoneCentroid(**coords) for zone_id, coords in centroids.items()},
        )
    except Exception as e:
        logger.error(f"Failed to get centroids for building {building_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Centroid retrieval failed: {e}")


@router.get("/{building_id}/zone-ingestion/validate")
async def validate_zone_structure(
    building_id: str = Path(..., description="Building UUID"),
) -> Dict[str, Any]:
    """Validate zone and desk structure for a building.

    Performs consistency checks:
    - All zones have desks
    - No orphaned desks
    - Desk coordinates are reasonable
    - Consistent floor assignments

    Args:
        building_id: Building UUID

    Returns:
        Dict with validation results

    Raises:
        HTTPException 500: Database error
    """
    service = ZoneIngestionService()

    try:
        is_valid, errors = await service.validate_zone_structure(building_id)

        return {
            "building_id": building_id,
            "is_valid": is_valid,
            "errors": errors,
            "error_count": len(errors),
        }
    except Exception as e:
        logger.error(f"Failed to validate structure for building {building_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Validation failed: {e}")
