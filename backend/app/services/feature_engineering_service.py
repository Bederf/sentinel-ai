"""Building-level Feature Engineering Service.

Computes derived building-level metrics for ML context injection and
building efficiency scoring. These are NOT per-equipment features
(see feature_service.py for those) — these are building-wide KPIs.

Derived features:
- EUI: Energy Use Intensity (kWh/m²)
- Base Load Index: off-hours consumption / total daily consumption
- Cooling Degree Days (CDD): weather-based normalisation
- Cooling Load Ratio: actual / theoretical baseline
- Setpoint Deviation Score: avg |actual - setpoint| across zones
- Building Efficiency Score: composite 0-100
"""

import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

# Singleton
_feature_engineering_service: Optional["FeatureEngineeringService"] = None


def get_feature_engineering_service() -> "FeatureEngineeringService":
    """Get singleton feature engineering service."""
    global _feature_engineering_service
    if _feature_engineering_service is None:
        _feature_engineering_service = FeatureEngineeringService()
    return _feature_engineering_service


class FeatureEngineeringService:
    """Computes building-level derived features from telemetry and metadata."""

    # South African grid constants
    SA_BASE_TEMP_C = 18.0  # CDD base temperature for SA commercial buildings
    SA_CARBON_INTENSITY = 0.35  # kg CO2/kWh

    def __init__(self):
        self._site_cache: Dict[str, Dict[str, Any]] = {}

    def _get_site_metadata(self, site_id: str) -> Dict[str, Any]:
        """Load building metadata (sqm, floors, operating hours)."""
        if site_id in self._site_cache:
            return self._site_cache[site_id]

        try:
            from app.services.ai_optimizer import load_sites

            sites = load_sites()
            for site in sites:
                if site.get("id") == site_id:
                    self._site_cache[site_id] = site
                    return site
        except Exception as e:
            logger.debug(f"Could not load building metadata for {site_id}: {e}")

        # Fallback defaults
        return {"sqm": 9000, "floors": 5, "operating_hours": {"start": "08:00", "end": "18:00"}}

    async def compute_site_features(self, site_id: str) -> Dict[str, Any]:
        """Compute all building-level derived features.

        Returns dict with: eui, base_load_index, cooling_degree_days,
        setpoint_deviation, efficiency_score, and their components.
        """
        features: Dict[str, Any] = {}
        building = self._get_site_metadata(site_id)
        sqm = building.get("sqm", 9000)

        # Gather telemetry from simulation store or Supabase
        telemetry = await self._get_daily_telemetry(site_id)

        # 1. Energy Use Intensity (EUI)
        daily_kwh = telemetry.get("total_daily_kwh")
        if daily_kwh is not None and sqm > 0:
            features["eui"] = round(daily_kwh / sqm, 4)

        # 2. Base Load Index
        off_hours_kwh = telemetry.get("off_hours_kwh")
        if daily_kwh and daily_kwh > 0 and off_hours_kwh is not None:
            features["base_load_index"] = round(off_hours_kwh / daily_kwh, 4)

        # 3. Cooling Degree Days (CDD)
        outdoor_temps = telemetry.get("outdoor_temps_hourly", [])
        if outdoor_temps:
            features["cooling_degree_days"] = self.compute_cdd(outdoor_temps)

        # 4. Setpoint Deviation Score
        zone_deviations = telemetry.get("zone_deviations", [])
        if zone_deviations:
            features["setpoint_deviation"] = round(sum(zone_deviations) / len(zone_deviations), 2)

        # 5. Building Efficiency Score (composite)
        features["efficiency_score"] = self.compute_efficiency_score(features, building)

        return features

    def compute_cdd(self, hourly_temps: list[float]) -> float:
        """Compute Cooling Degree Days from hourly outdoor temperatures.

        CDD = sum(max(0, T_hour - T_base)) / 24

        Args:
            hourly_temps: List of hourly outdoor temperatures (°C)

        Returns:
            CDD value for the period covered by the temperatures
        """
        if not hourly_temps:
            return 0.0

        cdd_sum = sum(max(0, t - self.SA_BASE_TEMP_C) for t in hourly_temps)
        # Normalise to days (24h)
        return round(cdd_sum / 24.0, 2)

    def compute_efficiency_score(self, features: Dict[str, Any], building: Dict[str, Any]) -> float:
        """Compute building efficiency score (0-100).

        Components (weighted):
        - EUI vs benchmark: 35% (lower is better)
        - Base load index: 25% (lower is better — less off-hours waste)
        - Setpoint deviation: 25% (lower is better — tighter control)
        - CDD-adjusted bonus: 15% (efficiency in hot conditions)

        Returns:
            Score 0-100, higher is better
        """
        score = 50.0  # Default when no data
        components = 0
        weighted_sum = 0.0

        # EUI component (35%)
        eui = features.get("eui")
        if eui is not None:
            # SA commercial benchmark: ~0.15 kWh/m²/day is excellent, 0.50 is poor
            eui_score = max(0, min(100, 100 - (eui - 0.10) * 300))
            weighted_sum += eui_score * 0.35
            components += 0.35

        # Base load index component (25%)
        bli = features.get("base_load_index")
        if bli is not None:
            # <0.15 is excellent (low off-hours waste), >0.40 is poor
            bli_score = max(0, min(100, 100 - (bli - 0.10) * 333))
            weighted_sum += bli_score * 0.25
            components += 0.25

        # Setpoint deviation component (25%)
        sd = features.get("setpoint_deviation")
        if sd is not None:
            # <0.5°C deviation is excellent, >3°C is poor
            sd_score = max(0, min(100, 100 - (sd * 33)))
            weighted_sum += sd_score * 0.25
            components += 0.25

        # CDD-adjusted efficiency bonus (15%)
        cdd = features.get("cooling_degree_days")
        if cdd is not None and eui is not None and cdd > 0:
            # Efficiency under heat: lower EUI per CDD is better
            eui_per_cdd = eui / max(cdd, 0.1)
            cdd_score = max(0, min(100, 100 - (eui_per_cdd - 0.01) * 500))
            weighted_sum += cdd_score * 0.15
            components += 0.15

        if components > 0:
            score = round(weighted_sum / components, 1)

        return max(0, min(100, score))

    async def _get_daily_telemetry(self, site_id: str) -> Dict[str, Any]:
        """Gather daily telemetry for feature computation.

        Tries simulation store first, then Supabase sustainability metrics.
        """
        telemetry: Dict[str, Any] = {}

        # Try simulation store (in-memory data from running simulation)
        try:
            from app.services.simulation_store import get_simulation_store

            store = get_simulation_store(site_id)
            state = store.get_latest_state() if store else None
            if state:
                # Extract daily energy from simulation state
                energy = state.get("energy", {})
                telemetry["total_daily_kwh"] = energy.get("total_kwh", 0)
                telemetry["off_hours_kwh"] = energy.get("off_hours_kwh")

                # Extract outdoor temps
                weather = state.get("weather", {})
                if weather.get("outdoor_temp"):
                    telemetry["outdoor_temps_hourly"] = [weather["outdoor_temp"]]

                # Extract zone deviations
                zones = state.get("zones", {})
                deviations = []
                for zone_data in zones.values():
                    actual = zone_data.get("temperature")
                    setpoint = zone_data.get("setpoint")
                    if actual is not None and setpoint is not None:
                        deviations.append(abs(actual - setpoint))
                if deviations:
                    telemetry["zone_deviations"] = deviations
        except Exception as e:
            logger.debug(f"Simulation store unavailable for telemetry: {e}")

        # Try Supabase sustainability metrics as fallback
        if not telemetry.get("total_daily_kwh"):
            try:
                from pathlib import Path
                import json

                metrics_path = (
                    Path(__file__).parent.parent / "data" / "sustainability" / "daily_metrics" / f"{site_id}.json"
                )
                if metrics_path.exists():
                    with open(metrics_path) as f:
                        metrics = json.load(f)
                    if isinstance(metrics, list) and metrics:
                        latest = metrics[-1]
                        telemetry.setdefault("total_daily_kwh", latest.get("total_kwh", 0))
            except Exception as e:
                logger.debug(f"Sustainability metrics unavailable: {e}")

        return telemetry
