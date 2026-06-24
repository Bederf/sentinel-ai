"""IPMVP Measurement & Verification Engine.

Implements IPMVP Option C (Whole Facility) and Option A (Retrofit Isolation)
baseline methodologies for automated M&V reporting.

IPMVP Reference: 2022 Edition, Volume III, Chapter 5 — Measurement & Verification

Usage:
    engine = IPMVPEngine(site_id="site-002")
    result = engine.calculate_savings(
        reporting_start="2026-01-01",
        reporting_end="2026-02-28",
    )
    print(result.baseline_equation)
    print(result.savings_kwh, result.cv_rmse_pct)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Data classes
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class EnergyRecord:
    """Single 15-minute energy reading."""

    timestamp: datetime
    kwh: float
    oat_celsius: float | None = None
    occupied: bool = True
    load_shedding: bool = False
    holiday: bool = False
    import_kwh: float | None = None
    export_kwh: float | None = None
    hvac_kwh: float | None = None
    lighting_kwh: float | None = None
    solar_generation_kwh: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "kwh": self.kwh,
            "oat_celsius": self.oat_celsius,
            "occupied": self.occupied,
            "load_shedding": self.load_shedding,
            "holiday": self.holiday,
            "import_kwh": self.import_kwh,
            "export_kwh": self.export_kwh,
            "hvac_kwh": self.hvac_kwh,
            "lighting_kwh": self.lighting_kwh,
            "solar_generation_kwh": self.solar_generation_kwh,
        }


@dataclass
class EquipmentEvent:
    """A change to equipment setpoints (lighting, HVAC, BESS, solar)."""

    event_id: str
    timestamp: datetime
    system_type: str  # lighting | hvac | chiller | bess | solar | power
    device_id: str
    point_name: str
    old_value: float | None
    new_value: float | None
    recommendation_id: str | None = None

    SYSTEM_MEASUREMENT_WINDOWS = {
        "lighting": 0.5,
        "hvac": 2.0,
        "chiller": 3.0,
        "bess": 0.25,
        "solar": 1.0,
        "power": 1.0,
    }

    @property
    def measurement_window_hours(self) -> float:
        return self.SYSTEM_MEASUREMENT_WINDOWS.get(self.system_type, 2.0)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "timestamp": self.timestamp.isoformat(),
            "system_type": self.system_type,
            "device_id": self.device_id,
            "point_name": self.point_name,
            "old_value": self.old_value,
            "new_value": self.new_value,
            "recommendation_id": self.recommendation_id,
        }


@dataclass
class BaselineModel:
    """OLS baseline regression model for one period (occupied or unoccupied)."""

    period: str  # "occupied" | "unoccupied"
    equation: str  # human-readable, e.g. "kWh = 0.45 × OAT + 120.3"
    coefficients: dict[str, float]
    intercept: float
    r_squared: float
    cv_rmse_pct: float  # CV(RMSE)% — IPMVP uncertainty metric
    n_samples: int
    std_err_residual: float


@dataclass
class SavingsResult:
    """IPMVP savings calculation result."""

    recommendation_id: str | None
    reporting_start: datetime
    reporting_end: datetime
    baseline: BaselineModel
    savings_kwh: float
    savings_zar: float
    cv_rmse_pct: float  # uncertainty of savings estimate
    occupancy_retained_pct: float
    excluded_load_shedding_kwh: float
    n_days_in_period: int
    n_load_shedding_days_excluded: int
    hourly_savings: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def is_acceptable_uncertainty(self) -> bool:
        return self.cv_rmse_pct < 20.0

    @property
    def uncertainty_flag(self) -> str:
        if self.cv_rmse_pct < 20:
            return "acceptable"
        elif self.cv_rmse_pct < 50:
            return "unreliable"
        return "not_determinable"

    def to_dict(self) -> dict[str, Any]:
        return {
            "recommendation_id": self.recommendation_id,
            "reporting_start": self.reporting_start.isoformat(),
            "reporting_end": self.reporting_end.isoformat(),
            "savings_kwh": round(self.savings_kwh, 2),
            "savings_zar": round(self.savings_zar, 2),
            "cv_rmse_pct": round(self.cv_rmse_pct, 1),
            "uncertainty_flag": self.uncertainty_flag,
            "is_acceptable_uncertainty": self.is_acceptable_uncertainty,
            "occupancy_retained_pct": round(self.occupancy_retained_pct, 1),
            "excluded_load_shedding_kwh": round(self.excluded_load_shedding_kwh, 2),
            "n_days_in_period": self.n_days_in_period,
            "n_load_shedding_days_excluded": self.n_load_shedding_days_excluded,
            "baseline_equation": self.baseline.equation,
            "baseline_r_squared": round(self.baseline.r_squared, 3),
            "baseline_cv_rmse_pct": round(self.baseline.cv_rmse_pct, 1),
            "hourly_savings": self.hourly_savings,
            "notes": self.notes,
        }


@dataclass
class IPMVPReport:
    """Complete IPMVP M&V report for a reporting period."""

    site_id: str
    generated_at: datetime
    reporting_start: datetime
    reporting_end: datetime
    option: str  # "C" or "A"
    results: list[SavingsResult]
    overall_savings_kwh: float
    overall_savings_zar: float
    aggregate_cv_rmse_pct: float
    methodology: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "site_id": self.site_id,
            "generated_at": self.generated_at.isoformat(),
            "reporting_start": self.reporting_start.isoformat(),
            "reporting_end": self.reporting_end.isoformat(),
            "option": self.option,
            "methodology": self.methodology,
            "overall_savings_kwh": round(self.overall_savings_kwh, 2),
            "overall_savings_zar": round(self.overall_savings_zar, 2),
            "aggregate_cv_rmse_pct": round(self.aggregate_cv_rmse_pct, 1),
            "individual_results": [r.to_dict() for r in self.results],
            "notes": [
                f"IPMVP {self.option} — Whole Facility M&V"
                if self.option == "C"
                else f"IPMVP {self.option} — Retrofit Isolation",
                "Uncertainty assessed per IPMVP 2022 Volume III Chapter 5",
                "Baseline model excludes load shedding event days",
            ],
        }


# ─────────────────────────────────────────────────────────────────────────────
# Data fetcher — adapt to your actual DB schema
# ─────────────────────────────────────────────────────────────────────────────


class IPMVPDataFetcher:
    """Fetch IPMVP data from site_002 database.

    Override column names to match your actual schema:
        fetch.energy_col = "active_energy_kwh"
        fetch.oat_col    = "outside_air_temp_c"
    """

    def __init__(self, site_id: str):
        self.site_id = site_id

        # ── Column names (override in subclass or set directly) ──────────────
        self.energy_table = f"{site_id}_energy_readings"
        self.energy_ts_col = "timestamp"
        self.energy_kwh_col = "kwh"
        self.oat_col = "outdoor_air_temp_c"
        self.occupied_col = "occupied"
        self.load_shedding_col = "load_shedding"

        self.oat_table = f"{site_id}_oat_readings"
        self.tariff_table = f"{site_id}_tariffs"
        self.events_table = f"{site_id}_equipment_events"

        # Occupied hours (default, override if you have a schedule table)
        self.occupied_start_hour = 8
        self.occupied_end_hour = 18

    # ── Public API ───────────────────────────────────────────────────────────

    async def fetch_energy_and_oat(
        self,
        start: datetime,
        end: datetime,
    ) -> list[EnergyRecord]:
        """Fetch 15-minute energy and OAT records for the given period.

        Returns records sorted by timestamp, with occupied/load_shedding flags.
        Override this method to plug in your actual DB query.
        """
        # TODO: Replace with actual Supabase/postgres query.
        # Example (Supabase service role):
        #
        # from app.services.supabase_client import get_service_client
        # client = get_service_client()
        # rows = client.table(self.energy_table).select(
        #     f"{self.energy_ts_col}, {self.energy_kwh_col}, {self.oat_col}"
        # ).gte(self.energy_ts_col, start.isoformat()).lte(
        #     self.energy_ts_col, end.isoformat()
        # ).execute()
        #
        # Or for direct postgres (site-002 tunnel):
        # from app.services.db_gateway import get_site002_connection
        # conn = get_site002_connection()
        # rows = conn.query(f"""
        #     SELECT {self.energy_ts_col}, {self.energy_kwh_col}, {self.oat_col}
        #     FROM {self.energy_table}
        #     WHERE {self.energy_ts_col} BETWEEN %s AND %s
        #     ORDER BY {self.energy_ts_col}
        # """, (start, end))
        raise NotImplementedError("IPMVPDataFetcher.fetch_energy_and_oat() — plug in your DB query before using")

    async def fetch_equipment_events(
        self,
        start: datetime,
        end: datetime,
        system_types: list[str] | None = None,
    ) -> list[EquipmentEvent]:
        """Fetch equipment change events in the reporting period.

        Override with actual DB query filtering by:
        - timestamp between start/end
        - optional system_type IN (...)
        """
        raise NotImplementedError("IPMVPDataFetcher.fetch_equipment_events() — plug in your DB query before using")

    async def fetch_tariff(self) -> dict[str, Any]:
        """Fetch tariff structure (Eskom MegaFlex or custom).

        Override. Expected return shape:
        {
          "peak_zar_per_kwh": 4.52,
          "standard_zar_per_kwh": 1.87,
          "offpeak_zar_per_kwh": 0.63,
          "peak_hours": [6, 7, 8, 17, 18, 19, 20],
          "weekday_only": True,
        }
        """
        raise NotImplementedError("IPMVPDataFetcher.fetch_tariff() — plug in your tariff query before using")

    async def fetch_load_shedding_days(
        self,
        start: datetime,
        end: datetime,
    ) -> set[datetime.date]:
        """Return set of dates with load shedding events.

        Used to exclude those days from baseline training.
        Override with actual query.
        """
        raise NotImplementedError("IPMVPDataFetcher.fetch_load_shedding_days() — plug in your query before using")

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _is_occupied(self, dt: datetime) -> bool:
        """Determine occupied hours from schedule.

        Override if you have an occupancy sensor or schedule table.
        """
        return dt.weekday() < 5 and self.occupied_start_hour <= dt.hour < self.occupied_end_hour

    def _is_load_shedding_day(self, dt: datetime, ls_days: set[datetime.date]) -> bool:
        return dt.date() in ls_days

    def _tariff_for_hour(self, dt: datetime, tariff: dict[str, Any]) -> float:
        """Return ZAR/kWh for the given hour based on tariff structure."""
        if dt.weekday() >= 5:
            return tariff.get("offpeak_zar_per_kwh", tariff.get("standard_zar_per_kwh", 1.0))

        peak_hours = set(tariff.get("peak_hours", []))
        if dt.hour in peak_hours:
            return tariff.get("peak_zar_per_kwh", 2.5)
        elif 9 <= dt.hour <= 15:
            return tariff.get("standard_zar_per_kwh", 1.5)
        else:
            return tariff.get("offpeak_zar_per_kwh", 0.7)


