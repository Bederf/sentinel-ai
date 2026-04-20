"""Repository for desk operations."""

import logging
import time
from typing import Any

from app.database.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)


class DeskRepository:
    """Repository for desk database operations."""

    def __init__(self):
        """Initialize the repository with a Supabase client."""
        self.client = get_supabase_client()

    def _execute_with_retry(self, query, max_retries: int = 3):
        """Execute a Supabase query with retry on rate limit."""
        delay = 0.5
        last_error = None

        for attempt in range(max_retries + 1):
            try:
                return query.execute()
            except Exception as e:
                error_msg = str(e)
                if "429" in error_msg or "rate limit" in error_msg.lower():
                    last_error = e
                    if attempt < max_retries:
                        logger.warning(f"Rate limit hit, retrying in {delay}s... (attempt {attempt + 1}/{max_retries})")
                        time.sleep(delay)
                        delay *= 2.0
                    else:
                        logger.error(f"Rate limit persists after {max_retries} retries")
                        raise e
                else:
                    raise e

        if last_error:
            raise last_error

    def get_all(self, site_id: str | None = None) -> list[dict[str, Any]]:
        """Get all desks with optional building filter.

        Args:
            site_id: Filter by building UUID

        Returns:
            List of desks
        """
        query = self.client.table("desks").select("*")

        if site_id:
            query = query.eq("site_id", site_id)

        response = query.execute()
        return response.data

    def get_by_site_code(self, site_code: str) -> list[dict[str, Any]]:
        """Get desks by building code with zone_id resolved.

        Args:
            site_code: Building code (e.g., 'sandton' or 'site-002')

        Returns:
            List of desks with zone_id (string) from hvac_zones join
        """
        site_uuid = self.get_site_uuid(site_code)
        if not site_uuid:
            return []

        # Join with hvac_zones to get zone_id string
        response = (
            self.client.table("desks").select("*, hvac_zones(zone_id, zone_name)").eq("site_id", site_uuid).execute()
        )

        # Flatten hvac_zones data into desk dict
        desks = []
        for desk in response.data:
            hvac_zone = desk.pop("hvac_zones", None)
            if hvac_zone:
                desk["zone_id"] = hvac_zone.get("zone_id", "")
                desk["zone_name"] = hvac_zone.get("zone_name", "")
            else:
                desk["zone_id"] = ""
                desk["zone_name"] = ""
            desks.append(desk)

        return desks

    def get_by_desk_id(self, desk_id: str) -> dict[str, Any] | None:
        """Get desk by desk_id.

        Args:
            desk_id: Desk ID (e.g., 'L12-D001')

        Returns:
            Desk data or None if not found
        """
        response = self.client.table("desks").select("*").eq("desk_id", desk_id).execute()

        if response.data:
            return response.data[0]
        return None

    def get_by_uuid(self, uuid: str) -> dict[str, Any] | None:
        """Get desk by UUID.

        Args:
            uuid: Desk UUID

        Returns:
            Desk data or None if not found
        """
        response = self.client.table("desks").select("*").eq("id", uuid).execute()

        if response.data:
            return response.data[0]
        return None

    def get_by_zone(self, hvac_zone_id: str) -> list[dict[str, Any]]:
        """Get desks by HVAC zone UUID.

        Args:
            hvac_zone_id: HVAC zone UUID

        Returns:
            List of desks in the zone
        """
        response = self.client.table("desks").select("*").eq("hvac_zone_id", hvac_zone_id).execute()

        return response.data

    def get_by_floor(self, site_code: str, floor: str) -> list[dict[str, Any]]:
        """Get desks by building and floor.

        Args:
            site_code: Building code
            floor: Floor identifier

        Returns:
            List of desks on the floor
        """
        site_uuid = self.get_site_uuid(site_code)
        if not site_uuid:
            return []

        response = self.client.table("desks").select("*").eq("site_id", site_uuid).eq("floor", floor).execute()

        return response.data

    def find_desk(self, desk_id: str, site_code: str | None = None) -> dict[str, Any] | None:
        """Find a desk by ID, optionally filtered by building.

        Handles various desk ID formats (e.g., '201', 'desk 201', 'L12-D001').

        Args:
            desk_id: Desk ID to search for
            site_code: Optional building code filter

        Returns:
            Desk data or None if not found
        """
        # Normalize desk ID
        normalized = desk_id.strip().lower()
        normalized = normalized.replace("desk ", "").strip()

        # Build query
        query = self.client.table("desks").select("*")

        if site_code:
            site_uuid = self.get_site_uuid(site_code)
            if site_uuid:
                query = query.eq("site_id", site_uuid)

        # Escape LIKE wildcards in user input
        from app.utils import escape_like

        safe = escape_like(normalized)

        # Try exact match first
        response = query.ilike("desk_id", safe).execute()
        if response.data:
            return response.data[0]

        # Try suffix match (e.g., '201' matches 'L12-D201')
        response = query.ilike("desk_id", f"%{safe}").execute()
        if response.data:
            return response.data[0]

        return None

    def get_site_uuid(self, site_code: str) -> str | None:
        """Get building UUID from building code.

        Args:
            site_code: Building code (e.g., 'sandton')

        Returns:
            Building UUID or None
        """
        response = self.client.table("sites").select("id").eq("code", site_code).execute()

        if response.data:
            return response.data[0]["id"]
        return None

    def get_hvac_zone_uuid(self, zone_id: str) -> str | None:
        """Get HVAC zone UUID from zone_id.

        Args:
            zone_id: Zone ID (e.g., 'Zone-L12-N')

        Returns:
            Zone UUID or None
        """
        response = self.client.table("hvac_zones").select("id").eq("zone_id", zone_id).execute()

        if response.data:
            return response.data[0]["id"]
        return None

    def upsert(self, desk_data: dict[str, Any]) -> dict[str, Any]:
        """Insert or update a desk.

        Args:
            desk_data: Desk data with desk_id as unique key

        Returns:
            Upserted desk data
        """
        response = self.client.table("desks").upsert(desk_data, on_conflict="desk_id").execute()
        return response.data[0] if response.data else {}

    def upsert_many(self, desks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Insert or update multiple desks.

        Args:
            desks: List of desk data dicts

        Returns:
            List of upserted desks
        """
        if not desks:
            return []

        response = self.client.table("desks").upsert(desks, on_conflict="desk_id").execute()
        return response.data

    def create(self, desk_data: dict[str, Any]) -> dict[str, Any]:
        """Create a new desk.

        Args:
            desk_data: Desk data

        Returns:
            Created desk
        """
        response = self.client.table("desks").insert(desk_data).execute()
        return response.data[0]

    def update(self, desk_id: str, desk_data: dict[str, Any]) -> dict[str, Any] | None:
        """Update a desk.

        Args:
            desk_id: Desk ID
            desk_data: Data to update

        Returns:
            Updated desk or None if not found
        """
        response = self.client.table("desks").update(desk_data).eq("desk_id", desk_id).execute()

        if response.data:
            return response.data[0]
        return None

    def delete(self, desk_id: str) -> bool:
        """Delete a desk.

        Args:
            desk_id: Desk ID

        Returns:
            True if deleted, False if not found
        """
        response = self.client.table("desks").delete().eq("desk_id", desk_id).execute()

        return len(response.data) > 0

    def delete_by_site(self, site_code: str) -> int:
        """Delete all desks for a building.

        Args:
            site_code: Building code

        Returns:
            Number of desks deleted
        """
        site_uuid = self.get_site_uuid(site_code)
        if not site_uuid:
            return 0

        response = self.client.table("desks").delete().eq("site_id", site_uuid).execute()

        return len(response.data)

    def get_with_comfort_context(self, desk_id: str) -> dict[str, Any] | None:
        """Get desk with full comfort context (HVAC zone, DALI zone).

        Args:
            desk_id: Desk ID

        Returns:
            Desk with related zone data or None
        """
        # Get desk with HVAC zone join
        response = (
            self.client.table("desks")
            .select("*, hvac_zones(zone_id, zone_name, current_temp, setpoint, status)")
            .eq("desk_id", desk_id)
            .execute()
        )

        if response.data:
            return response.data[0]
        return None

    def get_by_site_uuid(self, site_id: str) -> list[dict[str, Any]]:
        """Get all desks for a building UUID.

        Args:
            site_id: Building UUID

        Returns:
            List of desks in the building
        """
        query = self.client.table("desks").select("*").eq("site_id", site_id)
        response = self._execute_with_retry(query)
        return response.data

    def get_by_zone_id(self, site_id: str, zone_id: str) -> list[dict[str, Any]]:
        """Get desks by building-level zone ID.

        Args:
            site_id: Building UUID
            zone_id: Zone ID (e.g., 'Zone-L1-A')

        Returns:
            List of desks in the zone
        """
        response = self.client.table("desks").select("*").eq("site_id", site_id).eq("zone_id", zone_id).execute()

        return response.data

    def get_centroids_for_zones(self, site_id: str, zones: list[str]) -> dict[str, dict[str, float]]:
        """Get centroids for specific zones from desk positions.

        Args:
            site_id: Building UUID
            zones: List of zone IDs

        Returns:
            Dict mapping zone_id → {x: avg_x, z: avg_z}
        """
        all_desks = self.get_by_site_uuid(site_id)
        centroids = {}

        for zone_id in zones:
            zone_desks = [d for d in all_desks if d.get("zone_id") == zone_id]

            if zone_desks:
                avg_x = sum(float(d.get("x_coord", 0)) for d in zone_desks) / len(zone_desks)
                avg_z = sum(float(d.get("z_coord", 0)) for d in zone_desks) / len(zone_desks)
                centroids[zone_id] = {"x": round(avg_x, 2), "z": round(avg_z, 2)}

        return centroids
