"""Training Data Generation Service.

This service generates training datasets for ML models by:
- Computing features at regular intervals over a date range
- Adding labels from work order history
- Saving datasets in parquet format with metadata

Training datasets are saved to backend/app/data/training/
with metadata stored in a registry JSON file.
"""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

try:
    import pandas as pd

    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False
    pd = None

from app.models.feature import (
    TrainingDatasetMetadata,
)
from app.services.feature_service import get_feature_service

logger = logging.getLogger(__name__)

# Singleton instance
_training_data_service: Optional["TrainingDataService"] = None


class TrainingDataService:
    """Service for generating and managing ML training datasets."""

    def __init__(self, data_dir: str | None = None):
        """Initialize the training data service.

        Args:
            data_dir: Directory for training data files.
                     Defaults to backend/app/data/training/
        """
        data_dir = Path(__file__).parent.parent / "data" / "training" if data_dir is None else Path(data_dir)

        self._data_dir = data_dir
        self._registry_path = data_dir / "registry.json"
        self._feature_service = get_feature_service()

        # Ensure directory exists
        self._data_dir.mkdir(parents=True, exist_ok=True)

        # Load or create registry
        self._registry: dict[str, TrainingDatasetMetadata] = {}
        self._load_registry()

    def _load_registry(self) -> None:
        """Load dataset registry from JSON file."""
        if self._registry_path.exists():
            try:
                with open(self._registry_path) as f:
                    data = json.load(f)
                for key, meta in data.items():
                    # Parse datetime strings
                    meta["created_at"] = datetime.fromisoformat(meta["created_at"])
                    meta["start_date"] = datetime.fromisoformat(meta["start_date"])
                    meta["end_date"] = datetime.fromisoformat(meta["end_date"])
                    self._registry[key] = TrainingDatasetMetadata(**meta)
                logger.info(f"Loaded {len(self._registry)} datasets from registry")
            except Exception as e:
                logger.error(f"Failed to load registry: {e}")

    def _save_registry(self) -> None:
        """Save dataset registry to JSON file."""
        try:
            data = {}
            for key, meta in self._registry.items():
                meta_dict = meta.model_dump()
                # Convert datetime to ISO string
                meta_dict["created_at"] = meta_dict["created_at"].isoformat()
                meta_dict["start_date"] = meta_dict["start_date"].isoformat()
                meta_dict["end_date"] = meta_dict["end_date"].isoformat()
                data[key] = meta_dict

            with open(self._registry_path, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save registry: {e}")

    def _get_equipment_ids(self, equipment_type: str) -> list[str]:
        """Get equipment IDs of a given type from equipment.json.

        Args:
            equipment_type: Equipment type (chiller, ahu, generator)

        Returns:
            List of equipment IDs
        """
        equipment_path = Path(__file__).parent.parent / "data" / "equipment.json"
        try:
            with open(equipment_path) as f:
                equipment = json.load(f)
            return [eq["id"] for eq in equipment if eq.get("type", "").lower() == equipment_type.lower()]
        except Exception as e:
            logger.error(f"Failed to load equipment: {e}")
            return []

    def generate_training_data(
        self,
        equipment_type: str,
        start_date: datetime,
        end_date: datetime,
        sample_interval_days: int = 7,
    ) -> Optional["pd.DataFrame"]:
        """Generate training data for equipment type.

        Args:
            equipment_type: Equipment type (chiller, ahu, generator)
            start_date: Start date for data generation
            end_date: End date for data generation
            sample_interval_days: Days between samples

        Returns:
            pandas DataFrame with equipment_id, timestamp, and features
            Returns None if pandas not available
        """
        if not PANDAS_AVAILABLE:
            logger.error("pandas is required for training data generation")
            return None

        # Get equipment IDs
        equipment_ids = self._get_equipment_ids(equipment_type)
        if not equipment_ids:
            logger.warning(f"No equipment found for type: {equipment_type}")
            return None

        logger.info(
            f"Generating training data for {len(equipment_ids)} {equipment_type} "
            f"from {start_date.date()} to {end_date.date()}"
        )

        rows = []
        current_date = start_date

        while current_date <= end_date:
            for equipment_id in equipment_ids:
                # Compute features as of current_date
                features = self._feature_service.compute_features(
                    equipment_id=equipment_id,
                    equipment_type=equipment_type,
                    as_of=current_date,
                )

                row = {
                    "equipment_id": equipment_id,
                    "timestamp": current_date,
                    **features.features,
                }
                rows.append(row)

            current_date += timedelta(days=sample_interval_days)

        df = pd.DataFrame(rows)
        logger.info(f"Generated {len(df)} training samples")
        return df

    def add_labels(
        self,
        df: "pd.DataFrame",
        label_source: str = "work_orders",
        lookahead_days: int = 30,
    ) -> "pd.DataFrame":
        """Add failure labels to training data.

        Adds binary label indicating whether equipment failed
        within lookahead_days of the sample timestamp.

        Args:
            df: DataFrame with equipment_id and timestamp columns
            label_source: Source for labels (work_orders)
            lookahead_days: Days ahead to look for failures

        Returns:
            DataFrame with added label column
        """
        if not PANDAS_AVAILABLE:
            return df

        # Load work orders
        work_orders_path = Path(__file__).parent.parent / "data" / "work_orders.json"
        work_orders = []

        if work_orders_path.exists():
            try:
                with open(work_orders_path) as f:
                    work_orders = json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load work orders: {e}")

        # Build failure lookup: equipment_id -> list of failure dates
        failures: dict[str, list[datetime]] = {}
        failure_keywords = ["failure", "breakdown", "emergency", "critical", "repair"]

        for wo in work_orders:
            equipment_id = wo.get("equipment_id") or wo.get("asset_id")
            if not equipment_id:
                continue

            # Check if work order indicates a failure
            description = (wo.get("description", "") + " " + wo.get("type", "")).lower()
            is_failure = any(kw in description for kw in failure_keywords)

            if is_failure:
                # Parse date
                date_str = wo.get("created_at") or wo.get("date")
                if date_str:
                    try:
                        if isinstance(date_str, str):
                            failure_date = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                        else:
                            failure_date = date_str
                        if equipment_id not in failures:
                            failures[equipment_id] = []
                        failures[equipment_id].append(failure_date)
                    except Exception:
                        pass

        # Add label column
        label_col = f"failure_{lookahead_days}d"

        def check_failure(row):
            equipment_id = row["equipment_id"]
            timestamp = row["timestamp"]
            if equipment_id not in failures:
                return 0

            for failure_date in failures[equipment_id]:
                days_until = (failure_date - timestamp).days
                if 0 <= days_until <= lookahead_days:
                    return 1
            return 0

        df[label_col] = df.apply(check_failure, axis=1)

        positive_count = df[label_col].sum()
        logger.info(f"Added labels: {positive_count} positive samples ({100 * positive_count / len(df):.1f}%)")

        return df

    def save_dataset(
        self,
        df: "pd.DataFrame",
        name: str,
        version: str,
        equipment_type: str,
        start_date: datetime,
        end_date: datetime,
        sample_interval_days: int,
        label_column: str | None = None,
    ) -> TrainingDatasetMetadata:
        """Save training dataset to parquet file.

        Args:
            df: DataFrame to save
            name: Dataset name
            version: Dataset version (e.g., v1, v2)
            equipment_type: Equipment type
            start_date: Data start date
            end_date: Data end date
            sample_interval_days: Sampling interval
            label_column: Name of label column if present

        Returns:
            TrainingDatasetMetadata for the saved dataset
        """
        if not PANDAS_AVAILABLE:
            raise RuntimeError("pandas is required to save datasets")

        # Generate filename
        filename = f"{name}_{version}.parquet"
        file_path = self._data_dir / filename

        # Save to parquet
        df.to_parquet(file_path, index=False)
        file_size = file_path.stat().st_size

        # Get feature names (exclude equipment_id, timestamp, label columns)
        exclude_cols = {"equipment_id", "timestamp"}
        if label_column:
            exclude_cols.add(label_column)
        feature_names = [c for c in df.columns if c not in exclude_cols]

        # Count positive labels
        label_positive_count = None
        if label_column and label_column in df.columns:
            label_positive_count = int(df[label_column].sum())

        # Create metadata
        metadata = TrainingDatasetMetadata(
            name=name,
            version=version,
            equipment_type=equipment_type,
            created_at=datetime.utcnow(),
            start_date=start_date,
            end_date=end_date,
            sample_interval_days=sample_interval_days,
            row_count=len(df),
            equipment_count=df["equipment_id"].nunique(),
            feature_count=len(feature_names),
            feature_names=feature_names,
            label_column=label_column,
            label_positive_count=label_positive_count,
            file_path=str(file_path),
            file_size_bytes=file_size,
        )

        # Save to registry
        registry_key = f"{name}_{version}"
        self._registry[registry_key] = metadata
        self._save_registry()

        logger.info(
            f"Saved dataset {registry_key}: {len(df)} rows, {len(feature_names)} features, {file_size / 1024:.1f} KB"
        )

        return metadata

    def list_datasets(self) -> list[TrainingDatasetMetadata]:
        """List all available training datasets.

        Returns:
            List of TrainingDatasetMetadata objects
        """
        return list(self._registry.values())

    def get_dataset(self, name: str, version: str) -> TrainingDatasetMetadata | None:
        """Get metadata for a specific dataset.

        Args:
            name: Dataset name
            version: Dataset version

        Returns:
            TrainingDatasetMetadata or None if not found
        """
        key = f"{name}_{version}"
        return self._registry.get(key)

    def load_dataset(self, name: str, version: str) -> Optional["pd.DataFrame"]:
        """Load a dataset from parquet file.

        Args:
            name: Dataset name
            version: Dataset version

        Returns:
            pandas DataFrame or None if not found
        """
        if not PANDAS_AVAILABLE:
            logger.error("pandas is required to load datasets")
            return None

        metadata = self.get_dataset(name, version)
        if not metadata:
            logger.warning(f"Dataset not found: {name}_{version}")
            return None

        if not Path(metadata.file_path).exists():
            logger.warning(f"Dataset file not found: {metadata.file_path}")
            return None

        return pd.read_parquet(metadata.file_path)

    def delete_dataset(self, name: str, version: str) -> bool:
        """Delete a dataset and its file.

        Args:
            name: Dataset name
            version: Dataset version

        Returns:
            True if deleted, False if not found
        """
        key = f"{name}_{version}"
        if key not in self._registry:
            return False

        metadata = self._registry[key]

        # Delete file
        file_path = Path(metadata.file_path)
        if file_path.exists():
            file_path.unlink()

        # Remove from registry
        del self._registry[key]
        self._save_registry()

        logger.info(f"Deleted dataset: {key}")
        return True


def get_training_data_service() -> TrainingDataService:
    """Get singleton training data service instance.

    Returns:
        TrainingDataService instance
    """
    global _training_data_service

    if _training_data_service is None:
        _training_data_service = TrainingDataService()

    return _training_data_service
