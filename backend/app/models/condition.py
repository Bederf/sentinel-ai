"""
Condition Models - Pydantic models for element-level condition trending

Phase 56: Conditional Maintenance
Plan 01: Element-level history tracking and trend analysis

Models for tracking degradation rates, trend directions, and equipment
condition summaries derived from inspection measurement data over time.
"""

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


# ============================================================================
# Enums
# ============================================================================

class TrendDirection(str, Enum):
    """Direction of element degradation trend."""
    IMPROVING = "improving"
    STABLE = "stable"
    DEGRADING = "degrading"
    RAPID_DEGRADING = "rapid_degrading"


class TrendSource(str, Enum):
    """Source of a trend data point."""
    INSPECTION = "inspection"
    BASELINE = "baseline"
    SENSOR = "sensor"


# ============================================================================
# Data Models
# ============================================================================

class ElementTrendPoint(BaseModel):
    """A single measurement data point in an element's trend history."""
    timestamp: datetime = Field(..., description="When the measurement was taken")
    value: float = Field(..., description="Measured value")
    unit: str = Field(..., description="Unit of measurement (e.g., mm/s, C, bar)")
    deviation_percent: float = Field(default=0.0, description="Deviation from baseline as %")
    source: TrendSource = Field(default=TrendSource.INSPECTION, description="Data source")


class DegradationRate(BaseModel):
    """Calculated degradation rate for an element."""
    element_name: str = Field(..., description="Element/measurement point name")
    rate_per_day: float = Field(..., description="Change in value per day")
    rate_per_month: float = Field(..., description="Change in value per month (rate_per_day * 30)")
    unit: str = Field(..., description="Unit of rate (e.g., mm/s/day)")
    confidence: float = Field(..., ge=0, le=1, description="Confidence of fit (based on R-squared)")


class ElementTrend(BaseModel):
    """Complete trend analysis for a single element."""
    element_name: str = Field(..., description="Element/measurement point name")
    equipment_id: str = Field(..., description="Parent equipment ID")
    measurement_type: str = Field(..., description="Type of measurement (vibration, temperature, etc.)")
    data_points: List[ElementTrendPoint] = Field(default_factory=list, description="Historical data points")
    degradation_rate_per_day: Optional[float] = Field(None, description="Daily degradation rate")
    trend_direction: TrendDirection = Field(default=TrendDirection.STABLE, description="Trend classification")
    r_squared: Optional[float] = Field(None, ge=0, le=1, description="Linear fit quality (0-1)")
    days_of_data: int = Field(default=0, description="Number of days spanned by data")


class EquipmentTrendSummary(BaseModel):
    """Summary of all element trends for an equipment item."""
    equipment_id: str = Field(..., description="Equipment identifier")
    equipment_type: Optional[str] = Field(None, description="Type of equipment (chiller, ahu, etc.)")
    element_trends: List[ElementTrend] = Field(default_factory=list, description="Trends for each element")
    worst_element: Optional[str] = Field(None, description="Element with worst degradation")
    overall_trend_direction: TrendDirection = Field(
        default=TrendDirection.STABLE,
        description="Overall equipment trend"
    )
    condition_score: float = Field(
        default=100.0,
        ge=0,
        le=100,
        description="Overall condition score (0=worst, 100=best)"
    )
    analysis_date: datetime = Field(default_factory=datetime.now, description="When analysis was performed")
    message: Optional[str] = Field(None, description="Human-readable summary message")


# ============================================================================
# Request Models
# ============================================================================

class AnalyzeChangesRequest(BaseModel):
    """Request body for the analyze-changes endpoint."""
    equipment_id: str = Field(..., description="Equipment to analyze")
    element_name: Optional[str] = Field(None, description="Specific element (all if None)")
