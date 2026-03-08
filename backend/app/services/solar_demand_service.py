"""Solar Demand Charge Management — peak shaving, NMD tracking, load deferral.

Demand charges are typically 30-40% of a commercial electricity bill in SA.
For Site-002 (NMD 1,820 kVA), shaving just the top 200 kW of demand with BESS
saves ~R79,096/month (200 x R395.48/kVA).

NMD (Notified Maximum Demand):
  - Contractual maximum demand with City Power
  - Exceeding NMD incurs penalty charges
  - NMD ratchets up for 12 months if actual demand exceeds it
  - Alert at 85% of NMD to allow proactive BESS discharge

Peak shaving strategy:
  - Monitor 15-minute rolling demand
  - When demand approaches NMD threshold, discharge BESS to cap load
  - Peak shaving takes priority over TOU arbitrage during demand spikes
"""

import logging
import math
import random
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any

from app.services.solar_config_service import get_site_solar_config
from app.core.site_resolver import get_primary_site_code

logger = logging.getLogger(__name__)


# === Dataclass Models ===


@dataclass
class DemandStatus:
    """Current building demand snapshot."""

    site_id: str
    timestamp: str
    current_demand_kw: float
    monthly_peak_kw: float
    nmd_limit_kva: float
    headroom_kw: float  # nmd_limit - current_demand
    headroom_pct: float
    demand_trend: str  # rising / falling / stable
    alert_level: str  # normal / warning / critical
    bess_shaving_active: bool = False
    bess_shaving_kw: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "site_id": self.site_id,
            "timestamp": self.timestamp,
            "current_demand_kw": round(self.current_demand_kw, 1),
            "monthly_peak_kw": round(self.monthly_peak_kw, 1),
            "nmd_limit_kva": round(self.nmd_limit_kva, 0),
            "headroom_kw": round(self.headroom_kw, 1),
            "headroom_pct": round(self.headroom_pct, 1),
            "demand_trend": self.demand_trend,
            "alert_level": self.alert_level,
            "bess_shaving_active": self.bess_shaving_active,
            "bess_shaving_kw": round(self.bess_shaving_kw, 0),
        }


@dataclass
class DemandInterval:
    """A single 15-minute demand reading."""

    timestamp: str
    demand_kw: float
    solar_offset_kw: float = 0.0
    bess_offset_kw: float = 0.0
    net_demand_kw: float = 0.0  # after solar + bess offset

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "demand_kw": round(self.demand_kw, 1),
            "solar_offset_kw": round(self.solar_offset_kw, 1),
            "bess_offset_kw": round(self.bess_offset_kw, 1),
            "net_demand_kw": round(self.net_demand_kw, 1),
        }


@dataclass
class DemandProfile:
    """15-minute demand profile for a period."""

    site_id: str
    period: str  # day / week
    intervals: List[DemandInterval] = field(default_factory=list)
    peak_demand_kw: float = 0.0
    peak_demand_time: str = ""
    avg_demand_kw: float = 0.0
    peak_with_shaving_kw: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "site_id": self.site_id,
            "period": self.period,
            "interval_count": len(self.intervals),
            "peak_demand_kw": round(self.peak_demand_kw, 1),
            "peak_demand_time": self.peak_demand_time,
            "avg_demand_kw": round(self.avg_demand_kw, 1),
            "peak_with_shaving_kw": round(self.peak_with_shaving_kw, 1),
            "peak_reduction_kw": round(self.peak_demand_kw - self.peak_with_shaving_kw, 1),
            "intervals": [i.to_dict() for i in self.intervals],
        }


@dataclass
class MonthlyPeak:
    """Monthly peak demand record for NMD ratchet tracking."""

    month: str  # YYYY-MM
    peak_demand_kw: float
    peak_timestamp: str
    nmd_limit_kva: float
    exceeded_nmd: bool
    penalty_zar: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "month": self.month,
            "peak_demand_kw": round(self.peak_demand_kw, 1),
            "peak_timestamp": self.peak_timestamp,
            "nmd_limit_kva": round(self.nmd_limit_kva, 0),
            "exceeded_nmd": self.exceeded_nmd,
            "penalty_zar": round(self.penalty_zar, 2),
        }


