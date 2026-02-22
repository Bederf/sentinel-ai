"""Solar Financial Reporting Service.

Provides the monthly evidence that justifies SENTINEL's licence fee.
Generates financial reports showing the value delivered by solar+BESS
optimisation vs a counterfactual "no SENTINEL" scenario.

Savings categories:
  - Arbitrage savings: TOU tariff optimisation (peak vs off-peak delta)
  - Demand charge savings: peak shaving via BESS
  - Self-consumption value: avoided import kWh x tariff rate
  - Generator diesel avoidance: litres saved x R22/L
  - Total SENTINEL value: sum of all above

Carbon offset:
  - Solar kWh x 0.95 kg/kWh (Eskom grid emission factor)
  - Diesel CO2 avoided: litres x 2.68 kg/L

For demo: generates 3 months of retrospective financial reports
with realistic savings for Site-002 297 kWp rooftop array.
"""

import logging
import random
from dataclasses import dataclass, field
from datetime import datetime, timezone, date
from typing import Dict, List, Optional, Any

from app.services.solar_config_service import get_site_solar_config

logger = logging.getLogger(__name__)


# === Constants ===

# Eskom grid emission factor (kg CO2 per kWh)
ESKOM_EMISSION_FACTOR_KG_KWH = 0.95

# Diesel emission factor (kg CO2 per litre)
DIESEL_EMISSION_FACTOR_KG_L = 2.68

# Diesel price (ZAR per litre, Feb 2026)
DIESEL_PRICE_ZAR_L = 22.0

# City Power LPU-TOU 2025/26 — energy charge + 6 c/kWh network surcharge
# Summer rates (Sep-May); see city_power_2025_26.json for winter
PEAK_TARIFF_ZAR_KWH = 3.0139  # 295.39 + 6 c/kWh
STANDARD_TARIFF_ZAR_KWH = 2.2839  # 222.39 + 6 c/kWh
OFFPEAK_TARIFF_ZAR_KWH = 1.7695  # 170.95 + 6 c/kWh

# Weighted average (19% peak, 39% standard, 42% off-peak from reference bill)
AVG_TARIFF_ZAR_KWH = 2.21

# Demand charge rate (R/kVA/month)
DEMAND_CHARGE_ZAR_KVA = 395.48  # City Power LPU-TOU 2025/26 verified

# Generator consumption rate (litres/hour at 70% load)
GENERATOR_CONSUMPTION_L_HR = 30.0

# Site-002 installed capacity
_CAPACITY_KWP = 297.0  # Site-002: 4 × 100 kVA rooftop inverters


# === Data models ===


@dataclass
class SavingsBreakdown:
    """Breakdown of savings by category."""

    arbitrage_zar: float = 0.0
    demand_charge_zar: float = 0.0
    self_consumption_zar: float = 0.0
    diesel_avoidance_zar: float = 0.0
    total_zar: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "arbitrage_zar": round(self.arbitrage_zar, 2),
            "demand_charge_zar": round(self.demand_charge_zar, 2),
            "self_consumption_zar": round(self.self_consumption_zar, 2),
            "diesel_avoidance_zar": round(self.diesel_avoidance_zar, 2),
            "total_zar": round(self.total_zar, 2),
        }


@dataclass
class MonthlyFinancialReport:
    """Monthly financial report showing SENTINEL value delivered."""

    site_id: str
    month: int
    year: int
    month_name: str
    generation_kwh: float
    generation_value_zar: float
    savings: SavingsBreakdown
    counterfactual_cost_zar: float  # Cost without SENTINEL
    actual_cost_zar: float  # Cost with SENTINEL
    sentinel_value_zar: float  # Difference = value delivered
    performance_ratio: float
    self_consumption_pct: float
    peak_shaving_kw: float
    generator_hours_avoided: float
    diesel_litres_saved: float
    generated_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "site_id": self.site_id,
            "month": self.month,
            "year": self.year,
            "month_name": self.month_name,
            "generation_kwh": round(self.generation_kwh, 1),
            "generation_value_zar": round(self.generation_value_zar, 2),
            "savings": self.savings.to_dict(),
            "counterfactual_cost_zar": round(self.counterfactual_cost_zar, 2),
            "actual_cost_zar": round(self.actual_cost_zar, 2),
            "sentinel_value_zar": round(self.sentinel_value_zar, 2),
            "performance_ratio": round(self.performance_ratio, 3),
            "self_consumption_pct": round(self.self_consumption_pct, 1),
            "peak_shaving_kw": round(self.peak_shaving_kw, 1),
            "generator_hours_avoided": round(self.generator_hours_avoided, 1),
            "diesel_litres_saved": round(self.diesel_litres_saved, 1),
            "generated_at": self.generated_at,
        }


