"""Models for PARASITE decision audit records.

Complete schema for parasite_decisions table. Every Tier 1/2/3 decision
gets one record that is enriched through its lifecycle: routing -> execution
-> COV verification -> outcome measurement -> optional rollback.

Designed for post-hoc audit and debugging without opening logs.
"""

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class OperatingMode(str, Enum):
    """System operating mode at decision time."""

    SIMULATION = "simulation"
    SHADOW_LIVE = "shadow_live"
    LIVE_CONTROL = "live_control"


class GateStatus(str, Enum):
    """Quality gate evaluation result."""

    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


class EnforcementAction(str, Enum):
    """What the system did with the gate result."""

    NORMAL = "normal"
    CAP_CONFIDENCE = "cap_confidence"
    SUPPRESS_TIER3 = "suppress_tier3"
    BLOCK_WRITES = "block_writes"


class SafetyResult(str, Enum):
    """Single-flag outcome of safety check."""

    ALLOWED = "allowed"
    BLOCKED = "blocked"
    ALARMED = "alarmed"


class Actor(str, Enum):
    """Who or what triggered the decision."""

    AUTO_TIER3 = "auto_tier3"
    HUMAN_TIER2 = "human_tier2"
    API = "api"
    SYSTEM = "system"


class RejectionCategory(str, Enum):
    """Stable label for why a decision was rejected."""

    SAFETY_BLOCK = "safety_block"
    GATE_BLOCK = "gate_block"
    CONFIDENCE_CAP = "confidence_cap"
    RATE_LIMITED = "rate_limited"
    USER_REJECTED = "user_rejected"
    VALIDATION_ERROR = "validation_error"


class WriteStatus(str, Enum):
    """Status of the device write attempt."""

    SUCCESS = "success"
    FAILED = "failed"
    REJECTED = "rejected"
    SKIPPED = "skipped"
    BLOCKED = "blocked"  # AEGIS: write not attempted, awaiting ops CONFIRM


def _safe_json_value(value: Any) -> Any:
    """Ensure a value is JSON-serializable.

    Raises TypeError if value is a coroutine, mock, or other
    non-serializable type. This prevents test artifacts from
    leaking into persistent storage.
    """
    import asyncio
    import inspect

    # Block coroutines
    if asyncio.iscoroutine(value) or inspect.iscoroutinefunction(value):
        raise TypeError(f"Cannot serialize coroutine to parasite_decisions: {type(value).__name__}")

    # Block mock objects
    type_name = type(value).__name__
    if "Mock" in type_name or "MagicMock" in type_name or "AsyncMock" in type_name:
        raise TypeError(f"Cannot serialize mock object to parasite_decisions: {type_name}")

    # Block anything that isn't JSON-serializable
    if value is not None and not isinstance(value, (str, int, float, bool, list, dict)):
        try:
            json.dumps(value, default=str)
        except (TypeError, ValueError) as e:
            raise TypeError(f"Cannot serialize {type(value).__name__} to parasite_decisions: {e}") from e

    return value


class SafetyRuleHit:
    """A safety rule that was triggered during evaluation."""

    __slots__ = ("rule_id", "severity")

    def __init__(self, rule_id: str, severity: str):
        self.rule_id = rule_id
        self.severity = severity

    def to_dict(self) -> Dict[str, str]:
        return {"rule_id": self.rule_id, "severity": self.severity}

    @classmethod
    def from_dict(cls, data: Dict[str, str]) -> "SafetyRuleHit":
        return cls(rule_id=data["rule_id"], severity=data["severity"])


