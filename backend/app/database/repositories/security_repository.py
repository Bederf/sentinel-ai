"""Repository for security module data operations.

Follows dual-write pattern: Supabase (primary) + JSON (fallback/offline).
Static configuration (zones, doors, cameras) loaded from security_config.json.
Dynamic state (badge events, occupancy, alarm status) persisted to both stores.
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from pathlib import Path

from app.config.settings import settings

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent.parent / "data"
CONFIG_FILE = DATA_DIR / "security_config.json"
STATE_FILE = DATA_DIR / "security_state.json"

# Singleton instance
_instance: Optional["SecurityRepository"] = None


class SecurityRepository:
    """Repository for security data with Supabase + JSON dual-write."""

    def __init__(self):
        self._client = None
        self._use_json = settings.use_json_storage
        self._config_cache: Optional[Dict[str, Any]] = None

    @property
    def client(self):
        """Lazy load Supabase client."""
        if self._client is None and not self._use_json:
            try:
                from app.database.supabase_client import get_supabase_client
                self._client = get_supabase_client()
            except Exception as e:
                logger.warning(f"Failed to get Supabase client, using JSON fallback: {e}")
                self._use_json = True
        return self._client

    # --- JSON helpers ---

    def _load_config(self) -> Dict[str, Any]:
        """Load static security configuration from JSON."""
        if self._config_cache is not None:
            return self._config_cache
        if CONFIG_FILE.exists():
            with open(CONFIG_FILE) as f:
                self._config_cache = json.load(f)
                return self._config_cache
        return {}

    def _load_state(self) -> Dict[str, Any]:
        """Load dynamic security state from JSON."""
        if STATE_FILE.exists():
            with open(STATE_FILE) as f:
                return json.load(f)
        # Initialize from config
        config = self._load_config()
        return {
            "badge_events": config.get("badge_events", []),
            "alarm_zones": config.get("alarm_zones", []),
            "occupancy": [],
        }

    def _save_state(self, state: Dict[str, Any]) -> None:
        """Save dynamic security state to JSON."""
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=2, default=str)

    # --- Access zone operations (static config) ---

    def get_zones(self) -> List[Dict[str, Any]]:
        """Get all access zones."""
        if not self._use_json and self.client:
            try:
                response = self.client.table("security_access_zones").select("*").execute()
                if response.data:
                    return response.data
            except Exception as e:
                logger.warning(f"Supabase security_access_zones query failed, using JSON: {e}")

        config = self._load_config()
        return config.get("access_zones", [])

    def get_zone(self, zone_id: str) -> Optional[Dict[str, Any]]:
        """Get a single access zone by ID."""
        zones = self.get_zones()
        return next((z for z in zones if z.get("zone_id") == zone_id), None)

    # --- Door operations (static config + dynamic status) ---

    def get_doors(self) -> List[Dict[str, Any]]:
        """Get all doors with current status."""
        if not self._use_json and self.client:
            try:
                response = self.client.table("security_doors").select("*").execute()
                if response.data:
                    return response.data
            except Exception as e:
                logger.warning(f"Supabase security_doors query failed, using JSON: {e}")

        config = self._load_config()
        return config.get("doors", [])

    def get_door_status(self, door_id: str) -> Optional[Dict[str, Any]]:
        """Get a single door by ID."""
        doors = self.get_doors()
        return next((d for d in doors if d.get("door_id") == door_id), None)

    # --- Camera operations (static config + dynamic status) ---

    def get_cameras(self) -> List[Dict[str, Any]]:
        """Get all cameras with current status."""
        if not self._use_json and self.client:
            try:
                response = self.client.table("security_cameras").select("*").execute()
                if response.data:
                    return response.data
            except Exception as e:
                logger.warning(f"Supabase security_cameras query failed, using JSON: {e}")

        config = self._load_config()
        return config.get("cameras", [])

    def get_camera_status(self, camera_id: str) -> Optional[Dict[str, Any]]:
        """Get a single camera by ID."""
        cameras = self.get_cameras()
        return next((c for c in cameras if c.get("camera_id") == camera_id), None)

    # --- Badge event operations (dynamic) ---

    def get_badge_events(self, zone_id: str = None, since: str = None, limit: int = 50) -> List[Dict[str, Any]]:
        """Get badge events with optional filtering."""
        if not self._use_json and self.client:
            try:
                query = self.client.table("security_badge_events").select("*")
                if zone_id:
                    query = query.eq("zone_id", zone_id)
                if since:
                    query = query.gte("timestamp", since)
                query = query.order("timestamp", desc=True).limit(limit)
                response = query.execute()
                if response.data is not None:
                    return response.data
            except Exception as e:
                logger.warning(f"Supabase security_badge_events query failed, using JSON: {e}")

        # JSON fallback
        state = self._load_state()
        events = state.get("badge_events", [])

        if zone_id:
            events = [e for e in events if e.get("zone_id") == zone_id]
        if since:
            events = [e for e in events if e.get("timestamp", "") >= since]

        # Sort by timestamp descending
        events = sorted(events, key=lambda x: x.get("timestamp", ""), reverse=True)
        return events[:limit]

    def log_badge_event(self, event_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Log a new badge event (dual-write)."""
        if not self._use_json and self.client:
            try:
                response = self.client.table("security_badge_events").insert(event_data).execute()
                if response.data:
                    event_data = response.data[0]
            except Exception as e:
                logger.warning(f"Supabase security_badge_events insert failed: {e}")

        # Always write to JSON as backup
        state = self._load_state()
        state.setdefault("badge_events", []).append(event_data)
        # Keep only last 500 events in JSON
        if len(state["badge_events"]) > 500:
            state["badge_events"] = state["badge_events"][-500:]
        self._save_state(state)
        return event_data

    # --- Alarm zone operations (dynamic) ---

    def get_alarm_zones(self) -> List[Dict[str, Any]]:
        """Get all alarm zones with current status."""
        if not self._use_json and self.client:
            try:
                response = self.client.table("security_alarm_zones").select("*").execute()
                if response.data:
                    return response.data
            except Exception as e:
                logger.warning(f"Supabase security_alarm_zones query failed, using JSON: {e}")

        state = self._load_state()
        alarm_zones = state.get("alarm_zones", [])
        if alarm_zones:
            return alarm_zones
        config = self._load_config()
        return config.get("alarm_zones", [])

    def update_alarm_zone_status(self, zone_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update alarm zone status (dual-write)."""
        if not self._use_json and self.client:
            try:
                self.client.table("security_alarm_zones").update(data).eq("zone_id", zone_id).execute()
            except Exception as e:
                logger.warning(f"Supabase security_alarm_zones update failed: {e}")

        state = self._load_state()
        for zone in state.get("alarm_zones", []):
            if zone.get("zone_id") == zone_id:
                zone.update(data)
                break
        self._save_state(state)
        return data

    # --- Occupancy operations (dynamic) ---

    def get_occupancy(self, zone_id: str = None) -> List[Dict[str, Any]]:
        """Get occupancy data, optionally filtered by zone."""
        if not self._use_json and self.client:
            try:
                query = self.client.table("security_occupancy").select("*")
                if zone_id:
                    query = query.eq("zone_id", zone_id)
                query = query.order("last_updated", desc=True)
                response = query.execute()
                if response.data is not None:
                    return response.data
            except Exception as e:
                logger.warning(f"Supabase security_occupancy query failed, using JSON: {e}")

        state = self._load_state()
        occupancy = state.get("occupancy", [])
        if zone_id:
            occupancy = [o for o in occupancy if o.get("zone_id") == zone_id]
        return occupancy

    def update_occupancy(self, occupancy_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update occupancy for a zone (dual-write)."""
        zone_id = occupancy_data.get("zone_id")

        if not self._use_json and self.client:
            try:
                # Upsert based on zone_id
                self.client.table("security_occupancy").upsert(
                    occupancy_data, on_conflict="zone_id"
                ).execute()
            except Exception as e:
                logger.warning(f"Supabase security_occupancy upsert failed: {e}")

        # Always update JSON
        state = self._load_state()
        occupancy_list = state.setdefault("occupancy", [])
        found = False
        for i, o in enumerate(occupancy_list):
            if o.get("zone_id") == zone_id:
                occupancy_list[i] = occupancy_data
                found = True
                break
        if not found:
            occupancy_list.append(occupancy_data)
        self._save_state(state)
        return occupancy_data


def get_security_repository() -> SecurityRepository:
    """Get or create singleton SecurityRepository."""
    global _instance
    if _instance is None:
        _instance = SecurityRepository()
    return _instance
