"""Solar Self-Consumption Optimisation — maximise on-site solar use, minimise export.

Target: >95% self-consumption ratio (minimal grid export).

Self-consumption priorities (in order):
  1. Serve building load directly from solar
  2. Charge BESS with excess solar
  3. Export to grid only when BESS full AND excess solar (should be minimal)
  4. Curtail if export not allowed (zero-export SSEG)

Self-consumption ratio = (solar_gen - export) / solar_gen x 100
Self-sufficiency ratio = (solar_consumed + bess_discharge) / total_consumption x 100
"""

import logging
import math
import random
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any

from app.services.solar_config_service import get_site_solar_config
from app.core.site_resolver import get_primary_site

logger = logging.getLogger(__name__)


# === Dataclass Models ===


@dataclass
class SelfConsumptionMetrics:
    """Self-consumption and self-sufficiency ratios for a period."""

    site_id: str
    period: str  # day / week / month
    solar_generated_kwh: float
    solar_self_consumed_kwh: float
    solar_to_bess_kwh: float
    solar_exported_kwh: float
    self_consumption_ratio_pct: float  # (gen - export) / gen * 100
    self_sufficiency_ratio_pct: float  # (solar_consumed + bess_discharge) / total_consumption * 100
    total_consumption_kwh: float
    grid_imported_kwh: float
    bess_discharged_kwh: float
    target_self_consumption_pct: float = 95.0
    meets_target: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "site_id": self.site_id,
            "period": self.period,
            "solar_generated_kwh": round(self.solar_generated_kwh, 1),
            "solar_self_consumed_kwh": round(self.solar_self_consumed_kwh, 1),
            "solar_to_bess_kwh": round(self.solar_to_bess_kwh, 1),
            "solar_exported_kwh": round(self.solar_exported_kwh, 1),
            "self_consumption_ratio_pct": round(self.self_consumption_ratio_pct, 1),
            "self_sufficiency_ratio_pct": round(self.self_sufficiency_ratio_pct, 1),
            "total_consumption_kwh": round(self.total_consumption_kwh, 1),
            "grid_imported_kwh": round(self.grid_imported_kwh, 1),
            "bess_discharged_kwh": round(self.bess_discharged_kwh, 1),
            "target_self_consumption_pct": self.target_self_consumption_pct,
            "meets_target": self.meets_target,
        }


@dataclass
class ExportStatus:
    """Current grid export status."""

    site_id: str
    timestamp: str
    current_export_kw: float
    daily_export_kwh: float
    export_limit_kw: float  # 0 for zero-export
    within_limit: bool
    export_limit_type: str  # zero_export / capped / unlimited
    curtailment_active: bool = False
    curtailment_kw: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "site_id": self.site_id,
            "timestamp": self.timestamp,
            "current_export_kw": round(self.current_export_kw, 1),
            "daily_export_kwh": round(self.daily_export_kwh, 1),
            "export_limit_kw": round(self.export_limit_kw, 0),
            "within_limit": self.within_limit,
            "export_limit_type": self.export_limit_type,
            "curtailment_active": self.curtailment_active,
            "curtailment_kw": round(self.curtailment_kw, 1),
        }


@dataclass
class ExcessPlan:
    """Plan for handling excess solar generation."""

    site_id: str
    timestamp: str
    excess_solar_kw: float
    plan: List[Dict[str, Any]] = field(default_factory=list)
    # plan items: { "priority": 1, "action": "charge_bess", "power_kw": 500, "note": "..." }
    total_absorbed_kw: float = 0.0
    remaining_export_kw: float = 0.0
    bess_can_absorb: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "site_id": self.site_id,
            "timestamp": self.timestamp,
            "excess_solar_kw": round(self.excess_solar_kw, 1),
            "plan": self.plan,
            "total_absorbed_kw": round(self.total_absorbed_kw, 1),
            "remaining_export_kw": round(self.remaining_export_kw, 1),
            "bess_can_absorb": self.bess_can_absorb,
        }


