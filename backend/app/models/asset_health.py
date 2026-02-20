"""
Asset Health + Baseline response model.

Phase 109A: Surfaces baseline and health metadata on the equipment list.

Deviation classification is baseline-specific (NOT from HealthThresholdService):
- None: no comparisons in last 24h
- "normal": max deviation <= 15%
- "warning": 15% < max deviation < 30%
- "critical": max deviation >= 30%
"""

from typing import Optional

from pydantic import BaseModel, Field


class AssetHealthBaseline(BaseModel):
    """Combined health + baseline snapshot for a single equipment item."""

    # Equipment identity
    equipment_id: str = Field(..., description="Equipment code (e.g. S002-CHILLER-B1-001)")
    equipment_name: str = Field(..., description="Human-readable equipment name")
    equipment_type: str = Field(..., description="Equipment type (e.g. CHILLER, AHU)")
    category: str = Field(..., description="Equipment category (e.g. HVAC, Lighting)")

    # Health (from equipment table + HealthThresholdService)
    health_score: int = Field(..., description="Current health score 0-100")
    health_status: str = Field(..., description="'healthy' | 'warning' | 'critical' via HealthThresholdService")
    health_source: str = Field(
        "equipment_table",
        description="Origin: 'equipment_table' | 'alert_override' | 'simulation'",
    )
    health_updated_at: Optional[str] = Field(None, description="ISO timestamp of last health update")

    # Baseline
    has_active_baseline: bool = Field(False, description="Whether equipment has an active baseline")
    last_baseline_at: Optional[str] = Field(None, description="ISO timestamp of the active baseline capture date")
    total_baselines: int = Field(0, description="Total number of baselines ever captured")
    baseline_source: Optional[str] = Field(None, description="'manual' | 'bms_average' | 'mobile_sensor' | None")

    # Deviation (last 24h from baseline_comparisons)
    max_deviation_percent_24h: Optional[float] = Field(
        None, description="Maximum deviation % observed in last 24 hours"
    )
    deviation_status: Optional[str] = Field(None, description="'normal' | 'warning' | 'critical' | None")

    # Health assessment timeline fields (Phase 109B — optional for backward compat)
    confidence: Optional[str] = Field(None, description="Data quality confidence: 'high' | 'medium' | 'low'")
    trend_7d: Optional[float] = Field(None, description="7-day health score slope (points per day)")
    trend_30d: Optional[float] = Field(None, description="30-day health score slope (points per day)")
    assessment_state: Optional[str] = Field(None, description="'normal' | 'degraded_data' | 'insufficient_data'")
