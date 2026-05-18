"""Weather service for fetching real-time weather data from OpenWeatherMap.

Provides outdoor temperature, humidity, and forecasts for AI optimization.
Free tier: 1000 calls/day, 1-minute cache.
"""

import logging
import os
from datetime import datetime, timedelta
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# OpenWeatherMap API configuration
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY", "")
OPENWEATHER_BASE_URL = "https://api.openweathermap.org/data/2.5"
DEFAULT_LAT = -26.1061  # Sandton, South Africa
DEFAULT_LON = 28.0531

# Cache weather data to stay within free tier limits
_weather_cache: dict[str, Any] = {}
_cache_timestamp: datetime | None = None
_CACHE_TTL_MINUTES = 10  # 10-minute cache


async def get_current_weather(
    lat: float = DEFAULT_LAT,
    lon: float = DEFAULT_LON,
) -> dict[str, Any] | None:
    """Fetch current weather from OpenWeatherMap.

    Returns:
        {
            "outdoor_temp": float,  # Celsius
            "humidity": float,      # %
            "pressure": float,      # hPa
            "wind_speed": float,    # m/s
            "weather": str,         # Description
            "timestamp": str,       # ISO format
        }
    """
    global _weather_cache, _cache_timestamp

    if not OPENWEATHER_API_KEY:
        logger.warning("[WEATHER] OPENWEATHER_API_KEY not set - weather data unavailable")
        return None

    # Check cache
    now = datetime.utcnow()
    if _cache_timestamp and (now - _cache_timestamp) < timedelta(minutes=_CACHE_TTL_MINUTES):
        if _weather_cache:
            logger.debug("[WEATHER] Returning cached weather data")
            return _weather_cache

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{OPENWEATHER_BASE_URL}/weather",
                params={
                    "lat": lat,
                    "lon": lon,
                    "appid": OPENWEATHER_API_KEY,
                    "units": "metric",
                },
            )
            resp.raise_for_status()
            data = resp.json()

        main = data.get("main", {})
        weather = data.get("weather", [{}])[0]
        wind = data.get("wind", {})

        result = {
            "outdoor_temp": float(main.get("temp", 20.0)),
            "humidity": float(main.get("humidity", 50.0)),
            "pressure": float(main.get("pressure", 1013.0)),
            "wind_speed": float(wind.get("speed", 0.0)),
            "weather": weather.get("description", "unknown"),
            "timestamp": datetime.utcnow().isoformat(),
        }

        # Update cache
        _weather_cache = result
        _cache_timestamp = now

        logger.info(
            f"[WEATHER] Fetched current weather: {result['outdoor_temp']:.1f}°C, {result['humidity']:.0f}% humidity"
        )
        return result

    except Exception as e:
        logger.error(f"[WEATHER] Failed to fetch weather: {e}")
        # Return cached data if available, even if stale
        if _weather_cache:
            logger.warning("[WEATHER] Returning stale cached data due to API failure")
            return _weather_cache
        return None


async def get_weather_forecast(
    lat: float = DEFAULT_LAT,
    lon: float = DEFAULT_LON,
    hours: int = 4,
) -> dict[str, Any] | None:
    """Fetch weather forecast from OpenWeatherMap.

    Args:
        hours: Number of hours to forecast (max 48 for free tier)

    Returns:
        {
            "outside_temp": float,  # Predicted temp
            "humidity": float,      # Predicted humidity
            "solar_load": float,    # Estimated 0.0-1.0 based on cloud cover
            "forecast_time": str,   # ISO format
        }
    """
    if not OPENWEATHER_API_KEY:
        logger.warning("[WEATHER] OPENWEATHER_API_KEY not set - forecast unavailable")
        return None

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{OPENWEATHER_BASE_URL}/forecast",
                params={
                    "lat": lat,
                    "lon": lon,
                    "appid": OPENWEATHER_API_KEY,
                    "units": "metric",
                    "cnt": min(hours // 3 + 1, 16),  # API returns 3-hour intervals
                },
            )
            resp.raise_for_status()
            data = resp.json()

        # Get forecast for the target hour
        forecasts = data.get("list", [])
        if not forecasts:
            return None

        # Use the forecast closest to target hours
        target_idx = min(hours // 3, len(forecasts) - 1)
        forecast = forecasts[target_idx]

        main = forecast.get("main", {})
        clouds = forecast.get("clouds", {}).get("all", 0)

        # Estimate solar load based on cloud cover (0-100% -> 1.0-0.0)
        solar_load = max(0.0, min(1.0, 1.0 - (clouds / 100)))

        result = {
            "outside_temp": float(main.get("temp", 20.0)),
            "humidity": float(main.get("humidity", 50.0)),
            "solar_load": solar_load,
            "forecast_time": forecast.get("dt_txt", ""),
        }

        logger.info(
            f"[WEATHER] Fetched {hours}h forecast: {result['outside_temp']:.1f}°C, "
            f"solar_load={result['solar_load']:.2f}"
        )
        return result

    except Exception as e:
        logger.error(f"[WEATHER] Failed to fetch forecast: {e}")
        return None


def get_weather_sync() -> dict[str, Any] | None:
    """Synchronous wrapper for getting current weather.

    Returns cached data or None if no API key.
    """
    if not OPENWEATHER_API_KEY:
        return None

    # Check if cache is fresh
    now = datetime.utcnow()
    if _cache_timestamp and (now - _cache_timestamp) < timedelta(minutes=_CACHE_TTL_MINUTES):
        return _weather_cache

    return None  # Cache miss - async function must be called
