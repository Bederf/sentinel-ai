"""Device models for building automation system.

This module defines protocol-agnostic device models that can represent
any building automation device (HVAC, lighting, security, etc.) regardless
of the underlying protocol (BACnet, Modbus, mock, etc.).
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, Any, Optional, List
import uuid


class DeviceStatus(Enum):
    """Device operational status."""
    ONLINE = "online"
    OFFLINE = "offline"
    FAULT = "fault"
    MAINTENANCE = "maintenance"
    STANDBY = "standby"


class DeviceType(Enum):
    """Types of building automation devices."""
    HVAC = "hvac"
    LIGHTING = "lighting"
    SECURITY = "security"
    FIRE_SAFETY = "fire_safety"
    ACCESS_CONTROL = "access_control"
    POWER = "power"
    OTHER = "other"


class ProtocolType(Enum):
    """Communication protocols supported."""
    BACNET = "bacnet"
    MODBUS = "modbus"
    MOCK = "mock"
    HTTP = "http"
    MQTT = "mqtt"


class PointType(Enum):
    """Types of data points on devices."""
    ANALOG_INPUT = "analog_input"
    ANALOG_OUTPUT = "analog_output"
    ANALOG_VALUE = "analog_value"
    BINARY_INPUT = "binary_input"
    BINARY_OUTPUT = "binary_output"
    BINARY_VALUE = "binary_value"
    MULTISTATE_INPUT = "multistate_input"
    MULTISTATE_OUTPUT = "multistate_output"
    MULTISTATE_VALUE = "multistate_value"


@dataclass
class DevicePoint:
    """A data point on a device (sensor, actuator, value)."""
    name: str
    point_type: PointType
    description: str = ""
    unit: str = ""
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    default_value: Optional[Any] = None
    writable: bool = False
    priority: int = 8  # Default priority for writable points
    metadata: Dict[str, Any] = field(default_factory=dict)

    def validate_value(self, value: Any) -> bool:
        """Validate if value is within acceptable range for this point."""
        if self.point_type in [PointType.ANALOG_INPUT, PointType.ANALOG_OUTPUT, PointType.ANALOG_VALUE]:
            if not isinstance(value, (int, float)):
                return False
            if self.min_value is not None and value < self.min_value:
                return False
            if self.max_value is not None and value > self.max_value:
                return False
        elif self.point_type in [PointType.BINARY_INPUT, PointType.BINARY_OUTPUT, PointType.BINARY_VALUE]:
            # Accept both boolean and integer 0/1 values for binary points
            if not isinstance(value, (bool, int)):
                return False
            if isinstance(value, int) and value not in [0, 1]:
                return False
        elif self.point_type in [PointType.MULTISTATE_INPUT, PointType.MULTISTATE_OUTPUT, PointType.MULTISTATE_VALUE]:
            if not isinstance(value, int):
                return False
        return True


@dataclass
class DeviceValue:
    """A value read from or written to a device point."""
    point_name: str
    value: Any
    unit: str = ""
    timestamp: str = ""
    quality: str = "good"  # good, bad, uncertain
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response."""
        return {
            "point_name": self.point_name,
            "value": self.value,
            "unit": self.unit,
            "timestamp": self.timestamp,
            "quality": self.quality,
            **self.metadata
        }


