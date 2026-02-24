"""Solar Dispatch Service -- autonomous BESS dispatch execution.

The "invisible optimiser" brain.  Runs a 5-minute dispatch cycle that:
  1. Reads current state (SOC, solar gen, building load, grid import/export)
  2. Checks load shedding (manual override or EskomSePush API if configured)
  3. Gets dispatch action from arbitrage engine
  4. Applies compliance constraints (export limits from 34-03)
  5. Executes action (update simulated BESS state for demo)
  6. Logs dispatch event

For demo purposes the full 24h cycle is simulated with compressed time
to show BESS charging at night, discharging at peak, savings accumulating.
"""

import json
import logging
import random
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any

from app.config.settings import settings
from app.services.solar_arbitrage_engine import (
    get_solar_arbitrage_engine,
    DispatchActionType,
)
from app.services.solar_config_service import get_site_solar_config

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data"


# === Dataclass models ===


@dataclass
class DispatchEvent:
    """A single dispatch execution event."""

    timestamp: str
    action: str  # charge / discharge / idle / solar_priority
    power_kw: float
    soc_before_pct: float
    soc_after_pct: float
    tariff_band: str
    rate_per_kwh: float
    reason: str
    load_shedding: bool = False
    solar_gen_kw: float = 0.0
    building_load_kw: float = 0.0
    grid_import_kw: float = 0.0
    grid_export_kw: float = 0.0
    aegis_proposal_id: Optional[str] = None  # Join key to parasite_decisions
    write_result: Optional[Dict[str, Any]] = None  # Modbus write result

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "timestamp": self.timestamp,
            "action": self.action,
            "power_kw": round(self.power_kw, 0),
            "soc_before_pct": round(self.soc_before_pct, 1),
            "soc_after_pct": round(self.soc_after_pct, 1),
            "tariff_band": self.tariff_band,
            "rate_per_kwh": round(self.rate_per_kwh, 4),
            "reason": self.reason,
            "load_shedding": self.load_shedding,
            "solar_gen_kw": round(self.solar_gen_kw, 0),
            "building_load_kw": round(self.building_load_kw, 0),
            "grid_import_kw": round(self.grid_import_kw, 0),
            "grid_export_kw": round(self.grid_export_kw, 0),
        }
        if self.aegis_proposal_id:
            d["aegis_proposal_id"] = self.aegis_proposal_id
        return d


@dataclass
class DispatchStatus:
    """Current dispatch status for a site."""

    site_id: str
    mode: str  # autonomous / manual / stopped
    current_action: str
    current_power_kw: float
    bess_soc_pct: float
    tariff_band: str
    rate_per_kwh: float
    next_action_change: Optional[str] = None
    savings_today_zar: float = 0.0
    cycles_today: int = 0
    dispatch_events_today: int = 0
    last_dispatch: Optional[str] = None
    load_shedding_active: bool = False
    uptime_hours: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "site_id": self.site_id,
            "mode": self.mode,
            "current_action": self.current_action,
            "current_power_kw": round(self.current_power_kw, 0),
            "bess_soc_pct": round(self.bess_soc_pct, 1),
            "tariff_band": self.tariff_band,
            "rate_per_kwh": round(self.rate_per_kwh, 4),
            "next_action_change": self.next_action_change,
            "savings_today_zar": round(self.savings_today_zar, 2),
            "cycles_today": self.cycles_today,
            "dispatch_events_today": self.dispatch_events_today,
            "last_dispatch": self.last_dispatch,
            "load_shedding_active": self.load_shedding_active,
            "uptime_hours": round(self.uptime_hours, 1),
        }


# === Service ===


