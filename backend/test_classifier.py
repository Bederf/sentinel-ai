#!/usr/bin/env python
"""Demo script to train a Random Forest failure classifier.

This script trains a chiller failure classifier using synthetic data.
Run this to test the classification functionality.
"""

import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from ml.classifier.train import ClassifierTrainer

def main():
    """Train a demo chiller classifier."""
    print("=" * 60)
    print("Training Random Forest Failure Classifier")
    print("=" * 60)

    trainer = ClassifierTrainer()

    # Train chiller classifier
    print("\n🔧 Training chiller classifier...")
    result = trainer.train_equipment_type(
        "chiller",
        n_estimators=100,
        max_depth=10
    )

    if result["status"] == "success":
        print(f"\n✅ Training successful!")
        print(f"   Accuracy: {result['accuracy']:.3f}")
        print(f"   Classes: {result['n_classes']}")
        print(f"   Samples: {result['n_samples']}")
        print(f"   Model: {result['model_path']}")

        print("\n📊 Top 5 Features:")
        for i, feat in enumerate(result['feature_importance'][:5], 1):
            print(f"   {i}. {feat['feature']}: {feat['importance']:.3f}")

        print("\n🎯 Failure Types:")
        for cls in result['classes']:
            print(f"   - {cls}")

    else:
        print(f"\n❌ Training failed: {result.get('error', 'Unknown error')}")
        return 1

    print("\n" + "=" * 60)
    print("Training complete! Model ready for predictions.")
    print("=" * 60)

    return 0

if __name__ == "__main__":
    sys.exit(main())
