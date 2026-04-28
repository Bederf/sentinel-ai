"""Profile management service for optimization profiles and site-level configuration.

Handles loading, caching, and management of optimization profiles and site-specific
profile configurations including zone and schedule overrides.
"""

import copy
import json
import logging
from pathlib import Path
from typing import Any

from app.models.optimization import (
    ScheduleProfileOverride,
    SiteProfileConfig,
    ZoneProfileOverride,
)

logger = logging.getLogger(__name__)


def _normalize_site_id(site_id: str) -> str:
    """Normalize site_id to site code (e.g. site-002 → S002)."""
    import re

    normalized = site_id.strip()
    m = re.fullmatch(r"site-(\d+)", normalized, re.IGNORECASE)
    if m:
        return f"S{m.group(1).zfill(3)}"
    return normalized


class ProfileService:
    """Service for managing optimization profiles and site configurations."""

    def __init__(self):
        """Initialize ProfileService and load profiles from JSON."""
        self.profiles: dict[str, dict[str, Any]] = self._load_profiles()
        self.site_configs: dict[str, SiteProfileConfig] = {}  # Runtime cache

    def _load_profiles(self) -> dict[str, dict[str, Any]]:
        """Load optimization profiles from JSON file.

        Returns:
            Dictionary mapping profile IDs to profile definitions
        """
        profile_path = Path(__file__).parent.parent / "data" / "optimization_profiles.json"

        if not profile_path.exists():
            logger.warning(f"Optimization profiles file not found: {profile_path}")
            return {}

        try:
            with open(profile_path) as f:
                data = json.load(f)
                # Map profile names to IDs for consistent access
                profiles = {}
                for profile_id, profile_data in data.get("profiles", {}).items():
                    profiles[profile_id] = profile_data
                logger.info(f"Loaded {len(profiles)} optimization profiles")
                return profiles
        except Exception as e:
            logger.error(f"Error loading optimization profiles: {e}")
            return {}

    def get_site_profile(self, site_id: str) -> dict[str, Any] | None:
        """Get active profile for a site.

        Returns the profile object that corresponds to the site's active profile setting.

        Args:
            site_id: Site identifier

        Returns:
            Profile dictionary or None if not found
        """
        config = self.load_site_profile_config(site_id)
        logger.warning(
            f"[PROFILE] get_site_profile({site_id!r}) -> config.active_profile={config.active_profile if config else None}"
        )
        if not config:
            return None

        base_profile = self.profiles.get(config.active_profile)
        if not base_profile:
            return None

        # Copy to avoid mutating global profile definitions.
        profile = copy.deepcopy(base_profile)

        # Merge feedback-derived scoring inputs for dynamic recommendation ranking.
        try:
            from app.services.ml_feedback_service import get_ml_feedback_service

            scoring_inputs = get_ml_feedback_service().get_scoring_inputs(site_id)
            module_multipliers = scoring_inputs.get("module_multipliers", {})
            if isinstance(module_multipliers, dict):
                profile["module_multipliers"] = module_multipliers
                profile["feedback_scoring_refreshed_at"] = scoring_inputs.get("refreshed_at")
        except Exception as e:
            logger.debug(f"Could not load feedback scoring inputs for {site_id}: {e}")

        return profile

    def get_zone_profile(self, site_id: str, zone_id: str) -> dict[str, Any] | None:
        """Get profile for specific zone (handles overrides).

        If a zone has an override, returns the override profile. Otherwise,
        returns the site's active profile.

        Args:
            site_id: Site identifier
            zone_id: Zone identifier

        Returns:
            Profile dictionary or None if not found
        """
        config = self.load_site_profile_config(site_id)
        if not config:
            return None

        # Check for zone-specific override
        for override in config.zone_overrides:
            if override.zone_id == zone_id:
                return self.profiles.get(override.profile)

        # Fall back to site profile
        return self.get_site_profile(site_id)

    def get_profile_params(self, profile: str, module: str) -> dict[str, Any]:
        """Get module-specific parameters for a profile.

        Extracts parameters relevant to a specific module (e.g., hvac, lighting).

        Args:
            profile: Profile ID ("sweat_assets", "comfort", "cost")
            module: Module name ("hvac", "lighting", "power")

        Returns:
            Dictionary of module-specific parameters
        """
        profile_data = self.profiles.get(profile, {})
        if not profile_data:
            return {}

        # Extract weights that apply to this module
        weights = profile_data.get("weights", {})
        thresholds = profile_data.get("thresholds", {})

        module_params = {
            "weights": weights,
            "thresholds": thresholds,
        }

        return module_params

    def save_site_profile_config(self, site_id: str, config: SiteProfileConfig) -> bool:
        """Save profile configuration to building.json.

        Persists the profile configuration to the building's JSON file.

        Args:
            site_id: Site identifier
            config: SiteProfileConfig to save

        Returns:
            True if successful, False otherwise
        """
        try:
            site_path = Path(__file__).parent.parent / "data" / "buildings" / site_id / "building.json"

            if not site_path.exists():
                logger.warning(f"Building file not found: {site_path}")
                return False

            with open(site_path) as f:
                site_data = json.load(f)

            # Update optimization section
            site_data["optimization"] = config.to_dict()

            with open(site_path, "w") as f:
                json.dump(site_data, f, indent=2)

            # Update runtime cache
            self.site_configs[site_id] = config

            logger.info(f"Saved profile config for site {site_id}")
            return True

        except Exception as e:
            logger.error(f"Error saving profile config for {site_id}: {e}")
            return False

    def load_site_profile_config(self, site_id: str) -> SiteProfileConfig | None:
        """Load profile configuration for a site.

        Supabase `sites.optimization_settings` is the primary authority (Phase 183).
        Local JSON is only a backward-compatibility fallback.

        Args:
            site_id: Site identifier (S002 or site-002)

        Returns:
            SiteProfileConfig (never None — always returns a default if not found)
        """
        site_code = _normalize_site_id(site_id)

        # Check runtime cache first
        if site_code in self.site_configs:
            return self.site_configs[site_code]

        # 1) Try Supabase first (primary authority since Phase 183)
        # Try normalized code first, then original (DB uses 'site-002' format)
        try:
            from app.database.supabase_client import get_supabase_client

            client = get_supabase_client()
            for code in [site_code, site_id]:
                try:
                    result = client.table("sites").select("optimization_settings").eq("code", code).execute()
                    if result.data:
                        opt = result.data[0].get("optimization_settings") or {}
                        if opt:
                            config = SiteProfileConfig.from_dict(opt)
                            config.site_id = site_code
                            self.site_configs[site_code] = config
                            logger.info(f"Loaded profile config for {site_code} from Supabase (code={code})")
                            return config
                except Exception as e:
                    logger.warning(f"Supabase query failed for code={code!r}: {e}")
        except Exception as e:
            logger.warning(f"Could not load profile config from Supabase for {site_code}: {e}")

        # 2) Fall back to local JSON (backward compatibility)
        site_path = Path(__file__).parent.parent / "data" / "buildings" / site_code / "building.json"

        if not site_path.exists():
            # Return default config instead of None (matches existing fallback behavior)
            config = SiteProfileConfig(
                site_id=site_code,
                active_profile="balanced",
                control_tier="supervised",
            )
            self.site_configs[site_code] = config
            return config

        try:
            with open(site_path) as f:
                site_data = json.load(f)

            optimization_data = site_data.get("optimization", {})
            if not optimization_data:
                config = SiteProfileConfig(
                    site_id=site_code,
                    active_profile="cost",
                    control_tier="supervised",
                )
                self.site_configs[site_code] = config
                return config

            config = SiteProfileConfig.from_dict(optimization_data)
            config.site_id = site_code

            self.site_configs[site_code] = config
            return config

        except Exception as e:
            logger.error(f"Error loading profile config for {site_id}: {e}")
            config = SiteProfileConfig(
                site_id=site_code,
                active_profile="balanced",
                control_tier="supervised",
            )
            return config

    def list_profiles(self) -> list[dict[str, Any]]:
        """List all available optimization profiles.

        Returns:
            List of profile objects with metadata
        """
        profiles_list = []
        for profile_id, profile_data in self.profiles.items():
            profiles_list.append(
                {
                    "id": profile_id,
                    "name": profile_data.get("name", profile_id),
                    "description": profile_data.get("description", ""),
                    "weights": profile_data.get("weights", {}),
                }
            )
        return profiles_list

    def update_zone_override(self, site_id: str, zone_id: str, profile: str, reason: str) -> bool:
        """Add or update a zone profile override.

        Args:
            site_id: Site identifier
            zone_id: Zone identifier
            profile: Profile ID to apply
            reason: Reason for override

        Returns:
            True if successful, False otherwise
        """
        config = self.load_site_profile_config(site_id)
        if not config:
            return False

        # Remove existing override for this zone if present
        config.zone_overrides = [zo for zo in config.zone_overrides if zo.zone_id != zone_id]

        # Add new override
        if profile:  # Only add if profile is not empty
            config.zone_overrides.append(ZoneProfileOverride(zone_id=zone_id, profile=profile, reason=reason))

        return self.save_site_profile_config(site_id, config)

    def remove_zone_override(self, site_id: str, zone_id: str) -> bool:
        """Remove a zone profile override.

        Args:
            site_id: Site identifier
            zone_id: Zone identifier

        Returns:
            True if successful, False otherwise
        """
        config = self.load_site_profile_config(site_id)
        if not config:
            return False

        config.zone_overrides = [zo for zo in config.zone_overrides if zo.zone_id != zone_id]

        return self.save_site_profile_config(site_id, config)

    def add_schedule_override(
        self,
        site_id: str,
        day_of_week: str,
        start_hour: int,
        end_hour: int,
        profile: str,
        reason: str,
    ) -> bool:
        """Add a schedule-based profile override.

        Args:
            site_id: Site identifier
            day_of_week: Day name ("monday" through "sunday")
            start_hour: Start hour (0-23)
            end_hour: End hour (0-23)
            profile: Profile ID to apply
            reason: Reason for override

        Returns:
            True if successful, False otherwise
        """
        config = self.load_site_profile_config(site_id)
        if not config:
            return False

        config.schedule_overrides.append(
            ScheduleProfileOverride(
                day_of_week=day_of_week,
                start_hour=start_hour,
                end_hour=end_hour,
                profile=profile,
                reason=reason,
            )
        )

        return self.save_site_profile_config(site_id, config)

    def clear_cache(self, site_id: str | None = None) -> None:
        """Clear runtime cache.

        Args:
            site_id: Specific site to clear, or None to clear all
        """
        if site_id:
            self.site_configs.pop(site_id, None)
        else:
            self.site_configs.clear()
        logger.info(f"Cleared profile cache{f' for {site_id}' if site_id else ''}")


# Singleton instance
_profile_service: ProfileService | None = None


def get_profile_service() -> ProfileService:
    """Get or create ProfileService singleton.

    Returns:
        ProfileService instance
    """
    global _profile_service
    if _profile_service is None:
        _profile_service = ProfileService()
    return _profile_service
