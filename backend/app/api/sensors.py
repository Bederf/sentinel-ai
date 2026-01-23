"""Sensors API endpoints."""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

router = APIRouter()

# Load data directory
DATA_DIR = Path(__file__).parent.parent / "data"


def load_sensors() -> list[dict]:
    """Load sensors from JSON file."""
    sensors_file = DATA_DIR / "sensors.json"
    if sensors_file.exists():
        with open(sensors_file) as f:
            return json.load(f)
    return []


def load_readings() -> list[dict]:
    """Load readings from JSON file."""
    readings_file = DATA_DIR / "readings.json"
    if readings_file.exists():
        with open(readings_file) as f:
            return json.load(f)
    return []


def load_equipment() -> list[dict]:
    """Load equipment from JSON file."""
    equipment_file = DATA_DIR / "equipment.json"
    if equipment_file.exists():
        with open(equipment_file) as f:
            return json.load(f)
    return []


class SensorBase(BaseModel):
    """Base sensor model."""

    id: str
    equipment_id: str
    site_id: str
    type: str
    unit: str
    location: str
    name: str


class SensorResponse(SensorBase):
    """Sensor response with latest reading."""

    latest_value: Optional[float] = None
    latest_timestamp: Optional[str] = None


class SensorListResponse(BaseModel):
    """Response for sensor list."""

    total: int
    sensors: list[SensorResponse]


class ReadingResponse(BaseModel):
    """Single reading response."""

    timestamp: str
    value: float


class ReadingsResponse(BaseModel):
    """Response for sensor readings."""

    sensor_id: str
    sensor_name: str
    unit: str
    total: int
    readings: list[ReadingResponse]


class EnergyDataPoint(BaseModel):
    """Energy data point for a timestamp."""

    timestamp: str
    total_kw: float
    by_equipment_type: dict[str, float]


class EnergyResponse(BaseModel):
    """Response for site energy data."""

    site_id: str
    start_date: str
    end_date: str
    total_kwh: float
    avg_kw: float
    peak_kw: float
    data_points: list[EnergyDataPoint]


@router.get("/sensors", response_model=SensorListResponse)
async def list_sensors(
    site_id: Optional[str] = Query(None, description="Filter by site ID"),
    equipment_id: Optional[str] = Query(None, description="Filter by equipment ID"),
    sensor_type: Optional[str] = Query(None, alias="type", description="Filter by sensor type"),
) -> SensorListResponse:
    """
    List all sensors with optional filtering.

    Args:
        site_id: Filter by site ID
        equipment_id: Filter by equipment ID
        sensor_type: Filter by type (temperature, power, humidity, etc.)

    Returns:
        SensorListResponse with total count and list of sensors.
    """
    sensors = load_sensors()
    readings = load_readings()

    # Apply filters
    if site_id:
        sensors = [s for s in sensors if s["site_id"] == site_id]
    if equipment_id:
        sensors = [s for s in sensors if s["equipment_id"] == equipment_id]
    if sensor_type:
        sensors = [s for s in sensors if s["type"].lower() == sensor_type.lower()]

    # Get latest readings for each sensor
    sensor_readings: dict[str, tuple[str, float]] = {}
    for reading in readings:
        sensor_id = reading["sensor_id"]
        timestamp = reading["timestamp"]
        if sensor_id not in sensor_readings or timestamp > sensor_readings[sensor_id][0]:
            sensor_readings[sensor_id] = (timestamp, reading["value"])

    # Build response
    result = []
    for sensor in sensors:
        latest = sensor_readings.get(sensor["id"])
        result.append(
            SensorResponse(
                **sensor,
                latest_value=latest[1] if latest else None,
                latest_timestamp=latest[0] if latest else None,
            )
        )

    return SensorListResponse(total=len(result), sensors=result)


@router.get("/sensors/{sensor_id}", response_model=SensorResponse)
async def get_sensor(sensor_id: str) -> SensorResponse:
    """
    Get a single sensor by ID.

    Args:
        sensor_id: The sensor identifier.

    Returns:
        SensorResponse with sensor details.

    Raises:
        HTTPException: If sensor not found.
    """
    sensors = load_sensors()
    readings = load_readings()

    sensor = next((s for s in sensors if s["id"] == sensor_id), None)
    if not sensor:
        raise HTTPException(status_code=404, detail=f"Sensor {sensor_id} not found")

    # Get latest reading
    sensor_readings = [r for r in readings if r["sensor_id"] == sensor_id]
    latest = max(sensor_readings, key=lambda r: r["timestamp"]) if sensor_readings else None

    return SensorResponse(
        **sensor,
        latest_value=latest["value"] if latest else None,
        latest_timestamp=latest["timestamp"] if latest else None,
    )


