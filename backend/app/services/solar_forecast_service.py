"""Solar Generation Forecast Service -- 72-hour rolling forecast engine.

Provides generation forecasts using layered statistical + ML models:
  1. Persistence model (baseline): Tomorrow = Today
  2. Clear-sky model: Theoretical max based on solar geometry for Joburg (-26.2deg)
  3. Historical average model: Mean of same weekday over past 4 weeks
  4. ML gradient boosting model: Trained on synthetic historical data (34-08)
  5. Weighted ensemble: 20% persistence + 20% clear-sky + 30% historical + 30% ML

The ML model (gradient boosting) was added in Plan 34-08 as a foundation for
future LSTM/transformer models. It uses features: hour_of_day, day_of_year,
cloud_cover_estimate, temperature, yesterday_generation.

Solar geometry for southern hemisphere (Johannesburg):
  - Declination: delta = 23.45 * sin(360/365 * (284 + day_of_year))
  - Hour angle: omega = 15 * (hour - 12)
  - Solar altitude: sin(alpha) = sin(phi)sin(delta) + cos(phi)cos(delta)cos(omega)
  - Air mass: AM = 1/cos(zenith) (simplified Kasten-Young)
  - Clear-sky GHI: 1000 * 0.7^(AM^0.678) W/m2 (simplified Ineichen)
  - Panel output: P = capacity * (irradiance/1000) * temp_derate * soiling

Site-002 site (lat -26.13, 3,900.88 kWp installed):
  - Summer peak: ~3,200 kW at noon (clear day)
  - Winter peak: ~2,400 kW at noon (lower solar angle)
  - Daily yield: 15-22 MWh summer, 10-16 MWh winter
"""

import json
import logging
import math
import random
from dataclasses import dataclass, field
from datetime import datetime, date, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


# === Dataclass models ===


@dataclass
class SolarPosition:
    """Sun position at a specific time and location."""

    hour: int
    declination_deg: float
    hour_angle_deg: float
    altitude_deg: float
    zenith_deg: float
    air_mass: float
    ghi_wm2: float  # Global Horizontal Irradiance (clear sky)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "hour": self.hour,
            "declination_deg": round(self.declination_deg, 2),
            "hour_angle_deg": round(self.hour_angle_deg, 2),
            "altitude_deg": round(self.altitude_deg, 2),
            "zenith_deg": round(self.zenith_deg, 2),
            "air_mass": round(self.air_mass, 3),
            "ghi_wm2": round(self.ghi_wm2, 1),
        }


@dataclass
class HourlyGeneration:
    """Forecast generation for a single hour."""

    hour: str  # ISO timestamp e.g. 2026-02-06T15:00
    generation_kw: float
    confidence_high_kw: float
    confidence_low_kw: float
    clear_sky_kw: float = 0.0
    cloud_factor: float = 1.0  # 1.0 = clear, 0.0 = fully overcast

    def to_dict(self) -> Dict[str, Any]:
        return {
            "hour": self.hour,
            "generation_kw": round(self.generation_kw, 0),
            "confidence_high_kw": round(self.confidence_high_kw, 0),
            "confidence_low_kw": round(self.confidence_low_kw, 0),
            "clear_sky_kw": round(self.clear_sky_kw, 0),
            "cloud_factor": round(self.cloud_factor, 2),
        }


@dataclass
class DailyTotal:
    """Aggregated generation forecast for a full day."""

    date: str  # YYYY-MM-DD
    expected_kwh: float
    clear_sky_kwh: float
    cloud_factor: float  # average for the day

    def to_dict(self) -> Dict[str, Any]:
        return {
            "date": self.date,
            "expected_kwh": round(self.expected_kwh, 0),
            "clear_sky_kwh": round(self.clear_sky_kwh, 0),
            "cloud_factor": round(self.cloud_factor, 2),
        }


@dataclass
class ForecastAccuracy:
    """Accuracy metrics for the forecast vs actual generation."""

    site_id: str
    period_days: int
    rmse_kw: float  # Root mean square error
    mae_kw: float  # Mean absolute error
    bias_pct: float  # Systematic over/under prediction
    peak_capacity_kw: float = 0.0  # For RMSE % calculation

    def to_dict(self) -> Dict[str, Any]:
        return {
            "site_id": self.site_id,
            "period_days": self.period_days,
            "rmse_kw": round(self.rmse_kw, 1),
            "mae_kw": round(self.mae_kw, 1),
            "bias_pct": round(self.bias_pct, 1),
            "rmse_pct_of_peak": round(
                (self.rmse_kw / self.peak_capacity_kw * 100) if self.peak_capacity_kw > 0 else 0, 1
            ),
        }


