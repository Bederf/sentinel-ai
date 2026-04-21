"""Control policy models for the Control Policy Engine.

Defines control modes, command envelopes, and per-asset control policies.
Every AI control action must pass through these structures.

Phase 145: Control Policy Engine.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class ControlMode(StrEnum):
    """Operating control mode — determines what the AI can do."""

    RECOMMEND = "recommend"  # Advisory only, no writes
    SUPERVISED = "supervised"  # Writes require human approval
    FULL_CONTROL = "full_control"  # Auto-execute within policy limits


@dataclass
class AssetControlPolicy:
    """Per-equipment-type control constraints.

    Loaded from control_policies.json or Supabase.
    """

    equipment_type: str  # "CHILLER", "AHU", "BESS", etc.

    # Setpoint limits: point_name -> {min, max}
    setpoint_limits: dict[str, dict[str, float]] = field(default_factory=dict)

    # Ramp rate limits: point_name -> max change per 10 minutes
    ramp_limits: dict[str, float] = field(default_factory=dict)

    # Lockout windows: [{"start": "22:00", "end": "06:00"}]
    lockout_windows: list[dict[str, str]] = field(default_factory=list)

    # Dependencies: action -> [required_conditions]
    dependencies: dict[str, list[str]] = field(default_factory=dict)

    # Rate limiting
    max_auto_per_hour: int = 5

    # Kill switch
    kill_switch_enabled: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "equipment_type": self.equipment_type,
            "setpoint_limits": self.setpoint_limits,
            "ramp_limits": self.ramp_limits,
            "lockout_windows": self.lockout_windows,
            "dependencies": self.dependencies,
            "max_auto_per_hour": self.max_auto_per_hour,
            "kill_switch_enabled": self.kill_switch_enabled,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AssetControlPolicy:
        return cls(
            equipment_type=data.get("equipment_type", "UNKNOWN"),
            setpoint_limits=data.get("setpoint_limits", {}),
            ramp_limits=data.get("ramp_limits", {}),
            lockout_windows=data.get("lockout_windows", []),
            dependencies=data.get("dependencies", {}),
            max_auto_per_hour=data.get("max_auto_per_hour", 5),
            kill_switch_enabled=data.get("kill_switch_enabled", True),
        )


def _now_utc() -> datetime:
    return datetime.now(UTC)


@dataclass
class CommandEnvelope:
    """Wraps every control action for traceability and reversibility.

    Guarantees: traceable, reversible, policy-checked.
    """

    envelope_id: str = field(default_factory=lambda: f"CMD-{uuid.uuid4().hex[:12]}")
    proposed_action: dict[str, Any] = field(default_factory=dict)
    target_equipment: str = ""
    site_id: str = ""
    control_mode: ControlMode = ControlMode.RECOMMEND

    # Policy check
    policy_check_passed: bool = False
    policy_check_details: dict[str, Any] = field(default_factory=dict)

    # Safety check
    safety_check_passed: bool = False
    safety_check_details: dict[str, Any] = field(default_factory=dict)

    # State for rollback
    previous_state: dict[str, Any] | None = None
    rollback_command: dict[str, Any] | None = None
    rollback_timeout_seconds: int = 3600

    # Approval
    requires_approval: bool = True
    approved_by: str | None = None
    approved_at: datetime | None = None

    # Execution
    executed: bool = False
    executed_at: datetime | None = None
    execution_result: dict[str, Any] | None = None
    rolled_back: bool = False
    rolled_back_at: datetime | None = None

    # Audit
    created_at: datetime = field(default_factory=_now_utc)
    created_by: str = "ai_optimizer"
    reason: str = ""
    correlation_id: str | None = None
    tier_routing_result: str | None = None
    quality_gate_status: str | None = None

    def to_dict(self) -> dict[str, Any]:
        def _dt(v: datetime | None) -> str | None:
            return v.isoformat() if isinstance(v, datetime) else v

        return {
            "envelope_id": self.envelope_id,
            "proposed_action": self.proposed_action,
            "target_equipment": self.target_equipment,
            "site_id": self.site_id,
            "control_mode": self.control_mode.value,
            "policy_check_passed": self.policy_check_passed,
            "policy_check_details": self.policy_check_details,
            "safety_check_passed": self.safety_check_passed,
            "safety_check_details": self.safety_check_details,
            "previous_state": self.previous_state,
            "rollback_command": self.rollback_command,
            "rollback_timeout_seconds": self.rollback_timeout_seconds,
            "requires_approval": self.requires_approval,
            "approved_by": self.approved_by,
            "approved_at": _dt(self.approved_at),
            "executed": self.executed,
            "executed_at": _dt(self.executed_at),
            "execution_result": self.execution_result,
            "rolled_back": self.rolled_back,
            "rolled_back_at": _dt(self.rolled_back_at),
            "created_at": _dt(self.created_at),
            "created_by": self.created_by,
            "reason": self.reason,
            "correlation_id": self.correlation_id,
            "tier_routing_result": self.tier_routing_result,
            "quality_gate_status": self.quality_gate_status,
        }
