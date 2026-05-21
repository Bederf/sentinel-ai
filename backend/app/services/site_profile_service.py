"""
SiteProfileService — Phase 191 Wave 1.

Provides CRUD operations for site_profiles and the confirmed-profile gate
used by the phase transition handler in sites.py.
"""

import logging
from datetime import datetime

from app.database.supabase_client import get_supabase_client
from app.models.site_profile import SiteProfileCreate

logger = logging.getLogger("sentinel.site_profile_service")


class SiteProfileService:
    """Manages building profiles for new site onboarding."""

    def create_profile(self, site_id: str, payload: SiteProfileCreate, confirmed_by: str) -> dict:
        """Create or update a site profile (idempotent upsert).

        Resolves site_id (code like "S005" or UUID) to UUID before writing.
        Sets confirmed_at and confirmed_by on every upsert.
        Writes an audit log entry.
        """
        site_uuid = self._resolve_site_uuid(site_id)
        if site_uuid is None:
            raise ValueError(f"Site not found: {site_id}")

        client = get_supabase_client()

        row = {
            "site_id": site_uuid,
            "building_type": payload.building_type,
            "primary_objective": payload.primary_objective,
            "objective_weights": payload.objective_weights.model_dump(),
            "operating_schedule": payload.operating_schedule.model_dump(),
            "tariff_structure": payload.tariff_structure,
            "on_site_generation": payload.on_site_generation.model_dump(),
            "temp_band_min_c": payload.temp_band_min_c,
            "temp_band_max_c": payload.temp_band_max_c,
            "clinical_zones_present": payload.clinical_zones_present,
            "regulatory_frameworks": payload.regulatory_frameworks,
            "confirmed_at": datetime.utcnow().isoformat(),
            "confirmed_by": confirmed_by,
        }

        result = client.table("site_profiles").upsert(row, on_conflict="site_id").execute()

        if not result.data:
            raise RuntimeError(f"Profile upsert failed for site {site_id}")

        # Audit log
        try:
            client.table("audit_log").insert(
                {
                    "action": "site_profile_created",
                    "entity_type": "site_profile",
                    "entity_id": site_uuid,
                    "site_id": site_id,
                    "performed_by": confirmed_by,
                    "details": {"building_type": payload.building_type, "primary_objective": payload.primary_objective},
                }
            ).execute()
        except Exception as audit_err:
            logger.warning(f"Audit log write failed for site {site_id}: {audit_err}")

        return result.data[0]

    def get_profile(self, site_id: str) -> dict | None:
        """Retrieve a site profile by site_id (code or UUID)."""
        site_uuid = self._resolve_site_uuid(site_id)
        if site_uuid is None:
            return None

        client = get_supabase_client()
        result = client.table("site_profiles").select("*").eq("site_id", site_uuid).limit(1).execute()

        return result.data[0] if result.data else None

    def has_confirmed_profile(self, site_id: str) -> bool:
        """Return True only if profile exists AND confirmed_at is set.

        Gate check called by the phase transition handler before
        allowing a site to enter shadow or advisory mode.
        """
        site_uuid = self._resolve_site_uuid(site_id)
        if site_uuid is None:
            return False

        client = get_supabase_client()
        result = client.table("site_profiles").select("confirmed_at").eq("site_id", site_uuid).limit(1).execute()

        if not result.data:
            return False
        return result.data[0].get("confirmed_at") is not None

    def _resolve_site_uuid(self, site_id: str) -> str | None:
        """Resolve site_id to UUID.

        - If already a UUID (36 chars, contains hyphens) → return as-is
        - Otherwise query sites WHERE code = site_id → return id
        - Return None if not found
        """
        if site_id.count("-") >= 3 and len(site_id) == 36:
            return site_id  # Already a UUID

        client = get_supabase_client()
        result = client.table("sites").select("id").eq("code", site_id).limit(1).execute()

        return result.data[0]["id"] if result.data else None