@dataclass
class GenerationForecast:
    """Complete generation forecast response."""

    site_id: str
    generated_at: str  # ISO timestamp
    model: str  # persistence / clear_sky / historical / weighted_ensemble
    hourly: List[HourlyGeneration] = field(default_factory=list)
    daily_totals: List[DailyTotal] = field(default_factory=list)
    accuracy_7d: Optional[ForecastAccuracy] = None

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "site_id": self.site_id,
            "generated_at": self.generated_at,
            "model": self.model,
            "hourly": [h.to_dict() for h in self.hourly],
            "daily_totals": [d.to_dict() for d in self.daily_totals],
        }
        if self.accuracy_7d:
            result["accuracy_7d"] = self.accuracy_7d.to_dict()
        return result


# === Solar Geometry Engine ===


class SolarGeometry:
    """Solar position and irradiance calculations for southern hemisphere.

    All angles in degrees unless otherwise noted.
    Latitude convention: negative for southern hemisphere.
    """

    @staticmethod
    def declination(day_of_year: int) -> float:
        """Solar declination angle (degrees). Cooper's equation."""
        return 23.45 * math.sin(math.radians(360.0 / 365.0 * (284 + day_of_year)))

    @staticmethod
    def hour_angle(solar_hour: float) -> float:
        """Hour angle (degrees). Negative morning, positive afternoon."""
        return 15.0 * (solar_hour - 12.0)

    @staticmethod
    def solar_altitude(lat_deg: float, declination_deg: float, hour_angle_deg: float) -> float:
        """Solar altitude angle above horizon (degrees).

        sin(alpha) = sin(phi)*sin(delta) + cos(phi)*cos(delta)*cos(omega)
        """
        phi = math.radians(lat_deg)
        delta = math.radians(declination_deg)
        omega = math.radians(hour_angle_deg)

        sin_alpha = math.sin(phi) * math.sin(delta) + math.cos(phi) * math.cos(delta) * math.cos(omega)
        # Clamp to [-1, 1] for numerical safety
        sin_alpha = max(-1.0, min(1.0, sin_alpha))
        return math.degrees(math.asin(sin_alpha))

    @staticmethod
    def air_mass(zenith_deg: float) -> float:
        """Simplified Kasten-Young air mass model.

        AM = 1 / (cos(z) + 0.50572 * (96.07995 - z)^-1.6364)
        Returns high value for sun below horizon.
        """
        if zenith_deg >= 90.0:
            return 40.0  # Sun below horizon
        z_rad = math.radians(zenith_deg)
        denominator = math.cos(z_rad) + 0.50572 * (96.07995 - zenith_deg) ** (-1.6364)
        if denominator <= 0:
            return 40.0
        return min(1.0 / denominator, 40.0)

    @staticmethod
    def clear_sky_ghi(air_mass_val: float) -> float:
        """Clear-sky Global Horizontal Irradiance (W/m2) for Johannesburg.

        Uses Meinel model with Johannesburg altitude correction (1,753m ASL).
        The high altitude and generally clear atmosphere give peak GHI of ~950 W/m2.

        GHI = 1.353 * 0.7^(AM^0.678) * 1000 * altitude_correction
        The factor 1.353 is the solar constant normalised.
        Altitude correction for JHB: ~1.06 (6% more irradiance at 1,753m).
        Returns 0 when air mass indicates sun below horizon.
        """
        if air_mass_val >= 38.0:
            return 0.0
        # Meinel model with JHB altitude correction
        altitude_factor = 1.06  # 1,753m elevation correction
        ghi = 1353.0 * (0.7 ** (air_mass_val**0.678)) * altitude_factor
        return min(ghi, 1100.0)  # Cap at reasonable maximum

    @classmethod
    def get_position(cls, lat: float, lng: float, target_date: date, hour: int) -> SolarPosition:
        """Calculate full solar position for a given location, date, and hour (SAST)."""
        day_of_year = target_date.timetuple().tm_yday
        decl = cls.declination(day_of_year)

        # Simple longitude correction for SAST (UTC+2, standard meridian 30E)
        # Equation of time approximation (simplified)
        b = math.radians(360.0 / 365.0 * (day_of_year - 81))
        eot_minutes = 9.87 * math.sin(2 * b) - 7.53 * math.cos(b) - 1.5 * math.sin(b)
        solar_hour = hour + (lng - 30.0) * 4.0 / 60.0 + eot_minutes / 60.0

        ha = cls.hour_angle(solar_hour)
        altitude = cls.solar_altitude(lat, decl, ha)
        zenith = 90.0 - altitude
        am = cls.air_mass(zenith)
        ghi = cls.clear_sky_ghi(am)

        return SolarPosition(
            hour=hour,
            declination_deg=decl,
            hour_angle_deg=ha,
            altitude_deg=altitude,
            zenith_deg=zenith,
            air_mass=am,
            ghi_wm2=ghi,
        )


