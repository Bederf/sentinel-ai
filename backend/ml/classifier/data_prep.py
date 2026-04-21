"""Classification Data Preparation for Failure Type Prediction.

This module prepares labeled training data for Random Forest classifiers.
It extracts features from time before failure and labels them with failure types.
"""

import logging
from datetime import datetime, timedelta

import pandas as pd

from app.database.repositories.equipment_repository import EquipmentRepository
from app.services.feature_service import FeatureComputeService
from app.services.influxdb_service import get_influxdb_service

logger = logging.getLogger(__name__)


class ClassifierDataPrep:
    """Prepare data for failure type classification.

    Failure types are defined per equipment type and include:
    - Chiller: compressor_failure, refrigerant_leak, condenser_fouling, oil_issue, electrical
    - AHU: fan_motor, belt_failure, coil_fouling, damper_actuator, filter_blockage
    - Generator: battery_failure, fuel_system, starter_motor, alternator, cooling_system
    - FCU: fan_motor, valve_actuator, thermostat, filter_blockage
    - UPS: battery_failure, inverter, capacitor, overload
    """

    # Failure types per equipment
    FAILURE_TYPES = {
        "chiller": ["compressor_failure", "refrigerant_leak", "condenser_fouling", "oil_issue", "electrical"],
        "ahu": ["fan_motor", "belt_failure", "coil_fouling", "damper_actuator", "filter_blockage"],
        "generator": ["battery_failure", "fuel_system", "starter_motor", "alternator", "cooling_system"],
        "fcu": ["fan_motor", "valve_actuator", "thermostat", "filter_blockage"],
        "ups": ["battery_failure", "inverter", "capacitor", "overload"],
    }

    def __init__(self):
        """Initialize the data preparation service."""
        self.feature_service = FeatureComputeService()
        self.influxdb = get_influxdb_service()
        self.equipment_repo = EquipmentRepository()

    def prepare_training_data(self, equipment_type: str) -> tuple[pd.DataFrame, pd.Series]:
        """Prepare features and labels for classification.

        Args:
            equipment_type: Type of equipment (chiller, ahu, generator, etc.)

        Returns:
            Tuple of (X features DataFrame, y labels Series)

        Raises:
            ValueError: If insufficient failure data available
        """
        failure_types = self.FAILURE_TYPES.get(equipment_type, [])

        if not failure_types:
            raise ValueError(f"No failure types defined for equipment type: {equipment_type}")

        # Get equipment of this type (try both lowercase and uppercase)
        equipment_list = self.equipment_repo.get_by_type(equipment_type)
        if not equipment_list:
            equipment_list = self.equipment_repo.get_by_type(equipment_type.upper())

        if not equipment_list:
            # No real equipment found — will use synthetic data
            logger.info(f"No equipment found for {equipment_type}, will use synthetic training data")

        logger.info(f"Found {len(equipment_list)} equipment of type {equipment_type}")

        samples = []

        for eq in equipment_list:
            equipment_id = eq.get("id") if isinstance(eq, dict) else eq.id

            # Get labeled failures for this equipment
            failures = self._get_labeled_failures(equipment_id)

            logger.info(f"Found {len(failures)} labeled failures for {equipment_id}")

            for failure in failures:
                # Get features 7 days before failure
                features = self._get_features_before_failure(equipment_id, failure["occurred_at"], equipment_type)

                if features and failure["failure_type"] in failure_types:
                    sample = {**features, "label": failure["failure_type"]}
                    samples.append(sample)

        if len(samples) < 20:
            # Generate synthetic data for demo if insufficient real data
            logger.warning(f"Insufficient failures for {equipment_type}: {len(samples)}. Generating synthetic data.")
            samples = self._generate_synthetic_data(equipment_type, failure_types)

        df = pd.DataFrame(samples)

        if df.empty:
            raise ValueError(f"No training data available for {equipment_type}")

        X = df.drop("label", axis=1)
        y = df["label"]

        logger.info(f"Prepared {len(X)} samples with {len(y.unique())} classes for {equipment_type}")

        return X, y

    def _get_labeled_failures(self, equipment_id: str) -> list[dict]:
        """Get labeled failures for equipment.

        For MVP, generates synthetic failure data based on work orders.
        In production, this would query actual failure records from CAFM.
        """
        # Try to get from work orders
        failures = []
        try:
            from app.database.repositories.work_order_repository import WorkOrderRepository

            wo_repo = WorkOrderRepository()

            # Get work orders with failure codes
            work_orders = wo_repo.get_by_equipment(equipment_id)

            for wo in work_orders:
                if wo.get("failure_type"):
                    failures.append(
                        {
                            "occurred_at": datetime.fromisoformat(wo.get("created_at", datetime.now().isoformat())),
                            "failure_type": wo["failure_type"],
                        }
                    )
        except Exception as e:
            logger.debug(f"Could not load work orders: {e}. Using synthetic failures.")

        # Generate synthetic failures if none found
        if not failures:
            failures = self._generate_synthetic_failures(equipment_id)

        return failures

    def _generate_synthetic_failures(self, equipment_id: str) -> list[dict]:
        """Generate synthetic failure data for demo purposes.

        Creates 3-5 failures per equipment over the past 90 days.
        """
        failures = []
        base_time = datetime.now()

        # Random failure times in past 90 days
        import random

        num_failures = random.randint(3, 5)

        for _i in range(num_failures):
            days_ago = random.randint(1, 90)
            failure_time = base_time - timedelta(days=days_ago)

            # Determine equipment type from ID
            equipment_type = equipment_id.split("-")[-2] if "-" in equipment_id else "unknown"

            # Select random failure type
            failure_types = self.FAILURE_TYPES.get(equipment_type, ["general_failure"])
            failure_type = random.choice(failure_types)

            failures.append({"occurred_at": failure_time, "failure_type": failure_type})

        return failures

    def _get_features_before_failure(self, equipment_id: str, failure_time: datetime, equipment_type: str) -> dict:
        """Get features 7 days before failure for classification.

        Args:
            equipment_id: Equipment identifier
            failure_time: When the failure occurred
            equipment_type: Type of equipment

        Returns:
            Dictionary of feature values
        """
        # Get features as of 7 days before failure
        observation_time = failure_time - timedelta(days=7)

        try:
            features = self.feature_service.compute_features(
                equipment_id=equipment_id, equipment_type=equipment_type, as_of=observation_time
            )

            # Flatten nested dicts
            flattened = {}
            for key, value in features.items():
                if isinstance(value, dict):
                    for sub_key, sub_value in value.items():
                        flattened[f"{key}_{sub_key}"] = sub_value
                else:
                    flattened[key] = value

            return flattened

        except Exception as e:
            logger.error(f"Failed to get features for {equipment_id}: {e}")
            # Return default features
            return self._get_default_features(equipment_type)

    def _get_default_features(self, equipment_type: str) -> dict:
        """Get default feature values when actual features unavailable.

        Provides reasonable defaults for demo/training when real data missing.
        """
        # Common defaults
        defaults = {
            "age_years": 5.0,
            "criticality_score": 0.5,
            "total_work_orders": 10,
            "avg_temp": 20.0,
            "temp_std": 2.0,
            "temp_trend": 0.0,
            "avg_pressure": 100.0,
            "pressure_std": 10.0,
        }

        # Equipment-specific defaults
        if equipment_type == "chiller":
            defaults.update(
                {
                    "kw_rating": 500,
                    "efficiency_ratio": 3.0,
                    "run_hours": 40000,
                    "start_stop_count": 500,
                }
            )
        elif equipment_type == "ahu":
            defaults.update(
                {
                    "airflow_cfm": 5000,
                    "static_pressure": 2.5,
                    "belt_age_months": 12,
                }
            )
        elif equipment_type == "generator":
            defaults.update(
                {
                    "kva_rating": 500,
                    "fuel_level_percent": 75,
                    "battery_voltage": 13.5,
                    "last_test_days": 30,
                }
            )
        elif equipment_type == "fcu":
            defaults.update(
                {
                    "airflow_cfm": 500,
                    "valve_position": 50,
                    "filter_age_days": 90,
                }
            )
        elif equipment_type == "ups":
            defaults.update(
                {
                    "kva_rating": 10,
                    "battery_age_years": 3,
                    "load_percent": 60,
                    "estimated_runtime_minutes": 30,
                }
            )

        return defaults

    def _generate_synthetic_data(
        self, equipment_type: str, failure_types: list[str], n_samples: int = 100
    ) -> list[dict]:
        """Generate synthetic training data for demo purposes.

        Args:
            equipment_type: Type of equipment
            failure_types: List of possible failure types
            n_samples: Number of samples to generate

        Returns:
            List of feature dictionaries with labels
        """
        import random

        samples = []

        # Common features
        age_range = (1, 20)
        criticality_range = (0, 1)

        # Generate samples for each failure type
        samples_per_type = n_samples // len(failure_types)

        for failure_type in failure_types:
            for _ in range(samples_per_type):
                features = self._get_default_features(equipment_type)

                # Add variation
                features["age_years"] = random.uniform(*age_range)
                features["criticality_score"] = random.uniform(*criticality_range)
                features["total_work_orders"] = random.randint(0, 50)

                # Add feature patterns based on failure type
                if "compressor" in failure_type:
                    features["kw_rating"] *= random.uniform(0.9, 1.1)
                    features["avg_temp"] = random.uniform(22, 28)  # Higher temp
                elif "refrigerant" in failure_type:
                    features["efficiency_ratio"] = random.uniform(2.0, 2.8)  # Lower efficiency
                elif "fan" in failure_type or "motor" in failure_type:
                    features["avg_temp"] = random.uniform(25, 32)  # High temp
                    features["vibration"] = random.uniform(0.5, 1.5)  # High vibration
                elif "filter" in failure_type:
                    features["pressure_std"] = random.uniform(15, 25)  # High pressure variation
                elif "battery" in failure_type:
                    features["battery_voltage"] = random.uniform(11.5, 12.5)  # Low voltage
                    features["battery_age_years"] = random.uniform(3, 6)

                samples.append({**features, "label": failure_type})

        # Add some normal samples (no failure)
        for _ in range(20):
            features = self._get_default_features(equipment_type)
            features["age_years"] = random.uniform(*age_range)
            features["criticality_score"] = random.uniform(*criticality_range)
            features["total_work_orders"] = random.randint(0, 10)
            samples.append({**features, "label": "normal"})

        return samples
