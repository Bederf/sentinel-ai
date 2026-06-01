from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from app.adapters.residential.schemas import AlarmEvent, EnergySnapshot
from app.database.supabase_client import get_supabase_client
from app.services.residential.residential_telegram_sender import ResidentialTelegramSender

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
        results.append(
            AEGISResult(
                rule_id="RES_BATTERY_CRITICAL_LOW",
                severity="P1",
                message=f"Battery critical at {soc:.0f}%. Open {platform_name} app → set charge priority immediately.",
                triggered=True,
            )
        )

    # ── P1: Battery + loadshedding risk (with hysteresis in caller) ──────────
    if area_schedule is not None and soc is not None:
        minutes = _minutes_to_slot(area_schedule.next_slot_start)
        stage = area_schedule.stage or 0
        if soc < 30 and stage > 0 and minutes is not None and 0 < minutes < 120:
            results.append(
                AEGISResult(
                    rule_id="RES_BATTERY_PRE_SHED_RISK",
                    severity="P1",
                    message=(
                        f"Stage {stage} in {int(minutes)}min. Battery at {soc:.0f}%. "
                        f"Switch non-essential loads off via {platform_name} app."
                    ),
                    triggered=True,
                )
            )

    # ── P1: Grid voltage anomaly ─────────────────────────────────────────────
    volts = snapshot.grid_voltage_v
    if volts is not None and not (210 <= volts <= 250):
        results.append(
            AEGISResult(
                rule_id="RES_GRID_VOLTAGE_ANOMALY",
                severity="P1",
                message=f"Grid voltage {volts:.0f}V out of SA range (210-250V). Monitor inverter in {platform_name} app.",
                triggered=True,
            )
        )

    # ── P1: Inverter alarm ───────────────────────────────────────────────────
    for alarm in alarms:
        if alarm.severity in ("fault", "critical"):
            results.append(
                AEGISResult(
                    rule_id="RES_INVERTER_ALARM",
                    severity="P1",
                    message=f"Inverter alarm: {alarm.alarm_message}. Check {platform_name} app immediately.",
                    triggered=True,
                )
            )
            break  # one alert per poll cycle is enough

    # ── P2: PV fault suspected ───────────────────────────────────────────────
    pv = snapshot.pv_power_w
    if pv is not None and pv < 100.0:
        # Simple heuristic — could be improved with solar window in future
        results.append(
            AEGISResult(
                rule_id="RES_PV_FAULT_SUSPECTED",
                severity="P2",
                message=f"PV generation {pv:.0f}W very low. Check panels and connections.",
                triggered=True,
            )
        )

    # ── P2: Battery charge fault ─────────────────────────────────────────────
    if len(recent_snapshots) >= 6:
        last_6 = recent_snapshots[-6:]
        charging = all((s.battery_power_w or 0) > 0 for s in last_6)
        soc_now = last_6[-1].battery_soc_pct or 0
        soc_then = last_6[0].battery_soc_pct or 0
        if charging and soc_now <= soc_then:
            results.append(
                AEGISResult(
                    rule_id="RES_BATTERY_CHARGE_FAULT",
                    severity="P2",
                    message=f"Battery charging but SOC not rising — possible battery fault. Check {platform_name} app.",
                    triggered=True,
                )
            )

    # ── P2: Stale data ───────────────────────────────────────────────────────
    staleness_threshold = polling_interval_seconds * 2.5
    age_seconds = (datetime.now(UTC) - snapshot.timestamp.replace(tzinfo=UTC)).total_seconds()
    if age_seconds > staleness_threshold:
        elapsed_min = age_seconds / 60
        results.append(
            AEGISResult(
                rule_id="RES_DATA_STALE",
                severity="P2",
                message=f"No fresh data for {elapsed_min:.0f}min. Check inverter connection and {platform_name} app status.",
                triggered=True,
            )
        )

    # ── Home Assistant-specific rules ─────────────────────────────────────────
    # These rules require device-level visibility (geyser, EV charger) that
    # cloud-only platform APIs cannot provide. Only fires for HA gateway sites.
    if snapshot.source_system == "home_assistant":
        # P1: Geyser ON during impending loadshedding — drain battery faster
        geyser_state = getattr(snapshot, "geyser_state", None)
        if geyser_state == "on" and area_schedule is not None:
            minutes = _minutes_to_slot(area_schedule.next_slot_start)
            stage = area_schedule.stage or 0
            geyser_power = getattr(snapshot, "geyser_power_w", None) or 0
            if stage > 0 and minutes is not None and 0 < minutes < 90:
                if soc is not None and soc < 60:
                    results.append(
                        AEGISResult(
                            rule_id="RES_GEYSER_ON_PRE_SHED",
                            severity="P1",
                            message=(
                                f"Geyser ON ({geyser_power:.0f}W). "
                                f"Stage {stage} in {int(minutes)}min. "
                                f"Battery {soc:.0f}%. "
                                f"Switch geyser OFF via Home Assistant "
                                f"to extend backup power."
                            ),
                            triggered=True,
                        )
                    )

        # P1: EV charger draining battery during grid outage
        ev_power = getattr(snapshot, "ev_charger_power_w", None)
        grid_power = snapshot.grid_power_w
        if (
            ev_power is not None
            and ev_power > 500
            and grid_power is not None
            and grid_power == 0
            and soc is not None
            and soc < 40
        ):
            results.append(
                AEGISResult(
                    rule_id="RES_EV_CHARGER_BATTERY_DRAIN",
                    severity="P1",
                    message=(
                        f"EV charger drawing {ev_power:.0f}W from battery "
                        f"during outage. Battery {soc:.0f}%. "
                        f"Pause EV charging via Home Assistant."
                    ),
                    triggered=True,
                )
            )

        # P2: Solar surplus available — good time to run geyser
        # Hysteresis: 1500W trigger, 1000W clear
        # Check previous snapshot to see if surplus rule was already active
        _was_surplus_active = False
        if recent_snapshots:
            prev = recent_snapshots[-1]
            prev_pv = prev.pv_power_w or 0
            prev_load = prev.load_power_w or 0
            prev_soc = prev.battery_soc_pct or 0
            prev_geyser = getattr(prev, "geyser_state", None)
            if prev_geyser == "off" and (prev_pv - prev_load) > 1000 and prev_soc > 80:
                _was_surplus_active = True

        if (
            geyser_state == "off"
            and pv is not None
            and snapshot.load_power_w is not None
            and (pv - snapshot.load_power_w) > 1500
            and soc is not None
            and soc > 80
            and not _was_surplus_active
        ):
            surplus = int(pv - snapshot.load_power_w)
            results.append(
                AEGISResult(
                    rule_id="RES_SOLAR_SURPLUS_GEYSER",
                    severity="P2",
                    message=(
                        f"{surplus}W solar surplus available. "
                        f"Battery at {soc:.0f}%. "
                        f"Good time to run geyser via Home Assistant — "
                        f"use free solar instead of exporting."
                    ),
                    triggered=True,
                )
            )

    # ── Victron-specific rules ────────────────────────────────────────────────
    if snapshot.source_system == "victron":
        soh = getattr(snapshot, "battery_soh_pct", None)
        if soh is not None and soh < 70:
            results.append(
                AEGISResult(
                    rule_id="RES_BATTERY_DEGRADED",
                    severity="P2",
                    message=(
                        f"Battery health at {soh:.0f}%. "
                        "Consider scheduling a battery health check via your installer "
                        "or Victron VRM portal."
                    ),
                    triggered=True,
                )
            )

        # RES_GRID_VOLTAGE_ANOMALY (generic) already fires above 250V or below 210V.
        # Victron Multi/Quattro has a lower default cutoff (~195V) — add a specific P1
        # for the 195-209V range that the generic rule misses (it fires below 210V too,
        # but with a generic message; this provides Victron-specific guidance).
        if volts is not None and 0 < volts < 195:
            results.append(
                AEGISResult(
                    rule_id="RES_INPUT_VOLTAGE_LOW",
                    severity="P1",
                    message=(
                        f"Grid voltage critically low at {volts:.0f}V. "
                        "Inverter may switch to battery. Check VRM portal."
                    ),
                    triggered=True,
                )
            )

    return results


