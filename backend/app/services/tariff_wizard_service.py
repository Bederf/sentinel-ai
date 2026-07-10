"""Tariff seeding service for the onboarding wizard.

Automatically seeds the applicable municipal tariff schedule for a site
based on its geographic location. Called during the bridge-review commit
step of the SIMBIOT wizard.

The lookup chain:
  1. Resolve site municipality from sites table (address/location data)
  2. Check municipal_tariff_schedules for a matching tariff record
  3. Fall back to bundled JSON tariff files per municipality
  4. On match: upsert into municipal_tariff_schedules + ipmvp_tariff for site
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from app.database.repositories.tariff_schedule_repository import TariffScheduleRepository
from app.database.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)

# Map known site codes to their municipalities for tariff lookup.
# Extended as new sites are onboarded.
_SITE_MUNICIPALITY_MAP: dict[str, str] = {
    "site-005": "eThekwini",
}

# Bundled tariff JSON files by municipality name (lowercase key).
_TARIFF_FILES: dict[str, str] = {
    "ethekwini": "ethekwini_2025_26.json",
}


async def seed_site_tariff(site_id: str) -> dict[str, Any] | None:
    """Look up and seed the applicable tariff for a site.

    Returns dict with ``tariff_name`` and ``municipality`` if seeded,
    or ``None`` if no tariff is available for this site's location.
    """
    municipality = _resolve_municipality(site_id)
    if not municipality:
        logger.info("No municipality mapping for %s — tariff seeding skipped", site_id)
        return None

    repo = TariffScheduleRepository()

    # 1. Check if tariff already exists in the schedule store
    existing = repo.list_tariffs(municipality=municipality, utility_type="electricity")
    tariff_data: dict[str, Any] | None = None
    if existing:
        tariff_record = existing[0]
    else:
        # 2. Fall back to bundled JSON
        tariff_data = _load_bundled_tariff(municipality)
        if not tariff_data:
            logger.warning("No bundled tariff found for municipality '%s'", municipality)
            return None

        payload = {
            "municipality": municipality,
            "tariff_name": tariff_data.get("tariff_name", "Bulk Consumer TOU"),
            "utility_type": "electricity",
            "effective_date": tariff_data.get("effective_date", "2025-07-01"),
            "expiry_date": tariff_data.get("expiry_date", "2026-06-30"),
            "tariff_data": tariff_data,
        }
        tariff_record = repo.upsert_tariff(payload)

    if not tariff_record:
        logger.warning("Failed to upsert tariff for %s", site_id)
        return None

    # 3. Link tariff to site via ipmvp_tariff
    tariff_name = tariff_record.get("tariff_name")
    if not tariff_name and tariff_data:
        tariff_name = tariff_data.get("tariff_name", "Bulk Consumer TOU")
    tariff_name = tariff_name or "Bulk Consumer TOU"
    _link_tariff_to_site(site_id, tariff_record, tariff_name)

    logger.info("Seeded tariff '%s' for %s (%s)", tariff_name, site_id, municipality)
    return {"tariff_name": tariff_name, "municipality": municipality}


def _resolve_municipality(site_id: str) -> str | None:
    """Resolve municipality from site location data or static map."""
    # Check static map first
    if site_id in _SITE_MUNICIPALITY_MAP:
        return _SITE_MUNICIPALITY_MAP[site_id]

    # Try Supabase sites table (address/city fields)
    try:
        client = get_supabase_client()
        result = client.table("sites").select("address, city, province").eq("code", site_id).limit(1).execute()
        if result.data:
            row = result.data[0]
            city = (row.get("city") or "").strip()
            address = (row.get("address") or "").strip()
            # Crude municipality detection from address text
            for known in [
                "eThekwini",
                "Durban",
                "Johannesburg",
                "City Power",
                "Tshwane",
                "Cape Town",
                "Nelson Mandela",
            ]:
                if known.lower() in city.lower() or known.lower() in address.lower():
                    return known
    except Exception as exc:
        logger.warning("Failed to resolve municipality for %s from DB: %s", site_id, exc)

    return None


def _load_bundled_tariff(municipality: str) -> dict[str, Any] | None:
    """Load tariff data from bundled JSON files."""
    key = municipality.lower().replace(" ", "_").replace("-", "_")
    filename = _TARIFF_FILES.get(key)
    if not filename:
        return None

    path = Path(__file__).parent.parent / "data" / "solar" / "tariffs" / filename
    if not path.exists():
        logger.warning("Bundled tariff file not found: %s", path)
        return None

    try:
        import json

        with open(path) as f:
            return json.load(f)
    except Exception as exc:
        logger.warning("Failed to load bundled tariff %s: %s", path, exc)
        return None


def _link_tariff_to_site(site_id: str, tariff_record: dict[str, Any], tariff_name: str) -> None:
    """Write the tariff reference into ipmvp_tariff for the site."""
    try:
        client = get_supabase_client()
        client.table("ipmvp_tariff").upsert(
            {
                "site_id": site_id,
                "tariff_data": tariff_record.get("tariff_data", {}),
                "source": "onboarding_wizard",
            },
            on_conflict="site_id",
        ).execute()
        logger.info("Linked tariff '%s' to %s via ipmvp_tariff", tariff_name, site_id)
    except Exception as exc:
        logger.warning("Failed to link tariff to ipmvp_tariff for %s: %s", site_id, exc)
