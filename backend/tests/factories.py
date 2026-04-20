"""
Test data factories for creating mock objects in tests.
"""

import uuid
from datetime import datetime


class DeviceFactory:
    """Factory for creating test Device instances."""

    @staticmethod
    def create(
        device_id: str | None = None,
        name: str | None = None,
        device_type: str = "hvac",
        protocol: str = "mock",
        **kwargs,
    ) -> dict:
        """Create a test device dictionary."""
        return {
            "id": device_id or f"test-device-{uuid.uuid4().hex[:8]}",
            "name": name or "Test Device",
            "device_type": device_type,
            "protocol": protocol,
            "location": kwargs.get("location", "Test Location"),
            "site_id": kwargs.get("site_id", "test-site-001"),
            "description": kwargs.get("description", "Test device description"),
            "manufacturer": kwargs.get("manufacturer", "Test Manufacturer"),
            "model": kwargs.get("model", "Test Model"),
            "points": kwargs.get(
                "points",
                {
                    "setpoint": {
                        "name": "setpoint",
                        "point_type": "analog_output",
                        "description": "Temperature setpoint",
                        "unit": "°C",
                        "min_value": 16.0,
                        "max_value": 28.0,
                        "default_value": 22.0,
                        "writable": True,
                        "priority": 8,
                    },
                },
            ),
            "metadata": kwargs.get("metadata", {}),
        }

    @staticmethod
    def create_chiller(**kwargs) -> dict:
        """Create a test chiller device."""
        return DeviceFactory.create(
            device_type="hvac",
            name=kwargs.get("name", "Test Chiller"),
            points={
                "setpoint": {
                    "name": "setpoint",
                    "point_type": "analog_output",
                    "description": "Chiller setpoint",
                    "unit": "°C",
                    "min_value": 5.0,
                    "max_value": 15.0,
                    "default_value": 7.0,
                    "writable": True,
                    "priority": 8,
                },
            },
            **kwargs,
        )

    @staticmethod
    def create_ahu(**kwargs) -> dict:
        """Create a test AHU device."""
        return DeviceFactory.create(
            device_type="hvac",
            name=kwargs.get("name", "Test AHU"),
            points={
                "fan_speed": {
                    "name": "fan_speed",
                    "point_type": "analog_output",
                    "description": "Fan speed",
                    "unit": "%",
                    "min_value": 0,
                    "max_value": 100,
                    "default_value": 75,
                    "writable": True,
                    "priority": 8,
                },
            },
            **kwargs,
        )


class SiteFactory:
    """Factory for creating test Site instances."""

    @staticmethod
    def create(site_id: str | None = None, name: str | None = None, **kwargs) -> dict:
        """Create a test site dictionary."""
        return {
            "id": site_id or f"test-site-{uuid.uuid4().hex[:8]}",
            "name": name or "Test Site",
            "location": kwargs.get("location", "Test Location"),
            "region": kwargs.get("region", "Gauteng"),
            "type": kwargs.get("type", "office"),
            "equipment_count": kwargs.get("equipment_count", 10),
            "alert_count": kwargs.get("alert_count", 0),
            "status": kwargs.get("status", "normal"),
        }


class SafetyRuleFactory:
    """Factory for creating test SafetyRule instances."""

    @staticmethod
    def create_temperature_range(
        rule_id: str | None = None,
        device_type: str = "hvac",
        min_temp: float = 16.0,
        max_temp: float = 28.0,
        **kwargs,
    ) -> dict:
        """Create a temperature range safety rule."""
        return {
            "id": rule_id or f"test-rule-{uuid.uuid4().hex[:8]}",
            "name": kwargs.get("name", "Test Temperature Range"),
            "rule_type": "temperature_range",
            "severity": kwargs.get("severity", "block"),
            "description": kwargs.get("description", "Test temperature range rule"),
            "device_type": device_type,
            "device_id": kwargs.get("device_id"),
            "point_name": kwargs.get("point_name"),
            "enabled": kwargs.get("enabled", True),
            "min_temp": min_temp,
            "max_temp": max_temp,
            "unit": "°C",
            "metadata": kwargs.get("metadata", {}),
        }

    @staticmethod
    def create_runtime_limit(
        rule_id: str | None = None, device_type: str = "hvac", min_runtime_minutes: int = 5, **kwargs
    ) -> dict:
        """Create a runtime limit safety rule."""
        return {
            "id": rule_id or f"test-rule-{uuid.uuid4().hex[:8]}",
            "name": kwargs.get("name", "Test Runtime Limit"),
            "rule_type": "runtime_limit",
            "severity": kwargs.get("severity", "block"),
            "description": kwargs.get("description", "Test runtime limit rule"),
            "device_type": device_type,
            "device_id": kwargs.get("device_id"),
            "point_name": kwargs.get("point_name"),
            "enabled": kwargs.get("enabled", True),
            "min_runtime_minutes": min_runtime_minutes,
            "max_starts_per_hour": kwargs.get("max_starts_per_hour", 4),
            "metadata": kwargs.get("metadata", {}),
        }


class AuditLogFactory:
    """Factory for creating test AuditLogEntry instances."""

    @staticmethod
    def create(log_id: str | None = None, action: str = "DEVICE_CONTROL", result: str = "SUCCESS", **kwargs) -> dict:
        """Create a test audit log entry."""
        return {
            "id": log_id or f"test-audit-{uuid.uuid4().hex[:8]}",
            "timestamp": kwargs.get("timestamp", datetime.now().isoformat()),
            "action": action,
            "user": kwargs.get("user", "test-operator"),
            "device_id": kwargs.get("device_id", "test-device-001"),
            "point_name": kwargs.get("point_name", "setpoint"),
            "old_value": kwargs.get("old_value", 21.5),
            "new_value": kwargs.get("new_value", 22.0),
            "result": result,
            "safety_validation": kwargs.get(
                "safety_validation",
                {
                    "rules_checked": ["temperature_range"],
                    "passed_rules": ["temperature_range"] if result == "SUCCESS" else [],
                    "failed_rules": [] if result == "SUCCESS" else ["temperature_range"],
                },
            ),
            "error_message": kwargs.get("error_message"),
            "metadata": kwargs.get("metadata", {}),
        }

    @staticmethod
    def create_blocked(**kwargs) -> dict:
        """Create a blocked audit log entry."""
        return AuditLogFactory.create(
            result="BLOCKED",
            error_message=kwargs.get("error_message", "Safety rule violation"),
            safety_validation={
                "rules_checked": ["temperature_range"],
                "passed_rules": [],
                "failed_rules": ["temperature_range"],
            },
            **kwargs,
        )

    @staticmethod
    def create_success(**kwargs) -> dict:
        """Create a successful audit log entry."""
        return AuditLogFactory.create(result="SUCCESS", **kwargs)
