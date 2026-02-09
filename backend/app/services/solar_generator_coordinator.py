"""Solar Generator Coordinator -- priority dispatch and diesel avoidance.

Enforces the dispatch priority stack: Solar > BESS > Grid > Generator.
The generator is the absolute last resort -- only started when load shedding
is active AND BESS SOC is critically low AND solar generation is insufficient.

Diesel avoidance tracking provides tangible financial evidence of the
Solar+BESS investment: how many hours of generator runtime were avoided,
how many litres of diesel saved, and what that's worth in ZAR.

Site-002 generator specifications (from generator_service.py context):
  - 2x 500 kVA diesel gensets (DeepSea DSE8610 MKII controllers)
  - Fuel consumption: ~30 L/hour at 70% load (~90 L/hour at 100%)
  - Diesel price: ~R22/litre (2026 estimate)
  - Annual fuel budget without Solar+BESS: ~R2.5M
  - Target: reduce to <R500K/year (80% reduction)

Load shedding coordination:
  - Pre-LS: Ensure BESS charged to 80% SOC (handled by arbitrage engine)
  - During LS: Solar + BESS sustain critical loads
  - Generator: Only if BESS < 20% AND LS continues AND solar insufficient
  - Post-LS: Resume normal dispatch, log event
"""

import logging
import random
from dataclasses import dataclass, field
from datetime import datetime, date, timezone, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


# === Enums ===

class DispatchSource(str, Enum):
    """Energy source in the priority stack."""
    SOLAR = "solar"
    BESS = "bess"
    GRID = "grid"
    GENERATOR = "generator"


class GeneratorEventType(str, Enum):
    """Types of generator events."""
    START = "start"
    STOP = "stop"
    AVOIDED_START = "avoided_start"
    LS_OVERRIDE = "ls_override"
    LOW_SOC_START = "low_soc_start"


# === Dataclass models ===


@dataclass
class DispatchPriority:
    """Current dispatch priority determination."""
    site_id: str
    timestamp: str
    active_source: str  # solar / bess / grid / generator
    priority_stack: List[Dict[str, Any]] = field(default_factory=list)
    reason: str = ""
    solar_available_kw: float = 0.0
    bess_soc_pct: float = 0.0
    building_load_kw: float = 0.0
    load_shedding_active: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "site_id": self.site_id,
            "timestamp": self.timestamp,
            "active_source": self.active_source,
            "priority_stack": self.priority_stack,
            "reason": self.reason,
            "solar_available_kw": round(self.solar_available_kw, 0),
            "bess_soc_pct": round(self.bess_soc_pct, 1),
            "building_load_kw": round(self.building_load_kw, 0),
            "load_shedding_active": self.load_shedding_active,
        }


@dataclass
class GeneratorAssessment:
    """Assessment of whether the generator should be started."""
    site_id: str
    should_start: bool
    reason: str
    load_shedding_active: bool = False
    bess_soc_pct: float = 0.0
    bess_runtime_hours: float = 0.0  # How long BESS can sustain at current load
    ls_remaining_hours: float = 0.0  # Hours until load shedding ends
    solar_forecast_kw: float = 0.0  # Expected solar for remaining LS window
    building_load_kw: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "site_id": self.site_id,
            "should_start": self.should_start,
            "reason": self.reason,
            "load_shedding_active": self.load_shedding_active,
            "bess_soc_pct": round(self.bess_soc_pct, 1),
            "bess_runtime_hours": round(self.bess_runtime_hours, 2),
            "ls_remaining_hours": round(self.ls_remaining_hours, 2),
            "solar_forecast_kw": round(self.solar_forecast_kw, 0),
            "building_load_kw": round(self.building_load_kw, 0),
        }


