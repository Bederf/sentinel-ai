"""DALI-2 Lighting System Models.

Defines data structures for Tridonic Scenecom DALI-2 lighting integration.
Models for controllers, sensors (PIR/daylight), luminaires, and zone aggregations.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Dict, Any, Optional


class ControllerStatus(str, Enum):
    """Status of a DALI controller."""
    ONLINE = "online"
    OFFLINE = "offline"
    ERROR = "error"
    COMMISSIONING = "commissioning"


class SensorType(str, Enum):
    """Type of DALI sensor."""
    PIR = "pir"
    PIR_DAYLIGHT = "pir_daylight"
    DAYLIGHT_ONLY = "daylight"
    SWITCH = "switch"


class LuminaireType(str, Enum):
    """Type of luminaire."""
    LED_DOWNLIGHT = "led_downlight"
    LED_PANEL = "led_panel"
    LED_STRIP = "led_strip"
    LINEAR_LED = "linear_led"
    EMERGENCY = "emergency"


@dataclass
class DALIController:
    """DALI-2 controller (e.g., Tridonic Scenecom)."""

    controller_id: str
    name: str
    site_id: str
    building: str
    floor: str
    ip_address: str
    mac_address: str
    firmware_version: str
    status: str = "online"
    channel_count: int = 64
    sensors_connected: int = 0
    luminaires_connected: int = 0
    last_poll: Optional[str] = None
    created_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "controller_id": self.controller_id,
            "name": self.name,
            "site_id": self.site_id,
            "building": self.building,
            "floor": self.floor,
            "ip_address": self.ip_address,
            "mac_address": self.mac_address,
            "firmware_version": self.firmware_version,
            "status": self.status,
            "channel_count": self.channel_count,
            "sensors_connected": self.sensors_connected,
            "luminaires_connected": self.luminaires_connected,
            "last_poll": self.last_poll,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DALIController":
        """Create instance from dictionary."""
        return cls(
            controller_id=data.get("controller_id", ""),
            name=data.get("name", ""),
            site_id=data.get("site_id", ""),
            building=data.get("building", ""),
            floor=data.get("floor", ""),
            ip_address=data.get("ip_address", ""),
            mac_address=data.get("mac_address", ""),
            firmware_version=data.get("firmware_version", ""),
            status=data.get("status", "online"),
            channel_count=data.get("channel_count", 64),
            sensors_connected=data.get("sensors_connected", 0),
            luminaires_connected=data.get("luminaires_connected", 0),
            last_poll=data.get("last_poll"),
            created_at=data.get("created_at"),
        )


@dataclass
class DALISensor:
    """DALI-2 sensor (PIR occupancy and/or daylight)."""

    sensor_id: str
    name: str
    controller_id: str
    zone_id: str
    sensor_type: str = "pir_daylight"
    dali_address: int = 0
    occupancy: bool = False
    lux_level: float = 0.0
    has_daylight: bool = True
    desk_id: Optional[str] = None
    x_coord: Optional[float] = None
    y_coord: Optional[float] = None
    last_updated: Optional[str] = None
    # Scenecom extended fields
    daylight_setpoint: float = 500.0  # Target lux for daylight harvesting
    motion_count: int = 0  # Cumulative motion events (for analytics)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "sensor_id": self.sensor_id,
            "name": self.name,
            "controller_id": self.controller_id,
            "zone_id": self.zone_id,
            "sensor_type": self.sensor_type,
            "dali_address": self.dali_address,
            "occupancy": self.occupancy,
            "lux_level": self.lux_level,
            "has_daylight": self.has_daylight,
            "desk_id": self.desk_id,
            "x_coord": self.x_coord,
            "y_coord": self.y_coord,
            "last_updated": self.last_updated,
            "daylight_setpoint": self.daylight_setpoint,
            "motion_count": self.motion_count,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DALISensor":
        """Create instance from dictionary."""
        return cls(
            sensor_id=data.get("sensor_id", ""),
            name=data.get("name", ""),
            controller_id=data.get("controller_id", ""),
            zone_id=data.get("zone_id", ""),
            sensor_type=data.get("sensor_type", "pir_daylight"),
            dali_address=data.get("dali_address", 0),
            occupancy=data.get("occupancy", False),
            lux_level=data.get("lux_level", 0.0),
            has_daylight=data.get("has_daylight", True),
            desk_id=data.get("desk_id"),
            x_coord=data.get("x_coord"),
            y_coord=data.get("y_coord"),
            last_updated=data.get("last_updated"),
            daylight_setpoint=data.get("daylight_setpoint", 500.0),
            motion_count=data.get("motion_count", 0),
        )


@dataclass
class DALILuminaire:
    """DALI-2 controlled luminaire."""

    luminaire_id: str
    name: str
    controller_id: str
    zone_id: str
    luminaire_type: str = "led_panel"
    dali_address: int = 0
    current_level: int = 0  # 0-254 (DALI standard)
    target_level: int = 0
    min_level: int = 10
    max_level: int = 254
    power_consumption: float = 0.0  # Watts
    rated_power: float = 40.0
    fault_status: bool = False
    fault_code: Optional[str] = None
    lamp_hours: int = 0
    last_updated: Optional[str] = None
    # Scenecom extended fields
    color_temp_kelvin: Optional[int] = None  # Tunable white: 2700K-6500K (None if not supported)
    emergency_battery_pct: Optional[int] = None  # Emergency fitting battery % (None if not emergency)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "luminaire_id": self.luminaire_id,
            "name": self.name,
            "controller_id": self.controller_id,
            "zone_id": self.zone_id,
            "luminaire_type": self.luminaire_type,
            "dali_address": self.dali_address,
            "current_level": self.current_level,
            "target_level": self.target_level,
            "min_level": self.min_level,
            "max_level": self.max_level,
            "power_consumption": self.power_consumption,
            "rated_power": self.rated_power,
            "fault_status": self.fault_status,
            "fault_code": self.fault_code,
            "lamp_hours": self.lamp_hours,
            "last_updated": self.last_updated,
            "color_temp_kelvin": self.color_temp_kelvin,
            "emergency_battery_pct": self.emergency_battery_pct,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DALILuminaire":
        """Create instance from dictionary."""
        return cls(
            luminaire_id=data.get("luminaire_id", ""),
            name=data.get("name", ""),
            controller_id=data.get("controller_id", ""),
            zone_id=data.get("zone_id", ""),
            luminaire_type=data.get("luminaire_type", "led_panel"),
            dali_address=data.get("dali_address", 0),
            current_level=data.get("current_level", 0),
            target_level=data.get("target_level", 0),
            min_level=data.get("min_level", 10),
            max_level=data.get("max_level", 254),
            power_consumption=data.get("power_consumption", 0.0),
            rated_power=data.get("rated_power", 40.0),
            fault_status=data.get("fault_status", False),
            fault_code=data.get("fault_code"),
            lamp_hours=data.get("lamp_hours", 0),
            last_updated=data.get("last_updated"),
            color_temp_kelvin=data.get("color_temp_kelvin"),
            emergency_battery_pct=data.get("emergency_battery_pct"),
        )


@dataclass
class ZoneOccupancy:
    """Occupancy summary for a lighting zone."""

    zone_id: str
    zone_name: str
    total_sensors: int
    occupied_sensors: int
    occupancy_percent: float
    avg_lux_level: float = 0.0
    max_lux_level: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "zone_id": self.zone_id,
            "zone_name": self.zone_name,
            "total_sensors": self.total_sensors,
            "occupied_sensors": self.occupied_sensors,
            "occupancy_percent": self.occupancy_percent,
            "avg_lux_level": self.avg_lux_level,
            "max_lux_level": self.max_lux_level,
        }


@dataclass
class ZoneLighting:
    """Lighting summary for a zone."""

    zone_id: str
    zone_name: str
    total_luminaires: int
    active_luminaires: int
    avg_dim_level: float
    total_power_w: float
    faulty_count: int = 0
    # Scenecom extended fields
    active_scene: Optional[int] = None  # Current scene number (1-8), None if manual
    active_scene_name: Optional[str] = None  # Scene name (e.g., "Working", "Presentation")

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "zone_id": self.zone_id,
            "zone_name": self.zone_name,
            "total_luminaires": self.total_luminaires,
            "active_luminaires": self.active_luminaires,
            "avg_dim_level": self.avg_dim_level,
            "total_power_w": self.total_power_w,
            "faulty_count": self.faulty_count,
            "active_scene": self.active_scene,
            "active_scene_name": self.active_scene_name,
        }


@dataclass
class FloorSummary:
    """Occupancy and lighting summary for a floor."""

    floor: str
    zones: List[ZoneOccupancy] = field(default_factory=list)
    total_occupancy_percent: float = 0.0
    total_power_kw: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "floor": self.floor,
            "zones": [z.to_dict() for z in self.zones],
            "total_occupancy_percent": self.total_occupancy_percent,
            "total_power_kw": self.total_power_kw,
        }
