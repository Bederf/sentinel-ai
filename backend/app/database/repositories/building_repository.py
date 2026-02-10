"""Repository for building/site operations."""

from typing import List, Optional, Dict, Any
from app.database.supabase_client import get_supabase_client
from app.models.auth import SentinelRole


class BuildingRepository:
    """Repository for building/site database operations."""

    def __init__(self):
        """Initialize the repository with a Supabase client."""
        self.client = get_supabase_client()

    def get_all(
        self,
        region: Optional[str] = None,
        site_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get all buildings with optional filtering.

        Args:
            region: Filter by region
            site_type: Filter by building type

        Returns:
            List of buildings
        """
        query = self.client.table('buildings').select("*")

        if region:
            query = query.eq('region', region)
        if site_type:
            query = query.eq('type', site_type)

        response = query.execute()
        return response.data

    def get_by_id(self, building_id: str) -> Optional[Dict[str, Any]]:
        """Get a building by its code.

        Args:
            building_id: Building code (e.g., "site-001")

        Returns:
            Building data or None if not found
        """
        response = self.client.table('buildings').select("*").eq('code', building_id).execute()

        if response.data:
            return response.data[0]
        return None

    def get_by_uuid(self, uuid: str) -> Optional[Dict[str, Any]]:
        """Get a building by its UUID.

        Args:
            uuid: Building UUID

        Returns:
            Building data or None if not found
        """
        response = self.client.table('buildings').select("*").eq('id', uuid).execute()

        if response.data:
            return response.data[0]
        return None

    def get_equipment_count(self, building_uuid: str) -> int:
        """Get the equipment count for a building.

        Args:
            building_uuid: Building UUID

        Returns:
            Number of equipment items
        """
        # Use the equipment_count column that's maintained by triggers
        building = self.get_by_uuid(building_uuid)
        if building:
            return building.get('equipment_count', 0)
        return 0

    def get_alert_count(self, building_uuid: str, status: str = 'active') -> int:
        """Get the alert count for a building.

        Args:
            building_uuid: Building UUID
            status: Alert status filter (default: 'active')

        Returns:
            Number of alerts
        """
        response = self.client.table('alerts').select("id", count="exact").eq(
            'building_id', building_uuid
        ).eq('status', status).execute()

        return response.count or 0

    def get_at_risk_equipment_count(self, building_uuid: str) -> int:
        """Get the count of at-risk equipment (warning/critical status) for a building.

        Args:
            building_uuid: Building UUID

        Returns:
            Number of equipment with warning or critical status
        """
        response = self.client.table('equipment').select("id", count="exact").eq(
            'building_id', building_uuid
        ).in_('status', ['warning', 'critical']).execute()

        return response.count or 0

    def get_equipment(self, building_id: str) -> List[Dict[str, Any]]:
        """Get all equipment for a building.

        Args:
            building_id: Building code (e.g., "site-001")

        Returns:
            List of equipment items for the building
        """
        # Get building UUID from code
        building = self.get_by_id(building_id)
        if not building:
            return []
        
        # Query equipment table by building_id
        response = self.client.table('equipment').select(
            "id, code, name, status, health_score, type, building_id"
        ).eq('building_id', building['id']).execute()
        
        return response.data or []

    def create(self, building_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new building.

        Args:
            building_data: Building data

        Returns:
            Created building
        """
        response = self.client.table('buildings').insert(building_data).execute()
        return response.data[0]

    def update(self, building_id: str, building_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update a building.

        Args:
            building_id: Building code
            building_data: Data to update

        Returns:
            Updated building or None if not found
        """
        # First get the UUID
        building = self.get_by_id(building_id)
        if not building:
            return None

        response = self.client.table('buildings').update(
            building_data
        ).eq('id', building['id']).execute()

        if response.data:
            return response.data[0]
        return None

    def delete(self, building_id: str) -> bool:
        """Delete a building.

        Args:
            building_id: Building code

        Returns:
            True if deleted, False if not found
        """
        building = self.get_by_id(building_id)
        if not building:
            return False

        response = self.client.table('buildings').delete().eq(
            'id', building['id']
        ).execute()

        return len(response.data) > 0

    def get_asset_summary(self, building_uuid: str) -> Optional[Dict[str, Any]]:
        """Get categorized asset counts from Supabase view.

        Args:
            building_uuid: Building UUID

        Returns:
            Asset summary dict with counts by category, or None if not found
        """
        try:
            response = self.client.table('v_building_asset_summary').select(
                "*"
            ).eq('building_id', building_uuid).execute()

            if response.data:
                return response.data[0]
            return None
        except Exception:
            # View may not exist (migrations not applied)
            return None

    def get_asset_summary_by_code(self, building_code: str) -> Optional[Dict[str, Any]]:
        """Get categorized asset counts by building code.

        Args:
            building_code: Building code (e.g., 'sandton')

        Returns:
            Asset summary dict with counts by category, or None if not found
        """
        try:
            response = self.client.table('v_building_asset_summary').select(
                "*"
            ).eq('building_code', building_code).execute()

            if response.data:
                return response.data[0]
            return None
        except Exception:
            # View may not exist (migrations not applied)
            return None

    def get_all_for_user(
        self,
        user_email: str,
        user_role: SentinelRole,
        region: Optional[str] = None,
        site_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get all buildings accessible to a user with optional filtering.

        ADMIN role sees all buildings.
        Other roles see only buildings they have been granted access to.

        Args:
            user_email: User's email address
            user_role: User's role
            region: Filter by region
            site_type: Filter by building type

        Returns:
            List of buildings the user can access
        """
        # ADMIN sees all buildings
        if user_role == SentinelRole.ADMIN:
            return self.get_all(region=region, site_type=site_type)

        # Other roles need to check user_site_access
        try:
            email = user_email.lower().strip()

            # Get building IDs user has access to
            access_result = self.client.table('user_site_access').select(
                'building_id'
            ).eq('user_email', email).execute()

            if not access_result.data:
                return []

            building_ids = [a['building_id'] for a in access_result.data]

            # Get buildings with those IDs
            query = self.client.table('buildings').select("*").in_('id', building_ids)

            if region:
                query = query.eq('region', region)
            if site_type:
                query = query.eq('type', site_type)

            response = query.execute()
            return response.data or []

        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Error getting buildings for user: {e}")
            return []