@dataclass
class DieselAvoidance:
    """Diesel avoidance savings calculation."""
    site_id: str
    period: str  # day / week / month
    hours_would_have_run: float  # Generator hours without Solar+BESS
    hours_actually_ran: float  # Generator hours with Solar+BESS
    hours_avoided: float
    litres_saved: float  # At 30L/hour avg consumption
    zar_saved: float  # At R22/litre
    diesel_price_per_litre: float = 22.0
    generator_consumption_lph: float = 30.0  # Litres per hour at 70% load
    load_shedding_events: int = 0
    generator_starts: int = 0
    generator_avoided_starts: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "site_id": self.site_id,
            "period": self.period,
            "hours_would_have_run": round(self.hours_would_have_run, 1),
            "hours_actually_ran": round(self.hours_actually_ran, 1),
            "hours_avoided": round(self.hours_avoided, 1),
            "litres_saved": round(self.litres_saved, 0),
            "zar_saved": round(self.zar_saved, 2),
            "diesel_price_per_litre": self.diesel_price_per_litre,
            "generator_consumption_lph": self.generator_consumption_lph,
            "load_shedding_events": self.load_shedding_events,
            "generator_starts": self.generator_starts,
            "generator_avoided_starts": self.generator_avoided_starts,
        }


@dataclass
class GeneratorEvent:
    """Log entry for a generator-related event."""
    timestamp: str
    event_type: str  # start / stop / avoided_start / ls_override / low_soc_start
    site_id: str
    reason: str
    bess_soc_pct: float = 0.0
    solar_gen_kw: float = 0.0
    building_load_kw: float = 0.0
    load_shedding_stage: int = 0
    fuel_litres_used: float = 0.0
    duration_hours: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "timestamp": self.timestamp,
            "event_type": self.event_type,
            "site_id": self.site_id,
            "reason": self.reason,
            "bess_soc_pct": round(self.bess_soc_pct, 1),
            "solar_gen_kw": round(self.solar_gen_kw, 0),
            "building_load_kw": round(self.building_load_kw, 0),
        }
        if self.load_shedding_stage > 0:
            result["load_shedding_stage"] = self.load_shedding_stage
        if self.fuel_litres_used > 0:
            result["fuel_litres_used"] = round(self.fuel_litres_used, 1)
        if self.duration_hours > 0:
            result["duration_hours"] = round(self.duration_hours, 2)
        return result


@dataclass
class LSResponse:
    """Response to a load shedding event."""
    site_id: str
    stage: int
    ls_start: str
    ls_end: str
    strategy: str
    bess_soc_pct: float
    bess_can_sustain_hours: float
    generator_needed: bool
    solar_contribution_kw: float
    actions: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "site_id": self.site_id,
            "stage": self.stage,
            "ls_start": self.ls_start,
            "ls_end": self.ls_end,
            "strategy": self.strategy,
            "bess_soc_pct": round(self.bess_soc_pct, 1),
            "bess_can_sustain_hours": round(self.bess_can_sustain_hours, 2),
            "generator_needed": self.generator_needed,
            "solar_contribution_kw": round(self.solar_contribution_kw, 0),
            "actions": self.actions,
        }


# === Generator Coordinator ===