# === Forecast Service ===


class SolarForecastService:
    """72-hour rolling generation forecast using statistical + ML models.

    Loads site configuration (lat/lng/capacity) from site-002_config.json
    and generates forecasts using an ensemble of statistical and ML models.

    The forecast is used by the arbitrage engine (34-05) to decide whether
    to charge BESS aggressively overnight (cloudy forecast) or rely on
    solar to charge during the day (sunny forecast).

    ML model (34-08): Simple gradient boosting trained on 90 days of
    synthetic historical data. Features: hour_of_day, day_of_year,
    cloud_cover_estimate, temperature, yesterday_generation.
    """

    # Ensemble weights (updated in 34-08 to include ML model)
    WEIGHT_PERSISTENCE = 0.20
    WEIGHT_CLEAR_SKY = 0.20
    WEIGHT_HISTORICAL = 0.30
    WEIGHT_ML = 0.30

    # Panel derating factors
    TEMP_DERATE = 0.92  # Temperature derating (JHB summer ~35C)
    SOILING_FACTOR = 0.97  # 3% soiling loss (cleaned monthly)
    SYSTEM_LOSSES = 0.95  # Cable, mismatch, inverter clipping

    def __init__(self):
        self._site_configs: Dict[str, Dict] = {}
        self._persistence_cache: Dict[str, List[float]] = {}  # site_id -> 24h actuals
        self._historical_cache: Dict[str, List[List[float]]] = {}  # site_id -> weeks of 24h data
        self._geometry = SolarGeometry()
        # ML model state (34-08)
        self._ml_models: Dict[str, "_GradientBoostingModel"] = {}  # site_id -> model
        self._ml_accuracy: Dict[str, Dict[str, float]] = {}  # site_id -> accuracy metrics
        self._load_site_configs()
        self._seed_demo_data()
        self._train_ml_models()

    def _load_site_configs(self) -> None:
        """Load solar site configurations."""
        solar_dir = Path(__file__).parent.parent / "data" / "solar"
        if not solar_dir.exists():
            logger.warning("Solar data directory not found: %s", solar_dir)
            return

        for config_path in solar_dir.glob("*_config.json"):
            try:
                with open(config_path) as f:
                    config = json.load(f)
                site_id = config.get("site_id", config_path.stem.replace("_config", ""))
                total_capacity = sum(p.get("capacity_kwp", 0) for p in config.get("plants", []))
                self._site_configs[site_id] = {
                    "site_id": site_id,
                    "site_name": config.get("site_name", site_id),
                    "latitude": config.get("latitude", -26.13),
                    "longitude": config.get("longitude", 27.97),
                    "capacity_kwp": total_capacity,
                    "plant_count": len(config.get("plants", [])),
                    "tilt": config.get("plants", [{}])[0].get("tilt", 10),
                    "orientation": config.get("plants", [{}])[0].get("orientation", 0),
                }
                logger.info("Loaded solar site %s (%.1f kWp) for forecast", site_id, total_capacity)
            except Exception as e:
                logger.error("Failed to load solar config %s: %s", config_path, e)

    def _seed_demo_data(self) -> None:
        """Seed persistence and historical cache with realistic demo data."""
        for site_id, config in self._site_configs.items():
            lat = config["latitude"]
            lng = config["longitude"]
            capacity = config["capacity_kwp"]
            today = date.today()

            # Seed today's generation as persistence baseline (with some cloud variation)
            today_profile = self._generate_realistic_profile(lat, lng, capacity, today, cloud_seed=42)
            self._persistence_cache[site_id] = today_profile

            # Seed 4 weeks of historical data for the same weekday
            historical = []
            for week_offset in range(1, 5):
                hist_date = today - timedelta(days=7 * week_offset)
                seed = hash(f"{site_id}-{hist_date.isoformat()}") % 1000
                profile = self._generate_realistic_profile(lat, lng, capacity, hist_date, cloud_seed=seed)
                historical.append(profile)
            self._historical_cache[site_id] = historical

    def _generate_realistic_profile(
        self,
        lat: float,
        lng: float,
        capacity_kwp: float,
        target_date: date,
        cloud_seed: int = 0,
    ) -> List[float]:
        """Generate a realistic 24-hour generation profile in kW.

        Returns list of 24 values (index 0 = midnight, 23 = 11pm) in SAST.
        Cloud effects are seeded for reproducibility.
        """
        rng = random.Random(cloud_seed)

        # Generate base cloud pattern for the day
        # Decide if it's a mostly clear, partly cloudy, or overcast day
        day_type = rng.choices(
            ["clear", "partly_cloudy", "mostly_cloudy", "overcast"],
            weights=[0.45, 0.30, 0.15, 0.10],
            k=1,
        )[0]

        base_cloud_factors = {
            "clear": 0.95,
            "partly_cloudy": 0.70,
            "mostly_cloudy": 0.45,
            "overcast": 0.20,
        }
        base_cf = base_cloud_factors[day_type]

        profile = []
        for hour in range(24):
            pos = self._geometry.get_position(lat, lng, target_date, hour)
            if pos.ghi_wm2 <= 0:
                profile.append(0.0)
                continue

            # Effective irradiance on tilted panel (simplified - assume ~5% gain from tilt in JHB)
            effective_irradiance = pos.ghi_wm2 * 1.05

            # Panel output before cloud effects
            clear_sky_kw = (
                capacity_kwp
                * (effective_irradiance / 1000.0)
                * self.TEMP_DERATE
                * self.SOILING_FACTOR
                * self.SYSTEM_LOSSES
            )

            # Hourly cloud variation (clouds aren't constant)
            hourly_cf = base_cf + rng.uniform(-0.10, 0.10)
            hourly_cf = max(0.05, min(1.0, hourly_cf))

            # Afternoon thunderstorm effect (common in JHB summer, Dec-Feb)
            month = target_date.month
            if month in (11, 12, 1, 2) and hour >= 14 and hour <= 17:
                thunderstorm_chance = rng.random()
                if thunderstorm_chance < 0.25:
                    hourly_cf *= 0.30  # Heavy thunderstorm
                elif thunderstorm_chance < 0.50:
                    hourly_cf *= 0.60  # Light clouds building

            generation_kw = clear_sky_kw * hourly_cf
            profile.append(max(0.0, generation_kw))

        return profile

    # === Public API ===

    def get_forecast(
        self,
        site_id: str,
        hours_ahead: int = 72,
        model: str = "weighted_ensemble",
    ) -> GenerationForecast:
        """Generate rolling generation forecast.

        Args:
            site_id: Solar site identifier.
            hours_ahead: Forecast horizon in hours (default 72).
            model: Forecast model to use (persistence, clear_sky, historical, weighted_ensemble).

        Returns:
            GenerationForecast with hourly values and daily totals.
        """
        config = self._site_configs.get(site_id)
        if not config:
            # Return empty forecast for unknown site
            return GenerationForecast(
                site_id=site_id,
                generated_at=datetime.now(timezone.utc).isoformat(),
                model=model,
            )

        lat = config["latitude"]
        lng = config["longitude"]
        capacity = config["capacity_kwp"]
        now = datetime.now(timezone.utc)
        sast_now = now + timedelta(hours=2)
        hourly_entries: List[HourlyGeneration] = []
        daily_kwh: Dict[str, Dict[str, float]] = {}  # date -> {expected, clear_sky}

        for offset in range(hours_ahead):
            forecast_dt = sast_now + timedelta(hours=offset)
            forecast_hour = forecast_dt.hour
            forecast_date = forecast_dt.date()
            date_str = forecast_date.isoformat()

            # Get clear-sky generation for this hour
            clear_sky_kw = self._get_clear_sky_generation(lat, lng, capacity, forecast_date, forecast_hour)

            # Apply forecast model
            if model == "persistence":
                gen_kw = self._persistence_forecast(site_id, forecast_hour)
            elif model == "clear_sky":
                gen_kw = clear_sky_kw * 0.85  # Assume 85% typical conditions
            elif model == "historical":
                gen_kw = self._historical_forecast(site_id, forecast_hour)
            elif model == "ml":
                gen_kw = self._ml_forecast(site_id, forecast_date, forecast_hour)
            else:  # weighted_ensemble
                gen_kw = self._ensemble_forecast(site_id, lat, lng, capacity, forecast_date, forecast_hour)

            # Confidence bands widen with forecast horizon
            hours_from_now = offset
            uncertainty_pct = min(0.35, 0.05 + hours_from_now * 0.004)  # 5% -> 35% over 72h
            confidence_high = gen_kw * (1.0 + uncertainty_pct)
            confidence_low = max(0.0, gen_kw * (1.0 - uncertainty_pct))

            cloud_factor = (gen_kw / clear_sky_kw) if clear_sky_kw > 0 else 0.0

            hour_ts = forecast_dt.strftime("%Y-%m-%dT%H:%M")
            hourly_entries.append(
                HourlyGeneration(
                    hour=hour_ts,
                    generation_kw=gen_kw,
                    confidence_high_kw=confidence_high,
                    confidence_low_kw=confidence_low,
                    clear_sky_kw=clear_sky_kw,
                    cloud_factor=cloud_factor,
                )
            )

            # Accumulate daily totals
            if date_str not in daily_kwh:
                daily_kwh[date_str] = {"expected": 0.0, "clear_sky": 0.0}
            daily_kwh[date_str]["expected"] += gen_kw  # kW * 1h = kWh
            daily_kwh[date_str]["clear_sky"] += clear_sky_kw

        # Build daily totals
        daily_totals = []
        for dt_str in sorted(daily_kwh.keys()):
            exp = daily_kwh[dt_str]["expected"]
            cs = daily_kwh[dt_str]["clear_sky"]
            daily_totals.append(
                DailyTotal(
                    date=dt_str,
                    expected_kwh=exp,
                    clear_sky_kwh=cs,
                    cloud_factor=(exp / cs) if cs > 0 else 0.0,
                )
            )

        # Get accuracy metrics
        accuracy = self.get_forecast_accuracy(site_id)

        return GenerationForecast(
            site_id=site_id,
            generated_at=now.isoformat(),
            model=model,
            hourly=hourly_entries,
            daily_totals=daily_totals,
            accuracy_7d=accuracy,
        )

    def get_clear_sky_profile(
        self,
        site_id: str,
        target_date: Optional[date] = None,
    ) -> List[HourlyGeneration]:
        """Get theoretical maximum generation profile for a given date.

        Returns 24 hourly values representing perfect clear-sky conditions.
        """
        config = self._site_configs.get(site_id)
        if not config:
            return []

        d = target_date or date.today()
        lat = config["latitude"]
        lng = config["longitude"]
        capacity = config["capacity_kwp"]

        profile = []
        for hour in range(24):
            cs_kw = self._get_clear_sky_generation(lat, lng, capacity, d, hour)
            hour_ts = datetime(d.year, d.month, d.day, hour, 0).strftime("%Y-%m-%dT%H:%M")
            profile.append(
                HourlyGeneration(
                    hour=hour_ts,
                    generation_kw=cs_kw,
                    confidence_high_kw=cs_kw,
                    confidence_low_kw=cs_kw * 0.90,  # 10% uncertainty even for clear sky
                    clear_sky_kw=cs_kw,
                    cloud_factor=1.0,
                )
            )
        return profile

    def calculate_solar_geometry(
        self,
        lat: float,
        lng: float,
        target_date: date,
        hour: int,
    ) -> SolarPosition:
        """Calculate sun position, air mass, and irradiance."""
        return self._geometry.get_position(lat, lng, target_date, hour)

    def get_forecast_accuracy(
        self,
        site_id: str,
        days: int = 7,
    ) -> ForecastAccuracy:
        """Calculate forecast accuracy metrics (RMSE, MAE, bias) vs simulated actuals.

        For demo, generates realistic accuracy metrics based on model characteristics.
        In production, this would compare stored forecasts vs metered generation.
        """
        config = self._site_configs.get(site_id)
        if not config:
            return ForecastAccuracy(
                site_id=site_id,
                period_days=days,
                rmse_kw=0,
                mae_kw=0,
                bias_pct=0,
            )

        peak_capacity = config["capacity_kwp"]

        # Realistic accuracy for statistical ensemble models
        # RMSE typically 10-15% of peak for simple models
        rng = random.Random(hash(f"{site_id}-accuracy-{days}"))
        rmse = peak_capacity * rng.uniform(0.08, 0.13)
        mae = rmse * rng.uniform(0.70, 0.80)  # MAE typically 70-80% of RMSE
        bias = rng.uniform(-3.0, 1.0)  # Slight under-prediction bias (conservative)

        return ForecastAccuracy(
            site_id=site_id,
            period_days=days,
            rmse_kw=rmse,
            mae_kw=mae,
            bias_pct=bias,
            peak_capacity_kw=peak_capacity,
        )

    def update_persistence_model(self, site_id: str) -> None:
        """Store today's actual generation for use as tomorrow's persistence forecast.

        In production, called at end of day with metered data.
        For demo, regenerates with today's date as seed.
        """
        config = self._site_configs.get(site_id)
        if not config:
            return

        today = date.today()
        profile = self._generate_realistic_profile(
            config["latitude"],
            config["longitude"],
            config["capacity_kwp"],
            today,
            cloud_seed=hash(f"{site_id}-{today.isoformat()}") % 1000,
        )
        self._persistence_cache[site_id] = profile
        logger.info("Updated persistence model for %s with %d hours", site_id, len(profile))

    def is_cloudy_forecast(self, site_id: str, target_date: Optional[date] = None) -> bool:
        """Quick check: is tomorrow's forecast cloudy (< 50% of clear-sky)?

        Used by arbitrage engine to decide overnight BESS charging strategy.
        """
        config = self._site_configs.get(site_id)
        if not config:
            return False

        d = target_date or (date.today() + timedelta(days=1))
        lat = config["latitude"]
        lng = config["longitude"]
        capacity = config["capacity_kwp"]

        # Calculate clear-sky total
        clear_sky_total = sum(self._get_clear_sky_generation(lat, lng, capacity, d, h) for h in range(24))

        # Get ensemble forecast total
        forecast_total = sum(self._ensemble_forecast(site_id, lat, lng, capacity, d, h) for h in range(24))

        if clear_sky_total <= 0:
            return False

        cloud_factor = forecast_total / clear_sky_total
        return cloud_factor < 0.50

    # === Private forecast methods ===

    def _get_clear_sky_generation(
        self,
        lat: float,
        lng: float,
        capacity_kwp: float,
        target_date: date,
        hour: int,
    ) -> float:
        """Calculate clear-sky generation for a specific hour in kW."""
        pos = self._geometry.get_position(lat, lng, target_date, hour)
        if pos.ghi_wm2 <= 0:
            return 0.0

        # Effective irradiance on tilted panel (~5% gain from tilt in JHB)
        effective_irradiance = pos.ghi_wm2 * 1.05

        return (
            capacity_kwp * (effective_irradiance / 1000.0) * self.TEMP_DERATE * self.SOILING_FACTOR * self.SYSTEM_LOSSES
        )

    def _persistence_forecast(self, site_id: str, hour: int) -> float:
        """Persistence model: tomorrow = today."""
        cache = self._persistence_cache.get(site_id)
        if not cache or hour >= len(cache):
            return 0.0
        return cache[hour]

    def _historical_forecast(self, site_id: str, hour: int) -> float:
        """Historical average model: mean of same hour over past 4 weeks."""
        weeks = self._historical_cache.get(site_id, [])
        if not weeks:
            return 0.0

        values = [w[hour] for w in weeks if hour < len(w)]
        if not values:
            return 0.0
        return sum(values) / len(values)

    def _ml_forecast(
        self,
        site_id: str,
        forecast_date: date,
        hour: int,
    ) -> float:
        """ML gradient boosting forecast for a single hour.

        Uses trained model with features: hour_of_day, day_of_year,
        cloud_cover_estimate, temperature, yesterday_generation.
        Falls back to historical model if ML model not trained.
        """
        model = self._ml_models.get(site_id)
        if not model:
            return self._historical_forecast(site_id, hour)

        # Build feature vector
        day_of_year = forecast_date.timetuple().tm_yday

        # Cloud cover estimate from persistence deviation
        persistence_val = self._persistence_forecast(site_id, hour)
        config = self._site_configs.get(site_id, {})
        capacity = config.get("capacity_kwp", 3900)
        clear_sky = self._get_clear_sky_generation(
            config.get("latitude", -26.13),
            config.get("longitude", 27.97),
            capacity,
            forecast_date,
            hour,
        )
        cloud_estimate = 1.0 - (persistence_val / clear_sky) if clear_sky > 0 else 0.5
        cloud_estimate = max(0.0, min(1.0, cloud_estimate))

        # Temperature estimate (seasonal — JHB)
        month = forecast_date.month
        seasonal_temps = {1: 25, 2: 24, 3: 22, 4: 19, 5: 16, 6: 13, 7: 13, 8: 16, 9: 19, 10: 21, 11: 23, 12: 25}
        temp = seasonal_temps.get(month, 20)

        # Yesterday generation (from persistence cache)
        yesterday_gen = persistence_val

        features = [hour, day_of_year, cloud_estimate, temp, yesterday_gen]
        return model.predict(features)

    def _ensemble_forecast(
        self,
        site_id: str,
        lat: float,
        lng: float,
        capacity_kwp: float,
        forecast_date: date,
        hour: int,
    ) -> float:
        """Weighted ensemble: 20% persistence + 20% clear-sky + 30% historical + 30% ML.

        The ensemble smooths out noise from individual models:
        - Persistence captures yesterday's actual conditions
        - Clear-sky captures the theoretical envelope
        - Historical captures seasonal and weekday patterns
        - ML captures non-linear patterns from training data
        """
        persistence = self._persistence_forecast(site_id, hour)
        clear_sky = self._get_clear_sky_generation(lat, lng, capacity_kwp, forecast_date, hour) * 0.85
        historical = self._historical_forecast(site_id, hour)
        ml = self._ml_forecast(site_id, forecast_date, hour)

        ensemble = (
            self.WEIGHT_PERSISTENCE * persistence
            + self.WEIGHT_CLEAR_SKY * clear_sky
            + self.WEIGHT_HISTORICAL * historical
            + self.WEIGHT_ML * ml
        )
        return max(0.0, ensemble)

    # === ML Model Training (34-08) ===

    def _train_ml_models(self) -> None:
        """Train gradient boosting models for all registered sites.

        Generates 90 days of synthetic training data and fits a simple
        decision-tree ensemble model. This is a foundation — full
        LSTM/transformer models are future work beyond Phase 34.
        """
        for site_id, config in self._site_configs.items():
            try:
                model = self._train_site_model(site_id, config)
                if model:
                    self._ml_models[site_id] = model
                    logger.info("Trained ML forecast model for site %s", site_id)
            except Exception as e:
                logger.error("Failed to train ML model for %s: %s", site_id, e)

    def _train_site_model(self, site_id: str, config: Dict) -> Optional["_GradientBoostingModel"]:
        """Train ML model for a single site on 90 days of synthetic data.

        Features: hour_of_day, day_of_year, cloud_cover, temperature, yesterday_gen
        Target: generation_kw
        """
        lat = config["latitude"]
        lng = config["longitude"]
        capacity = config["capacity_kwp"]
        today = date.today()

        # Generate 90 days of training data
        features_list: List[List[float]] = []
        targets: List[float] = []

        for day_offset in range(90, 0, -1):
            d = today - timedelta(days=day_offset)
            seed = hash(f"{site_id}-train-{d.isoformat()}") % 10000
            profile = self._generate_realistic_profile(lat, lng, capacity, d, cloud_seed=seed)
            day_of_year = d.timetuple().tm_yday

            # Seasonal temperature
            month = d.month
            seasonal_temps = {1: 25, 2: 24, 3: 22, 4: 19, 5: 16, 6: 13, 7: 13, 8: 16, 9: 19, 10: 21, 11: 23, 12: 25}
            temp = seasonal_temps.get(month, 20)

            # Yesterday's profile for feature
            yesterday = today - timedelta(days=day_offset + 1)
            yesterday_seed = hash(f"{site_id}-train-{yesterday.isoformat()}") % 10000
            yesterday_profile = self._generate_realistic_profile(
                lat, lng, capacity, yesterday, cloud_seed=yesterday_seed
            )

            for hour in range(24):
                cs = self._get_clear_sky_generation(lat, lng, capacity, d, hour)
                actual = profile[hour]
                cloud = 1.0 - (actual / cs) if cs > 0 else 0.5
                cloud = max(0.0, min(1.0, cloud))

                yesterday_gen = yesterday_profile[hour] if hour < len(yesterday_profile) else 0.0

                features_list.append([hour, day_of_year, cloud, temp, yesterday_gen])
                targets.append(actual)

        if not features_list:
            return None

        # Train the model
        model = _GradientBoostingModel(capacity_kwp=capacity)
        model.fit(features_list, targets)

        # Calculate accuracy on the training data (in-sample, for tracking)
        predictions = [model.predict(f) for f in features_list]
        rmse = math.sqrt(sum((p - t) ** 2 for p, t in zip(predictions, targets)) / len(targets))
        mae = sum(abs(p - t) for p, t in zip(predictions, targets)) / len(targets)

        self._ml_accuracy[site_id] = {
            "training_samples": len(targets),
            "rmse_kw": rmse,
            "mae_kw": mae,
            "rmse_pct_of_capacity": (rmse / capacity * 100) if capacity > 0 else 0,
        }
        logger.info(
            "ML model for %s: RMSE=%.1f kW (%.1f%% of capacity), MAE=%.1f kW",
            site_id,
            rmse,
            self._ml_accuracy[site_id]["rmse_pct_of_capacity"],
            mae,
        )

        return model

    def train_site_model(self, site_id: str) -> bool:
        """Public API: retrain ML model for a site.

        Returns True if training succeeded.
        """
        config = self._site_configs.get(site_id)
        if not config:
            return False
        model = self._train_site_model(site_id, config)
        if model:
            self._ml_models[site_id] = model
            return True
        return False

    def get_ml_forecast(self, site_id: str, hours_ahead: int = 24) -> List[HourlyGeneration]:
        """Get ML-only forecast for a site.

        Returns hourly generation predictions using only the gradient boosting model.
        """
        config = self._site_configs.get(site_id)
        if not config:
            return []

        lat = config["latitude"]
        lng = config["longitude"]
        capacity = config["capacity_kwp"]
        now = datetime.now(timezone.utc)
        sast_now = now + timedelta(hours=2)

        result: List[HourlyGeneration] = []
        for offset in range(hours_ahead):
            forecast_dt = sast_now + timedelta(hours=offset)
            forecast_hour = forecast_dt.hour
            forecast_date = forecast_dt.date()

            gen_kw = self._ml_forecast(site_id, forecast_date, forecast_hour)
            cs_kw = self._get_clear_sky_generation(lat, lng, capacity, forecast_date, forecast_hour)

            uncertainty_pct = min(0.30, 0.05 + offset * 0.005)
            hour_ts = forecast_dt.strftime("%Y-%m-%dT%H:%M")

            result.append(
                HourlyGeneration(
                    hour=hour_ts,
                    generation_kw=gen_kw,
                    confidence_high_kw=gen_kw * (1.0 + uncertainty_pct),
                    confidence_low_kw=max(0.0, gen_kw * (1.0 - uncertainty_pct)),
                    clear_sky_kw=cs_kw,
                    cloud_factor=(gen_kw / cs_kw) if cs_kw > 0 else 0.0,
                )
            )

        return result

    def get_ml_accuracy(self, site_id: str) -> Optional[Dict[str, Any]]:
        """Get ML model accuracy metrics for a site."""
        return self._ml_accuracy.get(site_id)


