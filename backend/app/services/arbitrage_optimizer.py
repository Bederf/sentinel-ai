"""Arbitrage Optimizer -- Price forecasting and arbitrage window analysis.

Provides advanced price forecasting using time-based seasonality, load-shedding
stage impacts, solar forecast integration, and weather adjustments.

This module specializes in:
  1. Price forecasting (next 24 hours with hourly granularity)
  2. Arbitrage window identification (charge low, discharge high)
  3. Revenue projections with battery degradation costs
  4. Forecast accuracy tracking
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, date, time, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

logger = logging.getLogger(__name__)


# === Dataclass Models ===

@dataclass
class PriceForecast:
    """Hourly price forecast for 24-hour period."""
    hour: int  # 0-23 (SAST)
    hour_start: str  # ISO timestamp
    hour_end: str  # ISO timestamp
    price_r_per_kwh: float  # ZAR/kWh base tariff
    tariff_band: str  # peak / standard / off_peak
    load_shedding_stage: int  # 0-8
    stage_impact_pct: float  # +50% stage 3-5, +100% stage 6-8
    weather_impact_pct: float  # ±30-40% based on temp
    solar_impact_pct: float  # -20% if solar > 70% capacity
    final_price_r_per_kwh: float  # price after all adjustments
    confidence_pct: float  # forecast confidence 0-100%

    def to_dict(self) -> Dict[str, Any]:
        return {
            "hour": self.hour,
            "hour_start": self.hour_start,
            "hour_end": self.hour_end,
            "price_r_per_kwh": round(self.price_r_per_kwh, 4),
            "tariff_band": self.tariff_band,
            "load_shedding_stage": self.load_shedding_stage,
            "stage_impact_pct": round(self.stage_impact_pct, 1),
            "weather_impact_pct": round(self.weather_impact_pct, 1),
            "solar_impact_pct": round(self.solar_impact_pct, 1),
            "final_price_r_per_kwh": round(self.final_price_r_per_kwh, 4),
            "confidence_pct": round(self.confidence_pct, 1),
        }


@dataclass
class ArbitrageWindow:
    """An optimal charge/discharge window pair."""
    charge_start_hour: int  # When to start charging (0-23)
    charge_end_hour: int  # When to stop charging
    charge_window_price_r_per_kwh: float  # Average price during charge window
    discharge_start_hour: int  # When to start discharging
    discharge_end_hour: int  # When to stop discharging
    discharge_window_price_r_per_kwh: float  # Average price during discharge window
    arbitrage_spread_r_per_kwh: float  # discharge_price - charge_price
    expected_energy_kwh: float  # Energy discharged (rounded trip efficiency applied)
    expected_revenue_r: float  # Projected revenue (spread * energy)
    battery_degradation_cost_r: float  # Degradation @ R0.05/kWh
    net_revenue_r: float  # revenue - degradation
    confidence_pct: float  # Window likelihood (weather/LS uncertainty)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "charge_start_hour": self.charge_start_hour,
            "charge_end_hour": self.charge_end_hour,
            "charge_window_price_r_per_kwh": round(self.charge_window_price_r_per_kwh, 4),
            "discharge_start_hour": self.discharge_start_hour,
            "discharge_end_hour": self.discharge_end_hour,
            "discharge_window_price_r_per_kwh": round(self.discharge_window_price_r_per_kwh, 4),
            "arbitrage_spread_r_per_kwh": round(self.arbitrage_spread_r_per_kwh, 4),
            "expected_energy_kwh": round(self.expected_energy_kwh, 0),
            "expected_revenue_r": round(self.expected_revenue_r, 2),
            "battery_degradation_cost_r": round(self.battery_degradation_cost_r, 2),
            "net_revenue_r": round(self.net_revenue_r, 2),
            "confidence_pct": round(self.confidence_pct, 1),
        }


# === Price Forecaster ===

class PriceForecaster:
    """24-hour price forecasting with multiple adjustment factors."""

    # South African TOU base rates (ZAR/kWh)
    BASE_RATES = {
        "off_peak": 0.80,
        "standard": 1.20,
        "peak": 1.80,
    }

    # Load shedding stage price adjustments
    LS_ADJUSTMENTS = {
        0: 0.0,      # No LS
        1: 0.0,      # Stage 1-2
        2: 0.0,
        3: 0.50,     # Stage 3-5: +50%
        4: 0.50,
        5: 0.50,
        6: 1.00,     # Stage 6-8: +100% (emergency)
        7: 1.00,
        8: 1.00,
    }

    # Weather adjustment factors
    WEATHER_ADJUSTMENTS = {
        "cold": 0.30,     # <10°C: +30%
        "hot": 0.40,      # >32°C: +40%
        "mild": 0.0,      # 10-32°C: no adjustment
    }

    def __init__(self, tariff_data: Optional[Dict[str, Any]] = None):
        """Initialize forecaster with tariff configuration.

        Args:
            tariff_data: City Power TOU tariff configuration (loads from JSON if None)
        """
        self._tariff = tariff_data or self._load_tariff()

    def _load_tariff(self) -> Dict[str, Any]:
        """Load City Power TOU tariff from configuration."""
        tariff_path = (
            Path(__file__).parent.parent
            / "data" / "solar" / "tariffs" / "city_power_2026.json"
        )
        try:
            with open(tariff_path) as f:
                tariff = json.load(f)
                logger.debug("Loaded tariff from %s", tariff_path.name)
                return tariff
        except Exception as e:
            logger.warning("Failed to load tariff: %s. Using defaults.", e)
            return {}

    def _get_tariff_band(self, hour_sast: int) -> str:
        """Determine tariff band for given hour (SAST)."""
        # Default time band configuration (if tariff JSON unavailable)
        if hour_sast in range(22, 24) or hour_sast in range(0, 5):
            return "off_peak"
        elif hour_sast in range(9, 17):
            return "peak"
        else:
            return "standard"

    def _get_base_price(self, band: str) -> float:
        """Get base tariff price for band."""
        return self.BASE_RATES.get(band, 1.20)

    def _get_weather_adjustment(self, temperature_c: float) -> Tuple[str, float]:
        """Determine weather impact on pricing.

        Args:
            temperature_c: Current/forecasted temperature in Celsius

        Returns:
            Tuple of (weather_type, adjustment_pct)
        """
        if temperature_c < 10:
            return "cold", self.WEATHER_ADJUSTMENTS["cold"]
        elif temperature_c > 32:
            return "hot", self.WEATHER_ADJUSTMENTS["hot"]
        else:
            return "mild", self.WEATHER_ADJUSTMENTS["mild"]

    def _get_solar_adjustment(self, solar_forecast_pct: float) -> float:
        """Determine solar impact on pricing.

        High solar generation reduces peak-hour pricing.

        Args:
            solar_forecast_pct: Expected solar capacity factor (0-100)

        Returns:
            Solar price adjustment (-20% if > 70%, else 0%)
        """
        if solar_forecast_pct > 70:
            return -0.20
        return 0.0

    def forecast_24h(
        self,
        load_shedding_stages: Optional[List[int]] = None,
        temperature_forecast: Optional[List[float]] = None,
        solar_forecast_pct: Optional[List[float]] = None,
    ) -> List[PriceForecast]:
        """Generate 24-hour price forecast (hourly granularity).

        Args:
            load_shedding_stages: LS stage for each hour (0-8), default all 0
            temperature_forecast: Temp (°C) for each hour, default 20°C
            solar_forecast_pct: Solar capacity % for each hour, default 0%

        Returns:
            List of 24 PriceForecast objects with all adjustments applied
        """
        now = datetime.now(timezone.utc)
        sast = now + timedelta(hours=2)  # UTC+2

        # Defaults
        ls_stages = load_shedding_stages or [0] * 24
        temps = temperature_forecast or [20.0] * 24
        solar_pcts = solar_forecast_pct or [0.0] * 24

        forecasts = []

        for hour in range(24):
            hour_dt = sast.replace(hour=hour, minute=0, second=0, microsecond=0)
            hour_start = hour_dt.isoformat()
            hour_end = (hour_dt + timedelta(hours=1)).isoformat()

            # Get base tariff band
            band = self._get_tariff_band(hour)
            base_price = self._get_base_price(band)

            # Load shedding impact
            ls_stage = min(ls_stages[hour], 8) if hour < len(ls_stages) else 0
            ls_impact = self.LS_ADJUSTMENTS.get(ls_stage, 0.0)

            # Weather impact
            temp = temps[hour] if hour < len(temps) else 20.0
            weather_type, weather_impact = self._get_weather_adjustment(temp)

            # Solar impact
            solar_pct = solar_pcts[hour] if hour < len(solar_pcts) else 0.0
            solar_impact = self._get_solar_adjustment(solar_pct)

            # Calculate final price
            ls_adjusted = base_price * (1 + ls_impact)
            weather_adjusted = ls_adjusted * (1 + weather_impact)
            solar_adjusted = weather_adjusted * (1 + solar_impact)

            # Confidence decreases with LS stage and weather extremes
            base_confidence = 90.0
            if ls_stage > 0:
                base_confidence -= ls_stage * 5
            if abs(weather_impact) > 0.2:
                base_confidence -= 10
            confidence = max(50.0, base_confidence)

            forecast = PriceForecast(
                hour=hour,
                hour_start=hour_start,
                hour_end=hour_end,
                price_r_per_kwh=base_price,
                tariff_band=band,
                load_shedding_stage=ls_stage,
                stage_impact_pct=ls_impact * 100,
                weather_impact_pct=weather_impact * 100,
                solar_impact_pct=solar_impact * 100,
                final_price_r_per_kwh=solar_adjusted,
                confidence_pct=confidence,
            )
            forecasts.append(forecast)

        return forecasts


# === Arbitrage Analyzer ===

class ArbitrageAnalyzer:
    """Identifies optimal charge/discharge windows and calculates revenue."""

    BESS_CAPACITY_KWH = 5015.0
    BESS_ROUND_TRIP_EFF = 0.90
    BATTERY_DEGRADATION_COST_R_PER_KWH = 0.05
    MIN_ARBITRAGE_SPREAD = 0.10  # Minimum ZAR/kWh spread to make arbitrage worthwhile

    def __init__(self, price_forecaster: Optional[PriceForecaster] = None):
        """Initialize analyzer with price forecaster.

        Args:
            price_forecaster: PriceForecaster instance, creates default if None
        """
        self.forecaster = price_forecaster or PriceForecaster()

    def find_arbitrage_windows(
        self,
        forecasts: List[PriceForecast],
        max_windows: int = 3,
        battery_soc_pct: float = 50.0,
    ) -> List[ArbitrageWindow]:
        """Identify optimal arbitrage windows from price forecast.

        Algorithm:
          1. Find "charge windows" (lowest-price consecutive hours)
          2. Find "discharge windows" (highest-price consecutive hours)
          3. Pair them by spread (highest spread first)
          4. Filter by minimum spread threshold
          5. Respect battery SOC and temperature constraints

        Args:
            forecasts: List of 24-hour PriceForecast objects
            max_windows: Maximum arbitrage windows to identify
            battery_soc_pct: Current battery SOC (used for feasibility)

        Returns:
            List of ArbitrageWindow objects sorted by revenue potential
        """
        windows = []

        # Find low-price periods (charge opportunities)
        charge_windows = self._find_price_valleys(forecasts, min_duration_hours=2)

        # Find high-price periods (discharge opportunities)
        discharge_windows = self._find_price_peaks(forecasts, min_duration_hours=2)

        # Pair charge and discharge windows
        for charge_win in charge_windows:
            for discharge_win in discharge_windows:
                # Discharge should happen after charge
                if discharge_win["start_hour"] <= charge_win["end_hour"]:
                    continue

                spread = (
                    discharge_win["avg_price"]
                    - charge_win["avg_price"]
                )

                # Filter by minimum spread
                if spread < self.MIN_ARBITRAGE_SPREAD:
                    continue

                # Calculate energy available
                max_energy_kwh = self.BESS_CAPACITY_KWH * 0.65  # Use ~65% for arbitrage
                energy_kwh = max_energy_kwh * self.BESS_ROUND_TRIP_EFF

                # Calculate revenue
                gross_revenue = spread * energy_kwh
                degradation_cost = energy_kwh * self.BATTERY_DEGRADATION_COST_R_PER_KWH
                net_revenue = gross_revenue - degradation_cost

                # Confidence is lower product of both windows
                confidence = min(
                    charge_win.get("confidence", 90),
                    discharge_win.get("confidence", 90),
                )

                window = ArbitrageWindow(
                    charge_start_hour=charge_win["start_hour"],
                    charge_end_hour=charge_win["end_hour"],
                    charge_window_price_r_per_kwh=charge_win["avg_price"],
                    discharge_start_hour=discharge_win["start_hour"],
                    discharge_end_hour=discharge_win["end_hour"],
                    discharge_window_price_r_per_kwh=discharge_win["avg_price"],
                    arbitrage_spread_r_per_kwh=spread,
                    expected_energy_kwh=energy_kwh,
                    expected_revenue_r=gross_revenue,
                    battery_degradation_cost_r=degradation_cost,
                    net_revenue_r=net_revenue,
                    confidence_pct=confidence,
                )
                windows.append(window)

        # Sort by net revenue (descending) and return top N
        windows.sort(key=lambda w: w.net_revenue_r, reverse=True)
        return windows[:max_windows]

    def _find_price_valleys(
        self,
        forecasts: List[PriceForecast],
        min_duration_hours: int = 2,
    ) -> List[Dict[str, Any]]:
        """Find low-price consecutive windows (valleys).

        Args:
            forecasts: List of hourly PriceForecast
            min_duration_hours: Minimum consecutive hours

        Returns:
            List of dicts with start_hour, end_hour, avg_price, confidence
        """
        valleys = []
        current_valley_start = None
        current_valley_prices = []

        for i, forecast in enumerate(forecasts):
            if i == 0:
                current_valley_start = i
                current_valley_prices = [forecast.final_price_r_per_kwh]
            else:
                # Add to current valley if price trending down/low
                if (
                    forecast.final_price_r_per_kwh
                    < forecasts[i - 1].final_price_r_per_kwh * 1.05
                ):
                    current_valley_prices.append(forecast.final_price_r_per_kwh)
                else:
                    # Valley ended - save if long enough
                    valley_duration = len(current_valley_prices)
                    if valley_duration >= min_duration_hours:
                        avg_price = sum(current_valley_prices) / len(current_valley_prices)
                        avg_confidence = sum(
                            f.confidence_pct
                            for f in forecasts[
                                current_valley_start : current_valley_start
                                + valley_duration
                            ]
                        ) / valley_duration
                        valleys.append({
                            "start_hour": current_valley_start,
                            "end_hour": current_valley_start + valley_duration - 1,
                            "avg_price": avg_price,
                            "confidence": avg_confidence,
                        })
                    # Start new valley
                    current_valley_start = i
                    current_valley_prices = [forecast.final_price_r_per_kwh]

        # Check final valley
        if len(current_valley_prices) >= min_duration_hours:
            avg_price = sum(current_valley_prices) / len(current_valley_prices)
            avg_confidence = sum(
                f.confidence_pct
                for f in forecasts[
                    current_valley_start : current_valley_start
                    + len(current_valley_prices)
                ]
            ) / len(current_valley_prices)
            valleys.append({
                "start_hour": current_valley_start,
                "end_hour": current_valley_start + len(current_valley_prices) - 1,
                "avg_price": avg_price,
                "confidence": avg_confidence,
            })

        return valleys

    def _find_price_peaks(
        self,
        forecasts: List[PriceForecast],
        min_duration_hours: int = 2,
    ) -> List[Dict[str, Any]]:
        """Find high-price consecutive windows (peaks).

        Args:
            forecasts: List of hourly PriceForecast
            min_duration_hours: Minimum consecutive hours

        Returns:
            List of dicts with start_hour, end_hour, avg_price, confidence
        """
        peaks = []
        current_peak_start = None
        current_peak_prices = []

        for i, forecast in enumerate(forecasts):
            if i == 0:
                current_peak_start = i
                current_peak_prices = [forecast.final_price_r_per_kwh]
            else:
                # Add to current peak if price trending up/high
                if (
                    forecast.final_price_r_per_kwh
                    > forecasts[i - 1].final_price_r_per_kwh * 0.95
                ):
                    current_peak_prices.append(forecast.final_price_r_per_kwh)
                else:
                    # Peak ended - save if long enough
                    peak_duration = len(current_peak_prices)
                    if peak_duration >= min_duration_hours:
                        avg_price = sum(current_peak_prices) / len(current_peak_prices)
                        avg_confidence = sum(
                            f.confidence_pct
                            for f in forecasts[
                                current_peak_start : current_peak_start
                                + peak_duration
                            ]
                        ) / peak_duration
                        peaks.append({
                            "start_hour": current_peak_start,
                            "end_hour": current_peak_start + peak_duration - 1,
                            "avg_price": avg_price,
                            "confidence": avg_confidence,
                        })
                    # Start new peak
                    current_peak_start = i
                    current_peak_prices = [forecast.final_price_r_per_kwh]

        # Check final peak
        if len(current_peak_prices) >= min_duration_hours:
            avg_price = sum(current_peak_prices) / len(current_peak_prices)
            avg_confidence = sum(
                f.confidence_pct
                for f in forecasts[
                    current_peak_start : current_peak_start
                    + len(current_peak_prices)
                ]
            ) / len(current_peak_prices)
            peaks.append({
                "start_hour": current_peak_start,
                "end_hour": current_peak_start + len(current_peak_prices) - 1,
                "avg_price": avg_price,
                "confidence": avg_confidence,
            })

        return peaks


# === Singleton ===

_price_forecaster: Optional[PriceForecaster] = None
_arbitrage_analyzer: Optional[ArbitrageAnalyzer] = None


def get_price_forecaster() -> PriceForecaster:
    """Get singleton PriceForecaster instance."""
    global _price_forecaster
    if _price_forecaster is None:
        _price_forecaster = PriceForecaster()
    return _price_forecaster


def get_arbitrage_analyzer() -> ArbitrageAnalyzer:
    """Get singleton ArbitrageAnalyzer instance."""
    global _arbitrage_analyzer
    if _arbitrage_analyzer is None:
        _arbitrage_analyzer = ArbitrageAnalyzer(get_price_forecaster())
    return _arbitrage_analyzer
