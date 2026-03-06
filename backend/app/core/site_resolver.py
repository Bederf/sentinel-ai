"""Site Resolver — single source of truth for registered site resolution.

SENTINEL should never need to know a site ID in advance. There is no default site.
There is only "the registered sites."

This module provides:
- get_registered_sites()    -> list[dict]   All registered sites
- get_registered_site_ids() -> list[str]    Just the site ID codes
- get_primary_site()        -> dict | None  First registered site (or None)
- require_any_site()        -> FastAPI dependency that validates a site_id query param

Fallback order: Supabase -> JSON (backend/app/data/sites.json)
"""

import json
import logging
from pathlib import Path

from fastapi import HTTPException, Query

logger = logging.getLogger(__name__)

# JSON fallback path
_SITES_JSON = Path(__file__).parent.parent / "data" / "sites.json"

# In-memory cache (refreshed each call to Supabase; JSON is stable)
_cached_sites: list[dict] | None = None
_cache_source: str | None = None


def _load_from_supabase() -> list[dict] | None:
    """Attempt to load sites from Supabase.

    Returns:
        List of site dicts on success, None if Supabase is unavailable.
    """
    try:
        from app.database.supabase_client import get_supabase_client

        client = get_supabase_client()
        result = client.table("sites").select("*").execute()
        if result.data:
            return result.data
        # Empty table is a valid result — return empty list, not None
        return []
    except Exception as e:
        logger.debug("Supabase sites query failed (falling back to JSON): %s", e)
        return None


def _load_from_json() -> list[dict]:
    """Load sites from the local JSON fallback file.

    Returns:
        List of site dicts (may be empty if file is missing/corrupt).
    """
    try:
        if _SITES_JSON.exists():
            data = json.loads(_SITES_JSON.read_text())
            if isinstance(data, list):
                return data
            logger.warning("sites.json is not a list — returning empty")
            return []
        logger.info("No sites.json found at %s", _SITES_JSON)
        return []
    except Exception as e:
        logger.warning("Failed to load sites.json: %s", e)
        return []


def get_registered_sites() -> list[dict]:
    """Return all registered sites.

    Uses 2-tier fallback: Supabase -> JSON.
    Each dict has at minimum ``id`` and ``code`` fields.

    Returns:
        List of site dicts. Empty list if no sites are registered.
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
    """Return just the site ID strings (site codes) from registered sites.

    Convenience wrapper to avoid repeated list comprehensions in callers.

    Returns:
        List of site code strings, e.g. ['site-002', 'site-005'].
    """
    sites = get_registered_sites()
    return [s["code"] for s in sites if s.get("code")]


def get_primary_site() -> dict | None:
    """Return the first (or only) registered site, or None if empty.

    Useful for single-site deployments or as a safe accessor.

    Returns:
        Site dict or None.
    """
    sites = get_registered_sites()
    return sites[0] if sites else None


async def require_any_site(
    site_id: str = Query(..., description="Site code (e.g. site-002)"),
) -> str:
    """FastAPI Depends() dependency that validates a site_id query parameter.

    Checks that the requested site_id exists among registered sites.
    Raises HTTPException(404) if not found.

    Returns:
        The validated site_id string.
    """
    site_ids = get_registered_site_ids()
    if site_id not in site_ids:
        raise HTTPException(
            status_code=404,
            detail=f"Site '{site_id}' not found among registered sites: {site_ids}",
        )
    return site_id