@dataclass
class FinancialSummary:
    """Year-to-date financial summary."""

    site_id: str
    period: str
    months: List[Dict[str, Any]] = field(default_factory=list)
    cumulative_savings_zar: float = 0.0
    cumulative_generation_kwh: float = 0.0
    average_monthly_savings_zar: float = 0.0
    sentinel_licence_fee_zar: float = 0.0
    roi_percentage: float = 0.0
    payback_months: float = 0.0
    generated_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "site_id": self.site_id,
            "period": self.period,
            "months": self.months,
            "cumulative_savings_zar": round(self.cumulative_savings_zar, 2),
            "cumulative_generation_kwh": round(self.cumulative_generation_kwh, 1),
            "average_monthly_savings_zar": round(self.average_monthly_savings_zar, 2),
            "sentinel_licence_fee_zar": round(self.sentinel_licence_fee_zar, 2),
            "roi_percentage": round(self.roi_percentage, 1),
            "payback_months": round(self.payback_months, 1),
            "generated_at": self.generated_at,
        }


@dataclass
class CarbonReport:
    """Carbon offset report."""

    site_id: str
    period: str
    solar_kwh: float
    grid_co2_avoided_kg: float
    grid_co2_avoided_tonnes: float
    diesel_litres_avoided: float
    diesel_co2_avoided_kg: float
    diesel_co2_avoided_tonnes: float
    total_co2_avoided_kg: float
    total_co2_avoided_tonnes: float
    trees_equivalent: int  # 1 tree absorbs ~22 kg CO2/year
    generated_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "site_id": self.site_id,
            "period": self.period,
            "solar_kwh": round(self.solar_kwh, 1),
            "grid_co2_avoided_kg": round(self.grid_co2_avoided_kg, 1),
            "grid_co2_avoided_tonnes": round(self.grid_co2_avoided_tonnes, 2),
            "diesel_litres_avoided": round(self.diesel_litres_avoided, 1),
            "diesel_co2_avoided_kg": round(self.diesel_co2_avoided_kg, 1),
            "diesel_co2_avoided_tonnes": round(self.diesel_co2_avoided_tonnes, 2),
            "total_co2_avoided_kg": round(self.total_co2_avoided_kg, 1),
            "total_co2_avoided_tonnes": round(self.total_co2_avoided_tonnes, 2),
            "trees_equivalent": self.trees_equivalent,
            "eskom_emission_factor_kg_kwh": ESKOM_EMISSION_FACTOR_KG_KWH,
            "diesel_emission_factor_kg_l": DIESEL_EMISSION_FACTOR_KG_L,
            "generated_at": self.generated_at,
        }


# === Service ===


