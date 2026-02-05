"""
Technician Repository - Database operations for technicians and site assignments.
"""

from typing import Optional, List, Dict, Any
from ..supabase_client import get_supabase_client
import logging

logger = logging.getLogger(__name__)


class TechnicianRepository:
    """Repository for technician operations."""

    def __init__(self):
        self.client = get_supabase_client()

    async def get_technician_for_equipment(self, equipment_id: str) -> Optional[Dict[str, Any]]:
        """
        Get the assigned technician for a piece of equipment.
        Uses the get_technician_for_equipment Supabase function.

        Args:
            equipment_id: UUID of the equipment

        Returns:
            Technician details or None if not found
        """
        if not self.client:
            logger.warning("Supabase client not available")
            return None

        try:
            # Call the Supabase function
            result = self.client.rpc(
                'get_technician_for_equipment',
                {'p_equipment_id': equipment_id}
            ).execute()

            if result.data and len(result.data) > 0:
                tech = result.data[0]
                return {
                    "id": tech.get("technician_id"),
                    "name": tech.get("technician_name"),
                    "email": tech.get("technician_email"),
                    "phone": tech.get("technician_phone"),
                    "telegram_id": tech.get("technician_telegram_id"),
                    "specialty": tech.get("specialty")
                }

            return None

        except Exception as e:
            logger.error(f"Error getting technician for equipment {equipment_id}: {e}")
            return None

    def _parse_specialty_from_code(self, equipment_code: str) -> str:
        """
        Parse equipment type from code and map to specialty.

        Equipment code format: {site}-{type}-{floor}-{zone}
        Example: S002-DALI-L2-20 → type=DALI → specialty=dali
        """
        try:
            parts = equipment_code.upper().split('-')
            if len(parts) < 2:
                return 'general'

            eq_type = parts[1]

            # Map equipment type to specialty
            # Based on official naming conventions (docs/02-architecture/naming-conventions.md)
            type_to_specialty = {
                # HVAC (v2.0 naming)
                'CHILLER': 'hvac',
                'AHU': 'hvac',
                'FCU': 'hvac',
                'VAV': 'hvac',
                'SPLIT': 'hvac',
                'CT': 'hvac',      # Cooling Tower
                'CRAC': 'hvac',
                # DALI Lighting (v2.0 naming)
                'DALI': 'dali',
                'LUM': 'dali',     # Luminaire
                # Energy/Electrical (v2.0 naming)
                'GEN': 'electrical',
                'TX': 'electrical',   # Transformer
                'UPS': 'electrical',
                'ATS': 'electrical',  # Automatic Transfer Switch
                'MSB': 'electrical',  # Main Switchboard
                'MTR': 'electrical',  # Power Meter
                'PFC': 'electrical',  # Power Factor Correction
                'FDR': 'electrical',  # Feeder
                'MV': 'electrical',   # Medium Voltage
                'DB': 'electrical',   # Distribution Board
                # Sensors (monitored by general)
                'TS': 'general',      # Temperature Sensor
                'CO2': 'general',     # CO2 Sensor
                'OCC': 'general',     # Occupancy Sensor
                'DLS': 'general',     # Daylight Sensor
                # Plumbing
                'PUMP': 'plumbing',
                'TANK': 'plumbing',
                'BORE': 'plumbing',
                # Fire (v2.0 naming)
                'FIRE': 'fire',
                # Security (v2.0 naming)
                'ACC': 'security',    # Access Control
                'CCTV': 'security',
            }

            return type_to_specialty.get(eq_type, 'general')

        except Exception:
            return 'general'

    async def get_technician_for_equipment_code(self, equipment_code: str) -> Optional[Dict[str, Any]]:
        """
        Get the assigned technician for equipment by code.

        Parses the equipment code to determine specialty, then looks up
        the assigned technician for that specialty at the equipment's site.

        Args:
            equipment_code: Equipment code (e.g., S002-DALI-L2-20)

        Returns:
            Technician details or None if not found
        """
        if not self.client:
            logger.warning("Supabase client not available")
            return None

        try:
            # First get equipment ID and building_id from code
            eq_result = self.client.table("equipment").select(
                "id, building_id"
            ).eq("code", equipment_code).execute()

            if not eq_result.data or len(eq_result.data) == 0:
                logger.warning(f"Equipment not found: {equipment_code}")
                return None

            equipment = eq_result.data[0]
            equipment_id = equipment["id"]
            building_id = equipment["building_id"]

            # Try Supabase function first
            try:
                return await self.get_technician_for_equipment(equipment_id)
            except Exception as func_error:
                logger.debug(f"Supabase function failed, using fallback: {func_error}")

            # Fallback: Parse code and lookup manually
            specialty = self._parse_specialty_from_code(equipment_code)

            # Get technician for this building and specialty
            result = self.client.table("site_technicians").select(
                "specialty, technicians(id, name, email, phone, telegram_id)"
            ).eq("building_id", building_id).eq("specialty", specialty).eq(
                "is_primary", True
            ).execute()

            if result.data and len(result.data) > 0:
                assignment = result.data[0]
                tech = assignment.get("technicians", {})
                return {
                    "id": tech.get("id"),
                    "name": tech.get("name"),
                    "email": tech.get("email"),
                    "phone": tech.get("phone"),
                    "telegram_id": tech.get("telegram_id"),
                    "specialty": assignment.get("specialty")
                }

            # Fallback to 'general' specialty
            if specialty != 'general':
                result = self.client.table("site_technicians").select(
                    "specialty, technicians(id, name, email, phone, telegram_id)"
                ).eq("building_id", building_id).eq("specialty", "general").eq(
                    "is_primary", True
                ).execute()

                if result.data and len(result.data) > 0:
                    assignment = result.data[0]
                    tech = assignment.get("technicians", {})
                    return {
                        "id": tech.get("id"),
                        "name": tech.get("name"),
                        "email": tech.get("email"),
                        "phone": tech.get("phone"),
                        "telegram_id": tech.get("telegram_id"),
                        "specialty": assignment.get("specialty")
                    }

            return None

        except Exception as e:
            logger.error(f"Error getting technician for equipment code {equipment_code}: {e}")
            return None

    async def get_all_technicians(self, active_only: bool = True) -> List[Dict[str, Any]]:
        """Get all technicians."""
        if not self.client:
            return []

        try:
            query = self.client.table("technicians").select("*")
            if active_only:
                query = query.eq("active", True)

            result = query.execute()
            return result.data or []

        except Exception as e:
            logger.error(f"Error getting technicians: {e}")
            return []

    async def get_site_assignments(self, building_id: str) -> List[Dict[str, Any]]:
        """Get all technician assignments for a site."""
        if not self.client:
            return []

        try:
            result = self.client.table("site_technicians").select(
                "*, technicians(id, code, name, email, phone)"
            ).eq("building_id", building_id).execute()

            return result.data or []

        except Exception as e:
            logger.error(f"Error getting site assignments: {e}")
            return []


# Singleton instance
_repository: Optional[TechnicianRepository] = None


def get_technician_repository() -> TechnicianRepository:
    """Get singleton technician repository."""
    global _repository
    if _repository is None:
        _repository = TechnicianRepository()
    return _repository
