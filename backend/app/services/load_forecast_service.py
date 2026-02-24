"""Load Forecast Service — 15-minute building demand forecast (gradient boosting).

Provides 96-interval (24-hour) demand forecasts using scikit-learn
GradientBoostingRegressor trained on synthetic load profiles derived from
solar_demand_service._simulated_building_load().

Features per interval:
  - hour_of_day (0-23.75 in 0.25 steps)
  - day_of_week (0=Mon..6=Sun)
  - month (1-12)
  - is_weekend (0/1)
  - ambient_temp_c (JHB seasonal curve)
  - solar_generation_kw (from solar forecast or synthetic)
  - prev_interval_demand_kw
  - prev_day_same_interval_kw

Training: 90 days synthetic from solar_demand_service load curves
Output: 96 intervals (24h) with confidence bands

Follows the singleton + GBR pattern from solar_forecast_service.py.
"""

import logging
import math
import random
from datetime import datetime, date, timezone, timedelta
from typing import Dict, List, Optional, Any

import numpy as np
from sklearn.ensemble import GradientBoostingRegressor

from app.models.load_forecast import LoadForecast, LoadInterval

logger = logging.getLogger(__name__)

# JHB seasonal temperatures (monthly averages)
_SEASONAL_TEMPS = {
    1: 25,
    2: 24,
    3: 22,
    4: 19,
    5: 16,
    6: 13,
    7: 13,
    8: 16,
    9: 19,
    10: 21,
    11: 23,
    12: 25,
}

# TOU peak hours (SAST) for Site-002
_PEAK_HOURS = {7, 8, 9, 18, 19}


def _simulated_building_load(hour: float, rng: Optional[random.Random] = None) -> float:
    """Simulate Site-002 building load profile (kW) by hour of day.

    Sandton office tower: base load ~900 kW (overnight), peak ~1750-1850 kW
    during business hours (09:30-15:00). Morning ramp 06:00-09:30.

    Matches solar_demand_service._simulated_building_load() but accepts an
    optional seeded RNG for reproducibility.
    """
    noise = rng.uniform(-1, 1) if rng else random.uniform(-1, 1)

    if hour < 5:
        return 900 + noise * 30
    elif hour < 6:
        return 900 + (hour - 5) * 100 + noise * 20
    elif hour < 7:
        return 1000 + (hour - 6) * 200 + noise * 25
    elif hour < 8:
        return 1200 + (hour - 7) * 250 + noise * 30
    elif hour < 9:
        return 1450 + (hour - 8) * 200 + noise * 30
    elif hour < 9.5:
        return 1650 + (hour - 9) * 200 + noise * 25
    elif hour < 10:
        return 1750 + noise * 40
    elif hour < 12:
        return 1700 + noise * 50
    elif hour < 13:
        return 1650 + noise * 40
    elif hour < 14:
        return 1700 + noise * 50
    elif hour < 15:
        return 1850 + noise * 50  # afternoon peak
    elif hour < 16:
        return 1750 + noise * 40
    elif hour < 17:
        return 1550 + noise * 40
    elif hour < 18:
        return 1300 + noise * 30
    elif hour < 19:
        return 1100 + noise * 25
    elif hour < 20:
        return 1000 + noise * 20
    elif hour < 22:
        return 950 + noise * 20
    else:
        return 900 + noise * 20


def _synthetic_solar_kw(hour: float) -> float:
    """Synthetic solar generation for a clear day (kW). Bell curve peaking at ~3200 kW noon."""
    if hour < 6 or hour > 19:
        return 0.0
    peak_hour = 12.5
    spread = 3.5
    return 3200.0 * math.exp(-0.5 * ((hour - peak_hour) / spread) ** 2)