@dataclass
class NMDStatus:
    """NMD compliance and ratchet tracking."""

    site_id: str
    nmd_limit_kva: float
    current_demand_kw: float
    monthly_peak_kw: float
    utilisation_pct: float  # monthly_peak / nmd_limit * 100
    alert_level: str  # normal / warning / critical
    alert_message: str
    ratchet_risk: bool  # True if peak is approaching NMD
    months_history: List[MonthlyPeak] = field(default_factory=list)
    estimated_annual_penalty_zar: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "site_id": self.site_id,
            "nmd_limit_kva": round(self.nmd_limit_kva, 0),
            "current_demand_kw": round(self.current_demand_kw, 1),
            "monthly_peak_kw": round(self.monthly_peak_kw, 1),
            "utilisation_pct": round(self.utilisation_pct, 1),
            "alert_level": self.alert_level,
            "alert_message": self.alert_message,
            "ratchet_risk": self.ratchet_risk,
            "months_history": [m.to_dict() for m in self.months_history],
            "estimated_annual_penalty_zar": round(self.estimated_annual_penalty_zar, 2),
        }


@dataclass
class PeakRiskAssessment:
    """Prediction of peak demand risk for the current day."""

    site_id: str
    timestamp: str
    predicted_peak_kw: float
    predicted_peak_time: str
    nmd_limit_kva: float
    risk_level: str  # low / medium / high / critical
    risk_pct: float  # predicted_peak / nmd * 100
    contributing_factors: List[str] = field(default_factory=list)
    recommendation: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "site_id": self.site_id,
            "timestamp": self.timestamp,
            "predicted_peak_kw": round(self.predicted_peak_kw, 1),
            "predicted_peak_time": self.predicted_peak_time,
            "nmd_limit_kva": round(self.nmd_limit_kva, 0),
            "risk_level": self.risk_level,
            "risk_pct": round(self.risk_pct, 1),
            "contributing_factors": self.contributing_factors,
            "recommendation": self.recommendation,
        }


@dataclass
class ShavingPotential:
    """How much BESS can reduce peak demand."""

    site_id: str
    current_peak_kw: float
    bess_available_kw: float
    bess_soc_pct: float
    bess_duration_hours: float  # how long BESS can sustain shaving
    max_shaving_kw: float
    achievable_peak_kw: float  # current_peak - max_shaving
    demand_savings_zar_month: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "site_id": self.site_id,
            "current_peak_kw": round(self.current_peak_kw, 1),
            "bess_available_kw": round(self.bess_available_kw, 1),
            "bess_soc_pct": round(self.bess_soc_pct, 1),
            "bess_duration_hours": round(self.bess_duration_hours, 2),
            "max_shaving_kw": round(self.max_shaving_kw, 1),
            "achievable_peak_kw": round(self.achievable_peak_kw, 1),
            "demand_savings_zar_month": round(self.demand_savings_zar_month, 2),
        }


@dataclass
class ShavingRecommendation:
    """When to pre-emptively discharge BESS to cap demand."""

    site_id: str
    timestamp: str
    should_shave: bool
    target_demand_kw: float  # cap demand at this level
    discharge_kw: float  # BESS discharge power needed
    reason: str
    priority: str  # low / medium / high / critical
    estimated_savings_zar: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "site_id": self.site_id,
            "timestamp": self.timestamp,
            "should_shave": self.should_shave,
            "target_demand_kw": round(self.target_demand_kw, 1),
            "discharge_kw": round(self.discharge_kw, 1),
            "reason": self.reason,
            "priority": self.priority,
            "estimated_savings_zar": round(self.estimated_savings_zar, 2),
        }


@dataclass
class DeferralSuggestion:
    """Non-critical load that could shift to off-peak."""

    equipment_code: str
    equipment_name: str
    load_kw: float
    current_schedule: str
    suggested_schedule: str
    savings_zar_month: float
    criticality: str  # low / medium / high
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "equipment_code": self.equipment_code,
            "equipment_name": self.equipment_name,
            "load_kw": round(self.load_kw, 1),
            "current_schedule": self.current_schedule,
            "suggested_schedule": self.suggested_schedule,
            "savings_zar_month": round(self.savings_zar_month, 2),
            "criticality": self.criticality,
            "reason": self.reason,
        }


@dataclass
class DemandSavings:
    """Demand charge savings from peak shaving."""

    site_id: str
    period: str  # month
    unmanaged_peak_kw: float
    managed_peak_kw: float
    peak_reduction_kw: float
    demand_charge_per_kva: float  # R395.48/kVA for City Power
    unmanaged_cost_zar: float
    managed_cost_zar: float
    savings_zar: float
    savings_pct: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "site_id": self.site_id,
            "period": self.period,
            "unmanaged_peak_kw": round(self.unmanaged_peak_kw, 1),
            "managed_peak_kw": round(self.managed_peak_kw, 1),
            "peak_reduction_kw": round(self.peak_reduction_kw, 1),
            "demand_charge_per_kva": self.demand_charge_per_kva,
            "unmanaged_cost_zar": round(self.unmanaged_cost_zar, 2),
            "managed_cost_zar": round(self.managed_cost_zar, 2),
            "savings_zar": round(self.savings_zar, 2),
            "savings_pct": round(self.savings_pct, 1),
        }


