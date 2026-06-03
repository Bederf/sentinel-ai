"""Safety Interlock Service for building control safety validation.

This service provides safety rule evaluation and validation for device control
operations to prevent unsafe operations (e.g., overheating, pressure extremes).
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from app.models.device import Device
from app.models.safety_rules import RuleSeverity, SafetyRule, TemperatureRangeRule

logger = logging.getLogger(__name__)

# Data directory for safety rules
DATA_DIR = Path(__file__).parent.parent / "data"
SAFETY_RULES_FILE = DATA_DIR / "safety_rules.json"


class SafetyEngine:
    """Engine for evaluating safety rules."""

    def __init__(self):
        self.rules: dict[str, SafetyRule] = {}
        self._initialized = False
        self._repository = None

    @property
    def repository(self):
        """Lazy load SafetyRulesRepository."""
        if self._repository is None:
            from app.database.repositories.safety_rules_repository import SafetyRulesRepository

            self._repository = SafetyRulesRepository()
        return self._repository

    async def initialize(self, rules_data: list[dict[str, Any]] | None = None) -> None:
        """Initialize safety engine with rules."""
        if self._initialized and self.rules:
            return

        logger.info("Initializing SafetyEngine")

        if rules_data:
            # Load from provided data
            for rule_data in rules_data:
                await self.add_rule(rule_data)
        else:
            # Try to load from repository (Supabase or JSON fallback)
            await self.load_rules_from_repository()

        self._initialized = True
        logger.info(f"SafetyEngine initialized with {len(self.rules)} rules")

    async def load_rules_from_repository(self) -> None:
        """Load safety rules from repository (Supabase or JSON fallback)."""
        try:
            rules_data = self.repository.get_all()

            if not rules_data:
                logger.info("No rules found in repository, creating seeded rules")
                await self.create_seed_rules()
                return

            for rule_data in rules_data:
                await self.add_rule(rule_data)

            logger.info(f"Loaded {len(rules_data)} safety rules from repository")
        except Exception as e:
            logger.error(f"Failed to load safety rules from repository: {e}")
            # Try JSON file as fallback
            await self.load_rules_from_file()

    async def load_rules_from_file(self) -> None:
        """Load safety rules from JSON file (fallback)."""
        try:
            if not SAFETY_RULES_FILE.exists():
                logger.info("No safety rules file found, creating seeded rules")
                await self.create_seed_rules()
                return

            with open(SAFETY_RULES_FILE) as f:
                rules_data = json.load(f)

            for rule_data in rules_data:
                await self.add_rule(rule_data)

            logger.info(f"Loaded {len(rules_data)} safety rules from {SAFETY_RULES_FILE}")
        except Exception as e:
            logger.error(f"Failed to load safety rules from file: {e}")
            # Create seeded rules as fallback
            await self.create_seed_rules()

    async def save_rules_to_file(self) -> bool:
        """Save safety rules to storage (repository and JSON file)."""
        try:
            rules_data = [rule.to_dict() for rule in self.rules.values()]

            # Save to JSON file as backup
            with open(SAFETY_RULES_FILE, "w") as f:
                json.dump(rules_data, f, indent=2)

            logger.info(f"Saved {len(rules_data)} safety rules to {SAFETY_RULES_FILE}")
            return True
        except Exception as e:
            logger.error(f"Failed to save safety rules: {e}")
            return False

    async def create_seed_rules(self) -> None:
        """Create seeded safety rules for local validation."""
        seed_rules = [
            # HVAC temperature rules
            {
                "id": "temp_hvac_safe_range",
                "name": "HVAC Temperature Safe Range",
                "rule_type": "temperature_range",
                "severity": "block",
                "description": "HVAC temperature must be within 16-28°C for occupant comfort and equipment safety",
                "device_type": "hvac",
                "min_temp": 16.0,
                "max_temp": 28.0,
                "unit": "°C",
            },
            {
                "id": "temp_chiller_min",
                "name": "Chiller Minimum Temperature",
                "rule_type": "temperature_range",
                "severity": "block",
                "description": "Chiller supply temperature must be above 5°C to prevent freeze damage",
                "device_type": "hvac",
                "point_name": "supply_temp",
                "min_temp": 5.0,
                "max_temp": 15.0,
                "unit": "°C",
            },
            # Chiller runtime protection
            {
                "id": "chiller_runtime_limit",
                "name": "Chiller Minimum Runtime",
                "rule_type": "runtime_limit",
                "severity": "block",
                "description": "Chiller must run for at least 5 minutes before restart to protect compressor",
                "device_type": "hvac",
                "min_runtime_minutes": 5,
                "max_starts_per_hour": 4,
            },
            # Pressure safety rules
            {
                "id": "chiller_pressure_max",
                "name": "Chiller Maximum Pressure",
                "rule_type": "pressure_limit",
                "severity": "block",
                "description": "Chiller pressure must not exceed 1200 kPa for safety",
                "device_type": "hvac",
                "point_name": "discharge_pressure",
                "max_pressure": 1200.0,
                "unit": "kPa",
            },
            # Lighting brightness limits
            {
                "id": "lighting_brightness_max",
                "name": "Maximum Brightness Limit",
                "rule_type": "brightness_limit",
                "severity": "warning",
                "description": "Lighting brightness should not exceed 90% to save energy",
                "device_type": "lighting",
                "point_name": "brightness",
                "max_brightness": 90,
            },
            # Fire safety interlock
            {
                "id": "fire_alarm_hvac_interlock",
                "name": "Fire Alarm HVAC Interlock",
                "rule_type": "interlock",
                "severity": "block",
                "description": "When fire alarm is active, disable HVAC to prevent smoke spread",
                "device_type": "hvac",
                "trigger_device_id": "fire_pump_controller_001",
                "trigger_point": "fire_alarm_status",
                "trigger_value": True,
                "action": "disable",
            },
            # Emergency lighting interlock
            {
                "id": "power_failure_lighting",
                "name": "Power Failure Emergency Lighting",
                "rule_type": "interlock",
                "severity": "block",
                "description": "When power failure detected, enable emergency lighting circuits",
                "device_type": "lighting",
                "trigger_device_id": "main_panel_001",
                "trigger_point": "power_status",
                "trigger_value": False,
                "action": "enable",
                "action_value": 100,  # Full brightness for emergency
            },
            # VAV minimum airflow
            {
                "id": "vav_minimum_airflow",
                "name": "VAV Minimum Airflow",
                "rule_type": "custom",
                "severity": "warning",
                "description": "VAV boxes must maintain minimum airflow for ventilation",
                "device_type": "hvac",
                "point_name": "airflow_setpoint",
                "validation_logic": "value >= 20.0",  # 20% minimum
            },
        ]

        for rule_data in seed_rules:
            await self.add_rule(rule_data)

        # Save seeded rules to file
        await self.save_rules_to_file()
        logger.info(f"Created {len(seed_rules)} seeded safety rules")

    async def add_rule(self, rule_data: dict[str, Any]) -> SafetyRule:
        """Add a safety rule."""
        rule = SafetyRule.from_dict(rule_data)
        self.rules[rule.id] = rule
        logger.info(f"Added safety rule: {rule.name} ({rule.id})")
        return rule

    async def remove_rule(self, rule_id: str) -> bool:
        """Remove a safety rule."""
        if rule_id in self.rules:
            del self.rules[rule_id]
            logger.info(f"Removed safety rule: {rule_id}")
            return True
        return False

    async def get_rule(self, rule_id: str) -> SafetyRule | None:
        """Get a safety rule by ID."""
        return self.rules.get(rule_id)

    async def list_rules(self, filter_dict: dict[str, Any] | None = None) -> list[SafetyRule]:
        """List safety rules with optional filtering."""
        rules = list(self.rules.values())

        if filter_dict:
            filtered_rules = []
            for rule in rules:
                match = True
                for key, value in filter_dict.items():
                    rule_value = getattr(rule, key, None)
                    if rule_value != value:
                        match = False
                        break
                if match:
                    filtered_rules.append(rule)
            return filtered_rules

        return rules

    async def get_rules_for_device(
        self,
        device: Device,
        point_name: str | None = None,
        site_id: str | None = None,
    ) -> list[SafetyRule]:
        """Get safety rules applicable to a specific device (and optionally point).

        Site scoping: rules are filtered by the device's site_id. Rules with no
        site_id (global fallback rules) apply to all sites. This prevents a rule
        from one site bleeding into another.

        When a specific rule exists for a point (rule.point_name matches point_name),
        generic rules of the same type (rule.point_name is None) are excluded to
        prevent conflicts (e.g., chiller chw_setpoint 5-12°C vs generic HVAC 16-28°C).
        """
        # Use device.site_id as default if not provided
        if site_id is None:
            site_id = getattr(device, "site_id", None)

        applicable_rules = []
        specific_rule_types = set()  # Track rule types that have specific point rules

        logger.debug(
            f"get_rules_for_device called: device={device.id}, device_type={device.device_type}, "
            f"point={point_name}, site_id={site_id}"
        )
        logger.debug(f"Total rules in engine: {len(self.rules)}")

        # First pass: collect all matching rules and identify specific rules
        for rule in self.rules.values():
            logger.debug(
                f"Checking rule {rule.id}: enabled={rule.enabled}, "
                f"rule_device_type={rule.device_type}, rule_point={rule.point_name}, rule_site={getattr(rule, 'site_id', None)}"
            )

            if not rule.enabled:
                logger.debug("  -> Skipped: rule disabled")
                continue

            # Check device type match
            if rule.device_type and rule.device_type != device.device_type.value:
                logger.debug(f"  -> Skipped: device_type mismatch ({rule.device_type} != {device.device_type.value})")
                continue

            # Check site_id match — include rules scoped to this site OR global (null-site) fallbacks
            rule_site = getattr(rule, "site_id", None)
            if site_id is not None and rule_site is not None and rule_site != site_id:
                logger.debug(f"  -> Skipped: site_id mismatch ({rule_site} != {site_id})")
                continue

            # Check device ID match (if specified)
            if rule.device_id and rule.device_id != device.id:
                logger.debug(f"  -> Skipped: device_id mismatch ({rule.device_id} != {device.id})")
                continue

            # Check point name match (if specified)
            if point_name and rule.point_name and rule.point_name != point_name:
                logger.debug(f"  -> Skipped: point_name mismatch ({rule.point_name} != {point_name})")
                continue

            # Track if this is a specific rule for the requested point
            if point_name and rule.point_name == point_name:
                specific_rule_types.add(rule.rule_type)
                logger.debug(f"  -> SPECIFIC rule for point {point_name}")

            applicable_rules.append(rule)
            logger.debug("  -> MATCHED: added to applicable_rules")

        logger.debug(f"First pass: {len(applicable_rules)} applicable rules, specific_rule_types={specific_rule_types}")

        # Second pass: filter out generic rules when specific rules exist for same type
        if specific_rule_types:
            filtered_rules = []
            for rule in applicable_rules:
                # Keep the rule if:
                # 1. It has a specific point_name (not generic), OR
                # 2. Its rule_type doesn't have a specific rule that would conflict
                if rule.point_name is not None or rule.rule_type not in specific_rule_types:
                    filtered_rules.append(rule)
                    logger.debug(f"  -> Keeping rule {rule.id} (point_name={rule.point_name})")
                else:
                    logger.debug(f"  -> Filtering out generic rule {rule.id}")
            logger.debug(f"Second pass: {len(filtered_rules)} rules after filtering generics")
            return filtered_rules

        return applicable_rules

    async def validate_control(self, device: Device, point_name: str, value: Any) -> dict[str, Any]:
        """
        Validate a control action against safety rules.

        Args:
            device: Device being controlled
            point_name: Point name being written to
            value: Value being written

        Returns:
            Dict with validation results:
                - allowed: bool (True if operation allowed)
                - reasons: List of rule violation messages
                - warnings: List of warning messages
                - rule_results: Detailed results from each rule check
        """
        # Get applicable rules (site-scoped via device.site_id)
        applicable_rules = await self.get_rules_for_device(device, point_name)

        if not applicable_rules:
            # No rules for this device/point/scope — allow by default.
            # Safety thresholds are fully defined in Supabase via safety_rules table.
            return {
                "allowed": True,
                "reasons": [],
                "warnings": [],
                "alarms": [],
                "rule_results": [],
                "message": "No safety rules apply to this device/point — allow by default",
            }

        # Evaluate each rule
        rule_results = []
        block_violations = []
        warning_violations = []
        alarm_violations = []

        for rule in applicable_rules:
            result = rule.check(device, value)
            rule_results.append(result)

            if not result.get("allowed", True):
                if rule.severity == RuleSeverity.BLOCK:
                    block_violations.append(result.get("message", "Blocked by safety rule"))
                elif rule.severity == RuleSeverity.WARNING:
                    warning_violations.append(result.get("message", "Warning from safety rule"))
                elif rule.severity == RuleSeverity.ALARM:
                    alarm_violations.append(result.get("message", "Alarm from safety rule"))

        # Determine overall result
        allowed = len(block_violations) == 0

        # Prometheus metrics instrumentation (best-effort)
        try:
            from app.api.metrics import sentinel_safety_violations_total

            # Extract site_id from device context; fall back to "unknown"
            site_id = getattr(device, "site_id", None) or getattr(device, "site_id", None) or "unknown"
            if block_violations:
                sentinel_safety_violations_total.labels(site_id=site_id, severity="block").inc(len(block_violations))
            if warning_violations:
                sentinel_safety_violations_total.labels(site_id=site_id, severity="warning").inc(
                    len(warning_violations)
                )
            if alarm_violations:
                sentinel_safety_violations_total.labels(site_id=site_id, severity="alarm").inc(len(alarm_violations))
        except Exception:
            pass  # Metrics are best-effort, never block business logic

        return {
            "allowed": allowed,
            "reasons": block_violations,
            "warnings": warning_violations,
            "alarms": alarm_violations,
            "rule_results": rule_results,
            "message": "Safety validation complete",
            "device_id": device.id,
            "point_name": point_name,
            "value": value,
            "timestamp": datetime.now().isoformat(),
        }

    async def get_device_safety_status(self, device: Device) -> dict[str, Any]:
        """
        Get current safety status for a device.

        Args:
            device: Device to check

        Returns:
            Dict with safety status:
                - overall_status: "safe", "warning", "blocked"
                - active_rules: List of active rule IDs
                - last_check: Timestamp
                - details: Detailed status per point
        """
        # In local mode, check all points on the device
        point_statuses = {}

        for point_name, point in device.points.items():
            # Get current value (would read from device in real implementation)
            # In local mode, use default value or random value
            current_value = point.default_value or 0

            # Validate current value
            validation = await self.validate_control(device, point_name, current_value)

            # Get applicable rules to extract min/max from TemperatureRangeRule
            applicable_rules = await self.get_rules_for_device(device, point_name)
            min_value = None
            max_value = None
            logger.debug(f"Checking {len(applicable_rules)} rules for point {point_name}")
            for rule in applicable_rules:
                logger.debug(f"Rule {rule.id}: type={type(rule).__name__}, point_name={rule.point_name}")
                if isinstance(rule, TemperatureRangeRule) and rule.point_name == point_name:
                    min_value = rule.min_temp
                    max_value = rule.max_temp
                    logger.debug(f"Found TemperatureRangeRule for {point_name}: min={min_value}, max={max_value}")
                    # Take the first matching rule (most specific)
                    break

            point_status = {
                "value": current_value,
                "allowed": validation["allowed"],
                "warnings": validation["warnings"],
                "alarms": validation["alarms"],
            }

            # Add min/max if available
            if min_value is not None:
                point_status["min_value"] = min_value
            if max_value is not None:
                point_status["max_value"] = max_value

            point_statuses[point_name] = point_status

        # Determine overall status
        has_blocked = any(not status["allowed"] for status in point_statuses.values())
        has_warnings = any(len(status["warnings"]) > 0 for status in point_statuses.values())
        has_alarms = any(len(status["alarms"]) > 0 for status in point_statuses.values())

        if has_blocked:
            overall_status = "blocked"
        elif has_alarms:
            overall_status = "alarm"
        elif has_warnings:
            overall_status = "warning"
        else:
            overall_status = "safe"

        return {
            "device_id": device.id,
            "device_name": device.name,
            "overall_status": overall_status,
            "point_statuses": point_statuses,
            "active_rule_count": len(await self.get_rules_for_device(device)),
            "last_check": datetime.now().isoformat(),
        }


# Global instance for easy access
safety_engine = SafetyEngine()
