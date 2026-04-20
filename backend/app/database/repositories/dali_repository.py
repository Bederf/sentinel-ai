"""Repository for DALI lighting system operations.

This repository handles CRUD operations for DALI-2 controllers,
luminaires, sensors, zones, and groups.
"""

import logging
from typing import Any

from app.database.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)


class DALIControllerRepository:
    """Repository for DALI controller operations."""

    def __init__(self):
        """Initialize the repository with a Supabase client."""
        self.client = get_supabase_client()

    def get_all(self, site_id: str | None = None) -> list[dict[str, Any]]:
        """Get all DALI controllers with optional building filter.

        Args:
            site_id: Filter by building UUID

        Returns:
            List of DALI controllers
        """
        query = self.client.table("dali_controllers").select("*")

        if site_id:
            query = query.eq("site_id", site_id)

        response = query.execute()
        return response.data

    def get_by_id(self, site_id: str, controller_id: str) -> dict[str, Any] | None:
        """Get controller by building and controller_id composite key.

        Args:
            site_id: Building UUID
            controller_id: Controller identifier (e.g., 'DALI-L12-01')

        Returns:
            Controller data or None if not found
        """
        response = (
            self.client.table("dali_controllers")
            .select("*")
            .eq("site_id", site_id)
            .eq("controller_id", controller_id)
            .execute()
        )

        if response.data:
            return response.data[0]
        return None

    def get_by_uuid(self, uuid: str) -> dict[str, Any] | None:
        """Get controller by UUID.

        Args:
            uuid: Controller UUID

        Returns:
            Controller data or None if not found
        """
        response = self.client.table("dali_controllers").select("*").eq("id", uuid).execute()

        if response.data:
            return response.data[0]
        return None

    def upsert(self, controller_data: dict[str, Any]) -> dict[str, Any]:
        """Insert or update a controller.

        Args:
            controller_data: Controller data

        Returns:
            Upserted controller data
        """
        response = (
            self.client.table("dali_controllers").upsert(controller_data, on_conflict="site_id,controller_id").execute()
        )
        return response.data[0] if response.data else {}

    def update_status(self, site_id: str, controller_id: str, status: str) -> dict[str, Any] | None:
        """Update controller status.

        Args:
            site_id: Building UUID
            controller_id: Controller identifier
            status: New status ('online', 'offline', 'degraded')

        Returns:
            Updated controller or None if not found
        """
        response = (
            self.client.table("dali_controllers")
            .update({"status": status, "last_seen": "NOW()"})
            .eq("site_id", site_id)
            .eq("controller_id", controller_id)
            .execute()
        )

        if response.data:
            return response.data[0]
        return None