# === Service ===


class SolarDemandService:
    """Demand charge management: peak shaving, NMD tracking, load deferral.

    Monitors building demand against NMD limits and coordinates BESS discharge
    to shave demand peaks. Peak shaving takes priority over TOU arbitrage when
    demand approaches NMD threshold.
    """

    # Loaded from solar_config_service; class attrs are fallback defaults only
    NMD_LIMIT_KVA = 1820.0  # City Power contractual NMD (from energy_centre.json)
    DEMAND_CHARGE_PER_KVA = 395.48  # ZAR/kVA/month (City Power 2025/26 verified)
    NMD_WARNING_PCT = 85.0  # Alert when demand exceeds 85% of NMD
    NMD_CRITICAL_PCT = 95.0  # Critical when demand exceeds 95% of NMD

    # BESS parameters (Huawei LUNA2000, from site-002_config.json)
    BESS_CAPACITY_KWH = 200.0
    BESS_RATED_POWER_KW = 100.0  # 0.5C rate
    BESS_MIN_SOC_PCT = 10.0

    # Building profile (Site-002 Sandton office tower)
    BASE_LOAD_KW = 900.0
    PEAK_DEMAND_KW = 1850.0

    def __init__(self):
        self._demand_history: Dict[str, List[DemandInterval]] = {}
        self._monthly_peaks: Dict[str, List[MonthlyPeak]] = {}
        self._nmd_cache: Dict[str, float] = {}
        self._load_config(get_primary_site_code() or "unknown")
        self._seed_demo_data(get_primary_site_code() or "unknown")

    def _load_config(self, site_id: str):
        """Load site parameters from solar_config_service."""
        try:
            cfg = get_site_solar_config(site_id)
            self.NMD_LIMIT_KVA = cfg.grid.nmd_limit_kva
            self.DEMAND_CHARGE_PER_KVA = cfg.tariff.demand_charge_r_kva()
            self.BESS_CAPACITY_KWH = cfg.bess.capacity_kwh
            self.BESS_RATED_POWER_KW = cfg.bess.rated_power_kw
        except Exception as e:
            logger.warning(f"Failed to load solar config for {site_id}, using defaults: {e}")

    async def get_nmd_limit(self, site_id: str) -> float:
        """PHASE 081: Fetch actual NMD from database, fallback to hardcoded.

        Queries buildings table for nmd_limit_kva extracted from municipal bills.
        Falls back to NMD_LIMIT_KVA constant if not found in database.

        Args:
            site_id: Building/site code (e.g., "S002", "site-005")

        Returns:
            NMD limit in kVA from database or fallback constant
        """
        # Check cache first
        if site_id in self._nmd_cache:
            return self._nmd_cache[site_id]

        try:
            from app.database.repositories.site_repository import SiteRepository

            building_repo = SiteRepository()
            building = await building_repo.get_by_code(site_id)

            if building and building.get("nmd_limit_kva"):
                nmd_limit = float(building["nmd_limit_kva"])
                self._nmd_cache[site_id] = nmd_limit
                logger.info(f"Loaded NMD from database for {site_id}: {nmd_limit} kVA")
                return nmd_limit
            else:
                logger.debug(f"No NMD in database for {site_id}, using default: {self.NMD_LIMIT_KVA} kVA")
        except Exception as exc:
            logger.warning(f"Failed to fetch NMD from database for {site_id}: {exc}")

        # Fallback to constant
        self._nmd_cache[site_id] = self.NMD_LIMIT_KVA
        return self.NMD_LIMIT_KVA

    def _seed_demo_data(self, site_id: str) -> None:
        """Seed realistic demand profile and monthly peak history."""
        now = datetime.now(timezone.utc)
        sast = now + timedelta(hours=2)

        # Seed 15-minute demand intervals for today (starting from midnight SAST)
        start_sast = sast.replace(hour=0, minute=0, second=0, microsecond=0)
        start_utc = start_sast - timedelta(hours=2)

        intervals: List[DemandInterval] = []
        t = start_utc

        while t <= now:
            sast_t = t + timedelta(hours=2)
            hour = sast_t.hour + sast_t.minute / 60.0

            # Building load profile with morning and afternoon peaks
            building_kw = self._simulated_site_load(hour)

            # Solar offset (bell curve peaking at solar noon)
            solar_kw = self._simulated_solar_generation(hour)

            # BESS peak shaving: discharge when demand > NMD target
            nmd_target = self.NMD_LIMIT_KVA * 0.85  # Target 85% of NMD
            net_demand = building_kw - solar_kw
            bess_kw = 0.0

            if net_demand > nmd_target:
                bess_kw = min(self.BESS_RATED_POWER_KW, net_demand - nmd_target)
                net_demand -= bess_kw

            intervals.append(
                DemandInterval(
                    timestamp=t.isoformat(),
                    demand_kw=building_kw,
                    solar_offset_kw=solar_kw,
                    bess_offset_kw=bess_kw,
                    net_demand_kw=max(0, net_demand),
                )
            )

            t += timedelta(minutes=15)

        self._demand_history[site_id] = intervals

        # Seed 12 months of peak history
        monthly_peaks: List[MonthlyPeak] = []
        for months_ago in range(12, 0, -1):
            month_dt = now - timedelta(days=months_ago * 30)
            month_str = month_dt.strftime("%Y-%m")

            # Simulate seasonal variation (winter peaks higher in SA)
            is_winter = month_dt.month in (6, 7, 8)
            base_peak = 1800.0 if is_winter else 1700.0
            noise = random.uniform(-100, 100)
            peak = base_peak + noise

            # Simulate BESS shaving ~200kW off the top
            managed_peak = peak - random.uniform(150, 250)

            exceeded = managed_peak > self.NMD_LIMIT_KVA
            penalty = 0.0
            if exceeded:
                excess = managed_peak - self.NMD_LIMIT_KVA
                penalty = excess * self.DEMAND_CHARGE_PER_KVA * 1.5  # penalty multiplier

            peak_day = random.randint(1, 28)
            peak_hour = random.choice([9, 10, 14, 15])
            peak_ts = month_dt.replace(day=peak_day, hour=peak_hour, minute=30, second=0, microsecond=0)

            monthly_peaks.append(
                MonthlyPeak(
                    month=month_str,
                    peak_demand_kw=round(managed_peak, 1),
                    peak_timestamp=peak_ts.isoformat(),
                    nmd_limit_kva=self.NMD_LIMIT_KVA,
                    exceeded_nmd=exceeded,
                    penalty_zar=penalty,
                )
            )

        self._monthly_peaks[site_id] = monthly_peaks
        logger.info(
            "Seeded demand data for %s: %d intervals, %d monthly peaks",
            site_id,
            len(intervals),
            len(monthly_peaks),
        )

    @staticmethod
    def _simulated_site_load(hour: float) -> float:
        """Simulate Site-002 building load profile (kW) by hour of day.

        Sandton office tower: base load ~900 kW (overnight), peak ~1750-1850 kW
        during business hours (09:30-15:00). Morning ramp 06:00-09:30.
        """
        if hour < 5:
            return 900 + random.uniform(-30, 30)
        elif hour < 6:
            return 900 + (hour - 5) * 100 + random.uniform(-20, 20)
        elif hour < 7:
            return 1000 + (hour - 6) * 200 + random.uniform(-25, 25)
        elif hour < 8:
            return 1200 + (hour - 7) * 250 + random.uniform(-30, 30)
        elif hour < 9:
            return 1450 + (hour - 8) * 200 + random.uniform(-30, 30)
        elif hour < 9.5:
            return 1650 + (hour - 9) * 200 + random.uniform(-25, 25)
        elif hour < 10:
            return 1750 + random.uniform(-40, 40)
        elif hour < 12:
            return 1700 + random.uniform(-50, 50)
        elif hour < 13:
            return 1650 + random.uniform(-40, 40)
        elif hour < 14:
            return 1700 + random.uniform(-50, 50)
        elif hour < 15:
            return 1850 + random.uniform(-50, 50)  # afternoon peak
        elif hour < 16:
            return 1750 + random.uniform(-40, 40)
        elif hour < 17:
            return 1550 + random.uniform(-40, 40)
        elif hour < 18:
            return 1300 + random.uniform(-30, 30)
        elif hour < 19:
            return 1100 + random.uniform(-25, 25)
        elif hour < 20:
            return 1000 + random.uniform(-20, 20)
        elif hour < 22:
            return 950 + random.uniform(-20, 20)
        else:
            return 900 + random.uniform(-20, 20)

    @staticmethod
    def _simulated_solar_generation(hour: float) -> float:
        """Simulate solar generation (kW) for 297 kWp Site-002 installation.

        Bell curve peaking at ~238 kW at solar noon (12:30 SAST).
        297 kWp x ~80% performance ratio = ~238 kW peak output.
        """
        if hour < 6 or hour > 19:
            return 0.0

        # Bell curve centered on 12.5 (solar noon SAST)
        peak_hour = 12.5
        spread = 3.5  # hours of significant generation either side
        peak_kw = 238.0  # 297 kWp x 80% PR

        generation = peak_kw * math.exp(-0.5 * ((hour - peak_hour) / spread) ** 2)
        noise = random.uniform(0.92, 1.08)  # cloud cover variation
        return max(0, generation * noise)

    # === Peak demand tracking ===

    def get_current_demand(self, site_id: str) -> DemandStatus:
        """Get current building demand snapshot with NMD headroom."""
        now = datetime.now(timezone.utc)
        sast = now + timedelta(hours=2)
        hour = sast.hour + sast.minute / 60.0

        building_kw = self._simulated_site_load(hour)
        solar_kw = self._simulated_solar_generation(hour)
        net_demand = max(0, building_kw - solar_kw)

        # Monthly peak from history
        intervals = self._demand_history.get(site_id, [])
        monthly_peak = max((i.net_demand_kw for i in intervals), default=net_demand)

        headroom = self.NMD_LIMIT_KVA - net_demand
        headroom_pct = (headroom / self.NMD_LIMIT_KVA) * 100

        # Determine alert level
        utilisation = (net_demand / self.NMD_LIMIT_KVA) * 100
        if utilisation >= self.NMD_CRITICAL_PCT:
            alert_level = "critical"
        elif utilisation >= self.NMD_WARNING_PCT:
            alert_level = "warning"
        else:
            alert_level = "normal"

        # Demand trend (check last few intervals)
        trend = "stable"
        if len(intervals) >= 3:
            recent = [i.net_demand_kw for i in intervals[-3:]]
            if recent[-1] > recent[0] + 50:
                trend = "rising"
            elif recent[-1] < recent[0] - 50:
                trend = "falling"

        # BESS peak shaving active?
        nmd_target = self.NMD_LIMIT_KVA * (self.NMD_WARNING_PCT / 100)
        bess_shaving = net_demand > nmd_target
        bess_kw = min(self.BESS_RATED_POWER_KW, net_demand - nmd_target) if bess_shaving else 0.0

        return DemandStatus(
            site_id=site_id,
            timestamp=now.isoformat(),
            current_demand_kw=net_demand,
            monthly_peak_kw=monthly_peak,
            nmd_limit_kva=self.NMD_LIMIT_KVA,
            headroom_kw=headroom,
            headroom_pct=headroom_pct,
            demand_trend=trend,
            alert_level=alert_level,
            bess_shaving_active=bess_shaving,
            bess_shaving_kw=bess_kw,
        )

    def get_demand_profile(self, site_id: str, period: str = "day") -> DemandProfile:
        """Get 15-minute interval demand profile with shaving overlay."""
        intervals = self._demand_history.get(site_id, [])

        if not intervals:
            return DemandProfile(site_id=site_id, period=period)

        # For day: use today's intervals
        # For week: would aggregate, but for demo just use what we have
        peak_demand = max(i.demand_kw for i in intervals)
        peak_net = max(i.net_demand_kw for i in intervals)
        peak_time = ""
        for i in intervals:
            if i.demand_kw == peak_demand:
                peak_time = i.timestamp
                break

        avg_demand = sum(i.demand_kw for i in intervals) / len(intervals)

        return DemandProfile(
            site_id=site_id,
            period=period,
            intervals=intervals,
            peak_demand_kw=peak_demand,
            peak_demand_time=peak_time,
            avg_demand_kw=avg_demand,
            peak_with_shaving_kw=peak_net,
        )

    def get_monthly_peak_history(self, site_id: str, months: int = 12) -> List[MonthlyPeak]:
        """Get historical monthly peaks for NMD ratchet tracking."""
        peaks = self._monthly_peaks.get(site_id, [])
        return peaks[-months:]

    # === NMD management ===

    def check_nmd_status(self, site_id: str) -> NMDStatus:
        """Check current demand vs NMD limit with ratchet alert."""
        demand = self.get_current_demand(site_id)
        history = self.get_monthly_peak_history(site_id)

        utilisation = (demand.monthly_peak_kw / self.NMD_LIMIT_KVA) * 100

        if utilisation >= self.NMD_CRITICAL_PCT:
            alert_level = "critical"
            alert_msg = (
                f"CRITICAL: Monthly peak {demand.monthly_peak_kw:.0f} kW is "
                f"{utilisation:.1f}% of NMD ({self.NMD_LIMIT_KVA:.0f} kVA). "
                f"NMD ratchet imminent! Immediate BESS discharge recommended."
            )
        elif utilisation >= self.NMD_WARNING_PCT:
            alert_level = "warning"
            alert_msg = (
                f"WARNING: Monthly peak {demand.monthly_peak_kw:.0f} kW is "
                f"{utilisation:.1f}% of NMD ({self.NMD_LIMIT_KVA:.0f} kVA). "
                f"Monitor demand closely, BESS peak shaving active."
            )
        else:
            alert_level = "normal"
            alert_msg = (
                f"Normal: Monthly peak {demand.monthly_peak_kw:.0f} kW is {utilisation:.1f}% of NMD. Adequate headroom."
            )

        ratchet_risk = utilisation >= self.NMD_WARNING_PCT

        # Estimate annual penalty from history
        annual_penalty = sum(m.penalty_zar for m in history)

        return NMDStatus(
            site_id=site_id,
            nmd_limit_kva=self.NMD_LIMIT_KVA,
            current_demand_kw=demand.current_demand_kw,
            monthly_peak_kw=demand.monthly_peak_kw,
            utilisation_pct=utilisation,
            alert_level=alert_level,
            alert_message=alert_msg,
            ratchet_risk=ratchet_risk,
            months_history=history,
            estimated_annual_penalty_zar=annual_penalty,
        )

    def predict_peak_risk(self, site_id: str) -> PeakRiskAssessment:
        """Predict if today's peak will exceed NMD threshold."""
        now = datetime.now(timezone.utc)
        sast = now + timedelta(hours=2)
        hour = sast.hour + sast.minute / 60.0

        # Predicted peak based on time of day and historical patterns
        # Morning peak typically at 09:00-09:30, afternoon at 14:00-15:00
        if hour < 8:
            # Before peak: predict based on ramp rate
            predicted_peak = 1800 + random.uniform(-50, 100)
            predicted_time = sast.replace(hour=9, minute=30).isoformat()
        elif hour < 12:
            # Between peaks: morning peak likely happened
            predicted_peak = max(
                self._simulated_site_load(9.5),
                self._simulated_site_load(14.5),
            )
            predicted_time = sast.replace(hour=14, minute=30).isoformat()
        elif hour < 16:
            # Afternoon: peak imminent or happening
            predicted_peak = self._simulated_site_load(hour)
            predicted_time = sast.isoformat()
        else:
            # After peak hours: use actual observed max
            predicted_peak = 1700 + random.uniform(-100, 0)
            predicted_time = sast.replace(hour=14, minute=30).isoformat()

        # Account for solar offset
        solar_at_peak = self._simulated_solar_generation(14.5)
        net_predicted = predicted_peak - solar_at_peak

        risk_pct = (net_predicted / self.NMD_LIMIT_KVA) * 100

        if risk_pct >= 95:
            risk_level = "critical"
        elif risk_pct >= 85:
            risk_level = "high"
        elif risk_pct >= 70:
            risk_level = "medium"
        else:
            risk_level = "low"

        factors = []
        if sast.weekday() < 5:
            factors.append("Weekday (higher office occupancy)")
        if sast.month in (6, 7, 8):
            factors.append("Winter month (higher HVAC heating demand)")
        if sast.month in (12, 1, 2):
            factors.append("Summer month (higher cooling demand)")
        if 8 <= hour <= 10:
            factors.append("Morning ramp-up period (08:00-10:00)")
        if 14 <= hour <= 15:
            factors.append("Afternoon peak period (14:00-15:00)")

        recommendation = ""
        if risk_level in ("high", "critical"):
            recommendation = (
                f"Pre-emptive BESS discharge recommended. "
                f"Set demand cap at {self.NMD_LIMIT_KVA * 0.85:.0f} kW to protect NMD headroom."
            )
        elif risk_level == "medium":
            recommendation = "Monitor demand. BESS on standby for peak shaving if needed."
        else:
            recommendation = "No action required. Demand within normal range."

        return PeakRiskAssessment(
            site_id=site_id,
            timestamp=now.isoformat(),
            predicted_peak_kw=net_predicted,
            predicted_peak_time=predicted_time,
            nmd_limit_kva=self.NMD_LIMIT_KVA,
            risk_level=risk_level,
            risk_pct=risk_pct,
            contributing_factors=factors,
            recommendation=recommendation,
        )

    # === Peak shaving ===

    def calculate_shaving_potential(self, site_id: str) -> ShavingPotential:
        """Calculate how much BESS can reduce peak demand."""
        # Get current BESS state from dispatch service
        try:
            from app.services.solar_dispatch_service import get_solar_dispatch_service

            dispatch = get_solar_dispatch_service()
            status = dispatch.get_dispatch_status(site_id)
            bess_soc = status.bess_soc_pct if status else 50.0
        except Exception:
            bess_soc = 50.0

        # Available energy above minimum SOC
        usable_soc = max(0, bess_soc - self.BESS_MIN_SOC_PCT)
        available_kwh = self.BESS_CAPACITY_KWH * (usable_soc / 100.0)

        # Duration at max power
        duration_hours = available_kwh / self.BESS_RATED_POWER_KW if self.BESS_RATED_POWER_KW > 0 else 0

        # For peak shaving we care about the 30-min billing window
        # BESS can sustain rated power for the billing interval easily
        max_shaving = min(self.BESS_RATED_POWER_KW, available_kwh / 0.5)  # 30-min window

        # Current unmanaged peak from profile
        intervals = self._demand_history.get(site_id, [])
        unmanaged_peak = max((i.demand_kw - i.solar_offset_kw for i in intervals), default=self.PEAK_DEMAND_KW)
        achievable_peak = max(0, unmanaged_peak - max_shaving)

        # Monthly demand charge savings
        peak_reduction = unmanaged_peak - achievable_peak
        savings_month = peak_reduction * self.DEMAND_CHARGE_PER_KVA

        return ShavingPotential(
            site_id=site_id,
            current_peak_kw=unmanaged_peak,
            bess_available_kw=self.BESS_RATED_POWER_KW,
            bess_soc_pct=bess_soc,
            bess_duration_hours=duration_hours,
            max_shaving_kw=max_shaving,
            achievable_peak_kw=achievable_peak,
            demand_savings_zar_month=savings_month,
        )

    def get_shaving_recommendation(self, site_id: str) -> ShavingRecommendation:
        """Get real-time peak shaving recommendation."""
        now = datetime.now(timezone.utc)
        demand = self.get_current_demand(site_id)

        # NMD target with buffer
        nmd_target = self.NMD_LIMIT_KVA * (self.NMD_WARNING_PCT / 100)

        should_shave = demand.current_demand_kw > nmd_target
        discharge_kw = 0.0
        priority = "low"
        reason = "Demand within normal range. No shaving needed."

        if demand.current_demand_kw > self.NMD_LIMIT_KVA * 0.95:
            # Critical: NMD breach imminent
            discharge_kw = min(
                self.BESS_RATED_POWER_KW,
                demand.current_demand_kw - nmd_target,
            )
            should_shave = True
            priority = "critical"
            reason = (
                f"CRITICAL: Demand {demand.current_demand_kw:.0f} kW is >"
                f"95% of NMD ({self.NMD_LIMIT_KVA:.0f} kVA). "
                f"Immediate BESS discharge of {discharge_kw:.0f} kW required."
            )
        elif demand.current_demand_kw > nmd_target:
            # Warning: approaching NMD
            discharge_kw = min(
                self.BESS_RATED_POWER_KW,
                demand.current_demand_kw - nmd_target,
            )
            should_shave = True
            priority = "high"
            reason = (
                f"Demand {demand.current_demand_kw:.0f} kW exceeds {self.NMD_WARNING_PCT:.0f}% "
                f"NMD threshold ({nmd_target:.0f} kW). "
                f"BESS discharging {discharge_kw:.0f} kW to cap demand."
            )
        elif demand.demand_trend == "rising" and demand.current_demand_kw > nmd_target * 0.9:
            priority = "medium"
            reason = (
                f"Demand rising at {demand.current_demand_kw:.0f} kW. "
                f"Approaching NMD warning threshold ({nmd_target:.0f} kW). "
                f"BESS on standby."
            )

        estimated_savings = discharge_kw * self.DEMAND_CHARGE_PER_KVA / 30  # daily savings estimate

        return ShavingRecommendation(
            site_id=site_id,
            timestamp=now.isoformat(),
            should_shave=should_shave,
            target_demand_kw=nmd_target,
            discharge_kw=discharge_kw,
            reason=reason,
            priority=priority,
            estimated_savings_zar=estimated_savings,
        )

    # === Load deferral ===

    def get_deferral_suggestions(self, site_id: str) -> List[DeferralSuggestion]:
        """Identify non-critical loads that could shift to off-peak.

        Based on typical commercial building equipment at Site-002 campus.
        """
        # Standard deferral candidates for a large office complex
        suggestions = [
            DeferralSuggestion(
                equipment_code="S002-PUMP-CHW-1",
                equipment_name="CHW Secondary Pump Set",
                load_kw=75.0,
                current_schedule="06:00-18:00 (continuous)",
                suggested_schedule="Pre-cool 05:00-07:00, reduce 12:00-14:00 when solar peaks",
                savings_zar_month=round(75 * 2 * 22 * 0.02 * self.DEMAND_CHARGE_PER_KVA, 2),  # 2 hrs shifted
                criticality="medium",
                reason="Thermal mass allows 2-hour pre-cooling. Reduce pump speed during solar peak to lower demand.",
            ),
            DeferralSuggestion(
                equipment_code="S002-AHU-2",
                equipment_name="AHU-2 (Non-critical Zones)",
                load_kw=45.0,
                current_schedule="06:00-18:00 (continuous)",
                suggested_schedule="Staggered start: 06:30-18:00 (30-min delay reduces morning ramp)",
                savings_zar_month=round(45 * 0.5 * 22 * 0.015 * self.DEMAND_CHARGE_PER_KVA, 2),
                criticality="low",
                reason="Staggering AHU start times reduces coincident demand during morning ramp-up.",
            ),
            DeferralSuggestion(
                equipment_code="S002-UPS-1",
                equipment_name="UPS Battery Recharge",
                load_kw=120.0,
                current_schedule="On-demand (any time)",
                suggested_schedule="Defer to off-peak 22:00-06:00 unless post-load-shedding",
                savings_zar_month=round(120 * 4 * 10 * 0.01 * self.DEMAND_CHARGE_PER_KVA, 2),
                criticality="medium",
                reason="UPS battery charging is deferrable. Schedule post-LS recharge for off-peak hours.",
            ),
            DeferralSuggestion(
                equipment_code="S002-CT-1",
                equipment_name="Cooling Tower Fan VSD",
                load_kw=55.0,
                current_schedule="07:00-18:00 (follows chiller)",
                suggested_schedule="Reduce to 70% speed 14:00-15:00 during afternoon demand peak",
                savings_zar_month=round(55 * 0.3 * 22 * self.DEMAND_CHARGE_PER_KVA / 60, 2),
                criticality="low",
                reason="Brief CT fan speed reduction during demand peak. Condenser approach rises <2C, minimal impact.",
            ),
            DeferralSuggestion(
                equipment_code="S002-GEN-1",
                equipment_name="Generator Block Heater",
                load_kw=15.0,
                current_schedule="Continuous",
                suggested_schedule="Timer: 04:00-06:00 only (pre-heat before business hours)",
                savings_zar_month=round(15 * 20 * 22 * 0.005 * self.DEMAND_CHARGE_PER_KVA, 2),
                criticality="low",
                reason="Block heaters only needed pre-start. Timer control eliminates 20h/day unnecessary load.",
            ),
        ]

        return suggestions

    # === Demand charge savings ===

    def calculate_demand_savings(self, site_id: str, period: str = "month") -> DemandSavings:
        """Calculate demand charge savings from BESS peak shaving.

        Formula: savings = (unmanaged_peak - managed_peak) x demand_charge_per_kVA
        City Power 2025/26: R395.48/kVA/month
        """
        intervals = self._demand_history.get(site_id, [])

        if not intervals:
            # Use reference values
            unmanaged_peak = self.PEAK_DEMAND_KW
            managed_peak = unmanaged_peak - 200  # ~200 kW BESS shaving
        else:
            # Unmanaged = building demand minus solar only
            unmanaged_peak = max(
                (i.demand_kw - i.solar_offset_kw for i in intervals),
                default=self.PEAK_DEMAND_KW,
            )
            # Managed = with BESS shaving
            managed_peak = max(
                (i.net_demand_kw for i in intervals),
                default=unmanaged_peak - 200,
            )

        peak_reduction = max(0, unmanaged_peak - managed_peak)
        unmanaged_cost = unmanaged_peak * self.DEMAND_CHARGE_PER_KVA
        managed_cost = managed_peak * self.DEMAND_CHARGE_PER_KVA
        savings = peak_reduction * self.DEMAND_CHARGE_PER_KVA
        savings_pct = (savings / unmanaged_cost * 100) if unmanaged_cost > 0 else 0

        return DemandSavings(
            site_id=site_id,
            period=period,
            unmanaged_peak_kw=unmanaged_peak,
            managed_peak_kw=managed_peak,
            peak_reduction_kw=peak_reduction,
            demand_charge_per_kva=self.DEMAND_CHARGE_PER_KVA,
            unmanaged_cost_zar=unmanaged_cost,
            managed_cost_zar=managed_cost,
            savings_zar=savings,
            savings_pct=savings_pct,
        )


# === Singleton ===

_solar_demand_service: Optional[SolarDemandService] = None


def get_solar_demand_service() -> SolarDemandService:
    """Get the singleton solar demand service instance."""
    global _solar_demand_service
    if _solar_demand_service is None:
        _solar_demand_service = SolarDemandService()
    return _solar_demand_service