class LoadForecastService:
    """15-minute building load forecast using GradientBoostingRegressor.

    On init, generates 90 days of synthetic training data and fits a GBR
    model. Provides get_forecast() for 96-interval (24h) lookahead and
    get_current_load() for the instantaneous predicted demand.
    """

    N_FEATURES = 8
    INTERVALS_PER_HOUR = 4  # 15-minute intervals
    INTERVALS_PER_DAY = 96

    def __init__(self):
        self._models: Dict[str, GradientBoostingRegressor] = {}
        self._accuracy: Dict[str, Dict[str, float]] = {}
        self._last_forecast_cache: Dict[str, LoadForecast] = {}
        self._train_all_sites()

    def _train_all_sites(self) -> None:
        """Train models for all known sites. Currently just site-002."""
        for site_id in ["site-002"]:
            try:
                self._train_site(site_id)
            except Exception as e:
                logger.error("Failed to train load forecast for %s: %s", site_id, e)

    def _train_site(self, site_id: str) -> None:
        """Train a GBR model for a site on 90 days of synthetic 15-min data."""
        today = date.today()
        features_list: List[List[float]] = []
        targets: List[float] = []

        for day_offset in range(90, 0, -1):
            d = today - timedelta(days=day_offset)
            rng = random.Random(hash(f"{site_id}-load-{d.isoformat()}") % 100000)
            day_of_week = d.weekday()
            month = d.month
            is_weekend = 1.0 if day_of_week >= 5 else 0.0
            temp = _SEASONAL_TEMPS.get(month, 20)

            # Weekend load reduction factor
            weekend_factor = 0.65 if is_weekend else 1.0

            # Generate full day at 15-min resolution
            day_demands = []
            for interval in range(self.INTERVALS_PER_DAY):
                hour = interval / self.INTERVALS_PER_HOUR
                base_demand = _simulated_building_load(hour, rng) * weekend_factor
                day_demands.append(max(0.0, base_demand))

            # Previous day's demands for lagged feature
            prev_date = d - timedelta(days=1)
            prev_rng = random.Random(hash(f"{site_id}-load-{prev_date.isoformat()}") % 100000)
            prev_weekend = 1.0 if prev_date.weekday() >= 5 else 0.0
            prev_weekend_factor = 0.65 if prev_weekend else 1.0
            prev_demands = []
            for interval in range(self.INTERVALS_PER_DAY):
                hour = interval / self.INTERVALS_PER_HOUR
                prev_demands.append(max(0.0, _simulated_building_load(hour, prev_rng) * prev_weekend_factor))

            for interval in range(self.INTERVALS_PER_DAY):
                hour = interval / self.INTERVALS_PER_HOUR
                solar_kw = _synthetic_solar_kw(hour) * rng.uniform(0.3, 1.0)
                prev_interval = day_demands[interval - 1] if interval > 0 else day_demands[0]
                prev_day_same = prev_demands[interval]

                features_list.append(
                    [
                        hour,
                        float(day_of_week),
                        float(month),
                        is_weekend,
                        float(temp),
                        solar_kw,
                        prev_interval,
                        prev_day_same,
                    ]
                )
                targets.append(day_demands[interval])

        X = np.array(features_list)
        y = np.array(targets)

        model = GradientBoostingRegressor(
            n_estimators=100,
            max_depth=4,
            learning_rate=0.1,
            subsample=0.8,
            random_state=42,
        )
        model.fit(X, y)

        # In-sample accuracy
        predictions = model.predict(X)
        rmse = float(np.sqrt(np.mean((predictions - y) ** 2)))
        mae = float(np.mean(np.abs(predictions - y)))
        r2 = float(1.0 - np.sum((y - predictions) ** 2) / np.sum((y - np.mean(y)) ** 2))

        self._models[site_id] = model
        self._accuracy[site_id] = {
            "rmse_kw": rmse,
            "mae_kw": mae,
            "r2_score": r2,
            "training_samples": len(targets),
        }

        logger.info(
            "Load forecast model trained for %s: RMSE=%.1f kW, MAE=%.1f kW, R²=%.3f (%d samples)",
            site_id,
            rmse,
            mae,
            r2,
            len(targets),
        )

    def retrain(self, site_id: str) -> bool:
        """Public API: retrain the model for a site. Returns True on success."""
        try:
            self._train_site(site_id)
            # Invalidate forecast cache
            self._last_forecast_cache.pop(site_id, None)
            return True
        except Exception as e:
            logger.error("Retrain failed for %s: %s", site_id, e)
            return False

    def get_forecast(self, site_id: str, intervals_ahead: int = 96) -> LoadForecast:
        """Generate a 15-minute load forecast.

        Args:
            site_id: Site identifier
            intervals_ahead: Number of 15-min intervals (default 96 = 24h)

        Returns:
            LoadForecast with per-interval predictions and confidence bands.
        """
        model = self._models.get(site_id)
        now = datetime.now(timezone.utc)
        sast_now = now + timedelta(hours=2)

        if not model:
            return LoadForecast(
                site_id=site_id,
                generated_at=now.isoformat(),
                model="gradient_boosting",
            )

        intervals: List[LoadInterval] = []
        total_demand = 0.0
        peak_demand = 0.0

        for offset in range(intervals_ahead):
            forecast_dt = sast_now + timedelta(minutes=offset * 15)
            hour = forecast_dt.hour + forecast_dt.minute / 60.0
            day_of_week = forecast_dt.weekday()
            month = forecast_dt.month
            is_weekend = 1.0 if day_of_week >= 5 else 0.0
            temp = float(_SEASONAL_TEMPS.get(month, 20))
            solar_kw = _synthetic_solar_kw(hour)

            # Previous interval demand (use last predicted or current load)
            if intervals:
                prev_interval = intervals[-1].demand_kw
            else:
                prev_interval = self.get_current_load(site_id)

            # Previous day same interval (approximate with current model prediction)
            prev_day_dt = forecast_dt - timedelta(days=1)
            prev_day_hour = prev_day_dt.hour + prev_day_dt.minute / 60.0
            prev_day_features = np.array(
                [
                    [
                        prev_day_hour,
                        float(prev_day_dt.weekday()),
                        float(prev_day_dt.month),
                        1.0 if prev_day_dt.weekday() >= 5 else 0.0,
                        float(_SEASONAL_TEMPS.get(prev_day_dt.month, 20)),
                        _synthetic_solar_kw(prev_day_hour),
                        prev_interval,
                        prev_interval,  # approximation
                    ]
                ]
            )
            prev_day_same = float(max(0.0, model.predict(prev_day_features)[0]))

            features = np.array(
                [
                    [
                        hour,
                        float(day_of_week),
                        float(month),
                        is_weekend,
                        temp,
                        solar_kw,
                        prev_interval,
                        prev_day_same,
                    ]
                ]
            )

            demand_kw = float(max(0.0, model.predict(features)[0]))

            # Confidence bands widen with forecast horizon
            uncertainty_pct = min(0.25, 0.03 + offset * 0.002)
            confidence_high = demand_kw * (1.0 + uncertainty_pct)
            confidence_low = max(0.0, demand_kw * (1.0 - uncertainty_pct))

            # Tariff band
            int_hour = int(hour)
            is_peak = int_hour in _PEAK_HOURS
            if int_hour >= 22 or int_hour < 6:
                tariff_band = "off_peak"
            elif is_peak:
                tariff_band = "peak"
            else:
                tariff_band = "standard"

            interval = LoadInterval(
                timestamp=forecast_dt.strftime("%Y-%m-%dT%H:%M"),
                demand_kw=demand_kw,
                confidence_high_kw=confidence_high,
                confidence_low_kw=confidence_low,
                is_peak_hour=is_peak,
                tariff_band=tariff_band,
            )
            intervals.append(interval)

            total_demand += demand_kw
            peak_demand = max(peak_demand, demand_kw)

        avg_demand = total_demand / max(1, len(intervals))
        total_energy = total_demand * 0.25  # each interval is 0.25 hours

        forecast = LoadForecast(
            site_id=site_id,
            generated_at=now.isoformat(),
            model="gradient_boosting",
            intervals=intervals,
            peak_demand_kw=peak_demand,
            avg_demand_kw=avg_demand,
            total_energy_kwh=total_energy,
            accuracy=self._accuracy.get(site_id),
        )

        # Cache for dispatch optimizer consumption
        self._last_forecast_cache[site_id] = forecast
        return forecast

    def get_current_load(self, site_id: str) -> float:
        """Get the predicted current building load (kW).

        Uses the model to predict demand for the current 15-min interval.
        Falls back to a simple profile if model is not trained.
        """
        model = self._models.get(site_id)
        now = datetime.now(timezone.utc)
        sast = now + timedelta(hours=2)
        hour = sast.hour + sast.minute / 60.0

        if not model:
            return _simulated_building_load(hour)

        day_of_week = sast.weekday()
        month = sast.month
        is_weekend = 1.0 if day_of_week >= 5 else 0.0
        temp = float(_SEASONAL_TEMPS.get(month, 20))
        solar_kw = _synthetic_solar_kw(hour)

        # Use simulated values for lagged features
        prev_demand = _simulated_building_load(max(0, hour - 0.25))
        prev_day_demand = _simulated_building_load(hour)

        features = np.array(
            [
                [
                    hour,
                    float(day_of_week),
                    float(month),
                    is_weekend,
                    temp,
                    solar_kw,
                    prev_demand,
                    prev_day_demand,
                ]
            ]
        )

        return float(max(0.0, model.predict(features)[0]))

    def get_cached_forecast(self, site_id: str) -> Optional[LoadForecast]:
        """Return the most recent cached forecast, or None."""
        return self._last_forecast_cache.get(site_id)

    def get_accuracy(self, site_id: str) -> Optional[Dict[str, Any]]:
        """Return model accuracy metrics for a site."""
        return self._accuracy.get(site_id)


# === Singleton ===

_load_forecast_service: Optional[LoadForecastService] = None


def get_load_forecast_service() -> LoadForecastService:
    """Get the singleton load forecast service instance."""
    global _load_forecast_service
    if _load_forecast_service is None:
        _load_forecast_service = LoadForecastService()
    return _load_forecast_service
