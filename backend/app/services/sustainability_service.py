"""
Sustainability & ESG Service

Derives carbon emissions from existing energy data:
- Scope 1: Diesel generator consumption
- Scope 2: Grid electricity (Eskom)
- Scope 3: Water, waste, commuting estimates

No new data ingestion — uses Energy module + Generator service + building metadata.
"""

import json
import logging
import math
import random
from datetime import datetime, timedelta
from pathlib import Path

from app.models.sustainability import (
    BenchmarkComparison,
    EmissionFactors,
    EmissionsSnapshot,
    GreenStarAssessment,
    GreenStarCategory,
    SustainabilityConfig,
)

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data" / "sustainability"


class SustainabilityService:
    """Calculates emissions, efficiency metrics, and tracks Green Star SA."""

    def __init__(self):
        self._configs: dict[str, SustainabilityConfig] = {}
        self._assessments: dict[str, GreenStarAssessment] = {}
        self._benchmarks = BenchmarkComparison()

    def get_config(self, site_id: str) -> SustainabilityConfig:
        """Load site sustainability config from JSON."""
        if site_id in self._configs:
            return self._configs[site_id]

        config_path = DATA_DIR / f"{site_id}_config.json"
        if config_path.exists():
            with open(config_path) as f:
                data = json.load(f)
            config = SustainabilityConfig.from_dict(data)
        else:
            config = SustainabilityConfig(site_id=site_id)

        self._configs[site_id] = config
        return config

    def update_config(self, site_id: str, updates: dict) -> SustainabilityConfig:
        """Update and persist site sustainability config."""
        config = self.get_config(site_id)

        if "site_sqm" in updates:
            config.site_sqm = updates["site_sqm"]
        if "occupancy_capacity" in updates:
            config.occupancy_capacity = updates["occupancy_capacity"]
        if "target_reduction_pct" in updates:
            config.target_reduction_pct = updates["target_reduction_pct"]
        if "monthly_water_kl" in updates:
            config.monthly_water_kl = updates["monthly_water_kl"]
        if "monthly_waste_tons" in updates:
            config.monthly_waste_tons = updates["monthly_waste_tons"]
        if "working_days_per_month" in updates:
            config.working_days_per_month = updates["working_days_per_month"]
        if "avg_occupancy_pct" in updates:
            config.avg_occupancy_pct = updates["avg_occupancy_pct"]
        if "emission_factors" in updates:
            config.emission_factors = EmissionFactors.from_dict(updates["emission_factors"])

        self._configs[site_id] = config
        self._save_config(config)
        return config

    def _save_config(self, config: SustainabilityConfig):
        """Persist config to JSON."""
        config_path = DATA_DIR / f"{config.site_id}_config.json"
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(config_path, "w") as f:
            json.dump(config.to_dict(), f, indent=2)

    def _get_energy_data(self, site_id: str, days: int = 30) -> list[dict]:
        """Get energy consumption data from energy API."""
        try:
            from app.api.energy import generate_energy_data, load_equipment
            from app.services.site_loader import BuildingDataLoader

            loader = BuildingDataLoader()
            buildings = loader.get_all_sites()

            sites = []
            for b in buildings:
                b_dict = b if isinstance(b, dict) else {}
                metadata = b_dict.get("metadata", {})
                sites.append(
                    {
                        "id": b_dict.get("id"),
                        "name": b_dict.get("display_name") or b_dict.get("name") or b_dict.get("id"),
                        "sqm": metadata.get("sqm", 1000),
                    }
                )

            equipment = load_equipment()
            data_points = generate_energy_data(sites, equipment, days=days, site_id=site_id)

            return [
                {
                    "date": dp.date,
                    "hvac_kwh": dp.hvac_kwh,
                    "lighting_kwh": dp.lighting_kwh,
                    "other_kwh": dp.other_kwh,
                    "total_kwh": dp.total_kwh,
                }
                for dp in data_points
            ]
        except Exception as e:
            logger.warning(f"Could not load energy data from API: {e}")
            return self._generate_synthetic_energy(site_id, days)

    def _generate_synthetic_energy(self, site_id: str, days: int) -> list[dict]:
        """Generate synthetic energy data when energy API is unavailable."""
        random.seed(42)
        config = self.get_config(site_id)
        sqm = config.site_sqm

        # SA office typical: ~170 kWh/sqm/year = ~0.465 kWh/sqm/day
        daily_base = sqm * 0.465
        hvac_pct, lighting_pct, other_pct = 0.55, 0.25, 0.20

        result = []
        end_date = datetime.now().date()
        for i in range(days):
            date = end_date - timedelta(days=days - 1 - i)
            is_weekend = date.weekday() >= 5
            factor = 0.4 if is_weekend else 1.0
            var = random.uniform(0.85, 1.15)

            total = daily_base * factor * var
            result.append(
                {
                    "date": date.isoformat(),
                    "hvac_kwh": round(total * hvac_pct, 1),
                    "lighting_kwh": round(total * lighting_pct, 1),
                    "other_kwh": round(total * other_pct, 1),
                    "total_kwh": round(total, 1),
                }
            )

        return result

    def _get_daily_metrics(self, site_id: str, start_date: str, end_date: str) -> list[dict]:
        """Query daily_sustainability_metrics table. Falls back to JSON for local mode."""
        try:
            from app.database.supabase_client import get_supabase_client

            client = get_supabase_client()
            result = (
                client.table("daily_sustainability_metrics")
                .select("*")
                .eq("site_id", site_id)
                .gte("date", start_date)
                .lte("date", end_date)
                .order("date")
                .execute()
            )
            if result.data:
                return result.data
        except Exception as e:
            logger.debug(f"daily_sustainability_metrics query failed: {e}")

        # Fallback: JSON file
        json_path = DATA_DIR / "daily_metrics" / f"{site_id}.json"
        if json_path.exists():
            with open(json_path) as f:
                records = json.load(f)
            return [r for r in records if start_date <= r.get("date", "") <= end_date]

        return []  # No data available — will fall through to estimates

    def _get_diesel_data(self, site_id: str, month: str) -> tuple:
        """Get diesel liters. Returns (liters, source)."""
        # Try real metrics first
        start = f"{month}-01"
        end = f"{month}-28"  # Safe for all months
        metrics = self._get_daily_metrics(site_id, start, end)
        if metrics:
            total = sum(float(m.get("diesel_liters", 0)) for m in metrics)
            if total > 0:
                return total, "measured"

        # Fallback to estimate (existing logic)
        return self._estimate_diesel_litres_legacy(site_id, month), "estimated"

    def _get_water_data(self, site_id: str, month: str) -> tuple:
        """Get water kL. Returns (kl, source)."""
        metrics = self._get_daily_metrics(site_id, f"{month}-01", f"{month}-28")
        if metrics:
            total_liters = sum(float(m.get("water_liters", 0)) for m in metrics)
            if total_liters > 0:
                return total_liters / 1000, "measured"

        config = self.get_config(site_id)
        return config.monthly_water_kl, "estimated"

    def _estimate_diesel_litres_legacy(self, site_id: str, month: str) -> float:
        """Estimate diesel consumption for a month from generator data (legacy fallback)."""
        try:
            from app.services.generator_service import generator_service

            generators = generator_service.get_generators(site_id=site_id)
            if not generators:
                generators = generator_service.get_generators()

            total_litres = 0.0
            for gen in generators:
                fuel_rate = 0.0
                if hasattr(gen, "engine") and gen.engine:
                    fuel_rate = gen.engine.get("fuel_rate_lph", 0.0)
                elif isinstance(gen, dict):
                    engine = gen.get("engine", {})
                    fuel_rate = engine.get("fuel_rate_lph", 0.0) if engine else 0.0

                # Estimate ~2-4 hours/day average generator runtime (load shedding)
                avg_daily_hours = 3.0
                monthly_hours = avg_daily_hours * 22  # Working days
                total_litres += fuel_rate * monthly_hours

            return round(total_litres, 1) if total_litres > 0 else 85.0
        except Exception as e:
            logger.debug(f"Generator data unavailable: {e}")
            return 85.0  # Default estimate for local fallback mode

    def calculate_current_emissions(self, site_id: str) -> EmissionsSnapshot:
        """Calculate current month's emissions from live data.

        Data priority: daily_sustainability_metrics -> energy API -> synthetic estimates.
        Populates per-system breakdown, solar offset, and data_source tracking.
        """
        config = self.get_config(site_id)
        ef = config.emission_factors

        # Get current month energy data
        now = datetime.now()
        days_so_far = now.day
        month_str = now.strftime("%Y-%m")

        # Try daily_sustainability_metrics first for energy breakdown
        daily_metrics = self._get_daily_metrics(site_id, f"{month_str}-01", f"{month_str}-28")
        has_daily_metrics = len(daily_metrics) > 0
        data_source = "estimated"  # Conservative default

        if has_daily_metrics:
            # Use real metrics data
            grid_kwh = sum(float(m.get("grid_kwh", 0) or m.get("total_kwh", 0)) for m in daily_metrics)
            hvac_kwh = sum(float(m.get("hvac_kwh", 0)) for m in daily_metrics)
            lighting_kwh = sum(float(m.get("lighting_kwh", 0)) for m in daily_metrics)
            other_kwh = sum(float(m.get("other_kwh", 0)) for m in daily_metrics)
            solar_kwh = sum(float(m.get("solar_generation_kwh", 0)) for m in daily_metrics)
            data_source = "simulation"  # Data from daily metrics table
        else:
            # Fallback to energy API / synthetic
            energy_data = self._get_energy_data(site_id, days=days_so_far)
            grid_kwh = sum(d["total_kwh"] for d in energy_data)
            hvac_kwh = sum(d["hvac_kwh"] for d in energy_data)
            lighting_kwh = sum(d["lighting_kwh"] for d in energy_data)
            other_kwh = sum(d["other_kwh"] for d in energy_data)
            solar_kwh = 0.0

        # Diesel consumption (real data path first)
        diesel_litres, diesel_source = self._get_diesel_data(site_id, month_str)
        if diesel_source == "estimated":
            # Scale estimated diesel to days elapsed
            diesel_litres = diesel_litres * (days_so_far / 30.0)
            data_source = "estimated"  # Mixed data = conservative

        # Water consumption (real data path first)
        water_kl, water_source = self._get_water_data(site_id, month_str)
        if water_source == "estimated":
            data_source = "estimated"

        # Scope 1: Diesel
        scope1 = diesel_litres * ef.diesel_kg_co2_per_litre

        # Scope 2: Grid (gross, before solar offset)
        scope2 = grid_kwh * ef.grid_kg_co2_per_kwh

        # Solar offset for Scope 2
        solar_offset_kg = solar_kwh * ef.grid_kg_co2_per_kwh
        net_scope2 = max(0, scope2 - solar_offset_kg)

        # Scope 3: Water + Waste + Commuting (scaled to days elapsed)
        monthly_frac = days_so_far / 30.0
        water_co2 = water_kl * ef.water_kg_co2_per_kl * monthly_frac
        waste_co2 = config.monthly_waste_tons * ef.waste_kg_co2_per_ton * monthly_frac
        avg_employees = config.occupancy_capacity * (config.avg_occupancy_pct / 100.0)
        commute_co2 = avg_employees * days_so_far * ef.commute_kg_co2_per_person_day
        scope3 = water_co2 + waste_co2 + commute_co2

        # Per-system carbon breakdown
        hvac_co2 = hvac_kwh * ef.grid_kg_co2_per_kwh
        lighting_co2 = lighting_kwh * ef.grid_kg_co2_per_kwh
        other_co2 = other_kwh * ef.grid_kg_co2_per_kwh

        breakdown = {
            "hvac": round(hvac_co2, 2),
            "lighting": round(lighting_co2, 2),
            "other_electrical": round(other_co2, 2),
            "diesel_generators": round(scope1, 2),
            "water": round(water_co2, 2),
            "waste": round(waste_co2, 2),
            "commuting": round(commute_co2, 2),
        }

        sqm = config.site_sqm
        return EmissionsSnapshot(
            month=month_str,
            site_id=site_id,
            scope1_kg_co2=scope1,
            scope2_kg_co2=scope2,
            scope3_kg_co2=scope3,
            grid_kwh=grid_kwh,
            diesel_litres=diesel_litres,
            carbon_intensity_kg_per_sqm=(scope1 + scope2 + scope3) / sqm if sqm else 0,
            energy_intensity_kwh_per_sqm=grid_kwh / sqm if sqm else 0,
            breakdown_by_system=breakdown,
            # Per-system carbon breakdown (plan 111-02)
            hvac_kg_co2=hvac_co2,
            lighting_kg_co2=lighting_co2,
            other_kg_co2=other_co2,
            solar_offset_kg_co2=solar_offset_kg,
            net_scope2_kg_co2=net_scope2,
            # Source data tracking
            actual_diesel_liters=diesel_litres if diesel_source == "measured" else None,
            actual_water_kl=water_kl if water_source == "measured" else None,
            solar_generation_kwh=solar_kwh if solar_kwh > 0 else None,
            data_source=data_source,
        )

    def get_emissions_history(self, site_id: str, months: int = 12) -> list[EmissionsSnapshot]:
        """Get monthly emissions snapshots for the past N months."""
        config = self.get_config(site_id)
        ef = config.emission_factors
        sqm = config.site_sqm

        # Get energy data for the full period
        days = months * 30
        energy_data = self._get_energy_data(site_id, days=days)

        # Group by month
        monthly: dict[str, list[dict]] = {}
        for d in energy_data:
            month_key = d["date"][:7]  # YYYY-MM
            if month_key not in monthly:
                monthly[month_key] = []
            monthly[month_key].append(d)

        snapshots = []
        random.seed(123)  # Consistent diesel estimates
        for month_key in sorted(monthly.keys()):
            month_data = monthly[month_key]
            grid_kwh = sum(d["total_kwh"] for d in month_data)

            # Try real diesel data first, fall back to seasonal estimate
            diesel_litres, diesel_source = self._get_diesel_data(site_id, month_key)
            if diesel_source == "estimated":
                # Apply seasonal variation for estimated data
                month_num = int(month_key.split("-")[1])
                seasonal_factor = 1.0
                if month_num in (6, 7, 8):
                    seasonal_factor = 1.5  # Winter peak
                elif month_num in (12, 1, 2):
                    seasonal_factor = 1.3  # Summer peak
                diesel_litres = diesel_litres * seasonal_factor * random.uniform(0.8, 1.2)

            # Try real water data first
            water_kl, water_source = self._get_water_data(site_id, month_key)

            # Determine data source
            data_source = "estimated"
            if diesel_source == "measured" and water_source == "measured":
                data_source = "measured"
            elif diesel_source != "estimated" or water_source != "estimated":
                data_source = "simulation"

            scope1 = diesel_litres * ef.diesel_kg_co2_per_litre
            scope2 = grid_kwh * ef.grid_kg_co2_per_kwh

            # Check for solar data in daily metrics
            daily_metrics = self._get_daily_metrics(site_id, f"{month_key}-01", f"{month_key}-28")
            solar_kwh = sum(float(m.get("solar_generation_kwh", 0)) for m in daily_metrics)
            solar_offset_kg = solar_kwh * ef.grid_kg_co2_per_kwh
            net_scope2 = max(0, scope2 - solar_offset_kg)

            # Scope 3
            water_co2 = water_kl * ef.water_kg_co2_per_kl
            waste_co2 = config.monthly_waste_tons * ef.waste_kg_co2_per_ton
            avg_employees = config.occupancy_capacity * (config.avg_occupancy_pct / 100.0)
            commute_co2 = avg_employees * config.working_days_per_month * ef.commute_kg_co2_per_person_day
            scope3 = water_co2 + waste_co2 + commute_co2

            hvac_kwh = sum(d["hvac_kwh"] for d in month_data)
            lighting_kwh = sum(d["lighting_kwh"] for d in month_data)
            other_kwh = sum(d["other_kwh"] for d in month_data)

            hvac_co2 = hvac_kwh * ef.grid_kg_co2_per_kwh
            lighting_co2 = lighting_kwh * ef.grid_kg_co2_per_kwh
            other_co2 = other_kwh * ef.grid_kg_co2_per_kwh

            breakdown = {
                "hvac": round(hvac_co2, 2),
                "lighting": round(lighting_co2, 2),
                "other_electrical": round(other_co2, 2),
                "diesel_generators": round(scope1, 2),
                "water": round(water_co2, 2),
                "waste": round(waste_co2, 2),
                "commuting": round(commute_co2, 2),
            }

            total_co2 = scope1 + scope2 + scope3
            snapshots.append(
                EmissionsSnapshot(
                    month=month_key,
                    site_id=site_id,
                    scope1_kg_co2=scope1,
                    scope2_kg_co2=scope2,
                    scope3_kg_co2=scope3,
                    grid_kwh=grid_kwh,
                    diesel_litres=diesel_litres,
                    carbon_intensity_kg_per_sqm=total_co2 / sqm if sqm else 0,
                    energy_intensity_kwh_per_sqm=grid_kwh / sqm if sqm else 0,
                    breakdown_by_system=breakdown,
                    hvac_kg_co2=hvac_co2,
                    lighting_kg_co2=lighting_co2,
                    other_kg_co2=other_co2,
                    solar_offset_kg_co2=solar_offset_kg,
                    net_scope2_kg_co2=net_scope2,
                    actual_diesel_liters=diesel_litres if diesel_source == "measured" else None,
                    actual_water_kl=water_kl if water_source == "measured" else None,
                    solar_generation_kwh=solar_kwh if solar_kwh > 0 else None,
                    data_source=data_source,
                )
            )

        return snapshots

    def get_efficiency_metrics(self, site_id: str) -> dict:
        """Calculate efficiency metrics with benchmark comparison."""
        config = self.get_config(site_id)
        sqm = config.site_sqm

        # Get 12-month data
        history = self.get_emissions_history(site_id, months=12)
        if not history:
            return {"error": "No data available"}

        total_kwh_year = sum(s.grid_kwh for s in history)
        total_co2_year = sum(s.total_kg_co2 for s in history)

        # Guard against zero sqm and infinity
        if sqm and sqm > 0:
            energy_intensity = total_kwh_year / sqm
            if math.isinf(energy_intensity) or math.isnan(energy_intensity):
                energy_intensity = None
        else:
            energy_intensity = None

        if sqm and sqm > 0:
            carbon_intensity = total_co2_year / sqm
            if math.isinf(carbon_intensity) or math.isnan(carbon_intensity):
                carbon_intensity = None
        else:
            carbon_intensity = None

        bm = self._benchmarks
        return {
            "site_id": site_id,
            "period": "12 months",
            "site_sqm": sqm,
            "energy_intensity_kwh_per_sqm_yr": round(energy_intensity, 1) if energy_intensity is not None else None,
            "carbon_intensity_kg_per_sqm_yr": round(carbon_intensity, 1) if carbon_intensity is not None else None,
            "total_kwh_year": round(total_kwh_year, 0),
            "total_co2_tonnes_year": round(total_co2_year / 1000, 2),
            "benchmarks": {
                "energy_typical": bm.energy_typical_kwh_per_sqm_yr,
                "energy_efficient": bm.energy_efficient_kwh_per_sqm_yr,
                "carbon_typical": bm.carbon_typical_kg_per_sqm_yr,
                "carbon_efficient": bm.carbon_efficient_kg_per_sqm_yr,
            },
            "vs_typical": {
                "energy_pct": round(
                    ((energy_intensity - bm.energy_typical_kwh_per_sqm_yr) / bm.energy_typical_kwh_per_sqm_yr) * 100, 1
                )
                if energy_intensity is not None
                else None,
                "carbon_pct": round(
                    ((carbon_intensity - bm.carbon_typical_kg_per_sqm_yr) / bm.carbon_typical_kg_per_sqm_yr) * 100, 1
                )
                if carbon_intensity is not None
                else None,
            },
            "vs_efficient": {
                "energy_pct": round(
                    ((energy_intensity - bm.energy_efficient_kwh_per_sqm_yr) / bm.energy_efficient_kwh_per_sqm_yr)
                    * 100,
                    1,
                )
                if energy_intensity is not None
                else None,
                "carbon_pct": round(
                    ((carbon_intensity - bm.carbon_efficient_kg_per_sqm_yr) / bm.carbon_efficient_kg_per_sqm_yr) * 100,
                    1,
                )
                if carbon_intensity is not None
                else None,
            },
        }

    def get_green_star_assessment(self, site_id: str) -> GreenStarAssessment:
        """Load Green Star self-assessment."""
        if site_id in self._assessments:
            return self._assessments[site_id]

        assessment_path = DATA_DIR / f"{site_id}_assessment.json"
        if assessment_path.exists():
            with open(assessment_path) as f:
                data = json.load(f)
            assessment = GreenStarAssessment.from_dict(data)
        else:
            # Return empty assessment with default categories
            categories_path = DATA_DIR / "green_star_categories.json"
            categories = []
            if categories_path.exists():
                with open(categories_path) as f:
                    cat_data = json.load(f)
                for c in cat_data.get("categories", []):
                    categories.append(
                        GreenStarCategory(
                            category_id=c["category_id"],
                            name=c["name"],
                            max_points=c["max_points"],
                        )
                    )
            assessment = GreenStarAssessment(site_id=site_id, categories=categories)

        self._assessments[site_id] = assessment
        return assessment

    def update_green_star_score(
        self, site_id: str, category_id: str, points: int, notes: str | None = None
    ) -> GreenStarAssessment:
        """Update a Green Star category score."""
        assessment = self.get_green_star_assessment(site_id)

        for cat in assessment.categories:
            if cat.category_id == category_id:
                if points > cat.max_points:
                    raise ValueError(f"Points ({points}) exceed max ({cat.max_points}) for {category_id}")
                cat.achieved_points = points
                if notes is not None:
                    cat.notes = notes
                break
        else:
            raise ValueError(f"Unknown category: {category_id}")

        self._assessments[site_id] = assessment
        self._save_assessment(assessment)
        return assessment

    def _save_assessment(self, assessment: GreenStarAssessment):
        """Persist assessment to JSON."""
        path = DATA_DIR / f"{assessment.site_id}_assessment.json"
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(assessment.to_dict(), f, indent=2)

    def get_summary(self, site_id: str) -> dict:
        """Dashboard-ready summary: current month, YTD, trend, targets."""
        current = self.calculate_current_emissions(site_id)
        history = self.get_emissions_history(site_id, months=12)
        assessment = self.get_green_star_assessment(site_id)
        config = self.get_config(site_id)

        # YTD totals
        current_year = datetime.now().strftime("%Y")
        ytd_snapshots = [s for s in history if s.month.startswith(current_year)]
        ytd_co2_kg = sum(s.total_kg_co2 for s in ytd_snapshots) + current.total_kg_co2
        ytd_kwh = sum(s.grid_kwh for s in ytd_snapshots) + current.grid_kwh

        # Trend: compare last 3 months average vs previous 3 months
        trend = "stable"
        if len(history) >= 6:
            recent_3 = sum(s.total_kg_co2 for s in history[-3:]) / 3
            prev_3 = sum(s.total_kg_co2 for s in history[-6:-3]) / 3
            if prev_3 > 0:
                change_pct = ((recent_3 - prev_3) / prev_3) * 100
                if change_pct < -3:
                    trend = "improving"
                elif change_pct > 3:
                    trend = "worsening"

        return {
            "site_id": site_id,
            "current_month": current.to_dict(),
            "ytd": {
                "total_co2_kg": round(ytd_co2_kg, 2),
                "total_co2_tonnes": round(ytd_co2_kg / 1000, 2),
                "total_kwh": round(ytd_kwh, 0),
            },
            "trend": trend,
            "target_reduction_pct": config.target_reduction_pct,
            "green_star": {
                "total_achieved": assessment.total_achieved,
                "total_max": assessment.total_max,
                "estimated_rating": assessment.estimated_star_rating,
                "target_rating": assessment.target_rating,
            },
            "carbon_intensity_kg_per_sqm": current.carbon_intensity_kg_per_sqm,
            "energy_intensity_kwh_per_sqm": current.energy_intensity_kwh_per_sqm,
        }


# Singleton instance
sustainability_service = SustainabilityService()
