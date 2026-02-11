"""Repository for equipment operations."""

from typing import List, Optional, Dict, Any
import time
import logging
from app.database.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)


class EquipmentRepository:
    """Repository for equipment database operations."""

    def __init__(self):
        """Initialize the repository with a Supabase client."""
        self.client = get_supabase_client()

    def _execute_with_retry(self, query, max_retries: int = 3):
        """Execute a Supabase query with retry on rate limit.
        
        Args:
            query: Supabase query object
            max_retries: Maximum number of retries
            
        Returns:
            Response data
        """
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
        """Get all equipment with optional filtering.

        Args:
            building_id: Filter by building UUID

        Returns:
            List of equipment items
        """
        query = self.client.table('equipment').select("*")

        if building_id:
            query = query.eq('building_id', building_id)

        response = query.execute()
        return response.data

    def get_by_id(self, equipment_id: str) -> Optional[Dict[str, Any]]:
        """Get equipment by its code.

        Args:
            equipment_id: Equipment code (e.g., "eqp-001")

        Returns:
            Equipment data or None if not found
        """
        response = self.client.table('equipment').select("*").eq(
            'code', equipment_id
        ).execute()

        if response.data:
            return response.data[0]
        return None

    def get_by_uuid(self, uuid: str) -> Optional[Dict[str, Any]]:
        """Get equipment by its UUID.

        Args:
            uuid: Equipment UUID

        Returns:
            Equipment data or None if not found
        """
        response = self.client.table('equipment').select("*").eq('id', uuid).execute()

        if response.data:
            return response.data[0]
        return None

    def get_by_building_code(self, building_code: str) -> List[Dict[str, Any]]:
        """Get equipment by building code.

        Args:
            building_code: Building code (e.g., "site-001")

        Returns:
            List of equipment items
        """
        # First get the building UUID (with retry)
        building_query = self.client.table('buildings').select('id').eq('code', building_code)
        building_response = self._execute_with_retry(building_query)

        if not building_response.data:
            return []

        building_uuid = building_response.data[0]['id']

        # Get equipment for this building (with retry)
        equipment_query = self.client.table('equipment').select("*").eq('building_id', building_uuid)
        equipment_response = self._execute_with_retry(equipment_query)

        return equipment_response.data

    def get_by_type(self, equipment_type: str) -> List[Dict[str, Any]]:
        """Get equipment by type.

        Args:
            equipment_type: Equipment type (e.g., "hvac", "chiller")

        Returns:
            List of equipment items
        """
        response = self.client.table('equipment').select("*").eq(
            'type', equipment_type
        ).execute()

        return response.data

    def get_critical_equipment(self) -> List[Dict[str, Any]]:
        """Get all equipment with critical status.

        Returns:
            List of critical equipment items
        """
        response = self.client.table('equipment').select("*").eq(
            'status', 'critical'
        ).execute()

        return response.data

    def get_low_health_equipment(self, threshold: int = 70) -> List[Dict[str, Any]]:
        """Get equipment with health score below threshold.

        Args:
            threshold: Health score threshold (default: 70)

        Returns:
            List of equipment with low health
        """
        # Note: Supabase uses lt for less than
        response = self.client.table('equipment').select("*").lt(
            'health_score', threshold
        ).execute()

        return response.data

    def create(self, equipment_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create new equipment.

        Args:
            equipment_data: Equipment data

        Returns:
            Created equipment
        """
        response = self.client.table('equipment').insert(equipment_data).execute()
        return response.data[0]

    def update(self, equipment_id: str, equipment_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update equipment.

        Args:
            equipment_id: Equipment code
            equipment_data: Data to update

        Returns:
            Updated equipment or None if not found
        """
        equipment = self.get_by_id(equipment_id)
        if not equipment:
            return None

        response = self.client.table('equipment').update(
            equipment_data
        ).eq('id', equipment['id']).execute()

        if response.data:
            return response.data[0]
        return None

    def delete(self, equipment_id: str) -> bool:
        """Delete equipment.

        Args:
            equipment_id: Equipment code

        Returns:
            True if deleted, False if not found
        """
        equipment = self.get_by_id(equipment_id)
        if not equipment:
            return False

        response = self.client.table('equipment').delete().eq(
            'id', equipment['id']
        ).execute()

        return len(response.data) > 0

    def update_status(self, equipment_id: str, status: str) -> Optional[Dict[str, Any]]:
        """Update equipment status.

        Args:
            equipment_id: Equipment code
            status: New status ('normal', 'warning', 'critical', 'offline', 'maintenance')

        Returns:
            Updated equipment or None if not found
        """
        return self.update(equipment_id, {'status': status})

    def update_health_score(self, equipment_id: str, health_score: int) -> Optional[Dict[str, Any]]:
        """Update equipment health score.

        Args:
            equipment_id: Equipment code
            health_score: New health score (0-100)

        Returns:
            Updated equipment or None if not found
        """
        return self.update(equipment_id, {'health_score': health_score})
