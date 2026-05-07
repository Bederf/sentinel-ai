"""
Centralized Health Threshold Service

Provides a single source of truth for health score thresholds used across
the entire application. Reads from Supabase system_settings with fallback
to JSON settings.

Phase: Health Score Threshold Consistency Fix
"""

import logging
from datetime import datetime, timedelta

from typing import Any

from app.database.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)

# Cache TTL in seconds
CACHE_TTL = 300  # 5 minutes

# Default thresholds (used as ultimate fallback)
DEFAULT_THRESHOLDS = {"healthy": 90, "warning": 70, "critical": 50}


class HealthThresholdService:
    """Centralized service for health score thresholds."""

    def __init__(self):
        self._cache: dict[str, Any] | None = None
        self._cache_expiry: datetime | None = None

    def get_thresholds(self, force_refresh: bool = False) -> dict[str, int]:
        """
        Get current health score thresholds.

        Returns:
            Dict with keys: healthy, warning, critical (all 0-100)

        Priority order:
            1. Supabase system_settings table (key: health_thresholds)
            2. JSON settings file (backend/app/data/settings.json)
            3. Hardcoded defaults (healthy: 90, warning: 70, critical: 50)
        """
        # Check cache first
        if not force_refresh and self._is_cache_valid():
            logger.debug("Using cached health thresholds")
            return self._cache

        # Try Supabase first
        thresholds = self._load_from_supabase()

        # Fallback to JSON
        if not thresholds:
            thresholds = self._load_from_json()

        # Ultimate fallback to defaults
        if not thresholds:
            logger.warning("Using default health thresholds")
            thresholds = DEFAULT_THRESHOLDS.copy()

        # Update cache
        self._cache = thresholds
        self._cache_expiry = datetime.now() + timedelta(seconds=CACHE_TTL)

        logger.info(
            f"Health thresholds: healthy={thresholds['healthy']}, "
            f"warning={thresholds['warning']}, critical={thresholds['critical']}"
        )

        return thresholds

    def get_health_status(self, health_score: float) -> str:
        """
        Get health status string from score using current thresholds.

        Uses all three configurable thresholds from settings:
        - healthy (default 90): Score >= this is "healthy"
        - critical (default 50): Score < this is "critical"
        - Everything in between is "warning"

        Args:
            health_score: Health score (0-100)

        Returns:
            Status string: "healthy", "warning", or "critical"
        """
        thresholds = self.get_thresholds()

        if health_score >= thresholds["healthy"]:
            return "healthy"
        elif health_score < thresholds["critical"]:
            return "critical"
        else:
            return "warning"

    def get_health_color(self, health_score: float) -> str:
        """
        Get color for health score display.

        Args:
            health_score: Health score (0-100)

        Returns:
            Color string: "green", "amber", or "red"
        """
        status = self.get_health_status(health_score)
        return {"healthy": "green", "warning": "amber", "critical": "red"}[status]

    def _is_cache_valid(self) -> bool:
        """Check if cache is still valid."""
        if self._cache is None or self._cache_expiry is None:
            return False
        return datetime.now() < self._cache_expiry

    def _load_from_supabase(self) -> dict[str, int] | None:
        """Load thresholds from Supabase system_settings."""
        try:
            supabase = get_supabase_client()
            result = supabase.table("system_settings").select("value").eq("key", "health_thresholds").execute()

            if result.data:
                thresholds = result.data[0]["value"]
                # Validate structure
                if all(k in thresholds for k in ["healthy", "warning", "critical"]):
                    logger.debug("Loaded health thresholds from Supabase")
                    return thresholds
                else:
                    logger.warning("Invalid health thresholds structure in Supabase")

        except Exception as e:
            logger.debug(f"Could not load thresholds from Supabase: {e}")

        return None

    def _load_from_json(self) -> dict[str, int] | None:
        """Load thresholds from JSON settings file."""
        try:
            from app.api.settings import load_settings

            settings_data = load_settings()
            thresholds = settings_data.get("healthThresholds")

            if thresholds and all(k in thresholds for k in ["healthy", "warning", "critical"]):
                logger.debug("Loaded health thresholds from JSON settings")
                return thresholds

        except Exception as e:
            logger.debug(f"Could not load thresholds from JSON: {e}")

        return None

    def clear_cache(self):
        """Clear the threshold cache (for testing or manual refresh)."""
        self._cache = None
        self._cache_expiry = None
        logger.debug("Health threshold cache cleared")


# ============================================================================
# Singleton Instance
# ============================================================================

_service_instance: HealthThresholdService | None = None


def get_health_threshold_service() -> HealthThresholdService:
    """Get singleton health threshold service instance."""
    global _service_instance
    if _service_instance is None:
        _service_instance = HealthThresholdService()
    return _service_instance


# ============================================================================
# Convenience Functions
# ============================================================================


def get_health_thresholds(force_refresh: bool = False) -> dict[str, int]:
    """
    Get current health score thresholds.

    Convenience function that uses the singleton service.
    """
    return get_health_threshold_service().get_thresholds(force_refresh)


def get_health_status(health_score: float) -> str:
    """
    Get health status string from score.

    Convenience function that uses the singleton service.
    """
    return get_health_threshold_service().get_health_status(health_score)


def get_health_color(health_score: float) -> str:
    """
    Get color for health score display.

    Convenience function that uses the singleton service.
    """
    return get_health_threshold_service().get_health_color(health_score)


def clear_health_threshold_cache():
    """Clear the health threshold cache."""
    get_health_threshold_service().clear_cache()
