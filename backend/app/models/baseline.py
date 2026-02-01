"""
Baseline Models - Pydantic models for baseline assessment system

Phase 44: Asset Baseline Assessment
"""

from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


# ============================================================================
# Enums
# ============================================================================

class BaselineType(str, Enum):
    """Type of baseline capture."""
    INITIAL = "initial"  # First baseline at equipment installation/onboarding
    PERIODIC = "periodic"  # Regular recurring baseline (e.g., annual)
    POST_REPAIR = "post_repair"  # Baseline after maintenance/repair
    PRE_REPAIR = "pre_repair"  # Baseline before maintenance to assess repair effectiveness
    SEASONAL = "seasonal"  # Baseline at different operating conditions


class BaselineStatus(str, Enum):
    """Status of baseline record."""
    ACTIVE = "active"  # Current active baseline
    ARCHIVED = "archived"  # Archived baseline (kept for historical reference)
    SUPERSEDED = "superseded"  # Replaced by newer baseline


class BaselineSource(str, Enum):
    """Source of baseline data."""
    MANUAL = "manual"  # Engineer manual measurement and entry
    BMS_AVERAGE = "bms_average"  # Averaged from BMS sensor over time period
    MOBILE_SENSOR = "mobile_sensor"  # Captured via mobile phone sensors (vibration, audio, etc.)
    AUTOMATED = "automated"  # Automatically captured by system
    LAB = "lab"  # Laboratory analysis results


class ElementType(str, Enum):
    """Type of equipment element/component."""
    BEARING = "bearing"
    FILTER = "filter"
    COIL = "coil"
    COMPRESSOR_STAGE = "compressor_stage"
    FAN = "fan"
    MOTOR = "motor"
    PUMP = "pump"
    VALVE = "valve"
    BELT = "belt"
    CONTROLLER = "controller"


class MeasurementType(str, Enum):
    """Type of measurement for element baselines."""
    VIBRATION = "vibration"  # Vibration analysis (RMS, frequency spectrum)
    TEMPERATURE = "temperature"  # Temperature measurements (bearing, housing, oil)
    VISUAL_INSPECTION = "visual_inspection"  # Visual/tactile inspection results (wear, cracks, leaks)
    SOUND = "sound"  # Audio/sound level measurements (dBA, frequency spectrum)
    ELECTRICAL = "electrical"  # Electrical measurements (voltage, current, resistance)
    OIL_ANALYSIS = "oil_analysis"  # Oil analysis results (viscosity, particles, water)


class DeviationStatus(str, Enum):
    """Deviation status for comparison results."""
    NORMAL = "normal"
    WARNING = "warning"
    CRITICAL = "critical"