@dataclass
class ParasiteDecision:
    """Complete audit record for a PARASITE decision.

    Fields are grouped by lifecycle stage:
    - Identity: id, correlation_id, recommendation_id, site_id, equipment_code, device_id
    - Decision context: mode, gate_status, enforcement, gate_snapshot_id
    - Safety context: safety_check_version, safety_rules_evaluated, safety_rules_triggered, safety_result
    - Execution: actor, approval_id, command_id, tier, decision_type, write_status,
                 write_attempt_count, point_name, control_point (deprecated alias)
    - Values: original_value, target_value, actual_value
    - COV: cov_verified, cov_tolerance, cov_latency_ms
    - Timing: device_response_latency_ms, created_at, updated_at
    - Outcome: outcome, outcome_matched_prediction, outcome_measured_at,
               predicted_impact, measured_impact
    - Rollback: rolled_back, rollback_reason, rollback_at
    - Classification: confidence_score, contributing_factors, decision_details,
                      rejection_category
    """

    # --- Identity ---
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    correlation_id: Optional[str] = None
    recommendation_id: Optional[str] = None
    site_id: str = ""  # Must be non-empty in live_control
    equipment_code: Optional[str] = None
    device_id: Optional[str] = None  # Canonical control identity

    # --- Decision context (A) ---
    mode: Optional[str] = None  # OperatingMode value
    gate_status: Optional[str] = None  # GateStatus value
    enforcement: Optional[str] = None  # EnforcementAction value
    gate_snapshot_id: Optional[str] = None  # Links to exact 14-metric snapshot

    # --- Safety context (B) ---
    safety_check_version: Optional[str] = None  # Ruleset hash or version
    safety_rules_evaluated: List[str] = field(default_factory=list)  # Rule IDs checked
    safety_rules_triggered: List[Dict[str, str]] = field(default_factory=list)  # [{rule_id, severity}]
    safety_result: Optional[str] = None  # SafetyResult value

    # --- Execution context (C) ---
    actor: Optional[str] = None  # Actor value
    approval_id: Optional[str] = None  # Links tier2 to UI approval record
    command_id: Optional[str] = None  # Links set_value/read_value calls
    tier: Optional[str] = None  # tier1, tier2, tier3
    decision_type: Optional[str] = None  # tier2_approved, tier3_auto_execute, etc.
    write_status: Optional[str] = None  # WriteStatus value
    write_attempt_count: int = 1
    failure_reason: Optional[str] = None

    # --- Target identity (D) ---
    point_name: Optional[str] = None  # Canonical name
    control_point: Optional[str] = None  # Deprecated alias for point_name

    # --- Values ---
    original_value: Any = None  # Pre-write reading (JSON-typed)
    target_value: Any = None  # Proposed value (JSON-typed)
    actual_value: Any = None  # Post-write read-back (JSON-typed)

    # --- COV verification ---
    cov_verified: Optional[bool] = None
    cov_tolerance: Any = None  # Float or dict of per-point tolerances
    cov_latency_ms: Optional[int] = None

    # --- Timing ---
    device_response_latency_ms: Optional[int] = None
    confidence_score: Optional[float] = None
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    # --- Outcome and learning (E) ---
    outcome: Optional[Dict[str, Any]] = None
    outcome_matched_prediction: Optional[bool] = None
    outcome_measured_at: Optional[str] = None
    predicted_impact: Optional[Dict[str, Any]] = None  # {energy_kwh, comfort_delta, runtime_delta, cost}
    measured_impact: Optional[Dict[str, Any]] = None  # Same keys as predicted_impact

    # --- Rollback ---
    rolled_back: bool = False
    rollback_reason: Optional[str] = None
    rollback_at: Optional[str] = None

    # --- Classification ---
    contributing_factors: Optional[Dict[str, Any]] = None
    decision_details: Optional[Dict[str, Any]] = None
    rejection_category: Optional[str] = None  # RejectionCategory value

    # --- Routing provenance ---
    routing_source: Optional[str] = None  # recommendation_graph | optimization_api

    def __post_init__(self):
        """Normalize point_name / control_point."""
        # point_name is canonical; control_point is deprecated alias
        if self.point_name is None and self.control_point is not None:
            self.point_name = self.control_point
        elif self.control_point is None and self.point_name is not None:
            self.control_point = self.point_name

    def validate_for_persistence(self) -> None:
        """Check that critical values are JSON-serializable.

        Raises TypeError if any value would corrupt the store.
        Call this before writing to Supabase or JSON.
        """
        _safe_json_value(self.original_value)
        _safe_json_value(self.target_value)
        _safe_json_value(self.actual_value)
        _safe_json_value(self.cov_tolerance)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for persistence.

        Validates serialization safety before returning.
        """
        self.validate_for_persistence()
        d = {
            "id": self.id,
            "correlation_id": self.correlation_id,
            "recommendation_id": self.recommendation_id,
            "site_id": self.site_id,
            "equipment_code": self.equipment_code,
            "device_id": self.device_id,
            # Decision context
            "mode": self.mode,
            "gate_status": self.gate_status,
            "enforcement": self.enforcement,
            "gate_snapshot_id": self.gate_snapshot_id,
            # Safety context
            "safety_check_version": self.safety_check_version,
            "safety_rules_evaluated": self.safety_rules_evaluated,
            "safety_rules_triggered": self.safety_rules_triggered,
            "safety_result": self.safety_result,
            # Execution context
            "actor": self.actor,
            "approval_id": self.approval_id,
            "command_id": self.command_id,
            "tier": self.tier,
            "decision_type": self.decision_type,
            "write_status": self.write_status,
            "write_attempt_count": self.write_attempt_count,
            "failure_reason": self.failure_reason,
            # Target identity
            "point_name": self.point_name,
            "control_point": self.control_point,
            # Values
            "original_value": self.original_value,
            "target_value": self.target_value,
            "actual_value": self.actual_value,
            # COV
            "cov_verified": self.cov_verified,
            "cov_tolerance": self.cov_tolerance,
            "cov_latency_ms": self.cov_latency_ms,
            # Timing
            "device_response_latency_ms": self.device_response_latency_ms,
            "confidence_score": self.confidence_score,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            # Outcome
            "outcome": self.outcome,
            "outcome_matched_prediction": self.outcome_matched_prediction,
            "outcome_measured_at": self.outcome_measured_at,
            "predicted_impact": self.predicted_impact,
            "measured_impact": self.measured_impact,
            # Rollback
            "rolled_back": self.rolled_back,
            "rollback_reason": self.rollback_reason,
            "rollback_at": self.rollback_at,
            # Classification
            "contributing_factors": self.contributing_factors,
            "decision_details": self.decision_details,
            "rejection_category": self.rejection_category,
        }
        # Strip None values for cleaner storage
        return {k: v for k, v in d.items() if v is not None}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ParasiteDecision":
        """Create from dictionary (Supabase row or JSON record)."""
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            correlation_id=data.get("correlation_id"),
            recommendation_id=data.get("recommendation_id"),
            site_id=data.get("site_id", ""),
            equipment_code=data.get("equipment_code"),
            device_id=data.get("device_id"),
            mode=data.get("mode"),
            gate_status=data.get("gate_status"),
            enforcement=data.get("enforcement"),
            gate_snapshot_id=data.get("gate_snapshot_id"),
            safety_check_version=data.get("safety_check_version"),
            safety_rules_evaluated=data.get("safety_rules_evaluated", []),
            safety_rules_triggered=data.get("safety_rules_triggered", []),
            safety_result=data.get("safety_result"),
            actor=data.get("actor"),
            approval_id=data.get("approval_id"),
            command_id=data.get("command_id"),
            tier=data.get("tier"),
            decision_type=data.get("decision_type"),
            write_status=data.get("write_status"),
            write_attempt_count=data.get("write_attempt_count", 1),
            failure_reason=data.get("failure_reason"),
            point_name=data.get("point_name"),
            control_point=data.get("control_point"),
            original_value=data.get("original_value"),
            target_value=data.get("target_value"),
            actual_value=data.get("actual_value"),
            cov_verified=data.get("cov_verified"),
            cov_tolerance=data.get("cov_tolerance"),
            cov_latency_ms=data.get("cov_latency_ms"),
            device_response_latency_ms=data.get("device_response_latency_ms"),
            confidence_score=data.get("confidence_score"),
            created_at=data.get("created_at", datetime.utcnow().isoformat()),
            updated_at=data.get("updated_at", datetime.utcnow().isoformat()),
            outcome=data.get("outcome"),
            outcome_matched_prediction=data.get("outcome_matched_prediction"),
            outcome_measured_at=data.get("outcome_measured_at"),
            predicted_impact=data.get("predicted_impact"),
            measured_impact=data.get("measured_impact"),
            rolled_back=data.get("rolled_back", False),
            rollback_reason=data.get("rollback_reason"),
            rollback_at=data.get("rollback_at"),
            contributing_factors=data.get("contributing_factors"),
            decision_details=data.get("decision_details"),
            rejection_category=data.get("rejection_category"),
        )

    @classmethod
    def from_legacy_dict(cls, data: Dict[str, Any]) -> "ParasiteDecision":
        """Create from legacy format (existing record_decision call sites).

        Maps old field conventions to new canonical names.
        Legacy callers pass raw dicts without mode/gate/safety context.
        """
        decision = cls.from_dict(data)
        # Ensure point_name/control_point sync from legacy
        if decision.point_name is None and "control_point" in data:
            decision.point_name = data["control_point"]
            decision.control_point = data["control_point"]
        return decision