# ─────────────────────────────────────────────────────────────────────────────
# Baseline regressor — IPMVP Option C
# ─────────────────────────────────────────────────────────────────────────────


class BaselineRegressor:
    """OLS regression baseline: energy ~ f(OAT, hour, day_of_week).

    Trains separate models for occupied and unoccupied periods per IPMVP.
    Requires: pip install statsmodels scikit-learn
    """

    def __init__(self, min_samples: int = 100):
        self.min_samples = min_samples

    def train(
        self,
        records: list[EnergyRecord],
        period: str,
    ) -> BaselineModel | None:
        """Train OLS model for the given occupancy period.

        Feature vector: [OAT, hour, day_of_week, holiday_flag]
        """
        # Filter to period
        filtered = [
            r for r in records if (r.occupied and period == "occupied") or (not r.occupied and period == "unoccupied")
        ]

        # Exclude load shedding days
        filtered = [r for r in filtered if not r.load_shedding]

        if len(filtered) < self.min_samples:
            logger.warning(
                f"BaselineRegressor: only {len(filtered)} samples for {period}, need {self.min_samples}. Skipping."
            )
            return None

        import numpy as np

        try:
            import statsmodels.api as sm
        except ImportError:
            logger.error("statsmodels not installed: pip install statsmodels")
            return None

        # Build feature matrix
        X = np.array([[r.oat_celsius or 20.0, r.timestamp.hour, r.timestamp.weekday(), r.holiday] for r in filtered])
        y = np.array([r.kwh for r in filtered])

        # Add constant for intercept
        X = sm.add_constant(X)
        model = sm.OLS(y, X).fit()

        # CV(RMSE)% — IPMVP uncertainty metric
        residuals = model.resid
        rmse = np.sqrt(np.mean(residuals**2))
        cv_rmse_pct = (rmse / np.mean(y)) * 100 if np.mean(y) > 0 else 0

        # Coefficients: [const, oat, hour, dow, holiday]
        coef = {
            "const": model.params[0],
            "oat": model.params[1],
            "hour": model.params[2],
            "day_of_week": model.params[3],
            "holiday": model.params[4],
        }
        eq = (
            f"kWh = {coef['oat']:.3f} × OAT"
            f" + {coef['hour']:.3f} × hour"
            f" + {coef['day_of_week']:.3f} × day_of_week"
            f" + {coef['holiday']:.3f} × holiday"
            f" + {coef['const']:.2f}"
        )

        return BaselineModel(
            period=period,
            equation=eq,
            coefficients=coef,
            intercept=coef["const"],
            r_squared=model.rsquared,
            cv_rmse_pct=round(cv_rmse_pct, 2),
            n_samples=len(filtered),
            std_err_residual=rmse,
        )

    def predict(self, record: EnergyRecord, model: BaselineModel) -> float:
        """Apply trained baseline model to a single record."""
        return (
            model.intercept
            + model.coefficients["oat"] * (record.oat_celsius or 20.0)
            + model.coefficients["hour"] * record.timestamp.hour
            + model.coefficients["day_of_week"] * record.timestamp.weekday()
            + model.coefficients["holiday"] * (1 if record.holiday else 0)
        )


