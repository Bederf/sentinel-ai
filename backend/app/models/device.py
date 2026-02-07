"""Device models for building automation system.

This module defines protocol-agnostic device models that can represent
any building automation device (HVAC, lighting, security, etc.) regardless
of the underlying protocol (BACnet, Modbus, mock, etc.).
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, Any, Optional
import uuid

# Import water meter models
from app.models.water_meter import WaterMeter, WaterConsumption, WaterAlert


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
    REFRIGERATION = "refrigeration"
    MEDICAL = "medical"
    LIFT = "lift"
    CONTROLLER = "controller"
    METER = "meter"
    SOLAR = "solar"
    BESS = "bess"
    OTHER = "other"


class ProtocolType(Enum):
    """Communication protocols supported."""
    BACNET = "bacnet"
    MODBUS = "modbus"
    MOCK = "mock"
    HTTP = "http"
    MQTT = "mqtt"


class ZoneType(Enum):
    """Types of building zones for optimization prioritization."""
    EXECUTIVE = "executive"          # Priority 1 - always comfortable
    SERVER_ROOM = "server_room"      # Priority 1 - critical cooling
    MEETING_ROOM = "meeting_room"    # Priority 2 - when occupied
    OPEN_OFFICE = "open_office"      # Priority 3 - standard comfort
    LOBBY = "lobby"                  # Priority 4 - public facing
    PLANT_ROOM = "plant_room"        # Priority 5 - equipment only
    PARKING = "parking"              # Priority 6 - minimal HVAC
    BANKING_HALL = "banking_hall"    # Priority 2 - customer facing
    STAIRWELL = "stairwell"          # Priority 6 - minimal HVAC
    CORRIDOR = "corridor"            # Priority 5 - circulation
    RESTROOM = "restroom"            # Priority 4 - hygiene
    KITCHEN = "kitchen"              # Priority 3 - staff amenity
    STORAGE = "storage"              # Priority 6 - minimal HVAC
    RECEPTION = "reception"          # Priority 3 - visitor facing
    ROOF = "roof"                    # Priority 6 - equipment only
    BASEMENT = "basement"            # Priority 5 - varies
    UNKNOWN = "unknown"              # Default for unclassified zones


class ExposureDirection(Enum):
    """Exterior exposure direction for solar heat gain calculations."""
    NORTH = "north"           # Minimal solar gain (Southern Hemisphere)
    SOUTH = "south"           # Maximum solar gain (Southern Hemisphere)
    EAST = "east"             # Morning solar gain
    WEST = "west"             # Afternoon solar gain
    INTERIOR = "interior"     # No exterior exposure


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
class DeviceLocation:
    """Physical location of a device for technician navigation.

    Links devices to zones for zone-based control and analysis.
    A zone contains multiple devices/equipment (AHU, VAV, FCU, luminaires, etc.).
    """
    building: str  # Full building name
    floor: str  # FL1, FL2, Basement, Roof, Ground
    zone: str  # Q1-Q4 or directional (North, South, East, West)
    room: str  # MR4 (Mechanical Room 4), ER1, OR12, etc.
    description: str  # Human-readable location string
    zone_id: Optional[str] = None  # References hvac_zones.zone_id for device-to-zone mapping
    # Zone-aware optimization fields
    zone_type: Optional['ZoneType'] = None  # Type of zone for optimization priority
    exposure: Optional['ExposureDirection'] = None  # Exterior exposure for solar gain
    zone_priority: int = 3  # 1=critical (always maintain), 5=lowest (shed first)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response."""
        return {
            "building": self.building,
            "floor": self.floor,
            "zone": self.zone,
            "room": self.room,
            "description": self.description,
            "zone_id": self.zone_id,
            "zone_type": self.zone_type.value if self.zone_type else None,
            "exposure": self.exposure.value if self.exposure else None,
            "zone_priority": self.zone_priority
        }

    def compact_display(self) -> str:
        """Return compact location format: FL2/Q3/MR4"""
        return f"{self.floor}/{self.zone}/{self.room}"

    def full_display(self) -> str:
        """Return full location format: Building, Floor X, Zone Y, Room Z"""
        return f"{self.building}, {self.floor_description}, {self.zone_description}, {self.room_description}"

    @property
    def floor_description(self) -> str:
        """Get human-readable floor description."""
        if self.floor.startswith("FL"):
            return f"Floor {self.floor[2:]}"
        return self.floor

    @property
    def zone_description(self) -> str:
        """Get human-readable zone description."""
        if self.zone.startswith("Q"):
            return f"Quadrant {self.zone[1:]}"
        return self.zone

    @property
    def room_description(self) -> str:
        """Get human-readable room description."""
        # Room type codes
        room_types = {
            "MR": "Mechanical Room",
            "ER": "Electrical Room",
            "OR": "Office Room",
            "SR": "Server Room",
            "WR": "Washroom",
            "KR": "Kitchen",
            "LR": "Lobby/Reception",
            "ST": "Storage"
        }
        # Extract room type code (letters before numbers)
        import re
        match = re.match(r"([A-Z]+)(\d+)", self.room)
        if match:
            code, number = match.groups()
            room_type = room_types.get(code, "Room")
            return f"{room_type} {number}"
        return self.room


