"""Data Quality API Endpoints.

REST API for accessing data quality metrics, alerts, and training
readiness assessments for ML model development.

Endpoints:
- GET /api/data-quality/equipment/{equipment_id} - Quality for one equipment
- GET /api/data-quality/building/{building_id} - Quality for all equipment in building
- GET /api/data-quality/report/daily - Daily quality report
- GET /api/data-quality/alerts - Active quality alerts
- GET /api/data-quality/gaps/equipment/{equipment_id} - Data gaps for equipment
- GET /api/data-quality/training-readiness/{equipment_type} - ML training readiness
"""

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.models.data_quality import (
    DataQualityLevel,
    DataGap,
    EquipmentDataQuality,
    DataQualityAlert,
    BuildingDataQualityReport,
    TrainingReadiness,
)
from app.services.data_quality_service import get_data_quality_service
from app.services.data_quality_alerts import get_data_quality_alert_service

router = APIRouter(prefix="/api/data-quality", tags=["data-quality"])


# Response models
class AlertSummary(BaseModel):
    """Summary of data quality alerts."""
    total_active: int = Field(..., description="Total active alerts")
    by_type: dict = Field(default_factory=dict, description="Count by alert type")
    by_severity: dict = Field(default_factory=dict, description="Count by severity")
    total_history: int = Field(..., description="Total historical alerts")


class HealthCheckResponse(BaseModel):
    """Health check response for data quality service."""
    status: str = Field(..., description="Service status")
    influxdb_mode: str = Field(..., description="InfluxDB mode (real/mock)")
    active_alerts: int = Field(..., description="Number of active alerts")
    timestamp: datetime = Field(default_factory=datetime.utcnow)


@router.get("/health", response_model=HealthCheckResponse)
async def health_check():
    """Check data quality service health."""
    quality_service = get_data_quality_service()
    alert_service = get_data_quality_alert_service()

    influxdb_mode = "mock" if quality_service._influxdb.use_mock else "real"
    active_alerts = len(alert_service.get_active_alerts())

    return HealthCheckResponse(
        status="ok",
        influxdb_mode=influxdb_mode,
        active_alerts=active_alerts,
    )


@router.get("/equipment/{equipment_id}", response_model=EquipmentDataQuality)
async def get_equipment_quality(
    equipment_id: str,
    equipment_type: str = Query(default="unknown", description="Equipment type"),
    lookback_hours: int = Query(default=24, ge=1, le=168, description="Hours to analyze"),
):
    """Get data quality metrics for a single equipment.

    Computes sensor health, completeness, and gaps for the specified equipment.
    """
    quality_service = get_data_quality_service()

    quality = quality_service.get_equipment_quality(
        equipment_id=equipment_id,
        equipment_type=equipment_type,
        lookback_hours=lookback_hours,
    )

    return quality


@router.get("/building/{building_id}", response_model=BuildingDataQualityReport)
async def get_building_quality(
    building_id: str,
    building_name: str = Query(default="", description="Building name"),
):
    """Get data quality report for all equipment in a building.

    Aggregates quality metrics from all equipment in the building.
    """
    quality_service = get_data_quality_service()

    report = quality_service.generate_daily_report(
        building_id=building_id,
        building_name=building_name,
    )

    return report


@router.get("/report/daily", response_model=BuildingDataQualityReport)
async def get_daily_report(
    building_id: str = Query(..., description="Building ID for report"),
    building_name: str = Query(default="", description="Building name"),
):
    """Generate daily data quality report for a building.

    Provides comprehensive quality metrics for all equipment.
    """
    quality_service = get_data_quality_service()

    report = quality_service.generate_daily_report(
        building_id=building_id,
        building_name=building_name,
    )

    return report


