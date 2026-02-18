"""Repository for desk operations."""

from typing import List, Optional, Dict, Any
import logging
import time
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
                if '429' in error_msg or 'rate limit' in error_msg.lower():
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

    def get_all(self, building_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get all desks with optional building filter.

        Args:
            building_id: Filter by building UUID

        Returns:
            List of desks
        """
        query = self.client.table('desks').select("*")

        if building_id:
            query = query.eq('building_id', building_id)

        response = query.execute()
        return response.data

    def get_by_building_code(self, building_code: str) -> List[Dict[str, Any]]:
        """Get desks by building code with zone_id resolved.

        Args:
            building_code: Building code (e.g., 'sandton' or 'site-002')

        Returns:
            List of desks with zone_id (string) from hvac_zones join
        """
        building_uuid = self.get_building_uuid(building_code)
        if not building_uuid:
            return []

        # Join with hvac_zones to get zone_id string
        response = self.client.table('desks').select(
            "*, hvac_zones(zone_id, zone_name)"
        ).eq('building_id', building_uuid).execute()

        # Flatten hvac_zones data into desk dict
        desks = []
        for desk in response.data:
            hvac_zone = desk.pop('hvac_zones', None)
            if hvac_zone:
                desk['zone_id'] = hvac_zone.get('zone_id', '')
                desk['zone_name'] = hvac_zone.get('zone_name', '')
            else:
                desk['zone_id'] = ''
                desk['zone_name'] = ''
            desks.append(desk)

        return desks

    def get_by_desk_id(self, desk_id: str) -> Optional[Dict[str, Any]]:
        """Get desk by desk_id.

        Args:
            desk_id: Desk ID (e.g., 'L12-D001')

        Returns:
            Desk data or None if not found
        """
        response = self.client.table('desks').select("*").eq(
            'desk_id', desk_id
        ).execute()

        if response.data:
            return response.data[0]
        return None

    def get_by_uuid(self, uuid: str) -> Optional[Dict[str, Any]]:
        """Get desk by UUID.

        Args:
            uuid: Desk UUID

        Returns:
            Desk data or None if not found
        """
        response = self.client.table('desks').select("*").eq(
            'id', uuid
        ).execute()

        if response.data:
            return response.data[0]
        return None

    def get_by_zone(self, hvac_zone_id: str) -> List[Dict[str, Any]]:
        """Get desks by HVAC zone UUID.

        Args:
            hvac_zone_id: HVAC zone UUID

        Returns:
            List of desks in the zone
        """
        response = self.client.table('desks').select("*").eq(
            'hvac_zone_id', hvac_zone_id
        ).execute()

        return response.data

    def get_by_floor(self, building_code: str, floor: str) -> List[Dict[str, Any]]:
        """Get desks by building and floor.

        Args:
            building_code: Building code
            floor: Floor identifier

        Returns:
            List of desks on the floor
        """
        building_uuid = self.get_building_uuid(building_code)
        if not building_uuid:
            return []

        response = self.client.table('desks').select("*").eq(
            'building_id', building_uuid
        ).eq('floor', floor).execute()

        return response.data

    def find_desk(self, desk_id: str, building_code: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Find a desk by ID, optionally filtered by building.

        Handles various desk ID formats (e.g., '201', 'desk 201', 'L12-D001').

        Args:
            desk_id: Desk ID to search for
            building_code: Optional building code filter

        Returns:
            Desk data or None if not found
        """
        # Normalize desk ID
        normalized = desk_id.strip().lower()
        normalized = normalized.replace("desk ", "").strip()

        # Build query
        query = self.client.table('desks').select("*")

        if building_code:
            building_uuid = self.get_building_uuid(building_code)
            if building_uuid:
                query = query.eq('building_id', building_uuid)

        # Try exact match first
        response = query.ilike('desk_id', normalized).execute()
        if response.data:
            return response.data[0]

        # Try suffix match (e.g., '201' matches 'L12-D201')
        response = query.ilike('desk_id', f'%{normalized}').execute()
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

    def get_hvac_zone_uuid(self, zone_id: str) -> Optional[str]:
        """Get HVAC zone UUID from zone_id.

        Args:
            zone_id: Zone ID (e.g., 'Zone-L12-N')

        Returns:
            Zone UUID or None
        """
        response = self.client.table('hvac_zones').select('id').eq(
            'zone_id', zone_id
        ).execute()

        if response.data:
            return response.data[0]['id']
        return None

    def upsert(self, desk_data: Dict[str, Any]) -> Dict[str, Any]:
        """Insert or update a desk.

        Args:
            desk_data: Desk data with desk_id as unique key

        Returns:
            Upserted desk data
        """
        response = self.client.table('desks').upsert(
            desk_data,
            on_conflict='desk_id'
        ).execute()
        return response.data[0] if response.data else {}

    def upsert_many(self, desks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Insert or update multiple desks.

        Args:
            desks: List of desk data dicts

        Returns:
            List of upserted desks
        """
        if not desks:
            return []

        response = self.client.table('desks').upsert(
            desks,
            on_conflict='desk_id'
        ).execute()
        return response.data

    def create(self, desk_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new desk.

        Args:
            desk_data: Desk data

        Returns:
            Created desk
        """
        response = self.client.table('desks').insert(desk_data).execute()
        return response.data[0]

    def update(self, desk_id: str, desk_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update a desk.

        Args:
            desk_id: Desk ID
            desk_data: Data to update

        Returns:
            Updated desk or None if not found
        """
        response = self.client.table('desks').update(
            desk_data
        ).eq('desk_id', desk_id).execute()

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
        response = self.client.table('desks').delete().eq(
            'desk_id', desk_id
        ).execute()

        return len(response.data) > 0

    def delete_by_building(self, building_code: str) -> int:
        """Delete all desks for a building.

        Args:
            building_code: Building code

        Returns:
            Number of desks deleted
        """
        building_uuid = self.get_building_uuid(building_code)
        if not building_uuid:
            return 0

        response = self.client.table('desks').delete().eq(
            'building_id', building_uuid
        ).execute()

        return len(response.data)

    def get_with_comfort_context(self, desk_id: str) -> Optional[Dict[str, Any]]:
        """Get desk with full comfort context (HVAC zone, DALI zone).

        Args:
            desk_id: Desk ID

        Returns:
            Desk with related zone data or None
        """
        # Get desk with HVAC zone join
        response = self.client.table('desks').select(
            "*, hvac_zones(zone_id, zone_name, current_temp, setpoint, status)"
        ).eq('desk_id', desk_id).execute()

        if response.data:
            return response.data[0]
        return None

    def get_by_building_uuid(self, building_id: str) -> List[Dict[str, Any]]:
        """Get all desks for a building UUID.

        Args:
            building_id: Building UUID

        Returns:
            List of desks in the building
        """
        query = self.client.table('desks').select("*").eq('building_id', building_id)
        response = self._execute_with_retry(query)
        return response.data

    def get_by_zone_id(self, building_id: str, zone_id: str) -> List[Dict[str, Any]]:
        """Get desks by building-level zone ID.

        Args:
            building_id: Building UUID
            zone_id: Zone ID (e.g., 'Zone-L1-A')

        Returns:
            List of desks in the zone
        """
        response = self.client.table('desks').select("*").eq(
            'building_id', building_id
        ).eq('zone_id', zone_id).execute()

        return response.data

    def get_centroids_for_zones(
        self, building_id: str, zones: List[str]
    ) -> Dict[str, Dict[str, float]]:
        """Get centroids for specific zones from desk positions.

        Args:
            building_id: Building UUID
            zones: List of zone IDs

        Returns:
            Dict mapping zone_id → {x: avg_x, z: avg_z}
        """
        all_desks = self.get_by_building_uuid(building_id)
        centroids = {}

        for zone_id in zones:
            zone_desks = [d for d in all_desks if d.get('zone_id') == zone_id]

            if zone_desks:
                avg_x = sum(float(d.get('x_coord', 0)) for d in zone_desks) / len(zone_desks)
                avg_z = sum(float(d.get('z_coord', 0)) for d in zone_desks) / len(zone_desks)
                centroids[zone_id] = {'x': round(avg_x, 2), 'z': round(avg_z, 2)}

        return centroids
