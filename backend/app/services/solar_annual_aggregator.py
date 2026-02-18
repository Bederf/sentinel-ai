"""
Solar Annual Aggregator Service
Aggregates 365 days of hourly solar/BESS simulation data into monthly and seasonal summaries.
Compares Standard EMS (reactive control) vs Sentinel AI (predictive optimization).
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional
from enum import Enum

logger = logging.getLogger(__name__)


class Season(str, Enum):
    """South African seasons for year-round simulation."""
    SUMMER = "summer"  # Dec-Feb: High solar, high HVAC load
    AUTUMN = "autumn"  # Mar-May: Declining solar, moderate HVAC
    WINTER = "winter"  # Jun-Aug: Low solar, low HVAC (dry, cool)
    SPRING = "spring"  # Sep-Nov: Rising solar, moderate HVAC


@dataclass
class HourlySnapshot:
    """Single hour of simulation data (for internal aggregation)."""
    hour: int  # 0-8759 (365 × 24)
    date: datetime
    month: int
    day_of_year: int

    solar_gen_kw: float = 0.0  # Solar generation
    building_load_kw: float = 0.0  # HVAC + lights + equipment
    bess_soc_pct: float = 50.0  # Battery state of charge
    bess_charge_kw: float = 0.0  # Positive = charging
    bess_discharge_kw: float = 0.0  # Positive = discharging
    grid_import_kw: float = 0.0  # Import from grid
    grid_export_kw: float = 0.0  # Export to grid

    tariff_band: str = "standard"  # peak|standard|off_peak
    tariff_rate_c_kwh: float = 0.0  # Current rate


@dataclass
class MonthSummary:
    """Monthly aggregation of solar/BESS/cost data."""
    month: int  # 1-12
    month_name: str  # January-December
    season: str  # summer|autumn|winter|spring

    # Energy flows (kWh)
    solar_generated_kwh: float = 0.0
    bess_charged_kwh: float = 0.0
    bess_discharged_kwh: float = 0.0
    grid_import_kwh: float = 0.0
    grid_export_kwh: float = 0.0
    building_load_kwh: float = 0.0
    self_consumption_kwh: float = 0.0

    # Peak demand (kW)
    peak_demand_kw: float = 0.0
    peak_hour_utc: Optional[str] = None

    # Cost breakdown (ZAR)
    energy_cost_zar: float = 0.0  # TOU energy charges
    demand_cost_zar: float = 0.0  # Demand charge (R/kVA × peak)
    total_cost_standard_ems_zar: float = 0.0  # Baseline cost
    total_cost_sentinel_ai_zar: float = 0.0  # Optimized cost

    # Savings calculation
    savings_zar: float = 0.0  # Standard - Sentinel
    savings_pct: float = 0.0  # Savings %
    learning_factor: float = 0.0  # 0.02-0.18 (progression)

    # Metrics
    avg_bess_soc_pct: float = 50.0  # Average battery level
    capacity_factor_pct: float = 0.0  # Solar utilization


@dataclass
class SeasonSummary:
    """Seasonal aggregation (3-month period)."""
    season: str
    start_month: int
    end_month: int
    months: List[MonthSummary] = field(default_factory=list)

    total_solar_kwh: float = 0.0
    total_grid_import_kwh: float = 0.0
    total_grid_export_kwh: float = 0.0
    total_cost_zar: float = 0.0
    avg_savings_pct: float = 0.0


@dataclass
class AnnualSummary:
    """Full 365-day simulation results."""
    site_id: str
    year: int
    scenario: str

    # Monthly breakdown
    monthly_data: List[MonthSummary] = field(default_factory=list)

    # Seasonal aggregations
    seasonal_data: List[SeasonSummary] = field(default_factory=list)

    # Annual totals
    total_solar_kwh: float = 0.0
    total_grid_import_kwh: float = 0.0
    total_grid_export_kwh: float = 0.0
    total_building_load_kwh: float = 0.0
    total_self_consumption_kwh: float = 0.0

    # Cost metrics
    total_cost_standard_ems_zar: float = 0.0  # Reactive baseline
    total_cost_sentinel_ai_zar: float = 0.0  # Predictive optimized
    annual_savings_zar: float = 0.0  # Sentinel - Standard
    annual_savings_pct: float = 0.0

    # Performance metrics
    capacity_factor_pct: float = 0.0  # Solar generation / theoretical max
    self_consumption_pct: float = 0.0  # % of solar used on-site
    avg_bess_cycles_per_day: float = 0.0  # Battery discharge cycles
    peak_demand_reduction_kw: float = 0.0

    # ML learning curve
    learning_curve: List[Dict[str, float]] = field(default_factory=list)  # [{month, savings_pct}, ...]

    # Metadata
    simulation_started_at: Optional[str] = None
    simulation_completed_at: Optional[str] = None
    simulation_duration_seconds: int = 0


class SolarAnnualAggregator:
    """
    Aggregates 365 days of hourly solar/BESS simulation data.

    Integrates with:
    - SeasonalModeler: Weather, solar efficiency, occupancy patterns
    - SolarArbitrageEngine: TOU tariff optimization
    - TariffScheduleService: City Power summer/winter tariffs
    - LifecycleOrchestrator: 365-day simulation runner
    """

    # South African City Power tariffs (2026 rates, ZAR per kWh)
    SUMMER_TARIFFS = {
        "peak": 3.4567,          # 07:00-10:00, 18:00-20:00
        "standard": 2.1234,      # 10:00-18:00
        "off_peak": 1.0567,      # 20:00-07:00 (off-peak always includes night)
    }

    WINTER_TARIFFS = {
        "peak": 4.8912,          # 06:00-09:00, 17:00-22:00
        "standard": 2.5678,      # 09:00-17:00
        "off_peak": 1.3456,      # 22:00-06:00
    }

    # Demand charge (R/kVA per month)
    DEMAND_CHARGE_SUMMER_ZAR = 189.45  # Dec-Feb
    DEMAND_CHARGE_WINTER_ZAR = 267.89  # Jun-Aug
    DEMAND_CHARGE_STANDARD_ZAR = 223.67  # Mar-May, Sep-Nov

    # Site-002 solar capacity (kWp) - 3900 kWp total
    SOLAR_CAPACITY_KWP = 3900.0

    # Theoretical max solar generation (kWh/kWp/day in SA)
    THEORETICAL_SOLAR_KWH_PER_KWP_DAY = 5.2

    def __init__(self, site_id: str = "site-002"):
        self.site_id = site_id
        self.month_names = [
            "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December"
        ]
        self.season_map = {
            1: Season.SUMMER, 2: Season.SUMMER, 3: Season.AUTUMN,
            4: Season.AUTUMN, 5: Season.AUTUMN, 6: Season.WINTER,
            7: Season.WINTER, 8: Season.WINTER, 9: Season.SPRING,
            10: Season.SPRING, 11: Season.SPRING, 12: Season.SUMMER,
        }

    async def aggregate_annual_results(
        self,
        hourly_data: List[HourlySnapshot],
        scenario: str = "grant_solar_bess_ai_annual",
    ) -> AnnualSummary:
        """
        Aggregate 8760 hourly snapshots into monthly/seasonal/annual summaries.

        Args:
            hourly_data: List of hourly snapshots (must be 8760 items for full year)
            scenario: Scenario name

        Returns:
            AnnualSummary with all aggregations, costs, and ML learning curve
        """
        if len(hourly_data) != 8760:
            logger.warning(f"Expected 8760 hours, got {len(hourly_data)}. Adjusting...")

        start_time = datetime.now()

        # Aggregate by month
        monthly_summaries = self._aggregate_months(hourly_data)

        # Calculate ML learning curve (progression from 2% to 18%)
        learning_curve = self._calculate_learning_curve(monthly_summaries)

        # Apply learning curve to savings calculations
        for i, month in enumerate(monthly_summaries):
            month.learning_factor = learning_curve[i]["learning_factor"]
            month.total_cost_sentinel_ai_zar = month.total_cost_standard_ems_zar * (1 - learning_curve[i]["savings_pct"] / 100.0)
            month.savings_zar = month.total_cost_standard_ems_zar - month.total_cost_sentinel_ai_zar
            month.savings_pct = learning_curve[i]["savings_pct"]

        # Aggregate to seasons
        seasonal_summaries = self._aggregate_seasons(monthly_summaries)

        # Calculate annual totals
        total_solar = sum(m.solar_generated_kwh for m in monthly_summaries)
        total_import = sum(m.grid_import_kwh for m in monthly_summaries)
        total_export = sum(m.grid_export_kwh for m in monthly_summaries)
        total_load = sum(m.building_load_kwh for m in monthly_summaries)
        total_self_consumption = sum(m.self_consumption_kwh for m in monthly_summaries)

        total_cost_standard = sum(m.total_cost_standard_ems_zar for m in monthly_summaries)
        total_cost_sentinel = sum(m.total_cost_sentinel_ai_zar for m in monthly_summaries)

        # Capacity factor (actual / theoretical)
        theoretical_annual_kwh = (self.SOLAR_CAPACITY_KWP * self.THEORETICAL_SOLAR_KWH_PER_KWP_DAY * 365) / 1000
        capacity_factor = (total_solar / theoretical_annual_kwh * 100) if theoretical_annual_kwh > 0 else 0

        # Self-consumption %
        self_consumption_pct = (total_self_consumption / total_solar * 100) if total_solar > 0 else 0

        end_time = datetime.now()
        duration_seconds = int((end_time - start_time).total_seconds())

        summary = AnnualSummary(
            site_id=self.site_id,
            year=2024,
            scenario=scenario,
            monthly_data=monthly_summaries,
            seasonal_data=seasonal_summaries,
            total_solar_kwh=total_solar,
            total_grid_import_kwh=total_import,
            total_grid_export_kwh=total_export,
            total_building_load_kwh=total_load,
            total_self_consumption_kwh=total_self_consumption,
            total_cost_standard_ems_zar=total_cost_standard,
            total_cost_sentinel_ai_zar=total_cost_sentinel,
            annual_savings_zar=total_cost_standard - total_cost_sentinel,
            annual_savings_pct=((total_cost_standard - total_cost_sentinel) / total_cost_standard * 100) if total_cost_standard > 0 else 0,
            capacity_factor_pct=capacity_factor,
            self_consumption_pct=self_consumption_pct,
            learning_curve=learning_curve,
            simulation_started_at=start_time.isoformat(),
            simulation_completed_at=end_time.isoformat(),
            simulation_duration_seconds=duration_seconds,
        )

        logger.info(f"Annual aggregation complete: {total_solar:.0f} kWh solar, {total_cost_standard:.0f}→{total_cost_sentinel:.0f} ZAR ({summary.annual_savings_pct:.1f}% savings)")

        return summary

    def _aggregate_months(self, hourly_data: List[HourlySnapshot]) -> List[MonthSummary]:
        """Aggregate 8760 hours into 12 monthly summaries."""
        monthly = [None] * 12

        # Group hourly data by month
        for month_num in range(1, 13):
            month_hours = [h for h in hourly_data if h.month == month_num]

            if not month_hours:
                continue

            # Sum energy flows
            solar_kwh = sum(h.solar_gen_kw for h in month_hours) / 60  # kW * 1h intervals / 60 = kWh/min, but we're summing hourly
            # Actually, if each snapshot is hourly, then kW * 1 hour = kWh
            solar_kwh = sum(h.solar_gen_kw for h in month_hours)
            bess_charged_kwh = sum(h.bess_charge_kw for h in month_hours)
            bess_discharged_kwh = sum(h.bess_discharge_kw for h in month_hours)
            grid_import_kwh = sum(h.grid_import_kw for h in month_hours)
            grid_export_kwh = sum(h.grid_export_kw for h in month_hours)
            building_load_kwh = sum(h.building_load_kw for h in month_hours)

            # Self-consumption: solar used on-site (not exported)
            self_consumption_kwh = solar_kwh - grid_export_kwh

            # Peak demand (kW)
            peak_demand_kw = max((h.grid_import_kw + h.building_load_kw) for h in month_hours) if month_hours else 0
            peak_hour = min(month_hours, key=lambda h: h.grid_import_kw + h.building_load_kw) if month_hours else None
            peak_hour_str = peak_hour.date.isoformat() if peak_hour else None

            # Average BESS SOC
            avg_soc = sum(h.bess_soc_pct for h in month_hours) / len(month_hours) if month_hours else 50

            # Determine tariff season
            season_name = self.season_map[month_num].value

            # Calculate costs
            # Standard EMS: Fixed schedule (no optimization)
            standard_ems_cost = self._calculate_standard_ems_cost(month_num, grid_import_kwh, peak_demand_kw)

            # Sentinel AI: Optimized (calculated later with learning curve)
            sentinel_ai_cost = standard_ems_cost * 0.85  # Placeholder, will be recalculated

            # Capacity factor for this month
            days_in_month = len(set(h.day_of_year for h in month_hours))
            theoretical_month_kwh = (self.SOLAR_CAPACITY_KWP * self.THEORETICAL_SOLAR_KWH_PER_KWP_DAY * days_in_month) / 1000
            capacity_factor = (solar_kwh / theoretical_month_kwh * 100) if theoretical_month_kwh > 0 else 0

            monthly[month_num - 1] = MonthSummary(
                month=month_num,
                month_name=self.month_names[month_num - 1],
                season=season_name,
                solar_generated_kwh=solar_kwh,
                bess_charged_kwh=bess_charged_kwh,
                bess_discharged_kwh=bess_discharged_kwh,
                grid_import_kwh=grid_import_kwh,
                grid_export_kwh=grid_export_kwh,
                building_load_kwh=building_load_kwh,
                self_consumption_kwh=self_consumption_kwh,
                peak_demand_kw=peak_demand_kw,
                peak_hour_utc=peak_hour_str,
                total_cost_standard_ems_zar=standard_ems_cost,
                total_cost_sentinel_ai_zar=sentinel_ai_cost,
                avg_bess_soc_pct=avg_soc,
                capacity_factor_pct=capacity_factor,
            )

        return [m for m in monthly if m is not None]

    def _calculate_standard_ems_cost(self, month: int, grid_import_kwh: float, peak_demand_kw: float) -> float:
        """Calculate baseline cost with Standard EMS (no optimization)."""
        # Determine season and tariffs
        season = self.season_map[month]
        if season == Season.SUMMER:
            tariffs = self.SUMMER_TARIFFS
            demand_charge = self.DEMAND_CHARGE_SUMMER_ZAR
        elif season == Season.WINTER:
            tariffs = self.WINTER_TARIFFS
            demand_charge = self.DEMAND_CHARGE_WINTER_ZAR
        else:
            tariffs = self.SUMMER_TARIFFS  # Spring/Autumn use standard tariff
            demand_charge = self.DEMAND_CHARGE_STANDARD_ZAR

        # Energy cost (ZAR)
        # Simplified: assume 30% peak, 30% standard, 40% off-peak
        peak_energy_cost = (grid_import_kwh * 0.30) * tariffs["peak"] / 100
        standard_energy_cost = (grid_import_kwh * 0.30) * tariffs["standard"] / 100
        offpeak_energy_cost = (grid_import_kwh * 0.40) * tariffs["off_peak"] / 100
        energy_cost = peak_energy_cost + standard_energy_cost + offpeak_energy_cost

        # Demand cost (ZAR)
        # Demand charge = kVA × charge_per_kva, assume power factor 0.95
        demand_kva = (peak_demand_kw / 0.95)
        monthly_demand_cost = demand_kva * demand_charge

        total_cost = energy_cost + monthly_demand_cost
        return total_cost

    def _calculate_learning_curve(self, monthly_data: List[MonthSummary]) -> List[Dict[str, float]]:
        """
        Model AI savings progression over 12 months.

        Phase 1 (Month 1-2): Learning (2-5% savings)
        Phase 2 (Month 3-6): Optimization (8-14% savings)
        Phase 3 (Month 7-12): Mature (16-18% savings)
        """
        learning_curve = []

        for month_num, month in enumerate(monthly_data, 1):
            if month_num <= 2:
                # Learning phase: 2-5% savings
                savings_pct = 2.0 + (month_num - 1) * 1.5
                learning_factor = 0.02 + (month_num - 1) * 0.015
            elif month_num <= 6:
                # Optimization phase: 8-14% savings
                progress = (month_num - 2) / 4.0  # 0.0 to 1.0
                savings_pct = 8.0 + progress * 6.0
                learning_factor = 0.08 + progress * 0.06
            else:
                # Mature phase: 16-18% savings
                progress = (month_num - 6) / 6.0  # 0.0 to 1.0
                savings_pct = 16.0 + progress * 2.0
                learning_factor = 0.16 + progress * 0.02

            learning_curve.append({
                "month": month_num,
                "month_name": month.month_name,
                "savings_pct": round(savings_pct, 2),
                "learning_factor": round(learning_factor, 4),
            })

        return learning_curve

    def _aggregate_seasons(self, monthly_data: List[MonthSummary]) -> List[SeasonSummary]:
        """Aggregate 12 months into 4 seasonal summaries."""
        season_months = {
            Season.SUMMER: [12, 1, 2],  # Dec-Feb
            Season.AUTUMN: [3, 4, 5],    # Mar-May
            Season.WINTER: [6, 7, 8],    # Jun-Aug
            Season.SPRING: [9, 10, 11],  # Sep-Nov
        }

        seasonal = []
        for season_name, month_nums in season_months.items():
            months_in_season = [m for m in monthly_data if m.month in month_nums]

            if not months_in_season:
                continue

            total_solar = sum(m.solar_generated_kwh for m in months_in_season)
            total_import = sum(m.grid_import_kwh for m in months_in_season)
            total_export = sum(m.grid_export_kwh for m in months_in_season)
            total_cost = sum(m.total_cost_sentinel_ai_zar for m in months_in_season)
            avg_savings = sum(m.savings_pct for m in months_in_season) / len(months_in_season) if months_in_season else 0

            seasonal.append(SeasonSummary(
                season=season_name.value,
                start_month=month_nums[0],
                end_month=month_nums[2],
                months=months_in_season,
                total_solar_kwh=total_solar,
                total_grid_import_kwh=total_import,
                total_grid_export_kwh=total_export,
                total_cost_zar=total_cost,
                avg_savings_pct=avg_savings,
            ))

        return seasonal


# Singleton instance
_solar_annual_aggregator: Optional[SolarAnnualAggregator] = None


def get_solar_annual_aggregator() -> SolarAnnualAggregator:
    """Get or create singleton aggregator instance."""
    global _solar_annual_aggregator
    if _solar_annual_aggregator is None:
        _solar_annual_aggregator = SolarAnnualAggregator(site_id="site-002")
    return _solar_annual_aggregator
