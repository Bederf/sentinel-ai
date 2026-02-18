"""
Time-Series Data API - Endpoints for InfluxDB sensor data.

Phase 42: Data Collection & Storage
Provides REST endpoints for:
- Writing sensor readings
- Querying historical data
- Getting ML training data
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime

router = APIRouter(prefix="/api/timeseries", tags=["timeseries"])


# ============= Pydantic Models =============

class SensorReading(BaseModel):
    """Single sensor reading for write."""
    equipment_id: str
    sensor_type: str
    value: float
    timestamp: Optional[datetime] = None
    unit: Optional[str] = None
    tags: Optional[Dict[str, str]] = None


class BatchReadings(BaseModel):
    """Multiple sensor readings for batch write."""
    readings: List[SensorReading]


class WriteResponse(BaseModel):
    """Response for write operations."""
    success: bool
    count: int
    message: str


class QueryResult(BaseModel):
    """Result from time-series query."""
    equipment_id: str
    sensor_type: str
    data: List[Dict[str, Any]]
    count: int


class MLDataResult(BaseModel):
    """Result formatted for ML training."""
    equipment_id: str
    sensor_types: List[str]
    hours: int
    data: Dict[str, List[float]]


# ============= Write Endpoints =============

@router.post("/write", response_model=WriteResponse)
async def write_sensor_reading(reading: SensorReading):
    """
    Write a single sensor reading to InfluxDB.

    The reading is written to the raw bucket and will be
    automatically downsampled to 1m, 1h, and 1d buckets.
    """
    from app.services.influxdb_service import get_influxdb_service

    service = get_influxdb_service()
    success = service.write_sensor_data(
        equipment_id=reading.equipment_id,
        sensor_type=reading.sensor_type,
        value=reading.value,
        timestamp=reading.timestamp,
        unit=reading.unit,
        tags=reading.tags
    )

    if not success:
        raise HTTPException(status_code=500, detail="Failed to write sensor data")

    return WriteResponse(
        success=True,
        count=1,
        message=f"Written reading for {reading.equipment_id}:{reading.sensor_type}"
    )


@router.post("/write/batch", response_model=WriteResponse)
async def write_batch_readings(batch: BatchReadings):
    """
    Write multiple sensor readings in a single batch.

    More efficient than individual writes for bulk data ingestion.
    """
    from app.services.influxdb_service import get_influxdb_service

    service = get_influxdb_service()

    readings = [
        {
            "equipment_id": r.equipment_id,
            "sensor_type": r.sensor_type,
            "value": r.value,
            "timestamp": r.timestamp,
            "unit": r.unit
        }
        for r in batch.readings
    ]

    count = service.write_batch(readings)

    return WriteResponse(
        success=count > 0,
        count=count,
        message=f"Written {count} of {len(readings)} readings"
    )


# ============= Query Endpoints =============

@router.get("/query/raw", response_model=QueryResult)
async def query_raw_data(
    equipment_id: str,
    sensor_type: str,
    start: datetime,
    end: Optional[datetime] = None
):
    """
    Query raw sensor data for a time range.

    Returns individual readings at original resolution.
    """
    from app.services.influxdb_service import get_influxdb_service

    service = get_influxdb_service()
    readings = service.query_raw(equipment_id, sensor_type, start, end)

    return QueryResult(
        equipment_id=equipment_id,
        sensor_type=sensor_type,
        data=[{"timestamp": r.timestamp.isoformat(), "value": r.value} for r in readings],
        count=len(readings)
    )


@router.get("/query/hourly", response_model=QueryResult)
async def query_hourly_data(
    equipment_id: str,
    sensor_type: str,
    hours: int = Query(168, description="Hours of history (default 168 = 7 days)")
):
    """
    Query hourly aggregated sensor data.

    Returns mean values per hour, suitable for LSTM input.
    """
    from app.services.influxdb_service import get_influxdb_service

    service = get_influxdb_service()
    data = service.query_hourly(equipment_id, sensor_type, hours)

    return QueryResult(
        equipment_id=equipment_id,
        sensor_type=sensor_type,
        data=[{"timestamp": d["timestamp"].isoformat() if hasattr(d["timestamp"], "isoformat") else str(d["timestamp"]), "value": d["value"]} for d in data],
        count=len(data)
    )


@router.get("/query/ml-training", response_model=MLDataResult)
async def query_ml_training_data(
    equipment_id: str,
    sensor_types: str = Query(..., description="Comma-separated sensor types"),
    days: int = Query(180, description="Days of history")
):
    """
    Get data formatted for ML model training.

    Returns hourly values for each sensor type, suitable for
    direct input to LSTM or autoencoder models.
    """
    from app.services.influxdb_service import get_influxdb_service

    service = get_influxdb_service()
    types_list = [s.strip() for s in sensor_types.split(",")]
    data = service.get_ml_training_data(equipment_id, types_list, days)

    return MLDataResult(
        equipment_id=equipment_id,
        sensor_types=types_list,
        hours=days * 24,
        data=data
    )


# ============= Status Endpoints =============

@router.get("/health")
async def timeseries_health():
    """Check InfluxDB connection health."""
    from app.services.influxdb_service import get_influxdb_service

    service = get_influxdb_service()

    return {
        "status": "healthy",
        "mode": "mock" if service.use_mock else "live",
        "url": service.url if not service.use_mock else None,
        "buckets": list(service.BUCKETS.keys())
    }


@router.get("/buckets")
async def list_buckets():
    """List configured data buckets."""
    from app.services.influxdb_service import get_influxdb_service

    service = get_influxdb_service()
    return {
        "buckets": [
            {
                "key": key,
                "name": config["name"],
                "retention": config["retention"],
                "description": config["description"]
            }
            for key, config in service.BUCKETS.items()
        ]
    }
