"""
Condition Models - Pydantic models for element-level condition trending

Phase 56: Conditional Maintenance
Plan 01: Element-level history tracking and trend analysis
Plan 02: RUL prediction and service recommendations

Models for tracking degradation rates, trend directions, equipment
condition summaries, remaining useful life predictions, and service
recommendations derived from inspection measurement data over time.
"""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

# ============================================================================
# Enums
# ============================================================================


class TrendDirection(StrEnum):
    """Direction of element degradation trend."""

    IMPROVING = "improving"
    STABLE = "stable"
    DEGRADING = "degrading"
    RAPID_DEGRADING = "rapid_degrading"


class TrendSource(StrEnum):
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
    data_points: list[ElementTrendPoint] = Field(default_factory=list, description="Historical data points")
    degradation_rate_per_day: float | None = Field(None, description="Daily degradation rate")
    trend_direction: TrendDirection = Field(default=TrendDirection.STABLE, description="Trend classification")
    r_squared: float | None = Field(None, ge=0, le=1, description="Linear fit quality (0-1)")
    days_of_data: int = Field(default=0, description="Number of days spanned by data")


class EquipmentTrendSummary(BaseModel):
    """Summary of all element trends for an equipment item."""

    equipment_id: str = Field(..., description="Equipment identifier")
    equipment_type: str | None = Field(None, description="Type of equipment (chiller, ahu, etc.)")
    element_trends: list[ElementTrend] = Field(default_factory=list, description="Trends for each element")
    worst_element: str | None = Field(None, description="Element with worst degradation")
    overall_trend_direction: TrendDirection = Field(
        default=TrendDirection.STABLE, description="Overall equipment trend"
    )
    condition_score: float = Field(
        default=100.0, ge=0, le=100, description="Overall condition score (0=worst, 100=best)"
    )
    analysis_date: datetime = Field(default_factory=datetime.now, description="When analysis was performed")
    message: str | None = Field(None, description="Human-readable summary message")


# ============================================================================
# Request Models
# ============================================================================


