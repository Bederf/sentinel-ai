"""Repository for BMS device operations.

This repository handles CRUD operations for the devices table,
which represents the BMS control layer (protocol-agnostic device abstraction).
"""

import logging
from typing import Any

from app.database.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)


class DeviceRepository:
    """Repository for BMS device database operations."""

    def __init__(self):
        """Initialize the repository with a Supabase client."""
        self.client = get_supabase_client()

    def get_all(
        self, site_id: str | None = None, device_type: str | None = None, status: str | None = None
    ) -> list[dict[str, Any]]:
        """Get all devices with optional filtering.

        Args:
            site_id: Filter by building UUID
            device_type: Filter by device type (hvac, lighting, security, etc.)
            status: Filter by status (online, offline, fault, etc.)

        Returns:
            List of devices
        """
        query = self.client.table("devices").select("*")

        if site_id:
            query = query.eq("site_id", site_id)
        if device_type:
            query = query.eq("device_type", device_type)
        if status:
            query = query.eq("status", status)

        response = query.execute()
        return response.data

    def get_by_id(self, site_id: str, device_id: str) -> dict[str, Any] | None:
        """Get device by building and device_id composite key.

        Args:
            site_id: Building UUID
            device_id: Device identifier (e.g., 'S001-CHILLER-B1-001')

        Returns:
            Device data or None if not found
        """
        response = self.client.table("devices").select("*").eq("site_id", site_id).eq("device_id", device_id).execute()

        if response.data:
            return response.data[0]
        return None

    def get_by_uuid(self, uuid: str) -> dict[str, Any] | None:
        """Get device by its UUID.

        Args:
            uuid: Device UUID

        Returns:
            Device data or None if not found
        """
        response = self.client.table("devices").select("*").eq("id", uuid).execute()

        if response.data:
            return response.data[0]
        return None

    def get_by_site_code(self, site_code: str) -> list[dict[str, Any]]:
        """Get devices by building code.

        Args:
            site_code: Building code (e.g., 'sandton')

        Returns:
            List of devices
        """
        # First get the building UUID
        site_response = self.client.table("sites").select("id").eq("code", site_code).execute()

        if not site_response.data:
            return []

        site_uuid = site_response.data[0]["id"]

        # Get devices for this building
        response = self.client.table("devices").select("*").eq("site_id", site_uuid).execute()

        return response.data

    def get_by_equipment(self, equipment_id: str) -> list[dict[str, Any]]:
        """Get devices linked to specific equipment.

        Args:
            equipment_id: Equipment UUID

        Returns:
            List of devices controlling this equipment
        """
        response = self.client.table("devices").select("*").eq("equipment_id", equipment_id).execute()

        return response.data

    def get_by_zone(self, zone_id: str) -> list[dict[str, Any]]:
        """Get devices in a specific HVAC zone.

        Args:
            zone_id: HVAC Zone UUID

        Returns:
            List of devices in this zone
        """
        response = self.client.table("devices").select("*").eq("zone_id", zone_id).execute()

        return response.data

    def get_with_details(self, site_id: str | None = None) -> list[dict[str, Any]]:
        """Get devices with enriched building/equipment/zone details.

        Uses the v_devices_with_equipment view for efficient joins.

        Args:
            site_id: Optional filter by building UUID

        Returns:
            List of enriched device records
        """
        query = self.client.table("v_devices_with_equipment").select("*")

        if site_id:
            query = query.eq("site_id", site_id)

        response = query.execute()
        return response.data

    def get_fault_devices(self, site_id: str | None = None) -> list[dict[str, Any]]:
        """Get all devices with fault status.

        Args:
            site_id: Optional filter by building UUID

        Returns:
            List of devices in fault state
        """
        query = self.client.table("devices").select("*").eq("status", "fault")

        if site_id:
            query = query.eq("site_id", site_id)

        response = query.execute()
        return response.data

    def get_offline_devices(self, site_id: str | None = None) -> list[dict[str, Any]]:
        """Get all offline devices.

        Args:
            site_id: Optional filter by building UUID

        Returns:
            List of offline devices
        """
        query = self.client.table("devices").select("*").eq("status", "offline")

        if site_id:
            query = query.eq("site_id", site_id)

        response = query.execute()
        return response.data

    def create(self, device_data: dict[str, Any]) -> dict[str, Any]:
        """Create a new device.

        Args:
            device_data: Device data including site_id, device_id, name, etc.

        Returns:
            Created device
        """
        response = self.client.table("devices").insert(device_data).execute()
        return response.data[0]

    def upsert(self, device_data: dict[str, Any]) -> dict[str, Any]:
        """Insert or update a device.

        Uses composite unique constraint (site_id, device_id).

        Args:
            device_data: Device data

        Returns:
            Upserted device data
        """
        response = self.client.table("devices").upsert(device_data, on_conflict="site_id,device_id").execute()
        return response.data[0] if response.data else {}

    def upsert_many(self, devices: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Insert or update multiple devices.

        Args:
            devices: List of device data dicts

        Returns:
            List of upserted devices
        """
        if not devices:
            return []

        response = self.client.table("devices").upsert(devices, on_conflict="site_id,device_id").execute()
        return response.data

    def update(self, site_id: str, device_id: str, device_data: dict[str, Any]) -> dict[str, Any] | None:
        """Update a device.

        Args:
            site_id: Building UUID
            device_id: Device identifier
            device_data: Data to update

        Returns:
            Updated device or None if not found
        """
        response = (
            self.client.table("devices").update(device_data).eq("site_id", site_id).eq("device_id", device_id).execute()
        )

        if response.data:
            return response.data[0]
        return None

    def update_by_uuid(self, uuid: str, device_data: dict[str, Any]) -> dict[str, Any] | None:
        """Update a device by UUID.

        Args:
            uuid: Device UUID
            device_data: Data to update

        Returns:
            Updated device or None if not found
        """
        response = self.client.table("devices").update(device_data).eq("id", uuid).execute()

        if response.data:
            return response.data[0]
        return None

    def delete(self, site_id: str, device_id: str) -> bool:
        """Delete a device.

        Args:
            site_id: Building UUID
            device_id: Device identifier

        Returns:
            True if deleted, False if not found
        """
        response = self.client.table("devices").delete().eq("site_id", site_id).eq("device_id", device_id).execute()

        return len(response.data) > 0

    def delete_by_uuid(self, uuid: str) -> bool:
        """Delete a device by UUID.

        Args:
            uuid: Device UUID

        Returns:
            True if deleted, False if not found
        """
        response = self.client.table("devices").delete().eq("id", uuid).execute()
        return len(response.data) > 0

    def update_status(self, site_id: str, device_id: str, status: str) -> dict[str, Any] | None:
        """Update device status.

        Args:
            site_id: Building UUID
            device_id: Device identifier
            status: New status ('online', 'offline', 'fault', 'maintenance', 'standby')

        Returns:
            Updated device or None if not found
        """
        return self.update(site_id, device_id, {"status": status})

    def update_last_seen(self, site_id: str, device_id: str) -> dict[str, Any] | None:
        """Update device last_seen timestamp to NOW.

        Uses the optimized update_device_last_seen function.

        Args:
            site_id: Building UUID
            device_id: Device identifier

        Returns:
            None (function returns VOID for performance)
        """
        # Use the stored function for fast heartbeat updates
        try:
            self.client.rpc("update_device_last_seen", {"p_device_id": device_id, "p_site_id": site_id}).execute()
            return None
        except Exception as e:
            logger.error(f"Failed to update last_seen for device {device_id}: {e}")
            return None

    def update_points(self, site_id: str, device_id: str, points: dict[str, Any]) -> dict[str, Any] | None:
        """Update device points (control/monitoring points).

        Args:
            site_id: Building UUID
            device_id: Device identifier
            points: Points JSONB object

        Returns:
            Updated device or None if not found
        """
        return self.update(site_id, device_id, {"points": points})

    def get_site_summary(self, site_id: str) -> dict[str, Any] | None:
        """Get device summary for a building.

        Uses the v_site_device_summary view.

        Args:
            site_id: Building UUID

        Returns:
            Device summary with counts by type and status
        """
        response = self.client.table("v_site_device_summary").select("*").eq("site_id", site_id).execute()

        if response.data:
            return response.data[0]
        return None
