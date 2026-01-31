"""Repository for HVAC zone operations."""

from typing import List, Optional, Dict, Any
import logging
from app.database.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)


class HVACZoneRepository:
    """Repository for HVAC zone database operations."""

    def __init__(self):
        """Initialize the repository with a Supabase client."""
        self.client = get_supabase_client()

    def get_all(self, building_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get all HVAC zones with optional building filter.

        Args:
            building_id: Filter by building UUID

        Returns:
            List of HVAC zones
        """
        query = self.client.table('hvac_zones').select("*")

        if building_id:
            query = query.eq('building_id', building_id)

        response = query.execute()
        return response.data

    def get_by_building_code(self, building_code: str) -> List[Dict[str, Any]]:
        """Get HVAC zones by building code.

        Args:
            building_code: Building code (e.g., 'sandton')

        Returns:
            List of HVAC zones
        """
        # First get the building UUID
        building_response = self.client.table('buildings').select('id').eq(
            'code', building_code
        ).execute()

        if not building_response.data:
            return []

        building_uuid = building_response.data[0]['id']

        response = self.client.table('hvac_zones').select("*").eq(
            'building_id', building_uuid
        ).execute()

        return response.data

    def get_by_zone_id(self, zone_id: str) -> Optional[Dict[str, Any]]:
        """Get HVAC zone by zone_id.

        Args:
            zone_id: Zone ID (e.g., 'Zone-L12-N')

        Returns:
            Zone data or None if not found
        """
        response = self.client.table('hvac_zones').select("*").eq(
            'zone_id', zone_id
        ).execute()

        if response.data:
            return response.data[0]
        return None

    def get_by_uuid(self, uuid: str) -> Optional[Dict[str, Any]]:
        """Get HVAC zone by UUID.

        Args:
            uuid: Zone UUID

        Returns:
            Zone data or None if not found
        """
        response = self.client.table('hvac_zones').select("*").eq(
            'id', uuid
        ).execute()

        if response.data:
            return response.data[0]
        return None

    def get_building_uuid(self, building_code: str) -> Optional[str]:
        """Get building UUID from building code.

        Args:
            building_code: Building code (e.g., 'sandton')

        Returns:
            Building UUID or None
        """
        response = self.client.table('buildings').select('id').eq(
            'code', building_code
        ).execute()

        if response.data:
            return response.data[0]['id']
        return None

    def upsert(self, zone_data: Dict[str, Any]) -> Dict[str, Any]:
        """Insert or update an HVAC zone.

        Args:
            zone_data: Zone data with zone_id as unique key

        Returns:
            Upserted zone data
        """
        response = self.client.table('hvac_zones').upsert(
            zone_data,
            on_conflict='zone_id'
        ).execute()
        return response.data[0] if response.data else {}

    def upsert_many(self, zones: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Insert or update multiple HVAC zones.

        Args:
            zones: List of zone data dicts

        Returns:
            List of upserted zones
        """
        if not zones:
            return []

        response = self.client.table('hvac_zones').upsert(
            zones,
            on_conflict='zone_id'
        ).execute()
        return response.data

    def create(self, zone_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new HVAC zone.

        Args:
            zone_data: Zone data

        Returns:
            Created zone
        """
        response = self.client.table('hvac_zones').insert(zone_data).execute()
        return response.data[0]

    def update(self, zone_id: str, zone_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update an HVAC zone.

        Args:
            zone_id: Zone ID
            zone_data: Data to update

        Returns:
            Updated zone or None if not found
        """
        response = self.client.table('hvac_zones').update(
            zone_data
        ).eq('zone_id', zone_id).execute()

        if response.data:
            return response.data[0]
        return None

    def delete(self, zone_id: str) -> bool:
        """Delete an HVAC zone.

        Args:
            zone_id: Zone ID

        Returns:
            True if deleted, False if not found
        """
        response = self.client.table('hvac_zones').delete().eq(
            'zone_id', zone_id
        ).execute()

        return len(response.data) > 0

    def delete_by_building(self, building_code: str) -> int:
        """Delete all HVAC zones for a building.

        Args:
            building_code: Building code

        Returns:
            Number of zones deleted
        """
        building_uuid = self.get_building_uuid(building_code)
        if not building_uuid:
            return 0

        response = self.client.table('hvac_zones').delete().eq(
            'building_id', building_uuid
        ).execute()

        return len(response.data)

    def update_setpoint(self, zone_id: str, setpoint: float) -> Optional[Dict[str, Any]]:
        """Update zone setpoint temperature.

        Args:
            zone_id: Zone ID
            setpoint: New setpoint temperature

        Returns:
            Updated zone or None if not found
        """
        return self.update(zone_id, {'setpoint': setpoint})

    def update_status(self, zone_id: str, status: str) -> Optional[Dict[str, Any]]:
        """Update zone status.

        Args:
            zone_id: Zone ID
            status: New status ('running', 'idle', 'heating', 'cooling', 'fault', 'offline')

        Returns:
            Updated zone or None if not found
        """
        return self.update(zone_id, {'status': status})

    def update_current_temp(self, zone_id: str, temp: float) -> Optional[Dict[str, Any]]:
        """Update current zone temperature.

        Args:
            zone_id: Zone ID
            temp: Current temperature

        Returns:
            Updated zone or None if not found
        """
        return self.update(zone_id, {'current_temp': temp})
