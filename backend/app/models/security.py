"""Security module data models.

Provides data structures for:
- Access control events (badge access, overrides, denials)
- Access points (doors, readers, sensors)
- Access cards and credentials
- Visitor management and check-in/out tracking
- Security alerts (forced entry, tailgating, after-hours access)
"""

from typing import Optional, List, Dict, Any
from enum import Enum
from datetime import datetime
from pydantic import BaseModel, Field
import uuid


# ============================================================================
# Access Control Models
# ============================================================================


class AccessType(str, Enum):
    """Type of access credential used."""

    BADGE = "badge"
    CODE = "code"
    OVERRIDE = "override"
    BIOMETRIC = "biometric"
    MANUAL = "manual"


class AccessStatus(str, Enum):
    """Result of access attempt."""

    GRANTED = "granted"
    DENIED = "denied"
    TIMEOUT = "timeout"
    ERROR = "error"


class AccessEvent(BaseModel):
    """Single access control event (person entering/exiting)."""

    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime
    access_point_id: str  # Door/reader ID
    card_id: str  # Badge or credential ID
    person_name: str
    status: AccessStatus  # granted/denied/timeout
    access_type: AccessType  # badge/code/override/biometric
    location: str  # Building zone or door name
    duration_seconds: Optional[int] = None  # Time held door open

    class Config:
        use_enum_values = True

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "event_id": self.event_id,
            "timestamp": self.timestamp.isoformat(),
            "access_point_id": self.access_point_id,
            "card_id": self.card_id,
            "person_name": self.person_name,
            "status": self.status,
            "access_type": self.access_type,
            "location": self.location,
            "duration_seconds": self.duration_seconds,
        }


class DeviceType(str, Enum):
    """Type of access control device."""

    READER = "reader"
    LOCK = "lock"
    SENSOR = "sensor"
    CONTROLLER = "controller"


class PointStatus(str, Enum):
    """Status of access control point."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    ALARM = "alarm"
    MAINTENANCE = "maintenance"


class AccessPoint(BaseModel):
    """Physical access control point (door, gate, reader)."""

    point_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    building_id: str
    zone: str  # Floor or area
    location: str  # Descriptive name (e.g., "Server Room Door")
    device_type: DeviceType  # reader, lock, sensor, controller
    status: PointStatus  # active, inactive, alarm, maintenance
    last_activity: Optional[datetime] = None

    class Config:
        use_enum_values = True

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "point_id": self.point_id,
            "building_id": self.building_id,
            "zone": self.zone,
            "location": self.location,
            "device_type": self.device_type,
            "status": self.status,
            "last_activity": self.last_activity.isoformat() if self.last_activity else None,
        }


class CardStatus(str, Enum):
    """Status of access card."""

    ACTIVE = "active"
    REVOKED = "revoked"
    EXPIRED = "expired"
    SUSPENDED = "suspended"


class AccessLevel(str, Enum):
    """Access privilege level."""

    VISITOR = "visitor"
    EMPLOYEE = "employee"
    CONTRACTOR = "contractor"
    VENDOR = "vendor"
    EXECUTIVE = "executive"


class AccessCard(BaseModel):
    """Access credential (badge, card, code)."""

    card_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    person_name: str
    access_level: AccessLevel
    issued_date: datetime
    expiry_date: datetime
    status: CardStatus
    allowed_points: List[str] = Field(default_factory=list)  # Point IDs

    class Config:
        use_enum_values = True

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "card_id": self.card_id,
            "person_name": self.person_name,
            "access_level": self.access_level,
            "issued_date": self.issued_date.isoformat(),
            "expiry_date": self.expiry_date.isoformat(),
            "status": self.status,
            "allowed_points": self.allowed_points,
        }


# ============================================================================
# Visitor Management Models
# ============================================================================


class VisitorStatus(str, Enum):
    """Visitor state."""

    PENDING = "pending"
    CHECKED_IN = "checked_in"
    CHECKED_OUT = "checked_out"
    REVOKED = "revoked"


class Visitor(BaseModel):
    """Temporary visitor with managed access."""

    visitor_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    company: str
    visit_date: datetime
    host_contact: str  # Employee receiving visitor
    access_points: List[str] = Field(default_factory=list)  # Allowed point IDs
    status: VisitorStatus
    checkin_time: Optional[datetime] = None
    checkout_time: Optional[datetime] = None
    purpose: Optional[str] = None

    class Config:
        use_enum_values = True

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "visitor_id": self.visitor_id,
            "name": self.name,
            "company": self.company,
            "visit_date": self.visit_date.isoformat(),
            "host_contact": self.host_contact,
            "access_points": self.access_points,
            "status": self.status,
            "checkin_time": self.checkin_time.isoformat() if self.checkin_time else None,
            "checkout_time": self.checkout_time.isoformat() if self.checkout_time else None,
            "purpose": self.purpose,
        }


class VisitSchedule(BaseModel):
    """Scheduled visitor visit."""

    visit_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    visitor_id: str
    scheduled_date: datetime
    expected_duration: int  # Minutes
    purpose: str
    host_contact: str


# ============================================================================
# Alert Models
# ============================================================================


class AlertType(str, Enum):
    """Type of security alert."""

    FORCED_ENTRY = "forced_entry"
    TAILGATING = "tailgating"
    AFTER_HOURS = "after_hours"
    OVERRIDE = "override"
    CARD_REVOKED = "card_revoked"
    MULTIPLE_ATTEMPTS = "multiple_attempts"
    UNAUTHORIZED_ACCESS = "unauthorized_access"


class AlertSeverity(str, Enum):
    """Alert priority level."""

    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


class AlertStatus(str, Enum):
    """Alert resolution state."""

    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"


class SecurityAlert(BaseModel):
    """Security event that requires attention."""

    alert_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    alert_type: AlertType
    timestamp: datetime
    location: str
    building_id: str
    severity: AlertSeverity
    status: AlertStatus
    description: str
    related_events: List[str] = Field(default_factory=list)  # Event IDs
    acknowledged_by: Optional[str] = None
    acknowledged_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None

    class Config:
        use_enum_values = True

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "alert_id": self.alert_id,
            "alert_type": self.alert_type,
            "timestamp": self.timestamp.isoformat(),
            "location": self.location,
            "building_id": self.building_id,
            "severity": self.severity,
            "status": self.status,
            "description": self.description,
            "related_events": self.related_events,
            "acknowledged_by": self.acknowledged_by,
            "acknowledged_at": self.acknowledged_at.isoformat() if self.acknowledged_at else None,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
        }


# ============================================================================
# Summary Models (for API responses)
# ============================================================================


class SecurityOverview(BaseModel):
    """Security system status summary."""

    total_access_events_today: int
    active_visitors: int
    open_alerts: int
    after_hours_access_count: int
    system_status: str  # "online", "polling", "offline"
    last_updated: datetime


class OccupancyData(BaseModel):
    """Building occupancy from security system."""

    total_occupancy: int
    by_floor: Dict[str, int]
    by_zone: Dict[str, int]
    last_updated: datetime


class OccupancySource(str, Enum):
    """Source of occupancy data."""

    BADGE = "badge"
    SENSOR = "sensor"
    CAMERA = "camera"
    MANUAL = "manual"


class SecurityOccupancy(BaseModel):
    """Per-zone occupancy snapshot from security system."""

    zone_id: str
    zone_name: str = ""
    occupancy_count: int = 0
    badge_entries: int = 0
    badge_exits: int = 0
    last_updated: Optional[str] = None
    source: OccupancySource = OccupancySource.BADGE
