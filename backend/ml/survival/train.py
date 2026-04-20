"""
Survival Model Training Pipeline - Train and register Cox PH models.

Provides CLI and programmatic training for survival analysis models.
"""

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class SurvivalTrainer:
    """Training pipeline for survival analysis model."""

    def __init__(self, data_path: str = None):
        """
        Initialize trainer.

        Args:
            data_path: Path to equipment data file
        """
        from .data_prep import SurvivalDataPrep

        self.data_prep = SurvivalDataPrep(data_path)

    def train(self, penalizer: float = 0.1, min_samples: int = 10) -> dict:
        """
        Train universal Cox PH model.

        Args:
            penalizer: L2 regularization strength
            min_samples: Minimum samples required for training

        Returns:
            Training results with metrics
        """
        # Prepare data
        logger.info("Preparing survival dataset...")
        df = self.data_prep.prepare_survival_data()

        if len(df) < min_samples:
            raise ValueError(f"Insufficient data: {len(df)} equipment (need {min_samples}+)")

        n_events = df["event"].sum()
        if n_events < 2:
            raise ValueError(f"Insufficient failure events: {n_events} (need at least 2)")

        logger.info(f"Dataset: {len(df)} samples, {n_events} events")

        # Train model
        from .model import SurvivalModel

        logger.info("Training Cox PH model...")
        model = SurvivalModel(penalizer=penalizer)
        metrics = model.train(df)

        logger.info(f"C-index: {metrics['c_index']:.3f}")

        # Get hazard ratios
        hazard_ratios = model.get_hazard_ratios()

        # Save model
        models_dir = Path(__file__).parent.parent / "models" / "survival"
        models_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        model_path = models_dir / f"cox_ph_{timestamp}.joblib"
        model.save(str(model_path))

        # Register model
        from ml.registry import ModelRegistry

        registry = ModelRegistry()
        model_id = registry.register_model(
            "survival",
            "universal",
            str(model_path),
            {
                "c_index": float(metrics["c_index"]),
                "n_samples": metrics["n_samples"],
                "n_events": metrics["n_events"],
                "n_features": metrics["n_features"],
            },
            metadata={
                "penalizer": penalizer,
                "feature_cols": model.feature_cols,
                "trained_at": datetime.now().isoformat(),
            },
        )

        logger.info(f"Registered model: {model_id}")

        return {
            "model_id": model_id,
            "c_index": float(metrics["c_index"]),
            "n_samples": metrics["n_samples"],
            "n_events": metrics["n_events"],
            "n_features": metrics["n_features"],
            "hazard_ratios": hazard_ratios.to_dict("records"),
            "model_path": str(model_path),
        }

    def cross_validate(self, n_folds: int = 5) -> dict:
        """
        Perform k-fold cross-validation.

        Args:
            n_folds: Number of cross-validation folds

        Returns:
            CV results with mean c-index and std
        """
        from sklearn.model_selection import KFold

        from .model import SurvivalModel

        df = self.data_prep.prepare_survival_data()

        if len(df) < n_folds * 2:
            raise ValueError(f"Insufficient data for CV: {len(df)} samples (need at least {n_folds * 2})")

        c_indexes = []

        kf = KFold(n_splits=n_folds, shuffle=True, random_state=42)

        for fold, (train_idx, test_idx) in enumerate(kf.split(df)):
            logger.info(f"Training fold {fold + 1}/{n_folds}...")

            train_df = df.iloc[train_idx]
            test_df = df.iloc[test_idx]

            model = SurvivalModel(penalizer=0.1)
            model.train(train_df)

            # Evaluate on test set
            from lifelines.utils import concordance_index

            predictions = model.model.predict_partial_hazard(test_df)
            c_index = concordance_index(test_df["duration"], -predictions, test_df["event"])

            c_indexes.append(c_index)
            logger.info(f"Fold {fold + 1} C-index: {c_index:.3f}")

        return {
            "mean_c_index": float(np.mean(c_indexes)),
            "std_c_index": float(np.std(c_indexes)),
            "fold_c_indexes": [float(c) for c in c_indexes],
            "n_folds": n_folds,
        }


def main():
    """CLI entry point for training."""
    parser = argparse.ArgumentParser(description="Train survival analysis models")
    parser.add_argument("--penalizer", type=float, default=0.1, help="L2 regularization strength (default: 0.1)")
    parser.add_argument("--min-samples", type=int, default=10, help="Minimum samples required (default: 10)")
    parser.add_argument("--cross-validate", action="store_true", help="Perform k-fold cross-validation")
    parser.add_argument("--folds", type=int, default=5, help="Number of CV folds (default: 5)")
    parser.add_argument("--output", type=str, help="Output JSON file for results")

    args = parser.parse_args()

    trainer = SurvivalTrainer()

    if args.cross_validate:
        logger.info("Running cross-validation...")
        results = trainer.cross_validate(n_folds=args.folds)
    else:
        logger.info("Training survival model...")
        results = trainer.train(penalizer=args.penalizer, min_samples=args.min_samples)

    # Print results
    print(json.dumps(results, indent=2))

    # Save to file if specified
    if args.output:
        Path(args.output).write_text(json.dumps(results, indent=2))
        logger.info(f"Results saved to {args.output}")


if __name__ == "__main__":
    main()
