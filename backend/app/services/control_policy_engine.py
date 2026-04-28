"""Control Policy Engine — Central enforcement for all AI control actions.

Every control action MUST pass through this engine. The LLM proposes,
the policy engine decides.

Architecture:
    LLM Reasoning -> ControlPolicyEngine -> TierRouting -> Safety -> Approval -> Execution

Phase 145: Control Policy Engine.
"""

from __future__ import annotations

import json
import logging
import time
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.config.settings import IngestionMode, settings
from app.models.control_policy import (
    AssetControlPolicy,
    CommandEnvelope,
    ControlMode,
)

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data"
POLICIES_FILE = DATA_DIR / "control_policies.json"

# Write tools that should be gated by control mode
WRITE_TOOL_NAMES = frozenset(
    {
        "write_device_point",
        "set_hvac_setpoint",
        "set_lighting_level",
        "start_equipment",
        "stop_equipment",
        "dispatch_bess",
        "execute_control_action",
        "approve_recommendation",
    }
)

# Read-only tools available in all modes
READONLY_TOOL_NAMES = frozenset(
    {
        "get_equipment_status",
        "get_hybrid_context",
        "search_documents",
        "get_alerts_and_anomalies",
        "get_system_status",
        "get_telemetry",
        "list_equipment",
        "get_work_orders",
    }
)


