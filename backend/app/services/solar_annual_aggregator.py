"""
Solar Annual Aggregator Service
Aggregates 365 days of hourly solar/BESS simulation data into monthly and seasonal summaries.
Compares Standard EMS (reactive control) vs Sentinel AI (predictive optimization).
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from app.core.site_resolver import get_primary_site_code
from app.processing.solar_table import SolarTableProcessor

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
    site_load_kw: float = 0.0  # HVAC + lights + equipment
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
    site_load_kwh: float = 0.0
    self_consumption_kwh: float = 0.0

    # Peak demand (kW)
    peak_demand_kw: float = 0.0
    peak_hour_utc: str | None = None

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
    months: list[MonthSummary] = field(default_factory=list)

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
    monthly_data: list[MonthSummary] = field(default_factory=list)

    # Seasonal aggregations
    seasonal_data: list[SeasonSummary] = field(default_factory=list)

    # Annual totals
    total_solar_kwh: float = 0.0
    total_grid_import_kwh: float = 0.0
    total_grid_export_kwh: float = 0.0
    total_site_load_kwh: float = 0.0
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
    learning_curve: list[dict[str, float]] = field(default_factory=list)  # [{month, savings_pct}, ...]

    # Metadata
    simulation_started_at: str | None = None
    simulation_completed_at: str | None = None
    simulation_duration_seconds: int = 0


class SolarAnnualAggregator:
    """Aggregates 365 days of hourly solar/BESS simulation data.

    Tabular shaping (monthly groupby, seasonal rollup, learning-curve
    calculation) is delegated to ``SolarTableProcessor`` in
    ``app/processing/solar_table.py``.
    """

    def __init__(self, site_id: str | None = None):
        self.site_id = site_id or get_primary_site_code() or "unknown"

    async def aggregate_annual_results(
        self,
        hourly_data: list[HourlySnapshot],
        scenario: str = "sentinel_annual",
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

        # Tabular shaping delegated to SolarTableProcessor
        monthly_summaries = SolarTableProcessor.aggregate_months(hourly_data)
        learning_curve = SolarTableProcessor.calculate_learning_curve(monthly_summaries)

        for i, month in enumerate(monthly_summaries):
            month.learning_factor = learning_curve[i]["learning_factor"]
            month.total_cost_sentinel_ai_zar = month.total_cost_standard_ems_zar * (
                1 - learning_curve[i]["savings_pct"] / 100.0
            )
            month.savings_zar = month.total_cost_standard_ems_zar - month.total_cost_sentinel_ai_zar
            month.savings_pct = learning_curve[i]["savings_pct"]

        seasonal_summaries = SolarTableProcessor.aggregate_seasons(monthly_summaries)

        total_solar = sum(m.solar_generated_kwh for m in monthly_summaries)
        total_import = sum(m.grid_import_kwh for m in monthly_summaries)
        total_export = sum(m.grid_export_kwh for m in monthly_summaries)
        total_load = sum(m.site_load_kwh for m in monthly_summaries)
        total_self_consumption = sum(m.self_consumption_kwh for m in monthly_summaries)

        total_cost_standard = sum(m.total_cost_standard_ems_zar for m in monthly_summaries)
        total_cost_sentinel = sum(m.total_cost_sentinel_ai_zar for m in monthly_summaries)

        # Capacity factor (actual / theoretical)
        from app.processing.solar_table import SOLAR_CAPACITY_KWP, THEORETICAL_SOLAR_KWH_PER_KWP_DAY

        theoretical_annual_kwh = (SOLAR_CAPACITY_KWP * THEORETICAL_SOLAR_KWH_PER_KWP_DAY * 365) / 1000
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
            total_site_load_kwh=total_load,
            total_self_consumption_kwh=total_self_consumption,
            total_cost_standard_ems_zar=total_cost_standard,
            total_cost_sentinel_ai_zar=total_cost_sentinel,
            annual_savings_zar=total_cost_standard - total_cost_sentinel,
            annual_savings_pct=((total_cost_standard - total_cost_sentinel) / total_cost_standard * 100)
            if total_cost_standard > 0
            else 0,
            capacity_factor_pct=capacity_factor,
            self_consumption_pct=self_consumption_pct,
            learning_curve=learning_curve,
            simulation_started_at=start_time.isoformat(),
            simulation_completed_at=end_time.isoformat(),
            simulation_duration_seconds=duration_seconds,
        )

        logger.info(
            f"Annual aggregation complete: {total_solar:.0f} kWh solar, "
            f"{total_cost_standard:.0f}→{total_cost_sentinel:.0f} ZAR "
            f"({summary.annual_savings_pct:.1f}% savings)"
        )

        return summary

    # _aggregate_months, _calculate_learning_curve, _aggregate_seasons, and
    # _calculate_standard_ems_cost have moved to
    # app/processing/solar_table.py (SolarTableProcessor).


# Singleton instance
_solar_annual_aggregator: SolarAnnualAggregator | None = None


def get_solar_annual_aggregator() -> SolarAnnualAggregator:
    """Get or create singleton aggregator instance."""
    global _solar_annual_aggregator
    if _solar_annual_aggregator is None:
        _solar_annual_aggregator = SolarAnnualAggregator()
    return _solar_annual_aggregator