class SolarGeneratorCoordinator:
    """Coordinates dispatch priority and diesel avoidance tracking.

    Enforces: Solar > BESS > Grid > Generator priority stack.
    Tracks generator events and calculates diesel savings.
    """

    # BESS parameters (from arbitrage engine)
    BESS_CAPACITY_KWH = 5015.0
    BESS_RATED_POWER_KW = 2507.0
    BESS_MIN_SOC_PCT = 10.0
    BESS_MAX_SOC_PCT = 95.0
    GENERATOR_SOC_THRESHOLD = 20.0  # Only start generator if SOC below this

    # Generator parameters
    DIESEL_PRICE_PER_LITRE = 22.0  # ZAR/litre (2026 estimate)
    GENERATOR_CONSUMPTION_LPH = 30.0  # Litres/hour at ~70% load
    GENERATOR_FULL_LOAD_LPH = 90.0  # Litres/hour at 100% load

    # Building load profile
    DEFAULT_BUILDING_LOAD_KW = 1800.0  # Base load
    CRITICAL_LOAD_PCT = 0.70  # 70% of base load is critical

    def __init__(self):
        self._events: Dict[str, List[GeneratorEvent]] = {}  # site_id -> events
        self._seed_demo_events()

    def _seed_demo_events(self) -> None:
        """Seed realistic generator event history for demo."""
        site_id = "site-002"
        events: List[GeneratorEvent] = []
        now = datetime.now(timezone.utc)

        # Simulate a month of load shedding events
        # JHB typically sees Stage 2-4, 2-3 events per week
        rng = random.Random(42)
        for day_offset in range(30, 0, -1):
            day_dt = now - timedelta(days=day_offset)

            # ~40% chance of LS event on any given day
            if rng.random() < 0.40:
                ls_stage = rng.choice([2, 2, 3, 4])
                ls_hour = rng.choice([6, 10, 14, 18, 22])
                ls_duration = rng.choice([2.0, 2.5, 4.0, 4.5])  # Hours

                ls_start = day_dt.replace(hour=ls_hour, minute=0, second=0)
                ls_end = ls_start + timedelta(hours=ls_duration)

                # BESS SOC at start of LS (depends on time of day)
                if ls_hour < 10:
                    soc = rng.uniform(60, 85)  # Morning: BESS charged overnight
                elif ls_hour < 18:
                    soc = rng.uniform(30, 60)  # Afternoon: BESS partially discharged
                else:
                    soc = rng.uniform(20, 40)  # Evening: BESS mostly discharged

                # Solar generation during LS window
                solar_gen = 0.0
                if 7 <= ls_hour <= 17:
                    solar_gen = rng.uniform(1000, 2800)

                # Can BESS sustain the load?
                usable_kwh = self.BESS_CAPACITY_KWH * (soc - self.BESS_MIN_SOC_PCT) / 100.0
                critical_load = self.DEFAULT_BUILDING_LOAD_KW * self.CRITICAL_LOAD_PCT
                net_load = max(0, critical_load - solar_gen)
                bess_runtime = usable_kwh / net_load if net_load > 0 else 999

                if bess_runtime >= ls_duration:
                    # BESS can sustain -- generator avoided
                    events.append(GeneratorEvent(
                        timestamp=ls_start.isoformat(),
                        event_type=GeneratorEventType.AVOIDED_START.value,
                        site_id=site_id,
                        reason=f"LS Stage {ls_stage}: BESS can sustain {bess_runtime:.1f}h, LS duration {ls_duration:.1f}h",
                        bess_soc_pct=soc,
                        solar_gen_kw=solar_gen,
                        building_load_kw=critical_load,
                        load_shedding_stage=ls_stage,
                        duration_hours=ls_duration,
                    ))
                else:
                    # BESS depleted -- generator must start
                    gen_hours = ls_duration - bess_runtime
                    fuel = gen_hours * self.GENERATOR_CONSUMPTION_LPH

                    events.append(GeneratorEvent(
                        timestamp=ls_start.isoformat(),
                        event_type=GeneratorEventType.LOW_SOC_START.value,
                        site_id=site_id,
                        reason=f"LS Stage {ls_stage}: BESS sustains {bess_runtime:.1f}h but LS is {ls_duration:.1f}h",
                        bess_soc_pct=soc,
                        solar_gen_kw=solar_gen,
                        building_load_kw=critical_load,
                        load_shedding_stage=ls_stage,
                        fuel_litres_used=fuel,
                        duration_hours=gen_hours,
                    ))
                    events.append(GeneratorEvent(
                        timestamp=(ls_start + timedelta(hours=bess_runtime)).isoformat(),
                        event_type=GeneratorEventType.START.value,
                        site_id=site_id,
                        reason=f"BESS depleted during Stage {ls_stage}; generator started",
                        bess_soc_pct=self.BESS_MIN_SOC_PCT + 5,
                        solar_gen_kw=solar_gen * 0.5,
                        building_load_kw=critical_load,
                        load_shedding_stage=ls_stage,
                    ))
                    events.append(GeneratorEvent(
                        timestamp=ls_end.isoformat(),
                        event_type=GeneratorEventType.STOP.value,
                        site_id=site_id,
                        reason=f"Load shedding ended; generator stopped after {gen_hours:.1f}h",
                        bess_soc_pct=self.BESS_MIN_SOC_PCT,
                        solar_gen_kw=0,
                        building_load_kw=critical_load,
                        load_shedding_stage=ls_stage,
                        fuel_litres_used=fuel,
                        duration_hours=gen_hours,
                    ))

        # Sort by timestamp
        events.sort(key=lambda e: e.timestamp)
        self._events[site_id] = events

    # === Public API ===

    def get_dispatch_priority(self, site_id: str) -> DispatchPriority:
        """Determine current energy source priority.

        Priority stack: Solar > BESS > Grid > Generator.
        Returns active source and status of each tier.
        """
        now = datetime.now(timezone.utc)
        sast = now + timedelta(hours=2)
        hour = sast.hour

        # Simulate current state
        rng = random.Random(hash(f"{site_id}-{now.strftime('%Y%m%d%H')}"))

        # Solar generation (bell curve, zero at night)
        solar_kw = 0.0
        if 6 <= hour <= 18:
            peak_hour = 12.0
            spread = 3.5
            solar_factor = max(0, 1.0 - ((hour - peak_hour) / spread) ** 2)
            solar_kw = 3200 * solar_factor * rng.uniform(0.6, 1.0)

        # BESS SOC
        if hour < 6:
            bess_soc = rng.uniform(70, 90)  # Charged overnight
        elif hour < 10:
            bess_soc = rng.uniform(50, 80)  # Morning discharge
        elif hour < 18:
            bess_soc = rng.uniform(30, 60)  # Midday (solar charging)
        else:
            bess_soc = rng.uniform(15, 35)  # Evening discharge

        building_load = self.DEFAULT_BUILDING_LOAD_KW * rng.uniform(0.85, 1.15)
        ls_active = False  # Simulated -- no active LS

        # Determine active source
        if solar_kw >= building_load:
            active = DispatchSource.SOLAR.value
            reason = f"Solar ({solar_kw:.0f} kW) exceeds building load ({building_load:.0f} kW)"
        elif solar_kw + self.BESS_RATED_POWER_KW >= building_load and bess_soc > self.BESS_MIN_SOC_PCT:
            active = DispatchSource.BESS.value
            reason = f"Solar + BESS supplementing load; BESS at {bess_soc:.0f}% SOC"
        elif not ls_active:
            active = DispatchSource.GRID.value
            reason = "Grid importing to meet demand; BESS conserving for peak tariff"
        else:
            active = DispatchSource.GENERATOR.value
            reason = "Load shedding active and BESS depleted; generator running"

        priority_stack = [
            {"rank": 1, "source": "solar", "status": "active" if solar_kw > 0 else "unavailable", "output_kw": round(solar_kw, 0)},
            {"rank": 2, "source": "bess", "status": "available" if bess_soc > self.BESS_MIN_SOC_PCT else "depleted", "soc_pct": round(bess_soc, 1)},
            {"rank": 3, "source": "grid", "status": "available" if not ls_active else "unavailable"},
            {"rank": 4, "source": "generator", "status": "standby", "note": "Last resort only"},
        ]

        return DispatchPriority(
            site_id=site_id,
            timestamp=now.isoformat(),
            active_source=active,
            priority_stack=priority_stack,
            reason=reason,
            solar_available_kw=solar_kw,
            bess_soc_pct=bess_soc,
            building_load_kw=building_load,
            load_shedding_active=ls_active,
        )

    def evaluate_generator_need(self, site_id: str) -> GeneratorAssessment:
        """Assess whether the generator should be started.

        Only recommends generator start when ALL conditions met:
          1. Load shedding is active
          2. BESS SOC < 20%
          3. Solar generation insufficient for critical load
          4. BESS cannot sustain load for remaining LS window
        """
        now = datetime.now(timezone.utc)
        sast = now + timedelta(hours=2)
        hour = sast.hour
        rng = random.Random(hash(f"{site_id}-gen-{now.strftime('%Y%m%d%H')}"))

        # Simulate current state
        building_load = self.DEFAULT_BUILDING_LOAD_KW * rng.uniform(0.85, 1.15)
        bess_soc = rng.uniform(35, 65)

        # Solar generation
        solar_kw = 0.0
        if 6 <= hour <= 18:
            peak_hour = 12.0
            spread = 3.5
            solar_factor = max(0, 1.0 - ((hour - peak_hour) / spread) ** 2)
            solar_kw = 3200 * solar_factor * rng.uniform(0.6, 1.0)

        # For demo, no active load shedding (generator not needed)
        ls_active = False
        ls_remaining_hours = 0.0

        # BESS runtime calculation
        critical_load = building_load * self.CRITICAL_LOAD_PCT
        net_load = max(0, critical_load - solar_kw)
        usable_kwh = self.BESS_CAPACITY_KWH * (bess_soc - self.BESS_MIN_SOC_PCT) / 100.0
        bess_runtime = usable_kwh / net_load if net_load > 0 else 999.0

        # Decision logic
        should_start = (
            ls_active
            and bess_soc < self.GENERATOR_SOC_THRESHOLD
            and solar_kw < critical_load
            and bess_runtime < ls_remaining_hours
        )

        if not ls_active:
            reason = "No load shedding active; generator remains on standby"
        elif bess_soc >= self.GENERATOR_SOC_THRESHOLD:
            reason = f"BESS at {bess_soc:.0f}% SOC; sufficient to sustain load"
        elif solar_kw >= critical_load:
            reason = f"Solar ({solar_kw:.0f} kW) sufficient for critical load ({critical_load:.0f} kW)"
        elif bess_runtime >= ls_remaining_hours:
            reason = f"BESS can sustain {bess_runtime:.1f}h; LS ends in {ls_remaining_hours:.1f}h"
        else:
            reason = f"BESS depleted ({bess_soc:.0f}%), solar insufficient, LS continues for {ls_remaining_hours:.1f}h"

        return GeneratorAssessment(
            site_id=site_id,
            should_start=should_start,
            reason=reason,
            load_shedding_active=ls_active,
            bess_soc_pct=bess_soc,
            bess_runtime_hours=min(bess_runtime, 99.9),
            ls_remaining_hours=ls_remaining_hours,
            solar_forecast_kw=solar_kw,
            building_load_kw=building_load,
        )

    def calculate_diesel_avoidance(
        self,
        site_id: str,
        period: str = "month",
    ) -> DieselAvoidance:
        """Calculate diesel savings from Solar+BESS replacing generator runtime.

        Analyses generator event log to count:
        - Hours generator would have run without Solar+BESS (all LS events)
        - Hours generator actually ran (only when BESS depleted)
        - Litres and ZAR saved
        """
        events = self._events.get(site_id, [])
        now = datetime.now(timezone.utc)

        # Period filter
        if period == "day":
            cutoff = now - timedelta(days=1)
        elif period == "week":
            cutoff = now - timedelta(weeks=1)
        else:
            cutoff = now - timedelta(days=30)

        filtered = [e for e in events if e.timestamp >= cutoff.isoformat()]

        # Count events
        ls_events = set()
        avoided_starts = 0
        actual_starts = 0
        hours_ran = 0.0
        hours_would_have_run = 0.0

        for event in filtered:
            if event.event_type == GeneratorEventType.AVOIDED_START.value:
                avoided_starts += 1
                hours_would_have_run += event.duration_hours
                ls_events.add(event.timestamp[:10])

            elif event.event_type == GeneratorEventType.LOW_SOC_START.value:
                actual_starts += 1
                # The full LS duration would have been gen runtime without BESS
                # Actual gen runtime is just the portion after BESS depleted
                hours_would_have_run += event.duration_hours + event.bess_runtime_hours if hasattr(event, 'bess_runtime_hours') else event.duration_hours
                hours_ran += event.duration_hours
                ls_events.add(event.timestamp[:10])

            elif event.event_type == GeneratorEventType.START.value:
                ls_events.add(event.timestamp[:10])

            elif event.event_type == GeneratorEventType.STOP.value:
                if event.duration_hours > 0:
                    hours_ran += event.duration_hours

        # Avoid double-counting: use stops for actual hours
        # Recalculate hours_ran from stop events only
        stop_events = [e for e in filtered if e.event_type == GeneratorEventType.STOP.value]
        hours_ran = sum(e.duration_hours for e in stop_events)

        # Recalculate would-have-run: all LS events * their duration
        avoided_events = [e for e in filtered if e.event_type == GeneratorEventType.AVOIDED_START.value]
        low_soc_events = [e for e in filtered if e.event_type == GeneratorEventType.LOW_SOC_START.value]

        # Without Solar+BESS, generator would have run for full LS duration
        hours_would_have_run = (
            sum(e.duration_hours for e in avoided_events)
            + sum(e.duration_hours for e in low_soc_events)
            + hours_ran
        )

        hours_avoided = hours_would_have_run - hours_ran
        litres_saved = hours_avoided * self.GENERATOR_CONSUMPTION_LPH
        zar_saved = litres_saved * self.DIESEL_PRICE_PER_LITRE

        return DieselAvoidance(
            site_id=site_id,
            period=period,
            hours_would_have_run=hours_would_have_run,
            hours_actually_ran=hours_ran,
            hours_avoided=hours_avoided,
            litres_saved=litres_saved,
            zar_saved=zar_saved,
            diesel_price_per_litre=self.DIESEL_PRICE_PER_LITRE,
            generator_consumption_lph=self.GENERATOR_CONSUMPTION_LPH,
            load_shedding_events=len(ls_events),
            generator_starts=actual_starts,
            generator_avoided_starts=avoided_starts,
        )

    def get_generator_events(
        self,
        site_id: str,
        period: str = "month",
    ) -> List[GeneratorEvent]:
        """Get generator event log for a period."""
        events = self._events.get(site_id, [])
        now = datetime.now(timezone.utc)

        if period == "day":
            cutoff = now - timedelta(days=1)
        elif period == "week":
            cutoff = now - timedelta(weeks=1)
        else:
            cutoff = now - timedelta(days=30)

        filtered = [e for e in events if e.timestamp >= cutoff.isoformat()]
        # Most recent first
        filtered.sort(key=lambda e: e.timestamp, reverse=True)
        return filtered

    def handle_load_shedding_event(
        self,
        site_id: str,
        stage: int,
        start: str,
        end: str,
    ) -> LSResponse:
        """Handle a load shedding event with coordinated response.

        Evaluates BESS capacity vs LS duration and determines strategy.
        """
        now = datetime.now(timezone.utc)
        sast = now + timedelta(hours=2)
        hour = sast.hour
        rng = random.Random(hash(f"{site_id}-ls-{start}"))

        # Current BESS SOC
        bess_soc = rng.uniform(45, 80)

        # Parse LS window duration
        try:
            ls_start = datetime.fromisoformat(start.replace("Z", "+00:00"))
            ls_end = datetime.fromisoformat(end.replace("Z", "+00:00"))
            ls_hours = (ls_end - ls_start).total_seconds() / 3600.0
        except (ValueError, TypeError):
            ls_hours = 2.5  # Default assumption

        # Solar contribution during LS window
        solar_kw = 0.0
        if 7 <= hour <= 17:
            peak_hour = 12.0
            spread = 3.5
            solar_factor = max(0, 1.0 - ((hour - peak_hour) / spread) ** 2)
            solar_kw = 3200 * solar_factor * rng.uniform(0.5, 0.9)

        # BESS sustain calculation
        critical_load = self.DEFAULT_BUILDING_LOAD_KW * self.CRITICAL_LOAD_PCT
        net_load = max(0, critical_load - solar_kw)
        usable_kwh = self.BESS_CAPACITY_KWH * (bess_soc - self.BESS_MIN_SOC_PCT) / 100.0
        bess_sustain_hours = usable_kwh / net_load if net_load > 0 else 999.0

        generator_needed = bess_sustain_hours < ls_hours
        actions = []

        if bess_soc < 80:
            actions.append(f"Pre-charge BESS to 80% SOC (currently {bess_soc:.0f}%)")

        if solar_kw > 0:
            actions.append(f"Solar contributing {solar_kw:.0f} kW to critical loads")

        actions.append(f"BESS discharge at {min(net_load, self.BESS_RATED_POWER_KW):.0f} kW for critical loads")

        if generator_needed:
            gen_start_delay = bess_sustain_hours
            actions.append(
                f"Generator auto-start after {gen_start_delay:.1f}h when BESS reaches {self.BESS_MIN_SOC_PCT}% SOC"
            )
            strategy = f"BESS sustains for {bess_sustain_hours:.1f}h, then generator takes over"
        else:
            strategy = f"BESS + Solar can sustain {bess_sustain_hours:.1f}h; LS is {ls_hours:.1f}h -- no generator needed"

        actions.append("Post-LS: Resume normal dispatch schedule, recharge BESS")

        return LSResponse(
            site_id=site_id,
            stage=stage,
            ls_start=start,
            ls_end=end,
            strategy=strategy,
            bess_soc_pct=bess_soc,
            bess_can_sustain_hours=bess_sustain_hours,
            generator_needed=generator_needed,
            solar_contribution_kw=solar_kw,
            actions=actions,
        )


# === Singleton ===

_solar_generator_coordinator: Optional[SolarGeneratorCoordinator] = None


def get_solar_generator_coordinator() -> SolarGeneratorCoordinator:
    """Get the singleton generator coordinator instance."""
    global _solar_generator_coordinator
    if _solar_generator_coordinator is None:
        _solar_generator_coordinator = SolarGeneratorCoordinator()
    return _solar_generator_coordinator