# ─────────────────────────────────────────────────────────────────────────────
# Savings calculator — Option C
# ─────────────────────────────────────────────────────────────────────────────


class SavingsCalculator:
    """Calculate IPMVP Option C savings: baseline_predicted − actual."""

    def __init__(self, regressor: BaselineRegressor):
        self.regressor = regressor

    def calculate(
        self,
        recommendation_id: str | None,
        reporting_start: datetime,
        reporting_end: datetime,
        records: list[EnergyRecord],
        occupied_model: BaselineModel | None,
        unoccupied_model: BaselineModel | None,
        tariff: dict[str, Any],
        hourly_detail: bool = True,
    ) -> SavingsResult:
        """Calculate savings over a reporting period.

        Args:
            recommendation_id: Optional — links to a specific recommendation
            reporting_start/end: Period boundaries
            records: All energy + OAT records in period
            occupied_model: Trained OLS for occupied hours
            unoccupied_model: Trained OLS for unoccupied hours
            tariff: Tariff structure for cost conversion
            hourly_detail: If True, return per-hour savings breakdown
        """
        # Filter to reporting period
        period_records = [r for r in records if reporting_start <= r.timestamp <= reporting_end]

        # Identify load shedding days
        {r.timestamp.date() for r in period_records if r.load_shedding}
        ls_records = [r for r in period_records if r.load_shedding]
        normal_records = [r for r in period_records if not r.load_shedding]

        # Build hourly savings detail
        hourly_savings: list[dict[str, Any]] = []
        total_baseline_kwh = 0.0
        total_actual_kwh = 0.0

        for record in period_records:
            model = occupied_model if record.occupied else unoccupied_model
            if model is None:
                continue

            baseline_kwh = self.regressor.predict(record, model)
            actual_kwh = record.kwh

            # Savings: positive = energy reduction (good)
            savings_kwh = baseline_kwh - actual_kwh
            rate = self._tariff_for_hour(record.timestamp, tariff)
            savings_zar = savings_kwh * rate

            total_baseline_kwh += baseline_kwh
            total_actual_kwh += actual_kwh

            if hourly_detail:
                hourly_savings.append(
                    {
                        "timestamp": record.timestamp.isoformat(),
                        "occupied": record.occupied,
                        "load_shedding": record.load_shedding,
                        "oat_celsius": record.oat_celsius,
                        "baseline_kwh": round(baseline_kwh, 3),
                        "actual_kwh": round(actual_kwh, 3),
                        "savings_kwh": round(savings_kwh, 3),
                        "savings_zar": round(savings_zar, 3),
                    }
                )

        # Aggregate
        savings_kwh = total_baseline_kwh - total_actual_kwh
        avg_rate = self._average_tariff(tariff)
        savings_zar = savings_kwh * avg_rate

        # Occupancy retained (exclude load shedding days from denominator)
        normal_days = len({r.timestamp.date() for r in normal_records})
        ls_days_count = len({r.timestamp.date() for r in ls_records})
        n_days_total = len({r.timestamp.date() for r in period_records})
        occupancy_retained_pct = (normal_days / n_days_total * 100) if n_days_total else 0

        # Overall CV(RMSE)% — weighted by period baseline
        cv = self._weighted_cv(
            occupied_model, unoccupied_model, occupied_model is not None, unoccupied_model is not None
        )

        # Pick primary model for notes
        primary_model = occupied_model or unoccupied_model
        notes = []
        if primary_model:
            notes.append(
                f"Baseline model: {primary_model.equation}, "
                f"R²={primary_model.r_squared:.3f}, CV(RMSE)%={primary_model.cv_rmse_pct:.1f}%"
            )
        if ls_days_count > 0:
            notes.append(
                f"Excluded {ls_days_count} load shedding days "
                f"({ls_days_count / n_days_total * 100:.0f}% of period) from savings calculation"
            )
        if cv > 20:
            notes.append(f"WARNING: CV(RMSE)% = {cv:.1f}% > 20% — savings uncertainty is HIGH")

        return SavingsResult(
            recommendation_id=recommendation_id,
            reporting_start=reporting_start,
            reporting_end=reporting_end,
            baseline=primary_model
            or BaselineRegressor().train([r for r in records if not r.load_shedding], "occupied")
            or BaselineModel("occupied", "", {}, 0, 0, 999, 0, 0),
            savings_kwh=savings_kwh,
            savings_zar=savings_zar,
            cv_rmse_pct=cv,
            occupancy_retained_pct=occupancy_retained_pct,
            excluded_load_shedding_kwh=sum(r.kwh for r in ls_records),
            n_days_in_period=n_days_total,
            n_load_shedding_days_excluded=ls_days_count,
            hourly_savings=hourly_savings if hourly_detail else [],
            notes=notes,
        )

    def _tariff_for_hour(self, dt: datetime, tariff: dict[str, Any]) -> float:
        """Return ZAR/kWh for the given hour."""
        if dt.weekday() >= 5:
            return tariff.get("offpeak_zar_per_kwh", tariff.get("standard_zar_per_kwh", 1.0))
        peak_hours = set(tariff.get("peak_hours", []))
        if dt.hour in peak_hours:
            return tariff.get("peak_zar_per_kwh", 2.5)
        elif 9 <= dt.hour <= 15:
            return tariff.get("standard_zar_per_kwh", 1.5)
        return tariff.get("offpeak_zar_per_kwh", 0.7)

    def _average_tariff(self, tariff: dict[str, Any]) -> float:
        weights = {"peak": 6, "standard": 9, "offpeak": 9}
        total = sum(weights.values())
        return (
            weights["peak"] * tariff.get("peak_zar_per_kwh", 2.5)
            + weights["standard"] * tariff.get("standard_zar_per_kwh", 1.5)
            + weights["offpeak"] * tariff.get("offpeak_zar_per_kwh", 0.7)
        ) / total

    def _weighted_cv(
        self, occ: BaselineModel | None, unocc: BaselineModel | None, has_occ: bool, has_unocc: bool
    ) -> float:
        """Weighted average CV(RMSE)% across periods."""
        if not has_occ and not has_unocc:
            return 999.0
        cvs = []
        weights = []
        if has_occ and occ:
            cvs.append(occ.cv_rmse_pct)
            weights.append(occ.n_samples)
        if has_unocc and unocc:
            cvs.append(unocc.cv_rmse_pct)
            weights.append(unocc.n_samples)
        if not weights:
            return 999.0
        return sum(c * w for c, w in zip(cvs, weights)) / sum(weights)


