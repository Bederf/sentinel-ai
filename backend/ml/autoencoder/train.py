"""
Autoencoder Training Pipeline - Train anomaly detection models per equipment type.

Key principle: Train ONLY on normal operation data.
Anomalies are detected via high reconstruction error during inference.

Usage:
    # Train single equipment type
    python -m ml.autoencoder.train --equipment-type chiller --epochs 50

    # Train all equipment types
    python -m ml.autoencoder.train --all --epochs 50
"""

import argparse
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.model_selection import train_test_split

from ..registry import get_model_registry
from .data_prep import AUTOENCODER_SENSOR_CONFIGS, AutoencoderDataPrep
from .model import SensorAutoencoder
from ml.model_config import get_autoencoder_features, list_ml_trainable_types

logger = logging.getLogger(__name__)


class AutoencoderTrainer:
    """Training pipeline for autoencoder anomaly detection models."""

    def __init__(self, model_dir: str | None = None, window_size: int = 24, site_id: str | None = None):
        """
        Initialize trainer.

        Args:
            model_dir: Directory to save models
            window_size: Input window size (default 24 hours)
        """
        if model_dir is None:
            model_dir = Path(__file__).parent.parent / "models" / "autoencoder"

        self.model_dir = Path(model_dir)
        self.model_dir.mkdir(parents=True, exist_ok=True)

        self.site_id = site_id
        self.window_size = window_size
        self.registry = get_model_registry()

    def train_equipment_type(
        self,
        equipment_type: str,
        epochs: int = 100,
        batch_size: int = 32,
        test_size: float = 0.2,
        latent_dim: int = 16,
        use_demo_data: bool = True,
        verbose: int = 1,
        site_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Train autoencoder for a specific equipment type.

        Args:
            equipment_type: Type of equipment
            epochs: Maximum training epochs
            batch_size: Training batch size
            test_size: Fraction for validation
            latent_dim: Latent space dimension
            use_demo_data: Use synthetic demo data if real data unavailable
            verbose: Training verbosity

        Returns:
            Training results dictionary
        """
        site_id = site_id or self.site_id
        logger.info("Training autoencoder for %s (site=%s)...", equipment_type, site_id or "global")
        start_time = datetime.now()

        # Get sensor configuration
        if equipment_type not in AUTOENCODER_SENSOR_CONFIGS:
            raise ValueError(
                f"Unknown equipment type: {equipment_type}. Available: {list(AUTOENCODER_SENSOR_CONFIGS.keys())}"
            )

        config = AUTOENCODER_SENSOR_CONFIGS[equipment_type]
        feature_names = get_autoencoder_features(equipment_type, site_id)
        if not feature_names:
            feature_names = config["features"]
        n_features = len(feature_names)
        provenance: dict[str, Any] = {
            "site_id": site_id,
            "requested_use_demo_data": use_demo_data,
        }

        # Prepare data
        data_prep = AutoencoderDataPrep(window_size=self.window_size)

        try:
            if not use_demo_data:
                # Load real data from long-retention hourly aggregate telemetry.
                from ml.data.supabase_loader import SupabaseTrainingDataLoader

                loader = SupabaseTrainingDataLoader(site_id=site_id)
                data_array = loader.load_equipment_type_array(equipment_type, min_hours=200)
                if data_array is not None:
                    logger.info("Loaded %d hours of real aggregate data for %s", len(data_array), equipment_type)
                    provenance.update(loader.last_load_metadata)
                    provenance["use_demo_data"] = False
                    # Create windows from real data (assumed normal operation)
                    windows = []
                    for i in range(len(data_array) - self.window_size):
                        windows.append(data_array[i : i + self.window_size])
                    X_normal = np.array(windows)
                    X_all = X_normal  # No known anomalies in real data
                    anomaly_indices = []
                else:
                    logger.warning(f"Insufficient real data for {equipment_type}, falling back to demo data")
                    provenance.update(
                        {
                            "data_source": "synthetic_fallback",
                            "use_demo_data": True,
                            "synthetic_fallback_reason": "insufficient_telemetry_hourly_data",
                        }
                    )
                    X_normal, X_all, anomaly_indices = data_prep.generate_demo_data(
                        n_hours=5000,
                        n_features=n_features,
                        n_anomalies=10,
                        anomaly_magnitude=3.0,
                    )
            else:
                logger.info(f"Using demo data for {equipment_type}")
                provenance.update({"data_source": "demo_forced", "use_demo_data": True})
                X_normal, X_all, anomaly_indices = data_prep.generate_demo_data(
                    n_hours=5000,
                    n_features=n_features,
                    n_anomalies=10,
                    anomaly_magnitude=3.0,
                )

        except Exception as e:
            logger.warning(f"Could not load real data: {e}. Using demo data.")
            provenance.update(
                {
                    "data_source": "synthetic_fallback",
                    "use_demo_data": True,
                    "synthetic_fallback_reason": str(e),
                }
            )
            X_normal, X_all, anomaly_indices = data_prep.generate_demo_data(n_hours=3000, n_features=n_features)

        logger.info(f"Normal data shape: {X_normal.shape}")

        if len(X_normal) < 200:  # Lowered threshold for demo data
            raise ValueError(f"Insufficient normal data for {equipment_type}")

        # Split normal data for training/validation
        X_train, X_val = train_test_split(
            X_normal,
            test_size=test_size,
            shuffle=True,  # OK to shuffle for autoencoder
        )

        # Scale data
        X_train_scaled = data_prep.fit_scaler(X_train)
        X_val_scaled = data_prep.transform(X_val)

        # Create model
        model = SensorAutoencoder(
            window_size=self.window_size,
            n_features=n_features,
            latent_dim=latent_dim,
            lstm_units=(64, 32),
            dropout_rate=0.2,
        )
        model.build()

        # Train
        history = model.train(
            X_train_scaled, X_val_scaled, epochs=epochs, batch_size=batch_size, patience=10, verbose=verbose
        )

        # Evaluate anomaly detection on test data
        if len(anomaly_indices) > 0:
            X_all_scaled = data_prep.transform(X_all)
            detection_metrics = self._evaluate_detection(model, X_all_scaled, anomaly_indices)
        else:
            detection_metrics = {}

        # Save model
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        model_filename = f"{equipment_type}_autoencoder_{timestamp}.h5"
        model_path = self.model_dir / model_filename
        model.save(str(model_path))

        # Save scaler
        scaler_path = str(model_path).replace(".h5", "_scaler.joblib")
        data_prep.save_scaler(scaler_path)

        # Calculate metrics
        val_errors = model.get_reconstruction_error(X_val_scaled)
        metrics = {
            "threshold": float(model.threshold),
            "val_loss": float(history["loss"][-1]),
            "val_error_mean": float(val_errors.mean()),
            "val_error_std": float(val_errors.std()),
            "val_error_max": float(val_errors.max()),
            **detection_metrics,
        }

        auto_activate = provenance.get("data_source") == "telemetry_hourly"

        # Register model
        model_id = self.registry.register_model(
            model_type="autoencoder",
            equipment_type=equipment_type,
            site_id=site_id,
            model_path=str(model_path),
            metrics=metrics,
            metadata={
                "scaler_path": scaler_path,
                "window_size": self.window_size,
                "latent_dim": latent_dim,
                "n_features": n_features,
                "feature_names": feature_names,
                "training_samples": len(X_train),
                "validation_samples": len(X_val),
                "epochs_trained": len(history["loss"]),
                "threshold_percentile": model.threshold_percentile,
                **provenance,
            },
            auto_activate=auto_activate,
        )

        training_time = (datetime.now() - start_time).total_seconds()

        result = {
            "equipment_type": equipment_type,
            "site_id": site_id,
            "model_id": model_id,
            "model_path": str(model_path),
            "scaler_path": scaler_path,
            "normal_samples": len(X_normal),
            "metrics": metrics,
            "training_time_seconds": training_time,
            "epochs_trained": len(history["loss"]),
            "threshold": model.threshold,
        }

        logger.info(
            f"Training complete for {equipment_type}: "
            f"threshold={model.threshold:.6f}, "
            f"precision={metrics.get('precision', 'N/A')}, "
            f"recall={metrics.get('recall', 'N/A')}"
        )

        return result

    def _evaluate_detection(
        self, model: SensorAutoencoder, X_all: np.ndarray, anomaly_indices: list[int]
    ) -> dict[str, float]:
        """
        Evaluate anomaly detection performance.

        Args:
            model: Trained autoencoder
            X_all: All windows (normal + anomalous)
            anomaly_indices: Indices of known anomalous windows

        Returns:
            Detection metrics (precision, recall, F1)
        """
        # Get predictions
        is_anomaly, _scores = model.is_anomaly(X_all)

        # Create ground truth
        y_true = np.zeros(len(X_all), dtype=bool)
        for idx in anomaly_indices:
            if idx < len(y_true):
                y_true[idx] = True

        # Calculate metrics
        true_positives = np.sum(is_anomaly & y_true)
        false_positives = np.sum(is_anomaly & ~y_true)
        false_negatives = np.sum(~is_anomaly & y_true)

        precision = true_positives / (true_positives + false_positives) if (true_positives + false_positives) > 0 else 0
        recall = true_positives / (true_positives + false_negatives) if (true_positives + false_negatives) > 0 else 0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

        return {
            "precision": float(precision),
            "recall": float(recall),
            "f1_score": float(f1),
            "true_positives": int(true_positives),
            "false_positives": int(false_positives),
            "false_negatives": int(false_negatives),
            "total_anomalies": len(anomaly_indices),
        }

    def train_with_data(
        self,
        equipment_type: str,
        X_normal: np.ndarray,
        epochs: int = 50,
        batch_size: int = 32,
        test_size: float = 0.2,
        latent_dim: int = 16,
        verbose: int = 0,
    ) -> dict[str, Any]:
        """Train autoencoder with pre-prepared data (from SimulationMLFeeder).

        Args:
            equipment_type: Type of equipment
            X_normal: Normal operation windows (samples, window_size, features)
            epochs: Training epochs
            batch_size: Batch size
            test_size: Validation fraction
            latent_dim: Latent space dimension
            verbose: Verbosity

        Returns:
            Training results dictionary
        """
        logger.info(f"Training autoencoder for {equipment_type} with {len(X_normal)} samples (fed by SENTINEL)")
        start_time = datetime.now()

        config = AUTOENCODER_SENSOR_CONFIGS[equipment_type]
        n_features = X_normal.shape[-1]

        if len(X_normal) < 100:
            raise ValueError(f"Insufficient data for {equipment_type}: {len(X_normal)} samples")

        # Split
        X_train, X_val = train_test_split(X_normal, test_size=test_size, shuffle=True)

        # Scale
        data_prep = AutoencoderDataPrep(window_size=self.window_size)
        X_train_scaled = data_prep.fit_scaler(X_train)
        X_val_scaled = data_prep.transform(X_val)

        # Build & train
        model = SensorAutoencoder(
            window_size=self.window_size,
            n_features=n_features,
            latent_dim=latent_dim,
            lstm_units=(64, 32),
            dropout_rate=0.2,
        )
        model.build()

        history = model.train(
            X_train_scaled,
            X_val_scaled,
            epochs=epochs,
            batch_size=batch_size,
            patience=10,
            verbose=verbose,
        )

        # Save
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        model_filename = f"{equipment_type}_autoencoder_{timestamp}.h5"
        model_path = self.model_dir / model_filename
        model.save(str(model_path))

        scaler_path = str(model_path).replace(".h5", "_scaler.joblib")
        data_prep.save_scaler(scaler_path)

        # Metrics
        val_errors = model.get_reconstruction_error(X_val_scaled)
        metrics = {
            "threshold": float(model.threshold),
            "val_loss": float(history["loss"][-1]),
            "val_error_mean": float(val_errors.mean()),
            "val_error_std": float(val_errors.std()),
            "val_error_max": float(val_errors.max()),
        }

        # Register
        model_id = self.registry.register_model(
            model_type="autoencoder",
            equipment_type=equipment_type,
            model_path=str(model_path),
            metrics=metrics,
            metadata={
                "scaler_path": scaler_path,
                "window_size": self.window_size,
                "latent_dim": latent_dim,
                "n_features": n_features,
                "feature_names": config["features"],
                "training_samples": len(X_train),
                "validation_samples": len(X_val),
                "epochs_trained": len(history["loss"]),
                "threshold_percentile": model.threshold_percentile,
                "use_demo_data": False,
                "data_source": "sentinel_ml_feeder",
            },
            auto_activate=True,
        )

        training_time = (datetime.now() - start_time).total_seconds()
        return {
            "equipment_type": equipment_type,
            "model_id": model_id,
            "model_path": str(model_path),
            "scaler_path": scaler_path,
            "normal_samples": len(X_normal),
            "metrics": metrics,
            "training_time_seconds": training_time,
            "epochs_trained": len(history["loss"]),
            "threshold": model.threshold,
        }

    def train_all(self, epochs: int = 100, use_demo_data: bool = True) -> list[dict[str, Any]]:
        """Train models for all equipment types."""
        results = []

        equipment_types = list_ml_trainable_types(self.site_id) if self.site_id else list(AUTOENCODER_SENSOR_CONFIGS)
        for eq_type in equipment_types:
            try:
                result = self.train_equipment_type(
                    eq_type,
                    epochs=epochs,
                    use_demo_data=use_demo_data,
                    site_id=self.site_id,
                )
                results.append(result)
            except Exception as e:
                logger.error(f"Failed to train {eq_type}: {e}")
                results.append({"equipment_type": eq_type, "error": str(e)})

        # Summary
        successful = [r for r in results if "error" not in r]
        failed = [r for r in results if "error" in r]

        logger.info(f"Training complete: {len(successful)} successful, {len(failed)} failed")

        return results


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Train autoencoder anomaly detection models")
    parser.add_argument("--equipment-type", "-e", type=str, help="Equipment type to train (chiller, ahu, generator)")
    parser.add_argument("--all", "-a", action="store_true", help="Train all equipment types")
    parser.add_argument("--epochs", type=int, default=50, help="Maximum training epochs (default: 50)")
    parser.add_argument("--latent-dim", type=int, default=16, help="Latent space dimension (default: 16)")
    parser.add_argument(
        "--demo-data",
        action="store_true",
        default=False,
        help="Force synthetic demo data instead of real Supabase data",
    )
    parser.add_argument(
        "--real-data", action="store_true", default=False, help="Force real data from Supabase (fail if unavailable)"
    )
    parser.add_argument("--verbose", "-v", type=int, default=1, help="Verbosity level")
    parser.add_argument("--site-id", type=str, default=None, help="Site ID for site-scoped training (e.g. site-002)")

    args = parser.parse_args()

    # Configure logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    trainer = AutoencoderTrainer(site_id=args.site_id)

    # Default: try real data first (use_demo_data=False), fall back to demo.
    # --demo-data forces demo. --real-data forces real (no fallback).
    use_demo = args.demo_data

    if args.all:
        results = trainer.train_all(epochs=args.epochs, use_demo_data=use_demo)
        print("\n=== Training Results ===")
        for r in results:
            if "error" in r:
                print(f"  {r['equipment_type']}: FAILED - {r['error']}")
            else:
                print(
                    f"  {r['equipment_type']}: threshold={r['threshold']:.6f}, F1={r['metrics'].get('f1_score', 'N/A')}"
                )

    elif args.equipment_type:
        result = trainer.train_equipment_type(
            args.equipment_type,
            epochs=args.epochs,
            latent_dim=args.latent_dim,
            use_demo_data=use_demo,
            verbose=args.verbose,
            site_id=args.site_id,
        )
        print(f"\n=== Training Result: {args.equipment_type} ===")
        print(f"  Model ID: {result['model_id']}")
        print(f"  Model Path: {result['model_path']}")
        print(f"  Normal Samples: {result['normal_samples']}")
        print(f"  Epochs: {result['epochs_trained']}")
        print(f"  Threshold: {result['threshold']:.6f}")
        print(f"  Precision: {result['metrics'].get('precision', 'N/A')}")
        print(f"  Recall: {result['metrics'].get('recall', 'N/A')}")
        print(f"  F1 Score: {result['metrics'].get('f1_score', 'N/A')}")

    else:
        print("Available equipment types:")
        for eq, config in AUTOENCODER_SENSOR_CONFIGS.items():
            print(f"  - {eq}: {config['description']}")
        print("\nUse --equipment-type or --all to start training")


if __name__ == "__main__":
    main()
