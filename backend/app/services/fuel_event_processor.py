"""Fuel Event Processor — evaluates telemetry against thresholds to detect
7 event types, compute derived calculations, and track generator fuel
consumption per runtime session (Phase 149).

Transforms raw fuel telemetry (ingested by Phase 148 MQTT listener) into
actionable events for downstream alerting.

Usage:
    from app.services.fuel_event_processor import get_fuel_event_processor

    processor = get_fuel_event_processor()
    events = await processor.process_telemetry(telemetry, tank_config)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.config.settings import settings
from app.models.fuel import FuelEvent, FuelEventType, FuelTankConfig, FuelTelemetry

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal dataclasses
# ---------------------------------------------------------------------------


@dataclass
class _GenSession:
    """Tracks a generator runtime session for fuel consumption linkage."""

    generator_id: str
    tank_id: str
    start_time: float  # monotonic or ts
    start_level_litres: float


@dataclass
class _ActiveCondition:
    """Tracks a sustained condition (e.g. slow leak) by key."""

    condition_key: str
    started_at: float  # ts from telemetry
    readings_count: int = 0


# ---------------------------------------------------------------------------
# Importance mapping (reuse from fuel_mqtt_listener)
# ---------------------------------------------------------------------------


def _get_event_importance(event_type: str):
    """Map fuel event_type to Importance enum value."""
    from app.services.fuel_mqtt_listener import get_event_importance

    return get_event_importance(event_type)


# ---------------------------------------------------------------------------
# FuelEventProcessor
# ---------------------------------------------------------------------------


class FuelEventProcessor:
    """Evaluates fuel telemetry against configurable thresholds to detect
    events, compute derived values, and track generator consumption."""

    _instance: FuelEventProcessor | None = None

    def __init__(self) -> None:
        self._previous_readings: dict[str, FuelTelemetry] = {}  # tank_id -> last reading
        self._active_generator_sessions: dict[str, _GenSession] = {}  # generator_id -> session
        self._active_conditions: dict[str, _ActiveCondition] = {}  # condition_key -> state

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    async def process_telemetry(self, telemetry: FuelTelemetry, tank_config: FuelTankConfig) -> list[FuelEvent]:
        """Evaluate telemetry against thresholds, return detected events.

        Also mutates telemetry to fill derived fields (days_to_empty,
        consumption_anomaly, runtime_remaining_hrs).
        """
        previous = self._previous_readings.get(telemetry.tank_id)
        self._compute_derived(telemetry, tank_config, previous)

        events: list[FuelEvent] = []
        for check in (
            self._check_refill,
            self._check_theft,
            self._check_low_fuel,
            self._check_leak,
            self._check_temp,
            self._check_sensor_fault,
            self._check_runtime,
        ):
            evt = check(telemetry, previous, tank_config)
            if evt is not None:
                events.append(evt)

        # Store current reading as previous for next cycle
        self._previous_readings[telemetry.tank_id] = telemetry

        # Emit all detected events to event bus
        for evt in events:
            await self._emit_event(evt, telemetry)

        return events

    # ------------------------------------------------------------------
    # Event bus handler (called by bus.on("fuel.telemetry", ...))
    # ------------------------------------------------------------------

    async def handle_telemetry_event(self, event) -> None:
        """Handle a fuel.telemetry SentinelEvent from the event bus.

        Extracts telemetry data, looks up tank config, and processes.
        """
        from app.services.fuel_store import get_fuel_store

        payload = event.payload if hasattr(event, "payload") else {}
        tank_id = payload.get("tank_id", "")
        if not tank_id:
            return

        store = get_fuel_store()
        tank_config = store.get_tank_config(tank_id)
        if tank_config is None:
            logger.debug("No tank config for %s, skipping event processing", tank_id)
            return

        # Reconstruct a FuelTelemetry from the event payload
        telemetry = await store.get_latest_telemetry(tank_id)
        if telemetry is None:
            logger.debug("No telemetry available for %s, skipping", tank_id)
            return

        await self.process_telemetry(telemetry, tank_config)

    # ------------------------------------------------------------------
    # Derived calculations
    # ------------------------------------------------------------------

    def _compute_derived(
        self,
        telemetry: FuelTelemetry,
        tank_config: FuelTankConfig,
        previous: FuelTelemetry | None,
    ) -> None:
        """Mutate telemetry to fill days_to_empty, consumption_anomaly,
        runtime_remaining_hrs."""
        rate = telemetry.consumption_rate_lph if telemetry.consumption_rate_lph else 0.0
        safe_rate = max(rate, 0.01)

        # days_to_empty
        telemetry.days_to_empty = telemetry.fuel_level_litres / safe_rate / 24.0

        # runtime_remaining_hrs
        telemetry.runtime_remaining_hrs = telemetry.fuel_level_litres / safe_rate

        # consumption_anomaly — compare actual rate to spec
        spec = tank_config.consumption_spec_lph
        anomaly_threshold = self._get_threshold(
            tank_config, "consumption_anomaly_pct", settings.fuel_consumption_anomaly_pct
        )
        if spec > 0 and rate > 0:
            deviation_pct = abs(rate - spec) / spec * 100.0
            telemetry.consumption_anomaly = deviation_pct > anomaly_threshold
        else:
            telemetry.consumption_anomaly = False

    # ------------------------------------------------------------------
    # Detection rules
    # ------------------------------------------------------------------

    def _check_low_fuel(
        self,
        telemetry: FuelTelemetry,
        previous: FuelTelemetry | None,
        config: FuelTankConfig,
    ) -> FuelEvent | None:
        """Detect low fuel: below pct_2 = CRITICAL, below pct_1 = HIGH."""
        pct_1 = self._get_threshold(config, "low_alert_pct_1", settings.fuel_low_alert_pct_1)
        pct_2 = self._get_threshold(config, "low_alert_pct_2", settings.fuel_low_alert_pct_2)

        if telemetry.fuel_level_pct < pct_2:
            severity = "CRITICAL"
        elif telemetry.fuel_level_pct < pct_1:
            severity = "HIGH"
        else:
            return None

        return FuelEvent(
            node_id=telemetry.node_id,
            site_id=telemetry.site_id,
            tank_id=telemetry.tank_id,
            event_type=FuelEventType.LOW_FUEL,
            payload={
                "fuel_level_pct": telemetry.fuel_level_pct,
                "threshold_pct": pct_2 if severity == "CRITICAL" else pct_1,
                "severity": severity,
            },
            ts=telemetry.ts,
        )

    def _check_theft(
        self,
        telemetry: FuelTelemetry,
        previous: FuelTelemetry | None,
        config: FuelTankConfig,
    ) -> FuelEvent | None:
        """Detect theft: rapid fuel loss while generator is NOT running."""
        if previous is None:
            return None
        if telemetry.generator_running:
            return None  # Loss during generation is consumption, not theft

        time_delta_s = telemetry.ts - previous.ts
        if time_delta_s <= 0:
            return None

        time_delta_min = time_delta_s / 60.0
        loss_litres = previous.fuel_level_litres - telemetry.fuel_level_litres
        if loss_litres <= 0:
            return None

        loss_rate_lpm = loss_litres / time_delta_min
        threshold = self._get_threshold(config, "theft_rate_threshold_lpm", settings.fuel_theft_rate_threshold_lpm)

        if loss_rate_lpm > threshold:
            return FuelEvent(
                node_id=telemetry.node_id,
                site_id=telemetry.site_id,
                tank_id=telemetry.tank_id,
                event_type=FuelEventType.THEFT_ALERT,
                payload={
                    "loss_rate_lpm": round(loss_rate_lpm, 2),
                    "threshold_lpm": threshold,
                    "loss_litres": round(loss_litres, 2),
                    "time_delta_min": round(time_delta_min, 2),
                },
                ts=telemetry.ts,
            )
        return None

    def _check_refill(
        self,
        telemetry: FuelTelemetry,
        previous: FuelTelemetry | None,
        config: FuelTankConfig,
    ) -> FuelEvent | None:
        """Detect refill: level jumps above threshold."""
        if previous is None:
            return None

        jump_pct = telemetry.fuel_level_pct - previous.fuel_level_pct
        threshold = self._get_threshold(config, None, settings.fuel_refill_jump_pct)

        if jump_pct > threshold:
            return FuelEvent(
                node_id=telemetry.node_id,
                site_id=telemetry.site_id,
                tank_id=telemetry.tank_id,
                event_type=FuelEventType.REFILL_DETECTED,
                payload={
                    "jump_pct": round(jump_pct, 2),
                    "previous_pct": previous.fuel_level_pct,
                    "current_pct": telemetry.fuel_level_pct,
                },
                ts=telemetry.ts,
            )
        return None

    def _check_leak(
        self,
        telemetry: FuelTelemetry,
        previous: FuelTelemetry | None,
        config: FuelTankConfig,
    ) -> FuelEvent | None:
        """Detect leak: sustained slow fuel loss without generator running."""
        if previous is None:
            return None
        if telemetry.generator_running:
            # Clear active leak condition if generator starts
            condition_key = f"leak:{telemetry.tank_id}"
            self._active_conditions.pop(condition_key, None)
            return None

        loss_litres = previous.fuel_level_litres - telemetry.fuel_level_litres
        if loss_litres <= 0:
            # No loss, clear condition
            condition_key = f"leak:{telemetry.tank_id}"
            self._active_conditions.pop(condition_key, None)
            return None

        condition_key = f"leak:{telemetry.tank_id}"
        sustained_minutes = settings.fuel_leak_sustained_minutes

        if condition_key not in self._active_conditions:
            self._active_conditions[condition_key] = _ActiveCondition(
                condition_key=condition_key,
                started_at=previous.ts,
                readings_count=1,
            )
            return None

        condition = self._active_conditions[condition_key]
        condition.readings_count += 1
        elapsed_minutes = (telemetry.ts - condition.started_at) / 60.0

        if elapsed_minutes >= sustained_minutes:
            # Leak confirmed — clear condition and fire event
            self._active_conditions.pop(condition_key, None)
            return FuelEvent(
                node_id=telemetry.node_id,
                site_id=telemetry.site_id,
                tank_id=telemetry.tank_id,
                event_type=FuelEventType.LEAK_DETECTED,
                payload={
                    "sustained_minutes": round(elapsed_minutes, 1),
                    "readings_count": condition.readings_count,
                },
                ts=telemetry.ts,
            )
        return None

    def _check_temp(
        self,
        telemetry: FuelTelemetry,
        previous: FuelTelemetry | None,
        config: FuelTankConfig,
    ) -> FuelEvent | None:
        """Detect fuel temperature outside acceptable range."""
        temp_min = settings.fuel_temp_min_c
        temp_max = settings.fuel_temp_max_c

        if telemetry.fuel_temp_c < temp_min:
            return FuelEvent(
                node_id=telemetry.node_id,
                site_id=telemetry.site_id,
                tank_id=telemetry.tank_id,
                event_type=FuelEventType.TEMP_ALERT,
                payload={
                    "fuel_temp_c": telemetry.fuel_temp_c,
                    "threshold_min_c": temp_min,
                    "severity": "HIGH",
                },
                ts=telemetry.ts,
            )
        if telemetry.fuel_temp_c > temp_max:
            return FuelEvent(
                node_id=telemetry.node_id,
                site_id=telemetry.site_id,
                tank_id=telemetry.tank_id,
                event_type=FuelEventType.TEMP_ALERT,
                payload={
                    "fuel_temp_c": telemetry.fuel_temp_c,
                    "threshold_max_c": temp_max,
                    "severity": "HIGH",
                },
                ts=telemetry.ts,
            )
        return None

    def _check_sensor_fault(
        self,
        telemetry: FuelTelemetry,
        previous: FuelTelemetry | None,
        config: FuelTankConfig,
    ) -> FuelEvent | None:
        """Detect sensor fault (already flagged by validate_sensor_reading)."""
        if telemetry.sensor_fault:
            return FuelEvent(
                node_id=telemetry.node_id,
                site_id=telemetry.site_id,
                tank_id=telemetry.tank_id,
                event_type=FuelEventType.SENSOR_FAULT,
                payload={
                    "sensor_ma": telemetry.sensor_ma,
                    "severity": "MEDIUM",
                },
                ts=telemetry.ts,
            )
        return None

    def _check_runtime(
        self,
        telemetry: FuelTelemetry,
        previous: FuelTelemetry | None,
        config: FuelTankConfig,
    ) -> FuelEvent | None:
        """Detect generator runtime complete (True->False transition)."""
        gen_id = telemetry.generator_id or config.generator_id
        if not gen_id:
            return None

        if telemetry.generator_running:
            # Generator just started or is still running — track session
            if gen_id not in self._active_generator_sessions:
                self._active_generator_sessions[gen_id] = _GenSession(
                    generator_id=gen_id,
                    tank_id=telemetry.tank_id,
                    start_time=telemetry.ts,
                    start_level_litres=telemetry.fuel_level_litres,
                )
            return None

        # Generator not running — check for True->False transition
        if previous is None or not previous.generator_running:
            return None  # Was already off

        # True->False transition detected — close session
        session = self._active_generator_sessions.pop(gen_id, None)
        if session is None:
            # No tracked session, construct from previous reading
            session = _GenSession(
                generator_id=gen_id,
                tank_id=telemetry.tank_id,
                start_time=previous.ts,
                start_level_litres=previous.fuel_level_litres,
            )

        runtime_seconds = telemetry.ts - session.start_time
        runtime_hours = runtime_seconds / 3600.0
        fuel_burned = session.start_level_litres - telemetry.fuel_level_litres

        # Compare actual consumption vs spec
        spec = config.consumption_spec_lph
        expected_consumption = spec * runtime_hours if spec > 0 else 0
        anomaly_threshold = settings.fuel_consumption_anomaly_pct
        consumption_anomaly = False
        if expected_consumption > 0 and fuel_burned > 0:
            deviation_pct = abs(fuel_burned - expected_consumption) / expected_consumption * 100.0
            consumption_anomaly = deviation_pct > anomaly_threshold

        return FuelEvent(
            node_id=telemetry.node_id,
            site_id=telemetry.site_id,
            tank_id=telemetry.tank_id,
            event_type=FuelEventType.RUNTIME_COMPLETE,
            payload={
                "generator_id": gen_id,
                "runtime_hours": round(runtime_hours, 2),
                "fuel_burned_litres": round(fuel_burned, 2),
                "expected_consumption_litres": round(expected_consumption, 2),
                "consumption_anomaly": consumption_anomaly,
            },
            ts=telemetry.ts,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_threshold(config: FuelTankConfig, attr_name: str | None, global_default: float) -> float:
        """Return per-tank threshold if available, else global settings default."""
        if attr_name and hasattr(config, attr_name):
            val = getattr(config, attr_name, None)
            if val is not None:
                return float(val)
        return global_default

    async def _emit_event(self, fuel_event: FuelEvent, telemetry: FuelTelemetry) -> None:
        """Emit a detected fuel event to the SENTINEL event bus."""
        try:
            from app.services.event_bus import SentinelEvent, get_event_bus

            importance = _get_event_importance(fuel_event.event_type)
            await get_event_bus().emit(
                SentinelEvent(
                    event_type=f"fuel.{fuel_event.event_type}",
                    source="fuel_event_processor",
                    payload={
                        "tank_id": fuel_event.tank_id,
                        "event_subtype": fuel_event.event_type,
                        **fuel_event.payload,
                    },
                    importance=importance,
                    site_id=fuel_event.site_id,
                    equipment_id=fuel_event.tank_id,
                )
            )
        except Exception as exc:
            logger.debug("Event bus emit failed (non-fatal): %s", exc)


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_instance: FuelEventProcessor | None = None


def get_fuel_event_processor() -> FuelEventProcessor:
    """Return the singleton FuelEventProcessor instance."""
    global _instance
    if _instance is None:
        _instance = FuelEventProcessor()
    return _instance
