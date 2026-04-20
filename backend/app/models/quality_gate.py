"""Quality Gate Pydantic response models — Phase 109.

API response models for the quality gate evaluation endpoint.
Used by the /api/quality-gate/* routes to serialize gate results.
"""


from pydantic import BaseModel, Field


class QualityMetricDetail(BaseModel):
    """Detail for a single quality metric evaluation."""

    metric: str = Field(description="Metric name (e.g. 'freshness_minutes')")
    value: float = Field(description="Current metric value")
    state: str = Field(description="Evaluation state: pass/warn/fail/na")
    pass_bound: float | None = Field(default=None, description="Threshold for PASS")
    warn_bound: float | None = Field(default=None, description="Threshold for WARN")


class QualityGateResponse(BaseModel):
    """Response from quality gate evaluation."""

    overall_status: str = Field(description="Overall gate: pass/warn/fail")
    enforcement_action: str = Field(description="Enforcement: normal/cap_confidence/suppress_tier3/block_writes")
    mode: str = Field(description="Ingestion mode used for evaluation")
    metrics: list[QualityMetricDetail] = Field(default_factory=list, description="Per-metric evaluation details")
    failed_rules: list[str] = Field(default_factory=list, description="Metric names that failed")
    warn_rules: list[str] = Field(default_factory=list, description="Metric names that warned")
    reason_codes: list[str] = Field(default_factory=list, description="Machine-readable reason codes for failures")
    evaluated_at: str = Field(description="ISO timestamp of evaluation")


class QualityGateStatusResponse(BaseModel):
    """Full status response including thresholds and metric values."""

    site_id: str = Field(description="Site identifier")
    ingestion_mode: str = Field(description="Current ingestion mode")
    thresholds_used: str = Field(description="Mode whose thresholds were applied")
    metric_values: dict = Field(default_factory=dict, description="Raw metric values collected")
    rule_results: list[QualityMetricDetail] = Field(default_factory=list, description="Per-metric evaluation results")
    overall_status: str = Field(description="Overall gate: pass/warn/fail")
    enforcement_action: str = Field(description="Enforcement action applied")
    reason_codes: list[str] = Field(default_factory=list, description="Machine-readable reason codes")