class Criticality(str, Enum):
    """Criticality level for maintenance prioritization."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# ============================================================================
# Base Models
# ============================================================================

class ComparisonResult(BaseModel):
    """Result of comparing a single metric to its baseline."""
    baseline: float = Field(..., description="Baseline value")
    current: float = Field(..., description="Current measured value")
    deviation_percent: float = Field(..., description="Deviation from baseline as percentage")
    status: DeviationStatus = Field(..., description="Deviation status (normal/warning/critical)")

    class Config:
        json_schema_extra = {
            "example": {
                "baseline": 7.2,
                "current": 8.5,
                "deviation_percent": 18.1,
                "status": "warning"
            }
        }


# ============================================================================
# Equipment Baseline Models
# ============================================================================

class EquipmentBaselineBase(BaseModel):
    """Base model for equipment baseline."""
    equipment_id: str = Field(..., description="Equipment identifier")
    baseline_date: datetime = Field(default_factory=datetime.now, description="When baseline was captured")
    captured_by: str = Field(..., description="Engineer name or 'automated'")
    baseline_type: BaselineType = Field(default=BaselineType.INITIAL, description="Type of baseline")
    status: BaselineStatus = Field(default=BaselineStatus.ACTIVE, description="Baseline status")
    baseline_values: Dict[str, Any] = Field(..., description="Baseline measurement values (JSON)")
    measurement_conditions: Dict[str, Any] = Field(default_factory=dict, description="Measurement context")
    source_type: BaselineSource = Field(default=BaselineSource.MANUAL, description="Data source")
    notes: Optional[str] = Field(None, description="Engineer notes")
    attachment_urls: Optional[List[str]] = Field(None, description="URLs to documentation/photos")


class EquipmentBaselineCreate(EquipmentBaselineBase):
    """Model for creating new equipment baseline."""
    pass


class EquipmentBaseline(EquipmentBaselineBase):
    """Model for equipment baseline record."""
    id: str = Field(..., description="Baseline record ID")
    created_at: datetime
    updated_at: datetime

    class Config:
        json_schema_extra = {
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "equipment_id": "chiller-001",
                "baseline_date": "2026-02-01T14:30:00Z",
                "captured_by": "John Smith",
                "baseline_type": "initial",
                "status": "active",
                "baseline_values": {
                    "chw_supply_temp": 7.2,
                    "chw_return_temp": 12.5,
                    "motor_current": 145.2,
                    "suction_pressure": 4.2,
                    "discharge_pressure": 15.8
                },
                "measurement_conditions": {
                    "ambient_temp": 22.0,
                    "load_percent": 85
                },
                "source_type": "manual",
                "notes": "Baseline captured during peak summer conditions",
                "attachment_urls": ["https://storage.example.com/photo1.jpg"]
            }
        }


# ============================================================================
# Equipment Element Models
# ============================================================================

class EquipmentElementBase(BaseModel):
    """Base model for equipment element."""
    equipment_id: str = Field(..., description="Parent equipment identifier")
    element_id: str = Field(..., description="Element identifier (unique within equipment)")
    element_type: ElementType = Field(..., description="Type of element")
    element_name: Optional[str] = Field(None, description="Human-readable name")
    manufacturer: Optional[str] = Field(None, description="Element manufacturer")
    model: Optional[str] = Field(None, description="Element model")
    serial_number: Optional[str] = Field(None, description="Serial number")
    installation_date: Optional[str] = Field(None, description="When element was installed")
    expected_life_days: Optional[int] = Field(None, description="Expected lifespan")
    criticality: Criticality = Field(default=Criticality.MEDIUM, description="Maintenance priority")


class EquipmentElementCreate(EquipmentElementBase):
    """Model for creating equipment element."""
    pass


class EquipmentElement(EquipmentElementBase):
    """Model for equipment element record."""
    id: str = Field(..., description="Element record ID")
    created_at: datetime
    updated_at: datetime

    class Config:
        json_schema_extra = {
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174001",
                "equipment_id": "chiller-001",
                "element_id": "compressor_bearing_1",
                "element_type": "bearing",
                "element_name": "Compressor Bearing #1",
                "manufacturer": "SKF",
                "model": "6316/C3",
                "installation_date": "2025-01-15",
                "expected_life_days": 2555,
                "criticality": "high"
            }
        }


# ============================================================================
# Element Baseline Models
# ============================================================================

class ElementBaselineBase(BaseModel):
    """Base model for element baseline."""
    element_id: str = Field(..., description="Element identifier")
    baseline_date: datetime = Field(default_factory=datetime.now, description="Baseline capture date")
    captured_by: str = Field(..., description="Who captured the baseline")
    baseline_type: BaselineType = Field(default=BaselineType.INITIAL, description="Type of baseline")
    status: BaselineStatus = Field(default=BaselineStatus.ACTIVE, description="Baseline status")
    measurement_type: MeasurementType = Field(..., description="Type of measurement")
    baseline_values: Dict[str, Any] = Field(..., description="Baseline measurement values")
    measurement_conditions: Dict[str, Any] = Field(default_factory=dict, description="Measurement context")
    source_type: BaselineSource = Field(default=BaselineSource.MOBILE_SENSOR, description="Data source")
    notes: Optional[str] = Field(None, description="Measurement notes")
    attachment_urls: Optional[List[str]] = Field(None, description="URLs to photos/measurements")


class ElementBaselineCreate(ElementBaselineBase):
    """Model for creating element baseline."""
    pass


class ElementBaseline(ElementBaselineBase):
    """Model for element baseline record."""
    id: str = Field(..., description="Baseline record ID")
    created_at: datetime
    updated_at: datetime

    class Config:
        json_schema_extra = {
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174002",
                "element_id": "compressor_bearing_1",
                "baseline_date": "2026-02-01T15:00:00Z",
                "captured_by": "Sarah Johnson",
                "baseline_type": "initial",
                "status": "active",
                "measurement_type": "vibration",
                "baseline_values": {
                    "vibration_rms": 1.2,
                    "vibration_peak": 2.1,
                    "frequency_1x": 50.0,
                    "frequency_2x": 100.0,
                    "bearing_temp": 45.2
                },
                "measurement_conditions": {
                    "load_percent": 85,
                    "rpm": 1450
                },
                "notes": "Baseline captured during normal operation conditions"
            }
        }


# ============================================================================
# Baseline Comparison Models
# ============================================================================

class BaselineComparisonBase(BaseModel):
    """Base model for baseline comparison."""
    comparison_type: str = Field(..., description="Type: equipment_baseline or element_baseline")
    baseline_id: str = Field(..., description="Reference to baseline record")
    equipment_id: str = Field(..., description="Equipment identifier")
    element_id: Optional[str] = Field(None, description="Element identifier if element comparison")
    comparison_date: datetime = Field(default_factory=datetime.now, description="When comparison was made")
    comparison_results: Dict[str, ComparisonResult] = Field(..., description="Detailed comparison results")
    overall_status: DeviationStatus = Field(..., description="Overall deviation status")
    max_deviation_percent: float = Field(..., description="Maximum deviation found")
    data_source: str = Field(..., description="Source of current readings")
    comparison_notes: Optional[str] = Field(None, description="Notes about comparison")
    alert_generated: bool = Field(default=False, description="Whether alert was generated")
    alert_id: Optional[str] = Field(None, description="Alert ID if generated")


class BaselineComparisonCreate(BaselineComparisonBase):
    """Model for creating baseline comparison."""
    pass


class BaselineComparison(BaselineComparisonBase):
    """Model for baseline comparison record."""
    id: str = Field(..., description="Comparison record ID")
    created_at: datetime

    class Config:
        json_schema_extra = {
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174003",
                "comparison_type": "equipment_baseline",
                "baseline_id": "123e4567-e89b-12d3-a456-426614174000",
                "equipment_id": "chiller-001",
                "comparison_date": "2026-03-15T10:00:00Z",
                "comparison_results": {
                    "chw_supply_temp": {
                        "baseline": 7.2,
                        "current": 8.5,
                        "deviation_percent": 18.1,
                        "status": "warning"
                    },
                    "motor_current": {
                        "baseline": 145.2,
                        "current": 168.5,
                        "deviation_percent": 16.0,
                        "status": "warning"
                    }
                },
                "overall_status": "warning",
                "max_deviation_percent": 18.1,
                "data_source": "bms_sensor",
                "alert_generated": False
            }
        }


# ============================================================================
# Response Models
# ============================================================================

class BaselineCaptureResponse(BaseModel):
    """Response for baseline capture operations."""
    success: bool
    message: str
    baseline_id: str
    equipment_id: str
    metrics_captured: int


class BaselineComparisonResponse(BaseModel):
    """Response for baseline comparison."""
    success: bool
    comparison_id: str
    overall_status: DeviationStatus
    max_deviation_percent: float
    critical_count: int
    warning_count: int
    normal_count: int


class BaselineReportResponse(BaseModel):
    """Response for baseline report."""
    equipment_id: str
    active_baseline: Optional[EquipmentBaseline]
    element_baselines: List[ElementBaseline]
    recent_comparisons: List[BaselineComparison]
    summary: Dict[str, Any]


class DeviationSummary(BaseModel):
    """Summary of baseline deviations."""
    equipment_id: str
    last_comparison_date: Optional[datetime]
    overall_status: DeviationStatus
    max_deviation_percent: float
    deviations: Dict[str, ComparisonResult]


# ============================================================================
# Request Models
# ============================================================================

class ManualBaselineCaptureRequest(BaseModel):
    """Request for manual baseline capture."""
    captured_by: str = Field(..., description="Engineer name")
    baseline_type: BaselineType = Field(default=BaselineType.INITIAL, description="Type of baseline")
    baseline_values: Dict[str, Any] = Field(..., description="Manual measurement values")
    measurement_conditions: Optional[Dict[str, Any]] = Field(None, description="Measurement context")
    notes: Optional[str] = Field(None, description="Engineer notes")
    attachment_urls: Optional[List[str]] = Field(None, description="URLs to photos")


class ElementBaselineCaptureRequest(BaseModel):
    """Request for element baseline capture."""
    element_id: str = Field(..., description="Element identifier")
    captured_by: str = Field(..., description="Engineer name")
    measurement_type: MeasurementType = Field(..., description="Type of measurement")
    baseline_type: BaselineType = Field(default=BaselineType.INITIAL, description="Type of baseline")
    baseline_values: Dict[str, Any] = Field(..., description="Measurement values")
    measurement_conditions: Optional[Dict[str, Any]] = Field(None, description="Measurement context")
    notes: Optional[str] = Field(None, description="Measurement notes")
    attachment_urls: Optional[List[str]] = Field(None, description="URLs to photos")


class BaselineComparisonRequest(BaseModel):
    """Request for baseline comparison."""
    equipment_id: str = Field(..., description="Equipment to compare")
    current_values: Optional[Dict[str, Any]] = Field(None, description="Current readings (if None, fetch from BMS)")
    data_source: str = Field(default="bms_sensor", description="Source of current values")