@router.get("/alerts", response_model=List[DataQualityAlert])
async def get_alerts(
    equipment_id: Optional[str] = Query(None, description="Filter by equipment"),
    alert_type: Optional[str] = Query(None, description="Filter by alert type"),
    include_resolved: bool = Query(False, description="Include resolved alerts"),
    limit: int = Query(50, ge=1, le=500, description="Maximum alerts to return"),
):
    """Get data quality alerts.

    Returns active alerts by default. Use include_resolved=true for history.
    """
    alert_service = get_data_quality_alert_service()

    if include_resolved:
        alerts = alert_service.get_alert_history(
            limit=limit,
            equipment_id=equipment_id,
        )
        if alert_type:
            alerts = [a for a in alerts if a.alert_type == alert_type]
    else:
        alerts = alert_service.get_active_alerts(
            equipment_id=equipment_id,
            alert_type=alert_type,
        )

    return alerts[:limit]


@router.get("/alerts/summary", response_model=AlertSummary)
async def get_alert_summary():
    """Get summary of data quality alerts by type and severity."""
    alert_service = get_data_quality_alert_service()
    return alert_service.get_alert_summary()


@router.post("/alerts/check")
async def check_all_alerts():
    """Trigger alert check for all equipment.

    Scans all equipment for data quality issues and generates alerts.
    """
    alert_service = get_data_quality_alert_service()

    new_alerts = alert_service.check_all_equipment()

    return {
        "status": "ok",
        "new_alerts": len(new_alerts),
        "alerts": new_alerts,
    }


@router.post("/alerts/resolve")
async def resolve_alert(
    equipment_id: str = Query(..., description="Equipment ID"),
    sensor_type: str = Query(..., description="Sensor type"),
    alert_type: str = Query(..., description="Alert type"),
):
    """Manually resolve an alert."""
    alert_service = get_data_quality_alert_service()

    resolved = alert_service.resolve_alert(
        equipment_id=equipment_id,
        sensor_type=sensor_type,
        alert_type=alert_type,
    )

    if not resolved:
        raise HTTPException(
            status_code=404,
            detail=f"No active alert found for {equipment_id}/{sensor_type}/{alert_type}",
        )

    return {"status": "resolved", "equipment_id": equipment_id}


@router.get("/gaps/equipment/{equipment_id}", response_model=List[DataGap])
async def get_equipment_gaps(
    equipment_id: str,
    equipment_type: str = Query(default="unknown", description="Equipment type"),
    lookback_hours: int = Query(default=24, ge=1, le=168, description="Hours to analyze"),
):
    """Get all data gaps for an equipment.

    Returns gaps across all sensors, sorted by start time.
    """
    quality_service = get_data_quality_service()

    gaps = quality_service.get_equipment_gaps(
        equipment_id=equipment_id,
        equipment_type=equipment_type,
        lookback_hours=lookback_hours,
    )

    return gaps


@router.get("/training-readiness/{equipment_type}", response_model=TrainingReadiness)
async def check_training_readiness(
    equipment_type: str,
    minimum_equipment: int = Query(default=5, ge=1, description="Minimum equipment count"),
    minimum_days: int = Query(default=30, ge=7, le=365, description="Minimum days of data"),
    minimum_quality: float = Query(default=80.0, ge=0, le=100, description="Minimum quality score"),
):
    """Check if sufficient data exists for ML model training.

    Evaluates equipment count, data quality, and history duration
    to determine if ML training is viable.
    """
    quality_service = get_data_quality_service()

    readiness = quality_service.check_training_readiness(
        equipment_type=equipment_type,
        minimum_equipment=minimum_equipment,
        minimum_days=minimum_days,
        minimum_quality_score=minimum_quality,
    )

    return readiness


@router.get("/quality-levels")
async def get_quality_levels():
    """Get quality level definitions.

    Returns the thresholds for each quality level.
    """
    return {
        "levels": {
            "excellent": {"min_pct": 95, "description": "95%+ data completeness"},
            "good": {"min_pct": 80, "description": "80-95% data completeness"},
            "fair": {"min_pct": 60, "description": "60-80% data completeness"},
            "poor": {"min_pct": 0, "description": "<60% data completeness"},
        },
        "thresholds": {
            "stale_minutes": 15,
            "gap_minutes": 30,
            "drift_percent": 50,
        },
    }