class _GradientBoostingModel:
    """Simple gradient boosting regression model.

    Implements a lightweight ensemble of decision stumps (depth-1 trees)
    trained with gradient boosting on MSE loss. No external dependencies
    required (no scikit-learn, no xgboost).

    This is deliberately simple — a foundation for future ML work.
    Production models would use scikit-learn GradientBoostingRegressor
    or XGBoost/LightGBM.
    """

    def __init__(
        self,
        n_estimators: int = 50,
        learning_rate: float = 0.1,
        capacity_kwp: float = 3900,
    ):
        self.n_estimators = n_estimators
        self.learning_rate = learning_rate
        self.capacity_kwp = capacity_kwp
        self._trees: List[Dict[str, Any]] = []
        self._base_prediction: float = 0.0

    def fit(self, features: List[List[float]], targets: List[float]) -> None:
        """Train the model using gradient boosting on decision stumps."""
        n = len(targets)
        if n == 0:
            return

        # Start with mean prediction
        self._base_prediction = sum(targets) / n

        # Residuals
        residuals = [t - self._base_prediction for t in targets]

        for _ in range(self.n_estimators):
            # Find best split (decision stump)
            best_stump = self._find_best_stump(features, residuals)
            if best_stump is None:
                break

            self._trees.append(best_stump)

            # Update residuals
            for i in range(n):
                pred = self._predict_stump(best_stump, features[i])
                residuals[i] -= self.learning_rate * pred

    def predict(self, features: List[float]) -> float:
        """Predict generation for a single feature vector."""
        prediction = self._base_prediction
        for tree in self._trees:
            prediction += self.learning_rate * self._predict_stump(tree, features)
        # Clamp to [0, capacity]
        return max(0.0, min(self.capacity_kwp, prediction))

    def _find_best_stump(
        self,
        features: List[List[float]],
        residuals: List[float],
    ) -> Optional[Dict[str, Any]]:
        """Find the best single-feature split that minimises MSE of residuals."""
        n = len(features)
        if n < 4:
            return None

        n_features = len(features[0])
        best_mse = float("inf")
        best_stump = None

        for feat_idx in range(n_features):
            # Get unique split points (sample to keep fast)
            values = sorted(set(f[feat_idx] for f in features))
            if len(values) < 2:
                continue

            # Test a subset of split points for speed
            step = max(1, len(values) // 20)
            split_candidates = values[::step]

            for split_val in split_candidates:
                left_residuals = []
                right_residuals = []

                for i in range(n):
                    if features[i][feat_idx] <= split_val:
                        left_residuals.append(residuals[i])
                    else:
                        right_residuals.append(residuals[i])

                if len(left_residuals) < 2 or len(right_residuals) < 2:
                    continue

                left_mean = sum(left_residuals) / len(left_residuals)
                right_mean = sum(right_residuals) / len(right_residuals)

                # MSE reduction
                mse = sum((r - left_mean) ** 2 for r in left_residuals) + sum(
                    (r - right_mean) ** 2 for r in right_residuals
                )

                if mse < best_mse:
                    best_mse = mse
                    best_stump = {
                        "feature": feat_idx,
                        "threshold": split_val,
                        "left_value": left_mean,
                        "right_value": right_mean,
                    }

        return best_stump

    @staticmethod
    def _predict_stump(stump: Dict[str, Any], features: List[float]) -> float:
        """Predict using a single decision stump."""
        if features[stump["feature"]] <= stump["threshold"]:
            return stump["left_value"]
        return stump["right_value"]


# === Singleton ===

_solar_forecast_service: Optional[SolarForecastService] = None


def get_solar_forecast_service() -> SolarForecastService:
    """Get the singleton solar forecast service instance."""
    global _solar_forecast_service
    if _solar_forecast_service is None:
        _solar_forecast_service = SolarForecastService()
    return _solar_forecast_service
