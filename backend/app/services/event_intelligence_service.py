"""Operational Event Intelligence Service.

Converts raw telemetry changes into structured operational events.
Sits between telemetry ingestion and the reasoning layer.

Architecture:
    Telemetry -> EventIntelligenceService -> OperationalEvent -> EventBus -> Reasoning

Detection rules evaluate equipment telemetry against configurable thresholds
and emit OperationalEvent objects. Active conditions are tracked for duration
and trend analysis. Resolved conditions are automatically cleared.

Phase 145: Operational Event Intelligence.
"""

from __future__ import annotations

import logging
import math
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.models.operational_event import (
    EventSeverity,
    OperationalEvent,
    OperationalEventType,
    _generate_event_id,
)
from app.services.event_bus import get_event_bus
from app.services.ml_config import get_anomaly_alert_threshold

logger = logging.getLogger("sentinel.event_intelligence")


# ---------------------------------------------------------------------------
# Configuration defaults
# ---------------------------------------------------------------------------

DEFAULT_TEMP_DEVIATION_THRESHOLD_C = 2.0
DEFAULT_COMFORT_BAND_MIN_C = 20.0
DEFAULT_COMFORT_BAND_MAX_C = 24.0
DEFAULT_ENERGY_SPIKE_FACTOR = 1.5
DEFAULT_STALE_READING_MINUTES = 15.0
DEFAULT_ANOMALY_SCORE_THRESHOLD = 0.5
DEFAULT_SETPOINT_DRIFT_THRESHOLD_C = 1.0
TREND_BUFFER_SIZE = 5


# ---------------------------------------------------------------------------
# Detection Rule
# ---------------------------------------------------------------------------


@dataclass
class EventDetectionRule:
    """A single detection rule that checks telemetry for a specific condition.

    Attributes:
        rule_id: Unique identifier for this rule.
        event_type: The OperationalEventType this rule detects.
        equipment_types: Which equipment types this rule applies to.
            Empty list means the rule applies to all equipment types.
        check: Async detection function. Takes (equipment_id, site_id,
            telemetry, config) and returns an OperationalEvent or None.
    """

    rule_id: str
    event_type: OperationalEventType
    equipment_types: list[str]
    check: Callable


# ---------------------------------------------------------------------------
# Active condition tracker
# ---------------------------------------------------------------------------


@dataclass
class _ActiveCondition:
    """Internal tracker for an ongoing condition."""

    event: OperationalEvent
    first_detected: float  # monotonic timestamp
    last_detected: float  # monotonic timestamp


# ---------------------------------------------------------------------------
# Trend buffer
# ---------------------------------------------------------------------------