# ─────────────────────────────────────────────────────────────────────────────
# Option A retrofit isolator
# ─────────────────────────────────────────────────────────────────────────────


class RetrofitIsolator:
    """IPMVP Option A — Retrofit Isolation for discrete system changes.

    Used when a specific equipment change can be metered in isolation
    (e.g., lighting retrofit with sub-meter, or VSD on a single AHU).
    """

    def calculate(
        self,
        event: EquipmentEvent,
        pre_records: list[EnergyRecord],
        post_records: list[EnergyRecord],
        tariff: dict[str, Any],
    ) -> SavingsResult:
        """Calculate savings by comparing pre vs post metered periods.

        Args:
            event: The equipment change event
            pre_records: 2+ weeks of energy data before the change
            post_records: Reporting period energy data after the change
            tariff: For cost conversion
        """
        if not pre_records or not post_records:
            return SavingsResult(
                recommendation_id=event.recommendation_id,
                reporting_start=post_records[0].timestamp if post_records else datetime.min,
                reporting_end=post_records[-1].timestamp if post_records else datetime.min,
                baseline=BaselineModel("pre", "", {}, 0, 0, 999, 0, 0),
                savings_kwh=0.0,
                savings_zar=0.0,
                cv_rmse_pct=999,
                occupancy_retained_pct=0,
                excluded_load_shedding_kwh=0,
                n_days_in_period=0,
                n_load_shedding_days_excluded=0,
                notes=["INSUFFICIENT DATA: pre or post records empty"],
            )

        # Deemed savings: average pre minus average post (per interval)
        pre_avg = sum(r.kwh for r in pre_records) / len(pre_records)
        post_avg = sum(r.kwh for r in post_records) / len(post_records)

        savings_per_interval = pre_avg - post_avg
        n_intervals = len(post_records)
        savings_kwh = savings_per_interval * n_intervals

        # Exclude load shedding from post period
        ls_records = [r for r in post_records if r.load_shedding]
        ls_savings_excluded = sum(r.kwh for r in ls_records)
        savings_kwh_normal = savings_kwh - ls_savings_excluded

        avg_rate = (
            sum(r.kwh * self._rate_for(r.timestamp, tariff) for r in post_records) / sum(r.kwh for r in post_records)
            if post_records
            else 1.5
        )
        savings_zar = savings_kwh_normal * avg_rate

        # Uncertainty: CV of the two means
        import numpy as np

        pre_vals = np.array([r.kwh for r in pre_records])
        post_vals = np.array([r.kwh for r in post_records])
        combined_std = np.sqrt(np.var(pre_vals) / len(pre_vals) + np.var(post_vals) / len(post_vals))
        cv_rmse_pct = (combined_std / (np.mean(post_vals) or 1)) * 100

        return SavingsResult(
            recommendation_id=event.recommendation_id,
            reporting_start=post_records[0].timestamp,
            reporting_end=post_records[-1].timestamp,
            baseline=BaselineModel(
                period="pre_vs_post",
                equation=f"Deemed: pre_avg={pre_avg:.2f} kWh/interval vs post_avg={post_avg:.2f}",
                coefficients={},
                intercept=pre_avg,
                r_squared=0.0,
                cv_rmse_pct=round(cv_rmse_pct, 1),
                n_samples=len(pre_records) + len(post_records),
                std_err_residual=combined_std,
            ),
            savings_kwh=savings_kwh_normal,
            savings_zar=savings_zar,
            cv_rmse_pct=round(cv_rmse_pct, 1),
            occupancy_retained_pct=((1 - len(ls_records) / len(post_records)) * 100 if post_records else 0),
            excluded_load_shedding_kwh=ls_savings_excluded,
            n_days_in_period=len({r.timestamp.date() for r in post_records}),
            n_load_shedding_days_excluded=len({r.timestamp.date() for r in ls_records}),
            notes=[
                f"Option A — {event.system_type} retrofit isolation",
                f"Pre period: {pre_records[0].timestamp.date()} → {pre_records[-1].timestamp.date()}",
                f"Post period: {post_records[0].timestamp.date()} → {post_records[-1].timestamp.date()}",
                f"Pre avg: {pre_avg:.3f} kWh/interval | Post avg: {post_avg:.3f} kWh/interval",
            ],
        )

    def _rate_for(self, dt: datetime, tariff: dict[str, Any]) -> float:
        if dt.weekday() >= 5:
            return tariff.get("offpeak_zar_per_kwh", 0.7)
        peak_hours = set(tariff.get("peak_hours", []))
        if dt.hour in peak_hours:
            return tariff.get("peak_zar_per_kwh", 2.5)
        return tariff.get("standard_zar_per_kwh", 1.5)


