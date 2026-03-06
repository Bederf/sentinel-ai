"""Repository for equipment operations."""

from typing import List, Optional, Dict, Any
import time
import logging
from app.database.supabase_client import get_supabase_client
from app.services.cache_service import cache, CacheKeys, CacheService, CacheInvalidation, track_query

logger = logging.getLogger(__name__)


class EquipmentRepository:
    """Repository for equipment database operations."""

    # Column selection constants to avoid SELECT * overhead
    _LIST_COLUMNS = "id, code, name, status, health_score, type, site_id, location"
    _DETAIL_COLUMNS = (
        "id, code, name, status, health_score, type, site_id, "
        "manufacturer, model, install_date, commissioning_date, "
        "device_info, operating_data, network_info, location, "
        "service_provider_name, service_provider_email, "
        "service_provider_phone, service_provider_specialty, "
        "created_at, updated_at"
    )

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

    def get_all(self, site_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get all equipment with optional filtering.

        Args:
            site_id: Filter by site UUID

        Returns:
            List of equipment items
        """
        # Cache equipment-by-building (most common call)
        if site_id:
            cached = cache.get(CacheKeys.equipment_by_site(site_id))
            if cached is not None:
                return cached

        query = self.client.table("equipment").select(self._LIST_COLUMNS)

        if site_id:
            query = query.eq("site_id", site_id)

        with track_query("equipment", "get_all"):
            response = query.execute()
        result = response.data

        if site_id:
            cache.set(CacheKeys.equipment_by_site(site_id), result, CacheService.TTL_SEMI_STATIC)

        return result

    def get_by_id(self, equipment_id: str) -> Optional[Dict[str, Any]]:
        """Get equipment by its code.

        Args:
            equipment_id: Equipment code (e.g., "eqp-001")

        Returns:
            Equipment data or None if not found
        """
        cached = cache.get(CacheKeys.equipment_by_code(equipment_id))
        if cached is not None:
            return cached

        with track_query("equipment", "get_by_id"):
            response = self.client.table("equipment").select(self._DETAIL_COLUMNS).eq("code", equipment_id).execute()

        if response.data:
            result = response.data[0]
            cache.set(CacheKeys.equipment_by_code(equipment_id), result, CacheService.TTL_SEMI_STATIC)
            return result
        return None

    def get_by_uuid(self, uuid: str) -> Optional[Dict[str, Any]]:
        """Get equipment by its UUID.

        Args:
            uuid: Equipment UUID

        Returns:
            Equipment data or None if not found
        """
        response = self.client.table("equipment").select(self._DETAIL_COLUMNS).eq("id", uuid).execute()

        if response.data:
            return response.data[0]
        return None

    def get_by_site_code(self, site_code: str) -> List[Dict[str, Any]]:
        """Get equipment by building code.

        Args:
            site_code: Building code (e.g., "site-001")

        Returns:
            List of equipment items
        """
        # First get the building UUID (with retry)
        building_query = self.client.table("sites").select("id").eq("code", site_code)
        site_response = self._execute_with_retry(building_query)

        if not site_response.data:
            return []

        site_uuid = site_response.data[0]["id"]

        # Get equipment for this building (with retry)
        equipment_query = self.client.table("equipment").select(self._LIST_COLUMNS).eq("site_id", site_uuid)
        equipment_response = self._execute_with_retry(equipment_query)

        return equipment_response.data

    def get_by_type(self, equipment_type: str) -> List[Dict[str, Any]]:
        """Get equipment by type.

        Args:
            equipment_type: Equipment type (e.g., "hvac", "chiller")

        Returns:
            List of equipment items
        """
        response = self.client.table("equipment").select(self._LIST_COLUMNS).eq("type", equipment_type).execute()

        return response.data

    def get_critical_equipment(self) -> List[Dict[str, Any]]:
        """Get all equipment with critical status.

        Returns:
            List of critical equipment items
        """
        response = self.client.table("equipment").select(self._LIST_COLUMNS).eq("status", "critical").execute()

        return response.data

    def get_low_health_equipment(self, threshold: int = 70) -> List[Dict[str, Any]]:
        """Get equipment with health score below threshold.

        Args:
            threshold: Health score threshold (default: 70)

        Returns:
            List of equipment with low health
        """
        # Note: Supabase uses lt for less than
        response = self.client.table("equipment").select(self._LIST_COLUMNS).lt("health_score", threshold).execute()

        return response.data

    def create(self, equipment_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create new equipment.

        Args:
            equipment_data: Equipment data

        Returns:
            Created equipment
        """
        response = self.client.table("equipment").insert(equipment_data).execute()
        result = response.data[0]
        CacheInvalidation.on_equipment_change(site_id=equipment_data.get("site_id"))
        return result

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

        response = self.client.table("equipment").update(equipment_data).eq("id", equipment["id"]).execute()

        if response.data:
            CacheInvalidation.on_equipment_change(
                site_id=equipment.get("site_id"),
                equipment_code=equipment_id,
            )
            return response.data[0]
        return None

    def update_operating_data(self, equipment_id: str, point_values: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update equipment operating_data with new point values.

        Merges new point values into existing operating_data JSONB column.
        Used by device adapters to sync control state to database.

        Args:
            equipment_id: Equipment UUID or code
            point_values: Dict of point_name → {value, timestamp, source} to merge

        Returns:
            Updated equipment record or None if not found
        """
        from datetime import datetime

        # Get current equipment by UUID first, then fallback to code
        equipment = self.get_by_uuid(equipment_id) if self._is_uuid(equipment_id) else None
        if not equipment:
            equipment = self.get_by_id(equipment_id)

        if not equipment:
            return None

        # Get current operating_data to preserve existing points
        current_data = equipment.get("operating_data", {}) or {}
        if not isinstance(current_data, dict):
            current_data = {}

        # Merge new point values into existing data
        current_data.update(point_values)

        # Update database
        try:
            response = (
                self.client.table("equipment")
                .update({"operating_data": current_data, "updated_at": datetime.now().isoformat()})
                .eq("id", equipment["id"])
                .execute()
            )

            if response.data:
                return response.data[0]
            return None
        except Exception as e:
            logger.error(f"Failed to update operating_data for {equipment_id}: {e}")
            return None

    def _is_uuid(self, value: str) -> bool:
        """Check if value looks like a UUID."""
        import re

        uuid_pattern = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
        return bool(re.match(uuid_pattern, value, re.IGNORECASE))

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

        response = self.client.table("equipment").delete().eq("id", equipment["id"]).execute()

        if len(response.data) > 0:
            CacheInvalidation.on_equipment_change(
                site_id=equipment.get("site_id"),
                equipment_code=equipment_id,
            )
            return True
        return False

    def update_status(self, equipment_id: str, status: str) -> Optional[Dict[str, Any]]:
        """Update equipment status.

        Args:
            equipment_id: Equipment code
            status: New status ('normal', 'warning', 'critical', 'offline', 'maintenance')

        Returns:
            Updated equipment or None if not found
        """
        return self.update(equipment_id, {"status": status})

    def update_health_score(self, equipment_id: str, health_score: int) -> Optional[Dict[str, Any]]:
        """Update equipment health score.

        Args:
            equipment_id: Equipment code
            health_score: New health score (0-100)

        Returns:
            Updated equipment or None if not found
        """
        return self.update(equipment_id, {"health_score": health_score})

    def update_service_provider(
        self,
        equipment_id: str,
        provider_name: Optional[str] = None,
        provider_email: Optional[str] = None,
        provider_phone: Optional[str] = None,
        provider_specialty: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Update service provider information for equipment.

        Args:
            equipment_id: Equipment code
            provider_name: Service provider name
            provider_email: Service provider email
            provider_phone: Service provider phone
            provider_specialty: Service provider specialty (hvac, electrical, plumbing, dali, fire, security, general)

        Returns:
            Updated equipment or None if not found
        """
        update_data = {}
        if provider_name is not None:
            update_data["service_provider_name"] = provider_name
        if provider_email is not None:
            update_data["service_provider_email"] = provider_email
        if provider_phone is not None:
            update_data["service_provider_phone"] = provider_phone
        if provider_specialty is not None:
            update_data["service_provider_specialty"] = provider_specialty

        if not update_data:
            return self.get_by_id(equipment_id)

        return self.update(equipment_id, update_data)

    def get_by_service_provider(self, email: str) -> List[Dict[str, Any]]:
        """Get all equipment assigned to a service provider by email.

        Args:
            email: Service provider email

        Returns:
            List of equipment items
        """
        response = (
            self.client.table("equipment").select(self._LIST_COLUMNS).eq("service_provider_email", email).execute()
        )

        return response.data

    def get_by_service_provider_specialty(self, specialty: str) -> List[Dict[str, Any]]:
        """Get all equipment assigned to service providers with a specific specialty.

        Args:
            specialty: Service provider specialty

        Returns:
            List of equipment items
        """
        response = (
            self.client.table("equipment")
            .select(self._LIST_COLUMNS)
            .eq("service_provider_specialty", specialty)
            .execute()
        )

        return response.data


# Singleton instance
_equipment_repository_instance: Optional[EquipmentRepository] = None


def get_equipment_repository() -> EquipmentRepository:
    """Get or create the singleton EquipmentRepository instance."""
    global _equipment_repository_instance
    if _equipment_repository_instance is None:
        _equipment_repository_instance = EquipmentRepository()
    return _equipment_repository_instance
