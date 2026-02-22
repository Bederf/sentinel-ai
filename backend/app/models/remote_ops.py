"""Remote Operations Models - Authorization and diagnostic models for remote monitoring.

Phase 59: Remote Operations
Enables field technicians and dispatchers to check building status remotely
before dispatching, eliminating up to 50% of unnecessary callouts.
"""

from enum import IntEnum
from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field


class AuthorizationLevel(IntEnum):
    """4-level authorization model for remote operations.

    Higher levels include all permissions of lower levels.
    """

    VIEW_ONLY = 1  # Can view building status and readings
    OPERATOR = 2  # Can run diagnostics and assess dispatch need
    TECHNICIAN = 3  # Can adjust setpoints and override schedules
    ENGINEER = 4  # Can start/stop equipment, reset faults, fire panel reset


class RemoteCommandType(str):
    """Command types that can be executed remotely."""

    STATUS_CHECK = "status_check"
    SETPOINT_ADJUST = "setpoint_adjust"
    SCHEDULE_OVERRIDE = "schedule_override"
    EQUIPMENT_START_STOP = "equipment_start_stop"
    FAULT_RESET = "fault_reset"
    FIRE_PANEL_RESET = "fire_panel_reset"
    DOOR_UNLOCK = "door_unlock"


# Command type to minimum authorization level mapping
COMMAND_AUTHORIZATION: Dict[str, AuthorizationLevel] = {
    "status_check": AuthorizationLevel.VIEW_ONLY,
    "setpoint_adjust": AuthorizationLevel.TECHNICIAN,
    "schedule_override": AuthorizationLevel.TECHNICIAN,
    "equipment_start_stop": AuthorizationLevel.ENGINEER,
    "fault_reset": AuthorizationLevel.ENGINEER,
    "fire_panel_reset": AuthorizationLevel.ENGINEER,
    "door_unlock": AuthorizationLevel.OPERATOR,
}


class RemoteCommand(BaseModel):
    """A remote command with authorization requirements."""

    command_type: str
    required_level: AuthorizationLevel
    description: Optional[str] = None

    @classmethod
    def from_command_type(cls, command_type: str) -> "RemoteCommand":
        """Create a RemoteCommand from a command type string."""
        level = COMMAND_AUTHORIZATION.get(command_type, AuthorizationLevel.ENGINEER)
        return cls(
            command_type=command_type, required_level=level, description=f"Remote {command_type.replace('_', ' ')}"
        )


class RemoteDiagnosticRequest(BaseModel):
    """Request for a remote diagnostic on equipment."""

    equipment_id: str
    diagnostic_type: str = Field(
        default="quick_status", description="Type of diagnostic: quick_status, full_diagnostic, trend_analysis"
    )


class RemoteDiagnosticReport(BaseModel):
    """Report from a remote diagnostic assessment."""

    equipment_id: str
    timestamp: datetime = Field(default_factory=datetime.now)
    diagnostic_type: str
    status_summary: str
    readings: Dict[str, Any] = Field(default_factory=dict)
    anomalies: List[str] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)
    requires_dispatch: bool = False
    dispatch_reason: Optional[str] = None
    safety_status: Optional[Dict[str, Any]] = None


class RemoteSessionAction(BaseModel):
    """A single action within a remote session."""

    action_type: str
    target: Optional[str] = None
    details: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.now)
    result: Optional[str] = None


class RemoteSessionLog(BaseModel):
    """Log of a remote monitoring session."""

    session_id: str
    user_id: str
    user_role: str
    actions: List[RemoteSessionAction] = Field(default_factory=list)
    started_at: datetime = Field(default_factory=datetime.now)
    ended_at: Optional[datetime] = None


class DispatchDecision(BaseModel):
    """Decision on whether to dispatch a technician."""

    dispatch_required: bool
    reason: str
    urgency: str = Field(default="low", description="Urgency level: critical, high, medium, low")
    estimated_onsite_time_minutes: int = 0
    remote_actions_taken: List[str] = Field(default_factory=list)
    bundled_tasks: List[str] = Field(default_factory=list)
    equipment_id: Optional[str] = None
    assessed_at: datetime = Field(default_factory=datetime.now)
