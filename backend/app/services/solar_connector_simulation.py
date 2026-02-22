"""Simulated solar connector — reads from solar_annual_simulations table.

This connector doesn't connect to physical hardware. Instead, it queries
the solar_annual_simulations table for the most recent simulation results
and extracts current-hour data to populate inverter/BESS/meter models.

Uses the same SeasonalModeler as the simulation engine to ensure weather
patterns match. Scales generation based on actual plant capacity.

This allows simulations to feed live data into the solar dashboard via the
normal ingestion service pipeline.
"""

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

from app.models.solar import (
    SolarInverter,
    SolarString,
    BESSContainer,
    BESSRack,
    GridMeter,
    NormalisedReading,
    ConnectorStatus,
    QualityFlag,
)
from app.services.solar_connector_base import SolarConnector
from app.services.seasonal_modeler import SeasonalModeler
from app.database.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)


class SimulatedSolarConnector(SolarConnector):
    """Connector that pulls data from solar_annual_simulations table.

    When a 365-day simulation is running or completed, this connector
    reads the cached results and converts them to live-like inverter/BESS data
    for the current hour.
    """

    def __init__(self, site_id: str, plant_capacity_kwp: float = 3.875):
        super().__init__(manufacturer="simulation", protocol="database")
        self.site_id = site_id
        self.plant_capacity_kwp = plant_capacity_kwp  # From site config (e.g., site-002 = 3.875 MWp)
        self._cache = {}
        self._cache_time = None
        self._cache_ttl_seconds = 30  # Refresh every 30 seconds
        self._seasonal_modeler = SeasonalModeler(seed=42)  # Same seed as simulation engine for consistency

    async def connect(self) -> bool:
        """Simulated connection — always succeeds."""
        self._status = ConnectorStatus(connected=True)
        logger.info(f"Simulated connector connected for {self.site_id}")
        return True

    async def disconnect(self) -> None:
        """Simulated disconnection."""
        self._status = ConnectorStatus(connected=False)
        logger.info(f"Simulated connector disconnected for {self.site_id}")

    async def read_inverter(self, inverter_id: str) -> Optional[SolarInverter]:
        """Read a single inverter from simulation data."""
        readings = await self.get_normalised_readings()

        # Find inverter readings for this inverter_id
        for reading in readings:
            if reading.source_id == inverter_id:
                # Convert to SolarInverter
                return SolarInverter(
                    inverter_id=inverter_id,
                    plant_id="plant-001",
                    manufacturer="simulation",
                    model="sim-v1",
                    status="online",
                    ac_power_kw=reading.value,
                    ac_voltage_v=400,
                    ac_current_a=reading.value / 0.4 if reading.value > 0 else 0,
                    ac_frequency_hz=50,
                    daily_yield_kwh=reading.value * 0.5,  # Rough estimate
                    temperature_c=25,
                    efficiency_pct=97.0,
                )

        return None

    async def read_all_strings(self, inverter_id: str) -> List[SolarString]:
        """Read all strings attached to an inverter from simulation."""
        # For simulation, return a fixed set of 4 strings
        strings = []
        for i in range(4):
            strings.append(
                SolarString(
                    string_id=f"{inverter_id}_s{i + 1}",
                    inverter_id=inverter_id,
                    voltage_v=500 + i * 10,
                    current_a=10 + i,
                    power_kw=5 + i * 0.5,
                    insulation_resistance_kohm=1000,
                )
            )
        return strings

    async def read_bess(self, container_id: str) -> Optional[BESSContainer]:
        """Read BESS container from simulation data."""
        # Refresh cache if needed
        sim_data = await self._get_simulation_data()
        if not sim_data:
            return None

        # Extract BESS SOC from simulation
        current_hour_data = self._get_current_hour_data(sim_data)
        if not current_hour_data:
            return None

        bess_soc_pct = current_hour_data.get("bess_soc_pct", 65.0)

        return BESSContainer(
            container_id=container_id,
            capacity_kwh=5.015,
            nominal_voltage_v=800,
            status="online",
            soc_pct=bess_soc_pct,
            soh_pct=98.5,
            power_kw=2.5,
            racks=[
                BESSRack(
                    rack_id=f"{container_id}_r1",
                    container_id=container_id,
                    voltage_v=400,
                    current_a=6,
                    temperature_c=25,
                    soh_pct=98.5,
                )
            ],
        )

    async def read_meter(self, meter_id: str) -> Optional[GridMeter]:
        """Read grid meter from simulation data."""
        # Refresh cache if needed
        sim_data = await self._get_simulation_data()
        if not sim_data:
            return None

        # Extract grid data from simulation
        current_hour_data = self._get_current_hour_data(sim_data)
        if not current_hour_data:
            return None

        import_kw = current_hour_data.get("grid_import_kw", 0.0)
        export_kw = current_hour_data.get("grid_export_kw", 0.0)

        return GridMeter(
            meter_id=meter_id,
            site_id=self.site_id,
            import_kw=import_kw,
            export_kw=export_kw,
            import_kwh_daily=import_kw * 12,  # Rough 12-hour average
            export_kwh_daily=export_kw * 12,
            voltage_v=400,
            current_a=10,
            power_factor=0.95,
            frequency_hz=50,
        )

    async def get_normalised_readings(self) -> List[NormalisedReading]:
        """Poll simulation and return normalised readings for all equipment."""
        readings = []

        # Refresh cache if needed
        sim_data = await self._get_simulation_data()
        if not sim_data:
            return readings

        current_hour_data = self._get_current_hour_data(sim_data)
        if not current_hour_data:
            return readings

        # Extract key metrics from simulation
        solar_gen_kw = current_hour_data.get("solar_gen_kw", 0.0)
        building_load_kw = current_hour_data.get("building_load_kw", 500.0)
        grid_import_kw = current_hour_data.get("grid_import_kw", 0.0)
        grid_export_kw = current_hour_data.get("grid_export_kw", 0.0)

        # Create readings for each component
        readings.extend(
            [
                NormalisedReading(
                    source_id="inverter-001",
                    description="Main Inverter AC Power",
                    value=solar_gen_kw,
                    unit="kW",
                    quality=QualityFlag.GOOD,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                ),
                NormalisedReading(
                    source_id="building-load",
                    description="Building Load",
                    value=building_load_kw,
                    unit="kW",
                    quality=QualityFlag.GOOD,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                ),
                NormalisedReading(
                    source_id="grid-import",
                    description="Grid Import",
                    value=grid_import_kw,
                    unit="kW",
                    quality=QualityFlag.GOOD,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                ),
                NormalisedReading(
                    source_id="grid-export",
                    description="Grid Export",
                    value=grid_export_kw,
                    unit="kW",
                    quality=QualityFlag.GOOD,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                ),
            ]
        )

        return readings

    # --- private helpers ---

    async def _get_simulation_data(self) -> Optional[Dict]:
        """Query solar_annual_simulations table for most recent results.

        Returns the full results dict with monthly and daily data.
        Caches for 30 seconds to avoid hammering the database.
        """
        now = datetime.now()

        # Check cache validity
        if self._cache_time and (now - self._cache_time).total_seconds() < self._cache_ttl_seconds:
            return self._cache.get("sim_data")

        try:
            supabase = get_supabase_client()

            # Query for most recent simulation results for this site
            response = (
                supabase.table("solar_annual_simulations")
                .select("*")
                .eq("site_id", self.site_id)
                .order("created_at", desc=True)
                .limit(1)
                .execute()
            )

            if not response.data:
                logger.debug(f"No simulation data found for {self.site_id}")
                return None

            sim_result = response.data[0]
            results = sim_result.get("results", {})

            # Cache the results
            self._cache["sim_data"] = results
            self._cache_time = now

            logger.debug(f"Loaded simulation data for {self.site_id} (cached for {self._cache_ttl_seconds}s)")
            return results

        except Exception as e:
            logger.error(f"Failed to get simulation data: {e}")
            return None

    def _get_current_hour_data(self, sim_data: Dict) -> Optional[Dict]:
        """Extract current hour's data from simulation results.

        Uses SeasonalModeler (same as simulation engine) to generate realistic
        solar generation based on current date/time. Scales based on actual
        plant capacity to match weather patterns.
        """
        if not sim_data:
            return None

        try:
            now = datetime.now()
            current_date = now.date()
            current_hour = now.hour

            # === Use SeasonalModeler for consistent weather patterns ===
            # This matches what the simulation engine uses
            solar_efficiency = self._seasonal_modeler.get_solar_generation_factor(
                current_date,
                cloud_cover=0.2,  # Assume 20% cloud cover (matching simulation)
            )

            # Solar generation curve (Gaussian-like, peaks at 12:00)
            # Matches _generate_hourly_snapshots in solar_annual_aggregator.py
            hour_factor = max(0, 1 - abs(current_hour - 12) / 6)

            # Calculate current solar generation based on plant capacity
            # 3.9 MWp nominal capacity * efficiency * hour factor * 0.8 (losses)
            current_solar_kw = self.plant_capacity_kwp * 1000 * solar_efficiency * hour_factor * 0.8

            # === Building load (from simulation) ===
            occupancy_factor = self._seasonal_modeler.get_occupancy_factor(
                current_date,
                current_hour,
                rain_today=False,
            )
            base_load = 500  # 500 kW base load
            occupancy_load = 300 * occupancy_factor
            hvac_load = 200 * max(0, 1 - abs(current_hour - 14) / 8)  # HVAC peaks at 14:00
            building_load_kw = base_load + occupancy_load + hvac_load

            # === BESS dynamics (from simulation) ===
            if current_hour < 7 or current_hour > 20:  # Night: charge from solar surplus
                bess_charge_kw = max(0, current_solar_kw - building_load_kw)
                bess_discharge_kw = 0
            elif current_hour > 17:  # Evening peak: discharge
                bess_discharge_kw = min(500, building_load_kw - current_solar_kw)
                bess_charge_kw = 0
            else:
                bess_charge_kw = 0
                bess_discharge_kw = 0

            # Simple BESS SOC model
            bess_soc_pct = 50 + (bess_charge_kw - bess_discharge_kw) * 0.1
            bess_soc_pct = max(10, min(90, bess_soc_pct))

            # === Grid import/export ===
            net_solar = current_solar_kw - building_load_kw - bess_charge_kw + bess_discharge_kw
            grid_export_kw = max(0, net_solar)
            grid_import_kw = max(0, -net_solar)

            return {
                "solar_gen_kw": round(current_solar_kw, 1),
                "building_load_kw": round(building_load_kw, 1),
                "grid_import_kw": round(grid_import_kw, 1),
                "grid_export_kw": round(grid_export_kw, 1),
                "bess_soc_pct": round(bess_soc_pct, 1),
            }

        except Exception as e:
            logger.error(f"Failed to extract current hour data: {e}")
            return None
