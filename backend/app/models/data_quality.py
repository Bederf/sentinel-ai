"""Data Quality Models for ML Training Data Validation.

This module defines the data models for monitoring data quality:
- DataQualityLevel: Quality classification (EXCELLENT, GOOD, FAIR, POOR)
- SensorHealth: Health metrics for a single sensor
- DataGap: Missing data period information
- EquipmentDataQuality: Quality metrics for all sensors on an equipment
- DataQualityAlert: Alert for data quality issues
"""

from datetime import datetime
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class DataQualityLevel(str, Enum):
    """Data quality classification levels based on completeness percentage.

    - EXCELLENT: >= 95% data completeness
    - GOOD: 80-95% data completeness
    - FAIR: 60-80% data completeness
    - POOR: < 60% data completeness
    """

    EXCELLENT = "excellent"
    GOOD = "good"
    FAIR = "fair"
    POOR = "poor"


class DataGap(BaseModel):
    """Represents a gap (missing data period) in sensor readings.

    A gap is detected when the interval between consecutive readings
    exceeds the expected polling interval (typically 1 minute).
    """

    start: datetime = Field(..., description="Gap start time")
    end: datetime = Field(..., description="Gap end time")
    duration_minutes: float = Field(..., ge=0, description="Gap duration in minutes")
    sensor_type: str = Field(..., description="Sensor type affected")
    equipment_id: str = Field(..., description="Equipment with the gap")


class SensorHealth(BaseModel):
    """Health metrics for a single sensor over a time period.

    Tracks expected vs actual readings to compute completeness,
    and identifies gaps in the data stream.
    """

    sensor_type: str = Field(..., description="Type of sensor (temperature, vibration, etc.)")
    equipment_id: str = Field(..., description="Equipment this sensor belongs to")
    expected_readings_24h: int = Field(
        default=1440, ge=0, description="Expected readings in 24h (1-minute polling = 1440)"
    )
    actual_readings_24h: int = Field(default=0, ge=0, description="Actual readings received in 24h")
    completeness_pct: float = Field(default=0.0, ge=0.0, le=100.0, description="Data completeness percentage (0-100)")
    last_reading_at: Optional[datetime] = Field(None, description="Timestamp of most recent reading")
    gaps: List[DataGap] = Field(default_factory=list, description="List of detected data gaps")
    status: DataQualityLevel = Field(default=DataQualityLevel.POOR, description="Quality level for this sensor")

    @property
    def gap_count(self) -> int:
        """Number of data gaps detected."""
        return len(self.gaps)

    @property
    def total_gap_minutes(self) -> float:
        """Total minutes of gaps."""
        return sum(gap.duration_minutes for gap in self.gaps)


class EquipmentDataQuality(BaseModel):
    """Aggregated data quality metrics for an equipment.

    Combines health metrics from all sensors on an equipment
    to provide an overall quality assessment.
    """

    equipment_id: str = Field(..., description="Equipment identifier")
    equipment_type: str = Field(..., description="Equipment type (chiller, ahu, generator)")
    building_id: str = Field(default="", description="Building this equipment belongs to")
    overall_quality: DataQualityLevel = Field(default=DataQualityLevel.POOR, description="Overall data quality level")
    quality_score: float = Field(default=0.0, ge=0.0, le=100.0, description="Quality score (0-100)")
    sensor_health: List[SensorHealth] = Field(default_factory=list, description="Health metrics per sensor")
    total_expected_24h: int = Field(default=0, ge=0, description="Total expected readings across all sensors")
    total_actual_24h: int = Field(default=0, ge=0, description="Total actual readings across all sensors")
    completeness_pct: float = Field(default=0.0, ge=0.0, le=100.0, description="Overall data completeness percentage")
    last_updated: datetime = Field(default_factory=datetime.utcnow, description="When these metrics were computed")

    @property
    def sensor_count(self) -> int:
        """Number of sensors tracked."""
        return len(self.sensor_health)

    @property
    def healthy_sensor_count(self) -> int:
        """Number of sensors with GOOD or EXCELLENT status."""
        return sum(1 for s in self.sensor_health if s.status in (DataQualityLevel.EXCELLENT, DataQualityLevel.GOOD))

    @property
    def total_gaps(self) -> int:
        """Total number of gaps across all sensors."""
        return sum(s.gap_count for s in self.sensor_health)


