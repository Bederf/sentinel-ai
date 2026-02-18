"""
Energy Cost Calculation Service

Calculates energy costs from simulated HVAC power consumption using
location-based municipal tariffs (City Power TOU for Site 002).

Integrates with:
- thermal_simulation_engine: Power consumption data (kW)
- tariff_schedule_service: Tariff rates (c/kWh, R/kVA)
- energy_consumption_history: Hourly energy records
"""

import logging
from datetime import datetime, date, timedelta
from typing import Dict, Any, Optional, List
from dataclasses import dataclass

from app.database.supabase_client import get_supabase_client
from app.services.tariff_schedule_service import TariffScheduleService

logger = logging.getLogger(__name__)


@dataclass
class TariffBand:
    """Time-of-use tariff band details."""
    band: str  # "peak", "standard", "off_peak"
    energy_rate_c_kwh: float  # c/kWh
    network_rate_c_kwh: float  # c/kWh

    @property
    def total_rate_c_kwh(self) -> float:
        """Total rate including both energy and network."""
        return self.energy_rate_c_kwh + self.network_rate_c_kwh

    @property
    def total_rate_r_kwh(self) -> float:
        """Convert to ZAR/kWh."""
        return self.total_rate_c_kwh / 100.0


@dataclass
class HourlyCost:
    """Cost breakdown for one simulated hour."""
    simulated_hour: int
    power_kw: float
    energy_kwh: float  # 1 hour
    tariff_band: str
    rate_r_kwh: float
    energy_cost_r: float
    network_cost_r: float
    total_cost_r: float


