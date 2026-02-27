"""Repository for lighting system operations.

This repository handles CRUD operations for lighting controllers,
luminaires, sensors, zones, and groups.
"""

from typing import List, Optional, Dict, Any
import logging
from app.database.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)


class LightingControllerRepository:
    """Repository for lighting controller operations."""

    def __init__(self):
        """Initialize the repository with a Supabase client."""
        self.client = get_supabase_client()

    def get_all(self, building_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get all lighting controllers with optional building filter.

        Args:
            building_id: Filter by building UUID

        Returns:
            List of lighting controllers
        """
        query = self.client.table("dali_controllers").select("*")

        if building_id:
            query = query.eq("building_id", building_id)

        response = query.execute()
        return response.data

    def get_by_id(self, building_id: str, controller_id: str) -> Optional[Dict[str, Any]]:
        """Get controller by building and controller_id composite key.

        Args:
            building_id: Building UUID
            controller_id: Controller identifier (e.g., 'DALI-L12-01')

        Returns:
            Controller data or None if not found
        """
        response = (
            self.client.table("dali_controllers")
            .select("*")
            .eq("building_id", building_id)
            .eq("controller_id", controller_id)
            .execute()
        )

        if response.data:
            return response.data[0]
        return None

    def get_by_uuid(self, uuid: str) -> Optional[Dict[str, Any]]:
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

    def upsert(self, controller_data: Dict[str, Any]) -> Dict[str, Any]:
        """Insert or update a controller.

        Args:
            controller_data: Controller data

        Returns:
            Upserted controller data
        """
        response = (
            self.client.table("dali_controllers")
            .upsert(controller_data, on_conflict="building_id,controller_id")
            .execute()
        )
        return response.data[0] if response.data else {}

    def update_status(self, building_id: str, controller_id: str, status: str) -> Optional[Dict[str, Any]]:
        """Update controller status.

        Args:
            building_id: Building UUID
            controller_id: Controller identifier
            status: New status ('online', 'offline', 'degraded')

        Returns:
            Updated controller or None if not found
        """
        response = (
            self.client.table("dali_controllers")
            .update({"status": status, "last_seen": "NOW()"})
            .eq("building_id", building_id)
            .eq("controller_id", controller_id)
            .execute()
        )

        if response.data:
            return response.data[0]
        return None


class LightingLuminaireRepository:
    """Repository for lighting luminaire operations."""

    def __init__(self):
        """Initialize the repository with a Supabase client."""
        self.client = get_supabase_client()

    def get_all(
        self, building_id: Optional[str] = None, controller_id: Optional[str] = None, zone_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get all luminaires with optional filtering.

        Args:
            building_id: Filter by building UUID
            controller_id: Filter by controller UUID
            zone_id: Filter by HVAC zone UUID

        Returns:
            List of luminaires
        """
        query = self.client.table("dali_luminaires").select("*")

        if building_id:
            query = query.eq("building_id", building_id)
        if controller_id:
            query = query.eq("controller_id", controller_id)
        if zone_id:
            query = query.eq("hvac_zone_id", zone_id)

        response = query.execute()
        return response.data

    def get_by_id(self, building_id: str, luminaire_id: str) -> Optional[Dict[str, Any]]:
        """Get luminaire by building and luminaire_id composite key.

        Args:
            building_id: Building UUID
            luminaire_id: Luminaire identifier (e.g., 'LUM-L12-025')

        Returns:
            Luminaire data or None if not found
        """
        response = (
            self.client.table("dali_luminaires")
            .select("*")
            .eq("building_id", building_id)
            .eq("luminaire_id", luminaire_id)
            .execute()
        )

        if response.data:
            return response.data[0]
        return None

    def get_with_zone_info(self, building_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get luminaires with enriched zone details.

        Uses the v_luminaires_with_zones view.

        Args:
            building_id: Optional filter by building UUID

        Returns:
            List of enriched luminaire records
        """
        query = self.client.table("v_luminaires_with_zones").select("*")

        if building_id:
            query = query.eq("building_id", building_id)

        response = query.execute()
        return response.data

    def get_fault_luminaires(self, building_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get all luminaires with fault status.

        Args:
            building_id: Optional filter by building UUID

        Returns:
            List of luminaires in fault state
        """
        query = self.client.table("dali_luminaires").select("*").eq("fault_status", True)

        if building_id:
            query = query.eq("building_id", building_id)

        response = query.execute()
        return response.data

    def upsert(self, luminaire_data: Dict[str, Any]) -> Dict[str, Any]:
        """Insert or update a luminaire.

        Args:
            luminaire_data: Luminaire data

        Returns:
            Upserted luminaire data
        """
        response = (
            self.client.table("dali_luminaires")
            .upsert(luminaire_data, on_conflict="building_id,luminaire_id")
            .execute()
        )
        return response.data[0] if response.data else {}

    def upsert_many(self, luminaires: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Insert or update multiple luminaires.

        Args:
            luminaires: List of luminaire data dicts

        Returns:
            List of upserted luminaires
        """
        if not luminaires:
            return []

        response = (
            self.client.table("dali_luminaires").upsert(luminaires, on_conflict="building_id,luminaire_id").execute()
        )
        return response.data

    def update_level(self, building_id: str, luminaire_id: str, level: int) -> Optional[Dict[str, Any]]:
        """Update luminaire brightness level.

        Args:
            building_id: Building UUID
            luminaire_id: Luminaire identifier
            level: Brightness level (0-100)

        Returns:
            Updated luminaire or None if not found
        """
        response = (
            self.client.table("dali_luminaires")
            .update({"current_level": level, "last_updated": "NOW()"})
            .eq("building_id", building_id)
            .eq("luminaire_id", luminaire_id)
            .execute()
        )

        if response.data:
            return response.data[0]
        return None


class LightingSensorRepository:
    """Repository for lighting sensor operations."""

    def __init__(self):
        """Initialize the repository with a Supabase client."""
        self.client = get_supabase_client()

    def get_all(
        self, building_id: Optional[str] = None, controller_id: Optional[str] = None, zone_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get all sensors with optional filtering.

        Args:
            building_id: Filter by building UUID
            controller_id: Filter by controller UUID
            zone_id: Filter by HVAC zone UUID

        Returns:
            List of sensors
        """
        query = self.client.table("dali_sensors").select("*")

        if building_id:
            query = query.eq("building_id", building_id)
        if controller_id:
            query = query.eq("controller_id", controller_id)
        if zone_id:
            query = query.eq("hvac_zone_id", zone_id)

        response = query.execute()
        return response.data

    def get_by_id(self, building_id: str, sensor_id: str) -> Optional[Dict[str, Any]]:
        """Get sensor by building and sensor_id composite key.

        Args:
            building_id: Building UUID
            sensor_id: Sensor identifier (e.g., 'PIR-L12-025')

        Returns:
            Sensor data or None if not found
        """
        response = (
            self.client.table("dali_sensors")
            .select("*")
            .eq("building_id", building_id)
            .eq("sensor_id", sensor_id)
            .execute()
        )

        if response.data:
            return response.data[0]
        return None

    def get_by_desk(self, desk_id: str) -> List[Dict[str, Any]]:
        """Get sensors assigned to a specific desk.

        Args:
            desk_id: Desk identifier

        Returns:
            List of sensors for this desk
        """
        response = self.client.table("dali_sensors").select("*").eq("desk_id", desk_id).execute()

        return response.data

    def get_occupied_zones(self, building_id: str) -> List[Dict[str, Any]]:
        """Get all sensors showing occupancy in a building.

        Args:
            building_id: Building UUID

        Returns:
            List of sensors with occupancy = TRUE
        """
        response = (
            self.client.table("dali_sensors").select("*").eq("building_id", building_id).eq("occupancy", True).execute()
        )

        return response.data

    def upsert(self, sensor_data: Dict[str, Any]) -> Dict[str, Any]:
        """Insert or update a sensor.

        Args:
            sensor_data: Sensor data

        Returns:
            Upserted sensor data
        """
        response = self.client.table("dali_sensors").upsert(sensor_data, on_conflict="building_id,sensor_id").execute()
        return response.data[0] if response.data else {}


class LightingGroupRepository:
    """Repository for lighting group/scene operations."""

    def __init__(self):
        """Initialize the repository with a Supabase client."""
        self.client = get_supabase_client()

    def get_all(self, building_id: Optional[str] = None, controller_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get all groups with optional filtering.

        Args:
            building_id: Filter by building UUID
            controller_id: Filter by controller UUID

        Returns:
            List of groups
        """
        query = self.client.table("dali_groups").select("*")

        if building_id:
            query = query.eq("building_id", building_id)
        if controller_id:
            query = query.eq("controller_id", controller_id)

        response = query.execute()
        return response.data

    def get_by_id(self, building_id: str, group_id: str) -> Optional[Dict[str, Any]]:
        """Get group by building and group_id composite key.

        Args:
            building_id: Building UUID
            group_id: Group identifier (e.g., 'GRP-L12-N-001')

        Returns:
            Group data or None if not found
        """
        response = (
            self.client.table("dali_groups")
            .select("*")
            .eq("building_id", building_id)
            .eq("group_id", group_id)
            .execute()
        )

        if response.data:
            return response.data[0]
        return None

    def upsert(self, group_data: Dict[str, Any]) -> Dict[str, Any]:
        """Insert or update a group.

        Args:
            group_data: Group data

        Returns:
            Upserted group data
        """
        response = self.client.table("dali_groups").upsert(group_data, on_conflict="building_id,group_id").execute()
        return response.data[0] if response.data else {}

    def add_luminaire(self, building_id: str, group_id: str, luminaire_uuid: str) -> Optional[Dict[str, Any]]:
        """Add a luminaire to a group.

        Args:
            building_id: Building UUID
            group_id: Group identifier
            luminaire_uuid: Luminaire UUID to add

        Returns:
            Updated group or None if not found
        """
        group = self.get_by_id(building_id, group_id)
        if not group:
            return None

        luminaire_ids = group.get("luminaire_ids", [])
        if luminaire_uuid not in luminaire_ids:
            luminaire_ids.append(luminaire_uuid)

        response = (
            self.client.table("dali_groups")
            .update({"luminaire_ids": luminaire_ids})
            .eq("building_id", building_id)
            .eq("group_id", group_id)
            .execute()
        )

        if response.data:
            return response.data[0]
        return None

    def remove_luminaire(self, building_id: str, group_id: str, luminaire_uuid: str) -> Optional[Dict[str, Any]]:
        """Remove a luminaire from a group.

        Args:
            building_id: Building UUID
            group_id: Group identifier
            luminaire_uuid: Luminaire UUID to remove

        Returns:
            Updated group or None if not found
        """
        group = self.get_by_id(building_id, group_id)
        if not group:
            return None

        luminaire_ids = group.get("luminaire_ids", [])
        if luminaire_uuid in luminaire_ids:
            luminaire_ids.remove(luminaire_uuid)

        response = (
            self.client.table("dali_groups")
            .update({"luminaire_ids": luminaire_ids})
            .eq("building_id", building_id)
            .eq("group_id", group_id)
            .execute()
        )

        if response.data:
            return response.data[0]
        return None

    def update_scene(
        self, building_id: str, group_id: str, scene_name: str, scene_config: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Update a scene configuration in a group.

        Args:
            building_id: Building UUID
            group_id: Group identifier
            scene_name: Scene name (e.g., 'full_bright', 'working')
            scene_config: Scene configuration (e.g., {'level': 80, 'color_temp': 4000})

        Returns:
            Updated group or None if not found
        """
        group = self.get_by_id(building_id, group_id)
        if not group:
            return None

        scene_levels = group.get("scene_levels", {})
        scene_levels[scene_name] = scene_config

        response = (
            self.client.table("dali_groups")
            .update({"scene_levels": scene_levels})
            .eq("building_id", building_id)
            .eq("group_id", group_id)
            .execute()
        )

        if response.data:
            return response.data[0]
        return None
