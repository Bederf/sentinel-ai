"""Models for simulation analytics pipeline."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class OptimizationProfile(BaseModel):
    """Defines weight distribution for analyzing simulation results."""
    name: str
    description: str
    weights: Dict[str, float] = Field(
        description="Weight factors: runtime, comfort, cost, maintenance, energy (sum to 1.0)"
    )
    thresholds: Dict[str, float] = Field(
        default_factory=dict,
        description="Profile-specific thresholds (e.g. max_comfort_deviation_c)"
    )


class SimulationRunRecord(BaseModel):
    """Metadata for a single simulation run."""
    run_id: str
    scenario: str
    building_code: str
    started_at: str
    ended_at: Optional[str] = None
    duration_minutes: Optional[float] = None
    event_count: int = 0
    events_file: str
    config: Dict[str, Any] = Field(default_factory=dict)


class SimulationEvent(BaseModel):
    """A single event from a simulation JSONL log."""
    timestamp: str
    simulated_hour: int
    event_type: str
    equipment_id: Optional[str] = None
    equipment_name: Optional[str] = None
    description: str = ""
    details: Dict[str, Any] = Field(default_factory=dict)
    success: bool = True


class SimulationMetrics(BaseModel):
    """Computed metrics from simulation events."""
    total_events: int = 0
    total_faults: int = 0
    faults_repaired: int = 0
    mean_time_to_repair_hours: Optional[float] = None
    alerts_generated: int = 0
    work_orders_created: int = 0
    ai_optimizations: int = 0
    setpoint_changes: int = 0
    comfort_deviations: List[Dict[str, Any]] = Field(default_factory=list)
    equipment_runtime_hours: Dict[str, float] = Field(default_factory=dict)
    energy_events: int = 0
    fault_types: Dict[str, int] = Field(default_factory=dict)
    events_by_hour: Dict[int, int] = Field(default_factory=dict)


class ProfileAnalysisResult(BaseModel):
    """Analysis result for a single optimization profile."""
    profile_name: str
    overall_score: float = Field(description="Weighted score 0-100")
    component_scores: Dict[str, float] = Field(
        description="Individual dimension scores"
    )
    recommendations: List[str] = Field(default_factory=list)
    flags: List[str] = Field(
        default_factory=list,
        description="Threshold violations or notable findings"
    )


class SimulationAnalysisReport(BaseModel):
    """Full analysis report for a simulation run."""
    run_id: str
    scenario: str
    building_code: str
    analyzed_at: str
    metrics: SimulationMetrics
    profile_results: Dict[str, ProfileAnalysisResult] = Field(
        description="Analysis results keyed by profile name"
    )
