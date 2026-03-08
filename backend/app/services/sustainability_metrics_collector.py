"""
Sustainability Metrics Collector — Phase 111-01

Gathers daily sustainability metrics from existing simulation services.
Called at end of each simulated day by LifecycleOrchestrator.

Data sources:
- Energy breakdown: Passed directly from orchestrator accumulators
- Water: Queries energy_consumption_history (written hourly by thermal engine)
- Diesel: Queries generator_service for fuel rates + runtime hours
- Solar: Estimates daily generation from site capacity and month
- Occupancy: Passed directly from orchestrator samples

Persistence:
- Primary: Supabase upsert on (site_id, date) conflict
- Fallback: JSON file at data/sustainability/daily_metrics/{site_id}.json
"""

import json
import logging
from datetime import date
from pathlib import Path
from typing import Dict, Optional

from app.core.site_resolver import get_primary_site_code
from app.models.sustainability import (
    DailySustainabilityWrite,
    EmissionFactors,
    SustainabilityConfig,
)

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data" / "sustainability"
DAILY_METRICS_DIR = DATA_DIR / "daily_metrics"

# Monthly average solar generation factors for Johannesburg (kWh per kWp per day)
# Source: PVsyst / SolarGIS typical meteorological year data for -26.2, 28.0
_JHB_SOLAR_DAILY_FACTOR = {
    1: 5.8,  # Jan (summer, long days)
    2: 5.5,  # Feb
    3: 5.0,  # Mar
    4: 4.3,  # Apr
    5: 3.8,  # May
    6: 3.4,  # Jun (winter solstice)
    7: 3.6,  # Jul
    8: 4.2,  # Aug
    9: 4.8,  # Sep
    10: 5.1,  # Oct
    11: 5.5,  # Nov
    12: 5.7,  # Dec
}

# Default solar capacity for site-002 (kWp) — matches solar_annual_aggregator
DEFAULT_SOLAR_CAPACITY_KWP = 3900.0