class DataQualityAlert(BaseModel):
    """Alert for data quality issues that may affect ML training.

    Alert types:
    - gap: Significant data gap (>30 minutes)
    - drift: Sudden value change indicating sensor drift
    - stale: No readings for extended period (>15 minutes)
    - anomaly: Statistical anomaly in readings

    Severity levels:
    - warning: Issue detected, monitoring recommended
    - critical: Immediate attention needed, may affect ML training
    """

    alert_type: str = Field(..., description="Alert type: gap, drift, stale, anomaly")
    severity: str = Field(..., description="Severity level: warning, critical")
    equipment_id: str = Field(..., description="Affected equipment")
    sensor_type: str = Field(..., description="Affected sensor type")
    message: str = Field(..., description="Human-readable alert message")
    detected_at: datetime = Field(default_factory=datetime.utcnow, description="When the issue was detected")
    resolved_at: Optional[datetime] = Field(None, description="When the issue was resolved (None if still active)")
    details: Optional[dict] = Field(None, description="Additional details (gap duration, drift magnitude, etc.)")

    @property
    def is_active(self) -> bool:
        """Check if alert is still active (not resolved)."""
        return self.resolved_at is None

    @property
    def duration_minutes(self) -> Optional[float]:
        """Duration of the alert in minutes (if resolved)."""
        if self.resolved_at is None:
            return None
        delta = self.resolved_at - self.detected_at
        return delta.total_seconds() / 60


class BuildingDataQualityReport(BaseModel):
    """Daily data quality report for a building.

    Aggregates quality metrics from all equipment in a building
    for daily monitoring and reporting.
    """

    building_id: str = Field(..., description="Building identifier")
    building_name: str = Field(default="", description="Building name")
    report_date: datetime = Field(default_factory=datetime.utcnow, description="Report generation date")
    equipment_count: int = Field(default=0, ge=0, description="Number of equipment")
    overall_quality: DataQualityLevel = Field(default=DataQualityLevel.POOR, description="Building-wide quality level")
    average_quality_score: float = Field(default=0.0, ge=0.0, le=100.0, description="Average quality score")
    equipment_quality: List[EquipmentDataQuality] = Field(
        default_factory=list, description="Quality metrics per equipment"
    )
    active_alerts: int = Field(default=0, ge=0, description="Number of active alerts")
    total_gaps: int = Field(default=0, ge=0, description="Total gaps detected")

    @property
    def excellent_count(self) -> int:
        """Count of equipment with EXCELLENT quality."""
        return sum(1 for eq in self.equipment_quality if eq.overall_quality == DataQualityLevel.EXCELLENT)

    @property
    def poor_count(self) -> int:
        """Count of equipment with POOR quality."""
        return sum(1 for eq in self.equipment_quality if eq.overall_quality == DataQualityLevel.POOR)


class TrainingReadiness(BaseModel):
    """Assessment of data readiness for ML model training.

    Evaluates whether sufficient quality data exists to train
    ML models for a specific equipment type.

    Phase 109-03: Added mode, thresholds_used, gaps for mode-aware readiness.
    """

    equipment_type: str = Field(..., description="Equipment type assessed")
    is_ready: bool = Field(default=False, description="Whether data is sufficient for training")
    readiness_score: float = Field(default=0.0, ge=0.0, le=100.0, description="Readiness score (0-100)")
    equipment_count: int = Field(default=0, ge=0, description="Equipment count for type")
    equipment_with_good_data: int = Field(default=0, ge=0, description="Equipment with GOOD+ quality")
    minimum_required: int = Field(default=5, ge=1, description="Minimum equipment required for training")
    days_of_data: int = Field(default=0, ge=0, description="Days of historical data")
    minimum_days_required: int = Field(default=30, ge=1, description="Minimum days required for training")
    issues: List[str] = Field(default_factory=list, description="Issues preventing training readiness")
    recommendations: List[str] = Field(default_factory=list, description="Recommendations to improve readiness")
    mode: Optional[str] = Field(None, description="Ingestion mode used for threshold selection")
    thresholds_used: Optional[dict] = Field(
        None,
        description="Mode-specific thresholds applied: min_quality, min_days, min_equipment",
    )
    gaps: List[str] = Field(default_factory=list, description="Which thresholds were not met")
