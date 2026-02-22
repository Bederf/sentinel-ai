"""API endpoints for desk data queries.

Provides endpoints for:
- Querying desk data by building, floor, or zone
- Retrieving zone centroids (for Digital Twin positioning)
- Accessing desk position and context information
"""

import logging
import re
from typing import List, Dict, Optional, Any
from fastapi import APIRouter, HTTPException, Path, Query

from app.database.repositories.desk_repository import DeskRepository
from app.database.repositories.zone_repository import ZoneRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/buildings", tags=["desks"])


# ============================================================================
# Helper Functions
# ============================================================================


def _is_uuid(value: str) -> bool:
    """Check if value is a valid UUID format.

    Args:
        value: String to check

    Returns:
        True if value matches UUID format (8-4-4-4-12 hex pattern)
    """
    uuid_pattern = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE)
    return bool(uuid_pattern.match(value))


# ============================================================================
# Response Models
# ============================================================================


class DeskResponse(dict):
    """Desk data response."""

    pass


class ZoneCentroidData(dict):
    """Zone centroid data."""

    pass


class CentroidsMapResponse(dict):
    """Map of zone centroids."""

    pass


# ============================================================================
# Endpoints
# ============================================================================


@router.get("/{building_id}/desks")
async def get_desks(
    building_id: str = Path(..., description="Building UUID or code (e.g., 'site-002' or UUID)"),
    floor: Optional[str] = Query(None, description="Optional floor filter (L0, L1, L2, etc.)"),
) -> List[Dict[str, Any]]:
    """Get desk data for a building.

    Optionally filtered by floor. Returns all desks with their positions,
    zone assignments, and context information.

    **Query Parameters:**
    - `floor`: Filter to specific floor (e.g., "L1")

    **Example Response:**
    ```json
    [
      {
        "id": "uuid-1",
        "desk_id": "1001",
        "zone_id": "Zone-L1-A",
        "floor": "L1",
        "context": "near_window",
        "x_coord": 3.5,
        "y_coord": 3.5,
        "z_coord": 10.5
      }
    ]
    ```

    Args:
        building_id: Building UUID or code (accepts both formats for flexibility)
        floor: Optional floor code

    Returns:
        List of desk records

    Raises:
        HTTPException 500: Database error
    """
    desk_repo = DeskRepository()

    try:
        # Accept both building codes and UUIDs
        actual_building_id = building_id

        # If it looks like a building code (not UUID format), convert it to UUID
        if not _is_uuid(building_id):
            try:
                actual_building_id = desk_repo.get_building_uuid(building_id)
                if not actual_building_id:
                    logger.warning(f"Building not found for code: {building_id}")
                    # Return empty list if building not found
                    return []
            except Exception as e:
                logger.warning(f"Failed to resolve building code '{building_id}' to UUID: {e}")
                actual_building_id = building_id

        desks = desk_repo.get_by_building_uuid(actual_building_id)

        if floor:
            desks = [d for d in desks if d.get("floor") == floor]

        logger.info(
            f"Retrieved {len(desks)} desks for building {building_id} (UUID: {actual_building_id}) floor {floor or 'any'}"
        )
        return desks
    except Exception as e:
        logger.error(f"Failed to get desks for building {building_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve desks: {e}")


