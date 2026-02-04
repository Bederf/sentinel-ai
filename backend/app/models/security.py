"""Security module models.

Pydantic models for access control, CCTV monitoring, occupancy tracking,
alarm zones, and cross-module coordination with HVAC/Lighting.
"""

from datetime import datetime
from enum import Enum
from typing import List, Optional
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
