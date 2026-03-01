"""Repository for fire & life safety data operations.

Follows dual-write pattern: Supabase (primary) + JSON (fallback/offline).
Static configuration (zones, cause-effect) loaded from fire_system_config.json.
Dynamic state (alarms, dampers, pressurization) persisted to both stores.
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from pathlib import Path

from app.config.settings import settings

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent.parent / "data"
CONFIG_FILE = DATA_DIR / "fire_system_config.json"
STATE_FILE = DATA_DIR / "fire_system_state.json"

# Singleton instance
_instance: Optional["FireSafetyRepository"] = None


class FireSafetyRepository:
    """Repository for fire safety data with Supabase + JSON dual-write."""

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
        """Load static fire system configuration from JSON."""
        if self._config_cache is not None:
            return self._config_cache
        if CONFIG_FILE.exists():
            with open(CONFIG_FILE) as f:
                self._config_cache = json.load(f)
                return self._config_cache
        return {}

    def _load_state(self) -> Dict[str, Any]:
        """Load dynamic fire system state from JSON."""
        if STATE_FILE.exists():
            with open(STATE_FILE) as f:
                return json.load(f)
        # Initialize from config demo_state
        config = self._load_config()
        demo = config.get("demo_state", {})
        return {
            "alarms": demo.get("active_alarms", []),
            "dampers": config.get("dampers", []),
            "pressurization": config.get("pressurization", []),
            "action_log": [],
        }

    def _save_state(self, state: Dict[str, Any]) -> None:
        """Save dynamic fire system state to JSON."""
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=2, default=str)

    # --- Zone operations (static config) ---

    def get_zones(self, building_id: str | None = None) -> List[Dict[str, Any]]:
        """Get all fire zones for a building."""
        if not self._use_json and self.client:
            try:
                response = self.client.table("fire_zones").select("*").execute()
                if response.data:
                    return response.data
            except Exception as e:
                logger.warning(f"Supabase fire_zones query failed, using JSON: {e}")

        # JSON fallback
        config = self._load_config()
        return config.get("zones", [])

    def get_zone(self, zone_id: str) -> Optional[Dict[str, Any]]:
        """Get a single fire zone by ID."""
        zones = self.get_zones()
        return next((z for z in zones if z.get("zone_id") == zone_id), None)

    # --- Alarm operations (dynamic) ---

    def get_active_alarms(self, building_id: str | None = None) -> List[Dict[str, Any]]:
        """Get active (uncleared) fire alarms."""
        if not self._use_json and self.client:
            try:
                response = self.client.table("fire_alarms").select("*").eq("cleared", False).execute()
                if response.data is not None:
                    return response.data
            except Exception as e:
                logger.warning(f"Supabase fire_alarms query failed, using JSON: {e}")

        # JSON fallback
        state = self._load_state()
        return [a for a in state.get("alarms", []) if not a.get("cleared", False)]

    def get_all_alarms(self, building_id: str | None = None) -> List[Dict[str, Any]]:
        """Get all fire alarms (including cleared)."""
        if not self._use_json and self.client:
            try:
                response = self.client.table("fire_alarms").select("*").execute()
                if response.data is not None:
                    return response.data
            except Exception as e:
                logger.warning(f"Supabase fire_alarms query failed, using JSON: {e}")

        state = self._load_state()
        return state.get("alarms", [])

    def create_alarm(self, alarm_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Create a new fire alarm (dual-write)."""
        # Try Supabase first
        if not self._use_json and self.client:
            try:
                response = self.client.table("fire_alarms").insert(alarm_data).execute()
                if response.data:
                    alarm_data = response.data[0]
            except Exception as e:
                logger.warning(f"Supabase fire_alarms insert failed: {e}")

        # Always write to JSON as backup
        state = self._load_state()
        state.setdefault("alarms", []).append(alarm_data)
        self._save_state(state)
        return alarm_data

    def update_alarm(self, alarm_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update a fire alarm (dual-write)."""
        if not self._use_json and self.client:
            try:
                response = self.client.table("fire_alarms").update(data).eq("alarm_id", alarm_id).execute()
                if response.data:
                    pass  # Success in Supabase
            except Exception as e:
                logger.warning(f"Supabase fire_alarms update failed: {e}")

        # Always update JSON backup
        state = self._load_state()
        for alarm in state.get("alarms", []):
            if alarm.get("alarm_id") == alarm_id:
                alarm.update(data)
                break
        self._save_state(state)
        return data

    # --- Damper operations (dynamic) ---

    def get_dampers(self, building_id: str | None = None) -> List[Dict[str, Any]]:
        """Get all smoke damper positions and status."""
        if not self._use_json and self.client:
            try:
                response = self.client.table("fire_dampers").select("*").execute()
                if response.data:
                    return response.data
            except Exception as e:
                logger.warning(f"Supabase fire_dampers query failed, using JSON: {e}")

        # JSON fallback: from state if exists, else config
        state = self._load_state()
        dampers = state.get("dampers", [])
        if dampers:
            return dampers
        config = self._load_config()
        return config.get("dampers", [])

    def update_damper(self, damper_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update a smoke damper (dual-write)."""
        if not self._use_json and self.client:
            try:
                self.client.table("fire_dampers").update(data).eq("damper_id", damper_id).execute()
            except Exception as e:
                logger.warning(f"Supabase fire_dampers update failed: {e}")

        # Always update JSON backup
        state = self._load_state()
        for damper in state.get("dampers", []):
            if damper.get("damper_id") == damper_id:
                damper.update(data)
                break
        self._save_state(state)
        return data

    # --- Pressurization operations (dynamic) ---

    def get_pressurization(self, building_id: str | None = None) -> List[Dict[str, Any]]:
        """Get stairwell pressurization readings."""
        if not self._use_json and self.client:
            try:
                response = self.client.table("fire_pressurization").select("*").execute()
                if response.data:
                    return response.data
            except Exception as e:
                logger.warning(f"Supabase fire_pressurization query failed, using JSON: {e}")

        # JSON fallback
        state = self._load_state()
        press = state.get("pressurization", [])
        if press:
            return press
        config = self._load_config()
        return config.get("pressurization", [])

    def update_pressurization(self, stairwell_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update stairwell pressurization (dual-write)."""
        if not self._use_json and self.client:
            try:
                (self.client.table("fire_pressurization").update(data).eq("stairwell_id", stairwell_id).execute())
            except Exception as e:
                logger.warning(f"Supabase fire_pressurization update failed: {e}")

        state = self._load_state()
        for p in state.get("pressurization", []):
            if p.get("stairwell_id") == stairwell_id:
                p.update(data)
                break
        self._save_state(state)
        return data

    # --- Cause-effect matrix (static config) ---

    def get_cause_effect_matrix(self, building_id: str | None = None) -> List[Dict[str, Any]]:
        """Get the cause-effect matrix for fire coordination."""
        if not self._use_json and self.client:
            try:
                response = self.client.table("fire_cause_effect").select("*").execute()
                if response.data:
                    return response.data
            except Exception as e:
                logger.warning(f"Supabase fire_cause_effect query failed, using JSON: {e}")

        # JSON fallback
        config = self._load_config()
        return config.get("cause_effect_matrix", [])

    # --- Action log (audit trail, dual-write) ---

    def log_action(self, action_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Log a fire coordination action (dual-write)."""
        action_data.setdefault("created_at", datetime.utcnow().isoformat())

        if not self._use_json and self.client:
            try:
                response = self.client.table("fire_action_log").insert(action_data).execute()
                if response.data:
                    action_data = response.data[0]
            except Exception as e:
                logger.warning(f"Supabase fire_action_log insert failed: {e}")

        # Always write to JSON backup
        state = self._load_state()
        state.setdefault("action_log", []).append(action_data)
        # Keep only last 100 actions in JSON
        if len(state["action_log"]) > 100:
            state["action_log"] = state["action_log"][-100:]
        self._save_state(state)
        return action_data

    def get_action_log(self, building_id: str | None = None, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent fire action log entries."""
        if not self._use_json and self.client:
            try:
                response = (
                    self.client.table("fire_action_log")
                    .select("*")
                    .order("created_at", desc=True)
                    .limit(limit)
                    .execute()
                )
                if response.data is not None:
                    return response.data
            except Exception as e:
                logger.warning(f"Supabase fire_action_log query failed, using JSON: {e}")

        state = self._load_state()
        log = state.get("action_log", [])
        return sorted(log, key=lambda x: x.get("created_at", ""), reverse=True)[:limit]

    # --- Panel info (from config) ---

    def get_panel_info(self) -> Dict[str, Any]:
        """Get fire alarm panel information."""
        config = self._load_config()
        return config.get("panel", {})

    def get_demo_state(self) -> Dict[str, Any]:
        """Get pre-configured demo state."""
        config = self._load_config()
        return config.get("demo_state", {})


def get_fire_safety_repository() -> FireSafetyRepository:
    """Get or create singleton FireSafetyRepository."""
    global _instance
    if _instance is None:
        _instance = FireSafetyRepository()
    return _instance
