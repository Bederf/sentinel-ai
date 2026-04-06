"""
Carbon Calculator Service - Scope 1/2/3 Emissions Tracking

Calculates greenhouse gas emissions from building operations using:
- Scope 1: Direct emissions (generators, refrigerant leaks, company vehicles)
- Scope 2: Purchased electricity (grid consumption)
- Scope 3: Indirect/value chain (water, waste, employee commute, business travel)

Emission factors are configured per South African context:
- Diesel: 2.68 kg CO2/L (EPA GHG Inventory)
- Grid electricity: 0.95 kg CO2/kWh (Eskom 2025 average)
- Water: 0.45 kg CO2/m³ (treatment + distribution)
- Waste: 0.5 kg CO2/kg (landfill + methane)
- Car commute: 0.21 kg CO2/km (EPA Mobile6.2, South Africa)
"""

import logging
from datetime import date

from app.database.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)


class CarbonCalculator:
    """Calculate building carbon emissions (Scope 1/2/3) from raw consumption data."""

    # Emission factors in kg CO2e per unit (South Africa baseline)
    EMISSION_FACTORS = {
        "generator_diesel": {"factor": 2.68, "unit": "L", "scope": 1},
        "generator_lpg": {"factor": 1.63, "unit": "kg", "scope": 1},
        "grid_electricity": {"factor": 0.95, "unit": "kWh", "scope": 2},
        "water_supply": {"factor": 0.45, "unit": "m3", "scope": 3},
        "waste_landfill": {"factor": 0.5, "unit": "kg", "scope": 3},
        "employee_commute": {"factor": 0.21, "unit": "km", "scope": 3},
        "business_travel": {"factor": 0.12, "unit": "km", "scope": 3},
    }

    def __init__(self):
        """Initialize calculator with emission factors."""
        self.supabase = get_supabase_client()
        self._logger = logging.getLogger(__name__)

    def calculate_scope_1(
        self,
        site_id: str,
        period_start: date,
        period_end: date,
    ) -> tuple[float, dict]:
        """
        Calculate Scope 1 (direct) emissions for a building.

        Sources:
        - Diesel generator fuel consumption
        - LPG fuel consumption
        - Refrigerant leaks
        - Company vehicle fuel

        Args:
            site_id: UUID of building
            period_start: Start date for calculation period
            period_end: End date for calculation period

        Returns:
            Tuple of (total_kg_co2e, breakdown_dict with per-source emissions)
        """
        try:
            # Query emissions_sources table for Scope 1 data
            response = (
                self.supabase.table("emissions_sources")
                .select("source_type,monthly_value,unit,co2_factor,co2e_kg")
                .eq("site_id", site_id)
                .eq("scope", 1)
                .gte("measurement_date", period_start.isoformat())
                .lte("measurement_date", period_end.isoformat())
                .execute()
            )

            if not response.data:
                self._logger.warning(
                    f"No Scope 1 emissions data found for {site_id} in period {period_start} to {period_end}"
                )
                return 0.0, {}

            breakdown = {}
            total_kg_co2e = 0.0

            for row in response.data:
                source = row["source_type"]
                co2e = row.get("co2e_kg", 0)
                total_kg_co2e += co2e

                if source not in breakdown:
                    breakdown[source] = 0.0
                breakdown[source] += co2e

            self._logger.info(
                f"Scope 1 calculation for {site_id}: {total_kg_co2e:.2f} kg CO2e (sources: {list(breakdown.keys())})"
            )
            return total_kg_co2e, breakdown

        except Exception as e:
            self._logger.error(f"Error calculating Scope 1 emissions: {e}")
            return 0.0, {}

    def calculate_scope_2(
        self,
        site_id: str,
        period_start: date,
        period_end: date,
    ) -> tuple[float, dict]:
        """
        Calculate Scope 2 (purchased electricity) emissions.

        Sources:
        - Grid electricity consumption (kWh × 0.95 kg CO2/kWh for South Africa)
        - Renewable energy offset (if available from Phase 34 Solar module)

        Args:
            site_id: UUID of building
            period_start: Start date for calculation period
            period_end: End date for calculation period

        Returns:
            Tuple of (total_kg_co2e, breakdown_dict with grid vs renewable)
        """
        try:
            # Query Scope 2 (grid electricity)
            response = (
                self.supabase.table("emissions_sources")
                .select("source_type,monthly_value,unit,co2_factor,co2e_kg")
                .eq("site_id", site_id)
                .eq("scope", 2)
                .gte("measurement_date", period_start.isoformat())
                .lte("measurement_date", period_end.isoformat())
                .execute()
            )

            if not response.data:
                self._logger.warning(
                    f"No Scope 2 emissions data found for {site_id} in period {period_start} to {period_end}"
                )
                return 0.0, {}

            breakdown = {}
            total_kg_co2e = 0.0

            for row in response.data:
                source = row["source_type"]
                co2e = row.get("co2e_kg", 0)
                total_kg_co2e += co2e

                if source not in breakdown:
                    breakdown[source] = 0.0
                breakdown[source] += co2e

            # Solar offset — query daily_sustainability_metrics for generation
            solar_kwh = 0.0
            try:
                solar_result = (
                    self.supabase.table("daily_sustainability_metrics")
                    .select("solar_generation_kwh")
                    .eq("site_id", site_id)
                    .gte("date", period_start.isoformat())
                    .lte("date", period_end.isoformat())
                    .execute()
                )
                if solar_result.data:
                    solar_kwh = sum(float(r.get("solar_generation_kwh", 0) or 0) for r in solar_result.data)
            except Exception as solar_err:
                self._logger.debug(f"No solar data available: {solar_err}")

            if solar_kwh > 0:
                grid_factor = self.EMISSION_FACTORS["grid_electricity"]["factor"]
                solar_offset_kg = solar_kwh * grid_factor
                breakdown["solar_offset_kg_co2e"] = -round(solar_offset_kg, 2)
                total_kg_co2e = max(0, total_kg_co2e - solar_offset_kg)
                breakdown["net_grid_kg_co2e"] = round(total_kg_co2e, 2)

            self._logger.info(
                f"Scope 2 calculation for {site_id}: {total_kg_co2e:.2f} kg CO2e"
                f"{f' (solar offset: {solar_kwh:.1f} kWh)' if solar_kwh > 0 else ''}"
            )
            return total_kg_co2e, breakdown

        except Exception as e:
            self._logger.error(f"Error calculating Scope 2 emissions: {e}")
            return 0.0, {}

    def calculate_scope_3(
        self,
        site_id: str,
        period_start: date,
        period_end: date,
    ) -> tuple[float, dict]:
        """
        Calculate Scope 3 (indirect/value chain) emissions.

        Sources:
        - Water supply & treatment: m³ × 0.45 kg CO2/m³
        - Waste to landfill: kg × 0.5 kg CO2/kg
        - Employee commute: occupants × km × 0.21 kg CO2/km
        - Business travel: distance × 0.12 kg CO2/km

        Args:
            site_id: UUID of building
            period_start: Start date for calculation period
            period_end: End date for calculation period

        Returns:
            Tuple of (total_kg_co2e, breakdown_dict with per-source emissions)
        """
        try:
            # Query Scope 3 emissions
            response = (
                self.supabase.table("emissions_sources")
                .select("source_type,monthly_value,unit,co2_factor,co2e_kg")
                .eq("site_id", site_id)
                .eq("scope", 3)
                .gte("measurement_date", period_start.isoformat())
                .lte("measurement_date", period_end.isoformat())
                .execute()
            )

            if not response.data:
                self._logger.warning(
                    f"No Scope 3 emissions data found for {site_id} in period {period_start} to {period_end}"
                )
                # Return estimate based on occupancy if available
                return self._estimate_scope_3(site_id, period_start, period_end)

            breakdown = {}
            total_kg_co2e = 0.0

            for row in response.data:
                source = row["source_type"]
                co2e = row.get("co2e_kg", 0)
                total_kg_co2e += co2e

                if source not in breakdown:
                    breakdown[source] = 0.0
                breakdown[source] += co2e

            self._logger.info(f"Scope 3 calculation for {site_id}: {total_kg_co2e:.2f} kg CO2e")
            return total_kg_co2e, breakdown

        except Exception as e:
            self._logger.error(f"Error calculating Scope 3 emissions: {e}")
            return 0.0, {}

    def _estimate_scope_3(
        self,
        site_id: str,
        period_start: date,
        period_end: date,
    ) -> tuple[float, dict]:
        """
        Estimate Scope 3 emissions if measured data unavailable.

        Uses building occupancy capacity to estimate commute-based emissions.
        """
        try:
            # Get building info (occupancy, floor area)
            response = (
                self.supabase.table("sites").select("occupancy_capacity,floor_area_m2").eq("id", site_id).execute()
            )

            if not response.data:
                return 0.0, {}

            building = response.data[0]
            occupancy = building.get("occupancy_capacity", 100)

            # Estimate commute: occupancy × 25 km avg daily commute × 0.21 kg CO2/km
            num_months = (period_end - period_start).days / 30.0
            num_days = num_months * 20  # 20 working days/month
            estimated_commute_co2e = occupancy * 25 * 0.21 * num_days

            breakdown = {
                "employee_commute": estimated_commute_co2e,
                "data_quality": "estimated",
            }

            self._logger.info(
                f"Estimated Scope 3 for {site_id}: {estimated_commute_co2e:.2f} kg CO2e "
                f"(based on occupancy {occupancy})"
            )
            return estimated_commute_co2e, breakdown

        except Exception as e:
            self._logger.error(f"Error estimating Scope 3 emissions: {e}")
            return 0.0, {}

    def calculate_total_emissions(
        self,
        site_id: str,
        period_start: date,
        period_end: date,
    ) -> dict:
        """
        Calculate total emissions (Scope 1 + 2 + 3) for a building.

        Args:
            site_id: UUID of building
            period_start: Start date for calculation period
            period_end: End date for calculation period

        Returns:
            Dict with scope1_kg_co2e, scope2_kg_co2e, scope3_kg_co2e, total_kg_co2e, breakdown
        """
        scope1, breakdown1 = self.calculate_scope_1(site_id, period_start, period_end)
        scope2, breakdown2 = self.calculate_scope_2(site_id, period_start, period_end)
        scope3, breakdown3 = self.calculate_scope_3(site_id, period_start, period_end)

        return {
            "scope1_kg_co2e": round(scope1, 2),
            "scope2_kg_co2e": round(scope2, 2),
            "scope3_kg_co2e": round(scope3, 2),
            "total_kg_co2e": round(scope1 + scope2 + scope3, 2),
            "breakdown": {
                "scope1": breakdown1,
                "scope2": breakdown2,
                "scope3": breakdown3,
            },
        }

    def calculate_carbon_intensity(
        self,
        site_id: str,
        period_start: date,
        period_end: date,
    ) -> dict:
        """
        Calculate carbon intensity (kg CO2e per m² per month).

        Used for benchmarking: SA office average is 0.15 kg/m²/day.

        Args:
            site_id: UUID of building
            period_start: Start date for calculation period
            period_end: End date for calculation period

        Returns:
            Dict with intensity, comparison to SA benchmark, and baseline comparison
        """
        try:
            # Get emissions total
            emissions = self.calculate_total_emissions(site_id, period_start, period_end)
            total_co2e = emissions["total_kg_co2e"]

            # Get building floor area
            response = self.supabase.table("sites").select("floor_area_m2,code").eq("id", site_id).execute()

            if not response.data:
                self._logger.error(f"Building {site_id} not found")
                return {}

            building = response.data[0]
            floor_area = building.get("floor_area_m2", 1000)  # Default 1000 m² if missing
            site_code = building.get("code")

            if floor_area <= 0:
                floor_area = 1000

            # Calculate intensity
            num_days = (period_end - period_start).days + 1
            intensity_kg_per_m2_per_day = round(total_co2e / floor_area / num_days, 4)
            intensity_kg_per_m2_per_month = round(total_co2e / floor_area / (num_days / 30), 4)

            # SA benchmark: 0.15 kg/m²/day for office buildings
            sa_benchmark_kg_per_m2_per_day = 0.15
            benchmark_ratio = round(intensity_kg_per_m2_per_day / sa_benchmark_kg_per_m2_per_day, 2)

            result = {
                "site_id": site_id,
                "site_code": site_code,
                "period_start": period_start.isoformat(),
                "period_end": period_end.isoformat(),
                "total_emissions_kg_co2e": total_co2e,
                "floor_area_m2": floor_area,
                "intensity_kg_per_m2_per_day": intensity_kg_per_m2_per_day,
                "intensity_kg_per_m2_per_month": intensity_kg_per_m2_per_month,
                "sa_benchmark_kg_per_m2_per_day": sa_benchmark_kg_per_m2_per_day,
                "benchmark_ratio": benchmark_ratio,
                "above_benchmark_pct": round((benchmark_ratio - 1) * 100, 1) if benchmark_ratio > 1 else 0,
                "rating": "excellent"
                if intensity_kg_per_m2_per_day < 0.10
                else "good"
                if intensity_kg_per_m2_per_day < 0.15
                else "average"
                if intensity_kg_per_m2_per_day < 0.25
                else "above_target",
            }

            self._logger.info(
                f"Carbon intensity for {site_code}: {intensity_kg_per_m2_per_day} kg/m²/day "
                f"({result['rating']} vs SA benchmark {sa_benchmark_kg_per_m2_per_day})"
            )
            return result

        except Exception as e:
            self._logger.error(f"Error calculating carbon intensity: {e}")
            return {}

    def calculate_emissions_baseline(
        self,
        site_id: str,
        year: int,
    ) -> dict:
        """
        Calculate annual emissions baseline and store in database.

        Used for year-over-year benchmarking and carbon reduction tracking.

        Args:
            site_id: UUID of building
            year: Year for baseline calculation

        Returns:
            Dict with annual totals by scope and intensity
        """
        try:
            # Calculate for full year
            period_start = date(year, 1, 1)
            period_end = date(year, 12, 31)

            emissions = self.calculate_total_emissions(site_id, period_start, period_end)

            # Get building floor area
            response = self.supabase.table("sites").select("floor_area_m2").eq("id", site_id).execute()

            floor_area = response.data[0]["floor_area_m2"] if response.data else 1000

            # Update emissions_baseline table
            baseline = {
                "site_id": site_id,
                "baseline_year": year,
                "scope1_kg_co2e": emissions["scope1_kg_co2e"],
                "scope2_kg_co2e": emissions["scope2_kg_co2e"],
                "scope3_kg_co2e": emissions["scope3_kg_co2e"],
                "floor_area_m2": floor_area,
            }

            # Upsert to database
            self.supabase.table("emissions_baseline").upsert(
                baseline,
                on_conflict="site_id,baseline_year",
            ).execute()

            self._logger.info(
                f"Baseline calculated for {site_id} year {year}: "
                f"S1={baseline['scope1_kg_co2e']} S2={baseline['scope2_kg_co2e']} "
                f"S3={baseline['scope3_kg_co2e']} Total={emissions['total_kg_co2e']}"
            )

            return baseline

        except Exception as e:
            self._logger.error(f"Error calculating baseline: {e}")
            return {}

    def calculate_esg_score(
        self,
        site_id: str,
        period_start: date,
        period_end: date,
    ) -> dict:
        """
        Calculate ESG metrics and overall ESG score (0-100).

        Metrics weighted:
        - Carbon intensity score: 40%
        - Energy efficiency: 30%
        - Waste diversion: 20%
        - Water efficiency: 10%

        Args:
            site_id: UUID of building
            period_start: Start date
            period_end: End date

        Returns:
            Dict with individual scores and overall ESG score
        """
        try:
            # Get carbon intensity and convert to score (0-100)
            # Higher intensity = lower score
            intensity_data = self.calculate_carbon_intensity(site_id, period_start, period_end)

            if not intensity_data:
                return {}

            # Carbon score: 0.10 kg/m²/day = 100, 0.30+ = 0
            carbon_intensity = intensity_data["intensity_kg_per_m2_per_day"]
            carbon_score = max(0, min(100, 100 * (1 - (carbon_intensity / 0.30))))

            # Energy efficiency score (placeholder: correlates with carbon)
            energy_score = carbon_score * 0.95

            # Waste diversion score (placeholder: 70% default if no data)
            waste_score = 70.0

            # Water efficiency score (placeholder: 75% default if no data)
            water_score = 75.0

            # Overall ESG score (weighted average)
            overall_score = carbon_score * 0.40 + energy_score * 0.30 + waste_score * 0.20 + water_score * 0.10

            return {
                "carbon_intensity_score": round(carbon_score, 1),
                "energy_efficiency_score": round(energy_score, 1),
                "waste_diversion_score": waste_score,
                "water_efficiency_score": water_score,
                "overall_esg_score": round(overall_score, 1),
                "rating": "excellent"
                if overall_score >= 80
                else "good"
                if overall_score >= 60
                else "average"
                if overall_score >= 40
                else "needs_improvement",
            }

        except Exception as e:
            self._logger.error(f"Error calculating ESG score: {e}")
            return {}


# Singleton instance
_calculator = None


def get_carbon_calculator() -> CarbonCalculator:
    """Get singleton CarbonCalculator instance."""
    global _calculator
    if _calculator is None:
        _calculator = CarbonCalculator()
    return _calculator