class EnergyCostService:
    """Calculate energy costs from simulated power consumption."""

    def __init__(self, building_id: str = "site-002", municipality: str = "City Power Johannesburg"):
        self.building_id = building_id
        self.municipality = municipality
        self.supabase = get_supabase_client()
        self.tariff_svc = TariffScheduleService()

        # Cache tariff data
        self.tariff_data = self._load_tariff()
        self.demand_charge_r_kva = self._get_demand_charge()
        self.service_charge_r_month = self._get_service_charge()

    def _load_tariff(self) -> Optional[Dict[str, Any]]:
        """Load tariff schedule for municipality."""
        try:
            tariff = self.tariff_svc.get_tariff(
                municipality=self.municipality,
                tariff_name="TOU Commercial - Large Power User",
                effective_date=date.today()
            )
            if tariff:
                return tariff.tariff_data
        except Exception as e:
            logger.warning(f"[COST] Failed to load tariff: {e}")

        # Fallback to hardcoded rates (City Power 2026)
        return {
            "energy_charge_c_kwh": {
                "summer": {"peak": 345.67, "standard": 187.23, "off_peak": 112.45},
                "winter": {"peak": 489.12, "standard": 215.89, "off_peak": 134.67}
            },
            "network_charge_c_kwh": {
                "summer": {"peak": 45.12, "standard": 28.67, "off_peak": 15.23},
                "winter": {"peak": 52.34, "standard": 33.12, "off_peak": 18.45}
            },
            "demand_charge_r_kva": {"summer": 189.45, "winter": 267.89},
            "service_charge_r_month": 8456.78,
        }

    def _get_demand_charge(self) -> Dict[str, float]:
        """Get demand charge by season (R/kVA)."""
        if not self.tariff_data:
            return {"summer": 189.45, "winter": 267.89}
        return self.tariff_data.get("demand_charge_r_kva", {"summer": 189.45, "winter": 267.89})

    def _get_service_charge(self) -> float:
        """Get monthly service charge (R)."""
        if not self.tariff_data:
            return 8456.78
        return self.tariff_data.get("service_charge_r_month", 8456.78)

    def get_tariff_band(self, hour: int, simulated_date: datetime) -> str:
        """
        Determine tariff band (peak/standard/off_peak) for given hour.

        Varies by:
        - Time of day
        - Season (summer/winter)
        - Day type (weekday/weekend - simplified, assumes all weekdays)
        """
        if not self.tariff_data:
            return self._simple_tariff_band(hour)

        try:
            # Determine season
            month = simulated_date.month
            season = "winter" if month in [6, 7, 8] else "summer"

            # Get time band definitions
            time_bands = self.tariff_data.get("time_bands", {}).get(season, {})

            # Check which band this hour falls into
            time_str = f"{hour:02d}:00"

            for band_name in ["peak", "standard", "off_peak"]:
                bands = time_bands.get(band_name, [])
                for band_range in bands:
                    start = band_range.get("start")
                    end = band_range.get("end")

                    # Simple check (handles cases where end < start is wrapping to next day)
                    if start <= time_str < end or (end < start and (time_str >= start or time_str < end)):
                        return band_name

            return "standard"  # Default fallback
        except Exception as e:
            logger.warning(f"[COST] Error determining tariff band: {e}")
            return self._simple_tariff_band(hour)

    def _simple_tariff_band(self, hour: int) -> str:
        """Simple tariff band lookup (City Power standard summer)."""
        if 7 <= hour < 10 or 18 <= hour < 20:
            return "peak"
        elif 6 <= hour < 22:
            return "standard"
        else:
            return "off_peak"

    def get_hourly_rate(self, hour: int, simulated_date: datetime) -> TariffBand:
        """
        Get energy and network rates for a given hour.

        Returns: TariffBand with energy_rate_c_kwh and network_rate_c_kwh
        """
        if not self.tariff_data:
            return self._get_simple_rate()

        try:
            month = simulated_date.month
            season = "winter" if month in [6, 7, 8] else "summer"
            band = self.get_tariff_band(hour, simulated_date)

            energy_rates = self.tariff_data.get("energy_charge_c_kwh", {}).get(season, {})
            network_rates = self.tariff_data.get("network_charge_c_kwh", {}).get(season, {})

            energy_rate = energy_rates.get(band, 200.0)
            network_rate = network_rates.get(band, 30.0)

            return TariffBand(
                band=band,
                energy_rate_c_kwh=energy_rate,
                network_rate_c_kwh=network_rate
            )
        except Exception as e:
            logger.warning(f"[COST] Error getting hourly rate: {e}")
            return self._get_simple_rate()

    def _get_simple_rate(self) -> TariffBand:
        """Fallback simple rate (City Power 2026 average)."""
        return TariffBand(
            band="standard",
            energy_rate_c_kwh=200.0,
            network_rate_c_kwh=30.0
        )

    def calculate_hourly_cost(
        self,
        simulated_hour: int,
        power_kw: float,
        simulated_date: datetime,
    ) -> HourlyCost:
        """
        Calculate cost for 1 simulated hour.

        Args:
            simulated_hour: Hour of day (0-23)
            power_kw: HVAC power consumption (kW)
            simulated_date: Date for season determination

        Returns:
            HourlyCost with breakdown
        """
        # 1 hour of consumption = power_kw kWh
        energy_kwh = power_kw

        # Get tariff rate for this hour
        tariff_band = self.get_hourly_rate(simulated_hour, simulated_date)

        # Calculate costs
        energy_cost_r = (power_kw * tariff_band.energy_rate_c_kwh) / 100.0
        network_cost_r = (power_kw * tariff_band.network_rate_c_kwh) / 100.0
        total_cost_r = energy_cost_r + network_cost_r

        return HourlyCost(
            simulated_hour=simulated_hour,
            power_kw=power_kw,
            energy_kwh=energy_kwh,
            tariff_band=tariff_band.band,
            rate_r_kwh=tariff_band.total_rate_r_kwh,
            energy_cost_r=round(energy_cost_r, 2),
            network_cost_r=round(network_cost_r, 2),
            total_cost_r=round(total_cost_r, 2),
        )

    async def calculate_daily_cost(
        self,
        simulated_date: datetime,
        hourly_power_data: Dict[int, float],  # {hour: power_kw}
    ) -> Dict[str, Any]:
        """
        Calculate total cost for a simulated day.

        Args:
            simulated_date: Date of simulation
            hourly_power_data: Power consumption per hour {0-23: kW}

        Returns:
            Daily cost summary
        """
        hourly_costs = []
        total_energy_kwh = 0.0
        total_energy_cost_r = 0.0
        total_network_cost_r = 0.0
        total_cost_r = 0.0

        # Calculate cost for each hour
        for hour in range(24):
            power_kw = hourly_power_data.get(hour, 0.0)

            hourly_cost = self.calculate_hourly_cost(
                simulated_hour=hour,
                power_kw=power_kw,
                simulated_date=simulated_date
            )

            hourly_costs.append({
                "hour": hour,
                "power_kw": round(power_kw, 2),
                "energy_kwh": round(hourly_cost.energy_kwh, 2),
                "tariff_band": hourly_cost.tariff_band,
                "rate_r_kwh": round(hourly_cost.rate_r_kwh, 3),
                "energy_cost_r": hourly_cost.energy_cost_r,
                "network_cost_r": hourly_cost.network_cost_r,
                "total_cost_r": hourly_cost.total_cost_r,
            })

            total_energy_kwh += hourly_cost.energy_kwh
            total_energy_cost_r += hourly_cost.energy_cost_r
            total_network_cost_r += hourly_cost.network_cost_r
            total_cost_r += hourly_cost.total_cost_r

        # Add fixed monthly charges (amortized daily)
        daily_service_charge = self.service_charge_r_month / 30.0

        # Get peak demand for the day (used for demand charge if applicable)
        peak_power_kw = max(hourly_power_data.values()) if hourly_power_data else 0.0

        return {
            "date": simulated_date.isoformat(),
            "total_energy_kwh": round(total_energy_kwh, 2),
            "total_energy_cost_r": round(total_energy_cost_r, 2),
            "total_network_cost_r": round(total_network_cost_r, 2),
            "daily_service_charge_r": round(daily_service_charge, 2),
            "peak_power_kw": round(peak_power_kw, 2),
            "total_cost_r": round(total_cost_r + daily_service_charge, 2),
            "average_rate_r_kwh": round((total_cost_r / max(total_energy_kwh, 1)) if total_energy_kwh > 0 else 0, 3),
            "hourly_breakdown": hourly_costs,
        }

    async def write_daily_cost_summary(
        self,
        simulated_date: datetime,
        daily_cost: Dict[str, Any],
    ) -> bool:
        """
        Write daily cost summary to database for dashboard.

        Creates records in energy_cost_summary table for tracking
        and dashboard visualization.
        """
        try:
            record = {
                "building_id": self.building_id,
                "date": simulated_date.isoformat()[:10],  # YYYY-MM-DD
                "simulated_date": simulated_date.isoformat(),
                "total_energy_kwh": daily_cost["total_energy_kwh"],
                "total_cost_r": daily_cost["total_cost_r"],
                "energy_cost_r": daily_cost["total_energy_cost_r"],
                "network_cost_r": daily_cost["total_network_cost_r"],
                "service_charge_r": daily_cost["daily_service_charge_r"],
                "peak_power_kw": daily_cost["peak_power_kw"],
                "average_rate_r_kwh": daily_cost["average_rate_r_kwh"],
                "hourly_data": daily_cost.get("hourly_breakdown"),
                "timestamp": datetime.utcnow().isoformat() + "Z",
            }

            # Upsert into energy_cost_summary table
            self.supabase.table("energy_cost_summary").upsert(
                record,
                on_conflict="building_id,date"
            ).execute()

            logger.debug(
                f"[COST] Daily cost recorded for {simulated_date.date()}: "
                f"{daily_cost['total_energy_kwh']:.1f}kWh = R{daily_cost['total_cost_r']:.2f}"
            )

            return True
        except Exception as e:
            logger.error(f"[COST] Failed to write daily cost summary: {e}")
            return False

    async def get_monthly_summary(
        self,
        building_id: str,
        year: int,
        month: int,
    ) -> Dict[str, Any]:
        """
        Get monthly cost summary from daily records.

        Aggregates daily_cost_summary records into monthly view.
        """
        try:
            # Query energy_cost_summary for the month
            response = self.supabase.table("energy_cost_summary").select("*").eq(
                "building_id", building_id
            ).execute()

            if not response.data:
                return {"days": 0, "total_energy_kwh": 0, "total_cost_r": 0}

            # Filter by year/month and sum
            total_energy = 0.0
            total_cost = 0.0
            day_count = 0

            for record in response.data:
                record_date = datetime.fromisoformat(record.get("simulated_date", "")).date()
                if record_date.year == year and record_date.month == month:
                    total_energy += record.get("total_energy_kwh", 0)
                    total_cost += record.get("total_cost_r", 0)
                    day_count += 1

            return {
                "year": year,
                "month": month,
                "days_recorded": day_count,
                "total_energy_kwh": round(total_energy, 2),
                "total_cost_r": round(total_cost, 2),
                "average_daily_cost_r": round(total_cost / max(day_count, 1), 2),
                "average_daily_energy_kwh": round(total_energy / max(day_count, 1), 2),
            }
        except Exception as e:
            logger.error(f"[COST] Failed to get monthly summary: {e}")
            return {}
