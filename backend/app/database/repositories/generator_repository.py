"""Repository for generator, tank, and group operations."""

import logging
from typing import Any

from app.database.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)


class GeneratorRepository:
    """Repository for generator-related database operations.

    Handles three tables:
    - diesel_tanks: Fuel storage tanks
    - generator_groups: N+1 redundancy groups
    - generators: Individual generator units
    """

    def __init__(self):
        """Initialize the repository with a Supabase client."""
        self.client = get_supabase_client()

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def get_site_uuid(self, site_code: str) -> str | None:
        """Get building UUID from building code."""
        response = self.client.table("sites").select("id").eq("code", site_code).execute()

        if response.data:
            return response.data[0]["id"]
        return None

    # =========================================================================
    # Diesel Tanks
    # =========================================================================

    def get_tanks(self, site_code: str | None = None) -> list[dict[str, Any]]:
        """Get all diesel tanks, optionally filtered by building."""
        query = self.client.table("diesel_tanks").select("*")

        if site_code:
            site_uuid = self.get_site_uuid(site_code)
            if site_uuid:
                query = query.eq("site_id", site_uuid)

        response = query.execute()
        return response.data

    def get_tank_by_id(self, tank_id: str) -> dict[str, Any] | None:
        """Get diesel tank by tank_id."""
        response = self.client.table("diesel_tanks").select("*").eq("tank_id", tank_id).execute()

        if response.data:
            return response.data[0]
        return None

    def upsert_tank(self, tank_data: dict[str, Any]) -> dict[str, Any]:
        """Insert or update a diesel tank."""
        response = self.client.table("diesel_tanks").upsert(tank_data, on_conflict="tank_id").execute()
        return response.data[0] if response.data else {}

    def upsert_tanks(self, tanks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Insert or update multiple diesel tanks."""
        if not tanks:
            return []

        response = self.client.table("diesel_tanks").upsert(tanks, on_conflict="tank_id").execute()
        return response.data

    def delete_tank(self, tank_id: str) -> bool:
        """Delete a diesel tank."""
        response = self.client.table("diesel_tanks").delete().eq("tank_id", tank_id).execute()
        return len(response.data) > 0

    def update_tank_level(self, tank_id: str, level_liters: int, level_pct: float) -> dict[str, Any] | None:
        """Update diesel tank level."""
        response = (
            self.client.table("diesel_tanks")
            .update(
                {
                    "current_level_liters": level_liters,
                    "current_level_pct": level_pct,
                }
            )
            .eq("tank_id", tank_id)
            .execute()
        )

        if response.data:
            return response.data[0]
        return None

    # =========================================================================
    # Generator Groups
    # =========================================================================

    def get_groups(self, site_code: str | None = None) -> list[dict[str, Any]]:
        """Get all generator groups, optionally filtered by building."""
        query = self.client.table("generator_groups").select("*")

        if site_code:
            site_uuid = self.get_site_uuid(site_code)
            if site_uuid:
                query = query.eq("site_id", site_uuid)

        response = query.execute()
        return response.data

    def get_group_by_id(self, group_id: str) -> dict[str, Any] | None:
        """Get generator group by group_id."""
        response = self.client.table("generator_groups").select("*").eq("group_id", group_id).execute()

        if response.data:
            return response.data[0]
        return None

    def get_group_uuid(self, group_id: str) -> str | None:
        """Get generator group UUID from group_id."""
        response = self.client.table("generator_groups").select("id").eq("group_id", group_id).execute()

        if response.data:
            return response.data[0]["id"]
        return None

    def get_tank_uuid(self, tank_id: str) -> str | None:
        """Get diesel tank UUID from tank_id."""
        response = self.client.table("diesel_tanks").select("id").eq("tank_id", tank_id).execute()

        if response.data:
            return response.data[0]["id"]
        return None

    def upsert_group(self, group_data: dict[str, Any]) -> dict[str, Any]:
        """Insert or update a generator group."""
        response = self.client.table("generator_groups").upsert(group_data, on_conflict="group_id").execute()
        return response.data[0] if response.data else {}

    def upsert_groups(self, groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Insert or update multiple generator groups."""
        if not groups:
            return []

        response = self.client.table("generator_groups").upsert(groups, on_conflict="group_id").execute()
        return response.data

    def delete_group(self, group_id: str) -> bool:
        """Delete a generator group."""
        response = self.client.table("generator_groups").delete().eq("group_id", group_id).execute()
        return len(response.data) > 0

    def update_group_status(
        self, group_id: str, generators_running: int, total_load_kw: float, ats_position: str
    ) -> dict[str, Any] | None:
        """Update generator group operational status."""
        response = (
            self.client.table("generator_groups")
            .update(
                {
                    "generators_running": generators_running,
                    "total_load_kw": total_load_kw,
                    "ats_position": ats_position,
                }
            )
            .eq("group_id", group_id)
            .execute()
        )

        if response.data:
            return response.data[0]
        return None

    # =========================================================================
    # Generators
    # =========================================================================

    def get_generators(self, site_code: str | None = None) -> list[dict[str, Any]]:
        """Get all generators, optionally filtered by building."""
        query = self.client.table("generators").select("*")

        if site_code:
            site_uuid = self.get_site_uuid(site_code)
            if site_uuid:
                query = query.eq("site_id", site_uuid)

        response = query.execute()
        return response.data

    def get_generators_by_group(self, group_id: str) -> list[dict[str, Any]]:
        """Get all generators in a group."""
        group_uuid = self.get_group_uuid(group_id)
        if not group_uuid:
            return []

        response = self.client.table("generators").select("*").eq("group_id", group_uuid).execute()

        return response.data

    def get_generator_by_id(self, generator_id: str) -> dict[str, Any] | None:
        """Get generator by generator_id."""
        response = self.client.table("generators").select("*").eq("generator_id", generator_id).execute()

        if response.data:
            return response.data[0]
        return None

    def upsert_generator(self, gen_data: dict[str, Any]) -> dict[str, Any]:
        """Insert or update a generator."""
        response = self.client.table("generators").upsert(gen_data, on_conflict="generator_id").execute()
        return response.data[0] if response.data else {}

    def upsert_generators(self, generators: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Insert or update multiple generators."""
        if not generators:
            return []

        response = self.client.table("generators").upsert(generators, on_conflict="generator_id").execute()
        return response.data

    def delete_generator(self, generator_id: str) -> bool:
        """Delete a generator."""
        response = self.client.table("generators").delete().eq("generator_id", generator_id).execute()
        return len(response.data) > 0

    def update_generator_status(
        self, generator_id: str, status: str, engine_running: bool = False, on_load: bool = False
    ) -> dict[str, Any] | None:
        """Update generator operational status."""
        response = (
            self.client.table("generators")
            .update(
                {
                    "status": status,
                    "engine_running": engine_running,
                    "on_load": on_load,
                }
            )
            .eq("generator_id", generator_id)
            .execute()
        )

        if response.data:
            return response.data[0]
        return None

    def update_generator_engine(
        self, generator_id: str, rpm: int, oil_pressure_kpa: float, coolant_temp_c: float, fuel_rate_lph: float
    ) -> dict[str, Any] | None:
        """Update generator engine parameters."""
        response = (
            self.client.table("generators")
            .update(
                {
                    "rpm": rpm,
                    "oil_pressure_kpa": oil_pressure_kpa,
                    "coolant_temp_c": coolant_temp_c,
                    "fuel_rate_lph": fuel_rate_lph,
                }
            )
            .eq("generator_id", generator_id)
            .execute()
        )

        if response.data:
            return response.data[0]
        return None

    def update_generator_electrical(
        self,
        generator_id: str,
        voltage_l1: float,
        voltage_l2: float,
        voltage_l3: float,
        current_l1: float,
        current_l2: float,
        current_l3: float,
        power_kw: float,
        frequency: float,
    ) -> dict[str, Any] | None:
        """Update generator electrical output."""
        response = (
            self.client.table("generators")
            .update(
                {
                    "output_voltage_l1": voltage_l1,
                    "output_voltage_l2": voltage_l2,
                    "output_voltage_l3": voltage_l3,
                    "output_current_l1": current_l1,
                    "output_current_l2": current_l2,
                    "output_current_l3": current_l3,
                    "output_power_kw": power_kw,
                    "output_frequency": frequency,
                }
            )
            .eq("generator_id", generator_id)
            .execute()
        )

        if response.data:
            return response.data[0]
        return None

    # =========================================================================
    # Bulk Operations
    # =========================================================================

    def delete_all_by_site(self, site_code: str) -> dict[str, int]:
        """Delete all generator data for a building.

        Deletes in order: generators -> groups -> tanks (FK dependencies).

        Returns:
            Dict with counts of deleted items
        """
        site_uuid = self.get_site_uuid(site_code)
        if not site_uuid:
            return {"generators": 0, "groups": 0, "tanks": 0}

        # Delete generators first
        gen_response = self.client.table("generators").delete().eq("site_id", site_uuid).execute()

        # Delete groups
        grp_response = self.client.table("generator_groups").delete().eq("site_id", site_uuid).execute()

        # Delete tanks
        tank_response = self.client.table("diesel_tanks").delete().eq("site_id", site_uuid).execute()

        return {
            "generators": len(gen_response.data),
            "groups": len(grp_response.data),
            "tanks": len(tank_response.data),
        }

    def get_full_plant(self, site_code: str) -> dict[str, Any]:
        """Get complete generator plant configuration for a building.

        Returns:
            Dict with tanks, groups, and generators
        """
        return {
            "diesel_tanks": self.get_tanks(site_code),
            "groups": self.get_groups(site_code),
            "generators": self.get_generators(site_code),
        }