class DALILuminaireRepository:
    """Repository for DALI luminaire operations."""

    def __init__(self):
        """Initialize the repository with a Supabase client."""
        self.client = get_supabase_client()

    def get_all(
        self, site_id: str | None = None, controller_id: str | None = None, zone_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Get all luminaires with optional filtering.

        Args:
            site_id: Filter by building UUID
            controller_id: Filter by controller UUID
            zone_id: Filter by HVAC zone UUID

        Returns:
            List of luminaires
        """
        query = self.client.table("dali_luminaires").select("*")

        if site_id:
            query = query.eq("site_id", site_id)
        if controller_id:
            query = query.eq("controller_id", controller_id)
        if zone_id:
            query = query.eq("hvac_zone_id", zone_id)

        response = query.execute()
        return response.data

    def get_by_id(self, site_id: str, luminaire_id: str) -> dict[str, Any] | None:
        """Get luminaire by building and luminaire_id composite key.

        Args:
            site_id: Building UUID
            luminaire_id: Luminaire identifier (e.g., 'LUM-L12-025')

        Returns:
            Luminaire data or None if not found
        """
        response = (
            self.client.table("dali_luminaires")
            .select("*")
            .eq("site_id", site_id)
            .eq("luminaire_id", luminaire_id)
            .execute()
        )

        if response.data:
            return response.data[0]
        return None

    def get_with_zone_info(self, site_id: str | None = None) -> list[dict[str, Any]]:
        """Get luminaires with enriched zone details.

        Uses the v_luminaires_with_zones view.

        Args:
            site_id: Optional filter by building UUID

        Returns:
            List of enriched luminaire records
        """
        query = self.client.table("v_luminaires_with_zones").select("*")

        if site_id:
            query = query.eq("site_id", site_id)

        response = query.execute()
        return response.data

    def get_fault_luminaires(self, site_id: str | None = None) -> list[dict[str, Any]]:
        """Get all luminaires with fault status.

        Args:
            site_id: Optional filter by building UUID

        Returns:
            List of luminaires in fault state
        """
        query = self.client.table("dali_luminaires").select("*").eq("fault_status", True)

        if site_id:
            query = query.eq("site_id", site_id)

        response = query.execute()
        return response.data

    def upsert(self, luminaire_data: dict[str, Any]) -> dict[str, Any]:
        """Insert or update a luminaire.

        Args:
            luminaire_data: Luminaire data

        Returns:
            Upserted luminaire data
        """
        response = (
            self.client.table("dali_luminaires").upsert(luminaire_data, on_conflict="site_id,luminaire_id").execute()
        )
        return response.data[0] if response.data else {}

    def upsert_many(self, luminaires: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Insert or update multiple luminaires.

        Args:
            luminaires: List of luminaire data dicts

        Returns:
            List of upserted luminaires
        """
        if not luminaires:
            return []

        response = self.client.table("dali_luminaires").upsert(luminaires, on_conflict="site_id,luminaire_id").execute()
        return response.data

    def update_level(self, site_id: str, luminaire_id: str, level: int) -> dict[str, Any] | None:
        """Update luminaire brightness level.

        Args:
            site_id: Building UUID
            luminaire_id: Luminaire identifier
            level: Brightness level (0-100)

        Returns:
            Updated luminaire or None if not found
        """
        response = (
            self.client.table("dali_luminaires")
            .update({"current_level": level, "last_updated": "NOW()"})
            .eq("site_id", site_id)
            .eq("luminaire_id", luminaire_id)
            .execute()
        )

        if response.data:
            return response.data[0]
        return None


class DALISensorRepository:
    """Repository for DALI sensor operations."""

    def __init__(self):
        """Initialize the repository with a Supabase client."""
        self.client = get_supabase_client()

    def get_all(
        self, site_id: str | None = None, controller_id: str | None = None, zone_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Get all sensors with optional filtering.

        Args:
            site_id: Filter by building UUID
            controller_id: Filter by controller UUID
            zone_id: Filter by HVAC zone UUID

        Returns:
            List of sensors
        """
        query = self.client.table("dali_sensors").select("*")

        if site_id:
            query = query.eq("site_id", site_id)
        if controller_id:
            query = query.eq("controller_id", controller_id)
        if zone_id:
            query = query.eq("hvac_zone_id", zone_id)

        response = query.execute()
        return response.data

    def get_by_id(self, site_id: str, sensor_id: str) -> dict[str, Any] | None:
        """Get sensor by building and sensor_id composite key.

        Args:
            site_id: Building UUID
            sensor_id: Sensor identifier (e.g., 'PIR-L12-025')

        Returns:
            Sensor data or None if not found
        """
        response = (
            self.client.table("dali_sensors").select("*").eq("site_id", site_id).eq("sensor_id", sensor_id).execute()
        )

        if response.data:
            return response.data[0]
        return None

    def get_by_desk(self, desk_id: str) -> list[dict[str, Any]]:
        """Get sensors assigned to a specific desk.

        Args:
            desk_id: Desk identifier

        Returns:
            List of sensors for this desk
        """
        response = self.client.table("dali_sensors").select("*").eq("desk_id", desk_id).execute()

        return response.data

    def get_occupied_zones(self, site_id: str) -> list[dict[str, Any]]:
        """Get all sensors showing occupancy in a building.

        Args:
            site_id: Building UUID

        Returns:
            List of sensors with occupancy = TRUE
        """
        response = self.client.table("dali_sensors").select("*").eq("site_id", site_id).eq("occupancy", True).execute()

        return response.data

    def upsert(self, sensor_data: dict[str, Any]) -> dict[str, Any]:
        """Insert or update a sensor.

        Args:
            sensor_data: Sensor data

        Returns:
            Upserted sensor data
        """
        response = self.client.table("dali_sensors").upsert(sensor_data, on_conflict="site_id,sensor_id").execute()
        return response.data[0] if response.data else {}


class DALIGroupRepository:
    """Repository for DALI group/scene operations."""

    def __init__(self):
        """Initialize the repository with a Supabase client."""
        self.client = get_supabase_client()

    def get_all(self, site_id: str | None = None, controller_id: str | None = None) -> list[dict[str, Any]]:
        """Get all groups with optional filtering.

        Args:
            site_id: Filter by building UUID
            controller_id: Filter by controller UUID

        Returns:
            List of groups
        """
        query = self.client.table("dali_groups").select("*")

        if site_id:
            query = query.eq("site_id", site_id)
        if controller_id:
            query = query.eq("controller_id", controller_id)

        response = query.execute()
        return response.data

    def get_by_id(self, site_id: str, group_id: str) -> dict[str, Any] | None:
        """Get group by building and group_id composite key.

        Args:
            site_id: Building UUID
            group_id: Group identifier (e.g., 'GRP-L12-N-001')

        Returns:
            Group data or None if not found
        """
        response = (
            self.client.table("dali_groups").select("*").eq("site_id", site_id).eq("group_id", group_id).execute()
        )

        if response.data:
            return response.data[0]
        return None

    def upsert(self, group_data: dict[str, Any]) -> dict[str, Any]:
        """Insert or update a group.

        Args:
            group_data: Group data

        Returns:
            Upserted group data
        """
        response = self.client.table("dali_groups").upsert(group_data, on_conflict="site_id,group_id").execute()
        return response.data[0] if response.data else {}

    def add_luminaire(self, site_id: str, group_id: str, luminaire_uuid: str) -> dict[str, Any] | None:
        """Add a luminaire to a group.

        Args:
            site_id: Building UUID
            group_id: Group identifier
            luminaire_uuid: Luminaire UUID to add

        Returns:
            Updated group or None if not found
        """
        group = self.get_by_id(site_id, group_id)
        if not group:
            return None

        luminaire_ids = group.get("luminaire_ids", [])
        if luminaire_uuid not in luminaire_ids:
            luminaire_ids.append(luminaire_uuid)

        response = (
            self.client.table("dali_groups")
            .update({"luminaire_ids": luminaire_ids})
            .eq("site_id", site_id)
            .eq("group_id", group_id)
            .execute()
        )

        if response.data:
            return response.data[0]
        return None

    def remove_luminaire(self, site_id: str, group_id: str, luminaire_uuid: str) -> dict[str, Any] | None:
        """Remove a luminaire from a group.

        Args:
            site_id: Building UUID
            group_id: Group identifier
            luminaire_uuid: Luminaire UUID to remove

        Returns:
            Updated group or None if not found
        """
        group = self.get_by_id(site_id, group_id)
        if not group:
            return None

        luminaire_ids = group.get("luminaire_ids", [])
        if luminaire_uuid in luminaire_ids:
            luminaire_ids.remove(luminaire_uuid)

        response = (
            self.client.table("dali_groups")
            .update({"luminaire_ids": luminaire_ids})
            .eq("site_id", site_id)
            .eq("group_id", group_id)
            .execute()
        )

        if response.data:
            return response.data[0]
        return None

    def update_scene(
        self, site_id: str, group_id: str, scene_name: str, scene_config: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Update a scene configuration in a group.

        Args:
            site_id: Building UUID
            group_id: Group identifier
            scene_name: Scene name (e.g., 'full_bright', 'working')
            scene_config: Scene configuration (e.g., {'level': 80, 'color_temp': 4000})

        Returns:
            Updated group or None if not found
        """
        group = self.get_by_id(site_id, group_id)
        if not group:
            return None

        scene_levels = group.get("scene_levels", {})
        scene_levels[scene_name] = scene_config

        response = (
            self.client.table("dali_groups")
            .update({"scene_levels": scene_levels})
            .eq("site_id", site_id)
            .eq("group_id", group_id)
            .execute()
        )

        if response.data:
            return response.data[0]
        return None
