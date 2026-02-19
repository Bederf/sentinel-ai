"""
ML Feedback Models - Pydantic models for ML feedback loop

Phase 57: Repair Effectiveness
Plan 02: ML Feedback Loop

Models for recording repair outcomes, generating ML training data,
and tracking prediction accuracy to close the loop between
ML predictions and real-world maintenance results.
"""

from datetime import datetime
from typing import Dict, Optional

from pydantic import BaseModel, Field


# ============================================================================
# Core Data Models
# ============================================================================


class MLFeedbackRecord(BaseModel):
    """Single ML feedback entry recording a repair outcome or prediction evaluation."""

    id: str = Field(default="", description="Auto-generated feedback record ID")
    equipment_id: str = Field(..., description="Equipment identifier")
    work_order_id: str = Field(..., description="Related work order ID")
    feedback_type: str = Field(
        default="repair_outcome",
        description="Type of feedback: repair_outcome, prediction_accuracy, anomaly_confirmation, module_outcome",
    )
    repair_successful: bool = Field(default=False, description="Whether the repair was successful")
    effectiveness_score: float = Field(default=0.0, description="Repair effectiveness score (%)")
    prediction_id: Optional[str] = Field(None, description="Links to ML prediction that triggered this")
    predicted_failure_type: Optional[str] = Field(None, description="What was predicted to fail")
    actual_failure_type: Optional[str] = Field(None, description="What actually failed")
    prediction_was_correct: Optional[bool] = Field(None, description="Whether prediction matched actual outcome")
    time_to_failure_predicted: Optional[int] = Field(None, description="Predicted days to failure")
    time_to_failure_actual: Optional[int] = Field(None, description="Actual days to failure")
    recorded_at: datetime = Field(default_factory=datetime.now, description="When feedback was recorded")
    metadata: Dict = Field(default_factory=dict, description="Additional metadata")


class TrainingDataPoint(BaseModel):
    """Training data point for ML model retraining."""

    equipment_id: str = Field(..., description="Equipment identifier")
    equipment_type: str = Field(..., description="Type of equipment (chiller, ahu, fcu, etc.)")
    features: Dict[str, float] = Field(default_factory=dict, description="Flattened sensor readings and feature values")
    label: str = Field(..., description="Outcome label: failed, repaired, healthy")
    failure_type: Optional[str] = Field(None, description="Specific failure type if applicable")
    days_to_failure: Optional[int] = Field(None, description="Days until failure occurred")
    repair_effectiveness: Optional[float] = Field(None, description="Effectiveness of repair (0-100)")
    source: str = Field(default="repair_outcome", description="Data source: repair_outcome, inspection, baseline")


class PredictionAccuracy(BaseModel):
    """Accuracy tracking metrics for a specific ML model type."""

    model_type: str = Field(..., description="Model type: lstm, autoencoder, survival, random_forest")
    total_predictions: int = Field(default=0, description="Total predictions evaluated")
    correct_predictions: int = Field(default=0, description="Number of correct predictions")
    false_positives: int = Field(default=0, description="Predicted failure but none occurred")
    false_negatives: int = Field(default=0, description="Missed actual failures")
    accuracy_percent: float = Field(default=0.0, description="Overall accuracy percentage")
    precision: float = Field(default=0.0, description="Precision: TP / (TP + FP)")
    recall: float = Field(default=0.0, description="Recall: TP / (TP + FN)")
    last_evaluated: datetime = Field(default_factory=datetime.now, description="Last evaluation timestamp")


class MLFeedbackSummary(BaseModel):
    """Dashboard summary of ML feedback system status."""

    total_feedback_records: int = Field(default=0, description="Total feedback records stored")
    repair_outcomes_recorded: int = Field(default=0, description="Number of repair outcomes recorded")
    predictions_evaluated: int = Field(default=0, description="Number of predictions evaluated")
    avg_prediction_accuracy: float = Field(default=0.0, description="Average accuracy across all models")
    model_accuracies: Dict[str, PredictionAccuracy] = Field(
        default_factory=dict, description="Accuracy metrics per model type"
    )
    training_data_points: int = Field(default=0, description="Total training data points generated")
    module_feedback_records: int = Field(default=0, description="Number of module_outcome records")
    module_feedback_counts: Dict[str, int] = Field(
        default_factory=dict, description="Feedback record counts by module type"
    )
    module_success_rates: Dict[str, float] = Field(
        default_factory=dict, description="Module outcome success rates (%) by module type"
    )
    last_retrain_date: Optional[datetime] = Field(None, description="Last ML model retrain date")


# ============================================================================
# API Request Models
# ============================================================================


class RecordFeedbackRequest(BaseModel):
    """Request body for recording repair feedback."""

    equipment_id: str = Field(..., description="Equipment identifier")
    work_order_id: str = Field(..., description="Work order ID")
    effectiveness_score: float = Field(..., ge=0, le=100, description="Repair effectiveness score (%)")
    repair_successful: bool = Field(..., description="Whether the repair was successful")
    failure_type: Optional[str] = Field(None, description="Type of failure that was repaired")
    prediction_id: Optional[str] = Field(None, description="ML prediction ID that triggered this repair")
