"""Security module models.

Pydantic models for access control, CCTV monitoring, occupancy tracking,
alarm zones, and cross-module coordination with HVAC/Lighting.
"""

from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


# --- Enums ---

class DoorStatus(str, Enum):
    """Door status values."""
    OPEN = "open"
    CLOSED = "closed"
    LOCKED = "locked"
    FAULT = "fault"


class AccessLevel(str, Enum):
    """Zone access level."""
    PUBLIC = "public"
    RESTRICTED = "restricted"
    SECURE = "secure"
    CRITICAL = "critical"


class CameraStatus(str, Enum):
    """Camera operational status."""
    ONLINE = "online"
    OFFLINE = "offline"
    FAULT = "fault"


class CameraType(str, Enum):
    """Camera type."""
    FIXED = "fixed"
    PTZ = "ptz"
    DOME = "dome"


class AlarmStatus(str, Enum):
    """Alarm zone status."""
    ARMED = "armed"
    DISARMED = "disarmed"
    TRIGGERED = "triggered"
    FAULT = "fault"


class ArmType(str, Enum):
    """Alarm arm type."""
    FULL = "full"
    PERIMETER = "perimeter"
    NIGHT = "night"


class EventDirection(str, Enum):
    """Badge event direction."""
    ENTRY = "entry"
    EXIT = "exit"


class ReaderType(str, Enum):
    """Door reader type."""
    CARD = "card"
    BIOMETRIC = "biometric"
    PIN = "pin"


class OccupancySource(str, Enum):
    """Occupancy data source."""
    BADGE = "badge"
    CAMERA = "camera"
    COMBINED = "combined"


class CCureEventType(str, Enum):
    """C•CURE 9000 access event types."""
    ACCESS_GRANTED = "access_granted"
    ACCESS_DENIED = "access_denied"
    FORCED_DOOR = "forced_door"
    DOOR_HELD_OPEN = "door_held_open"
    ANTI_PASSBACK = "anti_passback"
    TAMPER = "tamper"
    CONTROLLER_OFFLINE = "controller_offline"
    DURESS = "duress"


class ControllerStatus(str, Enum):
    """C•CURE iSTAR controller status."""
    ONLINE = "online"
    OFFLINE = "offline"
    DEGRADED = "degraded"


class TamperStatus(str, Enum):
    """C•CURE controller tamper status."""
    NORMAL = "normal"
    ENCLOSURE_OPEN = "enclosure_open"
    BACK_TAMPER = "back_tamper"


# --- Models ---

class AccessZone(BaseModel):
    """Access zone definition with doors and access level."""
    zone_id: str
    name: str
    floor: str
    access_level: AccessLevel = AccessLevel.RESTRICTED
    doors: List[str] = []


class Door(BaseModel):
    """Door with reader and current status."""
    door_id: str
    name: str
    zone_id: str
    status: DoorStatus = DoorStatus.LOCKED
    reader_type: ReaderType = ReaderType.CARD
    last_event_time: Optional[datetime] = None


class BadgeEvent(BaseModel):
    """Badge access event."""
    event_id: str
    door_id: str
    zone_id: str
    badge_id: str
    person_name: str
    direction: EventDirection = EventDirection.ENTRY
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    granted: bool = True
    reason: str = ""
    # C•CURE-specific fields (optional, for extended functionality)
    event_type: Optional[CCureEventType] = CCureEventType.ACCESS_GRANTED
    clearance_level: Optional[str] = None
    department: Optional[str] = None
    after_hours: bool = False


class Camera(BaseModel):
    """CCTV camera status and details."""
    camera_id: str
    name: str
    zone_id: str
    floor: str
    status: CameraStatus = CameraStatus.ONLINE
    type: CameraType = CameraType.FIXED
    resolution: str = "1080p"
    has_analytics: bool = False
    motion_detected: bool = False


class AlarmZone(BaseModel):
    """Intrusion alarm zone."""
    zone_id: str
    name: str
    status: AlarmStatus = AlarmStatus.DISARMED
    arm_type: ArmType = ArmType.FULL


class SecurityOccupancy(BaseModel):
    """Per-zone occupancy derived from badge events."""
    zone_id: str
    zone_name: str
    occupancy_count: int = 0
    badge_entries: int = 0
    badge_exits: int = 0
    last_updated: Optional[datetime] = None
    source: OccupancySource = OccupancySource.BADGE


class SecuritySystemStatus(BaseModel):
    """Aggregate security system status."""
    total_doors: int = 0
    doors_secure: int = 0
    cameras_online: int = 0
    cameras_total: int = 0
    alarm_zones_armed: int = 0
    alarm_zones_total: int = 0
    active_alerts: int = 0
    occupancy_total: int = 0


# --- C•CURE 9000 Integration Models ---


class CCurePersonnel(BaseModel):
    """C•CURE personnel/badge holder information."""
    person_id: str
    badge_id: str
    first_name: str
    last_name: str
    department: Optional[str] = None
    clearance_level: str
    photo_url: Optional[str] = None
    active: bool = True

    @property
    def person_name(self) -> str:
        """Full name for display."""
        return f"{self.first_name} {self.last_name}"


class CCureController(BaseModel):
    """C•CURE iSTAR controller hardware status and details."""
    controller_id: str
    name: str
    model: str  # e.g., "iSTAR Ultra", "iSTAR Edge"
    firmware: str
    encryption_mode: str  # e.g., "FIPS 197 AES-256"
    tamper_status: str = TamperStatus.NORMAL
    last_seen: datetime
    ip_address: str
    reader_count: int
    status: ControllerStatus = ControllerStatus.ONLINE


class CCureClearance(BaseModel):
    """C•CURE clearance/access level definition."""
    clearance_id: str
    name: str
    description: Optional[str] = None
    partition: str
    door_ids: List[str] = []
    time_schedules: List[str] = []


class CCureZone(BaseModel):
    """C•CURE anti-passback zone for occupancy tracking."""
    zone_id: str
    name: str
    current_count: int = 0
    max_occupancy: int = 0
    anti_passback_enabled: bool = True


class SecurityAnomaly(BaseModel):
    """Detected security anomaly (after-hours, equipment health, etc.)."""
    anomaly_id: Optional[str] = None
    anomaly_type: str  # after_hours_access, controller_offline, forced_door, etc.
    severity: str  # warning, critical, info
    badge_event_id: Optional[str] = None
    zone_id: Optional[str] = None
    description: str
    hvac_correlation: Optional[Dict] = None
    lighting_correlation: Optional[Dict] = None
    energy_impact: Optional[str] = None
    resolved: bool = False
    detected_at: datetime = Field(default_factory=datetime.utcnow)
    resolved_at: Optional[datetime] = None
    notes: Optional[str] = None
