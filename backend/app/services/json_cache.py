"""JSON file caching for hot-path configuration and data files.

This module provides simple in-memory caching for JSON files to avoid
repeated disk I/O in request handlers.

Usage:
    # Config files (never change after startup)
    rules = get_json_cached("safety_rules.json", ttl=None)  # No expiry

    # Data files (change infrequently, cache 5 minutes)
    equipment = get_json_cached("equipment_registry.json", ttl=300)
"""

import json
import logging
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Global cache dictionary
_CACHE: dict[str, dict[str, Any]] = {}


def get_json_cached(
    filename: str,
    data_dir: Path | None = None,
    ttl: int | None = 300,
) -> dict | list:
    """
    Load JSON file with optional caching.

    Args:
        filename: JSON file name (e.g., "safety_rules.json")
        data_dir: Directory path (defaults to app/data/)
        ttl: Cache TTL in seconds (None = no expiry, 0 = no cache)

    Returns:
        Parsed JSON data (dict or list)

    Examples:
        >>> rules = get_json_cached("safety_rules.json", ttl=None)
        >>> equipment = get_json_cached("equipment_registry.json", ttl=300)
    """
    # Default to app/data directory
    if data_dir is None:
        data_dir = Path(__file__).parent.parent / "data"

    filepath = data_dir / filename
    cache_key = str(filepath)
    now = time.time()

    # Check cache
    if cache_key in _CACHE:
        entry = _CACHE[cache_key]
        # If no TTL (config file), return cached
        if entry.get("ttl") is None:
            return entry["data"]
        # If TTL expired, skip cache
        if now - entry["timestamp"] > entry["ttl"]:
            logger.debug(f"Cache expired for {filename}")
        else:
            return entry["data"]

    # Load from file
    if not filepath.exists():
        logger.warning(f"JSON file not found: {filename}")
        return [] if filename.endswith("s.json") else {}

    try:
        with open(filepath) as f:
            data = json.load(f)

        # Cache it
        if ttl != 0:  # 0 means don't cache
            _CACHE[cache_key] = {
                "data": data,
                "timestamp": now,
                "ttl": ttl,
            }

        return data

    except Exception as e:
        logger.error(f"Failed to load JSON file {filename}: {e}")
        return [] if filename.endswith("s.json") else {}


def invalidate_cache(filename: str | None = None) -> None:
    """
    Invalidate cache entry or entire cache.

    Args:
        filename: Specific file to invalidate (None = clear all)
    """
    global _CACHE

    if filename is None:
        _CACHE.clear()
        logger.debug("Cleared JSON cache")
    else:
        data_dir = Path(__file__).parent.parent / "data"
        cache_key = str(data_dir / filename)
        if cache_key in _CACHE:
            del _CACHE[cache_key]
            logger.debug(f"Invalidated cache for {filename}")


def get_cache_stats() -> dict[str, Any]:
    """Get cache statistics."""
    return {
        "entries": len(_CACHE),
        "keys": list(_CACHE.keys()),
    }
