"""Pydantic models for real-time equipment status streaming.

Used by the Digital Twin SSE endpoint to push equipment status
updates and predictive fault overlays to the frontend.
"""

from datetime import datetime

from pydantic import BaseModel, Field


class EquipmentStatusUpdate(BaseModel):
    """Real-time status update for a single equipment item."""

    equipment_id: str = Field(..., description="Equipment UUID")
    code: str = Field(..., description="Equipment code (e.g., S002-AHU-B1-001)")
    type: str = Field(..., description="Equipment type (e.g., ahu, chiller)")
    health_score: float = Field(..., ge=0, le=100, description="Current health score 0-100")
    status: str = Field(..., description="Current status (online, offline, fault, warning)")
    power_kw: float | None = Field(None, description="Current power consumption in kW")
    temperatures: dict | None = Field(None, description="Temperature readings (supply, return, etc.)")
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class PredictiveFault(BaseModel):
    """LSTM/ML prediction mapped for visualization overlay."""

    equipment_id: str = Field(..., description="Equipment UUID")
    prediction_type: str = Field(..., description="Type of prediction (e.g., bearing_failure, motor_degradation)")
    severity: str = Field(..., description="Severity level: critical (<7d) or warning (<30d)")
    timeframe_days: int = Field(..., ge=0, description="Days until predicted failure")
    confidence: float = Field(..., ge=0, le=1, description="Model confidence 0.0-1.0")
    model_name: str | None = Field(None, description="ML model that generated this prediction")


class EquipmentStatusFrame(BaseModel):
    """A single SSE frame containing all equipment updates and predictions for a site."""

    site_id: str = Field(..., description="Site UUID")
    equipment_updates: list[EquipmentStatusUpdate] = Field(default_factory=list)
    predictions: list[PredictiveFault] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
