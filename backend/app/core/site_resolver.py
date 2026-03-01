"""Site Resolver — single source of truth for registered building resolution.

SENTINEL should never need to know a site ID in advance. There is no default site.
There is only "the registered buildings."

This module provides:
- get_registered_sites()    -> list[dict]   All registered buildings
- get_registered_site_ids() -> list[str]    Just the site ID codes
- get_primary_site()        -> dict | None  First registered building (or None)
- require_any_site()        -> FastAPI dependency that validates a building_id query param

Fallback order: Supabase -> JSON (backend/app/data/buildings.json)
"""

import json
import logging
from pathlib import Path
from typing import Optional

from fastapi import HTTPException, Query

logger = logging.getLogger(__name__)

# JSON fallback path
_BUILDINGS_JSON = Path(__file__).parent.parent / "data" / "buildings.json"

# In-memory cache (refreshed each call to Supabase; JSON is stable)
_cached_sites: Optional[list[dict]] = None
_cache_source: Optional[str] = None


def _load_from_supabase() -> Optional[list[dict]]:
    """Attempt to load buildings from Supabase.

    Returns:
        List of building dicts on success, None if Supabase is unavailable.
    """
    try:
        from app.database.supabase_client import get_supabase_client

        client = get_supabase_client()
        result = client.table("buildings").select("*").execute()
        if result.data:
            return result.data
        # Empty table is a valid result — return empty list, not None
        return []
    except Exception as e:
        logger.debug("Supabase buildings query failed (falling back to JSON): %s", e)
        return None


def _load_from_json() -> list[dict]:
    """Load buildings from the local JSON fallback file.

    Returns:
        List of building dicts (may be empty if file is missing/corrupt).
    """
    try:
        if _BUILDINGS_JSON.exists():
            data = json.loads(_BUILDINGS_JSON.read_text())
            if isinstance(data, list):
                return data
            logger.warning("buildings.json is not a list — returning empty")
            return []
        logger.info("No buildings.json found at %s", _BUILDINGS_JSON)
        return []
    except Exception as e:
        logger.warning("Failed to load buildings.json: %s", e)
        return []


def get_registered_sites() -> list[dict]:
    """Return all registered buildings.

    Uses 2-tier fallback: Supabase -> JSON.
    Each dict has at minimum ``id`` and ``code`` fields.

    Returns:
        List of building dicts. Empty list if no buildings are registered.
    """
    global _cached_sites, _cache_source

    # Try Supabase first
    supabase_result = _load_from_supabase()
    if supabase_result is not None:
        _cached_sites = supabase_result
        _cache_source = "supabase"
        return supabase_result

    # Fallback to JSON
    json_result = _load_from_json()
    _cached_sites = json_result
    _cache_source = "json"
    return json_result


def get_registered_site_ids() -> list[str]:
    """Return just the site ID strings (building codes) from registered buildings.

    Convenience wrapper to avoid repeated list comprehensions in callers.

    Returns:
        List of site code strings, e.g. ['site-002', 'site-005'].
    """
    sites = get_registered_sites()
    return [s["code"] for s in sites if s.get("code")]


def get_primary_site() -> Optional[dict]:
    """Return the first (or only) registered building, or None if empty.

    Useful for single-site deployments or as a safe accessor.

    Returns:
        Building dict or None.
    """
    sites = get_registered_sites()
    return sites[0] if sites else None


async def require_any_site(
    building_id: str = Query(..., description="Building code (e.g. site-002)"),
) -> str:
    """FastAPI Depends() dependency that validates a building_id query parameter.

    Checks that the requested building_id exists among registered buildings.
    Raises HTTPException(404) if not found.

    Returns:
        The validated building_id string.
    """
    site_ids = get_registered_site_ids()
    if building_id not in site_ids:
        raise HTTPException(
            status_code=404,
            detail=f"Building '{building_id}' not found among registered sites: {site_ids}",
        )
    return building_id
