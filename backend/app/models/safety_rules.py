"""Safety rule models for building control safety interlocks.

This module defines safety rules that can prevent unsafe operations
(e.g., overheating, pressure extremes, dangerous interlock conditions).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any, Optional
from datetime import datetime


class RuleSeverity(Enum):
    """Severity levels for safety rules."""

    WARNING = "warning"  # Allow operation but show warning
    BLOCK = "block"  # Prevent operation entirely
    ALARM = "alarm"  # Trigger alarm, may allow with override


class RuleType(Enum):
    """Types of safety rules."""

    TEMPERATURE_RANGE = "temperature_range"
    PRESSURE_LIMIT = "pressure_limit"
    INTERLOCK = "interlock"
    RUNTIME_LIMIT = "runtime_limit"
    BRIGHTNESS_LIMIT = "brightness_limit"
    CUSTOM = "custom"


@dataclass
class SafetyRule(ABC):
    """Base class for safety rules."""

    id: str
    name: str
    rule_type: RuleType
    severity: RuleSeverity
    description: str = ""
    device_type: Optional[str] = None  # Optional: specific device type
    device_id: Optional[str] = None  # Optional: specific device ID
    point_name: Optional[str] = None  # Optional: specific point name
    enabled: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
        if not self.updated_at:
            self.updated_at = datetime.now().isoformat()

    @abstractmethod
    def check(self, device: Any, value: Any) -> Dict[str, Any]:
        """
        Check if the rule is violated.

        Args:
            device: Device object or device data
            value: Value being checked (for write operations) or current value

        Returns:
            Dict with keys:
                - allowed: bool (True if operation allowed)
                - severity: RuleSeverity
                - message: str (human-readable explanation)
                - rule_id: str
                - rule_name: str
        """
        pass

    def to_dict(self) -> Dict[str, Any]:
        """Convert rule to dictionary for serialization."""
        return {
            "id": self.id,
            "name": self.name,
            "rule_type": self.rule_type.value,
            "severity": self.severity.value,
            "description": self.description,
            "device_type": self.device_type,
            "device_id": self.device_id,
            "point_name": self.point_name,
            "enabled": self.enabled,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SafetyRule":
        """Create rule instance from dictionary."""
        rule_type = RuleType(data["rule_type"])
        _severity = RuleSeverity(data["severity"])

        # Create appropriate rule subclass
        if rule_type == RuleType.TEMPERATURE_RANGE:
            return TemperatureRangeRule.from_dict(data)
        elif rule_type == RuleType.PRESSURE_LIMIT:
            return PressureLimitRule.from_dict(data)
        elif rule_type == RuleType.INTERLOCK:
            return InterlockRule.from_dict(data)
        elif rule_type == RuleType.RUNTIME_LIMIT:
            return RuntimeLimitRule.from_dict(data)
        elif rule_type == RuleType.BRIGHTNESS_LIMIT:
            return BrightnessLimitRule.from_dict(data)
        else:
            return CustomRule.from_dict(data)


@dataclass
class TemperatureRangeRule(SafetyRule):
    """Rule for temperature range validation."""

    min_temp: float = 16.0  # Default from Phase 2 decision
    max_temp: float = 28.0  # Default from Phase 2 decision
    unit: str = "°C"

    def check(self, device: Any, value: Any) -> Dict[str, Any]:
        """Check if temperature is within safe range."""
        try:
            temp = float(value)
            if temp < self.min_temp or temp > self.max_temp:
                return {
                    "allowed": self.severity != RuleSeverity.BLOCK,
                    "severity": self.severity.value,
                    "message": (
                        f"Temperature {temp}{self.unit} is outside safe range "
                        f"({self.min_temp}-{self.max_temp}{self.unit})"
                    ),
                    "rule_id": self.id,
                    "rule_name": self.name,
                    "actual_value": temp,
                    "min_allowed": self.min_temp,
                    "max_allowed": self.max_temp,
                }
            return {
                "allowed": True,
                "severity": self.severity.value,
                "message": f"Temperature {temp}{self.unit} is within safe range",
                "rule_id": self.id,
                "rule_name": self.name,
            }
        except (ValueError, TypeError):
            return {
                "allowed": False,
                "severity": RuleSeverity.BLOCK.value,
                "message": f"Invalid temperature value: {value}",
                "rule_id": self.id,
                "rule_name": self.name,
            }

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary with temperature-specific fields."""
        base_dict = super().to_dict()
        base_dict.update(
            {
                "min_temp": self.min_temp,
                "max_temp": self.max_temp,
                "unit": self.unit,
            }
        )
        return base_dict

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TemperatureRangeRule":
        """Create from dictionary."""
        return cls(
            id=data["id"],
            name=data["name"],
            rule_type=RuleType.TEMPERATURE_RANGE,
            severity=RuleSeverity(data["severity"]),
            description=data.get("description", ""),
            device_type=data.get("device_type"),
            device_id=data.get("device_id"),
            point_name=data.get("point_name"),
            enabled=data.get("enabled", True),
            metadata=data.get("metadata", {}),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            min_temp=data.get("min_temp", 16.0),
            max_temp=data.get("max_temp", 28.0),
            unit=data.get("unit", "°C"),
        )


