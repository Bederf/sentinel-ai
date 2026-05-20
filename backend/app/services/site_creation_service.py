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
        site_code: str | None = None,
        enabled: bool = True,
        onboarding_phase: str = "advisory",
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
            onboarding_phase: Initial phase (default: monitoring)

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
                    payload["gross_floor_area"] = gross_floor_area

                result = self.supabase.table("sites").insert(payload).execute()

                if result.data:
                    logger.info(
                        "[SCS] Created site %s: %s (%s)",
                        site_code,
                        site_name,
                        building_type,
                    )
                    return result.data[0]

                raise RuntimeError(f"No data returned when creating site {site_code}")

            except Exception as exc:
                error_str = str(exc)
                # Check for unique constraint violation (Postgres error code 23505)
                if "23505" in error_str or "unique constraint" in error_str.lower():
                    if attempt < _MAX_CREATE_RETRIES - 1:
                        logger.warning(
                            "[SCS] Site code collision for %s, retrying with new ID "
                            "(attempt %d/%d)",
                            site_code,
                            attempt + 1,
                            _MAX_CREATE_RETRIES,
                        )
                        site_code = self.generate_next_site_code()
                        continue
                    raise RuntimeError(
                        f"Failed to create site after {_MAX_CREATE_RETRIES} attempts "
                        f"due to repeated code collisions"
                    ) from exc
                raise

        raise RuntimeError(f"Failed to create site {site_code} after {_MAX_CREATE_RETRIES} attempts")

    def get_site_by_code(self, site_code: str) -> dict[str, Any] | None:
        """Fetch a site by its code, or None if not found."""
        result = self.supabase.table("sites").select("*").eq(
            "code", site_code
        ).execute()
        return result.data[0] if result.data else None
