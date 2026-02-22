"""Grid Compliance Service — NRS 097-2-3 monitoring and load shedding coordination.

Monitors grid parameters (frequency, voltage, ramp rates) against South African
grid codes and coordinates automatic responses (curtailment, standby, droop).

Features:
  - Real-time monitoring of frequency, voltage, power quality
  - NRS 097-2-3 compliance validation every 10 seconds
  - Load shedding stage detection (stages 1-8 based on frequency)
  - Auto-response coordination: BESS discharge → solar curtailment → standby
  - Comprehensive logging of violations and actions
  - Hysteresis in stage transitions to prevent oscillation

Pattern follows solar_compliance_service.py and device_abstraction.py.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple

from app.models.solar import (
    GridParameter,
    ComplianceSeverity,
    FrequencyBand,
    VoltageBand,
    RampRateLimit,
    ComplianceViolation,
    GridComplianceStatus,
    LoadShedEvent,
)
from app.database.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)


# === Grid Compliance Rules (NRS 097-2-3) ===

NRS_097_2_3_FREQUENCY_BANDS = {
    "normal": FrequencyBand(
        band_name="normal",
        min_hz=49.5,
        max_hz=50.5,
        trip_low_hz=47.5,
        trip_high_hz=52.0,
        disconnect_delay_ms=200,
    ),
    "recovery": FrequencyBand(
        band_name="recovery",
        min_hz=49.5,
        max_hz=50.5,
        trip_low_hz=None,
        trip_high_hz=None,
    ),
    "emergency": FrequencyBand(
        band_name="emergency",
        min_hz=47.5,
        max_hz=52.0,
        trip_low_hz=47.5,
        trip_high_hz=52.0,
        disconnect_delay_ms=100,
    ),
}

NRS_097_2_3_VOLTAGE_BANDS = {
    "normal": VoltageBand(
        band_name="normal",
        nominal_v=400.0,
        min_v=360.0,  # -10%
        max_v=440.0,  # +10%
        trip_low_v=340.0,  # -15%
        trip_high_v=460.0,  # +15%
        disconnect_delay_ms=500,
    ),
    "recovery": VoltageBand(
        band_name="recovery",
        nominal_v=400.0,
        min_v=376.0,  # -6%
        max_v=424.0,  # +6%
        trip_low_v=360.0,
        trip_high_v=440.0,
        disconnect_delay_ms=200,
    ),
}

NRS_097_2_3_RAMP_RATES = {
    "normal": RampRateLimit(condition="normal", max_pct_per_min=10.0),
    "curtailment": RampRateLimit(condition="curtailment", max_pct_per_min=5.0),
    "recovery": RampRateLimit(condition="recovery", max_pct_per_min=3.0),
}

# Load shedding frequency markers (South African convention)
LOAD_SHED_STAGES = {
    1: 50.5,  # Stage 1: 1000 MW shed
    2: 50.4,
    3: 50.3,
    4: 50.2,
    5: 50.0,
    6: 49.5,
    7: 49.0,
    8: 47.5,  # Stage 8: 8000+ MW shed
}


@dataclass
class GridParameters:
    """Current grid parameters from BESS or site meter."""

    timestamp: str
    frequency_hz: float
    voltage_v: float  # Phase-to-phase or nominal
    current_a: float = 0.0
    power_factor: float = 1.0
    thd_pct: float = 0.0
    ac_power_kw: float = 0.0  # For ramp rate calculation
    previous_power_kw: float = 0.0  # For ramp rate
    time_delta_seconds: float = 1.0  # Seconds since last reading


class MonitoringEngine:
    """Validates grid parameters against grid codes and triggers auto-responses."""

    def __init__(self, grid_code: str = "nrs_097_2_3", system_id: str = "solar-001"):
        self.grid_code = grid_code
        self.system_id = system_id
        self.last_check_time = datetime.now(timezone.utc)
        self.violations: List[ComplianceViolation] = []
        self.monitoring_interval_seconds = 10

        # Load frequency and voltage bands
        if grid_code == "nrs_097_2_3":
            self.frequency_bands = NRS_097_2_3_FREQUENCY_BANDS
            self.voltage_bands = NRS_097_2_3_VOLTAGE_BANDS
            self.ramp_rates = NRS_097_2_3_RAMP_RATES
        else:
            raise ValueError(f"Unsupported grid code: {grid_code}")

        logger.info(
            "MonitoringEngine initialized for %s (system: %s)",
            grid_code,
            system_id,
        )

    async def validate(self, params: GridParameters) -> GridComplianceStatus:
        """Validate grid parameters and return compliance status.

        Args:
            params: GridParameters to validate

        Returns:
            GridComplianceStatus with violations and recommendations
        """
        now = datetime.now(timezone.utc)
        violations: List[ComplianceViolation] = []

        # Check frequency compliance
        freq_violations = self._validate_frequency(params, now)
        violations.extend(freq_violations)

        # Check voltage compliance
        volt_violations = self._validate_voltage(params, now)
        violations.extend(volt_violations)

        # Check ramp rate compliance
        ramp_violations = self._validate_ramp_rate(params, now)
        violations.extend(ramp_violations)

        # Determine overall compliance
        critical_violations = [v for v in violations if v.severity == ComplianceSeverity.CRITICAL]
        compliant = len(critical_violations) == 0

        # Log violations to persistent storage
        for violation in violations:
            await self._log_violation(violation)

        # Store for later reference
        self.violations = violations

        next_check = (now + timedelta(seconds=self.monitoring_interval_seconds)).isoformat()

        return GridComplianceStatus(
            system_id=self.system_id,
            grid_code=self.grid_code,
            compliant=compliant,
            last_check=now.isoformat(),
            next_check=next_check,
            active_violations=violations,
            frequency_hz=params.frequency_hz,
            voltage_v=params.voltage_v,
            current_a=params.current_a,
            power_factor=params.power_factor,
            temperature_c=25.0,
        )

    def _validate_frequency(self, params: GridParameters, now: datetime) -> List[ComplianceViolation]:
        """Validate frequency against grid code limits."""
        violations: List[ComplianceViolation] = []
        normal_band = self.frequency_bands["normal"]

        # Check normal operating band
        if params.frequency_hz < normal_band.min_hz:
            violation = ComplianceViolation(
                timestamp=now.isoformat(),
                system_id=self.system_id,
                parameter=GridParameter.FREQUENCY,
                measured_value=params.frequency_hz,
                limit_value=normal_band.min_hz,
                violation_type="below_min",
                severity=ComplianceSeverity.WARNING,
                auto_action="bess_discharge",  # Support grid with BESS
            )
            violations.append(violation)

        if params.frequency_hz > normal_band.max_hz:
            violation = ComplianceViolation(
                timestamp=now.isoformat(),
                system_id=self.system_id,
                parameter=GridParameter.FREQUENCY,
                measured_value=params.frequency_hz,
                limit_value=normal_band.max_hz,
                violation_type="exceeds_max",
                severity=ComplianceSeverity.WARNING,
                auto_action="solar_curtailment",  # Reduce injection
            )
            violations.append(violation)

        # Check trip thresholds (mandatory disconnect)
        if normal_band.trip_low_hz and params.frequency_hz < normal_band.trip_low_hz:
            violation = ComplianceViolation(
                timestamp=now.isoformat(),
                system_id=self.system_id,
                parameter=GridParameter.FREQUENCY,
                measured_value=params.frequency_hz,
                limit_value=normal_band.trip_low_hz,
                violation_type="below_min",
                severity=ComplianceSeverity.CRITICAL,
                auto_action="standby",
                duration_ms=normal_band.disconnect_delay_ms,
            )
            violations.append(violation)

        if normal_band.trip_high_hz and params.frequency_hz > normal_band.trip_high_hz:
            violation = ComplianceViolation(
                timestamp=now.isoformat(),
                system_id=self.system_id,
                parameter=GridParameter.FREQUENCY,
                measured_value=params.frequency_hz,
                limit_value=normal_band.trip_high_hz,
                violation_type="exceeds_max",
                severity=ComplianceSeverity.CRITICAL,
                auto_action="standby",
                duration_ms=normal_band.disconnect_delay_ms,
            )
            violations.append(violation)

        return violations

    def _validate_voltage(self, params: GridParameters, now: datetime) -> List[ComplianceViolation]:
        """Validate voltage against grid code limits."""
        violations: List[ComplianceViolation] = []
        normal_band = self.voltage_bands["normal"]

        # Check normal operating band
        if params.voltage_v < normal_band.min_v:
            violation = ComplianceViolation(
                timestamp=now.isoformat(),
                system_id=self.system_id,
                parameter=GridParameter.VOLTAGE,
                measured_value=params.voltage_v,
                limit_value=normal_band.min_v,
                violation_type="below_min",
                severity=ComplianceSeverity.WARNING,
                auto_action="active_current_support",
            )
            violations.append(violation)

        if params.voltage_v > normal_band.max_v:
            violation = ComplianceViolation(
                timestamp=now.isoformat(),
                system_id=self.system_id,
                parameter=GridParameter.VOLTAGE,
                measured_value=params.voltage_v,
                limit_value=normal_band.max_v,
                violation_type="exceeds_max",
                severity=ComplianceSeverity.WARNING,
                auto_action="solar_curtailment",
            )
            violations.append(violation)

        # Check trip thresholds
        if normal_band.trip_low_v and params.voltage_v < normal_band.trip_low_v:
            violation = ComplianceViolation(
                timestamp=now.isoformat(),
                system_id=self.system_id,
                parameter=GridParameter.VOLTAGE,
                measured_value=params.voltage_v,
                limit_value=normal_band.trip_low_v,
                violation_type="below_min",
                severity=ComplianceSeverity.CRITICAL,
                auto_action="standby",
                duration_ms=normal_band.disconnect_delay_ms,
            )
            violations.append(violation)

        if normal_band.trip_high_v and params.voltage_v > normal_band.trip_high_v:
            violation = ComplianceViolation(
                timestamp=now.isoformat(),
                system_id=self.system_id,
                parameter=GridParameter.VOLTAGE,
                measured_value=params.voltage_v,
                limit_value=normal_band.trip_high_v,
                violation_type="exceeds_max",
                severity=ComplianceSeverity.CRITICAL,
                auto_action="standby",
                duration_ms=normal_band.disconnect_delay_ms,
            )
            violations.append(violation)

        return violations

    def _validate_ramp_rate(self, params: GridParameters, now: datetime) -> List[ComplianceViolation]:
        """Validate power ramp rate against grid code limits."""
        violations: List[ComplianceViolation] = []

        if params.time_delta_seconds <= 0:
            return violations

        # Calculate ramp rate (% per minute)
        power_delta = params.ac_power_kw - params.previous_power_kw
        if params.previous_power_kw > 0:
            ramp_rate_pct_per_min = (
                (power_delta / params.previous_power_kw) * 100.0 * (60.0 / params.time_delta_seconds)
            )

            # Check against normal ramp rate limit
            normal_limit = self.ramp_rates["normal"].max_pct_per_min
            if abs(ramp_rate_pct_per_min) > normal_limit:
                violation = ComplianceViolation(
                    timestamp=now.isoformat(),
                    system_id=self.system_id,
                    parameter=GridParameter.RAMP_RATE,
                    measured_value=abs(ramp_rate_pct_per_min),
                    limit_value=normal_limit,
                    violation_type="ramp_too_fast",
                    severity=ComplianceSeverity.WARNING,
                    auto_action="frequency_droop",
                )
                violations.append(violation)

        return violations

    async def _log_violation(self, violation: ComplianceViolation) -> None:
        """Log violation to Supabase compliance_log table."""
        try:
            supabase = get_supabase_client()
            if supabase is None:
                logger.warning("Supabase unavailable, violation not persisted")
                return

            # Insert into compliance_log table
            # Note: Supabase client in synchronous mode, call it directly
            response = (
                supabase.table("compliance_log")
                .insert(
                    {
                        "system_id": violation.system_id,
                        "timestamp": violation.timestamp,
                        "parameter": violation.parameter,
                        "measured_value": float(violation.measured_value),
                        "limit_value": float(violation.limit_value),
                        "violation_type": violation.violation_type,
                        "severity": violation.severity,
                        "auto_action": violation.auto_action,
                        "duration_ms": violation.duration_ms,
                        "resolved": violation.resolved,
                    }
                )
                .execute()
            )

            logger.debug(f"Logged violation: {violation.parameter} at {violation.system_id}")

        except Exception as e:
            logger.error(f"Failed to log compliance violation: {e}")


class LoadShedScheduler:
    """Detects load shedding stages and coordinates dispatch actions."""

    def __init__(self):
        self.current_stage = 0
        self.previous_stage = 0
        self.last_frequency = 50.0
        self.stage_transition_time = None
        self.hysteresis_hz = 0.1  # Prevent oscillation between stages
        self.check_interval_seconds = 2  # Monitor frequency every 2 seconds
        self.history: List[LoadShedEvent] = []

        logger.info(
            "LoadShedScheduler initialized (check interval: %ds, hysteresis: %f Hz)",
            self.check_interval_seconds,
            self.hysteresis_hz,
        )

    async def detect_stage(self, frequency_hz: float) -> Tuple[int, Optional[LoadShedEvent]]:
        """Detect current load shedding stage and trigger dispatch if stage changed.

        Args:
            frequency_hz: Current grid frequency

        Returns:
            Tuple of (stage, LoadShedEvent if stage changed, else None)
        """
        self.last_frequency = frequency_hz

        # Determine stage based on frequency markers
        new_stage = self._calculate_stage(frequency_hz)

        # Check for stage transition with hysteresis
        if new_stage != self.current_stage:
            self.previous_stage = self.current_stage
            self.current_stage = new_stage
            self.stage_transition_time = datetime.now(timezone.utc)

            # Route dispatch commands
            dispatch_action, affected_systems = await self._route_dispatch(self.previous_stage, self.current_stage)

            # Create event record
            event = LoadShedEvent(
                timestamp=self.stage_transition_time.isoformat(),
                frequency_hz=frequency_hz,
                previous_stage=self.previous_stage,
                current_stage=self.current_stage,
                dispatch_action=dispatch_action,
                affected_systems=affected_systems,
            )

            # Log event
            await self._log_stage_transition(event)
            self.history.append(event)

            logger.info(
                f"Load shedding stage transition: {self.previous_stage} → {self.current_stage} "
                f"at {frequency_hz} Hz (action: {dispatch_action})"
            )

            return new_stage, event

        return self.current_stage, None

    def _calculate_stage(self, frequency_hz: float) -> int:
        """Calculate load shedding stage based on frequency with hysteresis."""
        # Start from stage 8 and work down to stage 1
        for stage in sorted(LOAD_SHED_STAGES.keys(), reverse=True):
            threshold = LOAD_SHED_STAGES[stage]

            # Apply hysteresis when transitioning from lower stage (frequency going up)
            if stage < self.current_stage:
                threshold += self.hysteresis_hz

            if frequency_hz <= threshold:
                return stage

        return 0  # No load shedding

    async def _route_dispatch(self, previous_stage: int, current_stage: int) -> Tuple[str, List[str]]:
        """Route dispatch commands based on stage transition.

        Priority: BESS discharge → Solar curtailment → Standby

        Returns:
            Tuple of (action_name, affected_system_ids)
        """
        affected_systems: List[str] = []

        if current_stage > previous_stage:
            # Shedding is worsening
            if current_stage <= 3:
                # Stages 1-3: Light shedding, use BESS
                return "bess_discharge", ["S002-BESS-B1-001"]
            elif current_stage <= 6:
                # Stages 4-6: Medium shedding, curtail solar
                return "solar_curtailment_50pct", ["S002-SOLAR-001"]
            else:
                # Stages 7-8: Critical, standby
                return "standby_mode", ["S002-SOLAR-001", "S002-BESS-B1-001"]
        else:
            # Shedding is improving, ramp up gradually
            return "ramp_up_5pct_per_min", ["S002-SOLAR-001", "S002-BESS-B1-001"]

    async def _log_stage_transition(self, event: LoadShedEvent) -> None:
        """Log stage transition to Supabase."""
        try:
            supabase = get_supabase_client()
            if supabase is None:
                logger.warning("Supabase unavailable, stage transition not persisted")
                return

            # Insert into load_shed_events table
            # Note: Supabase client in synchronous mode, call it directly
            response = (
                supabase.table("load_shed_events")
                .insert(
                    {
                        "timestamp": event.timestamp,
                        "frequency_hz": float(event.frequency_hz),
                        "previous_stage": event.previous_stage,
                        "current_stage": event.current_stage,
                        "dispatch_action": event.dispatch_action,
                        "affected_systems": event.affected_systems,
                        "expected_reduction_kw": float(event.expected_reduction_kw),
                    }
                )
                .execute()
            )

            logger.debug(f"Logged load shedding stage transition: stage {event.current_stage}")

        except Exception as e:
            logger.error(f"Failed to log load shedding event: {e}")

    def get_current_stage(self) -> int:
        """Get current load shedding stage (0-8)."""
        return self.current_stage

    def get_last_transition(self) -> Optional[LoadShedEvent]:
        """Get the last stage transition event."""
        return self.history[-1] if self.history else None


# === Singleton accessors ===

_monitoring_engines: Dict[str, MonitoringEngine] = {}
_load_shed_scheduler: Optional[LoadShedScheduler] = None


def get_monitoring_engine(grid_code: str = "nrs_097_2_3", system_id: str = "solar-001") -> MonitoringEngine:
    """Get or create a MonitoringEngine instance."""
    key = f"{grid_code}:{system_id}"
    if key not in _monitoring_engines:
        _monitoring_engines[key] = MonitoringEngine(grid_code, system_id)
    return _monitoring_engines[key]


def get_load_shed_scheduler() -> LoadShedScheduler:
    """Get or create the LoadShedScheduler singleton."""
    global _load_shed_scheduler
    if _load_shed_scheduler is None:
        _load_shed_scheduler = LoadShedScheduler()
    return _load_shed_scheduler