@dataclass
class Device:
    """Base device model."""
    id: str
    name: str
    device_type: DeviceType
    protocol: ProtocolType
    location: str
    site_id: str
    status: DeviceStatus = DeviceStatus.ONLINE
    description: str = ""
    manufacturer: str = ""
    model: str = ""
    points: Dict[str, DevicePoint] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    last_seen: str = ""
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self):
        if not self.last_seen:
            self.last_seen = datetime.now().isoformat()
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
        if not self.updated_at:
            self.updated_at = datetime.now().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response."""
        return {
            "id": self.id,
            "name": self.name,
            "device_type": self.device_type.value,
            "protocol": self.protocol.value,
            "location": self.location,
            "site_id": self.site_id,
            "status": self.status.value,
            "description": self.description,
            "manufacturer": self.manufacturer,
            "model": self.model,
            "points": {name: self._point_to_dict(point) for name, point in self.points.items()},
            "metadata": self.metadata,
            "last_seen": self.last_seen,
            "created_at": self.created_at,
            "updated_at": self.updated_at
        }

    def _point_to_dict(self, point: DevicePoint) -> Dict[str, Any]:
        """Convert DevicePoint to dictionary."""
        return {
            "name": point.name,
            "point_type": point.point_type.value,
            "description": point.description,
            "unit": point.unit,
            "min_value": point.min_value,
            "max_value": point.max_value,
            "default_value": point.default_value,
            "writable": point.writable,
            "priority": point.priority,
            "metadata": point.metadata
        }

    def get_point(self, point_name: str) -> Optional[DevicePoint]:
        """Get a point by name."""
        return self.points.get(point_name)

    def validate_point_value(self, point_name: str, value: Any) -> bool:
        """Validate if value is acceptable for the given point."""
        point = self.get_point(point_name)
        if not point:
            return False
        return point.validate_value(value)


@dataclass
class HVACDevice(Device):
    """HVAC-specific device (chillers, AHUs, fans, pumps)."""
    hvac_type: str = ""  # chiller, ahu, fan, pump, vav, etc.
    capacity: Optional[float] = None  # kW or tons
    efficiency: Optional[float] = None  # COP or efficiency rating
    setpoints: Dict[str, float] = field(default_factory=dict)  # temperature, pressure setpoints

    def __post_init__(self):
        super().__post_init__()
        self.device_type = DeviceType.HVAC


@dataclass
class LightingDevice(Device):
    """Lighting control device."""
    lighting_type: str = ""  # panel, dimmer, switch, sensor
    circuit_count: int = 1
    total_wattage: Optional[float] = None
    dimmable: bool = False

    def __post_init__(self):
        super().__post_init__()
        self.device_type = DeviceType.LIGHTING


@dataclass
class SecurityDevice(Device):
    """Security system device."""
    security_type: str = ""  # camera, reader, sensor, panel
    zone: str = ""
    armed: bool = False
    tamper_status: str = "normal"

    def __post_init__(self):
        super().__post_init__()
        self.device_type = DeviceType.SECURITY


def create_device_from_dict(data: Dict[str, Any]) -> Device:
    """Create appropriate device type from dictionary data."""
    device_type = DeviceType(data.get("device_type", "other"))

    # Set default values for required fields
    data.setdefault("id", str(uuid.uuid4()))
    data.setdefault("protocol", ProtocolType.MOCK.value)
    data.setdefault("status", DeviceStatus.ONLINE.value)

    # Extract site_id from metadata.building_id if not provided directly
    if "site_id" not in data and "metadata" in data:
        metadata = data.get("metadata", {})
        if "building_id" in metadata:
            data["site_id"] = metadata["building_id"]

    # Also set location from metadata if not provided
    if "location" not in data and "metadata" in data:
        metadata = data.get("metadata", {})
        if "location" in metadata:
            data["location"] = metadata["location"]

    # Convert string enums to Enum instances
    if isinstance(data.get("device_type"), str):
        data["device_type"] = DeviceType(data["device_type"])
    if isinstance(data.get("protocol"), str):
        data["protocol"] = ProtocolType(data["protocol"])
    if isinstance(data.get("status"), str):
        data["status"] = DeviceStatus(data["status"])

    # Convert points dictionary to DevicePoint objects
    if "points" in data and isinstance(data["points"], dict):
        points_dict = {}
        for point_name, point_data in data["points"].items():
            if isinstance(point_data, dict):
                point_data.setdefault("name", point_name)
                if isinstance(point_data.get("point_type"), str):
                    point_data["point_type"] = PointType(point_data["point_type"])
                points_dict[point_name] = DevicePoint(**point_data)
        data["points"] = points_dict

    # Create appropriate device subclass
    if device_type == DeviceType.HVAC:
        return HVACDevice(**data)
    elif device_type == DeviceType.LIGHTING:
        return LightingDevice(**data)
    elif device_type == DeviceType.SECURITY:
        return SecurityDevice(**data)
    else:
        return Device(**data)