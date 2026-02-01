"""Feature Computation Service for ML Training.

This service computes features from InfluxDB sensor data for ML training.
Features are defined in feature_definitions.json and include:
- Common features (applicable to all equipment types)
- Equipment-specific features (chiller, AHU, generator)

The service supports:
- Single equipment feature computation
- Batch computation for multiple equipment
- Trend calculation using linear regression
- Graceful handling of missing data
"""

import json
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any

from app.models.feature import (
    FeatureDefinition,
    FeatureSet,
    ComputedFeatures,
    FeatureBatchResponse,
    FeatureDefinitionsResponse,
)
from app.services.influxdb_service import get_influxdb_service, SensorReading

logger = logging.getLogger(__name__)

# Singleton instance
_feature_service: Optional["FeatureComputeService"] = None


class FeatureComputeService:
    """Service for computing ML features from sensor data.

    Features are computed from InfluxDB time-series data using
    various aggregation methods (mean, std, min, max, trend).
    """

    def __init__(self, definitions_path: Optional[str] = None):
        """Initialize the feature service.

        Args:
            definitions_path: Path to feature_definitions.json.
                            Defaults to backend/app/data/feature_definitions.json
        """
        if definitions_path is None:
            definitions_path = Path(__file__).parent.parent / "data" / "feature_definitions.json"
        else:
            definitions_path = Path(definitions_path)

        self._definitions_path = definitions_path
        self._definitions: Dict[str, Any] = {}
        self._load_definitions()

        # Get InfluxDB service
        self._influxdb = get_influxdb_service()

    def _load_definitions(self) -> None:
        """Load feature definitions from JSON file."""
        try:
            with open(self._definitions_path, "r") as f:
                self._definitions = json.load(f)
            logger.info(
                f"Loaded feature definitions v{self._definitions.get('version', 'unknown')}"
            )
        except Exception as e:
            logger.error(f"Failed to load feature definitions: {e}")
            self._definitions = {"version": "unknown", "common": [], "chiller": [], "ahu": [], "generator": []}

    def get_definitions(self) -> FeatureDefinitionsResponse:
        """Get all feature definitions.

        Returns:
            FeatureDefinitionsResponse with common and equipment-specific features
        """
        common = [
            FeatureDefinition(**f) for f in self._definitions.get("common", [])
        ]
        equipment_specific = {}
        for eq_type in ["chiller", "ahu", "generator"]:
            if eq_type in self._definitions:
                equipment_specific[eq_type] = [
                    FeatureDefinition(**f) for f in self._definitions[eq_type]
                ]

        return FeatureDefinitionsResponse(
            version=self._definitions.get("version", "unknown"),
            common_features=common,
            equipment_specific=equipment_specific,
        )

    def _get_feature_definitions(self, equipment_type: str) -> List[FeatureDefinition]:
        """Get feature definitions for an equipment type.

        Combines common features with type-specific features.

        Args:
            equipment_type: Equipment type (chiller, ahu, generator)

        Returns:
            List of FeatureDefinition objects
        """
        features = []

        # Add common features
        for f in self._definitions.get("common", []):
            features.append(FeatureDefinition(**f))

        # Add type-specific features
        eq_type_lower = equipment_type.lower()
        if eq_type_lower in self._definitions:
            for f in self._definitions[eq_type_lower]:
                features.append(FeatureDefinition(**f))

        return features

    def compute_features(
        self,
        equipment_id: str,
        equipment_type: str,
        as_of: Optional[datetime] = None,
    ) -> ComputedFeatures:
        """Compute features for a single equipment.

        Args:
            equipment_id: Equipment identifier
            equipment_type: Equipment type (chiller, ahu, generator)
            as_of: Compute features as of this time (default: now)

        Returns:
            ComputedFeatures with feature values and metadata
        """
        start_time = time.time()
        as_of = as_of or datetime.utcnow()

        features: Dict[str, Optional[float]] = {}
        missing_sensors: List[str] = []

        # Get feature definitions for this equipment type
        definitions = self._get_feature_definitions(equipment_type)

        # Group features by window_days to minimize queries
        windows: Dict[int, List[FeatureDefinition]] = {}
        for fd in definitions:
            if fd.window_days not in windows:
                windows[fd.window_days] = []
            windows[fd.window_days].append(fd)

        # Process each time window
        for window_days, window_features in windows.items():
            start_date = as_of - timedelta(days=window_days)

            # Get unique sensor types for this window
            sensor_types = list(set(f.source_sensor for f in window_features))

            # Query sensor data
            sensor_data: Dict[str, List[float]] = {}
            for sensor_type in sensor_types:
                readings = self._influxdb.query_raw(
                    equipment_id=equipment_id,
                    sensor_type=sensor_type,
                    start=start_date,
                    end=as_of,
                )
                if readings:
                    sensor_data[sensor_type] = [r.value for r in readings]
                else:
                    missing_sensors.append(sensor_type)

            # Compute features from sensor data
            for fd in window_features:
                if fd.source_sensor in sensor_data:
                    values = sensor_data[fd.source_sensor]
                    features[fd.name] = self._compute_aggregation(values, fd.aggregation)
                else:
                    features[fd.name] = None

        computation_time_ms = (time.time() - start_time) * 1000

        return ComputedFeatures(
            equipment_id=equipment_id,
            equipment_type=equipment_type,
            timestamp=as_of,
            features=features,
            missing_sensors=list(set(missing_sensors)),
            computation_time_ms=round(computation_time_ms, 2),
        )

    def compute_batch(
        self,
        equipment_ids: List[str],
        equipment_type: str,
        as_of: Optional[datetime] = None,
    ) -> FeatureBatchResponse:
        """Compute features for multiple equipment of the same type.

        Args:
            equipment_ids: List of equipment identifiers
            equipment_type: Equipment type (all must be same type)
            as_of: Compute features as of this time (default: now)

        Returns:
            FeatureBatchResponse with results for all equipment
        """
        start_time = time.time()
        as_of = as_of or datetime.utcnow()

        results = []
        for equipment_id in equipment_ids:
            result = self.compute_features(
                equipment_id=equipment_id,
                equipment_type=equipment_type,
                as_of=as_of,
            )
            results.append(result)

        total_time_ms = (time.time() - start_time) * 1000

        return FeatureBatchResponse(
            equipment_type=equipment_type,
            as_of=as_of,
            results=results,
            total_computation_time_ms=round(total_time_ms, 2),
        )

    def _compute_aggregation(
        self, values: List[float], aggregation: str
    ) -> Optional[float]:
        """Compute aggregation for a list of values.

        Args:
            values: List of sensor values
            aggregation: Aggregation method (mean, std, min, max, trend, count_delta)

        Returns:
            Computed value or None if insufficient data
        """
        if not values:
            return None

        if aggregation == "mean":
            return round(sum(values) / len(values), 4)

        elif aggregation == "std":
            if len(values) < 2:
                return 0.0
            mean = sum(values) / len(values)
            variance = sum((x - mean) ** 2 for x in values) / (len(values) - 1)
            return round(variance ** 0.5, 4)

        elif aggregation == "min":
            return round(min(values), 4)

        elif aggregation == "max":
            return round(max(values), 4)

        elif aggregation == "trend":
            return self._compute_trend(values)

        elif aggregation == "count_delta":
            # Difference between last and first value (for counters)
            if len(values) < 2:
                return 0
            return round(values[-1] - values[0], 4)

        else:
            logger.warning(f"Unknown aggregation method: {aggregation}")
            return None

    def _compute_trend(self, values: List[float]) -> Optional[float]:
        """Compute trend using linear regression slope.

        Uses simple linear regression: slope = sum((x-x_mean)(y-y_mean)) / sum((x-x_mean)^2)

        Args:
            values: List of values (assumed evenly spaced in time)

        Returns:
            Slope of trend line (positive = increasing, negative = decreasing)
            Returns None if insufficient data.
        """
        if len(values) < 2:
            return None

        n = len(values)
        # Use indices as x values (0, 1, 2, ...)
        x_mean = (n - 1) / 2
        y_mean = sum(values) / n

        numerator = 0.0
        denominator = 0.0
        for i, y in enumerate(values):
            x_diff = i - x_mean
            numerator += x_diff * (y - y_mean)
            denominator += x_diff * x_diff

        if denominator == 0:
            return 0.0

        slope = numerator / denominator
        return round(slope, 6)

    def get_feature_set(self, equipment_type: str) -> FeatureSet:
        """Get the complete feature set for an equipment type.

        Args:
            equipment_type: Equipment type (chiller, ahu, generator)

        Returns:
            FeatureSet with all applicable features
        """
        definitions = self._get_feature_definitions(equipment_type)
        return FeatureSet(equipment_type=equipment_type, features=definitions)


def get_feature_service() -> FeatureComputeService:
    """Get singleton feature service instance.

    Returns:
        FeatureComputeService instance
    """
    global _feature_service

    if _feature_service is None:
        _feature_service = FeatureComputeService()

    return _feature_service
