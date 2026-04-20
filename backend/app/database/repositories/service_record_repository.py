"""Repository for service record operations (Phase 41).

Handles CRUD operations for service records including
readings, attachments, and observations with Supabase integration.
"""

import builtins
from datetime import datetime
from typing import Any

from app.database.supabase_client import get_supabase_client


class ServiceRecordRepository:
    """Repository for service record data access."""

    def __init__(self):
        """Initialize the repository with a Supabase client."""
        self.client = get_supabase_client()
        self.table = "service_records"

    async def create(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a new service record."""
        response = self.client.table(self.table).insert(data).execute()
        return response.data[0] if response.data else {}

    async def get_by_id(self, record_id: str) -> dict[str, Any] | None:
        """Get service record by ID."""
        response = self.client.table(self.table).select("*").eq("id", record_id).execute()
        return response.data[0] if response.data else None

    async def get_detail(self, record_id: str) -> dict[str, Any] | None:
        """Get service record with all related data."""
        # Get base record
        record = await self.get_by_id(record_id)
        if not record:
            return None

        # Get related data
        readings = await self.list_readings(record_id)
        attachments = await self.list_attachments(record_id)
        observations = await self.list_observations(record_id)

        # Combine all data
        record["readings"] = readings
        record["attachments"] = attachments
        record["observations"] = observations

        return record

    async def list(self, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """List service records with optional filtering."""
        query = self.client.table(self.table).select("*")
        if filters:
            for key, value in filters.items():
                query = query.eq(key, value)
        response = query.execute()
        return response.data

    async def update(self, record_id: str, data: dict[str, Any]) -> dict[str, Any] | None:
        """Update service record."""
        data["updated_at"] = datetime.now().isoformat()
        response = self.client.table(self.table).update(data).eq("id", record_id).execute()
        return response.data[0] if response.data else None

    async def add_reading(self, record_id: str, reading_data: dict[str, Any]) -> dict[str, Any]:
        """Add a reading to service record."""
        reading_data["service_record_id"] = record_id
        response = self.client.table("service_readings").insert(reading_data).execute()
        return response.data[0] if response.data else {}

    async def list_readings(self, record_id: str) -> builtins.list[dict[str, Any]]:
        """Get all readings for a service record."""
        response = self.client.table("service_readings").select("*").eq("service_record_id", record_id).execute()
        return response.data

    async def add_attachment(self, attachment_data: dict[str, Any]) -> dict[str, Any]:
        """Add attachment to service record."""
        response = self.client.table("service_attachments").insert(attachment_data).execute()
        return response.data[0] if response.data else {}

    async def list_attachments(self, record_id: str) -> builtins.list[dict[str, Any]]:
        """Get all attachments for a service record."""
        response = self.client.table("service_attachments").select("*").eq("service_record_id", record_id).execute()
        return response.data

    async def add_observation(self, record_id: str, observation_data: dict[str, Any]) -> dict[str, Any]:
        """Add observation to service record."""
        observation_data["service_record_id"] = record_id
        response = self.client.table("service_observations").insert(observation_data).execute()
        return response.data[0] if response.data else {}

    async def list_observations(self, record_id: str) -> builtins.list[dict[str, Any]]:
        """Get all observations for a service record."""
        response = self.client.table("service_observations").select("*").eq("service_record_id", record_id).execute()
        return response.data

    async def get_equipment_by_id(self, equipment_id: str) -> dict[str, Any] | None:
        """Get equipment details by ID."""
        response = self.client.table("equipment").select("*").eq("id", equipment_id).execute()
        return response.data[0] if response.data else None

    async def equipment_exists(self, equipment_id: str) -> bool:
        """Check if equipment exists."""
        equipment = await self.get_equipment_by_id(equipment_id)
        return equipment is not None

    async def update_items_collected(self, record_id: str, item: str) -> dict[str, Any] | None:
        """Add item to collected items list."""
        # Get current record
        record = await self.get_by_id(record_id)
        if not record:
            return None

        # Get current items list
        items_collected = record.get("items_collected", [])

        # Add new item if not already present
        if item not in items_collected:
            items_collected.append(item)

        # Update record
        return await self.update(record_id, {"items_collected": items_collected})

    async def count_by_status(self, status: str) -> int:
        """Count service records by status."""
        response = self.client.table(self.table).select("id", count="exact").eq("status", status).execute()
        return len(response.data) if response.data else 0

    async def count_by_technician(self, technician_id: str) -> int:
        """Count active service records for technician."""
        response = (
            self.client.table(self.table)
            .select("id", count="exact")
            .eq("technician_id", technician_id)
            .neq("status", "closed")
            .execute()
        )
        return len(response.data) if response.data else 0
