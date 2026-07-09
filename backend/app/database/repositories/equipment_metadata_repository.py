"""Equipment Metadata Repository - CRUD operations for equipment metadata and notes."""

import json
from datetime import datetime

from app.database.supabase_client import get_supabase_client


class EquipmentMetadataRepository:
    """Repository for equipment metadata operations."""

    def __init__(self):
        """Initialize the repository with a Supabase client."""
        self.client = get_supabase_client()

    def get_equipment_metadata(self, equipment_id: str) -> dict | None:
        """Get full metadata for equipment by ID or code.

        Args:
            equipment_id: Equipment UUID or code

        Returns:
            Equipment record with metadata fields, or None if not found
        """
        # Try by UUID first, then by code
        query = self.client.table("equipment").select(
            "id, code, name, type, manufacturer, model, serial_number, capacity, "
            "notes, network_info, device_info, operating_data, "
            "commissioning_date, warranty_expiry, last_discovery, "
            "install_date, last_service, status, health_score, location, "
            "service_provider_name, service_interval_days, baseline_state, last_rollup_at"
        )

        # Check if it looks like a UUID
        if len(equipment_id) == 36 and "-" in equipment_id:
            response = query.eq("id", equipment_id).execute()
        else:
            response = query.eq("code", equipment_id).execute()

        if response.data:
            return response.data[0]
        return None

    def update_notes(self, equipment_id: str, notes: str, changed_by: str, change_reason: str | None = None) -> dict:
        """Update equipment notes with audit trail.

        Args:
            equipment_id: Equipment UUID or code
            notes: New notes content
            changed_by: User making the change
            change_reason: Optional reason for change

        Returns:
            Updated equipment record
        """
        # Set session variables for audit trigger
        try:
            self.client.rpc("set_config", {"setting": "app.current_user", "value": changed_by}).execute()
            if change_reason:
                self.client.rpc("set_config", {"setting": "app.change_reason", "value": change_reason}).execute()
        except Exception:
            # Session variables may not be supported, continue anyway
            pass

        # Find equipment
        eq = self.get_equipment_metadata(equipment_id)
        if not eq:
            raise ValueError(f"Equipment {equipment_id} not found")

        # Update notes
        response = (
            self.client.table("equipment")
            .update({"notes": notes, "updated_at": datetime.utcnow().isoformat()})
            .eq("id", eq["id"])
            .execute()
        )

        if response.data:
            return response.data[0]
        raise ValueError("Failed to update notes")

    def update_network_info(self, equipment_id: str, network_info: dict, merge: bool = True) -> dict:
        """Update equipment network information.

        Args:
            equipment_id: Equipment UUID or code
            network_info: Network info dict (ip_address, mac_address, dali_address, etc.)
            merge: If True, merge with existing; if False, replace

        Returns:
            Updated equipment record
        """
        eq = self.get_equipment_metadata(equipment_id)
        if not eq:
            raise ValueError(f"Equipment {equipment_id} not found")

        if merge and eq.get("network_info"):
            existing = eq["network_info"] if isinstance(eq["network_info"], dict) else {}
            network_info = {**existing, **network_info}

        response = (
            self.client.table("equipment")
            .update({"network_info": network_info, "updated_at": datetime.utcnow().isoformat()})
            .eq("id", eq["id"])
            .execute()
        )

        if response.data:
            return response.data[0]
        raise ValueError("Failed to update network_info")

    def update_device_info(self, equipment_id: str, device_info: dict, merge: bool = True) -> dict:
        """Update equipment device information (from discovery).

        Args:
            equipment_id: Equipment UUID or code
            device_info: Device info dict (gtin, serial, manufacturer, firmware, etc.)
            merge: If True, merge with existing; if False, replace

        Returns:
            Updated equipment record
        """
        eq = self.get_equipment_metadata(equipment_id)
        if not eq:
            raise ValueError(f"Equipment {equipment_id} not found")

        if merge and eq.get("device_info"):
            existing = eq["device_info"] if isinstance(eq["device_info"], dict) else {}
            device_info = {**existing, **device_info}

        response = (
            self.client.table("equipment")
            .update(
                {
                    "device_info": device_info,
                    "last_discovery": datetime.utcnow().isoformat(),
                    "updated_at": datetime.utcnow().isoformat(),
                }
            )
            .eq("id", eq["id"])
            .execute()
        )

        if response.data:
            return response.data[0]
        raise ValueError("Failed to update device_info")

    def update_operating_data(self, equipment_id: str, operating_data: dict, merge: bool = True) -> dict:
        """Update equipment operating data (lamp hours, cycles, etc.).

        Args:
            equipment_id: Equipment UUID or code
            operating_data: Operating data dict
            merge: If True, merge with existing; if False, replace

        Returns:
            Updated equipment record
        """
        eq = self.get_equipment_metadata(equipment_id)
        if not eq:
            raise ValueError(f"Equipment {equipment_id} not found")

        if merge and eq.get("operating_data"):
            existing = eq["operating_data"] if isinstance(eq["operating_data"], dict) else {}
            operating_data = {**existing, **operating_data}

        response = (
            self.client.table("equipment")
            .update({"operating_data": operating_data, "updated_at": datetime.utcnow().isoformat()})
            .eq("id", eq["id"])
            .execute()
        )

        if response.data:
            return response.data[0]
        raise ValueError("Failed to update operating_data")

    def update_from_discovery(
        self,
        equipment_id: str,
        network_info: dict | None = None,
        device_info: dict | None = None,
        operating_data: dict | None = None,
    ) -> dict:
        """Update equipment from auto-discovery (DALI, BACnet, etc.).

        Merges all provided data and updates last_discovery timestamp.

        Args:
            equipment_id: Equipment UUID or code
            network_info: Network configuration discovered
            device_info: Device identification discovered
            operating_data: Operating statistics discovered

        Returns:
            Updated equipment record
        """
        eq = self.get_equipment_metadata(equipment_id)
        if not eq:
            raise ValueError(f"Equipment {equipment_id} not found")

        updates = {"last_discovery": datetime.utcnow().isoformat(), "updated_at": datetime.utcnow().isoformat()}

        if network_info:
            existing = eq.get("network_info") or {}
            if isinstance(existing, str):
                existing = json.loads(existing)
            updates["network_info"] = {**existing, **network_info}

        if device_info:
            existing = eq.get("device_info") or {}
            if isinstance(existing, str):
                existing = json.loads(existing)
            updates["device_info"] = {**existing, **device_info}

        if operating_data:
            existing = eq.get("operating_data") or {}
            if isinstance(existing, str):
                existing = json.loads(existing)
            updates["operating_data"] = {**existing, **operating_data}

        response = self.client.table("equipment").update(updates).eq("id", eq["id"]).execute()

        if response.data:
            return response.data[0]
        raise ValueError("Failed to update from discovery")

    def get_notes_history(self, equipment_id: str, limit: int = 20) -> list:
        """Get notes change history for equipment.

        Args:
            equipment_id: Equipment UUID or code
            limit: Max records to return

        Returns:
            List of notes history records
        """
        eq = self.get_equipment_metadata(equipment_id)
        if not eq:
            return []

        response = (
            self.client.table("equipment_notes_history")
            .select("*")
            .eq("equipment_id", eq["id"])
            .order("changed_at", desc=True)
            .limit(limit)
            .execute()
        )

        return response.data or []

    def set_commissioning_info(
        self, equipment_id: str, commissioning_date: str | None = None, warranty_expiry: str | None = None
    ) -> dict:
        """Set commissioning and warranty dates.

        Args:
            equipment_id: Equipment UUID or code
            commissioning_date: Date commissioned (YYYY-MM-DD)
            warranty_expiry: Warranty expiry date (YYYY-MM-DD)

        Returns:
            Updated equipment record
        """
        eq = self.get_equipment_metadata(equipment_id)
        if not eq:
            raise ValueError(f"Equipment {equipment_id} not found")

        updates = {"updated_at": datetime.utcnow().isoformat()}
        if commissioning_date:
            updates["commissioning_date"] = commissioning_date
        if warranty_expiry:
            updates["warranty_expiry"] = warranty_expiry

        response = self.client.table("equipment").update(updates).eq("id", eq["id"]).execute()

        if response.data:
            return response.data[0]
        raise ValueError("Failed to update commissioning info")

    def search_by_network_info(self, search_key: str, search_value: str) -> list:
        """Search equipment by network info field.

        Args:
            search_key: Key to search (e.g., 'ip_address', 'mac_address')
            search_value: Value to match

        Returns:
            List of matching equipment records
        """
        # Use JSONB containment operator
        response = (
            self.client.table("equipment")
            .select("id, code, name, type, network_info, device_info")
            .filter("network_info", "cs", json.dumps({search_key: search_value}))
            .execute()
        )

        return response.data or []
