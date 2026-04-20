"""Features API - ML Feature Store Endpoints.

This module provides REST API endpoints for:
- Real-time feature computation for equipment
- Batch feature computation
- Feature definitions listing
- Training dataset generation and management
"""

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.models.feature import (
    ComputedFeatures,
    FeatureBatchRequest,
    FeatureBatchResponse,
    FeatureDefinitionsResponse,
    TrainingDataRequest,
    TrainingDatasetMetadata,
)
from app.services.feature_service import get_feature_service
from app.services.training_data_service import get_training_data_service

router = APIRouter(prefix="/api/features", tags=["features"])


# Response models
class DatasetListResponse(BaseModel):
    """Response containing list of training datasets."""

    datasets: list[TrainingDatasetMetadata] = Field(..., description="List of available training datasets")
    count: int = Field(..., description="Total count of datasets")


class TrainingDataResponse(BaseModel):
    """Response after generating training data."""

    success: bool = Field(..., description="Whether generation succeeded")
    message: str = Field(..., description="Status message")
    metadata: TrainingDatasetMetadata | None = Field(None, description="Dataset metadata if saved")


# Feature Definition Endpoints


@router.get("/definitions", response_model=FeatureDefinitionsResponse)
async def get_feature_definitions():
    """Get all feature definitions.

    Returns feature definitions organized by:
    - common: Features applicable to all equipment types
    - equipment_specific: Features for chiller, AHU, generator
    """
    service = get_feature_service()
    return service.get_definitions()


@router.get("/definitions/{equipment_type}")
async def get_feature_definitions_for_type(equipment_type: str):
    """Get feature definitions for a specific equipment type.

    Args:
        equipment_type: Equipment type (chiller, ahu, generator)

    Returns:
        FeatureSet with all applicable features
    """
    service = get_feature_service()
    feature_set = service.get_feature_set(equipment_type.lower())
    return {
        "equipment_type": equipment_type,
        "feature_count": feature_set.feature_count,
        "features": [f.model_dump() for f in feature_set.features],
    }


# Real-time Feature Endpoints


@router.get("/equipment/{equipment_id}", response_model=ComputedFeatures)
async def get_equipment_features(
    equipment_id: str,
    equipment_type: str = Query(..., description="Equipment type (chiller, ahu, generator)"),
    as_of: datetime | None = Query(None, description="Compute features as of this time"),
):
    """Compute features for a single equipment.

    Computes all applicable features (common + type-specific) for the
    specified equipment using sensor data from InfluxDB.

    Args:
        equipment_id: Equipment identifier
        equipment_type: Equipment type
        as_of: Optional timestamp to compute features at (default: now)

    Returns:
        ComputedFeatures with feature values and metadata
    """
    service = get_feature_service()
    return service.compute_features(
        equipment_id=equipment_id,
        equipment_type=equipment_type.lower(),
        as_of=as_of,
    )


@router.post("/batch", response_model=FeatureBatchResponse)
async def compute_batch_features(request: FeatureBatchRequest):
    """Compute features for multiple equipment in batch.

    All equipment must be of the same type. Returns features for
    each equipment with overall timing metrics.

    Args:
        request: FeatureBatchRequest with equipment IDs and type

    Returns:
        FeatureBatchResponse with results for all equipment
    """
    service = get_feature_service()
    return service.compute_batch(
        equipment_ids=request.equipment_ids,
        equipment_type=request.equipment_type.lower(),
        as_of=request.as_of,
    )


# Training Data Endpoints


@router.post("/training-data", response_model=TrainingDataResponse)
async def generate_training_data(request: TrainingDataRequest):
    """Generate and save a training dataset.

    Generates features at regular intervals over the specified date range
    for all equipment of the given type. Optionally adds failure labels
    from work order history.

    Args:
        request: TrainingDataRequest with generation parameters

    Returns:
        TrainingDataResponse with success status and metadata
    """
    service = get_training_data_service()

    try:
        # Generate features
        df = service.generate_training_data(
            equipment_type=request.equipment_type.lower(),
            start_date=request.start_date,
            end_date=request.end_date,
            sample_interval_days=request.sample_interval_days,
        )

        if df is None:
            return TrainingDataResponse(
                success=False,
                message="Failed to generate training data. Check if pandas is installed.",
                metadata=None,
            )

        if len(df) == 0:
            return TrainingDataResponse(
                success=False,
                message=f"No equipment found for type: {request.equipment_type}",
                metadata=None,
            )

        # Add labels if requested
        label_column = None
        if request.add_labels:
            label_column = f"failure_{request.label_lookahead_days}d"
            df = service.add_labels(
                df=df,
                lookahead_days=request.label_lookahead_days,
            )

        # Save dataset
        metadata = service.save_dataset(
            df=df,
            name=request.name,
            version=request.version,
            equipment_type=request.equipment_type.lower(),
            start_date=request.start_date,
            end_date=request.end_date,
            sample_interval_days=request.sample_interval_days,
            label_column=label_column,
        )

        return TrainingDataResponse(
            success=True,
            message=f"Generated {metadata.row_count} samples with {metadata.feature_count} features",
            metadata=metadata,
        )

    except Exception as e:
        return TrainingDataResponse(
            success=False,
            message=f"Error generating training data: {e!s}",
            metadata=None,
        )


@router.get("/datasets", response_model=DatasetListResponse)
async def list_datasets(
    equipment_type: str | None = Query(None, description="Filter by equipment type"),
):
    """List all available training datasets.

    Returns metadata for all saved training datasets, optionally
    filtered by equipment type.

    Args:
        equipment_type: Optional filter by equipment type

    Returns:
        DatasetListResponse with list of datasets
    """
    service = get_training_data_service()
    datasets = service.list_datasets()

    if equipment_type:
        datasets = [d for d in datasets if d.equipment_type == equipment_type.lower()]

    return DatasetListResponse(
        datasets=datasets,
        count=len(datasets),
    )


@router.get("/datasets/{name}/{version}", response_model=TrainingDatasetMetadata)
async def get_dataset_metadata(name: str, version: str):
    """Get metadata for a specific training dataset.

    Args:
        name: Dataset name
        version: Dataset version

    Returns:
        TrainingDatasetMetadata for the dataset

    Raises:
        HTTPException 404 if dataset not found
    """
    service = get_training_data_service()
    metadata = service.get_dataset(name, version)

    if not metadata:
        raise HTTPException(status_code=404, detail=f"Dataset not found: {name}_{version}")

    return metadata


@router.delete("/datasets/{name}/{version}")
async def delete_dataset(name: str, version: str):
    """Delete a training dataset.

    Removes the dataset file and its registry entry.

    Args:
        name: Dataset name
        version: Dataset version

    Returns:
        Success message

    Raises:
        HTTPException 404 if dataset not found
    """
    service = get_training_data_service()
    deleted = service.delete_dataset(name, version)

    if not deleted:
        raise HTTPException(status_code=404, detail=f"Dataset not found: {name}_{version}")

    return {"message": f"Deleted dataset: {name}_{version}"}
