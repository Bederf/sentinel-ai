"""
Technician Repository - Database operations for technicians and site assignments.
"""

import logging
from typing import Any

from ..supabase_client import get_supabase_client

logger = logging.getLogger(__name__)


class TechnicianRepository:
    """Repository for technician operations."""

    def __init__(self):
        self.client = get_supabase_client()

    async def get_technician_for_equipment(self, equipment_id: str) -> dict[str, Any] | None:
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
            result = self.client.rpc("get_technician_for_equipment", {"p_equipment_id": equipment_id}).execute()

            if result.data and len(result.data) > 0:
                tech = result.data[0]
                return {
                    "id": tech.get("technician_id"),
                    "name": tech.get("technician_name"),
                    "email": tech.get("technician_email"),
                    "phone": tech.get("technician_phone"),
                    "telegram_id": tech.get("technician_telegram_id"),
                    "specialty": tech.get("specialty"),
                }

            return None

        except Exception as e:
            logger.error(f"Error getting technician for equipment {equipment_id}: {e}")
            return None

    def _parse_specialty_from_code(self, equipment_code: str) -> str:
        """
        Parse equipment type from code and map to specialty.

        Supports two equipment code formats:
        1. Compact (Office): {site}-{type}-{floor/zone}
           Example: S002-DALI-L2-20 → parts[1]=DALI → specialty=dali
        2. Hospital: {site}-{building}-{type}-{floor}-{id}
           Example: site-005-UMH-AHU-L3-ICU → parts[3]=AHU → specialty=hvac

        Returns the matched specialty or 'general' as fallback.
        """
        try:
            parts = equipment_code.upper().split("-")
            if len(parts) < 2:
                logger.warning(f"Cannot parse {equipment_code}: insufficient parts ({len(parts)})")
                return "general"

            # Map equipment type to specialty
            # Based on official naming conventions (docs/02-architecture/naming-conventions.md)
            type_to_specialty = {
                # HVAC (v2.0 naming)
                "CHILLER": "hvac",
                "AHU": "hvac",
                "FCU": "hvac",
                "VAV": "hvac",
                "SPLIT": "hvac",
                "CT": "hvac",  # Cooling Tower
                "CRAC": "hvac",
                "PUMP": "hvac",  # PUMP is HVAC (not plumbing) per Phase 79
                # DALI Lighting (v2.0 naming)
                "DALI": "dali",
                "LUM": "dali",  # Luminaire
                # Energy/Electrical (v2.0 naming)
                "GEN": "electrical",
                "TX": "electrical",  # Transformer
                "UPS": "electrical",
                "ATS": "electrical",  # Automatic Transfer Switch
                "MSB": "electrical",  # Main Switchboard
                "MTR": "electrical",  # Power Meter
                "PFC": "electrical",  # Power Factor Correction
                "FDR": "electrical",  # Feeder
                "MV": "electrical",  # Medium Voltage
                "DB": "electrical",  # Distribution Board
                # Additional electrical types from hospital naming
                "KEF": "electrical",  # Kitchen Exhaust Fan
                "JACE": "electrical",  # Building automation controller
                # Medical equipment
                "COLD": "general",  # Cold storage (vaccine/blood)
                "BOILER": "hvac",  # Boiler (hot water heating)
                "LIFT": "general",  # Elevators (structural/safety)
                "MEDGAS": "general",  # Medical gas systems
                # Sensors (monitored by general)
                "TS": "general",  # Temperature Sensor
                "CO2": "general",  # CO2 Sensor
                "OCC": "general",  # Occupancy Sensor
                "DLS": "general",  # Daylight Sensor
                # Plumbing (legacy - now PUMP is HVAC)
                "TANK": "plumbing",
                "BORE": "plumbing",
                # Fire (v2.0 naming)
                "FIRE": "fire",
                # Security (v2.0 naming)
                "ACC": "security",  # Access Control
                "CCTV": "security",
            }

            # Try parsing in order of likelihood
            # Strategy 1: parts[1] for compact format (S002-TYPE-...)
            if parts[1] in type_to_specialty:
                return type_to_specialty[parts[1]]

            # Strategy 2: parts[3] for hospital format (site-005-UMH-TYPE-...)
            if len(parts) > 3 and parts[3] in type_to_specialty:
                return type_to_specialty[parts[3]]

            # Strategy 3: Fallback to general
            return "general"

        except Exception as e:
            logger.error(f"Error parsing {equipment_code}: {e}")
            return "general"

    async def get_technician_for_equipment_code(self, equipment_code: str) -> dict[str, Any] | None:
        """
        Get the assigned technician for equipment by code.

        Parses the equipment code to determine specialty, then looks up
        the assigned technician for that specialty at the equipment's site.

        Args:
            equipment_code: Equipment code (e.g., S002-DALI-L2-20 or site-005-UMH-AHU-L3-ICU)

        Returns:
            Technician details or None if not found
        """
        if not self.client:
            logger.warning("Supabase client not available")
            return None

        try:
            # First get equipment ID and site_id from code
            eq_result = self.client.table("equipment").select("id, site_id").eq("code", equipment_code).execute()

            if not eq_result.data or len(eq_result.data) == 0:
                logger.warning(f"Equipment not found: {equipment_code}")
                return None

            equipment = eq_result.data[0]
            _equipment_id = equipment["id"]
            site_id = equipment["site_id"]

            # Parse code to determine specialty (supports both site-002 and site-005 formats)
            specialty = self._parse_specialty_from_code(equipment_code)
            logger.debug(f"Parsed equipment {equipment_code} → specialty={specialty}")

            # Get technician for this building and specialty
            result = (
                self.client.table("site_technicians")
                .select("specialty, technicians(id, name, email, phone, telegram_id)")
                .eq("site_id", site_id)
                .eq("specialty", specialty)
                .eq("is_primary", True)
                .execute()
            )

            logger.debug(
                "Site_technicians query for specialty="
                f"{specialty}: found {len(result.data) if result.data else 0} results"
            )

            if result.data and len(result.data) > 0:
                assignment = result.data[0]
                tech = assignment.get("technicians", {})
                logger.debug(
                    f"Found technician {tech.get('name')} for "
                    f"{equipment_code} (specialty={assignment.get('specialty')})"
                )
                return {
                    "id": tech.get("id"),
                    "name": tech.get("name"),
                    "email": tech.get("email"),
                    "phone": tech.get("phone"),
                    "telegram_id": tech.get("telegram_id"),
                    "specialty": assignment.get("specialty"),
                }

            logger.debug(f"No technician found for specialty={specialty}, trying fallback to 'general'")

            # Fallback to 'general' specialty
            if specialty != "general":
                result = (
                    self.client.table("site_technicians")
                    .select("specialty, technicians(id, name, email, phone, telegram_id)")
                    .eq("site_id", site_id)
                    .eq("specialty", "general")
                    .eq("is_primary", True)
                    .execute()
                )

                if result.data and len(result.data) > 0:
                    assignment = result.data[0]
                    tech = assignment.get("technicians", {})
                    return {
                        "id": tech.get("id"),
                        "name": tech.get("name"),
                        "email": tech.get("email"),
                        "phone": tech.get("phone"),
                        "telegram_id": tech.get("telegram_id"),
                        "specialty": assignment.get("specialty"),
                    }

            return None

        except Exception as e:
            logger.error(f"Error getting technician for equipment code {equipment_code}: {e}")
            return None

    async def get_all_technicians(self, active_only: bool = True) -> list[dict[str, Any]]:
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

    async def get_technician_by_telegram_id(self, telegram_id: str) -> dict[str, Any] | None:
        """Resolve a technician and their primary site from a Telegram user ID."""
        if not self.client or not telegram_id:
            return None

        try:
            tech_result = (
                self.client.table("technicians")
                .select("*")
                .eq("telegram_id", telegram_id)
                .eq("active", True)
                .limit(1)
                .execute()
            )
            if not tech_result.data:
                return None

            technician = tech_result.data[0]
            assignments = (
                self.client.table("site_technicians")
                .select("site_id, is_primary")
                .eq("technician_id", technician["id"])
                .execute()
            ).data or []

            primary = next((row for row in assignments if row.get("is_primary")), None)
            first_assignment = primary or (assignments[0] if assignments else {})
            technician["site_id"] = first_assignment.get("site_id") or ""
            return technician
        except Exception as e:
            logger.error(f"Error getting technician by telegram_id {telegram_id}: {e}")
            return None

    async def get_site_assignments(self, site_id: str) -> list[dict[str, Any]]:
        """Get all technician assignments for a site."""
        if not self.client:
            return []

        try:
            result = (
                self.client.table("site_technicians")
                .select("*, technicians(id, code, name, email, phone)")
                .eq("site_id", site_id)
                .execute()
            )

            return result.data or []

        except Exception as e:
            logger.error(f"Error getting site assignments: {e}")
            return []

    # ==================== CRUD (Phase: Technician Registry UI) ====================

    def _resolve_site_uuid(self, site_id: str) -> str:
        """Resolve a site code (e.g. 'site-002') to its UUID if needed."""
        import re

        uuid_pattern = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
        if uuid_pattern.match(site_id):
            return site_id
        result = self.client.table("sites").select("id").eq("code", site_id).limit(1).execute()
        if result.data:
            return result.data[0]["id"]
        return site_id

    async def get_technicians_with_assignments(self, site_id: str | None = None) -> list[dict[str, Any]]:
        """Get technicians with their site assignments and notification channels.

        Returns a combined view for the Settings UI. When site_id is provided,
        only returns technicians assigned to that site.
        """
        if not self.client:
            logger.warning("Supabase client not available for get_technicians_with_assignments")
            return []

        try:
            # Resolve site code → UUID (site_technicians stores UUIDs)
            resolved_site_uuid = self._resolve_site_uuid(site_id) if site_id else None

            # Get site assignments (filtered by resolved UUID)
            assign_query = self.client.table("site_technicians").select("*")
            if resolved_site_uuid:
                assign_query = assign_query.eq("site_id", resolved_site_uuid)
            assignments = (assign_query.execute()).data or []

            # Build set of technician IDs that have assignments at this site
            assigned_tech_ids = {a["technician_id"] for a in assignments} if resolved_site_uuid else None

            # Get technicians — filtered to site-assigned ones when a site is specified
            tech_query = self.client.table("technicians").select("*").order("name")
            result = tech_query.execute()
            technicians = result.data or []

            if assigned_tech_ids is not None:
                technicians = [t for t in technicians if t["id"] in assigned_tech_ids]

            # Get notification channels for relevant technician IDs
            tech_ids = [t["id"] for t in technicians]
            if tech_ids:
                channels = (
                    self.client.table("technician_notification_channels")
                    .select("*")
                    .in_("technician_id", tech_ids)
                    .execute()
                ).data or []
            else:
                channels = []

            # Merge
            for tech in technicians:
                tid = tech["id"]
                tech["specialties"] = [a["specialty"] for a in assignments if a.get("technician_id") == tid]
                tech["site_assignments"] = [
                    {"site_id": a["site_id"], "specialty": a["specialty"], "is_primary": a.get("is_primary", False)}
                    for a in assignments
                    if a.get("technician_id") == tid
                ]
                tech["channels"] = [
                    {"channel_type": c["channel_type"], "is_verified": c.get("is_verified", False)}
                    for c in channels
                    if c.get("technician_id") == tid
                ]

            return technicians

        except Exception as e:
            logger.error(f"Error getting technicians with assignments: {e}")
            return []

    async def create_technician(
        self,
        name: str,
        email: str,
        phone: str,
        specialties: list[str],
        site_id: str,
        telegram_id: str | None = None,
    ) -> dict[str, Any] | None:
        """Create a new technician with site assignment(s).

        Creates:
        1. technicians record
        2. site_technicians assignment(s) per specialty
        3. technician_notification_channels if telegram/whatsapp provided
        """
        if not self.client:
            logger.warning("Supabase client not available for create_technician")
            return None

        try:
            import uuid

            # Generate a readable code
            code_suffix = name.split()[0].upper()[:4] + "-" + str(uuid.uuid4())[:4].upper()
            tech_code = f"TECH-{code_suffix}"

            # 1. Create technician
            tech_data = {
                "code": tech_code,
                "name": name,
                "email": email,
                "phone": phone,
                "active": True,
            }
            if telegram_id:
                tech_data["telegram_id"] = telegram_id

            result = self.client.table("technicians").insert(tech_data).execute()
            if not result.data:
                logger.error("Failed to insert technician")
                return None

            tech = result.data[0]
            tech_id = tech["id"]

            resolved_site_uuid = self._resolve_site_uuid(site_id)

            # 2. Create site_technicians for each specialty
            for i, spec in enumerate(specialties):
                self.client.table("site_technicians").insert(
                    {
                        "site_id": resolved_site_uuid,
                        "technician_id": tech_id,
                        "specialty": spec,
                        "is_primary": i == 0,
                    }
                ).execute()

            # 3. Create notification channel if contact info provided
            if telegram_id:
                self.client.table("technician_notification_channels").insert(
                    {
                        "technician_id": tech_id,
                        "channel_type": "telegram",
                        "telegram_id": telegram_id,
                        "is_verified": False,
                    }
                ).execute()

            if phone:
                self.client.table("technician_notification_channels").insert(
                    {
                        "technician_id": tech_id,
                        "channel_type": "whatsapp",
                        "whatsapp_number": phone,
                        "is_verified": False,
                    }
                ).execute()

            tech["specialties"] = specialties
            tech["channels"] = []
            if telegram_id:
                tech["channels"].append({"channel_type": "telegram", "is_verified": False})
            if phone:
                tech["channels"].append({"channel_type": "whatsapp", "is_verified": False})

            logger.info(f"Created technician {name} ({tech_code}) with specialties {specialties}")
            return tech

        except Exception as e:
            logger.error(f"Error creating technician: {e}")
            return None

    async def update_technician(
        self,
        tech_id: str,
        updates: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Update technician fields (name, email, phone, active)."""
        if not self.client:
            return None

        try:
            allowed = {k: v for k, v in updates.items() if k in ("name", "email", "phone", "active", "telegram_id")}
            if not allowed:
                return None

            result = self.client.table("technicians").update(allowed).eq("id", tech_id).execute()
            return result.data[0] if result.data else None

        except Exception as e:
            logger.error(f"Error updating technician {tech_id}: {e}")
            return None

    async def update_specialties(
        self,
        tech_id: str,
        site_id: str,
        specialties: list[str],
    ) -> bool:
        """Replace all specialty assignments for a technician at a site."""
        if not self.client:
            return False

        try:
            resolved_site_uuid = self._resolve_site_uuid(site_id)

            # Delete existing assignments for this tech at this site
            self.client.table("site_technicians").delete().eq("technician_id", tech_id).eq(
                "site_id", resolved_site_uuid
            ).execute()

            # Create new assignments
            for i, spec in enumerate(specialties):
                self.client.table("site_technicians").insert(
                    {
                        "site_id": resolved_site_uuid,
                        "technician_id": tech_id,
                        "specialty": spec,
                        "is_primary": i == 0,
                    }
                ).execute()

            return True
        except Exception as e:
            logger.error(f"Error updating specialties for {tech_id}: {e}")
            return False

    async def deactivate_technician(self, tech_id: str) -> bool:
        """Soft-deactivate a technician (preserves audit trail)."""
        result = await self.update_technician(tech_id, {"active": False})
        return result is not None

    async def reactivate_technician(self, tech_id: str) -> bool:
        """Reactivate a deactivated technician."""
        result = await self.update_technician(tech_id, {"active": True})
        return result is not None


# Singleton instance
_repository: TechnicianRepository | None = None


def get_technician_repository() -> TechnicianRepository:
    """Get singleton technician repository."""
    global _repository
    if _repository is None:
        _repository = TechnicianRepository()
    return _repository
