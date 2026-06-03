"""Repository for safety rules operations."""

import json
import logging
from pathlib import Path
from typing import Any

from app.config.settings import settings

logger = logging.getLogger(__name__)

# Data directory for JSON fallback
DATA_DIR = Path(__file__).parent.parent.parent / "data"


class SafetyRulesRepository:
    """Repository for safety rules database operations."""

    def __init__(self):
        """Initialize the repository."""
        self._client = None
        self._use_json = settings.use_json_storage

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

    def _load_json_rules(self) -> list[dict[str, Any]]:
        """Load rules from JSON file (fallback)."""
        filepath = DATA_DIR / "safety_rules.json"
        if filepath.exists():
            with open(filepath) as f:
                return json.load(f)
        return []

    def _save_json_rules(self, rules: list[dict[str, Any]]) -> None:
        """Save rules to JSON file (fallback)."""
        filepath = DATA_DIR / "safety_rules.json"
        with open(filepath, "w") as f:
            json.dump(rules, f, indent=2)

    def _db_to_rule(self, db_record: dict[str, Any]) -> dict[str, Any]:
        """Convert database record to rule format."""
        params = db_record.get("parameters", {})
        if isinstance(params, str):
            params = json.loads(params)

        rule = {
            "id": db_record.get("code", db_record.get("id")),
            "name": db_record.get("name"),
            "rule_type": db_record.get("rule_type"),
            "severity": db_record.get("severity"),
            "description": db_record.get("description", ""),
            "device_type": db_record.get("device_type"),
            "device_id": db_record.get("device_id"),
            "point_name": db_record.get("point_name"),
            "enabled": db_record.get("enabled", True),
            "site_id": db_record.get("site_id"),
            "metadata": {},
            "created_at": db_record.get("created_at", ""),
            "updated_at": db_record.get("updated_at", ""),
        }

        # Merge parameters into the rule based on rule_type
        rule.update(params)

        return rule

    def _rule_to_db(self, rule: dict[str, Any]) -> dict[str, Any]:
        """Convert rule format to database record."""
        # Extract parameters based on rule_type
        params = {}
        rule_type = rule.get("rule_type", "")

        if rule_type == "temperature_range":
            params = {
                "min_temp": rule.get("min_temp", 16.0),
                "max_temp": rule.get("max_temp", 28.0),
                "unit": rule.get("unit", "°C"),
            }
        elif rule_type == "pressure_limit":
            params = {
                "min_pressure": rule.get("min_pressure", 0.0),
                "max_pressure": rule.get("max_pressure", 100.0),
                "unit": rule.get("unit", "kPa"),
            }
        elif rule_type == "runtime_limit":
            params = {
                "min_runtime_minutes": rule.get("min_runtime_minutes", 5),
                "max_starts_per_hour": rule.get("max_starts_per_hour", 4),
            }
        elif rule_type == "brightness_limit":
            params = {
                "min_brightness": rule.get("min_brightness", 0),
                "max_brightness": rule.get("max_brightness", 100),
            }
        elif rule_type == "interlock":
            params = {
                "trigger_device_id": rule.get("trigger_device_id"),
                "trigger_device_type": rule.get("trigger_device_type"),
                "trigger_point": rule.get("trigger_point"),
                "trigger_value": rule.get("trigger_value"),
                "action": rule.get("action"),
                "action_value": rule.get("action_value"),
            }
        elif rule_type == "custom":
            params = {
                "validation_logic": rule.get("validation_logic", ""),
                "min_value": rule.get("min_value"),
                "max_value": rule.get("max_value"),
                "unit": rule.get("unit", ""),
            }

        return {
            "code": rule.get("id"),
            "name": rule.get("name"),
            "rule_type": rule_type,
            "severity": rule.get("severity", "warning"),
            "description": rule.get("description", ""),
            "device_type": rule.get("device_type"),
            "device_id": rule.get("device_id"),
            "point_name": rule.get("point_name"),
            "enabled": rule.get("enabled", True),
            "parameters": params,
        }

    def get_all(self, enabled_only: bool = False) -> list[dict[str, Any]]:
        """Get all safety rules."""
        if self._use_json or not self.client:
            rules = self._load_json_rules()
            if enabled_only:
                rules = [r for r in rules if r.get("enabled", True)]
            return rules

        try:
            query = self.client.table("safety_rules").select("*")
            if enabled_only:
                query = query.eq("enabled", True)

            response = query.execute()
            return [self._db_to_rule(r) for r in response.data]
        except Exception as e:
            logger.error(f"Failed to get safety rules from Supabase: {e}")
            return self._load_json_rules()

    def get_by_id(self, rule_id: str) -> dict[str, Any] | None:
        """Get a rule by ID."""
        if self._use_json or not self.client:
            rules = self._load_json_rules()
            return next((r for r in rules if r.get("id") == rule_id), None)

        try:
            response = self.client.table("safety_rules").select("*").eq("code", rule_id).execute()
            if response.data:
                return self._db_to_rule(response.data[0])
            return None
        except Exception as e:
            logger.error(f"Failed to get safety rule {rule_id}: {e}")
            return None

    def get_for_device(
        self,
        device_type: str,
        device_id: str | None = None,
        point_name: str | None = None,
        site_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get rules applicable to a device.

        Args:
            device_type: Type of device (e.g., 'hvac', 'lighting')
            device_id: Specific device ID to match (optional)
            point_name: Specific point name to match (optional)
            site_id: Site ID to filter rules (optional). Rules with matching
                site_id OR null site_id (global fallback) are returned.
        """
        all_rules = self.get_all(enabled_only=True)

        applicable = []
        for rule in all_rules:
            # Check device type match
            if rule.get("device_type") and rule["device_type"] != device_type:
                continue

            # Check site_id match — include rules scoped to this site OR global (null) rules
            rule_site = rule.get("site_id")
            if site_id is not None and rule_site is not None and rule_site != site_id:
                continue

            # Check device ID match (if rule specifies one)
            if rule.get("device_id") and rule["device_id"] != device_id:
                continue

            # Check point name match (if both specified)
            if point_name and rule.get("point_name") and rule["point_name"] != point_name:
                continue

            applicable.append(rule)

        return applicable

    def create(self, rule_data: dict[str, Any]) -> dict[str, Any] | None:
        """Create a new safety rule."""
        if self._use_json or not self.client:
            rules = self._load_json_rules()
            rules.append(rule_data)
            self._save_json_rules(rules)
            return rule_data

        try:
            db_record = self._rule_to_db(rule_data)
            response = self.client.table("safety_rules").insert(db_record).execute()
            if response.data:
                return self._db_to_rule(response.data[0])
            return None
        except Exception as e:
            logger.error(f"Failed to create safety rule: {e}")
            return None

    def update(self, rule_id: str, rule_data: dict[str, Any]) -> dict[str, Any] | None:
        """Update an existing safety rule."""
        if self._use_json or not self.client:
            rules = self._load_json_rules()
            for i, rule in enumerate(rules):
                if rule.get("id") == rule_id:
                    rules[i] = {**rule, **rule_data}
                    self._save_json_rules(rules)
                    return rules[i]
            return None

        try:
            db_record = self._rule_to_db(rule_data)
            # Remove code from update to avoid changing the ID
            if "code" in db_record:
                del db_record["code"]

            response = self.client.table("safety_rules").update(db_record).eq("code", rule_id).execute()
            if response.data:
                return self._db_to_rule(response.data[0])
            return None
        except Exception as e:
            logger.error(f"Failed to update safety rule {rule_id}: {e}")
            return None

    def delete(self, rule_id: str) -> bool:
        """Delete a safety rule."""
        if self._use_json or not self.client:
            rules = self._load_json_rules()
            original_len = len(rules)
            rules = [r for r in rules if r.get("id") != rule_id]
            if len(rules) < original_len:
                self._save_json_rules(rules)
                return True
            return False

        try:
            response = self.client.table("safety_rules").delete().eq("code", rule_id).execute()
            return len(response.data) > 0
        except Exception as e:
            logger.error(f"Failed to delete safety rule {rule_id}: {e}")
            return False

    def toggle_enabled(self, rule_id: str, enabled: bool) -> dict[str, Any] | None:
        """Toggle a rule's enabled status."""
        return self.update(rule_id, {"enabled": enabled})