@router.get("/{building_id}/desks/zones/{zone_id}")
async def get_desks_by_zone(
    building_id: str = Path(..., description="Building UUID or code (e.g., 'site-002' or UUID)"),
    zone_id: str = Path(..., description="Zone ID (e.g., Zone-L1-A)"),
) -> List[Dict[str, Any]]:
    """Get all desks in a specific zone.

    Returns all desks for a given zone with their positions and context.

    Args:
        building_id: Building UUID or code (accepts both formats for flexibility)
        zone_id: Zone ID

    Returns:
        List of desk records in the zone

    Raises:
        HTTPException 500: Database error
    """
    desk_repo = DeskRepository()

    try:
        # Accept both building codes and UUIDs
        actual_building_id = building_id

        # If it looks like a building code (not UUID format), convert it to UUID
        if not _is_uuid(building_id):
            try:
                actual_building_id = desk_repo.get_building_uuid(building_id)
                if not actual_building_id:
                    logger.warning(f"Building not found for code: {building_id}")
                    return []
            except Exception as e:
                logger.warning(f"Failed to resolve building code '{building_id}' to UUID: {e}")
                actual_building_id = building_id

        desks = desk_repo.get_by_zone_id(actual_building_id, zone_id)

        logger.info(
            f"Retrieved {len(desks)} desks for zone {zone_id} in building {building_id} (UUID: {actual_building_id})"
        )
        return desks
    except Exception as e:
        logger.error(f"Failed to get desks for zone {zone_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve desks: {e}")


