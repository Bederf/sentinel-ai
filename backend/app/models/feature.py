"""Feature models for ML training datasets.

This module defines the data models for:
- FeatureDefinition: Individual feature specifications
- FeatureSet: Collection of features for an equipment type
- ComputedFeatures: Computed feature values for an equipment
- TrainingDataset: Metadata for a saved training dataset
"""

from datetime import datetime
from typing import Dict, List, Optional, Any, Literal
from pydantic import BaseModel, Field


class FeatureDefinition(BaseModel):
    """Definition of a single feature for ML training.

    Attributes:
        name: Unique feature name (e.g., temp_mean_7d)
        dtype: Data type (float, int, bool)
        description: Human-readable description
        source_sensor: Sensor type to compute from (e.g., temperature)
        aggregation: Aggregation method (mean, std, min, max, trend, count_delta)
        window_days: Time window for computation in days
    """
    name: str = Field(..., description="Unique feature name")
    dtype: Literal["float", "int", "bool"] = Field(default="float", description="Data type")
    description: str = Field(..., description="Human-readable description")
    source_sensor: str = Field(..., description="Sensor type to compute from")
    aggregation: Literal["mean", "std", "min", "max", "trend", "count_delta"] = Field(
        ..., description="Aggregation method"
    )
    window_days: int = Field(..., ge=1, le=365, description="Time window in days")


class FeatureSet(BaseModel):
    """Collection of features for an equipment type.

    Combines common features (applicable to all equipment) with
    type-specific features (e.g., chiller, AHU, generator).
    """
    equipment_type: str = Field(..., description="Equipment type (chiller, ahu, generator)")
    features: List[FeatureDefinition] = Field(..., description="List of feature definitions")

    @property
    def feature_names(self) -> List[str]:
        """Get list of all feature names."""
        return [f.name for f in self.features]

    @property
    def feature_count(self) -> int:
        """Get total number of features."""
        return len(self.features)


class ComputedFeatures(BaseModel):
    """Computed feature values for a single equipment at a point in time.

    Features are stored as a dictionary mapping feature name to value.
    Missing features (insufficient data) have None values.
    """
    equipment_id: str = Field(..., description="Equipment identifier")
    equipment_type: str = Field(..., description="Equipment type")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Computation timestamp")
    features: Dict[str, Optional[float]] = Field(
        default_factory=dict, description="Feature name to value mapping"
    )
    missing_sensors: List[str] = Field(
        default_factory=list, description="Sensors with insufficient data"
    )
    computation_time_ms: Optional[float] = Field(
        None, description="Time taken to compute features in milliseconds"
    )

    @property
    def valid_feature_count(self) -> int:
        """Count features with non-None values."""
        return sum(1 for v in self.features.values() if v is not None)

    @property
    def completeness(self) -> float:
        """Fraction of features with valid values (0.0 to 1.0)."""
        if not self.features:
            return 0.0
        return self.valid_feature_count / len(self.features)


class FeatureBatchRequest(BaseModel):
    """Request to compute features for multiple equipment."""
    equipment_ids: List[str] = Field(..., min_length=1, description="Equipment IDs to compute")
    equipment_type: str = Field(..., description="Equipment type (all must be same type)")
    as_of: Optional[datetime] = Field(None, description="Compute features as of this time")


class FeatureBatchResponse(BaseModel):
    """Response containing computed features for multiple equipment."""
    equipment_type: str = Field(..., description="Equipment type")
    as_of: datetime = Field(..., description="Features computed as of this time")
    results: List[ComputedFeatures] = Field(..., description="Computed features per equipment")
    total_computation_time_ms: float = Field(..., description="Total computation time")

    @property
    def average_completeness(self) -> float:
        """Average feature completeness across all equipment."""
        if not self.results:
            return 0.0
        return sum(r.completeness for r in self.results) / len(self.results)


class TrainingDatasetMetadata(BaseModel):
    """Metadata for a saved training dataset."""
    name: str = Field(..., description="Dataset name")
    version: str = Field(..., description="Dataset version (e.g., v1, v2)")
    equipment_type: str = Field(..., description="Equipment type")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    start_date: datetime = Field(..., description="Data start date")
    end_date: datetime = Field(..., description="Data end date")
    sample_interval_days: int = Field(..., description="Sampling interval in days")
    row_count: int = Field(..., description="Number of rows in dataset")
    equipment_count: int = Field(..., description="Number of unique equipment")
    feature_count: int = Field(..., description="Number of features")
    feature_names: List[str] = Field(..., description="List of feature names")
    label_column: Optional[str] = Field(None, description="Label column name if labeled")
    label_positive_count: Optional[int] = Field(None, description="Positive label count")
    file_path: str = Field(..., description="Path to parquet file")
    file_size_bytes: int = Field(default=0, description="File size in bytes")


class TrainingDataRequest(BaseModel):
    """Request to generate a training dataset."""
    equipment_type: str = Field(..., description="Equipment type to generate data for")
    start_date: datetime = Field(..., description="Start date for data")
    end_date: datetime = Field(..., description="End date for data")
    sample_interval_days: int = Field(
        default=7, ge=1, le=30, description="Days between samples"
    )
    name: str = Field(..., description="Dataset name")
    version: str = Field(default="v1", description="Dataset version")
    add_labels: bool = Field(
        default=False, description="Add failure labels from work order history"
    )
    label_lookahead_days: int = Field(
        default=30, ge=7, le=90, description="Days ahead to look for failures"
    )


class FeatureDefinitionsResponse(BaseModel):
    """Response containing all feature definitions."""
    version: str = Field(..., description="Feature definitions version")
    common_features: List[FeatureDefinition] = Field(..., description="Common features")
    equipment_specific: Dict[str, List[FeatureDefinition]] = Field(
        ..., description="Equipment-specific features by type"
    )

    def get_features_for_type(self, equipment_type: str) -> FeatureSet:
        """Get all features for an equipment type (common + specific)."""
        features = list(self.common_features)
        if equipment_type in self.equipment_specific:
            features.extend(self.equipment_specific[equipment_type])
        return FeatureSet(equipment_type=equipment_type, features=features)