class RiskLevel(StrEnum):
    """Risk level classification for RUL predictions."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Urgency(StrEnum):
    """Urgency classification for service recommendations."""

    ROUTINE = "routine"
    SOON = "soon"
    URGENT = "urgent"
    IMMEDIATE = "immediate"


class ElementRUL(BaseModel):
    """Remaining Useful Life prediction for a single element."""

    element_name: str = Field(..., description="Element/measurement point name")
    current_value: float | None = Field(None, description="Current measured value")
    threshold_value: float = Field(..., description="Failure threshold value")
    unit: str = Field(default="", description="Unit of measurement")
    days_until_threshold: float | None = Field(
        None, description="Predicted days until threshold reached (None if stable/improving)"
    )
    confidence: float = Field(default=0.0, ge=0, le=1, description="Prediction confidence (0-1)")
    prediction_date: datetime = Field(default_factory=datetime.now, description="When prediction was made")
    risk_level: RiskLevel = Field(default=RiskLevel.LOW, description="Risk classification")


class EquipmentRUL(BaseModel):
    """Remaining Useful Life prediction for equipment (all elements)."""

    equipment_id: str = Field(..., description="Equipment identifier")
    equipment_type: str | None = Field(None, description="Type of equipment")
    element_ruls: list[ElementRUL] = Field(default_factory=list, description="RUL per element")
    worst_element_name: str | None = Field(None, description="Element closest to failure")
    days_until_first_threshold: float | None = Field(
        None, description="Days until first element reaches threshold (None if all stable)"
    )
    overall_risk_level: RiskLevel = Field(default=RiskLevel.LOW, description="Worst-case risk level")
    recommended_service_window: str | None = Field(
        None, description="Service scheduling recommendation (e.g., 'within 30 days')"
    )
    message: str | None = Field(None, description="Human-readable RUL summary")


class ServiceRecommendation(BaseModel):
    """Service recommendation for a degrading element."""

    equipment_id: str = Field(..., description="Equipment identifier")
    element_name: str = Field(..., description="Element/measurement point name")
    recommended_action: str = Field(..., description="Specific recommended maintenance action")
    urgency: Urgency = Field(default=Urgency.ROUTINE, description="Action urgency")
    reason: str = Field(..., description="Why this action is recommended")
    estimated_days_remaining: float | None = Field(
        None, description="Estimated days before failure (None if unknown)"
    )
    confidence: float = Field(default=0.0, ge=0, le=1, description="Recommendation confidence")
    app_version: str | None = Field(None, description="Runtime application version")
    config_checksum: str | None = Field(None, description="Runtime configuration checksum")


# ============================================================================
# Request Models
# ============================================================================


class AnalyzeChangesRequest(BaseModel):
    """Request body for the analyze-changes endpoint."""

    equipment_id: str = Field(..., description="Equipment to analyze")
    element_name: str | None = Field(None, description="Specific element (all if None)")


# ============================================================================
# Service Optimization Models (Phase 56-03)
# ============================================================================


class UtilizationStatus(StrEnum):
    """Status classification for asset utilization."""

    HEALTHY = "healthy"
    AGING = "aging"
    END_OF_LIFE = "end_of_life"


class AssetUtilization(BaseModel):
    """Utilization tracking for a single equipment element."""

    equipment_id: str = Field(..., description="Equipment identifier")
    equipment_type: str | None = Field(None, description="Type of equipment (chiller, ahu, etc.)")
    element_name: str = Field(..., description="Element/measurement point name")
    current_value: float | None = Field(None, description="Current measured value")
    threshold_value: float = Field(..., description="Failure threshold value")
    unit: str = Field(default="", description="Unit of measurement")
    utilization_percent: float = Field(
        default=0.0, ge=0, le=100, description="Percentage of usable life consumed (0=new, 100=end of life)"
    )
    remaining_percent: float = Field(default=100.0, ge=0, le=100, description="Percentage of usable life remaining")
    status: UtilizationStatus = Field(
        default=UtilizationStatus.HEALTHY, description="Health status based on utilization"
    )


class ServiceWindow(BaseModel):
    """Optimized service scheduling window for equipment."""

    equipment_id: str = Field(..., description="Equipment identifier")
    optimal_date: str = Field(..., description="Optimal service date (YYYY-MM-DD)")
    earliest_date: str = Field(..., description="Earliest recommended service date")
    latest_date: str = Field(..., description="Latest safe service date")
    reason: str = Field(..., description="Reason for service recommendation")
    elements_driving: list[str] = Field(default_factory=list, description="Element names driving the service need")
    cost_impact: str = Field(
        default="low", description="Cost impact of timing: low (>90 days), medium (30-90), high (<30 days)"
    )


class MaintenanceCostComparison(BaseModel):
    """Cost comparison between fixed-schedule and condition-based maintenance."""

    equipment_id: str = Field(..., description="Equipment identifier")
    equipment_type: str | None = Field(None, description="Type of equipment")
    fixed_schedule_services_per_year: int = Field(..., description="Number of services per year on fixed schedule")
    conditional_services_per_year: float = Field(
        ..., description="Estimated services per year based on actual condition"
    )
    fixed_annual_cost_estimate: float = Field(
        ..., description="Estimated annual cost for fixed-schedule maintenance (ZAR)"
    )
    conditional_annual_cost_estimate: float = Field(
        ..., description="Estimated annual cost for condition-based maintenance (ZAR)"
    )
    savings_percent: float = Field(
        default=0.0, description="Cost savings percentage (positive = condition-based is cheaper)"
    )
    recommendation: str = Field(default="", description="Human-readable recommendation based on cost comparison")


class OptimizeScheduleRequest(BaseModel):
    """Request body for the optimize-service-schedule endpoint."""

    equipment_ids: list[str] | None = Field(None, description="Equipment IDs to optimize (all if None)")
    fixed_interval_days: int = Field(
        default=90, ge=7, le=365, description="Fixed-schedule interval in days for comparison"
    )


class OptimizedSchedule(BaseModel):
    """Fleet-wide optimized service schedule."""

    equipment_ids: list[str] = Field(default_factory=list, description="Equipment IDs included in schedule")
    schedule: list[ServiceWindow] = Field(default_factory=list, description="Sorted service windows (by optimal_date)")
    total_equipment: int = Field(default=0, description="Total equipment analyzed")
    equipment_needing_service: int = Field(default=0, description="Equipment with active service windows")
    cost_comparison_summary: str = Field(
        default="", description="Summary of cost savings from condition-based approach"
    )
