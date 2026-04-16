"""Repository for building/site operations."""

import logging
import time
from typing import List, Optional, Dict, Any
from app.database.supabase_client import get_supabase_client
from app.models.auth import SentinelRole
from app.services.cache_service import cache, CacheKeys, CacheService, CacheInvalidation, track_query

logger = logging.getLogger(__name__)


class SiteRepository:
    """Repository for building/site database operations."""

    _COLUMNS = (
        "id, code, name, type, region, address, latitude, longitude, "
        "equipment_count, floors, sqm, created_at, updated_at, "
        "year_built, operating_hours, occupancy_pattern, "
        "contact_email, contact_phone, "
        "optimization_enabled, optimization_status, "
        "control_enabled, control_note, "
        "sentinel_processing_enabled, "
        "onboarding_phase"
    )

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
                if "429" in error_msg or "rate limit" in error_msg.lower():
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

    def get_all(self, region: Optional[str] = None, site_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get all buildings with optional filtering.

        Args:
            region: Filter by region
            site_type: Filter by building type

        Returns:
            List of buildings
        """
        # Only cache unfiltered full list
        if not region and not site_type:
            cached = cache.get(CacheKeys.sites_all())
            if cached is not None:
                return cached

        query = self.client.table("sites").select(self._COLUMNS)

        if region:
            query = query.eq("region", region)
        if site_type:
            query = query.eq("type", site_type)

        with track_query("building", "get_all"):
            response = self._execute_with_retry(query)
        result = response.data

        if not region and not site_type:
            cache.set(CacheKeys.sites_all(), result, CacheService.TTL_SEMI_STATIC)

        return result

    def get_by_id(self, site_id: str) -> Optional[Dict[str, Any]]:
        """Get a building by its code.

        Args:
            site_id: Building code (e.g., "site-001")

        Returns:
            Building data or None if not found
        """
        cached = cache.get(CacheKeys.building(site_id))
        if cached is not None:
            return cached

        query = self.client.table("sites").select(self._COLUMNS).eq("code", site_id)
        with track_query("building", "get_by_id"):
            response = self._execute_with_retry(query)

        if response.data:
            result = response.data[0]
            cache.set(CacheKeys.building(site_id), result, CacheService.TTL_SEMI_STATIC)
            return result
        return None

    def get_by_uuid(self, uuid: str) -> Optional[Dict[str, Any]]:
        """Get a building by its UUID.

        Args:
            uuid: Building UUID

        Returns:
            Building data or None if not found
        """
        cached = cache.get(CacheKeys.building_by_id(uuid))
        if cached is not None:
            return cached

        query = self.client.table("sites").select(self._COLUMNS).eq("id", uuid)
        response = self._execute_with_retry(query)

        if response.data:
            result = response.data[0]
            cache.set(CacheKeys.building_by_id(uuid), result, CacheService.TTL_SEMI_STATIC)
            return result
        return None

    def get_equipment_count(self, site_uuid: str) -> int:
        """Get the equipment count for a building.

        Args:
            site_uuid: Building UUID

        Returns:
            Number of equipment items
        """
        # Use the equipment_count column that's maintained by triggers
        building = self.get_by_uuid(site_uuid)
        if building:
            return building.get("equipment_count", 0)
        return 0

    def get_alert_count(self, site_uuid: str, status: str = "active") -> int:
        """Get the alert count for a building.

        Args:
            site_uuid: Building UUID
            status: Alert status filter (default: 'active')

        Returns:
            Number of alerts
        """
        response = (
            self.client.table("alerts")
            .select("id", count="exact")
            .eq("site_id", site_uuid)
            .eq("status", status)
            .execute()
        )

        return response.count or 0

    def get_at_risk_equipment_count(self, site_uuid: str) -> int:
        """Get the count of at-risk equipment (warning/critical status) for a building.

        Args:
            site_uuid: Building UUID

        Returns:
            Number of equipment with warning or critical status
        """
        response = (
            self.client.table("equipment")
            .select("id", count="exact")
            .eq("site_id", site_uuid)
            .in_("status", ["warning", "critical"])
            .execute()
        )

        return response.count or 0

    def get_equipment(self, site_id: str) -> List[Dict[str, Any]]:
        """Get all equipment for a building.

        Args:
            site_id: Building code (e.g., "site-001")

        Returns:
            List of equipment items for the building
        """
        # Get building UUID from code
        building = self.get_by_id(site_id)
        if not building:
            return []

        # Query equipment table by site_id (includes metadata fields)
        response = (
            self.client.table("equipment")
            .select(
                "id, code, name, status, health_score, type, site_id, "
                "manufacturer, model, install_date, commissioning_date, "
                "device_info, operating_data, network_info, location"
            )
            .eq("site_id", building["id"])
            .execute()
        )

        return response.data or []

    def create(self, site_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new building.

        Args:
            site_data: Building data

        Returns:
            Created building
        """
        response = self.client.table("sites").insert(site_data).execute()
        result = response.data[0]
        CacheInvalidation.on_building_change()
        return result

    def update(self, site_id: str, site_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update a building.

        Args:
            site_id: Building code
            site_data: Data to update

        Returns:
            Updated building or None if not found
        """
        # First get the UUID
        building = self.get_by_id(site_id)
        if not building:
            return None

        response = self.client.table("sites").update(site_data).eq("id", building["id"]).execute()

        if response.data:
            CacheInvalidation.on_building_change(site_id=building["id"], site_code=site_id)
            return response.data[0]
        return None

    def delete(self, site_id: str) -> bool:
        """Delete a building.

        Args:
            site_id: Building code

        Returns:
            True if deleted, False if not found
        """
        building = self.get_by_id(site_id)
        if not building:
            return False

        response = self.client.table("sites").delete().eq("id", building["id"]).execute()

        if len(response.data) > 0:
            CacheInvalidation.on_building_change(site_id=building["id"], site_code=site_id)
            return True
        return False

    def get_asset_summary(self, site_uuid: str) -> Optional[Dict[str, Any]]:
        """Get categorized asset counts from Supabase view.

        Args:
            site_uuid: Building UUID

        Returns:
            Asset summary dict with counts by category, or None if not found
        """
        try:
            response = self.client.table("v_site_asset_summary").select("*").eq("site_id", site_uuid).execute()

            if response.data:
                return response.data[0]
            return None
        except Exception:
            # View may not exist (migrations not applied)
            return None

    def get_asset_summary_by_code(self, site_code: str) -> Optional[Dict[str, Any]]:
        """Get categorized asset counts by building code.

        Args:
            site_code: Building code (e.g., 'sandton')

        Returns:
            Asset summary dict with counts by category, or None if not found
        """
        try:
            response = self.client.table("v_site_asset_summary").select("*").eq("site_code", site_code).execute()

            if response.data:
                return response.data[0]
            return None
        except Exception:
            # View may not exist (migrations not applied)
            return None

    def get_all_for_user(
        self, user_email: str, user_role: SentinelRole, region: Optional[str] = None, site_type: Optional[str] = None
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
            access_result = self.client.table("user_site_access").select("site_id").eq("user_email", email).execute()

            if not access_result.data:
                return []

            site_ids = [a["site_id"] for a in access_result.data]

            # Get buildings with those IDs
            query = self.client.table("sites").select(self._COLUMNS).in_("id", site_ids)

            if region:
                query = query.eq("region", region)
            if site_type:
                query = query.eq("type", site_type)

            response = query.execute()
            return response.data or []

        except Exception as e:
            import logging

            logging.getLogger(__name__).error(f"Error getting buildings for user: {e}")
            return []