class SolarFinancialService:
    """Financial reporting for solar installations."""

    # Monthly demo data for Site-002 (297 kWp, JHB)
    # Realistic for SA commercial installation
    DEMO_MONTHLY_DATA = {
        # (month, year) -> (generation_kwh, pr, gen_hours_avoided, ls_events)
        # 297 kWp × ~5.5 PSH × days × PR = ~40-44k kWh/month in JHB summer
        (12, 2025): {
            "generation_kwh": 43_400,
            "pr": 0.815,
            "gen_hours_avoided": 24,
            "ls_events": 12,
            "peak_shaving_kw": 85,
        },
        (1, 2026): {
            "generation_kwh": 42_800,
            "pr": 0.822,
            "gen_hours_avoided": 18,
            "ls_events": 9,
            "peak_shaving_kw": 78,
        },
        (2, 2026): {
            "generation_kwh": 36_200,
            "pr": 0.808,
            "gen_hours_avoided": 22,
            "ls_events": 11,
            "peak_shaving_kw": 90,
        },
    }

    def __init__(self):
        try:
            cfg = get_site_solar_config("site-002")
            self.DEMAND_CHARGE_ZAR_KVA = cfg.tariff.demand_charge_r_kva()
            self._CAPACITY_KWP = cfg.pv.total_capacity_kwp
        except Exception:
            pass
        logger.info("SolarFinancialService initialized")

    def generate_monthly_report(self, site_id: str, month: int, year: int) -> MonthlyFinancialReport:
        """Generate monthly financial report with full savings breakdown.

        For demo, uses pre-seeded data for Dec 2025, Jan 2026, Feb 2026.
        """
        now = datetime.now(timezone.utc)
        month_name = date(year, month, 1).strftime("%B %Y")

        # Get demo data or generate synthetic
        data = self.DEMO_MONTHLY_DATA.get(
            (month, year),
            self._generate_synthetic_month(month, year),
        )

        generation_kwh = data["generation_kwh"]
        pr = data["pr"]
        gen_hours_avoided = data["gen_hours_avoided"]
        peak_shaving_kw = data["peak_shaving_kw"]

        # --- Calculate SENTINEL optimisation savings (delta vs no-optimisation) ---
        # These represent the incremental value SENTINEL adds, not total solar value.
        # Target: R80-150K/month for a 3.9 MWp Site-002 campus.

        # 1. Arbitrage savings (BESS TOU optimisation)
        # SENTINEL shifts ~350 kWh/day from off-peak charge to peak discharge
        # 5 MWh BESS, ~70% usable, one cycle per day
        bess_shifted_kwh_day = 350
        days_in_month = 30
        arbitrage_delta_per_kwh = PEAK_TARIFF_ZAR_KWH - OFFPEAK_TARIFF_ZAR_KWH  # R2.63/kWh
        arbitrage = bess_shifted_kwh_day * days_in_month * arbitrage_delta_per_kwh * random.uniform(0.85, 0.95)

        # 2. Demand charge savings (peak shaving via BESS)
        demand_savings = peak_shaving_kw * DEMAND_CHARGE_ZAR_KVA

        # 3. Self-consumption optimisation (SENTINEL routes excess solar to BESS)
        # Without optimisation ~85% self-consumption, with ~97%
        # Delta: ~3% of generation value captured rather than curtailed/exported at zero
        self_consumption_pct = 96.5 + random.uniform(-2, 2)
        delta_kwh = generation_kwh * 0.03  # 3% improvement from SENTINEL
        self_consumption_value = delta_kwh * AVG_TARIFF_ZAR_KWH * random.uniform(0.8, 1.0)

        # 4. Diesel avoidance (SENTINEL sustains BESS through LS, avoiding generator)
        diesel_litres = gen_hours_avoided * GENERATOR_CONSUMPTION_L_HR
        diesel_value = diesel_litres * DIESEL_PRICE_ZAR_L

        # Total SENTINEL optimisation savings
        total_savings = arbitrage + demand_savings + self_consumption_value + diesel_value

        savings = SavingsBreakdown(
            arbitrage_zar=arbitrage,
            demand_charge_zar=demand_savings,
            self_consumption_zar=self_consumption_value,
            diesel_avoidance_zar=diesel_value,
            total_zar=total_savings,
        )

        # Generation value at average TOU rate
        generation_value = generation_kwh * AVG_TARIFF_ZAR_KWH

        # Counterfactual: what would the building spend without SENTINEL/solar?
        building_consumption_kwh = generation_kwh * 1.3  # building uses more than solar provides
        counterfactual = building_consumption_kwh * AVG_TARIFF_ZAR_KWH
        actual_cost = counterfactual - total_savings

        return MonthlyFinancialReport(
            site_id=site_id,
            month=month,
            year=year,
            month_name=month_name,
            generation_kwh=generation_kwh,
            generation_value_zar=generation_value,
            savings=savings,
            counterfactual_cost_zar=counterfactual,
            actual_cost_zar=actual_cost,
            sentinel_value_zar=total_savings,
            performance_ratio=pr,
            self_consumption_pct=self_consumption_pct,
            peak_shaving_kw=peak_shaving_kw,
            generator_hours_avoided=gen_hours_avoided,
            diesel_litres_saved=diesel_litres,
            generated_at=now.isoformat(),
        )

    def get_financial_summary(self, site_id: str, period: str = "ytd") -> FinancialSummary:
        """Get year-to-date cumulative savings with monthly breakdown."""
        now = datetime.now(timezone.utc)

        # Generate reports for available months
        months_data = []
        cumulative_savings = 0.0
        cumulative_generation = 0.0

        for (month, year), _ in sorted(self.DEMO_MONTHLY_DATA.items()):
            report = self.generate_monthly_report(site_id, month, year)
            months_data.append(
                {
                    "month": report.month,
                    "year": report.year,
                    "month_name": report.month_name,
                    "generation_kwh": round(report.generation_kwh, 1),
                    "total_savings_zar": round(report.savings.total_zar, 2),
                    "arbitrage_zar": round(report.savings.arbitrage_zar, 2),
                    "demand_charge_zar": round(report.savings.demand_charge_zar, 2),
                    "self_consumption_zar": round(report.savings.self_consumption_zar, 2),
                    "diesel_avoidance_zar": round(report.savings.diesel_avoidance_zar, 2),
                }
            )
            cumulative_savings += report.savings.total_zar
            cumulative_generation += report.generation_kwh

        num_months = len(months_data) or 1
        avg_monthly = cumulative_savings / num_months

        # SENTINEL licence fee (demo estimate for a 297 kWp site)
        licence_fee = 85_000.0  # R85K/month

        roi = ((avg_monthly - licence_fee) / licence_fee * 100) if licence_fee > 0 else 0
        payback = licence_fee / avg_monthly if avg_monthly > 0 else 999

        return FinancialSummary(
            site_id=site_id,
            period=period,
            months=months_data,
            cumulative_savings_zar=cumulative_savings,
            cumulative_generation_kwh=cumulative_generation,
            average_monthly_savings_zar=avg_monthly,
            sentinel_licence_fee_zar=licence_fee * num_months,
            roi_percentage=roi,
            payback_months=payback,
            generated_at=now.isoformat(),
        )

    def get_carbon_offset(self, site_id: str, period: str = "month") -> CarbonReport:
        """Calculate carbon offset from solar generation.

        Eskom grid emission factor: 0.95 kg CO2/kWh (2024 IRP)
        Diesel CO2: 2.68 kg CO2/litre
        """
        now = datetime.now(timezone.utc)

        if period == "month":
            # Use current month data
            current_data = self.DEMO_MONTHLY_DATA.get(
                (now.month, now.year),
                self._generate_synthetic_month(now.month, now.year),
            )
            solar_kwh = current_data["generation_kwh"]
            diesel_litres = current_data["gen_hours_avoided"] * GENERATOR_CONSUMPTION_L_HR
        else:
            # YTD — sum all months
            solar_kwh = sum(d["generation_kwh"] for d in self.DEMO_MONTHLY_DATA.values())
            diesel_litres = sum(
                d["gen_hours_avoided"] * GENERATOR_CONSUMPTION_L_HR for d in self.DEMO_MONTHLY_DATA.values()
            )

        grid_co2_kg = solar_kwh * ESKOM_EMISSION_FACTOR_KG_KWH
        diesel_co2_kg = diesel_litres * DIESEL_EMISSION_FACTOR_KG_L
        total_co2_kg = grid_co2_kg + diesel_co2_kg

        # Tree equivalent: ~22 kg CO2 absorbed per tree per year
        trees = int(total_co2_kg / 22 * 12)  # monthly extrapolated to annual

        return CarbonReport(
            site_id=site_id,
            period=period,
            solar_kwh=solar_kwh,
            grid_co2_avoided_kg=grid_co2_kg,
            grid_co2_avoided_tonnes=grid_co2_kg / 1000,
            diesel_litres_avoided=diesel_litres,
            diesel_co2_avoided_kg=diesel_co2_kg,
            diesel_co2_avoided_tonnes=diesel_co2_kg / 1000,
            total_co2_avoided_kg=total_co2_kg,
            total_co2_avoided_tonnes=total_co2_kg / 1000,
            trees_equivalent=trees,
            generated_at=now.isoformat(),
        )

    def _generate_synthetic_month(self, month: int, year: int) -> Dict[str, Any]:
        """Generate synthetic monthly data for months without demo data."""
        # JHB solar resource varies by season
        seasonal_factor = {
            1: 1.05,
            2: 1.00,
            3: 0.95,
            4: 0.85,
            5: 0.75,
            6: 0.70,
            7: 0.72,
            8: 0.80,
            9: 0.90,
            10: 0.95,
            11: 1.02,
            12: 1.05,
        }
        factor = seasonal_factor.get(month, 0.85)

        # Base generation: capacity * 5.5 peak sun hours * 30 days * PR * factor
        base_gen = _CAPACITY_KWP * 5.5 * 30 * 0.81 * factor
        generation = base_gen * random.uniform(0.95, 1.05)

        return {
            "generation_kwh": round(generation, 0),
            "pr": round(0.80 + random.uniform(0, 0.03), 3),
            "gen_hours_avoided": round(15 + random.uniform(0, 15)),
            "ls_events": round(8 + random.uniform(0, 8)),
            "peak_shaving_kw": round(60 + random.uniform(0, 35)),
        }


# === Singleton ===

_service: Optional[SolarFinancialService] = None


def get_solar_financial_service() -> SolarFinancialService:
    """Get or create the singleton financial service."""
    global _service
    if _service is None:
        _service = SolarFinancialService()
    return _service
