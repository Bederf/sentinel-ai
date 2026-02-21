"""BESS Dispatch Engine -- Autonomous battery dispatch execution with constraints.

Implements real-time dispatch optimization that respects:
  - Temperature limits (charge if < 40°C, discharge if > 12°C)
  - Charge limits (min 20% reserve, max 95%)
  - Grid frequency (reduce discharge if > 50.3 Hz)
  - Ramp rates (max 5% Prated/min during LS, 10% normally)
  - Export limits (never > 50% Prated to distribution)
  - Load-shedding coordination (stages 1-8)

This module specializes in dispatch execution, constraint validation,
and load-shedding emergency response.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional, Any, Tuple

from app.services.solar_config_service import get_site_solar_config

logger = logging.getLogger(__name__)


# === Enums ===


class DispatchActionType(str, Enum):
    """Dispatch action types."""

    CHARGE = "charge"
    DISCHARGE = "discharge"
    IDLE = "idle"


class ConstraintType(str, Enum):
    """Constraint violation types."""

    TEMPERATURE_HIGH = "temperature_high"
    TEMPERATURE_LOW = "temperature_low"
    SOC_MIN = "soc_min"
    SOC_MAX = "soc_max"
    FREQUENCY_HIGH = "frequency_high"
    RAMP_RATE = "ramp_rate"
    EXPORT_LIMIT = "export_limit"
    LOAD_SHEDDING = "load_shedding"


# === Dataclass Models ===


@dataclass
class DispatchConstraint:
    """A constraint violation or limit applied."""

    constraint_type: str  # ConstraintType
    severity: str  # warning / block / alarm
    current_value: float
    limit_value: float
    message: str
    mitigation: str  # What action was taken

    def to_dict(self) -> Dict[str, Any]:
        return {
            "constraint_type": self.constraint_type,
            "severity": self.severity,
            "current_value": round(self.current_value, 2),
            "limit_value": round(self.limit_value, 2),
            "message": self.message,
            "mitigation": self.mitigation,
        }


@dataclass
class DispatchCommand:
    """A BESS dispatch command ready for execution."""

    site_id: str
    timestamp: str  # ISO timestamp
    action: str  # charge / discharge / idle
    requested_power_kw: float  # Requested power
    actual_power_kw: float  # Power after constraint limiting
    duration_minutes: int
    reason: str
    constraints_applied: List[DispatchConstraint] = field(default_factory=list)
    success: bool = True
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "site_id": self.site_id,
            "timestamp": self.timestamp,
            "action": self.action,
            "requested_power_kw": round(self.requested_power_kw, 0),
            "actual_power_kw": round(self.actual_power_kw, 0),
            "duration_minutes": self.duration_minutes,
            "reason": self.reason,
            "constraints_applied": [c.to_dict() for c in self.constraints_applied],
            "success": self.success,
            "error_message": self.error_message,
        }


@dataclass
class BESSState:
    """Current BESS state for constraint validation."""

    soc_pct: float  # 0-100 State of charge
    temperature_c: float  # °C
    power_kw: float  # Current power (positive = discharge)
    grid_frequency_hz: float  # Current grid frequency


# === BESS Dispatch Engine ===


class BESSDispatchEngine:
    """Autonomous BESS dispatch executor with multi-constraint safety system."""

    # BESS specifications (Site-002 LUNA2000-200KWH-2H1)
    BESS_CAPACITY_KWH = 500.0
    BESS_RATED_POWER_KW = 250.0

    # Operating constraints
    CHARGE_TEMP_MIN_C = 12.0
    CHARGE_TEMP_MAX_C = 40.0
    DISCHARGE_TEMP_MIN_C = 12.0
    DISCHARGE_TEMP_MAX_C = 44.0
    SOC_MIN_PCT = 20.0  # Reserve for emergency grid support
    SOC_MAX_PCT = 95.0
    SOC_LS_RESERVE_PCT = 80.0  # Charge to this before load shedding

    # Grid constraints (NRS 097)
    EXPORT_LIMIT_PCT = 50.0  # Max 50% Prated to distribution
    GRID_FREQUENCY_NORMAL_HZ = 50.0
    GRID_FREQUENCY_HIGH_THRESHOLD = 50.3  # Reduce discharge to avoid over-frequency

    # Ramp rate constraints
    RAMP_RATE_NORMAL_PCT_PER_MIN = 10.0  # 10% Prated per minute
    RAMP_RATE_LS_PCT_PER_MIN = 5.0  # 5% Prated per minute during LS

    def __init__(self):
        """Initialize dispatch engine."""
        self._last_power_kw = 0.0
        self._last_update_time = datetime.now(timezone.utc)

        # Override class defaults from site solar config
        try:
            cfg = get_site_solar_config("site-002")
            self.BESS_CAPACITY_KWH = cfg.bess.capacity_kwh
            self.BESS_RATED_POWER_KW = cfg.bess.rated_power_kw
        except Exception:
            pass  # use class defaults

    def validate_dispatch(
        self,
        action: str,
        requested_power_kw: float,
        bess_state: BESSState,
        load_shedding_stage: int = 0,
    ) -> Tuple[float, List[DispatchConstraint]]:
        """Validate dispatch command and apply constraints.

        Args:
            action: 'charge' or 'discharge'
            requested_power_kw: Requested power
            bess_state: Current BESS state
            load_shedding_stage: Current LS stage (0-8)

        Returns:
            Tuple of (actual_power_kw_after_constraints, list_of_constraints_applied)
        """
        constraints = []
        limited_power = requested_power_kw

        # 1. Temperature constraints
        if action == "charge":
            if bess_state.temperature_c < self.CHARGE_TEMP_MIN_C:
                constraint = DispatchConstraint(
                    constraint_type=ConstraintType.TEMPERATURE_LOW.value,
                    severity="block",
                    current_value=bess_state.temperature_c,
                    limit_value=self.CHARGE_TEMP_MIN_C,
                    message=(
                        f"Charge blocked: temperature {bess_state.temperature_c}°C"
                        f" below minimum {self.CHARGE_TEMP_MIN_C}°C"
                    ),
                    mitigation="Action blocked",
                )
                constraints.append(constraint)
                limited_power = 0.0
            elif bess_state.temperature_c > self.CHARGE_TEMP_MAX_C:
                # Reduce charge power as temp approaches limit
                temp_headroom = self.CHARGE_TEMP_MAX_C - bess_state.temperature_c
                if temp_headroom < 5:  # < 5°C headroom
                    reduction_factor = max(0.0, temp_headroom / 5.0)
                    limited_power = limited_power * reduction_factor
                    constraint = DispatchConstraint(
                        constraint_type=ConstraintType.TEMPERATURE_HIGH.value,
                        severity="warning",
                        current_value=bess_state.temperature_c,
                        limit_value=self.CHARGE_TEMP_MAX_C,
                        message=(
                            f"Charge power reduced due to temperature"
                            f" {bess_state.temperature_c}°C approaching limit"
                            f" {self.CHARGE_TEMP_MAX_C}°C"
                        ),
                        mitigation=(f"Reduced to {limited_power:.0f} kW ({reduction_factor * 100:.0f}%)"),
                    )
                    constraints.append(constraint)
        else:  # discharge
            if bess_state.temperature_c < self.DISCHARGE_TEMP_MIN_C:
                constraint = DispatchConstraint(
                    constraint_type=ConstraintType.TEMPERATURE_LOW.value,
                    severity="block",
                    current_value=bess_state.temperature_c,
                    limit_value=self.DISCHARGE_TEMP_MIN_C,
                    message=(
                        f"Discharge blocked: temperature {bess_state.temperature_c}°C"
                        f" below minimum {self.DISCHARGE_TEMP_MIN_C}°C"
                    ),
                    mitigation="Action blocked",
                )
                constraints.append(constraint)
                limited_power = 0.0
            elif bess_state.temperature_c > self.DISCHARGE_TEMP_MAX_C:
                constraint = DispatchConstraint(
                    constraint_type=ConstraintType.TEMPERATURE_HIGH.value,
                    severity="block",
                    current_value=bess_state.temperature_c,
                    limit_value=self.DISCHARGE_TEMP_MAX_C,
                    message=(
                        f"Discharge blocked: temperature {bess_state.temperature_c}°C"
                        f" exceeds maximum {self.DISCHARGE_TEMP_MAX_C}°C"
                    ),
                    mitigation="Action blocked",
                )
                constraints.append(constraint)
                limited_power = 0.0

        # 2. SOC constraints
        if action == "charge":
            if bess_state.soc_pct >= self.SOC_MAX_PCT:
                constraint = DispatchConstraint(
                    constraint_type=ConstraintType.SOC_MAX.value,
                    severity="block",
                    current_value=bess_state.soc_pct,
                    limit_value=self.SOC_MAX_PCT,
                    message=f"Charge blocked: SOC {bess_state.soc_pct:.1f}% at maximum {self.SOC_MAX_PCT}%",
                    mitigation="Action blocked",
                )
                constraints.append(constraint)
                limited_power = 0.0
        else:  # discharge
            if bess_state.soc_pct <= self.SOC_MIN_PCT:
                constraint = DispatchConstraint(
                    constraint_type=ConstraintType.SOC_MIN.value,
                    severity="block",
                    current_value=bess_state.soc_pct,
                    limit_value=self.SOC_MIN_PCT,
                    message=f"Discharge blocked: SOC {bess_state.soc_pct:.1f}% at minimum {self.SOC_MIN_PCT}%",
                    mitigation="Action blocked",
                )
                constraints.append(constraint)
                limited_power = 0.0

        # 3. Grid frequency constraint
        if action == "discharge" and bess_state.grid_frequency_hz > self.GRID_FREQUENCY_HIGH_THRESHOLD:
            freq_headroom = 50.5 - bess_state.grid_frequency_hz
            if freq_headroom < 0.2:
                reduction_factor = max(0.0, freq_headroom / 0.2)
                limited_power = limited_power * reduction_factor
                constraint = DispatchConstraint(
                    constraint_type=ConstraintType.FREQUENCY_HIGH.value,
                    severity="warning",
                    current_value=bess_state.grid_frequency_hz,
                    limit_value=self.GRID_FREQUENCY_HIGH_THRESHOLD,
                    message=(
                        f"Discharge reduced: grid frequency"
                        f" {bess_state.grid_frequency_hz:.2f} Hz above threshold"
                        f" {self.GRID_FREQUENCY_HIGH_THRESHOLD} Hz"
                    ),
                    mitigation=(f"Reduced to {limited_power:.0f} kW ({reduction_factor * 100:.0f}%)"),
                )
                constraints.append(constraint)

        # 4. Ramp rate constraint
        max_ramp_pct = self.RAMP_RATE_LS_PCT_PER_MIN if load_shedding_stage >= 4 else self.RAMP_RATE_NORMAL_PCT_PER_MIN
        max_ramp_power = self.BESS_RATED_POWER_KW * max_ramp_pct / 100.0

        time_delta = (datetime.now(timezone.utc) - self._last_update_time).total_seconds() / 60.0
        max_power_change = max_ramp_power * max(1.0, time_delta)

        if abs(limited_power - self._last_power_kw) > max_power_change:
            limited_power = self._last_power_kw + (
                max_power_change if limited_power > self._last_power_kw else -max_power_change
            )
            constraint = DispatchConstraint(
                constraint_type=ConstraintType.RAMP_RATE.value,
                severity="warning",
                current_value=abs(limited_power - self._last_power_kw),
                limit_value=max_power_change,
                message=(
                    f"Ramp rate limited: requested change"
                    f" {abs(limited_power - self._last_power_kw):.0f} kW"
                    f" exceeds max {max_power_change:.0f} kW/min"
                ),
                mitigation=f"Limited to {limited_power:.0f} kW",
            )
            constraints.append(constraint)

        # 5. Export limit constraint (for discharge)
        if action == "discharge":
            max_export = self.BESS_RATED_POWER_KW * self.EXPORT_LIMIT_PCT / 100.0
            if limited_power > max_export:
                constraint = DispatchConstraint(
                    constraint_type=ConstraintType.EXPORT_LIMIT.value,
                    severity="warning",
                    current_value=limited_power,
                    limit_value=max_export,
                    message=(
                        f"Export limited: requested {limited_power:.0f} kW"
                        f" exceeds NRS 097 limit of 50% Prated ({max_export:.0f} kW)"
                    ),
                    mitigation=f"Limited to {max_export:.0f} kW",
                )
                constraints.append(constraint)
                limited_power = max_export

        # 6. Load shedding stage adjustments
        if load_shedding_stage >= 4:
            if action == "discharge":
                # During LS stages 4-5, reduce discharge to 50%
                if load_shedding_stage < 6:
                    reduced_power = limited_power * 0.5
                else:
                    # Stages 6-8: stop discharge, prepare for emergency support
                    reduced_power = 0.0

                if reduced_power < limited_power:
                    constraint = DispatchConstraint(
                        constraint_type=ConstraintType.LOAD_SHEDDING.value,
                        severity="warning",
                        current_value=load_shedding_stage,
                        limit_value=3,  # Normal is 0-3
                        message=(
                            f"Discharge limited for load shedding stage"
                            f" {load_shedding_stage}: reserving capacity"
                            f" for grid support"
                        ),
                        mitigation=f"Limited to {reduced_power:.0f} kW ({reduced_power / limited_power * 100:.0f}%)"
                        if reduced_power > 0
                        else "Disabled",
                    )
                    constraints.append(constraint)
                    limited_power = reduced_power

        # Clamp to positive values
        if limited_power < 0:
            limited_power = 0.0

        return limited_power, constraints

    def execute_dispatch(
        self,
        site_id: str,
        action: str,
        requested_power_kw: float,
        bess_state: BESSState,
        duration_minutes: int = 15,
        reason: str = "arbitrage",
        load_shedding_stage: int = 0,
    ) -> DispatchCommand:
        """Execute a dispatch command with constraint validation.

        Args:
            site_id: Site identifier
            action: 'charge' or 'discharge'
            requested_power_kw: Requested power
            bess_state: Current BESS state
            duration_minutes: Duration of action
            reason: Reason for dispatch
            load_shedding_stage: Current LS stage (0-8)

        Returns:
            DispatchCommand with actual power and constraints applied
        """
        timestamp = datetime.now(timezone.utc).isoformat()

        # Validate action
        if action not in [DispatchActionType.CHARGE.value, DispatchActionType.DISCHARGE.value]:
            return DispatchCommand(
                site_id=site_id,
                timestamp=timestamp,
                action=action,
                requested_power_kw=requested_power_kw,
                actual_power_kw=0.0,
                duration_minutes=duration_minutes,
                reason=reason,
                success=False,
                error_message=f"Invalid action '{action}'. Must be 'charge' or 'discharge'.",
            )

        # Validate and apply constraints
        actual_power, constraints = self.validate_dispatch(
            action,
            requested_power_kw,
            bess_state,
            load_shedding_stage,
        )

        # Update state for next ramp rate check
        self._last_power_kw = actual_power
        self._last_update_time = datetime.now(timezone.utc)

        # Determine success
        success = actual_power > 0.0 or action == "idle"
        error_msg = None
        if not success:
            error_msg = "Dispatch blocked due to active constraints"

        return DispatchCommand(
            site_id=site_id,
            timestamp=timestamp,
            action=action,
            requested_power_kw=requested_power_kw,
            actual_power_kw=actual_power,
            duration_minutes=duration_minutes,
            reason=reason,
            constraints_applied=constraints,
            success=success,
            error_message=error_msg,
        )

    def respond_to_load_shedding(
        self,
        site_id: str,
        ls_stage: int,
        current_bess_state: BESSState,
    ) -> Dict[str, Any]:
        """Automatically adjust dispatch for load shedding event.

        Strategy:
          - Stages 1-3: Continue normal arbitrage (no change)
          - Stages 4-5: Reduce discharge to 50%, maintain charging
          - Stages 6-8: Stop discharge, charge to reserve SOC

        Args:
            site_id: Site identifier
            ls_stage: Current LS stage (0-8)
            current_bess_state: Current BESS state

        Returns:
            Dict with stage, action_taken, power_change_kw, recommendation
        """
        timestamp = datetime.now(timezone.utc).isoformat()
        action_taken = "none"
        power_change_kw = 0.0
        recommendation = ""

        if ls_stage < 4:
            # Normal operation - no special action
            action_taken = "continue_normal"
            recommendation = "Continue normal TOU arbitrage dispatch"
        elif ls_stage < 6:
            # Stages 4-5: Reduce discharge
            action_taken = "reduce_discharge_50pct"
            power_change_kw = -self.BESS_RATED_POWER_KW * 0.5
            recommendation = "Reducing discharge to 50% to reserve BESS capacity for grid support during stages 4-5"
        else:
            # Stages 6-8: Stop discharge, charge to reserve
            action_taken = "stop_discharge_charge_reserve"
            power_change_kw = self.BESS_RATED_POWER_KW  # Switch to charging
            recommendation = (
                f"Emergency: stopping discharge and charging to"
                f" {self.SOC_LS_RESERVE_PCT}% SOC reserve for grid support"
                f" during stages 6-8"
            )

        return {
            "site_id": site_id,
            "timestamp": timestamp,
            "load_shedding_stage": ls_stage,
            "action_taken": action_taken,
            "power_change_kw": round(power_change_kw, 0),
            "recommendation": recommendation,
            "bess_soc_before_pct": round(current_bess_state.soc_pct, 1),
            "target_soc_pct": self.SOC_LS_RESERVE_PCT if ls_stage >= 6 else None,
        }


# === Singleton ===

_bess_dispatch_engine: Optional[BESSDispatchEngine] = None


def get_bess_dispatch_engine() -> BESSDispatchEngine:
    """Get singleton BESS dispatch engine instance."""
    global _bess_dispatch_engine
    if _bess_dispatch_engine is None:
        _bess_dispatch_engine = BESSDispatchEngine()
    return _bess_dispatch_engine
