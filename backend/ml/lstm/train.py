"""
LSTM Training Pipeline - Train forecasting models per equipment type.

Usage:
    # Train single equipment type
    python -m ml.lstm.train --equipment-type chiller --epochs 50

    # Train all equipment types
    python -m ml.lstm.train --all --epochs 50
"""

import argparse
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

from ..registry import get_model_registry
from .data_prep import EquipmentDataLoader, LSTMDataPrep
from .model import SensorLSTM

logger = logging.getLogger(__name__)


class LSTMTrainer:
    """Training pipeline for LSTM forecasting models."""

    def __init__(self, model_dir: str = None, window_size: int = 168, forecast_horizons: list[int] = None):
        """
        Initialize trainer.

        Args:
            model_dir: Directory to save models
            window_size: Input window size (default 168 = 7 days hourly)
            forecast_horizons: Hours ahead to predict (default [24, 48, 72])
        """
        if model_dir is None:
            model_dir = Path(__file__).parent.parent / "models" / "lstm"

        self.model_dir = Path(model_dir)
        self.model_dir.mkdir(parents=True, exist_ok=True)

        self.window_size = window_size
        self.forecast_horizons = forecast_horizons or [24, 48, 72]
        self.registry = get_model_registry()

    def train_equipment_type(
        self,
        equipment_type: str,
        epochs: int = 100,
        batch_size: int = 32,
        test_size: float = 0.2,
        use_demo_data: bool = True,
        verbose: int = 1,
    ) -> dict[str, Any]:
        """
        Train LSTM model for a specific equipment type.

        Args:
            equipment_type: Type of equipment (chiller, ahu, generator, etc.)
            epochs: Maximum training epochs
            batch_size: Training batch size
            test_size: Fraction for validation
            use_demo_data: Use synthetic demo data if real data unavailable
            verbose: Training verbosity

        Returns:
            Training results dictionary
        """
        logger.info(f"Training LSTM for {equipment_type}...")
        start_time = datetime.now()

        # Get sensor configuration
        config = EquipmentDataLoader.get_config(equipment_type)
        n_features = len(config["features"])

        # Prepare data
        data_prep = LSTMDataPrep(window_size=self.window_size, forecast_horizons=self.forecast_horizons)

        try:
            if not use_demo_data:
                # Load real data from Supabase equipment_sensor_readings
                from ml.data.supabase_loader import SupabaseTrainingDataLoader

                loader = SupabaseTrainingDataLoader()
                df = loader.load_equipment_type_dataframe(equipment_type, min_hours=500)
                if df is not None:
                    logger.info(f"Loaded {len(df)} hours of real data for {equipment_type}")
                    X, y = data_prep.prepare_from_dataframe(
                        df,
                        feature_cols=config["features"],
                        target_col=config["target"],
                        timestamp_col="timestamp",
                    )
                else:
                    logger.warning(f"Insufficient real data for {equipment_type}, falling back to demo data")
                    X, y = data_prep.generate_demo_data(n_samples=5000, n_features=n_features, noise_level=0.1)
            else:
                logger.info(f"Using demo data for {equipment_type}")
                X, y = data_prep.generate_demo_data(n_samples=5000, n_features=n_features, noise_level=0.1)

        except Exception as e:
            logger.warning(f"Could not load real data: {e}. Using demo data.")
            X, y = data_prep.generate_demo_data(n_samples=5000, n_features=n_features)

        # Verify data shape
        logger.info(f"Data shape: X={X.shape}, y={y.shape}")

        if len(X) < 1000:
            raise ValueError(f"Insufficient data for {equipment_type}: {len(X)} samples")

        # Split data (time-series: no shuffle!)
        split_idx = int(len(X) * (1 - test_size))
        X_train, X_val = X[:split_idx], X[split_idx:]
        y_train, y_val = y[:split_idx], y[split_idx:]

        # Scale data
        X_train_scaled = data_prep.fit_scaler(X_train)
        X_val_scaled = data_prep.transform(X_val)

        # Create model
        model = SensorLSTM(
            window_size=self.window_size,
            n_features=n_features,
            n_outputs=len(self.forecast_horizons),
            lstm_units=(128, 64, 32),
            dropout_rate=0.2,
        )
        model.build()

        # Train
        history = model.train(
            X_train_scaled,
            y_train,
            X_val_scaled,
            y_val,
            epochs=epochs,
            batch_size=batch_size,
            patience=10,
            verbose=verbose,
        )

        # Evaluate
        val_predictions = model.predict(X_val_scaled)
        metrics = self._calculate_metrics(y_val, val_predictions)

        # Save model
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        model_filename = f"{equipment_type}_lstm_{timestamp}.h5"
        model_path = self.model_dir / model_filename
        model.save(str(model_path))

        # Save scaler
        scaler_path = str(model_path).replace(".h5", "_scaler.joblib")
        data_prep.save_scaler(scaler_path)

        # Register model
        model_id = self.registry.register_model(
            model_type="lstm",
            equipment_type=equipment_type,
            model_path=str(model_path),
            metrics=metrics,
            metadata={
                "scaler_path": scaler_path,
                "window_size": self.window_size,
                "forecast_horizons": self.forecast_horizons,
                "n_features": n_features,
                "feature_names": config["features"],
                "target": config["target"],
                "training_samples": len(X_train),
                "validation_samples": len(X_val),
                "epochs_trained": len(history["loss"]),
                "use_demo_data": use_demo_data,
            },
            auto_activate=True,
        )

        training_time = (datetime.now() - start_time).total_seconds()

        result = {
            "equipment_type": equipment_type,
            "model_id": model_id,
            "model_path": str(model_path),
            "scaler_path": scaler_path,
            "samples": len(X),
            "metrics": metrics,
            "training_time_seconds": training_time,
            "epochs_trained": len(history["loss"]),
            "final_loss": history["loss"][-1],
            "final_val_loss": history.get("val_loss", [None])[-1],
        }

        logger.info(
            f"Training complete for {equipment_type}: MAE_24h={metrics['mae_24h']:.4f}, R2_24h={metrics['r2_24h']:.4f}"
        )

        return result

    def _calculate_metrics(self, y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float]:
        """Calculate prediction metrics for each forecast horizon."""
        from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

        metrics = {}
        horizon_names = ["24h", "48h", "72h"]

        for i, name in enumerate(horizon_names[: y_true.shape[1]]):
            metrics[f"mae_{name}"] = float(mean_absolute_error(y_true[:, i], y_pred[:, i]))
            metrics[f"rmse_{name}"] = float(np.sqrt(mean_squared_error(y_true[:, i], y_pred[:, i])))
            metrics[f"r2_{name}"] = float(r2_score(y_true[:, i], y_pred[:, i]))

        # Overall metrics
        metrics["mae_avg"] = float(np.mean([metrics[f"mae_{n}"] for n in horizon_names[: y_true.shape[1]]]))
        metrics["r2_avg"] = float(np.mean([metrics[f"r2_{n}"] for n in horizon_names[: y_true.shape[1]]]))

        return metrics

    def train_with_data(
        self,
        equipment_type: str,
        X: np.ndarray,
        y: np.ndarray,
        epochs: int = 50,
        batch_size: int = 32,
        test_size: float = 0.2,
        verbose: int = 0,
    ) -> dict[str, Any]:
        """Train LSTM model with pre-prepared data (from SimulationMLFeeder).

        Args:
            equipment_type: Type of equipment
            X: Input sequences (samples, window_size, features)
            y: Target values (samples, forecast_horizons)
            epochs: Training epochs
            batch_size: Batch size
            test_size: Validation fraction
            verbose: Verbosity

        Returns:
            Training results dictionary
        """
        logger.info(f"Training LSTM for {equipment_type} with {len(X)} samples (fed by SENTINEL)")
        start_time = datetime.now()

        config = EquipmentDataLoader.get_config(equipment_type)
        n_features = X.shape[-1]

        if len(X) < 100:
            raise ValueError(f"Insufficient data for {equipment_type}: {len(X)} samples")

        # Split (time-series: no shuffle)
        split_idx = int(len(X) * (1 - test_size))
        X_train, X_val = X[:split_idx], X[split_idx:]
        y_train, y_val = y[:split_idx], y[split_idx:]

        # Scale
        data_prep = LSTMDataPrep(window_size=self.window_size, forecast_horizons=self.forecast_horizons)
        X_train_scaled = data_prep.fit_scaler(X_train)
        X_val_scaled = data_prep.transform(X_val)

        # Build & train
        model = SensorLSTM(
            window_size=self.window_size,
            n_features=n_features,
            n_outputs=y.shape[1] if y.ndim > 1 else 1,
            lstm_units=(128, 64, 32),
            dropout_rate=0.2,
        )
        model.build()

        history = model.train(
            X_train_scaled,
            y_train,
            X_val_scaled,
            y_val,
            epochs=epochs,
            batch_size=batch_size,
            patience=10,
            verbose=verbose,
        )

        # Evaluate
        val_predictions = model.predict(X_val_scaled)
        metrics = self._calculate_metrics(y_val, val_predictions)

        # Save
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        model_filename = f"{equipment_type}_lstm_{timestamp}.h5"
        model_path = self.model_dir / model_filename
        model.save(str(model_path))

        scaler_path = str(model_path).replace(".h5", "_scaler.joblib")
        data_prep.save_scaler(scaler_path)

        # Register
        model_id = self.registry.register_model(
            model_type="lstm",
            equipment_type=equipment_type,
            model_path=str(model_path),
            metrics=metrics,
            metadata={
                "scaler_path": scaler_path,
                "window_size": self.window_size,
                "forecast_horizons": self.forecast_horizons,
                "n_features": n_features,
                "feature_names": config["features"],
                "target": config["target"],
                "training_samples": len(X_train),
                "validation_samples": len(X_val),
                "epochs_trained": len(history["loss"]),
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
            "samples": len(X),
            "metrics": metrics,
            "training_time_seconds": training_time,
            "epochs_trained": len(history["loss"]),
            "final_loss": history["loss"][-1],
            "final_val_loss": history.get("val_loss", [None])[-1],
        }

    def train_all(self, epochs: int = 100, use_demo_data: bool = True) -> list[dict[str, Any]]:
        """Train models for all equipment types."""
        results = []

        for eq_type in EquipmentDataLoader.list_equipment_types():
            try:
                result = self.train_equipment_type(eq_type, epochs=epochs, use_demo_data=use_demo_data)
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
    parser = argparse.ArgumentParser(description="Train LSTM forecasting models")
    parser.add_argument(
        "--equipment-type", "-e", type=str, help="Equipment type to train (chiller, ahu, generator, etc.)"
    )
    parser.add_argument("--all", "-a", action="store_true", help="Train all equipment types")
    parser.add_argument("--epochs", type=int, default=50, help="Maximum training epochs (default: 50)")
    parser.add_argument(
        "--demo-data",
        action="store_true",
        default=False,
        help="Force synthetic demo data instead of real Supabase data",
    )
    parser.add_argument(
        "--real-data", action="store_true", default=False, help="Force real data from Supabase (fail if unavailable)"
    )
    parser.add_argument(
        "--verbose", "-v", type=int, default=1, help="Verbosity level (0=silent, 1=progress, 2=detailed)"
    )

    args = parser.parse_args()

    # Configure logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    trainer = LSTMTrainer()

    # Default: try real data first (use_demo_data=False), fall back to demo.
    # --demo-data forces demo. --real-data forces real (no fallback).
    use_demo = args.demo_data  # Explicit demo requested

    if args.all:
        results = trainer.train_all(epochs=args.epochs, use_demo_data=use_demo)
        print("\n=== Training Results ===")
        for r in results:
            if "error" in r:
                print(f"  {r['equipment_type']}: FAILED - {r['error']}")
            else:
                print(f"  {r['equipment_type']}: MAE={r['metrics']['mae_24h']:.4f}, R2={r['metrics']['r2_24h']:.4f}")

    elif args.equipment_type:
        result = trainer.train_equipment_type(
            args.equipment_type, epochs=args.epochs, use_demo_data=use_demo, verbose=args.verbose
        )
        print(f"\n=== Training Result: {args.equipment_type} ===")
        print(f"  Model ID: {result['model_id']}")
        print(f"  Model Path: {result['model_path']}")
        print(f"  Samples: {result['samples']}")
        print(f"  Epochs: {result['epochs_trained']}")
        print(f"  MAE (24h): {result['metrics']['mae_24h']:.4f}")
        print(f"  R2 (24h): {result['metrics']['r2_24h']:.4f}")

    else:
        print("Available equipment types:")
        for eq in EquipmentDataLoader.list_equipment_types():
            config = EquipmentDataLoader.get_config(eq)
            print(f"  - {eq}: {config['description']}")
        print("\nUse --equipment-type or --all to start training")


if __name__ == "__main__":
    main()
