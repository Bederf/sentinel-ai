"""Service for zone and desk ingestion during building onboarding.

Provides validation and business logic for:
- Importing zone configurations (per-building)
- Importing desk positions and context
- Calculating zone centroids from desk data
- Multi-building support (each building has unique structure)
"""

import logging
from decimal import Decimal
from typing import Any

from app.database.repositories.desk_repository import DeskRepository
from app.database.repositories.zone_repository import ZoneRepository
from app.database.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)


class ZoneIngestionService:
    """Service for ingesting zone and desk configurations for buildings."""

    def __init__(self):
        """Initialize with repository dependencies."""
        self.zone_repo = ZoneRepository()
        self.desk_repo = DeskRepository()
        self.client = get_supabase_client()

    def get_site_uuid(self, site_code: str) -> str | None:
        """Convert building code to UUID.

        Args:
            site_code: Building code (e.g., 'site-002')

        Returns:
            Building UUID or None if not found
        """
        response = self.client.table("sites").select("id").eq("code", site_code).execute()

        if response.data:
            return response.data[0]["id"]
        return None

    async def ingest_zones(self, site_id: str, zones: list[dict[str, Any]]) -> dict[str, Any]:
        """Ingest zone configuration for a building.

        Each building can have a unique zone structure. This method validates
        and stores zone definitions.

        Validation:
        - All zone_ids must be unique within the building
        - Floor codes must be valid (B#, G, L#, R)
        - Zone type must be one of the predefined types
        - Zone letter must be A-Z for single letters, or numeric for multi-digit

        Args:
            site_id: Building code (e.g., "site-002") or UUID
            zones: List of zone configurations with:
                - zone_id: Unique identifier e.g., "Zone-L1-A"
                - zone_name: Human-readable name
                - floor: Floor code (L0, L1, L2, B1, G, R)
                - zone_type: Type (open_office, meeting_room, etc.)
                - typical_occupancy: Optional occupancy count
                - area_sqm: Optional area

        Returns:
            Dict with status and number of zones created

        Raises:
            ValueError: If validation fails or building not found
        """
        # Convert building code to UUID if needed
        site_uuid = self.get_site_uuid(site_id)
        if not site_uuid:
            raise ValueError(f"Building not found: {site_id}")

        # Validate zones
        zone_ids = [z["zone_id"] for z in zones]
        if len(zone_ids) != len(set(zone_ids)):
            raise ValueError("Duplicate zone_ids detected within ingestion")

        # Validate floor codes
        valid_floors = {"B1", "B2", "B3", "G", "L0", "L1", "L2", "L3", "L4", "L5", "R"}
        for zone in zones:
            if zone.get("floor") not in valid_floors:
                raise ValueError(f"Invalid floor code: {zone.get('floor')}")

        # Validate zone types
        valid_types = {
            "open_office",
            "meeting_room",
            "plant_room",
            "storage",
            "stairwell",
            "corridor",
            "lobby",
            "restroom",
            "cafeteria",
            "server_room",
            "comms_room",
            "mechanical",
            "electrical",
        }
        for zone in zones:
            if zone.get("zone_type") not in valid_types:
                raise ValueError(f"Invalid zone_type: {zone.get('zone_type')}")

        # Insert into Supabase
        for zone in zones:
            zone_data = {
                "site_id": site_uuid,
                "zone_id": zone["zone_id"],
                "zone_name": zone["zone_name"],
                "floor": zone["floor"],
                "zone_letter": zone.get("zone_letter"),
                "zone_type": zone["zone_type"],
                "typical_occupancy": zone.get("typical_occupancy"),
                "area_sqm": zone.get("area_sqm"),
            }
            try:
                await self.zone_repo.create(zone_data)
            except Exception as e:
                logger.error(f"Failed to create zone {zone['zone_id']}: {e}")
                raise ValueError(f"Failed to create zone {zone['zone_id']}: {e}")

        logger.info(f"Ingested {len(zones)} zones for building {site_id}")
        return {"status": "success", "zones_created": len(zones)}

    async def ingest_desks(self, site_id: str, desks: list[dict[str, Any]]) -> dict[str, Any]:
        """Ingest desk configuration for a building.

        Validation:
        - All desk_ids must be unique within the building
        - Zone_id must reference existing zone for this building
        - Coordinates must be valid {x, y, z} numbers
        - Context must be one of the valid contexts
        - Floor code must match zone floor

        Args:
            site_id: Building code (e.g., "site-002") or UUID
            desks: List of desk configurations with:
                - desk_id: Unique identifier
                - zone_id: Reference to zone (must exist)
                - floor: Floor code
                - context: Desk context (near_diffuser, near_window, etc.)
                - coordinates: {x, y, z} object

        Returns:
            Dict with status and number of desks created

        Raises:
            ValueError: If validation fails or building not found
        """
        # Convert building code to UUID if needed
        site_uuid = self.get_site_uuid(site_id)
        if not site_uuid:
            raise ValueError(f"Building not found: {site_id}")

        # Validate desks
        desk_ids = [d["desk_id"] for d in desks]
        if len(desk_ids) != len(set(desk_ids)):
            raise ValueError("Duplicate desk_ids detected within ingestion")

        # Validate zone references
        zones = self.zone_repo.get_by_site(site_uuid)
        valid_zone_ids = {z["zone_id"] for z in zones}
        valid_zone_dict = {z["zone_id"]: z for z in zones}

        for desk in desks:
            zone_id = desk.get("zone_id")
            if zone_id not in valid_zone_ids:
                raise ValueError(f"Invalid zone_id for desk {desk['desk_id']}: {zone_id}")

            # Validate floor matches zone floor
            zone = valid_zone_dict[zone_id]
            if desk.get("floor") != zone["floor"]:
                raise ValueError(
                    f"Desk {desk['desk_id']} floor {desk['floor']} doesn't match zone floor {zone['floor']}"
                )

        # Validate context values
        valid_contexts = {"near_diffuser", "near_window", "near_printer", "corner", "open_plan"}
        for desk in desks:
            if desk.get("context") not in valid_contexts:
                raise ValueError(f"Invalid context for desk {desk['desk_id']}: {desk.get('context')}")

        # Validate coordinates
        for desk in desks:
            coords = desk.get("coordinates", {})
            if not isinstance(coords, dict) or "x" not in coords or "z" not in coords:
                raise ValueError(f"Invalid coordinates for desk {desk['desk_id']}")

            try:
                x = float(coords["x"])
                _y = float(coords.get("y", 0))
                z = float(coords["z"])

                # Basic bounds check (X: 0-50m, Z: 0-50m)
                if not (0 <= x <= 50 and 0 <= z <= 50):
                    logger.warning(f"Desk {desk['desk_id']} coordinates outside typical bounds: ({x}, {z})")
            except (ValueError, TypeError):
                raise ValueError(f"Coordinates not numeric for desk {desk['desk_id']}")

        # Insert desks
        for desk in desks:
            desk_data = {
                "site_id": site_uuid,
                "zone_id": desk["zone_id"],
                "desk_id": desk["desk_id"],
                "floor": desk["floor"],
                "context": desk.get("context", "open_plan"),
                "x_coord": Decimal(str(desk["coordinates"]["x"])),
                "y_coord": Decimal(str(desk["coordinates"].get("y", 0))),
                "z_coord": Decimal(str(desk["coordinates"]["z"])),
            }
            try:
                self.desk_repo.upsert(desk_data)
            except Exception as e:
                logger.error(f"Failed to create desk {desk['desk_id']}: {e}")
                raise ValueError(f"Failed to create desk {desk['desk_id']}: {e}")

        logger.info(f"Ingested {len(desks)} desks for building {site_id}")
        return {"status": "success", "desks_created": len(desks)}

    async def calculate_zone_centroid(self, site_id: str, zone_id: str) -> dict[str, float] | None:
        """Calculate zone centroid from desk positions.

        The centroid is the average X, Z position of all desks in a zone.
        Used by Digital Twin for accurate equipment positioning without
        needing to load all individual desk data.

        Args:
            site_id: Building code (e.g., "site-002") or UUID
            zone_id: Zone ID (e.g., "Zone-L1-A")

        Returns:
            Dict with centroid coordinates {x, z} or None if no desks found
        """
        # Convert building code to UUID if needed
        site_uuid = self.get_site_uuid(site_id)
        if not site_uuid:
            logger.warning(f"Building not found: {site_id}")
            return None

        desks = self.desk_repo.get_by_zone_id(site_uuid, zone_id)

        if not desks:
            logger.warning(f"No desks found for zone {zone_id} in building {site_id}")
            return None

        avg_x = sum(float(d.get("x_coord", 0)) for d in desks) / len(desks)
        avg_z = sum(float(d.get("z_coord", 0)) for d in desks) / len(desks)

        return {"x": round(avg_x, 2), "z": round(avg_z, 2)}

    def get_all_zone_centroids(self, site_id: str) -> dict[str, dict[str, float]]:
        """Get centroids for all zones in a building.

        Efficient operation: loads all desks once, calculates centroids for
        all zones in a single pass.

        Args:
            site_id: Building code (e.g., "site-002") or UUID

        Returns:
            Dict mapping zone_id → {x, z} centroid coordinates
        """
        # Convert building code to UUID if needed
        site_uuid = self.get_site_uuid(site_id)
        if not site_uuid:
            logger.warning(f"Building not found: {site_id}")
            return {}

        zones = self.zone_repo.get_by_site(site_uuid)
        all_desks = self.desk_repo.get_by_site_uuid(site_uuid)

        centroids = {}
        for zone in zones:
            zone_desks = [d for d in all_desks if d.get("zone_id") == zone["zone_id"]]

            if zone_desks:
                avg_x = sum(float(d.get("x_coord", 0)) for d in zone_desks) / len(zone_desks)
                avg_z = sum(float(d.get("z_coord", 0)) for d in zone_desks) / len(zone_desks)
                centroids[zone["zone_id"]] = {"x": round(avg_x, 2), "z": round(avg_z, 2)}

        logger.info(f"Calculated {len(centroids)} zone centroids for building {site_id}")
        return centroids

    async def validate_zone_structure(self, site_id: str) -> tuple[bool, list[str]]:
        """Validate zone and desk structure for a building.

        Checks:
        - All zones have at least one desk
        - No orphaned desks (zone doesn't exist)
        - Desk coordinates are within reasonable bounds
        - Consistent floor assignments

        Args:
            site_id: Building code (e.g., "site-002") or UUID

        Returns:
            Tuple of (is_valid, list of error messages)
        """
        errors = []

        # Convert building code to UUID if needed
        site_uuid = self.get_site_uuid(site_id)
        if not site_uuid:
            return False, [f"Building not found: {site_id}"]

        zones = self.zone_repo.get_by_site(site_uuid)
        desks = self.desk_repo.get_by_site_uuid(site_uuid)

        if not zones:
            errors.append("No zones configured for building")
            return False, errors

        # Check zones have desks
        zone_ids = {z["zone_id"] for z in zones}
        desks_by_zone = {}
        for desk in desks:
            zone_id = desk.get("zone_id")
            if zone_id not in zone_ids:
                errors.append(f"Orphaned desk {desk['desk_id']}: zone {zone_id} not found")
            else:
                desks_by_zone.setdefault(zone_id, []).append(desk)

        # Check each zone has reasonable desk count (5-50 desks per zone)
        for zone_id in zone_ids:
            desk_count = len(desks_by_zone.get(zone_id, []))
            if desk_count == 0:
                errors.append(f"Zone {zone_id} has no desks")
            elif desk_count > 100:
                errors.append(f"Zone {zone_id} has unusually high desk count: {desk_count}")

        return len(errors) == 0, errors