@dataclass
class EnergyBalanceInterval:
    """Energy balance for a single time interval."""

    timestamp: str
    solar_gen_kwh: float
    solar_self_consumed_kwh: float
    solar_to_bess_kwh: float
    solar_exported_kwh: float
    grid_imported_kwh: float
    bess_discharged_kwh: float
    building_consumed_kwh: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "solar_gen_kwh": round(self.solar_gen_kwh, 2),
            "solar_self_consumed_kwh": round(self.solar_self_consumed_kwh, 2),
            "solar_to_bess_kwh": round(self.solar_to_bess_kwh, 2),
            "solar_exported_kwh": round(self.solar_exported_kwh, 2),
            "grid_imported_kwh": round(self.grid_imported_kwh, 2),
            "bess_discharged_kwh": round(self.bess_discharged_kwh, 2),
            "building_consumed_kwh": round(self.building_consumed_kwh, 2),
        }


@dataclass
class EnergyBalance:
    """Complete daily energy balance breakdown."""

    site_id: str
    period: str  # day / week / month
    date: str
    solar_generated_kwh: float
    solar_self_consumed_kwh: float
    solar_to_bess_kwh: float
    solar_exported_kwh: float
    grid_imported_kwh: float
    bess_discharged_kwh: float
    building_consumed_kwh: float
    self_consumption_pct: float
    self_sufficiency_pct: float
    balance_check: bool  # True if energy in = energy out (sanity check)
    intervals: List[EnergyBalanceInterval] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "site_id": self.site_id,
            "period": self.period,
            "date": self.date,
            "summary": {
                "solar_generated_kwh": round(self.solar_generated_kwh, 1),
                "solar_self_consumed_kwh": round(self.solar_self_consumed_kwh, 1),
                "solar_to_bess_kwh": round(self.solar_to_bess_kwh, 1),
                "solar_exported_kwh": round(self.solar_exported_kwh, 1),
                "grid_imported_kwh": round(self.grid_imported_kwh, 1),
                "bess_discharged_kwh": round(self.bess_discharged_kwh, 1),
                "building_consumed_kwh": round(self.building_consumed_kwh, 1),
            },
            "ratios": {
                "self_consumption_pct": round(self.self_consumption_pct, 1),
                "self_sufficiency_pct": round(self.self_sufficiency_pct, 1),
            },
            "balance_check": self.balance_check,
            "interval_count": len(self.intervals),
            "intervals": [i.to_dict() for i in self.intervals],
        }


# === Service ===


