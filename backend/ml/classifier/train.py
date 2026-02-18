"""Training Pipeline for Failure Classifiers.

This module provides the complete training pipeline for Random Forest
failure type classifiers.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import List

from ml.classifier.data_prep import ClassifierDataPrep
from ml.classifier.model import FailureClassifier
from ml.registry import ModelRegistry

logger = logging.getLogger(__name__)


class ClassifierTrainer:
    """Training pipeline for failure classifiers."""

    def __init__(self, models_dir: str = None):
        """Initialize the trainer.

        Args:
            models_dir: Directory to save trained models
        """
        if models_dir is None:
            models_dir = Path(__file__).parent.parent / "models" / "classifier"
        else:
            models_dir = Path(models_dir)

        self.models_dir = Path(models_dir)
        self.models_dir.mkdir(parents=True, exist_ok=True)

        self.registry = ModelRegistry()

    def train_equipment_type(
        self,
        equipment_type: str,
        n_estimators: int = 100,
        max_depth: int = 10
    ) -> dict:
        """Train classifier for an equipment type.

        Args:
            equipment_type: Type of equipment (chiller, ahu, etc.)
            n_estimators: Number of trees in Random Forest
            max_depth: Maximum tree depth

        Returns:
            Training result dictionary
        """
        logger.info(f"Training classifier for {equipment_type}")

        # Prepare data
        data_prep = ClassifierDataPrep()

        try:
            X, y = data_prep.prepare_training_data(equipment_type)
            logger.info(f"Prepared {len(X)} samples with {len(y.unique())} classes")
        except Exception as e:
            logger.error(f"Failed to prepare data for {equipment_type}: {e}")
            return {
                "equipment_type": equipment_type,
                "error": str(e),
                "status": "failed"
            }

        # Train model
        model = FailureClassifier(n_estimators=n_estimators, max_depth=max_depth)

        try:
            metrics = model.train(X, y)
            logger.info(f"Training complete: CV accuracy {metrics['cv_accuracy']:.3f}")
        except Exception as e:
            logger.error(f"Failed to train model for {equipment_type}: {e}")
            return {
                "equipment_type": equipment_type,
                "error": str(e),
                "status": "failed"
            }

        # Save model
        timestamp = datetime.now().strftime('%Y%m%d')
        model_filename = f"{equipment_type}_rf_{timestamp}.joblib"
        model_path = self.models_dir / model_filename

        try:
            model.save(str(model_path))
            logger.info(f"Model saved to {model_path}")
        except Exception as e:
            logger.error(f"Failed to save model: {e}")
            return {
                "equipment_type": equipment_type,
                "error": f"Save failed: {e}",
                "status": "failed"
            }

        # Register in model registry
        try:
            self.registry.register_model(
                model_type="classifier",
                equipment_type=equipment_type,
                model_path=str(model_path),
                metadata={
                    "accuracy": metrics["cv_accuracy"],
                    "n_classes": metrics["n_classes"],
                    "classes": metrics["classes"],
                    "n_samples": metrics["n_samples"],
                    "n_estimators": n_estimators,
                    "max_depth": max_depth,
                    "trained_at": datetime.now().isoformat()
                }
            )
            logger.info("Model registered in registry")
        except Exception as e:
            logger.warning(f"Failed to register model: {e}")

        return {
            "equipment_type": equipment_type,
            "status": "success",
            "accuracy": metrics["cv_accuracy"],
            "cv_std": metrics["cv_std"],
            "n_samples": metrics["n_samples"],
            "n_classes": metrics["n_classes"],
            "classes": metrics["classes"],
            "model_path": str(model_path),
            "feature_importance": metrics["feature_importance"][:5]  # Top 5
        }

    def train_all(
        self,
        n_estimators: int = 100,
        max_depth: int = 10
    ) -> List[dict]:
        """Train classifiers for all equipment types.

        Args:
            n_estimators: Number of trees in Random Forest
            max_depth: Maximum tree depth

        Returns:
            List of training results for each equipment type
        """
        results = []

        for eq_type in ClassifierDataPrep.FAILURE_TYPES.keys():
            logger.info(f"Training {eq_type} classifier...")
            result = self.train_equipment_type(eq_type, n_estimators, max_depth)
            results.append(result)

        # Summary
        successful = sum(1 for r in results if r.get("status") == "success")
        logger.info(f"Training complete: {successful}/{len(results)} successful")

        return results


def main():
    """CLI entry point for training classifiers."""
    import argparse

    parser = argparse.ArgumentParser(description="Train failure type classifiers")
    parser.add_argument(
        "--equipment-type",
        type=str,
        help="Equipment type to train (chiller, ahu, generator, fcu, ups)"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Train all equipment types"
    )
    parser.add_argument(
        "--n-estimators",
        type=int,
        default=100,
        help="Number of trees in Random Forest (default: 100)"
    )
    parser.add_argument(
        "--max-depth",
        type=int,
        default=10,
        help="Maximum tree depth (default: 10)"
    )

    args = parser.parse_args()

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    trainer = ClassifierTrainer()

    if args.all:
        print("Training all equipment types...")
        results = trainer.train_all(args.n_estimators, args.max_depth)

        print("\n=== Training Summary ===")
        for result in results:
            status = result["status"]
            eq_type = result["equipment_type"]
            if status == "success":
                acc = result["accuracy"]
                print(f"{eq_type}: {acc:.3f} accuracy")
            else:
                print(f"{eq_type}: FAILED - {result.get('error', 'Unknown error')}")

    elif args.equipment_type:
        print(f"Training {args.equipment_type} classifier...")
        result = trainer.train_equipment_type(
            args.equipment_type,
            args.n_estimators,
            args.max_depth
        )

        if result["status"] == "success":
            print("\nTraining successful!")
            print(f"Accuracy: {result['accuracy']:.3f}")
            print(f"Classes: {result['n_classes']}")
            print(f"Samples: {result['n_samples']}")
            print(f"Model: {result['model_path']}")
        else:
            print(f"\nTraining failed: {result.get('error', 'Unknown error')}")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