@dataclass
class PressureLimitRule(SafetyRule):
    """Rule for pressure limit validation."""

    max_pressure: float = 100.0  # kPa
    min_pressure: float = 0.0  # kPa
    unit: str = "kPa"

    def check(self, device: Any, value: Any) -> Dict[str, Any]:
        """Check if pressure is within safe limits."""
        try:
            pressure = float(value)
            if pressure < self.min_pressure:
                return {
                    "allowed": False,
                    "severity": RuleSeverity.BLOCK.value,
                    "message": f"Pressure {pressure}{self.unit} is below minimum ({self.min_pressure}{self.unit})",
                    "rule_id": self.id,
                    "rule_name": self.name,
                    "actual_value": pressure,
                    "min_allowed": self.min_pressure,
                }
            if pressure > self.max_pressure:
                return {
                    "allowed": False,
                    "severity": RuleSeverity.BLOCK.value,
                    "message": f"Pressure {pressure}{self.unit} exceeds maximum ({self.max_pressure}{self.unit})",
                    "rule_id": self.id,
                    "rule_name": self.name,
                    "actual_value": pressure,
                    "max_allowed": self.max_pressure,
                }
            return {
                "allowed": True,
                "severity": self.severity.value,
                "message": f"Pressure {pressure}{self.unit} is within safe limits",
                "rule_id": self.id,
                "rule_name": self.name,
            }
        except (ValueError, TypeError):
            return {
                "allowed": False,
                "severity": RuleSeverity.BLOCK.value,
                "message": f"Invalid pressure value: {value}",
                "rule_id": self.id,
                "rule_name": self.name,
            }

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary with pressure-specific fields."""
        base_dict = super().to_dict()
        base_dict.update(
            {
                "max_pressure": self.max_pressure,
                "min_pressure": self.min_pressure,
                "unit": self.unit,
            }
        )
        return base_dict

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PressureLimitRule":
        """Create from dictionary."""
        return cls(
            id=data["id"],
            name=data["name"],
            rule_type=RuleType.PRESSURE_LIMIT,
            severity=RuleSeverity(data["severity"]),
            description=data.get("description", ""),
            device_type=data.get("device_type"),
            device_id=data.get("device_id"),
            point_name=data.get("point_name"),
            enabled=data.get("enabled", True),
            metadata=data.get("metadata", {}),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            max_pressure=data.get("max_pressure", 100.0),
            min_pressure=data.get("min_pressure", 0.0),
            unit=data.get("unit", "kPa"),
        )


@dataclass
class InterlockRule(SafetyRule):
    """Rule for device interlocks (e.g., fire alarm → disable HVAC)."""

    trigger_device_id: str = ""  # Device that triggers the interlock
    trigger_point: str = ""  # Point on trigger device
    trigger_value: Any = None  # Value that triggers the interlock
    action: str = "disable"  # disable, enable, set_value
    action_value: Optional[Any] = None

    def check(self, device: Any, value: Any) -> Dict[str, Any]:
        """Check if interlock condition is active."""
        # This rule requires checking the state of another device
        # For now, return a placeholder result
        # In a real implementation, we would query the trigger device state
        return {
            "allowed": True,  # Default to allowed for demo
            "severity": self.severity.value,
            "message": f"Interlock check: {self.trigger_device_id}.{self.trigger_point} = {self.trigger_value}",
            "rule_id": self.id,
            "rule_name": self.name,
            "interlock_active": False,  # Assume not active for demo
        }

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary with interlock-specific fields."""
        base_dict = super().to_dict()
        base_dict.update(
            {
                "trigger_device_id": self.trigger_device_id,
                "trigger_point": self.trigger_point,
                "trigger_value": self.trigger_value,
                "action": self.action,
                "action_value": self.action_value,
            }
        )
        return base_dict

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "InterlockRule":
        """Create from dictionary."""
        return cls(
            id=data["id"],
            name=data["name"],
            rule_type=RuleType.INTERLOCK,
            severity=RuleSeverity(data["severity"]),
            description=data.get("description", ""),
            device_type=data.get("device_type"),
            device_id=data.get("device_id"),
            point_name=data.get("point_name"),
            enabled=data.get("enabled", True),
            metadata=data.get("metadata", {}),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            trigger_device_id=data["trigger_device_id"],
            trigger_point=data["trigger_point"],
            trigger_value=data["trigger_value"],
            action=data.get("action", "disable"),
            action_value=data.get("action_value"),
        )


