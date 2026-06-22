"""
Site Creation Service — handles auto-incrementing site ID generation for new site onboarding.

When the SIMBIOT wizard onboards a new site, this service:
1. Generates the next sequential site code (S001 → S002 → ... → S006)
2. Creates the site record in Supabase
3. Handles collision retry for concurrent onboarding attempts
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger("sentinel.site_creation")

# Max retry attempts when a site code collision is detected
_MAX_CREATE_RETRIES = 3


class SiteCreationService:
    """Creates new sites with auto-generated or manual site codes."""

    def __init__(self, supabase_client=None):
        self._supabase = supabase_client

    @property
    def supabase(self):
        if self._supabase is None:
            from app.database import get_supabase_client as get_supabase

            self._supabase = get_supabase()
        return self._supabase

    def generate_next_site_code(self) -> str:
        """
        Generate the next sequential site code.

        Logic:
        1. Query all existing site_codes from sites table
        2. Extract numeric suffix (S001 → 1, S002 → 2)
        3. Find max number
        4. Return max + 1, zero-padded to 3 digits

        Returns:
            Next site code string (e.g., "S006")

        Examples:
            Existing: [S001, S002, S005] → Returns: S006
            Existing: [S001, S002]         → Returns: S003
            Existing: []                   → Returns: S001
        """
        result = self.supabase.table("sites").select("code").execute()

        if not result.data:
            return "S001"

        max_num = 0
        for row in result.data:
            code = row.get("code", "")
            match = re.match(r"^site-(\d+)$", code)
            if match:
                num = int(match.group(1))
                if num > max_num:
                    max_num = num

        return f"site-{max_num + 1:03d}"

    def create_site(
        self,
        site_name: str,
        building_type: str,
        location: str,
        gross_floor_area: float | None = None,
        year_built: int | None = None,
        latitude: float | None = None,
        longitude: float | None = None,
        contact_phone: str | None = None,
        contact_email: str | None = None,
        whatsapp_phone: str | None = None,
        occupancy_capacity: int | None = None,
        total_desks: int | None = None,
        parking_bays: int | None = None,
        nmd_limit_kva: float | None = None,
        demand_charge_per_kva: float | None = None,
        electricity_provider: str | None = None,
        operating_hours: dict[str, Any] | None = None,
        optimization_settings: dict[str, Any] | None = None,
        building_geometry: dict[str, Any] | None = None,
        site_code: str | None = None,
        enabled: bool = True,
        onboarding_phase: str = "shadow_live",
    ) -> dict[str, Any]:
        """
        Create a new site record.

        Args:
            site_name: Display name (e.g., "Example Hospital")
            building_type: Type (office, retail, hospital, etc.)
            location: Physical address or city
            gross_floor_area: Square metres
            site_code: Optional manual override (auto-generated if None)
            enabled: Whether site is active
            onboarding_phase: Initial phase (default: shadow_live)

        Returns:
            Created site record dict including auto-generated site_code

        Raises:
            RuntimeError: After max retries on unique constraint violation
        """
        if not site_code:
            site_code = self.generate_next_site_code()
            logger.info("[SCS] Auto-generated site code: %s", site_code)

        for attempt in range(_MAX_CREATE_RETRIES):
            try:
                payload: dict[str, Any] = {
                    "code": site_code,
                    "name": site_name,
                    "type": building_type,
                    "address": location,
                    "optimization_enabled": enabled,
                    "onboarding_phase": onboarding_phase,
                }
                if gross_floor_area is not None:
                    payload["sqm"] = gross_floor_area
                optional_fields = {
                    "year_built": year_built,
                    "latitude": latitude,
                    "longitude": longitude,
                    "contact_phone": contact_phone,
                    "contact_email": contact_email,
                    "whatsapp_phone": whatsapp_phone,
                    "occupancy_capacity": occupancy_capacity,
                    "total_desks": total_desks,
                    "parking_bays": parking_bays,
                    "nmd_limit_kva": nmd_limit_kva,
                    "demand_charge_per_kva": demand_charge_per_kva,
                    "electricity_provider": electricity_provider,
                    "operating_hours": operating_hours,
                    "optimization_settings": optimization_settings,
                    "building_geometry": building_geometry,
                }
                payload.update({key: value for key, value in optional_fields.items() if value is not None})

                result = self.supabase.table("sites").insert(payload).execute()

                if result.data:
                    logger.info(
                        "[SCS] Created site %s: %s (%s)",
                        site_code,
                        site_name,
                        building_type,
                    )
                    self._seed_phase_promotion_gates(site_code)
                    return result.data[0]

                raise RuntimeError(f"No data returned when creating site {site_code}")

            except Exception as exc:
                error_str = str(exc)
                # Check for unique constraint violation (Postgres error code 23505)
                if "23505" in error_str or "unique constraint" in error_str.lower():
                    if attempt < _MAX_CREATE_RETRIES - 1:
                        logger.warning(
                            "[SCS] Site code collision for %s, retrying with new ID (attempt %d/%d)",
                            site_code,
                            attempt + 1,
                            _MAX_CREATE_RETRIES,
                        )
                        site_code = self.generate_next_site_code()
                        continue
                    raise RuntimeError(
                        f"Failed to create site after {_MAX_CREATE_RETRIES} attempts due to repeated code collisions"
                    ) from exc
                raise

        raise RuntimeError(f"Failed to create site {site_code} after {_MAX_CREATE_RETRIES} attempts")

    def get_site_by_code(self, site_code: str) -> dict[str, Any] | None:
        """Fetch a site by its code, or None if not found."""
        result = self.supabase.table("sites").select("*").eq("code", site_code).execute()
        return result.data[0] if result.data else None

    def _seed_phase_promotion_gates(self, site_code: str) -> None:
        """Seed standard phase promotion gates for a newly created site.

        Mirrors the gates defined in the 20260509_001 migration for site-002.
        Called automatically during SIMBIOT wizard onboarding so every new site
        has a promotion path from shadow_live through to automatic.
        """
        gates = [
            # shadow_live → advisory (6 gates)
            (
                site_code,
                "shadow_live",
                "advisory",
                "ml_hours_ingested",
                "threshold",
                72,
                ">=",
                "ML training hours accumulated",
            ),
            (
                site_code,
                "shadow_live",
                "advisory",
                "bridge_connected",
                "boolean",
                None,
                "==true",
                "Shadow Bridge connected and polling",
            ),
            (
                site_code,
                "shadow_live",
                "advisory",
                "freshness_hours_max",
                "threshold",
                4.0,
                "<=",
                "Data freshness (max age in hours)",
            ),
            (
                site_code,
                "shadow_live",
                "advisory",
                "anomaly_scores_writing",
                "count",
                0,
                ">",
                "Anomaly scores writing to equipment_analytics",
            ),
            (
                site_code,
                "shadow_live",
                "advisory",
                "match_coverage_min_pct",
                "threshold",
                50.0,
                ">=",
                "Equipment BACnet point match coverage %",
            ),
            (
                site_code,
                "shadow_live",
                "advisory",
                "error_rate_max_pct",
                "threshold",
                10.0,
                "<=",
                "Adapter error rate %",
            ),
            # advisory → supervised (5 gates)
            (
                site_code,
                "advisory",
                "supervised",
                "ml_hours_ingested",
                "threshold",
                500,
                ">=",
                "ML training hours (extended learning period)",
            ),
            (
                site_code,
                "advisory",
                "supervised",
                "time_in_advisory_days",
                "threshold",
                30,
                ">=",
                "Days in advisory phase before supervised",
            ),
            (
                site_code,
                "advisory",
                "supervised",
                "recommendations_generated",
                "count",
                50,
                ">=",
                "Total recommendations generated",
            ),
            (
                site_code,
                "advisory",
                "supervised",
                "no_safety_violations_30d",
                "boolean",
                None,
                "==true",
                "No safety violations in last 30 days",
            ),
            (
                site_code,
                "advisory",
                "supervised",
                "bridge_connected_uptime_pct",
                "threshold",
                0.90,
                ">=",
                "Bridge connected uptime >= 90%",
            ),
            # supervised → automatic (6 gates)
            (
                site_code,
                "supervised",
                "automatic",
                "ml_hours_ingested",
                "threshold",
                2000,
                ">=",
                "ML training hours (mature deployment)",
            ),
            (
                site_code,
                "supervised",
                "automatic",
                "approval_accuracy",
                "threshold",
                0.85,
                ">=",
                "Recommendation approval accuracy >= 85%",
            ),
            (
                site_code,
                "supervised",
                "automatic",
                "false_positive_rate",
                "threshold",
                0.10,
                "<=",
                "False positive rate <= 10%",
            ),
            (
                site_code,
                "supervised",
                "automatic",
                "recommendations_approved",
                "count",
                30,
                ">=",
                "Recommendations approved by operators",
            ),
            (
                site_code,
                "supervised",
                "automatic",
                "no_safety_violations_7d",
                "boolean",
                None,
                "==true",
                "No safety violations in last 7 days",
            ),
            (
                site_code,
                "supervised",
                "automatic",
                "human_approved_autonomous",
                "boolean",
                None,
                "==true",
                "At least one human-approved autonomous action logged",
            ),
        ]

        try:
            data = [
                {
                    "site_id": g[0],
                    "from_phase": g[1],
                    "to_phase": g[2],
                    "gate_name": g[3],
                    "gate_type": g[4],
                    "threshold_value": g[5],
                    "operator": g[6],
                    "description": g[7],
                }
                for g in gates
            ]
            self.supabase.table("phase_promotion_gates").upsert(
                data,
                on_conflict="site_id, from_phase, to_phase, gate_name",
            ).execute()
            logger.info("[SCS] Seeded %d phase promotion gates for %s", len(gates), site_code)
        except Exception as e:
            logger.warning("[SCS] Failed to seed phase promotion gates for %s: %s", site_code, e)
