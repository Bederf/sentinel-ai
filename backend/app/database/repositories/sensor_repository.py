"""Repository for sensor operations."""

from typing import List, Optional, Dict, Any
from app.database.supabase_client import get_supabase_client


class SensorRepository:
    """Repository for sensor database operations."""

    def __init__(self):
        """Initialize the repository with a Supabase client."""
        self.client = get_supabase_client()

    def get_all(self, equipment_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get all sensors with optional filtering.

        Args:
            equipment_id: Filter by equipment UUID

        Returns:
            List of sensors
        """
        query = self.client.table('sensors').select("*")

        if equipment_id:
            query = query.eq('equipment_id', equipment_id)

        response = query.execute()
        return response.data

    def get_by_id(self, sensor_id: str) -> Optional[Dict[str, Any]]:
        """Get sensor by its code.

        Args:
            sensor_id: Sensor code

        Returns:
            Sensor data or None if not found
        """
        response = self.client.table('sensors').select("*").eq(
            'code', sensor_id
        ).execute()

        if response.data:
            return response.data[0]
        return None

    def get_by_uuid(self, uuid: str) -> Optional[Dict[str, Any]]:
        """Get sensor by its UUID.

        Args:
            uuid: Sensor UUID

        Returns:
            Sensor data or None if not found
        """
        response = self.client.table('sensors').select("*").eq('id', uuid).execute()

        if response.data:
            return response.data[0]
        return None

    def get_by_equipment(self, equipment_uuid: str) -> List[Dict[str, Any]]:
        """Get sensors for equipment.

        Args:
            equipment_uuid: Equipment UUID

        Returns:
            List of sensors
        """
        response = self.client.table('sensors').select("*").eq(
            'equipment_id', equipment_uuid
        ).execute()

        return response.data

    def get_by_type(self, sensor_type: str) -> List[Dict[str, Any]]:
        """Get sensors by type.

        Args:
            sensor_type: Sensor type

        Returns:
            List of sensors
        """
        response = self.client.table('sensors').select("*").eq(
            'type', sensor_type
        ).execute()

        return response.data

    def create(self, sensor_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new sensor.

        Args:
            sensor_data: Sensor data

        Returns:
            Created sensor
        """
        response = self.client.table('sensors').insert(sensor_data).execute()
        return response.data[0]

    def update(self, sensor_id: str, sensor_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update a sensor.

        Args:
            sensor_id: Sensor code
            sensor_data: Data to update

        Returns:
            Updated sensor or None if not found
        """
        sensor = self.get_by_id(sensor_id)
        if not sensor:
            return None

        response = self.client.table('sensors').update(
            sensor_data
        ).eq('id', sensor['id']).execute()

        if response.data:
            return response.data[0]
        return None

    def delete(self, sensor_id: str) -> bool:
        """Delete a sensor.

        Args:
            sensor_id: Sensor code

        Returns:
            True if deleted, False if not found
        """
        sensor = self.get_by_id(sensor_id)
        if not sensor:
            return False

        response = self.client.table('sensors').delete().eq(
            'id', sensor['id']
        ).execute()

        return len(response.data) > 0