class SolarSelfConsumptionService:
    """Self-consumption optimisation: maximise on-site solar use.

    Coordinates with BESS dispatch to ensure excess solar charges the
    battery rather than being exported. For Site-002 (297 kWp PV,
    200 kWh BESS), target is >95% self-consumption.
    """

    # Site-002 reference parameters
    PV_CAPACITY_KWP = 297.0  # 4 × 100 kVA rooftop inverters
    BESS_CAPACITY_KWH = 200.0  # Huawei LUNA2000-200KWH-2H1
    BESS_RATED_POWER_KW = 100.0  # 0.5C rate
    BESS_EFFICIENCY = 0.90
    BASE_LOAD_KW = 1800.0

    # Export limits (SSEG Category B)
    EXPORT_LIMIT_KW = 297.0  # SSEG Category B max export
    EXPORT_LIMIT_TYPE = "capped"  # zero_export / capped / unlimited

    def __init__(self):
        self._energy_balance_cache: Dict[str, EnergyBalance] = {}
        try:
            cfg = get_site_solar_config()
            self.PV_CAPACITY_KWP = cfg.pv.total_capacity_kwp
            self.BESS_CAPACITY_KWH = cfg.bess.capacity_kwh
            self.BESS_RATED_POWER_KW = cfg.bess.rated_power_kw
            self.EXPORT_LIMIT_KW = cfg.grid.max_export_kw
        except Exception:
            pass
        self._seed_demo_data(get_primary_site() or "unknown")

    def _seed_demo_data(self, site_id: str) -> None:
        """Seed a full day energy balance for demo."""
        balance = self._simulate_day_balance(site_id)
        self._energy_balance_cache[site_id] = balance
        logger.info(
            "Seeded energy balance for %s: %.0f kWh solar, %.1f%% self-consumption",
            site_id,
            balance.solar_generated_kwh,
            balance.self_consumption_pct,
        )

    @staticmethod
    def _solar_generation_kw(hour: float) -> float:
        """Simulate 297 kWp solar generation for JHB latitude."""
        if hour < 6 or hour > 19:
            return 0.0
        peak_hour = 12.5
        spread = 3.5
        peak_kw = 244.0  # ~82% performance ratio on 297 kWp
        gen = peak_kw * math.exp(-0.5 * ((hour - peak_hour) / spread) ** 2)
        return max(0, gen * random.uniform(0.93, 1.07))

    @staticmethod
    def _site_load_kw(hour: float) -> float:
        """Simulate Site-002 building load profile."""
        if hour < 5:
            return 1200 + random.uniform(-30, 30)
        elif hour < 7:
            return 1200 + (hour - 5) * 500 + random.uniform(-30, 30)
        elif hour < 9:
            return 2200 + (hour - 7) * 600 + random.uniform(-50, 50)
        elif hour < 10:
            return 3400 + random.uniform(-50, 50)
        elif hour < 16:
            return 3200 + random.uniform(-100, 100)
        elif hour < 18:
            return 2800 + random.uniform(-50, 50)
        elif hour < 20:
            return 2000 + random.uniform(-40, 40)
        elif hour < 22:
            return 1500 + random.uniform(-30, 30)
        else:
            return 1200 + random.uniform(-30, 30)

    def _simulate_day_balance(self, site_id: str) -> EnergyBalance:
        """Simulate complete day energy balance with 15-min intervals."""
        now = datetime.now(timezone.utc)
        sast = now + timedelta(hours=2)
        start_sast = sast.replace(hour=0, minute=0, second=0, microsecond=0)
        start_utc = start_sast - timedelta(hours=2)

        intervals: List[EnergyBalanceInterval] = []
        totals = {
            "solar_gen": 0.0,
            "solar_self": 0.0,
            "solar_bess": 0.0,
            "solar_export": 0.0,
            "grid_import": 0.0,
            "bess_discharge": 0.0,
            "building": 0.0,
        }

        bess_soc = 15.0  # Start of day: low after overnight discharge
        interval_hours = 0.25  # 15 minutes

        t = start_utc
        end = min(start_utc + timedelta(hours=24), now)

        while t < end:
            sast_t = t + timedelta(hours=2)
            hour = sast_t.hour + sast_t.minute / 60.0

            solar_kw = self._solar_generation_kw(hour)
            load_kw = self._site_load_kw(hour)

            solar_kwh = solar_kw * interval_hours
            load_kwh = load_kw * interval_hours

            # === Self-consumption priority logic ===

            # 1. Solar directly serves building load
            solar_to_building = min(solar_kwh, load_kwh)
            remaining_solar = solar_kwh - solar_to_building
            remaining_load = load_kwh - solar_to_building

            # 2. Excess solar charges BESS
            solar_to_bess = 0.0
            if remaining_solar > 0 and bess_soc < 95.0:
                max_charge_kwh = self.BESS_RATED_POWER_KW * interval_hours
                charge_room_kwh = self.BESS_CAPACITY_KWH * (95.0 - bess_soc) / 100.0
                solar_to_bess = min(remaining_solar, max_charge_kwh, charge_room_kwh) * self.BESS_EFFICIENCY
                bess_soc += (solar_to_bess / self.BESS_CAPACITY_KWH) * 100
                remaining_solar -= solar_to_bess / self.BESS_EFFICIENCY  # pre-efficiency

            # 3. Remaining solar exports (should be minimal with BESS)
            solar_exported = max(0, remaining_solar)

            # 4. BESS discharge to serve remaining load (during peak hours)
            bess_discharge = 0.0
            if remaining_load > 0 and bess_soc > 10.0:
                # Only discharge during peak/standard hours, not off-peak
                if 7 <= hour < 20:
                    max_discharge_kwh = self.BESS_RATED_POWER_KW * interval_hours
                    available_kwh = self.BESS_CAPACITY_KWH * (bess_soc - 10.0) / 100.0
                    bess_discharge = min(remaining_load, max_discharge_kwh, available_kwh)
                    bess_soc -= (bess_discharge / self.BESS_CAPACITY_KWH) * 100
                    remaining_load -= bess_discharge

            # 5. Grid import for whatever remains
            grid_import = max(0, remaining_load)

            # Off-peak grid charging of BESS
            if hour >= 22 or hour < 6:
                if bess_soc < 90.0:
                    charge_kwh = min(
                        self.BESS_RATED_POWER_KW * interval_hours,
                        self.BESS_CAPACITY_KWH * (90.0 - bess_soc) / 100.0,
                    )
                    bess_soc += (charge_kwh * self.BESS_EFFICIENCY / self.BESS_CAPACITY_KWH) * 100
                    grid_import += charge_kwh

            intervals.append(
                EnergyBalanceInterval(
                    timestamp=t.isoformat(),
                    solar_gen_kwh=solar_kwh,
                    solar_self_consumed_kwh=solar_to_building,
                    solar_to_bess_kwh=solar_to_bess,
                    solar_exported_kwh=solar_exported,
                    grid_imported_kwh=grid_import,
                    bess_discharged_kwh=bess_discharge,
                    building_consumed_kwh=load_kwh,
                )
            )

            totals["solar_gen"] += solar_kwh
            totals["solar_self"] += solar_to_building
            totals["solar_bess"] += solar_to_bess
            totals["solar_export"] += solar_exported
            totals["grid_import"] += grid_import
            totals["bess_discharge"] += bess_discharge
            totals["building"] += load_kwh

            t += timedelta(minutes=15)

        # Calculate ratios
        sc_ratio = 0.0
        if totals["solar_gen"] > 0:
            sc_ratio = ((totals["solar_gen"] - totals["solar_export"]) / totals["solar_gen"]) * 100

        ss_ratio = 0.0
        if totals["building"] > 0:
            ss_ratio = ((totals["solar_self"] + totals["bess_discharge"]) / totals["building"]) * 100

        # Balance check: supply = demand (within rounding tolerance)
        supply = totals["solar_gen"] + totals["grid_import"] + totals["bess_discharge"]
        demand = totals["building"] + totals["solar_bess"] + totals["solar_export"]
        balance_ok = abs(supply - demand) < supply * 0.05  # 5% tolerance

        return EnergyBalance(
            site_id=site_id,
            period="day",
            date=sast.strftime("%Y-%m-%d"),
            solar_generated_kwh=totals["solar_gen"],
            solar_self_consumed_kwh=totals["solar_self"],
            solar_to_bess_kwh=totals["solar_bess"],
            solar_exported_kwh=totals["solar_export"],
            grid_imported_kwh=totals["grid_import"],
            bess_discharged_kwh=totals["bess_discharge"],
            building_consumed_kwh=totals["building"],
            self_consumption_pct=sc_ratio,
            self_sufficiency_pct=ss_ratio,
            balance_check=balance_ok,
            intervals=intervals,
        )

    # === Self-consumption metrics ===

    def get_selfconsumption_ratio(self, site_id: str, period: str = "day") -> SelfConsumptionMetrics:
        """Get self-consumption and self-sufficiency ratios for a period."""
        balance = self._energy_balance_cache.get(site_id)
        if not balance:
            balance = self._simulate_day_balance(site_id)
            self._energy_balance_cache[site_id] = balance

        multiplier = 1.0
        if period == "week":
            multiplier = 5.0  # weekdays
        elif period == "month":
            multiplier = 22.0  # business days

        solar_gen = balance.solar_generated_kwh * multiplier
        solar_self = balance.solar_self_consumed_kwh * multiplier
        solar_bess = balance.solar_to_bess_kwh * multiplier
        solar_export = balance.solar_exported_kwh * multiplier
        grid_import = balance.grid_imported_kwh * multiplier
        bess_discharge = balance.bess_discharged_kwh * multiplier
        total_consumption = balance.building_consumed_kwh * multiplier

        # Ratios stay the same regardless of period multiplier
        sc_ratio = balance.self_consumption_pct
        ss_ratio = balance.self_sufficiency_pct

        return SelfConsumptionMetrics(
            site_id=site_id,
            period=period,
            solar_generated_kwh=solar_gen,
            solar_self_consumed_kwh=solar_self,
            solar_to_bess_kwh=solar_bess,
            solar_exported_kwh=solar_export,
            self_consumption_ratio_pct=sc_ratio,
            self_sufficiency_ratio_pct=ss_ratio,
            total_consumption_kwh=total_consumption,
            grid_imported_kwh=grid_import,
            bess_discharged_kwh=bess_discharge,
            meets_target=sc_ratio >= 95.0,
        )

    # === Export status ===

    def get_export_status(self, site_id: str) -> ExportStatus:
        """Get current grid export status and limit compliance."""
        now = datetime.now(timezone.utc)
        sast = now + timedelta(hours=2)
        hour = sast.hour + sast.minute / 60.0

        solar_kw = self._solar_generation_kw(hour)
        load_kw = self._site_load_kw(hour)

        # Net export = solar - load (if positive, we're exporting)
        net = solar_kw - load_kw
        current_export = max(0, net)

        # BESS should absorb most excess, leaving minimal export
        if current_export > 0:
            bess_absorb = min(current_export, self.BESS_RATED_POWER_KW)
            current_export = max(0, current_export - bess_absorb)

        # Estimate daily export from balance
        balance = self._energy_balance_cache.get(site_id)
        daily_export = balance.solar_exported_kwh if balance else 0.0

        within_limit = current_export <= self.EXPORT_LIMIT_KW

        curtailment = False
        curtailment_kw = 0.0
        if current_export > self.EXPORT_LIMIT_KW:
            curtailment = True
            curtailment_kw = current_export - self.EXPORT_LIMIT_KW

        return ExportStatus(
            site_id=site_id,
            timestamp=now.isoformat(),
            current_export_kw=current_export,
            daily_export_kwh=daily_export,
            export_limit_kw=self.EXPORT_LIMIT_KW,
            within_limit=within_limit,
            export_limit_type=self.EXPORT_LIMIT_TYPE,
            curtailment_active=curtailment,
            curtailment_kw=curtailment_kw,
        )

    # === Excess generation plan ===

    def get_excess_generation_plan(self, site_id: str) -> ExcessPlan:
        """Plan for handling excess solar: BESS first, building second, export last."""
        now = datetime.now(timezone.utc)
        sast = now + timedelta(hours=2)
        hour = sast.hour + sast.minute / 60.0

        solar_kw = self._solar_generation_kw(hour)
        load_kw = self._site_load_kw(hour)
        excess = max(0, solar_kw - load_kw)

        plan_items: List[Dict[str, Any]] = []
        total_absorbed = 0.0

        if excess <= 0:
            return ExcessPlan(
                site_id=site_id,
                timestamp=now.isoformat(),
                excess_solar_kw=0,
                plan=[
                    {
                        "priority": 1,
                        "action": "no_excess",
                        "power_kw": 0,
                        "note": f"No excess solar. Generation {solar_kw:.0f} kW < Load {load_kw:.0f} kW",
                    }
                ],
                total_absorbed_kw=0,
                remaining_export_kw=0,
                bess_can_absorb=True,
            )

        # Get BESS SOC to determine absorption capacity
        try:
            from app.services.solar_dispatch_service import get_solar_dispatch_service

            dispatch = get_solar_dispatch_service()
            status = dispatch.get_dispatch_status(site_id)
            bess_soc = status.bess_soc_pct if status else 50.0
        except Exception:
            bess_soc = 50.0

        remaining_excess = excess

        # Priority 1: Charge BESS
        if bess_soc < 95.0:
            bess_room_kwh = self.BESS_CAPACITY_KWH * (95.0 - bess_soc) / 100.0
            bess_absorb = min(remaining_excess, self.BESS_RATED_POWER_KW)
            plan_items.append(
                {
                    "priority": 1,
                    "action": "charge_bess",
                    "power_kw": round(bess_absorb, 0),
                    "note": (
                        f"BESS at {bess_soc:.1f}% SOC, can absorb"
                        f" {bess_absorb:.0f} kW"
                        f" ({bess_room_kwh:.0f} kWh remaining capacity)"
                    ),
                }
            )
            total_absorbed += bess_absorb
            remaining_excess -= bess_absorb

        # Priority 2: Increase building load (pre-cool, charge UPS, etc.)
        if remaining_excess > 0:
            deferrable_load = min(remaining_excess, 200)  # ~200 kW of deferrable loads
            if deferrable_load > 50:
                plan_items.append(
                    {
                        "priority": 2,
                        "action": "increase_site_load",
                        "power_kw": round(deferrable_load, 0),
                        "note": "Bring forward deferrable loads: pre-cooling, UPS charging, hot water",
                    }
                )
                total_absorbed += deferrable_load
                remaining_excess -= deferrable_load

        # Priority 3: Export (if allowed and economical)
        if remaining_excess > 0:
            if self.EXPORT_LIMIT_TYPE == "unlimited":
                plan_items.append(
                    {
                        "priority": 3,
                        "action": "export_to_grid",
                        "power_kw": round(remaining_excess, 0),
                        "note": f"Export {remaining_excess:.0f} kW to grid (SSEG feed-in)",
                    }
                )
                total_absorbed += remaining_excess
                remaining_excess = 0
            elif self.EXPORT_LIMIT_TYPE == "capped":
                exportable = min(remaining_excess, self.EXPORT_LIMIT_KW)
                if exportable > 0:
                    plan_items.append(
                        {
                            "priority": 3,
                            "action": "export_to_grid",
                            "power_kw": round(exportable, 0),
                            "note": f"Export {exportable:.0f} kW (within {self.EXPORT_LIMIT_KW:.0f} kW cap)",
                        }
                    )
                    total_absorbed += exportable
                    remaining_excess -= exportable

        # Priority 4: Curtail if still excess
        if remaining_excess > 0:
            plan_items.append(
                {
                    "priority": 4,
                    "action": "curtail",
                    "power_kw": round(remaining_excess, 0),
                    "note": f"Curtail {remaining_excess:.0f} kW (BESS full, export limit reached)",
                }
            )
            total_absorbed += remaining_excess
            remaining_export = 0
        else:
            remaining_export = remaining_excess

        bess_can_absorb = bess_soc < 90.0

        return ExcessPlan(
            site_id=site_id,
            timestamp=now.isoformat(),
            excess_solar_kw=excess,
            plan=plan_items,
            total_absorbed_kw=total_absorbed,
            remaining_export_kw=max(0, remaining_export),
            bess_can_absorb=bess_can_absorb,
        )

    # === Energy balance ===

    def get_energy_balance(self, site_id: str, period: str = "day") -> EnergyBalance:
        """Get complete energy balance breakdown for a period."""
        balance = self._energy_balance_cache.get(site_id)
        if not balance:
            balance = self._simulate_day_balance(site_id)
            self._energy_balance_cache[site_id] = balance

        if period == "day":
            return balance

        # For week/month, scale totals (intervals remain daily)
        multiplier = 5.0 if period == "week" else 22.0

        return EnergyBalance(
            site_id=site_id,
            period=period,
            date=balance.date,
            solar_generated_kwh=balance.solar_generated_kwh * multiplier,
            solar_self_consumed_kwh=balance.solar_self_consumed_kwh * multiplier,
            solar_to_bess_kwh=balance.solar_to_bess_kwh * multiplier,
            solar_exported_kwh=balance.solar_exported_kwh * multiplier,
            grid_imported_kwh=balance.grid_imported_kwh * multiplier,
            bess_discharged_kwh=balance.bess_discharged_kwh * multiplier,
            building_consumed_kwh=balance.building_consumed_kwh * multiplier,
            self_consumption_pct=balance.self_consumption_pct,
            self_sufficiency_pct=balance.self_sufficiency_pct,
            balance_check=balance.balance_check,
            intervals=balance.intervals,  # Always daily intervals
        )


# === Singleton ===

_solar_selfconsumption_service: Optional[SolarSelfConsumptionService] = None


def get_solar_selfconsumption_service() -> SolarSelfConsumptionService:
    """Get the singleton solar self-consumption service instance."""
    global _solar_selfconsumption_service
    if _solar_selfconsumption_service is None:
        _solar_selfconsumption_service = SolarSelfConsumptionService()
    return _solar_selfconsumption_service