@router.get("/sensors/{sensor_id}/readings", response_model=ReadingsResponse)
async def get_sensor_readings(
    sensor_id: str,
    start_date: Optional[str] = Query(None, description="Start date (ISO format)"),
    end_date: Optional[str] = Query(None, description="End date (ISO format)"),
    limit: int = Query(720, ge=1, le=10000, description="Max readings to return"),
) -> ReadingsResponse:
    """
    Get time-series readings for a sensor.

    Args:
        sensor_id: The sensor identifier.
        start_date: Optional start date filter (ISO format).
        end_date: Optional end date filter (ISO format).
        limit: Maximum number of readings to return (default 720 = 30 days hourly).

    Returns:
        ReadingsResponse with time-series data.

    Raises:
        HTTPException: If sensor not found.
    """
    sensors = load_sensors()
    readings = load_readings()

    sensor = next((s for s in sensors if s["id"] == sensor_id), None)
    if not sensor:
        raise HTTPException(status_code=404, detail=f"Sensor {sensor_id} not found")

    # Filter readings for this sensor
    sensor_readings = [r for r in readings if r["sensor_id"] == sensor_id]

    # Apply date filters
    if start_date:
        sensor_readings = [r for r in sensor_readings if r["timestamp"] >= start_date]
    if end_date:
        sensor_readings = [r for r in sensor_readings if r["timestamp"] <= end_date]

    # Sort by timestamp and limit
    sensor_readings = sorted(sensor_readings, key=lambda r: r["timestamp"])[-limit:]

    return ReadingsResponse(
        sensor_id=sensor_id,
        sensor_name=sensor["name"],
        unit=sensor["unit"],
        total=len(sensor_readings),
        readings=[
            ReadingResponse(timestamp=r["timestamp"], value=r["value"])
            for r in sensor_readings
        ],
    )


@router.get("/sites/{site_id}/energy", response_model=EnergyResponse)
async def get_site_energy(
    site_id: str,
    start_date: Optional[str] = Query(None, description="Start date (ISO format)"),
    end_date: Optional[str] = Query(None, description="End date (ISO format)"),
    resolution: str = Query("hourly", description="Resolution: hourly or daily"),
) -> EnergyResponse:
    """
    Get aggregated energy data for a site.

    Args:
        site_id: The site identifier.
        start_date: Optional start date filter.
        end_date: Optional end date filter.
        resolution: Data resolution (hourly or daily).

    Returns:
        EnergyResponse with aggregated energy data.

    Raises:
        HTTPException: If site not found or no data.
    """
    sensors = load_sensors()
    readings = load_readings()
    equipment = load_equipment()

    # Get power sensors for this site
    site_sensors = [s for s in sensors if s["site_id"] == site_id and s["type"] == "power"]
    if not site_sensors:
        raise HTTPException(status_code=404, detail=f"No energy data for site {site_id}")

    sensor_ids = {s["id"] for s in site_sensors}

    # Create equipment type lookup
    eq_lookup = {eq["id"]: eq["type"] for eq in equipment}
    sensor_eq_type = {
        s["id"]: eq_lookup.get(s["equipment_id"], "unknown") for s in site_sensors
    }

    # Filter readings
    site_readings = [r for r in readings if r["sensor_id"] in sensor_ids]

    if start_date:
        site_readings = [r for r in site_readings if r["timestamp"] >= start_date]
    if end_date:
        site_readings = [r for r in site_readings if r["timestamp"] <= end_date]

    if not site_readings:
        raise HTTPException(status_code=404, detail="No readings found for date range")

    # Aggregate by timestamp
    timestamp_data: dict[str, dict] = {}
    for reading in site_readings:
        ts = reading["timestamp"]
        if resolution == "daily":
            ts = ts[:10] + "T00:00:00"  # Truncate to day

        if ts not in timestamp_data:
            timestamp_data[ts] = {"total": 0, "by_type": {}}

        eq_type = sensor_eq_type.get(reading["sensor_id"], "unknown")
        timestamp_data[ts]["total"] += reading["value"]
        timestamp_data[ts]["by_type"][eq_type] = (
            timestamp_data[ts]["by_type"].get(eq_type, 0) + reading["value"]
        )

    # Build data points
    data_points = []
    for ts in sorted(timestamp_data.keys()):
        data = timestamp_data[ts]
        data_points.append(
            EnergyDataPoint(
                timestamp=ts,
                total_kw=round(data["total"], 2),
                by_equipment_type={k: round(v, 2) for k, v in data["by_type"].items()},
            )
        )

    # Calculate summary stats
    totals = [dp.total_kw for dp in data_points]
    total_kwh = sum(totals)  # Assuming hourly data
    avg_kw = total_kwh / len(totals) if totals else 0
    peak_kw = max(totals) if totals else 0

    timestamps = [r["timestamp"] for r in site_readings]

    return EnergyResponse(
        site_id=site_id,
        start_date=min(timestamps) if timestamps else "",
        end_date=max(timestamps) if timestamps else "",
        total_kwh=round(total_kwh, 2),
        avg_kw=round(avg_kw, 2),
        peak_kw=round(peak_kw, 2),
        data_points=data_points[-168:],  # Last week of hourly data
    )