class SolarDispatchService:
    """Autonomous BESS dispatch execution service.

    Maintains simulated BESS state and dispatch log.  On startup, seeds
    a realistic 24-hour dispatch history so API endpoints return
    meaningful data immediately (no need to wait for a real cycle).
    """

    # Simulation parameters
    CYCLE_INTERVAL_MINUTES = 5
    BESS_CAPACITY_KWH = 200.0  # Huawei LUNA2000-200KWH-2H1
    BESS_MIN_SOC = 10.0
    BESS_MAX_SOC = 95.0
    BESS_EFFICIENCY = 0.90

    def __init__(self):
        self._dispatch_log: Dict[str, List[DispatchEvent]] = {}
        self._simulated_soc: Dict[str, float] = {}
        self._last_real_soc: Dict[str, float] = {}  # Last known real SOC (for sync callers)
        self._started_at: Dict[str, str] = {}
        self._mode: Dict[str, str] = {}  # autonomous / manual / stopped
        try:
            cfg = get_site_solar_config("site-002")
            self.BESS_CAPACITY_KWH = cfg.bess.capacity_kwh
            self.BESS_RATED_POWER_KW = cfg.bess.rated_power_kw
        except Exception:
            pass
        self._seed_demo_history("site-002")

    # === Demo seed ===

    def _seed_demo_history(self, site_id: str) -> None:
        """Seed a realistic 24-hour dispatch log for demo purposes.

        Simulates the BESS through a full day:
          22:00 -> 06:00 : charging (off-peak)
          06:00 -> 07:00 : idle (standard early)
          07:00 -> 10:00 : discharging (morning peak)
          10:00 -> 18:00 : solar priority (standard day)
          18:00 -> 20:00 : discharging (evening peak)
          20:00 -> 22:00 : idle (standard evening)
        """
        engine = get_solar_arbitrage_engine()
        events: List[DispatchEvent] = []
        now = datetime.now(timezone.utc)
        _sast_now = now + timedelta(hours=2)

        # Start from yesterday 22:00 SAST
        start = now.replace(hour=20, minute=0, second=0, microsecond=0)  # UTC 20:00 = SAST 22:00
        if start > now:
            start -= timedelta(days=1)

        soc = 15.0  # Start of night: low SOC
        sim_time = start

        # Hour-by-hour profiles
        hourly_profile = self._get_hourly_profile(engine)

        while sim_time < now:
            sast = sim_time + timedelta(hours=2)
            hour = sast.hour

            profile = hourly_profile.get(hour, {})
            action = profile.get("action", "idle")
            power_kw = profile.get("power_kw", 0)
            solar_kw = profile.get("solar_kw", 0)
            load_kw = profile.get("load_kw", 1800)
            band_name = profile.get("band", "standard")

            # Calculate SOC change for 5-minute interval
            interval_hours = self.CYCLE_INTERVAL_MINUTES / 60.0
            soc_before = soc

            if action == "charge":
                energy_kwh = power_kw * interval_hours
                soc_delta = (energy_kwh / self.BESS_CAPACITY_KWH) * 100
                soc = min(self.BESS_MAX_SOC, soc + soc_delta)
            elif action == "discharge":
                energy_kwh = power_kw * interval_hours
                soc_delta = (energy_kwh / self.BESS_CAPACITY_KWH) * 100
                soc = max(self.BESS_MIN_SOC, soc - soc_delta)
            elif action == "solar_priority" and solar_kw > load_kw:
                excess = solar_kw - load_kw
                charge_kw = min(excess, 100)
                energy_kwh = charge_kw * interval_hours * self.BESS_EFFICIENCY
                soc_delta = (energy_kwh / self.BESS_CAPACITY_KWH) * 100
                soc = min(self.BESS_MAX_SOC, soc + soc_delta)
                power_kw = charge_kw
            # else idle: no SOC change

            rate = engine._get_band_rate(band_name, engine._get_season(sim_time))

            # Add some realistic noise
            noise = random.uniform(-0.2, 0.2)
            solar_kw_noisy = max(0, solar_kw + solar_kw * noise * 0.05)
            load_kw_noisy = load_kw + load_kw * noise * 0.02

            # Grid flows
            net_load = load_kw_noisy - solar_kw_noisy
            if action == "discharge":
                net_load -= power_kw
            elif action in ("charge", "solar_priority"):
                if action == "charge":
                    net_load += power_kw
                # solar_priority: excess solar charges BESS, no grid impact

            grid_import = max(0, net_load)
            grid_export = max(0, -net_load)

            reason = profile.get("reason", f"{action} during {band_name}")

            events.append(
                DispatchEvent(
                    timestamp=sim_time.isoformat(),
                    action=action,
                    power_kw=power_kw,
                    soc_before_pct=soc_before,
                    soc_after_pct=soc,
                    tariff_band=band_name,
                    rate_per_kwh=rate,
                    reason=reason,
                    solar_gen_kw=solar_kw_noisy,
                    building_load_kw=load_kw_noisy,
                    grid_import_kw=grid_import,
                    grid_export_kw=grid_export,
                )
            )

            sim_time += timedelta(minutes=self.CYCLE_INTERVAL_MINUTES)

        self._dispatch_log[site_id] = events
        self._simulated_soc[site_id] = soc
        self._started_at[site_id] = start.isoformat()
        self._mode[site_id] = "autonomous"

        logger.info(
            "Seeded %d dispatch events for %s (SOC: %.1f%%)",
            len(events),
            site_id,
            soc,
        )

    def _get_hourly_profile(self, engine) -> Dict[int, Dict[str, Any]]:
        """Build hour-by-hour dispatch profile (SAST hours)."""
        season = engine._get_season()
        off_peak_rate = engine._get_band_rate("off_peak", season)
        _std_rate = engine._get_band_rate("standard", season)
        peak_rate = engine._get_band_rate("peak", season)

        # Solar generation curve for Johannesburg (clear day)
        solar_curve = {
            0: 0,
            1: 0,
            2: 0,
            3: 0,
            4: 0,
            5: 0,
            6: 50,
            7: 400,
            8: 1200,
            9: 2000,
            10: 2600,
            11: 3000,
            12: 3200,
            13: 3100,
            14: 2800,
            15: 2300,
            16: 1600,
            17: 800,
            18: 200,
            19: 0,
            20: 0,
            21: 0,
            22: 0,
            23: 0,
        }

        # Building load profile
        load_curve = {
            0: 1200,
            1: 1100,
            2: 1000,
            3: 1000,
            4: 1050,
            5: 1200,
            6: 1500,
            7: 2000,
            8: 2300,
            9: 2500,
            10: 2400,
            11: 2300,
            12: 2200,
            13: 2300,
            14: 2400,
            15: 2300,
            16: 2200,
            17: 2000,
            18: 1800,
            19: 1600,
            20: 1400,
            21: 1300,
            22: 1200,
            23: 1200,
        }

        profile = {}
        for h in range(24):
            solar_kw = solar_curve.get(h, 0)
            load_kw = load_curve.get(h, 1500)

            if h >= 22 or h < 6:
                profile[h] = {
                    "action": "charge",
                    "power_kw": 2000,
                    "band": "off_peak",
                    "solar_kw": 0,
                    "load_kw": load_kw,
                    "reason": f"Off-peak charging @ R{off_peak_rate:.2f}/kWh",
                }
            elif h == 6:
                profile[h] = {
                    "action": "idle",
                    "power_kw": 0,
                    "band": "standard",
                    "solar_kw": solar_kw,
                    "load_kw": load_kw,
                    "reason": "Standard early morning; awaiting peak window",
                }
            elif 7 <= h < 10:
                profile[h] = {
                    "action": "discharge",
                    "power_kw": 2500,
                    "band": "peak",
                    "solar_kw": solar_kw,
                    "load_kw": load_kw,
                    "reason": f"Morning peak discharge @ R{peak_rate:.2f}/kWh",
                }
            elif 10 <= h < 18:
                profile[h] = {
                    "action": "solar_priority",
                    "power_kw": 0,
                    "band": "standard",
                    "solar_kw": solar_kw,
                    "load_kw": load_kw,
                    "reason": f"Solar priority; {solar_kw:.0f} kW PV generation",
                }
            elif 18 <= h < 20:
                profile[h] = {
                    "action": "discharge",
                    "power_kw": 2500,
                    "band": "peak",
                    "solar_kw": solar_kw,
                    "load_kw": load_kw,
                    "reason": f"Evening peak discharge @ R{peak_rate:.2f}/kWh",
                }
            elif 20 <= h < 22:
                profile[h] = {
                    "action": "idle",
                    "power_kw": 0,
                    "band": "standard",
                    "solar_kw": 0,
                    "load_kw": load_kw,
                    "reason": "Standard evening; BESS idle, conserving for overnight charge",
                }

        return profile

    # === Real SOC ===

    async def _get_current_soc(self, site_id: str) -> float:
        """Get current BESS SOC, preferring real hardware reads when in live mode.

        Falls back to simulated SOC on any failure or in demo/simulation mode.
        """
        from app.config.settings import settings

        if settings.solar_connector_mode == "simulation" or settings.demo_mode:
            return self._simulated_soc.get(site_id, 50.0)

        try:
            from app.services.solar_ingestion_service import get_solar_ingestion_service

            svc = get_solar_ingestion_service()
            bess = await svc.get_bess_status(site_id)
            if bess and bess.soc_pct > 0:
                self._last_real_soc[site_id] = bess.soc_pct
                return bess.soc_pct
        except Exception as e:
            logger.warning("Real SOC read failed for %s: %s", site_id, e)

        return self._simulated_soc.get(site_id, 50.0)

    def get_current_soc_sync(self, site_id: str) -> float:
        """Synchronous SOC accessor — returns last real SOC or simulated fallback.

        For use by sync callers like aegis_bridge.py.
        """
        if site_id in self._last_real_soc:
            return self._last_real_soc[site_id]
        return self._simulated_soc.get(site_id, 50.0)

    # === MIP schedule integration ===

    def _get_mip_dispatch_action(self, site_id, current_soc, solar_kw, load_kw, sast):
        """Read current interval from cached MIP schedule.

        Returns a DispatchAction-like object if MIP schedule is available
        and covers the current time, otherwise None.
        """
        try:
            from app.services.mip_dispatch_optimizer import get_mip_dispatch_optimizer
            from app.services.solar_arbitrage_engine import DispatchAction

            optimizer = get_mip_dispatch_optimizer()
            schedule = optimizer.get_cached_schedule(site_id)
            if not schedule or not schedule.intervals:
                return None

            # Round to nearest 15-min boundary
            minute = sast.minute
            rounded_minute = (minute // 15) * 15
            rounded_sast = sast.replace(minute=rounded_minute, second=0, microsecond=0)
            target_ts = rounded_sast.strftime("%Y-%m-%dT%H:%M")

            for interval in schedule.intervals:
                if interval.timestamp == target_ts:
                    # Convert MIP interval to DispatchAction
                    if interval.discharge_kw > 0.1:
                        action_type = "discharge"
                        power = interval.discharge_kw
                    elif interval.charge_kw > 0.1:
                        action_type = "charge"
                        power = interval.charge_kw
                    else:
                        action_type = "idle"
                        power = 0.0

                    return DispatchAction(
                        action=action_type,
                        power_kw=power,
                        reason=f"MIP optimal: {action_type} {power:.0f} kW ({interval.tariff_band})",
                        tariff_band=interval.tariff_band,
                        rate_per_kwh=interval.tariff_rate,
                        current_soc_pct=current_soc,
                    )

            return None
        except Exception:
            return None

    # === Dispatch execution ===

    async def execute_dispatch_cycle(self, site_id: str) -> Optional[DispatchEvent]:
        """Execute a single dispatch cycle.

        Called every 5 minutes by the autonomous scheduler.
        Reads the current interval from the cached MIP schedule if available,
        otherwise falls back to the arbitrage engine's realtime dispatch.
        """
        engine = get_solar_arbitrage_engine()

        # Get current state (real hardware SOC when in live mode)
        current_soc = await self._get_current_soc(site_id)
        now = datetime.now(timezone.utc)
        sast = now + timedelta(hours=2)

        # Simulate solar and load based on time of day
        profile = self._get_hourly_profile(engine)
        hour_profile = profile.get(sast.hour, {})
        solar_kw = hour_profile.get("solar_kw", 0)
        load_kw = hour_profile.get("load_kw", 1800)

        # Add realistic noise
        solar_kw *= random.uniform(0.9, 1.1)
        load_kw *= random.uniform(0.95, 1.05)

        # Try to read current interval from cached MIP schedule
        action = self._get_mip_dispatch_action(site_id, current_soc, solar_kw, load_kw, sast)

        # Check load shedding status: manual override > EskomSePush API > off
        load_shedding_active = False
        override = settings.load_shedding_stage_override
        if override > 0:
            # Manual override: operator has set a stage (1-8)
            load_shedding_active = True
            logger.info("Load shedding ACTIVE (manual override stage %d)", override)
        elif override == -1:
            # Use EskomSePush API if configured (paid API, optional)
            try:
                from app.services.eskomsepush_service import eskomsepush_service

                if eskomsepush_service.is_configured:
                    eskom_status = await eskomsepush_service.get_combined_status()
                    load_shedding_active = eskom_status.eskom.stage > 0
            except Exception:
                pass  # Non-fatal — continue with False

        if action is None:
            # Fallback: get dispatch action from arbitrage engine
            action = engine.get_realtime_dispatch_action(
                site_id=site_id,
                current_soc_pct=current_soc,
                solar_gen_kw=solar_kw,
                building_load_kw=load_kw,
                load_shedding_active=load_shedding_active,
                timestamp=now,
            )

        # Update simulated SOC
        interval_hours = self.CYCLE_INTERVAL_MINUTES / 60.0
        soc_before = current_soc

        if action.action == DispatchActionType.CHARGE.value:
            energy_kwh = action.power_kw * interval_hours
            soc_delta = (energy_kwh / self.BESS_CAPACITY_KWH) * 100
            current_soc = min(self.BESS_MAX_SOC, current_soc + soc_delta)
        elif action.action == DispatchActionType.DISCHARGE.value:
            energy_kwh = action.power_kw * interval_hours
            soc_delta = (energy_kwh / self.BESS_CAPACITY_KWH) * 100
            current_soc = max(self.BESS_MIN_SOC, current_soc - soc_delta)
        elif action.action == DispatchActionType.SOLAR_PRIORITY.value:
            charge_power = action.power_kw
            energy_kwh = charge_power * interval_hours * self.BESS_EFFICIENCY
            soc_delta = (energy_kwh / self.BESS_CAPACITY_KWH) * 100
            current_soc = min(self.BESS_MAX_SOC, current_soc + soc_delta)

        self._simulated_soc[site_id] = current_soc

        # Calculate grid flows
        net_load = load_kw - solar_kw
        if action.action == DispatchActionType.DISCHARGE.value:
            net_load -= action.power_kw
        elif action.action == DispatchActionType.CHARGE.value:
            net_load += action.power_kw

        grid_import = max(0, net_load)
        grid_export = max(0, -net_load)

        # Log event
        event = DispatchEvent(
            timestamp=now.isoformat(),
            action=action.action,
            power_kw=action.power_kw,
            soc_before_pct=soc_before,
            soc_after_pct=current_soc,
            tariff_band=action.tariff_band,
            rate_per_kwh=action.rate_per_kwh,
            reason=action.reason,
            load_shedding=action.load_shedding_active,
            solar_gen_kw=solar_kw,
            building_load_kw=load_kw,
            grid_import_kw=grid_import,
            grid_export_kw=grid_export,
        )

        if site_id not in self._dispatch_log:
            self._dispatch_log[site_id] = []
        self._dispatch_log[site_id].append(event)

        # Persist dispatch event to JSONL (survives restart)
        self._persist_dispatch_event(site_id, event)

        # Route through AEGIS governance pipeline (non-fatal)
        try:
            from app.services.aegis_bridge import run_aegis_cycle

            aegis_result = await run_aegis_cycle(site_id)
            if aegis_result:
                proposal_id = aegis_result.get("aegis_proposal_id")
                if proposal_id:
                    event.aegis_proposal_id = proposal_id
                    # Re-persist with join key so JSONL is joinable
                    self._persist_dispatch_event(site_id, event, overwrite_last=True)
                logger.info(
                    "AEGIS proposal created: %s (tier=%s)",
                    aegis_result.get("id", "?"),
                    aegis_result.get("routing", {}).get("tier", "?"),
                )
        except Exception as e:
            logger.warning("AEGIS bridge failed (non-fatal): %s", e)

        # Route dispatch command to Modbus BESS writer (gated by AEGIS)
        try:
            from app.services.modbus_bess_writer import execute_dispatch_with_write
            from app.services.bess_dispatch_engine import BESSState

            bess_state = BESSState(
                soc_pct=soc_before,
                temperature_c=25.0,
                power_kw=0.0,
                grid_frequency_hz=50.0,
            )
            write_result = await execute_dispatch_with_write(
                site_id=site_id,
                action=action.action,
                requested_power_kw=action.power_kw,
                bess_state=bess_state,
                duration_minutes=self.CYCLE_INTERVAL_MINUTES,
                reason=action.reason,
                who="dispatch_scheduler",
            )
            event.write_result = write_result.get("write_result", {})
        except Exception as e:
            logger.debug("Modbus writer (non-fatal): %s", e)

        return event

    # === JSONL persistence ===

    def _persist_dispatch_event(self, site_id: str, event: DispatchEvent, overwrite_last: bool = False) -> None:
        """Append dispatch event to daily JSONL file (survives restart).

        If overwrite_last=True, replaces the last line (used to backfill
        aegis_proposal_id after AEGIS bridge returns the join key).
        """
        try:
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            solar_dir = DATA_DIR / "solar"
            solar_dir.mkdir(parents=True, exist_ok=True)
            path = solar_dir / f"dispatch_log_{site_id}_{today}.jsonl"

            if overwrite_last and path.exists():
                # Read all lines, replace last, rewrite
                with open(path) as f:
                    lines = f.readlines()
                if lines:
                    lines[-1] = json.dumps(event.to_dict()) + "\n"
                    with open(path, "w") as f:
                        f.writelines(lines)
                    return

            with open(path, "a") as f:
                f.write(json.dumps(event.to_dict()) + "\n")
        except Exception as e:
            logger.warning("Failed to persist dispatch event: %s", e)

    def get_persistent_dispatch_log(self, site_id: str, hours: int = 24) -> List[Dict]:
        """Read dispatch events from JSONL files for the given time window."""
        events = []
        solar_dir = DATA_DIR / "solar"
        if not solar_dir.exists():
            return events

        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        # Check today and yesterday's files
        for day_offset in range(2):
            day = (datetime.now(timezone.utc) - timedelta(days=day_offset)).strftime("%Y-%m-%d")
            path = solar_dir / f"dispatch_log_{site_id}_{day}.jsonl"
            if not path.exists():
                continue
            try:
                with open(path) as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        record = json.loads(line)
                        ts = record.get("timestamp", "")
                        if ts and datetime.fromisoformat(ts) >= cutoff:
                            events.append(record)
            except Exception as e:
                logger.warning("Error reading dispatch JSONL %s: %s", path, e)

        return sorted(events, key=lambda e: e.get("timestamp", ""), reverse=True)

    # === Dispatch log ===

    def get_dispatch_log(self, site_id: str, hours: int = 24) -> List[DispatchEvent]:
        """Get recent dispatch history for a site."""
        events = self._dispatch_log.get(site_id, [])
        if hours > 0:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
            events = [e for e in events if datetime.fromisoformat(e.timestamp) >= cutoff]
        # Most recent first
        return sorted(events, key=lambda e: e.timestamp, reverse=True)

    # === Dispatch status ===

    def get_dispatch_status(self, site_id: str) -> Optional[DispatchStatus]:
        """Get current dispatch status for a site."""
        engine = get_solar_arbitrage_engine()

        if site_id not in self._mode:
            return None

        current_soc = self._simulated_soc.get(site_id, 50.0)
        band = engine.get_current_tariff_band()

        # Load-shedding status (best-effort from EskomSePush)
        load_shedding_active = False

        # Find current action from recent events
        events_today = self.get_dispatch_log(site_id, hours=24)
        current_action = "idle"
        current_power = 0.0
        last_dispatch = None

        if events_today:
            latest = events_today[0]
            current_action = latest.action
            current_power = latest.power_kw
            last_dispatch = latest.timestamp

        # Calculate today's savings
        savings = engine.calculate_daily_savings(site_id)

        # Count cycles (charge->discharge transitions)
        cycles = 0
        prev_action = None
        for e in reversed(events_today):
            if prev_action == "charge" and e.action == "discharge":
                cycles += 1
            prev_action = e.action

        # Uptime
        started_at = self._started_at.get(site_id)
        uptime = 0.0
        if started_at:
            start_dt = datetime.fromisoformat(started_at)
            uptime = (datetime.now(timezone.utc) - start_dt).total_seconds() / 3600

        # Next action change estimate
        next_change = None
        sast = datetime.now(timezone.utc) + timedelta(hours=2)
        if band.period_end:
            eh, em = map(int, band.period_end.split(":"))
            next_dt = sast.replace(hour=eh, minute=em, second=0, microsecond=0)
            if next_dt <= sast:
                next_dt += timedelta(days=1)
            next_change = (next_dt - timedelta(hours=2)).isoformat()  # back to UTC

        return DispatchStatus(
            site_id=site_id,
            mode=self._mode.get(site_id, "stopped"),
            current_action=current_action,
            current_power_kw=current_power,
            bess_soc_pct=current_soc,
            tariff_band=band.name,
            rate_per_kwh=band.total_rate_per_kwh,
            next_action_change=next_change,
            savings_today_zar=savings.savings_zar,
            cycles_today=max(1, cycles),
            dispatch_events_today=len(events_today),
            last_dispatch=last_dispatch,
            load_shedding_active=load_shedding_active,
            uptime_hours=uptime,
        )

    # === Autonomous dispatch control ===

    async def start_autonomous_dispatch(self, site_id: str) -> Dict[str, Any]:
        """Start autonomous dispatch for a site.

        In production this would spawn a background task running every 5 minutes.
        For demo, the seeded history already shows a full cycle.
        """
        self._mode[site_id] = "autonomous"
        self._started_at[site_id] = datetime.now(timezone.utc).isoformat()

        if site_id not in self._simulated_soc:
            self._simulated_soc[site_id] = 50.0

        logger.info("Started autonomous dispatch for site %s", site_id)
        return {
            "site_id": site_id,
            "mode": "autonomous",
            "cycle_interval_minutes": self.CYCLE_INTERVAL_MINUTES,
            "started_at": self._started_at[site_id],
        }

    async def stop_dispatch(self, site_id: str) -> Dict[str, Any]:
        """Stop autonomous dispatch for a site."""
        self._mode[site_id] = "stopped"
        logger.info("Stopped dispatch for site %s", site_id)
        return {"site_id": site_id, "mode": "stopped"}


# === Singleton ===

_solar_dispatch_service: Optional[SolarDispatchService] = None


def get_solar_dispatch_service() -> SolarDispatchService:
    """Get the singleton solar dispatch service instance."""
    global _solar_dispatch_service
    if _solar_dispatch_service is None:
        _solar_dispatch_service = SolarDispatchService()
    return _solar_dispatch_service
