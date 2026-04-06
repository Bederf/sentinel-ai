"""Solar/BESS annual simulation tabular processing.

Owns monthly groupby, seasonal rollup, learning-curve calculation, and
annual-total aggregation for hourly solar simulation data.

Polars adoption path
--------------------
``aggregate_months()`` groups 8 760 HourlySnapshot rows by month and computes
energy sums, peak demand, and capacity factor.  Replace with a Polars
``group_by("month").agg(...)`` — the input can be converted to a DataFrame
with ``pl.DataFrame([s.__dict__ for s in hourly_data])``.
``aggregate_seasons()`` is a second group-by pass over the 12 MonthSummary
rows — trivially expressible as a Polars ``group_by("season").agg(...)``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    # Avoid circular imports at runtime; only used for type hints.
    from app.services.solar_annual_aggregator import HourlySnapshot, MonthSummary, SeasonSummary

# South African City Power tariffs (2026 rates, ZAR per kWh)
_SUMMER_TARIFFS: dict[str, float] = {
    "peak": 3.4567,
    "standard": 2.1234,
    "off_peak": 1.0567,
}
_WINTER_TARIFFS: dict[str, float] = {
    "peak": 4.8912,
    "standard": 2.5678,
    "off_peak": 1.3456,
}

# Demand charges (ZAR / kVA / month)
_DEMAND_CHARGE_SUMMER_ZAR = 189.45
_DEMAND_CHARGE_WINTER_ZAR = 267.89
_DEMAND_CHARGE_STANDARD_ZAR = 223.67

# Solar capacity / theoretical yield
SOLAR_CAPACITY_KWP = 3900.0
THEORETICAL_SOLAR_KWH_PER_KWP_DAY = 5.2

_MONTH_NAMES = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
]

# Month → SA season name (SA seasons)
_SEASON_MAP: dict[int, str] = {
    1: "summer",
    2: "summer",
    3: "autumn",
    4: "autumn",
    5: "autumn",
    6: "winter",
    7: "winter",
    8: "winter",
    9: "spring",
    10: "spring",
    11: "spring",
    12: "summer",
}

_SEASON_MONTHS: dict[str, list[int]] = {
    "summer": [12, 1, 2],
    "autumn": [3, 4, 5],
    "winter": [6, 7, 8],
    "spring": [9, 10, 11],
}


class SolarTableProcessor:
    """Pure tabular shaping for solar/BESS simulation data.

    All methods are static and side-effect free.  No database access.
    """

    # ------------------------------------------------------------------
    # Monthly aggregation (hourly → monthly)
    # ------------------------------------------------------------------

    @staticmethod
    def aggregate_months(hourly_data: list[HourlySnapshot]) -> list[MonthSummary]:
        """Group 8 760 hourly snapshots into 12 MonthSummary objects.

        Args:
            hourly_data: List of HourlySnapshot dataclass instances.

        Returns:
            List of MonthSummary objects (only months that have data).
        """
        # Import here to avoid circular dependency at module load time.
        from app.services.solar_annual_aggregator import MonthSummary

        monthly: list[MonthSummary | None] = [None] * 12

        for month_num in range(1, 13):
            month_hours = [h for h in hourly_data if h.month == month_num]
            if not month_hours:
                continue

            solar_kwh = sum(h.solar_gen_kw for h in month_hours)
            bess_charged_kwh = sum(h.bess_charge_kw for h in month_hours)
            bess_discharged_kwh = sum(h.bess_discharge_kw for h in month_hours)
            grid_import_kwh = sum(h.grid_import_kw for h in month_hours)
            grid_export_kwh = sum(h.grid_export_kw for h in month_hours)
            site_load_kwh = sum(h.site_load_kw for h in month_hours)
            self_consumption_kwh = solar_kwh - grid_export_kwh

            peak_demand_kw = max((h.grid_import_kw + h.site_load_kw) for h in month_hours)
            peak_hour = min(month_hours, key=lambda h: h.grid_import_kw + h.site_load_kw)
            peak_hour_str = peak_hour.date.isoformat() if peak_hour else None

            avg_soc = sum(h.bess_soc_pct for h in month_hours) / len(month_hours)

            season_name = _SEASON_MAP[month_num]
            standard_ems_cost = SolarTableProcessor._calculate_standard_ems_cost(
                month_num, grid_import_kwh, peak_demand_kw
            )
            # Sentinel AI cost is a placeholder — recalculated later by the caller
            # after the learning curve is applied.
            sentinel_ai_cost = standard_ems_cost * 0.85

            days_in_month = len({h.day_of_year for h in month_hours})
            theoretical_month_kwh = (SOLAR_CAPACITY_KWP * THEORETICAL_SOLAR_KWH_PER_KWP_DAY * days_in_month) / 1000
            capacity_factor = (solar_kwh / theoretical_month_kwh * 100) if theoretical_month_kwh > 0 else 0.0

            monthly[month_num - 1] = MonthSummary(
                month=month_num,
                month_name=_MONTH_NAMES[month_num - 1],
                season=season_name,
                solar_generated_kwh=solar_kwh,
                bess_charged_kwh=bess_charged_kwh,
                bess_discharged_kwh=bess_discharged_kwh,
                grid_import_kwh=grid_import_kwh,
                grid_export_kwh=grid_export_kwh,
                site_load_kwh=site_load_kwh,
                self_consumption_kwh=self_consumption_kwh,
                peak_demand_kw=peak_demand_kw,
                peak_hour_utc=peak_hour_str,
                total_cost_standard_ems_zar=standard_ems_cost,
                total_cost_sentinel_ai_zar=sentinel_ai_cost,
                avg_bess_soc_pct=avg_soc,
                capacity_factor_pct=capacity_factor,
            )

        return [m for m in monthly if m is not None]

    # ------------------------------------------------------------------
    # Learning curve (monthly sequence → progression factors)
    # ------------------------------------------------------------------

    @staticmethod
    def calculate_learning_curve(monthly_data: list[MonthSummary]) -> list[dict[str, Any]]:
        """Model AI savings progression over 12 months.

        Phase 1 (months 1-2):  Learning  — 2-5 % savings
        Phase 2 (months 3-6):  Optimisation — 8-14 %
        Phase 3 (months 7-12): Mature — 16-18 %
        """
        learning_curve = []
        for month_num, month in enumerate(monthly_data, 1):
            if month_num <= 2:
                savings_pct = 2.0 + (month_num - 1) * 1.5
                learning_factor = 0.02 + (month_num - 1) * 0.015
            elif month_num <= 6:
                progress = (month_num - 2) / 4.0
                savings_pct = 8.0 + progress * 6.0
                learning_factor = 0.08 + progress * 0.06
            else:
                progress = (month_num - 6) / 6.0
                savings_pct = 16.0 + progress * 2.0
                learning_factor = 0.16 + progress * 0.02

            learning_curve.append(
                {
                    "month": month_num,
                    "month_name": month.month_name,
                    "savings_pct": round(savings_pct, 2),
                    "learning_factor": round(learning_factor, 4),
                }
            )
        return learning_curve

    # ------------------------------------------------------------------
    # Seasonal rollup (monthly → seasonal)
    # ------------------------------------------------------------------

    @staticmethod
    def aggregate_seasons(monthly_data: list[MonthSummary]) -> list[SeasonSummary]:
        """Aggregate 12 monthly summaries into 4 seasonal summaries.

        Args:
            monthly_data: List returned by ``aggregate_months`` (after learning
                          curve has been applied so savings_pct is populated).
        """
        from app.services.solar_annual_aggregator import SeasonSummary

        seasonal = []
        for season_name, month_nums in _SEASON_MONTHS.items():
            months_in_season = [m for m in monthly_data if m.month in month_nums]
            if not months_in_season:
                continue

            total_solar = sum(m.solar_generated_kwh for m in months_in_season)
            total_import = sum(m.grid_import_kwh for m in months_in_season)
            total_export = sum(m.grid_export_kwh for m in months_in_season)
            total_cost = sum(m.total_cost_sentinel_ai_zar for m in months_in_season)
            avg_savings = sum(m.savings_pct for m in months_in_season) / len(months_in_season)

            seasonal.append(
                SeasonSummary(
                    season=season_name,
                    start_month=month_nums[0],
                    end_month=month_nums[2],
                    months=months_in_season,
                    total_solar_kwh=total_solar,
                    total_grid_import_kwh=total_import,
                    total_grid_export_kwh=total_export,
                    total_cost_zar=total_cost,
                    avg_savings_pct=avg_savings,
                )
            )

        return seasonal

    # ------------------------------------------------------------------
    # Cost calculation helper
    # ------------------------------------------------------------------

    @staticmethod
    def _calculate_standard_ems_cost(month: int, grid_import_kwh: float, peak_demand_kw: float) -> float:
        """Baseline cost with Standard EMS (no optimisation).

        Simplified TOU breakdown: 30 % peak, 30 % standard, 40 % off-peak.
        """
        season_name = _SEASON_MAP[month]
        if season_name == "summer":
            tariffs = _SUMMER_TARIFFS
            demand_charge = _DEMAND_CHARGE_SUMMER_ZAR
        elif season_name == "winter":
            tariffs = _WINTER_TARIFFS
            demand_charge = _DEMAND_CHARGE_WINTER_ZAR
        else:
            tariffs = _SUMMER_TARIFFS
            demand_charge = _DEMAND_CHARGE_STANDARD_ZAR

        energy_cost = (
            (grid_import_kwh * 0.30) * tariffs["peak"] / 100
            + (grid_import_kwh * 0.30) * tariffs["standard"] / 100
            + (grid_import_kwh * 0.40) * tariffs["off_peak"] / 100
        )
        demand_kva = peak_demand_kw / 0.95
        return energy_cost + demand_kva * demand_charge