# ─────────────────────────────────────────────────────────────────────────────
# IPMVP Orchestrator
# ─────────────────────────────────────────────────────────────────────────────


class IPMVPEngine:
    """Main orchestrator for IPMVP M&V.

    Usage:
        engine = IPMVPEngine(site_id="site-002", fetcher=my_data_fetcher)
        report = await engine.run_report(
            reporting_start=datetime(2026, 1, 1),
            reporting_end=datetime(2026, 2, 28),
        )
    """

    def __init__(
        self,
        site_id: str,
        fetcher: IPMVPDataFetcher | None = None,
        regressor: BaselineRegressor | None = None,
        calculator: SavingsCalculator | None = None,
        isolator: RetrofitIsolator | None = None,
    ):
        self.site_id = site_id
        self.fetcher = fetcher or IPMVPDataFetcher(site_id)
        self.regressor = regressor or BaselineRegressor()
        self.calculator = calculator or SavingsCalculator(self.regressor)
        self.isolator = isolator or RetrofitIsolator()

    async def run_report(
        self,
        reporting_start: datetime,
        reporting_end: datetime,
        option: str = "C",
        recommendation_id: str | None = None,
        hourly_detail: bool = True,
        baseline_cutoff: datetime | None = None,
    ) -> IPMVPReport:
        """Generate full IPMVP M&V report.

        Args:
            reporting_start: Beginning of reporting period
            reporting_end: End of reporting period
            option: "C" (whole facility) or "A" (retrofit isolation)
            recommendation_id: Optional — for Option A, links to specific event
            hourly_detail: Include per-interval savings breakdown
            baseline_cutoff: Date when site entered advisory phase (intervention start).
                Records before cutoff train the baseline; records after are the
                reporting period. When None, trains on the full window (valid for
                pre-advisory or backwards compatibility).
        """
        logger.info(
            f"IPMVPEngine[{self.site_id}]: running Option {option} "
            f"report for {reporting_start.date()} → {reporting_end.date()}"
            + (f" (baseline cutoff: {baseline_cutoff.date()})" if baseline_cutoff else "")
        )

        # 1. Fetch all data
        records = await self.fetcher.fetch_energy_and_oat(reporting_start, reporting_end)
        tariff = await self.fetcher.fetch_tariff()

        # 2. Train baseline models (Option C)
        if option == "C":
            # Split records into baseline training set and reporting set
            if baseline_cutoff:
                training_records = [r for r in records if r.timestamp < baseline_cutoff]
                reporting_records = [r for r in records if r.timestamp >= baseline_cutoff]
                if not training_records:
                    logger.warning(
                        "No pre-advisory records for baseline training "
                        "(cutoff=%s, earliest=%s) — falling back to full window",
                        baseline_cutoff.date(),
                        records[0].timestamp.date() if records else "none",
                    )
                    training_records = records
                    reporting_records = records
                logger.info(
                    "IPMVP baseline: %d training records (pre-%s), %d reporting records",
                    len(training_records),
                    baseline_cutoff.date(),
                    len(reporting_records),
                )
            else:
                training_records = records
                reporting_records = records

            occupied_model = self.regressor.train(training_records, "occupied")
            unoccupied_model = self.regressor.train(training_records, "unoccupied")
            result = self.calculator.calculate(
                recommendation_id=recommendation_id,
                reporting_start=reporting_start,
                reporting_end=reporting_end,
                records=reporting_records,
                occupied_model=occupied_model,
                unoccupied_model=unoccupied_model,
                tariff=tariff,
                hourly_detail=hourly_detail,
            )
            results = [result]
        # 3. Option A — isolate specific event
        elif option == "A":
            events = await self.fetcher.fetch_equipment_events(
                reporting_start,
                reporting_end,
            )
            if not events:
                return IPMVPReport(
                    site_id=self.site_id,
                    generated_at=datetime.now(),
                    reporting_start=reporting_start,
                    reporting_end=reporting_end,
                    option=option,
                    results=[],
                    overall_savings_kwh=0,
                    overall_savings_zar=0,
                    aggregate_cv_rmse_pct=999,
                    methodology="IPMVP Option A — No events found in period",
                )
            event = events[0]
            # Split pre/post at event timestamp
            pre = [r for r in records if r.timestamp < event.timestamp]
            post = [r for r in records if r.timestamp >= event.timestamp]
            result = self.isolator.calculate(event, pre, post, tariff)
            results = [result]
        else:
            raise ValueError(f"Unknown option: {option}")

        overall_kwh = sum(r.savings_kwh for r in results)
        overall_zar = sum(r.savings_zar for r in results)
        sum(r.n_days_in_period for r in results)
        n_samples = sum(r.baseline.n_samples for r in results if r.baseline)
        agg_cv = (
            sum(r.cv_rmse_pct * r.baseline.n_samples for r in results if r.baseline) / n_samples if n_samples else 999
        )

        return IPMVPReport(
            site_id=self.site_id,
            generated_at=datetime.now(),
            reporting_start=reporting_start,
            reporting_end=reporting_end,
            option=option,
            results=results,
            overall_savings_kwh=overall_kwh,
            overall_savings_zar=overall_zar,
            aggregate_cv_rmse_pct=round(agg_cv, 2),
            methodology=(
                "IPMVP 2022 Edition Volume III Chapter 5 — Option C Whole Facility"
                if option == "C"
                else "IPMVP 2022 Edition Volume III Chapter 5 — Option A Retrofit Isolation"
            ),
        )

    async def run_baseline_only(
        self,
        baseline_start: datetime,
        baseline_end: datetime,
    ) -> dict[str, BaselineModel | None]:
        """Train baseline models without calculating savings (for validation)."""
        records = await self.fetcher.fetch_energy_and_oat(baseline_start, baseline_end)
        return {
            "occupied": self.regressor.train(records, "occupied"),
            "unoccupied": self.regressor.train(records, "unoccupied"),
        }