@router.get("/{building_id}/desks/zones/{zone_id}/centroid")
async def get_zone_centroid(
    building_id: str = Path(..., description="Building UUID or code (e.g., 'site-002' or UUID)"),
    zone_id: str = Path(..., description="Zone ID (e.g., Zone-L1-A)"),
) -> Dict[str, Any]:
    """Get centroid for a specific zone.

    The centroid is the average X, Z position of all desks in the zone.
    Used by Digital Twin for accurate equipment positioning.

    **Example Response:**
    ```json
    {
      "zone_id": "Zone-L1-A",
      "centroid": {"x": 3.5, "z": 10.5},
      "desk_count": 20
    }
    ```

    Args:
        building_id: Building UUID or code (accepts both formats for flexibility)
        zone_id: Zone ID

    Returns:
        Dict with zone_id, centroid coordinates, and desk count

    Raises:
        HTTPException 404: Zone or desks not found
        HTTPException 500: Database error
    """
    desk_repo = DeskRepository()

    try:
        # Accept both building codes and UUIDs
        actual_building_id = building_id

        # If it looks like a building code (not UUID format), convert it to UUID
        if not _is_uuid(building_id):
            try:
                actual_building_id = desk_repo.get_building_uuid(building_id)
                if not actual_building_id:
                    logger.warning(f"Building not found for code: {building_id}")
                    raise HTTPException(status_code=404, detail=f"Building not found: {building_id}")
            except HTTPException:
                raise
            except Exception as e:
                logger.warning(f"Failed to resolve building code '{building_id}' to UUID: {e}")
                actual_building_id = building_id

        desks = desk_repo.get_by_zone_id(actual_building_id, zone_id)

        if not desks:
            logger.warning(f"No desks found for zone {zone_id}")
            raise HTTPException(status_code=404, detail=f"No desks found for zone: {zone_id}")

        avg_x = sum(float(d.get("x_coord", 0)) for d in desks) / len(desks)
        avg_z = sum(float(d.get("z_coord", 0)) for d in desks) / len(desks)

        return {
            "zone_id": zone_id,
            "centroid": {"x": round(avg_x, 2), "z": round(avg_z, 2)},
            "desk_count": len(desks),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to calculate centroid for zone {zone_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Centroid calculation failed: {e}")


@router.get("/{building_id}/desks/centroids")
async def get_all_zone_centroids(
    building_id: str = Path(..., description="Building UUID or code (e.g., 'site-002' or UUID)"),
) -> Dict[str, Any]:
    """Get centroids for all zones in a building.

    Efficient operation: returns pre-calculated centroids for all zones.
    Ideal for Digital Twin initialization to avoid loading all desk data.

    **Performance:** ~80x smaller payload than loading all desks.

    **Example Response:**
    ```json
    {
      "building_id": "uuid",
      "zone_count": 15,
      "centroids": {
        "Zone-L1-A": {"x": 3.5, "z": 10.5},
        "Zone-L1-B": {"x": 9.5, "z": 10.5},
        ...
      }
    }
    ```

    Args:
        building_id: Building UUID or code (accepts both formats for flexibility)

    Returns:
        Dict with map of zone_id → centroid coordinates

    Raises:
        HTTPException 404: Building not found
        HTTPException 500: Database error
    """
    desk_repo = DeskRepository()
    zone_repo = ZoneRepository()

    try:
        # Accept both building codes (e.g., 'site-002') and UUIDs
        actual_building_id = building_id

        # If it looks like a building code (not UUID format), convert it to UUID
        if not _is_uuid(building_id):
            try:
                actual_building_id = desk_repo.get_building_uuid(building_id)
                if not actual_building_id:
                    logger.warning(f"Building not found for code: {building_id}")
                    raise HTTPException(status_code=404, detail=f"Building not found: {building_id}")
            except Exception as e:
                logger.warning(f"Failed to resolve building code '{building_id}' to UUID: {e}")
                # Try querying anyway in case it's already a UUID
                actual_building_id = building_id

        zones = zone_repo.get_by_building(actual_building_id)

        if not zones:
            logger.warning(f"No zones found for building {building_id} (UUID: {actual_building_id})")
            # Return empty centroids instead of error
            return {
                "building_id": building_id,
                "zone_count": 0,
                "centroid_count": 0,
                "centroids": {},
            }

        zone_ids = [z["zone_id"] for z in zones]
        centroids = desk_repo.get_centroids_for_zones(actual_building_id, zone_ids)

        logger.info(
            f"Retrieved {len(centroids)} zone centroids for building {building_id} (UUID: {actual_building_id})"
        )

        return {
            "building_id": building_id,
            "zone_count": len(zones),
            "centroid_count": len(centroids),
            "centroids": centroids,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get centroids for building {building_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Centroid retrieval failed: {e}")


@router.get("/{building_id}/desks/stats")
async def get_desk_statistics(
    building_id: str = Path(..., description="Building UUID or code (e.g., 'site-002' or UUID)"),
) -> Dict[str, Any]:
    """Get desk statistics for a building.

    Provides summary information about desks and zones:
    - Total desk count
    - Desks per zone
    - Desks per floor
    - Distribution by context

    Args:
        building_id: Building UUID or code (accepts both formats for flexibility)

    Returns:
        Dict with desk statistics

    Raises:
        HTTPException 500: Database error
    """
    desk_repo = DeskRepository()
    zone_repo = ZoneRepository()

    try:
        # Accept both building codes and UUIDs
        actual_building_id = building_id

        # If it looks like a building code (not UUID format), convert it to UUID
        if not _is_uuid(building_id):
            try:
                actual_building_id = desk_repo.get_building_uuid(building_id)
                if not actual_building_id:
                    logger.warning(f"Building not found for code: {building_id}")
                    return {
                        "building_id": building_id,
                        "total_desks": 0,
                        "total_zones": 0,
                        "desks_per_zone": {},
                        "desks_per_floor": {},
                        "desks_by_context": {},
                    }
            except Exception as e:
                logger.warning(f"Failed to resolve building code '{building_id}' to UUID: {e}")
                actual_building_id = building_id

        desks = desk_repo.get_by_building_uuid(actual_building_id)
        zones = zone_repo.get_by_building(actual_building_id)

        # Group by zone
        desks_by_zone = {}
        for desk in desks:
            zone = desk.get("zone_id", "unknown")
            desks_by_zone[zone] = desks_by_zone.get(zone, 0) + 1

        # Group by floor
        desks_by_floor = {}
        for desk in desks:
            floor = desk.get("floor", "unknown")
            desks_by_floor[floor] = desks_by_floor.get(floor, 0) + 1

        # Group by context
        desks_by_context = {}
        for desk in desks:
            context = desk.get("context", "unknown")
            desks_by_context[context] = desks_by_context.get(context, 0) + 1

        return {
            "building_id": building_id,
            "total_desks": len(desks),
            "total_zones": len(zones),
            "desks_per_zone": desks_by_zone,
            "desks_per_floor": desks_by_floor,
            "desks_by_context": desks_by_context,
        }
    except Exception as e:
        logger.error(f"Failed to get desk statistics for building {building_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Statistics retrieval failed: {e}")