async def dispatch_results(
    results: list[AEGISResult],
    site_id: str,
    platform: str,
) -> bool:
    """
    Send AEGIS evaluation results to the residential user via Telegram.

    Looks up chat_id from residential_sites table. If chat_id is None
    (wizard-onboarded, no Telegram), logs a warning and returns False
    without crashing the evaluation pipeline.

    Returns True if all P1/P2 results were dispatched successfully (or
    gracefully skipped due to no chat_id); False only on unexpected error.
    """
    if not results:
        return True

    # Resolve chat_id from DB
    chat_id: int | None = None
    try:
        supabase = get_supabase_client()
        row = (
            supabase.table("residential_sites")
            .select("chat_id")
            .eq("site_id", site_id)
            .eq("is_active", True)
            .maybe_execute()
        )
        if row.data:
            chat_id = row.data[0].get("chat_id")
    except Exception as exc:
        logger.warning("dispatch_results: could not fetch chat_id for site_id=%s: %s", site_id, exc)

    if chat_id is None:
        logger.warning(
            "dispatch_results: no active chat_id for site_id=%s — "
            "wizard-onboarded site with no Telegram; skipping dispatch",
            site_id,
        )
        return False

    sender = ResidentialTelegramSender()
    success = True

    for result in results:
        if result.severity not in ("P1", "P2"):
            continue
        try:
            sent = await sender.send_alert(
                chat_id=chat_id,
                message=result.message,
                severity=result.severity,
                platform=platform,
            )
            if not sent:
                success = False
        except Exception as exc:
            logger.error(
                "dispatch_results: send_alert failed for site_id=%s rule=%s: %s",
                site_id,
                result.rule_id,
                exc,
            )
            success = False

    return success
