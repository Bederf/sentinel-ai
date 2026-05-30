from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from app.adapters.residential.schemas import AlarmEvent, EnergySnapshot

logger = logging.getLogger(__name__)


@dataclass
class AEGISResult:
    rule_id: str
    severity: str  # "P1" | "P2"
    message: str
    triggered: bool


def _minutes_to_slot(next_slot_start: datetime | None) -> float | None:
    if next_slot_start is None:
        return None
    delta = (next_slot_start - datetime.now(UTC)).total_seconds()
    return delta / 60.0


def evaluate(
    snapshot: EnergySnapshot,
    area_schedule,  # AreaSchedule | None from eskomsepush_client
    recent_snapshots: list[EnergySnapshot],
    alarms: list[AlarmEvent],
    platform_name: str,
    polling_interval_seconds: int = 300,
) -> list[AEGISResult]:
    """Evaluate all residential AEGIS rules. Returns triggered results only."""
    results: list[AEGISResult] = []

    # ── P1: Battery critical ─────────────────────────────────────────────────
    soc = snapshot.battery_soc_pct
    if soc is not None and soc < 10:
        results.append(AEGISResult(
            rule_id="RES_BATTERY_CRITICAL_LOW",
            severity="P1",
            message=f"Battery critical at {soc:.0f}%. Open {platform_name} app → set charge priority immediately.",
            triggered=True,
        ))

    # ── P1: Battery + loadshedding risk (with hysteresis in caller) ──────────
    if area_schedule is not None and soc is not None:
        minutes = _minutes_to_slot(area_schedule.next_slot_start)
        stage = area_schedule.stage or 0
        if soc < 30 and stage > 0 and minutes is not None and 0 < minutes < 120:
            results.append(AEGISResult(
                rule_id="RES_BATTERY_PRE_SHED_RISK",
                severity="P1",
                message=(
                    f"Stage {stage} in {int(minutes)}min. Battery at {soc:.0f}%. "
                    f"Switch non-essential loads off via {platform_name} app."
                ),
                triggered=True,
            ))

    # ── P1: Grid voltage anomaly ─────────────────────────────────────────────
    volts = snapshot.grid_voltage_v
    if volts is not None and not (210 <= volts <= 250):
        results.append(AEGISResult(
            rule_id="RES_GRID_VOLTAGE_ANOMALY",
            severity="P1",
            message=f"Grid voltage {volts:.0f}V out of SA range (210-250V). Monitor inverter in {platform_name} app.",
            triggered=True,
        ))

    # ── P1: Inverter alarm ───────────────────────────────────────────────────
    for alarm in alarms:
        if alarm.severity in ("fault", "critical"):
            results.append(AEGISResult(
                rule_id="RES_INVERTER_ALARM",
                severity="P1",
                message=f"Inverter alarm: {alarm.alarm_message}. Check {platform_name} app immediately.",
                triggered=True,
            ))
            break  # one alert per poll cycle is enough

    # ── P2: PV fault suspected ───────────────────────────────────────────────
    pv = snapshot.pv_power_w
    if pv is not None and pv < 100.0:
        # Simple heuristic — could be improved with solar window in future
        results.append(AEGISResult(
            rule_id="RES_PV_FAULT_SUSPECTED",
            severity="P2",
            message=f"PV generation {pv:.0f}W very low. Check panels and connections.",
            triggered=True,
        ))

    # ── P2: Battery charge fault ─────────────────────────────────────────────
    if len(recent_snapshots) >= 6:
        last_6 = recent_snapshots[-6:]
        charging = all(
            (s.battery_power_w or 0) > 0 for s in last_6
        )
        soc_now = last_6[-1].battery_soc_pct or 0
        soc_then = last_6[0].battery_soc_pct or 0
        if charging and soc_now <= soc_then:
            results.append(AEGISResult(
                rule_id="RES_BATTERY_CHARGE_FAULT",
                severity="P2",
                message=f"Battery charging but SOC not rising — possible battery fault. Check {platform_name} app.",
                triggered=True,
            ))

    # ── P2: Stale data ───────────────────────────────────────────────────────
    staleness_threshold = polling_interval_seconds * 2.5
    age_seconds = (datetime.now(UTC) - snapshot.timestamp.replace(tzinfo=UTC)).total_seconds()
    if age_seconds > staleness_threshold:
        elapsed_min = age_seconds / 60
        results.append(AEGISResult(
            rule_id="RES_DATA_STALE",
            severity="P2",
            message=f"No fresh data for {elapsed_min:.0f}min. Check inverter connection and {platform_name} app status.",
            triggered=True,
        ))

    # ── Victron-specific rules ────────────────────────────────────────────────
    if snapshot.source_system == "victron":
        soh = getattr(snapshot, "battery_soh_pct", None)
        if soh is not None and soh < 70:
            results.append(AEGISResult(
                rule_id="RES_BATTERY_DEGRADED",
                severity="P2",
                message=(
                    f"Battery health at {soh:.0f}%. "
                    "Consider scheduling a battery health check via your installer "
                    "or Victron VRM portal."
                ),
                triggered=True,
            ))

        # RES_GRID_VOLTAGE_ANOMALY (generic) already fires above 250V or below 210V.
        # Victron Multi/Quattro has a lower default cutoff (~195V) — add a specific P1
        # for the 195-209V range that the generic rule misses (it fires below 210V too,
        # but with a generic message; this provides Victron-specific guidance).
        if volts is not None and 0 < volts < 195:
            results.append(AEGISResult(
                rule_id="RES_INPUT_VOLTAGE_LOW",
                severity="P1",
                message=(
                    f"Grid voltage critically low at {volts:.0f}V. "
                    "Inverter may switch to battery. Check VRM portal."
                ),
                triggered=True,
            ))

    return results
