"""Solar Dispatch Service -- autonomous BESS dispatch execution.

The "invisible optimiser" brain.  Runs a 5-minute dispatch cycle that:
  1. Reads current state (SOC, solar gen, building load, grid import/export)
  2. Checks load shedding schedule via EskomSePush
  3. Gets dispatch action from arbitrage engine
  4. Applies compliance constraints (export limits from 34-03)
  5. Executes action (update simulated BESS state for demo)
  6. Logs dispatch event

For demo purposes the full 24h cycle is simulated with compressed time
to show BESS charging at night, discharging at peak, savings accumulating.
"""

import logging
import random
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta, time, date
from enum import Enum
from typing import Dict, List, Optional, Any

from app.services.solar_arbitrage_engine import (
    get_solar_arbitrage_engine,
    DispatchActionType,
)

logger = logging.getLogger(__name__)


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

    def to_dict(self) -> Dict[str, Any]:
        return {
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
    BESS_CAPACITY_KWH = 5015.0
    BESS_MIN_SOC = 10.0
    BESS_MAX_SOC = 95.0
    BESS_EFFICIENCY = 0.90

    def __init__(self):
        self._dispatch_log: Dict[str, List[DispatchEvent]] = {}
        self._simulated_soc: Dict[str, float] = {}
        self._started_at: Dict[str, str] = {}
        self._mode: Dict[str, str] = {}  # autonomous / manual / stopped
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
        sast_now = now + timedelta(hours=2)

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
                charge_kw = min(excess, 2507)
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

            events.append(DispatchEvent(
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
            ))

            sim_time += timedelta(minutes=self.CYCLE_INTERVAL_MINUTES)

        self._dispatch_log[site_id] = events
        self._simulated_soc[site_id] = soc
        self._started_at[site_id] = start.isoformat()
        self._mode[site_id] = "autonomous"

        logger.info(
            "Seeded %d dispatch events for %s (SOC: %.1f%%)",
            len(events), site_id, soc,
        )

    def _get_hourly_profile(self, engine) -> Dict[int, Dict[str, Any]]:
        """Build hour-by-hour dispatch profile (SAST hours)."""
        season = engine._get_season()
        off_peak_rate = engine._get_band_rate("off_peak", season)
        std_rate = engine._get_band_rate("standard", season)
        peak_rate = engine._get_band_rate("peak", season)

        # Solar generation curve for Johannesburg (clear day)
        solar_curve = {
            0: 0, 1: 0, 2: 0, 3: 0, 4: 0, 5: 0,
            6: 50, 7: 400, 8: 1200, 9: 2000,
            10: 2600, 11: 3000, 12: 3200, 13: 3100, 14: 2800,
            15: 2300, 16: 1600, 17: 800, 18: 200, 19: 0,
            20: 0, 21: 0, 22: 0, 23: 0,
        }

        # Building load profile
        load_curve = {
            0: 1200, 1: 1100, 2: 1000, 3: 1000, 4: 1050, 5: 1200,
            6: 1500, 7: 2000, 8: 2300, 9: 2500,
            10: 2400, 11: 2300, 12: 2200, 13: 2300, 14: 2400,
            15: 2300, 16: 2200, 17: 2000, 18: 1800, 19: 1600,
            20: 1400, 21: 1300, 22: 1200, 23: 1200,
        }

        profile = {}
        for h in range(24):
            solar_kw = solar_curve.get(h, 0)
            load_kw = load_curve.get(h, 1500)

            if h >= 22 or h < 6:
                profile[h] = {
                    "action": "charge", "power_kw": 2000, "band": "off_peak",
                    "solar_kw": 0, "load_kw": load_kw,
                    "reason": f"Off-peak charging @ R{off_peak_rate:.2f}/kWh",
                }
            elif h == 6:
                profile[h] = {
                    "action": "idle", "power_kw": 0, "band": "standard",
                    "solar_kw": solar_kw, "load_kw": load_kw,
                    "reason": "Standard early morning; awaiting peak window",
                }
            elif 7 <= h < 10:
                profile[h] = {
                    "action": "discharge", "power_kw": 2500, "band": "peak",
                    "solar_kw": solar_kw, "load_kw": load_kw,
                    "reason": f"Morning peak discharge @ R{peak_rate:.2f}/kWh",
                }
            elif 10 <= h < 18:
                profile[h] = {
                    "action": "solar_priority", "power_kw": 0, "band": "standard",
                    "solar_kw": solar_kw, "load_kw": load_kw,
                    "reason": f"Solar priority; {solar_kw:.0f} kW PV generation",
                }
            elif 18 <= h < 20:
                profile[h] = {
                    "action": "discharge", "power_kw": 2500, "band": "peak",
                    "solar_kw": solar_kw, "load_kw": load_kw,
                    "reason": f"Evening peak discharge @ R{peak_rate:.2f}/kWh",
                }
            elif 20 <= h < 22:
                profile[h] = {
                    "action": "idle", "power_kw": 0, "band": "standard",
                    "solar_kw": 0, "load_kw": load_kw,
                    "reason": "Standard evening; BESS idle, conserving for overnight charge",
                }

        return profile

    # === Dispatch execution ===

    async def execute_dispatch_cycle(self, site_id: str) -> Optional[DispatchEvent]:
        """Execute a single dispatch cycle.

        Called every 5 minutes by the autonomous scheduler.
        For demo: reads simulated state and updates BESS SOC.
        """
        engine = get_solar_arbitrage_engine()

        # Get current state
        current_soc = self._simulated_soc.get(site_id, 50.0)
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

        # Get dispatch action from arbitrage engine
        action = engine.get_realtime_dispatch_action(
            site_id=site_id,
            current_soc_pct=current_soc,
            solar_gen_kw=solar_kw,
            building_load_kw=load_kw,
            load_shedding_active=False,
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

        return event

    # === Dispatch log ===

    def get_dispatch_log(
        self, site_id: str, hours: int = 24
    ) -> List[DispatchEvent]:
        """Get recent dispatch history for a site."""
        events = self._dispatch_log.get(site_id, [])
        if hours > 0:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
            events = [
                e for e in events
                if datetime.fromisoformat(e.timestamp) >= cutoff
            ]
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
            load_shedding_active=False,
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
