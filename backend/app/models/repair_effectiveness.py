"""
Repair Effectiveness Models - Pydantic models for post-repair validation

Phase 57: Repair Effectiveness
Plan 01: Core service and API endpoints

Models for recording repair outcomes, calculating effectiveness scores,
tracking element-level improvements, and health score recalculation.
"""

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


# ============================================================================
# Core Models
# ============================================================================


class RepairOutcome(BaseModel):
    """Records a repair event with metadata."""

    equipment_id: str = Field(..., description="Equipment identifier (v2.0 format)")
    work_order_id: str = Field(..., description="Work order reference")
    repair_type: str = Field(..., description="Type of repair (e.g., bearing_replacement, filter_change)")
    repair_date: datetime = Field(default_factory=datetime.now, description="When repair was performed")
    technician: str = Field(..., description="Technician who performed the repair")
    parts_used: List[str] = Field(default_factory=list, description="Parts used in repair")
    labor_hours: float = Field(default=0.0, ge=0, description="Labor hours spent")
    repair_cost: float = Field(default=0.0, ge=0, description="Total repair cost (ZAR)")
    fault_description: str = Field(default="", description="Description of the fault")
    actions_taken: str = Field(default="", description="Description of repair actions taken")


class ElementImprovement(BaseModel):
    """Per-element improvement detail from pre/post repair comparison."""

    element_name: str = Field(..., description="Element/measurement point name")
    pre_value: float = Field(..., description="Pre-repair measurement value")
    post_value: float = Field(..., description="Post-repair measurement value")
    baseline_value: float = Field(..., description="Original baseline value")
    improvement_percent: float = Field(..., description="Improvement as percentage")
    back_to_baseline: bool = Field(default=False, description="Whether element returned to baseline")
    status: str = Field(default="unchanged", description="Status: improved, unchanged, or worsened")


class EffectivenessScore(BaseModel):
    """Computed effectiveness result from pre/post repair comparison."""

    work_order_id: str = Field(..., description="Work order reference")
    equipment_id: str = Field(..., description="Equipment identifier")
    pre_baseline_id: str = Field(default="", description="Pre-repair baseline ID")
    post_baseline_id: str = Field(default="", description="Post-repair baseline ID")
    effectiveness_score: float = Field(..., ge=0, le=100, description="Overall effectiveness score (0-100)")
    element_improvements: Dict[str, ElementImprovement] = Field(
        default_factory=dict, description="Per-element improvement details"
    )
    repair_successful: bool = Field(default=False, description="Whether repair met success threshold")
    back_to_baseline: bool = Field(default=False, description="Whether all elements returned to baseline")
    health_score_before: float = Field(default=0.0, ge=0, le=100, description="Health score before repair")
    health_score_after: float = Field(default=0.0, ge=0, le=100, description="Health score after repair")
    health_improvement: float = Field(default=0.0, description="Health score improvement (points)")
    validated_at: datetime = Field(default_factory=datetime.now, description="When validation was performed")


class HealthScoreUpdate(BaseModel):
    """Equipment health recalculation result."""

    equipment_id: str = Field(..., description="Equipment identifier")
    previous_score: float = Field(default=100.0, ge=0, le=100, description="Previous health score")
    new_score: float = Field(default=100.0, ge=0, le=100, description="Newly calculated health score")
    contributing_factors: Dict[str, float] = Field(
        default_factory=dict, description="Factors contributing to score (element_name -> score contribution)"
    )
    updated_at: datetime = Field(default_factory=datetime.now, description="When score was updated")


# ============================================================================
# Request / Response Models
# ============================================================================


class RepairEffectivenessRequest(BaseModel):
    """API request for repair effectiveness validation."""

    equipment_id: str = Field(..., description="Equipment identifier")
    work_order_id: str = Field(..., description="Work order reference")
    post_repair_readings: Optional[Dict[str, float]] = Field(
        None, description="Post-repair readings (if None, fetch from BMS)"
    )


class RepairHistoryEntry(BaseModel):
    """Summary entry for repair history queries."""

    work_order_id: str = Field(..., description="Work order reference")
    equipment_id: str = Field(..., description="Equipment identifier")
    repair_date: datetime = Field(..., description="When repair was performed")
    effectiveness_score: float = Field(..., description="Effectiveness score (0-100)")
    repair_successful: bool = Field(default=False, description="Whether repair was successful")
    repair_cost: float = Field(default=0.0, description="Repair cost (ZAR)")
    fault_type: str = Field(default="", description="Type of fault repaired")
