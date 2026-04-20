"""Repository for building-level zone operations.

Manages per-building zone configuration for multi-building support.
Each building can have a unique zone structure.
"""

import logging
import time
from typing import Any

from app.database.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)


class ZoneRepository:
    """Repository for building-level zone database operations."""

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
        """Get all zones with optional building filter.

        Args:
            site_id: Filter by building UUID

        Returns:
            List of zones
        """
        query = self.client.table("zones").select("*")

        if site_id:
            query = query.eq("site_id", site_id)

        response = query.execute()
        return response.data

    def get_by_site(self, site_id: str) -> list[dict[str, Any]]:
        """Get all zones for a specific building.

        Args:
            site_id: Building UUID

        Returns:
            List of zones in the building
        """
        query = self.client.table("zones").select("*").eq("site_id", site_id)
        response = self._execute_with_retry(query)
        return response.data

    def get_by_zone_id(self, site_id: str, zone_id: str) -> dict[str, Any] | None:
        """Get a specific zone by zone_id within a building.

        Args:
            site_id: Building UUID
            zone_id: Zone ID (e.g., "Zone-L1-A")

        Returns:
            Zone data or None if not found
        """
        response = self.client.table("zones").select("*").eq("site_id", site_id).eq("zone_id", zone_id).execute()

        if response.data:
            return response.data[0]
        return None

    def get_by_uuid(self, uuid: str) -> dict[str, Any] | None:
        """Get zone by UUID.

        Args:
            uuid: Zone UUID

        Returns:
            Zone data or None if not found
        """
        response = self.client.table("zones").select("*").eq("id", uuid).execute()

        if response.data:
            return response.data[0]
        return None

    def get_by_floor(self, site_id: str, floor: str) -> list[dict[str, Any]]:
        """Get zones by building and floor.

        Args:
            site_id: Building UUID
            floor: Floor code (L0, L1, L2, B1, etc.)

        Returns:
            List of zones on the floor
        """
        response = self.client.table("zones").select("*").eq("site_id", site_id).eq("floor", floor).execute()
        return response.data

    def create(self, zone_data: dict[str, Any]) -> dict[str, Any]:
        """Create a new zone.

        Args:
            zone_data: Zone data including:
                - site_id
                - zone_id
                - zone_name
                - floor
                - zone_type

        Returns:
            Created zone data
        """
        response = self.client.table("zones").insert(zone_data).execute()
        if response.data:
            logger.info(f"Created zone {zone_data.get('zone_id')} for building {zone_data.get('site_id')}")
            return response.data[0]
        else:
            raise ValueError(f"Failed to create zone: {zone_data}")

    def update(self, zone_id: str, zone_data: dict[str, Any]) -> dict[str, Any] | None:
        """Update a zone.

        Args:
            zone_id: Zone UUID
            zone_data: Data to update

        Returns:
            Updated zone or None if not found
        """
        response = self.client.table("zones").update(zone_data).eq("id", zone_id).execute()

        if response.data:
            logger.info(f"Updated zone {zone_id}")
            return response.data[0]
        return None

    def upsert(self, zone_data: dict[str, Any]) -> dict[str, Any]:
        """Insert or update a zone.

        Args:
            zone_data: Zone data with site_id and zone_id as unique key

        Returns:
            Upserted zone data
        """
        response = self.client.table("zones").upsert(zone_data, on_conflict="site_id,zone_id").execute()
        return response.data[0] if response.data else {}

    def upsert_many(self, zones: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Insert or update multiple zones.

        Args:
            zones: List of zone data dicts

        Returns:
            List of upserted zones
        """
        if not zones:
            return []

        response = self.client.table("zones").upsert(zones, on_conflict="site_id,zone_id").execute()
        return response.data

    def delete(self, zone_id: str) -> bool:
        """Delete a zone.

        Args:
            zone_id: Zone UUID

        Returns:
            True if deleted, False if not found
        """
        response = self.client.table("zones").delete().eq("id", zone_id).execute()

        if response.data:
            logger.info(f"Deleted zone {zone_id}")
            return True
        return False

    def delete_by_site(self, site_id: str) -> int:
        """Delete all zones for a building.

        Args:
            site_id: Building UUID

        Returns:
            Number of zones deleted
        """
        response = self.client.table("zones").delete().eq("site_id", site_id).execute()

        count = len(response.data)
        logger.info(f"Deleted {count} zones for building {site_id}")
        return count

    def get_zone_centroids(self, site_id: str) -> dict[str, dict[str, float]]:
        """Get zone centroids for all zones in a building.

        Centroids are calculated from desk positions and used for
        accurate equipment positioning in 3D visualization.

        Args:
            site_id: Building UUID

        Returns:
            Dict mapping zone_id → {x, z} centroid coordinates
        """
        # Query the zone_centroids view
        response = self.client.table("zone_centroids").select("*").eq("site_id", site_id).execute()

        centroids = {}
        for row in response.data:
            centroids[row["zone_id"]] = {"x": float(row["centroid_x"]), "z": float(row["centroid_z"])}

        return centroids