class SustainabilityMetricsCollector:
    """Gathers and persists daily sustainability metrics.

    Designed to be instantiated once by LifecycleOrchestrator and called
    at each simulated day boundary.
    """

    def __init__(self, site_id: str):
        self.site_id = site_id
        self._supabase = None
        self._emission_factors = EmissionFactors()
        self._config: Optional[SustainabilityConfig] = None

    @property
    def supabase(self):
        """Lazy Supabase client (None when unavailable / demo mode)."""
        if self._supabase is None:
            try:
                from app.database.supabase_client import get_supabase_client

                self._supabase = get_supabase_client()
            except Exception:
                pass  # Fall back to JSON
        return self._supabase

    def _get_config(self) -> SustainabilityConfig:
        """Load sustainability config for the site (cached)."""
        if self._config is None:
            config_path = DATA_DIR / f"{self.site_id}_config.json"
            if config_path.exists():
                with open(config_path) as f:
                    data = json.load(f)
                self._config = SustainabilityConfig.from_dict(data)
            else:
                self._config = SustainabilityConfig(site_id=self.site_id)
        return self._config

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def collect_daily_metrics(
        self,
        date: date,
        energy_breakdown: Dict,
        occupancy_data: Dict,
    ) -> DailySustainabilityWrite:
        """Collect daily sustainability metrics from all available sources.

        Args:
            date: Simulated date for this snapshot.
            energy_breakdown: Dict with keys total_kwh, hvac_kwh, lighting_kwh, other_kwh
                              (passed directly from orchestrator accumulators).
            occupancy_data: Dict with keys avg_pct, peak_count
                            (passed directly from orchestrator).

        Returns:
            DailySustainabilityWrite ready for persistence.
        """
        # --- Energy (from orchestrator) ---
        grid_kwh = energy_breakdown.get("total_kwh") or 0.0
        hvac_kwh = energy_breakdown.get("hvac_kwh") or 0.0
        lighting_kwh = energy_breakdown.get("lighting_kwh") or 0.0
        other_kwh = energy_breakdown.get("other_kwh") or 0.0

        # --- Water (query DB or fallback to config estimate) ---
        water_liters = await self._collect_water(date)

        # --- Diesel / generator runtime ---
        diesel_liters, runtime_hours = await self._collect_diesel()

        # --- Solar ---
        solar_kwh = self._estimate_daily_solar(date)

        # --- Occupancy ---
        avg_occupancy_pct = occupancy_data.get("avg_pct") or 0.0
        peak_occupancy_count = int(occupancy_data.get("peak_count") or 0)

        # --- Emissions (inline using frozen emission factors) ---
        ef = self._emission_factors
        scope1_kg_co2 = diesel_liters * ef.diesel_kg_co2_per_litre
        net_grid = max(0.0, grid_kwh - solar_kwh)
        scope2_kg_co2 = net_grid * ef.grid_kg_co2_per_kwh
        scope3_water = (water_liters / 1000.0) * ef.water_kg_co2_per_kl
        config = self._get_config()
        scope3_commute = (avg_occupancy_pct / 100.0) * config.occupancy_capacity * ef.commute_kg_co2_per_person_day
        scope3_kg_co2 = scope3_water + scope3_commute

        return DailySustainabilityWrite(
            site_id=self.site_id,
            date=date,
            grid_kwh=round(grid_kwh, 2),
            hvac_kwh=round(hvac_kwh, 2),
            lighting_kwh=round(lighting_kwh, 2),
            other_kwh=round(other_kwh, 2),
            solar_generation_kwh=round(solar_kwh, 2),
            solar_export_kwh=0.0,  # No export modelling yet
            water_liters=round(water_liters, 1),
            diesel_liters=round(diesel_liters, 2),
            generator_runtime_hours=round(runtime_hours, 2),
            avg_occupancy_pct=round(avg_occupancy_pct, 1),
            peak_occupancy_count=peak_occupancy_count,
            scope1_kg_co2=round(scope1_kg_co2, 2),
            scope2_kg_co2=round(scope2_kg_co2, 2),
            scope3_kg_co2=round(scope3_kg_co2, 2),
            source="simulation",
        )

    async def persist(self, metrics: DailySustainabilityWrite) -> None:
        """Upsert metrics to Supabase; fall back to JSON on failure."""
        row = metrics.to_dict()
        persisted = False

        # --- Try Supabase ---
        if self.supabase:
            try:
                self.supabase.table("daily_sustainability_metrics").upsert(
                    row,
                    on_conflict="site_id,date",
                ).execute()
                persisted = True
                logger.info(f"[SUSTAINABILITY] Persisted metrics for {metrics.site_id} on {metrics.date} to Supabase")
            except Exception as e:
                logger.warning(f"[SUSTAINABILITY] Supabase upsert failed: {e}")

        # --- JSON fallback ---
        if not persisted:
            self._persist_json(row)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _collect_water(self, for_date: date) -> float:
        """Retrieve daily water consumption from energy_consumption_history.

        The thermal engine writes hourly water data via update_simulation_water()
        to energy_consumption_history with energy_type='WATER'.
        Sum today's records; fall back to config estimate if none found.
        """
        if self.supabase:
            try:
                date_str = for_date.isoformat()
                resp = (
                    self.supabase.table("energy_consumption_history")
                    .select("value")
                    .eq("site_id", self.site_id)
                    .eq("energy_type", "WATER")
                    .gte("timestamp", f"{date_str}T00:00:00")
                    .lt("timestamp", f"{date_str}T23:59:59")
                    .execute()
                )
                if resp.data:
                    total = sum(float(r.get("value") or 0) for r in resp.data)
                    if total > 0:
                        return total
            except Exception as e:
                logger.debug(f"[SUSTAINABILITY] Water query failed: {e}")

        # Fallback: config-based daily estimate
        config = self._get_config()
        return (config.monthly_water_kl * 1000.0) / 30.0

    async def _collect_diesel(self) -> tuple[float, float]:
        """Retrieve diesel consumption from generator service.

        Returns:
            (diesel_liters, runtime_hours) for the day.
        """
        try:
            from app.services.generator_service import GeneratorService

            gen_svc = GeneratorService()
            generators = gen_svc.get_generators(site_id=self.site_id)

            total_diesel = 0.0
            total_runtime = 0.0

            for gen in generators:
                fuel_rate = 0.0
                if gen.engine and isinstance(gen.engine, dict):
                    fuel_rate = float(gen.engine.get("fuel_rate_lph") or 0)
                elif hasattr(gen, "engine") and hasattr(gen.engine, "fuel_rate_lph"):
                    fuel_rate = gen.engine.fuel_rate_lph

                # Estimate daily runtime from SA load-shedding schedule:
                # Average ~3 hours/day on working days during simulation.
                # This is the legacy estimate; future plans can refine with
                # actual telemetry tracking.
                estimated_runtime_hours = 3.0
                total_runtime += estimated_runtime_hours
                total_diesel += fuel_rate * estimated_runtime_hours

            if total_diesel > 0:
                return total_diesel, total_runtime

        except Exception as e:
            logger.debug(f"[SUSTAINABILITY] Generator query failed: {e}")

        # Legacy fallback: 3 hrs/day, 22L/hr (typical 250 kVA genset)
        return 66.0, 3.0

    def _estimate_daily_solar(self, for_date: date) -> float:
        """Estimate daily solar generation from site capacity and month.

        Uses Johannesburg monthly solar factors. Returns 0 if site has
        no solar installation.
        """
        month = for_date.month
        factor = _JHB_SOLAR_DAILY_FACTOR.get(month, 4.5)

        # Check if site has solar (primary site does)
        # For now, use default capacity; future: read from site config
        capacity_kwp = DEFAULT_SOLAR_CAPACITY_KWP if self.site_id == get_primary_site_code() else 0.0
        if capacity_kwp <= 0:
            return 0.0

        return round(capacity_kwp * factor, 2)

    def _persist_json(self, row: Dict) -> None:
        """Append daily metrics to JSON fallback file."""
        DAILY_METRICS_DIR.mkdir(parents=True, exist_ok=True)
        json_path = DAILY_METRICS_DIR / f"{self.site_id}.json"

        records = []
        if json_path.exists():
            try:
                with open(json_path) as f:
                    records = json.load(f)
            except (json.JSONDecodeError, OSError):
                records = []

        # Upsert: replace existing record for same date
        date_str = row.get("date", "")
        records = [r for r in records if r.get("date") != date_str]
        records.append(row)

        # Keep last 400 days to avoid unbounded growth
        records = sorted(records, key=lambda r: r.get("date", ""))[-400:]

        with open(json_path, "w") as f:
            json.dump(records, f, indent=2)

        logger.info(
            f"[SUSTAINABILITY] Persisted metrics for {row.get('site_id')} "
            f"on {date_str} to JSON fallback ({len(records)} records)"
        )
