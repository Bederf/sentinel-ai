"""
Health Rating models for the 5-component weighted assessment formula.

Phase 109B: Health Assessment Timeline

These models represent the output of HealthRatingCalculator and
HealthDataQualityGate, stored as asset_health_snapshots in the database.

Key invariant: health_status is ALWAYS determined by HealthThresholdService,
never computed locally by the calculator.
"""


from pydantic import BaseModel, Field


class HealthComponentBreakdown(BaseModel):
    """Individual component scores from the 5-component formula.

    Each score is in the range [0, 100]. Weights:
        baseline_alignment  = 0.35
        service_compliance  = 0.20
        runtime_age         = 0.20
        fault_burden        = 0.15
        trend_momentum      = 0.10
    """

    baseline_alignment_score: float | None = Field(
        None, ge=0, le=100, description="Score from baseline deviation (weight 0.35)"
    )
    service_compliance_score: float | None = Field(
        None, ge=0, le=100, description="Score from service schedule adherence (weight 0.20)"
    )
    runtime_age_score: float | None = Field(
        None, ge=0, le=100, description="Score from runtime hours and age vs expected life (weight 0.20)"
    )
    fault_burden_score: float | None = Field(
        None, ge=0, le=100, description="Score from fault count and severity (weight 0.15)"
    )
    trend_momentum_score: float | None = Field(
        None, ge=0, le=100, description="Score from health trend slope (weight 0.10)"
    )


class HealthDataQualityResult(BaseModel):
    """Output of the data quality gate evaluation.

    Evaluates data freshness, snapshot density, point validity, and
    baseline recency against mode-specific thresholds.
    """

    freshness_minutes: float = Field(..., description="Minutes since last sensor data")
    snapshot_count_24h: int = Field(..., description="Number of snapshots in last 24 hours")
    valid_point_ratio: float = Field(..., ge=0, le=1, description="Ratio of valid data points (0.0-1.0)")
    baseline_age_days: int = Field(..., description="Days since last baseline capture")
    gates_passed: int = Field(..., ge=0, description="Number of quality gates passed")
    gates_total: int = Field(..., ge=0, description="Total number of quality gates evaluated")
    confidence: str = Field(..., description="Confidence level: 'high' (all pass), 'medium' (1 fail), 'low' (2+ fail)")
    assessment_state: str = Field(..., description="Assessment state: 'normal' or 'degraded_data'")


class HealthRating(BaseModel):
    """Complete health rating for a single equipment item.

    Combines the overall score, status (from HealthThresholdService),
    component breakdown, and data quality assessment.
    """

    equipment_id: str = Field(..., description="Equipment code or UUID")
    health_score: float = Field(..., ge=0, le=100, description="Weighted composite health score")
    health_status: str = Field(..., description="'healthy' | 'warning' | 'critical' — from HealthThresholdService only")
    confidence: str = Field(..., description="Data quality confidence: 'high' | 'medium' | 'low'")
    assessment_state: str = Field(..., description="'normal' | 'degraded_data' | 'insufficient_data'")
    components: HealthComponentBreakdown = Field(..., description="Breakdown of individual component scores")
    data_quality: HealthDataQualityResult = Field(..., description="Data quality gate evaluation result")
    formula_version: str = Field("v1", description="Version of the scoring formula")
    snapshot_at: str = Field(..., description="ISO timestamp when this rating was computed")


class DailyRollup(BaseModel):
    """Daily aggregation of health snapshots for trend display."""

    date: str = Field(..., description="Date in YYYY-MM-DD format")
    score_min: float | None = Field(None, description="Minimum health score for the day")
    score_max: float | None = Field(None, description="Maximum health score for the day")
    score_avg: float | None = Field(None, description="Average health score for the day")
    status_mode: str | None = Field(None, description="Most common status for the day")
    confidence_mode: str | None = Field(None, description="Most common confidence for the day")
    snapshot_count: int = Field(0, description="Number of snapshots in the day")


class HealthRatingHistory(BaseModel):
    """Historical health ratings for an equipment item."""

    equipment_id: str = Field(..., description="Equipment code or UUID")
    range_days: int = Field(..., description="Number of days in the history range")
    snapshots: list[HealthRating] = Field(default_factory=list, description="Individual snapshots within the range")
    daily_rollups: list[DailyRollup] = Field(default_factory=list, description="Daily aggregated rollups")


class AssetHealthSummaryItem(BaseModel):
    """Summary view of a single asset's health for list/dashboard display."""

    equipment_id: str = Field(..., description="Equipment code or UUID")
    equipment_name: str = Field(..., description="Human-readable equipment name")
    equipment_type: str = Field(..., description="Equipment type (e.g. CHILLER, AHU)")
    category: str = Field(..., description="Equipment category (e.g. HVAC, Lighting)")
    health_score: float = Field(..., ge=0, le=100, description="Current health score")
    health_status: str = Field(..., description="'healthy' | 'warning' | 'critical' — from HealthThresholdService")
    confidence: str = Field(..., description="Data quality confidence level")
    trend_7d: float | None = Field(None, description="7-day score trend (positive = improving)")
    trend_30d: float | None = Field(None, description="30-day score trend")
    has_active_baseline: bool = Field(False, description="Whether equipment has an active baseline")
    last_baseline_at: str | None = Field(None, description="ISO timestamp of active baseline")
    max_deviation_percent_24h: float | None = Field(None, description="Max deviation % in last 24 hours")
    deviation_status: str | None = Field(None, description="'normal' | 'warning' | 'critical' | None")
    assessment_state: str = Field("normal", description="Assessment data quality state")
    health_updated_at: str | None = Field(None, description="ISO timestamp of last health update")
    health_source: str = Field("calculator", description="'calculator' | 'simulation' | 'manual_override'")


class HealthFeaturePayload(BaseModel):
    """Health signals for recommendation ranking. Separate from risk probability.

    HARD RULE: This payload contains ONLY health assessment data.
    It NEVER contains risk probabilities or failure predictions.
    Risk prediction is a separate concern handled by PredictionGeneratorService.
    """

    health_score_current: float = Field(..., ge=0, le=100, description="Current composite health score (0-100)")
    health_status_current: str = Field(..., description="Current health status: 'healthy' | 'warning' | 'critical'")
    health_trend_7d_slope: float | None = Field(
        None, description="7-day health score trend slope (points/day, negative = improving)"
    )
    health_trend_30d_slope: float | None = Field(
        None, description="30-day health score trend slope (points/day, negative = improving)"
    )
    health_volatility_30d: float | None = Field(
        None, description="30-day health score volatility (stddev of daily avg scores)"
    )
    health_confidence: str = Field(..., description="Data quality confidence: 'high' | 'medium' | 'low'")
    baseline_deviation_max_24h: float | None = Field(
        None, description="Maximum baseline deviation percentage in last 24 hours"
    )


class RecomputeRequest(BaseModel):
    """Request to recompute health ratings."""

    equipment_id: str | None = Field(None, description="Single equipment to recompute")
    site_id: str | None = Field(None, description="Recompute all equipment at a site")
    scope: str = Field("single", description="Scope of recompute: 'single' | 'site' | 'all'")


class RecomputeResult(BaseModel):
    """Result of a health rating recompute operation."""

    scope: str = Field(..., description="Scope that was processed")
    equipment_processed: int = Field(0, description="Number of equipment items processed")
    equipment_failed: int = Field(0, description="Number of equipment items that failed")
    duration_ms: int = Field(0, description="Total duration in milliseconds")