class _TrendBuffer:
    """Ring buffer for tracking recent values of a single point."""

    def __init__(self, maxlen: int = TREND_BUFFER_SIZE):
        self._values: deque[float] = deque(maxlen=maxlen)

    def add(self, value: float) -> None:
        self._values.append(value)

    def trend(self) -> str | None:
        """Determine trend from buffered values.

        Returns:
            "rising" if monotonically increasing (3+ values),
            "falling" if monotonically decreasing (3+ values),
            "stable" otherwise, or None if insufficient data.
        """
        if len(self._values) < 3:
            return None

        vals = list(self._values)
        rising = all(vals[i] < vals[i + 1] for i in range(len(vals) - 1))
        falling = all(vals[i] > vals[i + 1] for i in range(len(vals) - 1))

        if rising:
            return "rising"
        if falling:
            return "falling"
        return "stable"


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class EventIntelligenceService:
    """Detects operational events from telemetry and emits them to the event bus.

    Usage:
        service = get_event_intelligence_service()
        events = await service.process_site("site-002")

    The service maintains:
    - A registry of detection rules
    - Active condition tracking with duration
    - Per-point trend buffers
    - Rolling event history
    """

    def __init__(
        self,
        *,
        temp_deviation_threshold: float = DEFAULT_TEMP_DEVIATION_THRESHOLD_C,
        comfort_band_min: float = DEFAULT_COMFORT_BAND_MIN_C,
        comfort_band_max: float = DEFAULT_COMFORT_BAND_MAX_C,
        energy_spike_factor: float = DEFAULT_ENERGY_SPIKE_FACTOR,
        stale_reading_minutes: float = DEFAULT_STALE_READING_MINUTES,
        anomaly_score_threshold: float = DEFAULT_ANOMALY_SCORE_THRESHOLD,
        setpoint_drift_threshold: float = DEFAULT_SETPOINT_DRIFT_THRESHOLD_C,
    ):
        self._rules: list[EventDetectionRule] = []
        self._active_conditions: dict[str, _ActiveCondition] = {}
        self._event_history: deque[OperationalEvent] = deque(maxlen=10000)
        self._trend_buffers: dict[str, _TrendBuffer] = {}
        self._energy_history: dict[str, deque[float]] = {}

        # Configurable thresholds
        self._temp_deviation_threshold = temp_deviation_threshold
        self._comfort_band_min = comfort_band_min
        self._comfort_band_max = comfort_band_max
        self._energy_spike_factor = energy_spike_factor
        self._stale_reading_minutes = stale_reading_minutes
        self._anomaly_score_threshold = anomaly_score_threshold
        self._setpoint_drift_threshold = setpoint_drift_threshold

        self._register_default_rules()

    # ------------------------------------------------------------------
    # Rule registration
    # ------------------------------------------------------------------

    def _register_default_rules(self) -> None:
        """Register the built-in detection rules."""
        self._rules = [
            EventDetectionRule(
                rule_id="temp_deviation",
                event_type=OperationalEventType.TEMPERATURE_DEVIATION,
                equipment_types=["FCU", "AHU", "VAV", "SPLIT", "CRAC"],
                check=self._check_temperature_deviation,
            ),
            EventDetectionRule(
                rule_id="energy_spike",
                event_type=OperationalEventType.ENERGY_SPIKE,
                equipment_types=[],  # all equipment
                check=self._check_energy_spike,
            ),
            EventDetectionRule(
                rule_id="sensor_failure",
                event_type=OperationalEventType.SENSOR_FAILURE,
                equipment_types=[],  # all equipment
                check=self._check_sensor_failure,
            ),
            EventDetectionRule(
                rule_id="comfort_violation",
                event_type=OperationalEventType.COMFORT_VIOLATION,
                equipment_types=["FCU", "AHU", "VAV", "SPLIT", "CRAC"],
                check=self._check_comfort_violation,
            ),
            EventDetectionRule(
                rule_id="pattern_anomaly",
                event_type=OperationalEventType.PATTERN_ANOMALY,
                equipment_types=[],  # all equipment
                check=self._check_ml_anomaly,
            ),
            EventDetectionRule(
                rule_id="setpoint_drift",
                event_type=OperationalEventType.SETPOINT_DRIFT,
                equipment_types=["FCU", "AHU", "VAV", "SPLIT", "CRAC"],
                check=self._check_setpoint_drift,
            ),
            EventDetectionRule(
                rule_id="threshold_breach",
                event_type=OperationalEventType.THRESHOLD_BREACH,
                equipment_types=[],  # all equipment
                check=self._check_threshold_breach,
            ),
        ]

    def register_rule(self, rule: EventDetectionRule) -> None:
        """Register an additional detection rule.

        Args:
            rule: The detection rule to add.
        """
        self._rules.append(rule)

    # ------------------------------------------------------------------
    # Equipment type extraction
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_equipment_type(equipment_id: str) -> str:
        """Extract equipment type from equipment code.

        Format: {site}-{type}-{zone_id} or {site}-{type}-{loc}-{seq}
        Examples: S002-FCU-101 -> FCU, S002-CHILLER-B1-001 -> CHILLER
        """
        parts = equipment_id.split("-")
        if len(parts) >= 2:
            return parts[1].upper()
        return "UNKNOWN"

    # ------------------------------------------------------------------
    # Trend tracking
    # ------------------------------------------------------------------

    def _get_trend(self, equipment_id: str, point_name: str, value: float) -> str | None:
        """Record a value and return the current trend for a point.

        Args:
            equipment_id: Equipment code.
            point_name: Name of the telemetry point.
            value: Current value.

        Returns:
            Trend string or None if insufficient data.
        """
        key = f"{equipment_id}:{point_name}"
        if key not in self._trend_buffers:
            self._trend_buffers[key] = _TrendBuffer()
        self._trend_buffers[key].add(value)
        return self._trend_buffers[key].trend()

    # ------------------------------------------------------------------
    # Detection rule implementations
    # ------------------------------------------------------------------

    async def _check_temperature_deviation(
        self, equipment_id: str, site_id: str, telemetry: dict[str, Any]
    ) -> OperationalEvent | None:
        """Detect temperature deviation from setpoint.

        Triggers when actual temperature deviates from setpoint by more than
        the configured threshold (default 2 deg C).
        """
        current_temp = telemetry.get("current_temp") or telemetry.get("supply_temp")
        setpoint = telemetry.get("setpoint") or telemetry.get("setpoint_temp")

        if current_temp is None or setpoint is None:
            return None

        try:
            current_temp = float(current_temp)
            setpoint = float(setpoint)
        except (ValueError, TypeError):
            return None

        deviation = abs(current_temp - setpoint)
        if deviation <= self._temp_deviation_threshold:
            return None

        trend = self._get_trend(equipment_id, "current_temp", current_temp)
        severity = EventSeverity.HIGH if deviation > self._temp_deviation_threshold * 2 else EventSeverity.WARNING

        return OperationalEvent(
            event_id=_generate_event_id(),
            event_type=OperationalEventType.TEMPERATURE_DEVIATION,
            equipment_id=equipment_id,
            site_id=site_id,
            severity=severity,
            timestamp=datetime.now(UTC),
            signals=[{"point": "current_temp", "value": current_temp, "setpoint": setpoint}],
            description=(
                f"{equipment_id}: temperature {current_temp:.1f}C deviates "
                f"{deviation:.1f}C from setpoint {setpoint:.1f}C"
            ),
            trend=trend,
            threshold_value=self._temp_deviation_threshold,
            actual_value=current_temp,
        )

    async def _check_energy_spike(
        self, equipment_id: str, site_id: str, telemetry: dict[str, Any]
    ) -> OperationalEvent | None:
        """Detect energy consumption spikes.

        Compares current power reading to a rolling average. Triggers when
        current power exceeds the average by the configured factor (default 1.5x).
        """
        power = telemetry.get("power_kw") or telemetry.get("current_power_kw")
        if power is None:
            return None

        try:
            power = float(power)
        except (ValueError, TypeError):
            return None

        if power <= 0:
            return None

        # Maintain rolling average
        key = f"{equipment_id}:power"
        if key not in self._energy_history:
            self._energy_history[key] = deque(maxlen=20)

        history = self._energy_history[key]
        if len(history) >= 3:
            avg = sum(history) / len(history)
            if avg > 0 and power > avg * self._energy_spike_factor:
                trend = self._get_trend(equipment_id, "power_kw", power)
                severity = EventSeverity.HIGH if power > avg * 2.0 else EventSeverity.WARNING

                # Still record the value
                history.append(power)

                return OperationalEvent(
                    event_id=_generate_event_id(),
                    event_type=OperationalEventType.ENERGY_SPIKE,
                    equipment_id=equipment_id,
                    site_id=site_id,
                    severity=severity,
                    timestamp=datetime.now(UTC),
                    signals=[{"point": "power_kw", "value": power, "rolling_avg": round(avg, 2)}],
                    description=(
                        f"{equipment_id}: power {power:.1f}kW is {power / avg:.1f}x the rolling average {avg:.1f}kW"
                    ),
                    trend=trend,
                    threshold_value=round(avg * self._energy_spike_factor, 2),
                    actual_value=power,
                )

        history.append(power)
        return None

    async def _check_sensor_failure(
        self, equipment_id: str, site_id: str, telemetry: dict[str, Any]
    ) -> OperationalEvent | None:
        """Detect sensor failures — NaN, None, or stale readings.

        Checks all numeric telemetry values. Also checks for a
        'last_reading_timestamp' field to detect stale data.
        """
        failed_points: list[dict[str, Any]] = []

        for key, value in telemetry.items():
            if key in ("status", "mode", "equipment_type", "is_running", "last_reading_timestamp"):
                continue

            if value is None:
                failed_points.append({"point": key, "reason": "null_value"})
            elif isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
                failed_points.append({"point": key, "reason": "nan_or_inf"})

        # Check for stale readings
        last_ts = telemetry.get("last_reading_timestamp")
        if last_ts is not None:
            try:
                if isinstance(last_ts, str):
                    last_dt = datetime.fromisoformat(last_ts.replace("Z", "+00:00"))
                elif isinstance(last_ts, (int, float)):
                    last_dt = datetime.fromtimestamp(last_ts, tz=UTC)
                else:
                    last_dt = None

                if last_dt is not None:
                    age_minutes = (datetime.now(UTC) - last_dt).total_seconds() / 60.0
                    if age_minutes > self._stale_reading_minutes:
                        failed_points.append(
                            {
                                "point": "last_reading_timestamp",
                                "reason": "stale_reading",
                                "age_minutes": round(age_minutes, 1),
                            }
                        )
            except (ValueError, TypeError, OSError):
                pass

        if not failed_points:
            return None

        severity = EventSeverity.HIGH if len(failed_points) >= 3 else EventSeverity.WARNING

        return OperationalEvent(
            event_id=_generate_event_id(),
            event_type=OperationalEventType.SENSOR_FAILURE,
            equipment_id=equipment_id,
            site_id=site_id,
            severity=severity,
            timestamp=datetime.now(UTC),
            signals=failed_points,
            description=(
                f"{equipment_id}: {len(failed_points)} sensor failure(s) detected "
                f"({', '.join(p['point'] for p in failed_points)})"
            ),
            actual_value=float(len(failed_points)),
        )

    async def _check_comfort_violation(
        self, equipment_id: str, site_id: str, telemetry: dict[str, Any]
    ) -> OperationalEvent | None:
        """Detect zone temperature outside comfort band.

        Default comfort band is 20-24 deg C (configurable).
        """
        zone_temp = telemetry.get("zone_temp") or telemetry.get("current_temp")
        if zone_temp is None:
            return None

        try:
            zone_temp = float(zone_temp)
        except (ValueError, TypeError):
            return None

        if self._comfort_band_min <= zone_temp <= self._comfort_band_max:
            return None

        trend = self._get_trend(equipment_id, "zone_temp", zone_temp)

        if zone_temp < self._comfort_band_min:
            deviation = self._comfort_band_min - zone_temp
            direction = "below"
            threshold = self._comfort_band_min
        else:
            deviation = zone_temp - self._comfort_band_max
            direction = "above"
            threshold = self._comfort_band_max

        severity = EventSeverity.HIGH if deviation > 3.0 else EventSeverity.WARNING

        return OperationalEvent(
            event_id=_generate_event_id(),
            event_type=OperationalEventType.COMFORT_VIOLATION,
            equipment_id=equipment_id,
            site_id=site_id,
            severity=severity,
            timestamp=datetime.now(UTC),
            signals=[
                {
                    "point": "zone_temp",
                    "value": zone_temp,
                    "comfort_min": self._comfort_band_min,
                    "comfort_max": self._comfort_band_max,
                }
            ],
            description=(
                f"{equipment_id}: zone temperature {zone_temp:.1f}C is "
                f"{deviation:.1f}C {direction} comfort band "
                f"({self._comfort_band_min}-{self._comfort_band_max}C)"
            ),
            trend=trend,
            threshold_value=threshold,
            actual_value=zone_temp,
        )

    async def _check_ml_anomaly(
        self, equipment_id: str, site_id: str, telemetry: dict[str, Any]
    ) -> OperationalEvent | None:
        """Detect ML-flagged pattern anomalies.

        Checks if the telemetry contains an anomaly_score field (injected
        by upstream ML inference) above the dynamic threshold. The threshold
        starts conservative (0.87) at 72 hours of shadow data and eases to
        0.75 once 2000+ hours have accumulated — preventing noisy Telegram
        alerts during early sparse-data calibration.
        """
        anomaly_score = telemetry.get("anomaly_score")
        if anomaly_score is None:
            return None

        try:
            anomaly_score = float(anomaly_score)
        except (ValueError, TypeError):
            return None

        # Dynamic threshold — reads ml_hours_ingested from SentinelDataSync singleton
        threshold = self._get_dynamic_anomaly_threshold()

        if anomaly_score <= threshold:
            return None

        severity = EventSeverity.CRITICAL if anomaly_score > 0.8 else EventSeverity.HIGH

        return OperationalEvent(
            event_id=_generate_event_id(),
            event_type=OperationalEventType.PATTERN_ANOMALY,
            equipment_id=equipment_id,
            site_id=site_id,
            severity=severity,
            timestamp=datetime.now(UTC),
            signals=[{"point": "anomaly_score", "value": anomaly_score}],
            description=(f"{equipment_id}: ML anomaly score {anomaly_score:.2f} exceeds threshold {threshold}"),
            threshold_value=threshold,
            actual_value=anomaly_score,
            metadata={"anomaly_score": anomaly_score},
        )

    def _get_dynamic_anomaly_threshold(self) -> float:
        """Return the graduated alert threshold based on ml_hours_ingested.

        Reads hours from the shared SentinelDataSync singleton so the
        EventIntelligenceService stays decoupled from the ML feeder.
        Returns the static default if the singleton is unavailable.
        """
        try:
            from app.services.sentinel_data_sync import get_sentinel_data_sync

            sync = get_sentinel_data_sync()
            hours = sync.ml_feeder.hours_ingested
            return get_anomaly_alert_threshold(hours)
        except Exception:
            # Fallback to conservative static default if singleton is not available
            return DEFAULT_ANOMALY_SCORE_THRESHOLD

    async def _check_setpoint_drift(
        self, equipment_id: str, site_id: str, telemetry: dict[str, Any]
    ) -> OperationalEvent | None:
        """Detect setpoint drift from baseline.

        Triggers when the current setpoint differs from the baseline
        setpoint by more than the configured threshold (default 1 deg C).
        """
        setpoint = telemetry.get("setpoint") or telemetry.get("setpoint_temp")
        baseline = telemetry.get("baseline_setpoint") or telemetry.get("design_setpoint")

        if setpoint is None or baseline is None:
            return None

        try:
            setpoint = float(setpoint)
            baseline = float(baseline)
        except (ValueError, TypeError):
            return None

        drift = abs(setpoint - baseline)
        if drift <= self._setpoint_drift_threshold:
            return None

        return OperationalEvent(
            event_id=_generate_event_id(),
            event_type=OperationalEventType.SETPOINT_DRIFT,
            equipment_id=equipment_id,
            site_id=site_id,
            severity=EventSeverity.WARNING,
            timestamp=datetime.now(UTC),
            signals=[{"point": "setpoint", "value": setpoint, "baseline": baseline}],
            description=(
                f"{equipment_id}: setpoint {setpoint:.1f}C has drifted {drift:.1f}C from baseline {baseline:.1f}C"
            ),
            threshold_value=self._setpoint_drift_threshold,
            actual_value=setpoint,
        )

    async def _check_threshold_breach(
        self, equipment_id: str, site_id: str, telemetry: dict[str, Any]
    ) -> OperationalEvent | None:
        """Generic threshold check for points with configured min/max.

        Looks for a 'thresholds' dict in telemetry with per-point min/max:
        {"thresholds": {"supply_temp": {"min": 5, "max": 15}, ...}}
        """
        thresholds = telemetry.get("thresholds")
        if not isinstance(thresholds, dict):
            return None

        breaches: list[dict[str, Any]] = []
        for point_name, limits in thresholds.items():
            if not isinstance(limits, dict):
                continue

            value = telemetry.get(point_name)
            if value is None:
                continue

            try:
                value = float(value)
            except (ValueError, TypeError):
                continue

            point_min = limits.get("min")
            point_max = limits.get("max")

            if point_min is not None and value < float(point_min):
                breaches.append(
                    {
                        "point": point_name,
                        "value": value,
                        "min": point_min,
                        "breach": "below_min",
                    }
                )
            elif point_max is not None and value > float(point_max):
                breaches.append(
                    {
                        "point": point_name,
                        "value": value,
                        "max": point_max,
                        "breach": "above_max",
                    }
                )

        if not breaches:
            return None

        severity = EventSeverity.HIGH if len(breaches) >= 2 else EventSeverity.WARNING

        return OperationalEvent(
            event_id=_generate_event_id(),
            event_type=OperationalEventType.THRESHOLD_BREACH,
            equipment_id=equipment_id,
            site_id=site_id,
            severity=severity,
            timestamp=datetime.now(UTC),
            signals=breaches,
            description=(
                f"{equipment_id}: {len(breaches)} threshold breach(es) ({', '.join(b['point'] for b in breaches)})"
            ),
            actual_value=breaches[0]["value"] if len(breaches) == 1 else None,
        )

    # ------------------------------------------------------------------
    # Core evaluation
    # ------------------------------------------------------------------

    async def evaluate_equipment(
        self, equipment_id: str, site_id: str, telemetry: dict[str, Any]
    ) -> list[OperationalEvent]:
        """Evaluate all rules against equipment telemetry.

        Args:
            equipment_id: Equipment code (e.g. S002-FCU-101).
            site_id: Site identifier (e.g. site-002).
            telemetry: Operating data dict from equipment.

        Returns:
            List of detected operational events.
        """
        equip_type = self._extract_equipment_type(equipment_id)
        events: list[OperationalEvent] = []

        for rule in self._rules:
            # Check if rule applies to this equipment type
            if rule.equipment_types and equip_type not in rule.equipment_types:
                continue

            try:
                event = await rule.check(equipment_id, site_id, telemetry)
                if event is not None:
                    # Track duration via active conditions
                    condition_key = f"{equipment_id}:{rule.event_type.value}"
                    now = time.monotonic()

                    existing = self._active_conditions.get(condition_key)
                    if existing is not None:
                        # Update duration
                        duration = (now - existing.first_detected) / 60.0
                        event.duration_minutes = round(duration, 1)
                        event.correlation_id = existing.event.event_id
                        existing.last_detected = now
                        existing.event = event
                    else:
                        # New condition
                        self._active_conditions[condition_key] = _ActiveCondition(
                            event=event,
                            first_detected=now,
                            last_detected=now,
                        )

                    events.append(event)
            except Exception as e:
                logger.warning(
                    "Rule %s failed for %s: %s",
                    rule.rule_id,
                    equipment_id,
                    e,
                )

        # Clear resolved conditions (rules that did NOT fire)
        fired_keys = {f"{equipment_id}:{e.event_type.value}" for e in events}
        stale_keys = [
            k for k in list(self._active_conditions.keys()) if k.startswith(f"{equipment_id}:") and k not in fired_keys
        ]
        for k in stale_keys:
            del self._active_conditions[k]

        return events

    async def process_site(
        self,
        site_id: str,
        equipment_telemetry: dict[str, dict[str, Any]] | None = None,
    ) -> list[OperationalEvent]:
        """Process all equipment in a site, detect events, emit to bus.

        This is the main entry point, called periodically by the scheduler
        or on-demand via the API.

        Args:
            site_id: Site identifier.
            equipment_telemetry: Optional pre-loaded telemetry dict keyed
                by equipment_id. If None, attempts to load from repository.

        Returns:
            All detected operational events.
        """
        if equipment_telemetry is None:
            equipment_telemetry = await self._load_site_telemetry(site_id)

        all_events: list[OperationalEvent] = []
        bus = get_event_bus()

        for equipment_id, telemetry in equipment_telemetry.items():
            events = await self.evaluate_equipment(equipment_id, site_id, telemetry)
            for event in events:
                # Deduplicate: only emit if this is a new condition or severity changed
                condition_key = f"{equipment_id}:{event.event_type.value}"
                active = self._active_conditions.get(condition_key)
                is_new = active is not None and active.event.event_id == event.event_id

                if is_new or event.duration_minutes is None:
                    # New event - emit to bus
                    try:
                        sentinel_event = event.to_sentinel_event()
                        await bus.emit(sentinel_event)
                    except Exception as e:
                        logger.error("Failed to emit event %s: %s", event.event_id, e)

                self._event_history.append(event)
                all_events.append(event)

        logger.info(
            "Processed site %s: %d equipment, %d events detected",
            site_id,
            len(equipment_telemetry),
            len(all_events),
        )
        return all_events

    async def _load_site_telemetry(self, site_id: str) -> dict[str, dict[str, Any]]:
        """Load equipment telemetry for a site from the repository.

        Uses lazy import to avoid circular dependencies and ensure
        zero side effects at import time.

        Args:
            site_id: Site identifier.

        Returns:
            Dict mapping equipment_id to operating_data.
        """
        result: dict[str, dict[str, Any]] = {}
        try:
            from app.database.repositories.equipment_repository import EquipmentRepository

            repo = EquipmentRepository()
            equipment_list = repo.get_by_site_code(site_id)

            for eq in equipment_list:
                code = eq.get("code")
                if not code:
                    continue
                # operating_data may not be in list columns; need detail fetch
                operating_data = eq.get("operating_data")
                if operating_data and isinstance(operating_data, dict):
                    result[code] = operating_data
        except Exception as e:
            logger.warning("Failed to load telemetry for site %s: %s", site_id, e)

        return result

    # ------------------------------------------------------------------
    # Query methods
    # ------------------------------------------------------------------

    async def get_active_events(
        self,
        site_id: str | None = None,
        equipment_id: str | None = None,
    ) -> list[OperationalEvent]:
        """Get currently active (unresolved) operational events.

        Args:
            site_id: Optional filter by site.
            equipment_id: Optional filter by equipment.

        Returns:
            List of active OperationalEvent objects.
        """
        events = [ac.event for ac in self._active_conditions.values()]

        if site_id:
            events = [e for e in events if e.site_id == site_id]
        if equipment_id:
            events = [e for e in events if e.equipment_id == equipment_id]

        return events

    async def get_event_summary(self, site_id: str) -> dict[str, Any]:
        """Get summary of events for a site (counts by type, severity).

        Args:
            site_id: Site identifier.

        Returns:
            Dict with total count, counts by type, counts by severity,
            and the most recent events.
        """
        active = await self.get_active_events(site_id=site_id)

        by_type: dict[str, int] = {}
        by_severity: dict[str, int] = {}

        for event in active:
            by_type[event.event_type.value] = by_type.get(event.event_type.value, 0) + 1
            by_severity[event.severity.value] = by_severity.get(event.severity.value, 0) + 1

        # Recent history for this site
        recent = [e.to_dict() for e in reversed(self._event_history) if e.site_id == site_id][:20]

        return {
            "site_id": site_id,
            "active_count": len(active),
            "by_type": by_type,
            "by_severity": by_severity,
            "recent_events": recent,
        }

    async def get_event_history(
        self,
        site_id: str | None = None,
        equipment_id: str | None = None,
        event_type: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Get event history with optional filters.

        Args:
            site_id: Optional filter by site.
            equipment_id: Optional filter by equipment.
            event_type: Optional filter by event type.
            limit: Maximum results to return.

        Returns:
            List of event dicts, most recent first.
        """
        results: list[dict[str, Any]] = []

        for event in reversed(self._event_history):
            if site_id and event.site_id != site_id:
                continue
            if equipment_id and event.equipment_id != equipment_id:
                continue
            if event_type and event.event_type.value != event_type:
                continue

            results.append(event.to_dict())
            if len(results) >= limit:
                break

        return results

    async def get_event_by_id(self, event_id: str) -> dict[str, Any] | None:
        """Get a specific event by its ID.

        Searches active conditions first, then history.

        Args:
            event_id: The event ID to look up.

        Returns:
            Event dict or None if not found.
        """
        # Check active conditions
        for ac in self._active_conditions.values():
            if ac.event.event_id == event_id:
                return ac.event.to_dict()

        # Check history
        for event in self._event_history:
            if event.event_id == event_id:
                return event.to_dict()

        return None


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_service: EventIntelligenceService | None = None


def get_event_intelligence_service() -> EventIntelligenceService:
    """Get or create the EventIntelligenceService singleton.

    Returns:
        The EventIntelligenceService singleton instance.
    """
    global _service
    if _service is None:
        _service = EventIntelligenceService()
        logger.info("EventIntelligenceService created")
    return _service


def reset_event_intelligence_service() -> None:
    """Reset the singleton for testing. Clears all state."""
    global _service
    _service = None