@dataclass
class RuntimeLimitRule(SafetyRule):
    """Rule for minimum runtime before restart (compressor protection)."""

    min_runtime_minutes: int = 5  # Minimum run time before restart
    max_starts_per_hour: int = 4  # Maximum starts per hour

    def check(self, device: Any, value: Any) -> Dict[str, Any]:
        """Check runtime and start frequency limits."""
        # For demo, assume device has runtime data in metadata
        runtime = device.metadata.get("runtime_minutes", 0) if hasattr(device, "metadata") else 0
        starts_this_hour = device.metadata.get("starts_this_hour", 0) if hasattr(device, "metadata") else 0

        violations = []

        # Check minimum runtime
        if runtime < self.min_runtime_minutes:
            violations.append(f"Runtime {runtime}min < minimum {self.min_runtime_minutes}min")

        # Check start frequency
        if starts_this_hour >= self.max_starts_per_hour:
            violations.append(f"Starts this hour {starts_this_hour} >= maximum {self.max_starts_per_hour}")

        if violations:
            return {
                "allowed": self.severity != RuleSeverity.BLOCK,
                "severity": self.severity.value,
                "message": f"Runtime limit violation: {', '.join(violations)}",
                "rule_id": self.id,
                "rule_name": self.name,
                "violations": violations,
            }

        return {
            "allowed": True,
            "severity": self.severity.value,
            "message": f"Runtime OK: {runtime}min runtime, {starts_this_hour} starts/hour",
            "rule_id": self.id,
            "rule_name": self.name,
        }

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary with runtime-specific fields."""
        base_dict = super().to_dict()
        base_dict.update(
            {
                "min_runtime_minutes": self.min_runtime_minutes,
                "max_starts_per_hour": self.max_starts_per_hour,
            }
        )
        return base_dict

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RuntimeLimitRule":
        """Create from dictionary."""
        return cls(
            id=data["id"],
            name=data["name"],
            rule_type=RuleType.RUNTIME_LIMIT,
            severity=RuleSeverity(data["severity"]),
            description=data.get("description", ""),
            device_type=data.get("device_type"),
            device_id=data.get("device_id"),
            point_name=data.get("point_name"),
            enabled=data.get("enabled", True),
            metadata=data.get("metadata", {}),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            min_runtime_minutes=data.get("min_runtime_minutes", 5),
            max_starts_per_hour=data.get("max_starts_per_hour", 4),
        )


@dataclass
class BrightnessLimitRule(SafetyRule):
    """Rule for maximum brightness limit."""

    max_brightness: int = 100  # Percentage
    min_brightness: int = 0  # Percentage

    def check(self, device: Any, value: Any) -> Dict[str, Any]:
        """Check if brightness is within limits."""
        try:
            brightness = int(value)
            if brightness < self.min_brightness:
                return {
                    "allowed": False,
                    "severity": RuleSeverity.BLOCK.value,
                    "message": f"Brightness {brightness}% is below minimum ({self.min_brightness}%)",
                    "rule_id": self.id,
                    "rule_name": self.name,
                    "actual_value": brightness,
                    "min_allowed": self.min_brightness,
                }
            if brightness > self.max_brightness:
                return {
                    "allowed": self.severity != RuleSeverity.BLOCK,
                    "severity": self.severity.value,
                    "message": f"Brightness {brightness}% exceeds maximum ({self.max_brightness}%)",
                    "rule_id": self.id,
                    "rule_name": self.name,
                    "actual_value": brightness,
                    "max_allowed": self.max_brightness,
                }
            return {
                "allowed": True,
                "severity": self.severity.value,
                "message": f"Brightness {brightness}% is within limits",
                "rule_id": self.id,
                "rule_name": self.name,
            }
        except (ValueError, TypeError):
            return {
                "allowed": False,
                "severity": RuleSeverity.BLOCK.value,
                "message": f"Invalid brightness value: {value}",
                "rule_id": self.id,
                "rule_name": self.name,
            }

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary with brightness-specific fields."""
        base_dict = super().to_dict()
        base_dict.update(
            {
                "max_brightness": self.max_brightness,
                "min_brightness": self.min_brightness,
            }
        )
        return base_dict

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BrightnessLimitRule":
        """Create from dictionary."""
        return cls(
            id=data["id"],
            name=data["name"],
            rule_type=RuleType.BRIGHTNESS_LIMIT,
            severity=RuleSeverity(data["severity"]),
            description=data.get("description", ""),
            device_type=data.get("device_type"),
            device_id=data.get("device_id"),
            point_name=data.get("point_name"),
            enabled=data.get("enabled", True),
            metadata=data.get("metadata", {}),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            max_brightness=data.get("max_brightness", 100),
            min_brightness=data.get("min_brightness", 0),
        )


@dataclass
class CustomRule(SafetyRule):
    """Custom rule with arbitrary validation logic."""

    validation_logic: str = ""  # Could be Python code or expression

    def check(self, device: Any, value: Any) -> Dict[str, Any]:
        """Execute custom validation logic."""
        # For demo, always allow with warning about custom logic
        return {
            "allowed": True,
            "severity": self.severity.value,
            "message": f"Custom rule check: {self.validation_logic[:50]}...",
            "rule_id": self.id,
            "rule_name": self.name,
        }

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary with custom-specific fields."""
        base_dict = super().to_dict()
        base_dict.update(
            {
                "validation_logic": self.validation_logic,
            }
        )
        return base_dict

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CustomRule":
        """Create from dictionary."""
        return cls(
            id=data["id"],
            name=data["name"],
            rule_type=RuleType.CUSTOM,
            severity=RuleSeverity(data["severity"]),
            description=data.get("description", ""),
            device_type=data.get("device_type"),
            device_id=data.get("device_id"),
            point_name=data.get("point_name"),
            enabled=data.get("enabled", True),
            metadata=data.get("metadata", {}),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            validation_logic=data.get("validation_logic", ""),
        )
