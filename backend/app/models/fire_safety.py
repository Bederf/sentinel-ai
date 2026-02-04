"""Fire & life safety system models.

Pydantic models for fire alarm panels, smoke dampers, stairwell pressurization,
and cause-effect matrix coordination.
"""

from datetime import datetime
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


# --- Enums ---

class FireZoneType(str, Enum):
    """Types of fire zones."""
    CORRIDOR = "corridor"
    OFFICE = "office"
    STAIRWELL = "stairwell"
    PLANT_ROOM = "plant_room"
    PARKING = "parking"
    SERVER_ROOM = "server_room"
    LOBBY = "lobby"


class AlarmType(str, Enum):
    """Types of fire alarms."""
    SMOKE = "smoke"
    HEAT = "heat"
    MANUAL = "manual"
    FLOW = "flow"
    FAULT = "fault"


class AlarmSeverity(str, Enum):
    """Fire alarm severity levels."""
    FIRE = "fire"
    PRE_ALARM = "pre_alarm"
    FAULT = "fault"
    SUPERVISORY = "supervisory"


class DamperStatusEnum(str, Enum):
    """Smoke damper status values."""
    OPEN = "open"
    CLOSED = "closed"
    TRANSIT = "transit"
    FAULT = "fault"
    UNKNOWN = "unknown"


class FanStatus(str, Enum):
    """Pressurization fan status values."""
    OFF = "off"
    RUNNING = "running"
    FAULT = "fault"


class PanelStatus(str, Enum):
    """Fire alarm panel status."""
    NORMAL = "normal"
    ALARM = "alarm"
    FAULT = "fault"
    DISABLED = "disabled"


class HealthStatus(str, Enum):
    """Overall system health status."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    CRITICAL = "critical"


class CauseEffectTargetType(str, Enum):
    """Target types for cause-effect matrix."""
    HVAC = "hvac"
    DAMPER = "damper"
    PRESSURIZATION = "pressurization"
    EXHAUST = "exhaust"


# --- Models ---

class FireZone(BaseModel):
    """Fire zone definition with detector counts."""
    zone_id: str
    zone_name: str
    floor: str
    zone_type: FireZoneType
    smoke_detectors: int = 0
    heat_detectors: int = 0
    beam_detectors: int = 0
    manual_call_points: int = 0


class FireAlarm(BaseModel):
    """Active or historical fire alarm event."""
    alarm_id: str
    zone_id: str
    alarm_type: AlarmType
    severity: AlarmSeverity
    description: str = ""
    acknowledged: bool = False
    acknowledged_by: Optional[str] = None
    acknowledged_at: Optional[datetime] = None
    cleared: bool = False
    cleared_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class DamperStatus(BaseModel):
    """Smoke damper position and health status."""
    damper_id: str
    equipment_id: Optional[str] = None
    zone_id: Optional[str] = None
    floor: str = ""
    position: int = 100  # 0-100, 100 = fully open
    target_position: int = 100
    status: DamperStatusEnum = DamperStatusEnum.OPEN
    last_tested: Optional[datetime] = None


class StairwellPressure(BaseModel):
    """Stairwell pressurization fan and pressure readings."""
    stairwell_id: str
    floor: str = ""
    current_pressure_pa: float = 0.0
    target_pressure_pa: float = 50.0
    fan_status: FanStatus = FanStatus.OFF
    fan_speed_pct: int = 0


class CauseEffectEffect(BaseModel):
    """Single effect action in the cause-effect matrix."""
    target_type: CauseEffectTargetType
    target_id: str
    action: str
    delay_seconds: int = 0
    priority: int = 1


class CauseEffectEntry(BaseModel):
    """Cause-effect matrix entry mapping triggers to actions."""
    trigger_zone: str
    trigger_type: str
    effects: List[CauseEffectEffect] = []


class FireSystemStatus(BaseModel):
    """Aggregate fire system status."""
    panel_status: PanelStatus = PanelStatus.NORMAL
    active_alarms: List[FireAlarm] = []
    zone_count: int = 0
    damper_count: int = 0
    all_dampers_healthy: bool = True
    pressurization_ok: bool = True
    battery_voltage: float = 27.6
    last_test_date: Optional[str] = None


class FireSystemHealth(BaseModel):
    """Fire system health summary."""
    panel_comms: str = "ok"  # ok, fault
    battery_status: str = "ok"  # ok, low, critical
    detector_faults: int = 0
    damper_faults: int = 0
    overall_health: HealthStatus = HealthStatus.HEALTHY