class ControlPolicyEngine:
    """Central policy enforcement for all control actions.

    Singleton service that:
    - Determines current control mode from settings
    - Gates tool availability by mode
    - Validates actions against per-asset policies
    - Wraps actions in CommandEnvelopes for audit
    - Enforces rate limits, setpoint limits, ramp rates
    """

    _instance: ControlPolicyEngine | None = None

    def __init__(self) -> None:
        self._policies: dict[str, AssetControlPolicy] = {}
        self._active_envelopes: dict[str, CommandEnvelope] = {}
        self._hourly_counts: dict[str, list[float]] = defaultdict(list)
        self._load_policies()

    # -----------------------------------------------------------------
    # Control mode
    # -----------------------------------------------------------------

    def get_control_mode(self) -> ControlMode:
        """Determine current control mode from settings.

        Maps IngestionMode to ControlMode:
        - SIMULATION -> RECOMMEND
        - SHADOW_LIVE -> SUPERVISED
        - LIVE_CONTROL -> FULL_CONTROL
        """
        mode = settings.resolved_ingestion_mode
        control_tier = getattr(settings, "control_tier", "supervised")

        if mode == IngestionMode.SIMULATION:
            return ControlMode.RECOMMEND
        elif mode == IngestionMode.SHADOW_LIVE:
            return ControlMode.SUPERVISED
        elif mode == IngestionMode.LIVE_CONTROL:
            if control_tier == "monitor":
                return ControlMode.RECOMMEND
            elif control_tier == "auto_execute":
                return ControlMode.FULL_CONTROL
            else:
                return ControlMode.SUPERVISED
        return ControlMode.RECOMMEND

    def get_available_tools(self) -> list[str]:
        """Return tool names available in current control mode.

        RECOMMEND: Read-only tools only
        SUPERVISED/FULL_CONTROL: Read-only + write tools
        """
        mode = self.get_control_mode()
        tools = list(READONLY_TOOL_NAMES)
        if mode != ControlMode.RECOMMEND:
            tools.extend(WRITE_TOOL_NAMES)
        return sorted(tools)

    def is_write_allowed(self) -> bool:
        """Check if write operations are allowed in current mode."""
        return self.get_control_mode() != ControlMode.RECOMMEND

    # -----------------------------------------------------------------
    # Policy management
    # -----------------------------------------------------------------

    def _load_policies(self) -> None:
        """Load asset control policies from JSON file."""
        try:
            if POLICIES_FILE.exists():
                with open(POLICIES_FILE) as f:
                    data = json.load(f)
                for eq_type, policy_data in data.items():
                    policy_data.setdefault("equipment_type", eq_type)
                    self._policies[eq_type] = AssetControlPolicy.from_dict(policy_data)
                logger.info("Loaded %d asset control policies", len(self._policies))
            else:
                logger.warning("No control_policies.json found at %s", POLICIES_FILE)
        except Exception as e:
            logger.error("Failed to load control policies: %s", e)

    def get_policy(self, equipment_type: str) -> AssetControlPolicy | None:
        """Get control policy for an equipment type."""
        return self._policies.get(equipment_type.upper())

    def register_policy(self, policy: AssetControlPolicy) -> None:
        """Register or update an asset control policy."""
        self._policies[policy.equipment_type.upper()] = policy

    def list_policies(self) -> list[AssetControlPolicy]:
        """List all registered policies."""
        return list(self._policies.values())

    # -----------------------------------------------------------------
    # Action evaluation
    # -----------------------------------------------------------------

    async def evaluate_action(
        self,
        target_equipment: str,
        site_id: str,
        proposed_action: dict[str, Any],
        reason: str = "",
        created_by: str = "ai_optimizer",
        correlation_id: str | None = None,
    ) -> CommandEnvelope:
        """Evaluate a proposed action against all policy checks.

        Returns a CommandEnvelope with all checks completed.
        The caller inspects policy_check_passed to decide whether to proceed.

        Args:
            target_equipment: Equipment code (e.g., "S002-CHILLER-B1-001")
            site_id: Site identifier
            proposed_action: Dict with "point", "value", and optionally "action_type"
            reason: Why this action is proposed
            created_by: Who proposed it
            correlation_id: Link to event chain

        Returns:
            CommandEnvelope with policy and safety check results
        """
        mode = self.get_control_mode()

        envelope = CommandEnvelope(
            proposed_action=proposed_action,
            target_equipment=target_equipment,
            site_id=site_id,
            control_mode=mode,
            reason=reason,
            created_by=created_by,
            correlation_id=correlation_id,
        )

        # Step 1: Mode check
        if mode == ControlMode.RECOMMEND:
            envelope.policy_check_passed = False
            envelope.policy_check_details = {
                "blocked_by": "recommend_mode",
                "reason": "Write operations not allowed in recommend mode",
            }
            envelope.requires_approval = True
            return envelope

        # Step 2: Extract equipment type
        eq_type = self._extract_equipment_type(target_equipment)
        policy = self.get_policy(eq_type)

        checks: dict[str, Any] = {"equipment_type": eq_type, "control_mode": mode.value}

        # Step 3: Setpoint limits
        if policy:
            point_name = proposed_action.get("point", "")
            value = proposed_action.get("value")
            limits = policy.setpoint_limits.get(point_name)
            if limits and value is not None:
                try:
                    numeric_value = float(value)
                    if numeric_value < limits["min"] or numeric_value > limits["max"]:
                        checks["setpoint_violation"] = {
                            "point": point_name,
                            "value": numeric_value,
                            "min": limits["min"],
                            "max": limits["max"],
                        }
                        envelope.policy_check_passed = False
                        envelope.policy_check_details = checks
                        return envelope
                except (TypeError, ValueError):
                    pass
            checks["setpoint_check"] = "passed"

            # Step 4: Ramp rate limits
            ramp_limit = policy.ramp_limits.get(point_name)
            if ramp_limit is not None and value is not None:
                previous = self._get_previous_value(target_equipment, point_name)
                if previous is not None:
                    try:
                        delta = abs(float(value) - float(previous))
                        if delta > ramp_limit:
                            checks["ramp_violation"] = {
                                "point": point_name,
                                "delta": delta,
                                "max_ramp": ramp_limit,
                                "previous": previous,
                            }
                            envelope.policy_check_passed = False
                            envelope.policy_check_details = checks
                            return envelope
                    except (TypeError, ValueError):
                        pass
            checks["ramp_check"] = "passed"

            # Step 5: Lockout windows
            if self._in_lockout_window(policy):
                checks["lockout_violation"] = "Current time is within lockout window"
                envelope.policy_check_passed = False
                envelope.policy_check_details = checks
                return envelope
            checks["lockout_check"] = "passed"

            # Step 6: Rate limiting
            if not self._check_rate_limit(target_equipment, policy):
                checks["rate_limit_violation"] = {
                    "max_per_hour": policy.max_auto_per_hour,
                    "message": "Rate limit exceeded for this equipment",
                }
                envelope.policy_check_passed = False
                envelope.policy_check_details = checks
                return envelope
            checks["rate_limit_check"] = "passed"

        # Step 7: Generate rollback command
        envelope.previous_state = await self._capture_previous_state(target_equipment, proposed_action)
        envelope.rollback_command = self._generate_rollback(target_equipment, proposed_action, envelope.previous_state)

        # Step 8: Approval requirements
        if mode == ControlMode.SUPERVISED:
            envelope.requires_approval = True
        elif mode == ControlMode.FULL_CONTROL:
            envelope.requires_approval = False
        else:
            envelope.requires_approval = True

        checks["all_checks"] = "passed"
        envelope.policy_check_passed = True
        envelope.policy_check_details = checks

        # Store active envelope
        self._active_envelopes[envelope.envelope_id] = envelope

        return envelope

    async def execute_envelope(self, envelope_id: str, approved_by: str | None = None) -> CommandEnvelope:
        """Execute a command envelope after all checks pass.

        Args:
            envelope_id: ID of the envelope to execute
            approved_by: Required in supervised mode

        Returns:
            Updated CommandEnvelope with execution results

        Raises:
            ValueError: If envelope not found, checks failed, or approval missing
        """
        envelope = self._active_envelopes.get(envelope_id)
        if not envelope:
            raise ValueError(f"Envelope {envelope_id} not found")

        if not envelope.policy_check_passed:
            raise ValueError("Cannot execute: policy check failed")

        if envelope.executed:
            raise ValueError("Envelope already executed")

        if envelope.control_mode == ControlMode.RECOMMEND:
            raise ValueError("Cannot execute in recommend mode")

        if envelope.requires_approval and not approved_by:
            raise ValueError("Approval required in supervised mode")

        if approved_by:
            envelope.approved_by = approved_by
            envelope.approved_at = datetime.now(UTC)

        # Record rate limit
        self._record_execution(envelope.target_equipment)

        envelope.executed = True
        envelope.executed_at = datetime.now(UTC)
        envelope.execution_result = {"status": "executed", "envelope_id": envelope_id}

        logger.info(
            "Executed envelope %s for %s (mode=%s, approved_by=%s)",
            envelope_id,
            envelope.target_equipment,
            envelope.control_mode.value,
            approved_by,
        )

        return envelope

    async def rollback_envelope(self, envelope_id: str, reason: str) -> CommandEnvelope:
        """Roll back a previously executed command.

        Args:
            envelope_id: ID of the envelope to roll back
            reason: Why the rollback is needed

        Returns:
            Updated CommandEnvelope

        Raises:
            ValueError: If envelope not found or not executed
        """
        envelope = self._active_envelopes.get(envelope_id)
        if not envelope:
            raise ValueError(f"Envelope {envelope_id} not found")
        if not envelope.executed:
            raise ValueError("Cannot rollback: envelope not yet executed")
        if envelope.rolled_back:
            raise ValueError("Envelope already rolled back")

        envelope.rolled_back = True
        envelope.rolled_back_at = datetime.now(UTC)
        envelope.execution_result = envelope.execution_result or {}
        envelope.execution_result["rollback_reason"] = reason

        logger.info("Rolled back envelope %s: %s", envelope_id, reason)
        return envelope

    def get_active_envelopes(self, site_id: str | None = None) -> list[CommandEnvelope]:
        """Get active (executed, not rolled back) command envelopes."""
        results = []
        for env in self._active_envelopes.values():
            if env.executed and not env.rolled_back and (site_id is None or env.site_id == site_id):
                results.append(env)
        return results

    # -----------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------

    def _extract_equipment_type(self, equipment_id: str) -> str:
        """Extract equipment type from equipment code.

        S002-CHILLER-B1-001 -> CHILLER
        S002-FCU-101 -> FCU
        """
        parts = equipment_id.split("-")
        if len(parts) >= 2:
            return parts[1].upper()
        return "UNKNOWN"

    def _get_previous_value(self, equipment_id: str, point_name: str) -> float | None:
        """Get previous value for ramp rate checking.

        Checks active envelopes for the most recent executed action on this point.
        """
        for env in reversed(list(self._active_envelopes.values())):
            if (
                env.target_equipment == equipment_id
                and env.executed
                and not env.rolled_back
                and env.proposed_action.get("point") == point_name
            ):
                return env.proposed_action.get("value")
        return None

    def _in_lockout_window(self, policy: AssetControlPolicy) -> bool:
        """Check if current time is within any lockout window."""
        if not policy.lockout_windows:
            return False
        now = datetime.now(UTC)
        current_time = now.strftime("%H:%M")
        for window in policy.lockout_windows:
            start = window.get("start", "")
            end = window.get("end", "")
            if start and end:
                if start <= end:
                    if start <= current_time <= end:
                        return True
                else:  # Wraps midnight
                    if current_time >= start or current_time <= end:
                        return True
        return False

    def _check_rate_limit(self, equipment_id: str, policy: AssetControlPolicy) -> bool:
        """Check hourly rate limit for equipment."""
        now = time.monotonic()
        hour_ago = now - 3600
        key = equipment_id

        # Clean old entries
        self._hourly_counts[key] = [t for t in self._hourly_counts[key] if t > hour_ago]

        return len(self._hourly_counts[key]) < policy.max_auto_per_hour

    def _record_execution(self, equipment_id: str) -> None:
        """Record an execution for rate limiting."""
        self._hourly_counts[equipment_id].append(time.monotonic())

    async def _capture_previous_state(
        self, equipment_id: str, proposed_action: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Capture current state before executing action."""
        try:
            from app.database.repositories.equipment_repository import get_equipment_repository

            repo = get_equipment_repository()
            equipment = await repo.get_by_code(equipment_id)
            if equipment and equipment.get("operating_data"):
                point_name = proposed_action.get("point", "")
                op_data = equipment["operating_data"]
                current_value = op_data.get(point_name)
                return {
                    "point": point_name,
                    "value": current_value,
                    "captured_at": datetime.now(UTC).isoformat(),
                }
        except Exception as e:
            logger.debug("Could not capture previous state for %s: %s", equipment_id, e)
        return None

    def _generate_rollback(
        self,
        equipment_id: str,
        proposed_action: dict[str, Any],
        previous_state: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        """Generate a rollback command from the previous state."""
        if not previous_state or previous_state.get("value") is None:
            return None
        return {
            "equipment_id": equipment_id,
            "point": previous_state["point"],
            "value": previous_state["value"],
            "reason": "rollback",
        }


# -----------------------------------------------------------------
# Singleton
# -----------------------------------------------------------------

_engine: ControlPolicyEngine | None = None


def get_control_policy_engine() -> ControlPolicyEngine:
    """Get or create singleton ControlPolicyEngine."""
    global _engine
    if _engine is None:
        _engine = ControlPolicyEngine()
    return _engine


def reset_control_policy_engine() -> None:
    """Reset singleton for testing."""
    global _engine
    _engine = None