@dataclass
class DeviceEquipment:
    """Equipment make, model, and specifications."""
    manufacturer: str  # Manufacturer name
    model: str  # Model number/name
    serial_number: Optional[str] = None  # Asset serial number
    installation_year: Optional[int] = None  # Year installed
    capacity_kw: Optional[float] = None  # Capacity in kW (for HVAC)
    specifications: Dict[str, Any] = field(default_factory=dict)  # Additional specs

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response."""
        return {
            "manufacturer": self.manufacturer,
            "model": self.model,
            "serial_number": self.serial_number,
            "installation_year": self.installation_year,
            "capacity_kw": self.capacity_kw,
            "specifications": self.specifications
        }


@dataclass
class Device:
    """Base device model."""
    id: str
    name: str
    device_type: DeviceType
    protocol: ProtocolType
    site_id: str

    # New structured location and equipment (recommended)
    device_location: DeviceLocation
    equipment: DeviceEquipment

    # Legacy fields for backward compatibility (deprecated)
    location: str = ""  # Use device_location instead
    manufacturer: str = ""  # Use equipment.manufacturer instead
    model: str = ""  # Use equipment.model instead

    status: DeviceStatus = DeviceStatus.ONLINE
    description: str = ""
    points: Dict[str, DevicePoint] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    last_seen: str = ""
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self):
        # Sync legacy fields with new structured fields
        if self.device_location and not self.location:
            self.location = self.device_location.compact_display()
        if self.equipment:
            if not self.manufacturer:
                self.manufacturer = self.equipment.manufacturer
            if not self.model:
                self.model = self.equipment.model

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
            "site_id": self.site_id,
            "location": self.location,  # Legacy compact format
            "device_location": self.device_location.to_dict(),  # New structured format
            "equipment": self.equipment.to_dict(),  # New structured format
            "manufacturer": self.manufacturer,  # Legacy (kept for backward compatibility)
            "model": self.model,  # Legacy (kept for backward compatibility)
            "status": self.status.value,
            "description": self.description,
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
    try:
        device_type = DeviceType(data.get("device_type", "other"))
    except ValueError:
        device_type = DeviceType.OTHER

    # Set default values for required fields
    data.setdefault("id", str(uuid.uuid4()))
    data.setdefault("protocol", ProtocolType.MOCK.value)
    data.setdefault("status", DeviceStatus.ONLINE.value)

    # Extract site_id from metadata.building_id if not provided directly
    if "site_id" not in data and "metadata" in data:
        metadata = data.get("metadata", {})
        if "building_id" in metadata:
            data["site_id"] = metadata["building_id"]

    # Handle device_location (new structured format)
    if "device_location" in data and isinstance(data["device_location"], dict):
        loc_data = data["device_location"]
        # Convert zone_type and exposure strings to enums if present (with fallback)
        if "zone_type" in loc_data and isinstance(loc_data["zone_type"], str):
            try:
                loc_data["zone_type"] = ZoneType(loc_data["zone_type"])
            except ValueError:
                loc_data["zone_type"] = ZoneType.UNKNOWN
        if "exposure" in loc_data and isinstance(loc_data["exposure"], str):
            try:
                loc_data["exposure"] = ExposureDirection(loc_data["exposure"])
            except ValueError:
                loc_data["exposure"] = ExposureDirection.INTERIOR
        data["device_location"] = DeviceLocation(**loc_data)
    elif "location" in data and isinstance(data["location"], str):
        # Legacy string location - create basic DeviceLocation
        data["device_location"] = DeviceLocation(
            building=data.get("name", "Unknown"),
            floor="Ground",
            zone="Q1",
            room=data["location"],
            description=data["location"]
        )
    else:
        # Default location
        data["device_location"] = DeviceLocation(
            building=data.get("name", "Unknown"),
            floor="Ground",
            zone="Q1",
            room="Unknown",
            description="Unknown location"
        )

    # Handle equipment (new structured format)
    if "equipment" in data and isinstance(data["equipment"], dict):
        data["equipment"] = DeviceEquipment(**data["equipment"])
    else:
        # Create equipment from legacy manufacturer/model fields
        data["equipment"] = DeviceEquipment(
            manufacturer=data.get("manufacturer", ""),
            model=data.get("model", "")
        )

    # Also set location string from metadata if not provided (backward compatibility)
    if "location" not in data and "metadata" in data:
        metadata = data.get("metadata", {})
        if "location" in metadata:
            data["location"] = metadata["location"]

    # Convert string enums to Enum instances (with fallbacks for invalid values)
    if isinstance(data.get("device_type"), str):
        try:
            data["device_type"] = DeviceType(data["device_type"])
        except ValueError:
            data["device_type"] = DeviceType.OTHER
    if isinstance(data.get("protocol"), str):
        try:
            data["protocol"] = ProtocolType(data["protocol"])
        except ValueError:
            data["protocol"] = ProtocolType.MOCK
    if isinstance(data.get("status"), str):
        try:
            data["status"] = DeviceStatus(data["status"])
        except ValueError:
            data["status"] = DeviceStatus.ONLINE

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

    # Get valid fields for each device class to filter out unknown kwargs
    device_fields = {f.name for f in Device.__dataclass_fields__.values()}
    hvac_fields = device_fields | {f.name for f in HVACDevice.__dataclass_fields__.values()}
    lighting_fields = device_fields | {f.name for f in LightingDevice.__dataclass_fields__.values()}
    security_fields = device_fields | {f.name for f in SecurityDevice.__dataclass_fields__.values()}

    # Create appropriate device subclass with filtered data
    if device_type == DeviceType.HVAC:
        filtered = {k: v for k, v in data.items() if k in hvac_fields}
        return HVACDevice(**filtered)
    elif device_type == DeviceType.LIGHTING:
        filtered = {k: v for k, v in data.items() if k in lighting_fields}
        return LightingDevice(**filtered)
    elif device_type == DeviceType.SECURITY:
        filtered = {k: v for k, v in data.items() if k in security_fields}
        return SecurityDevice(**filtered)
    else:
        filtered = {k: v for k, v in data.items() if k in device_fields}
        return Device(**filtered)