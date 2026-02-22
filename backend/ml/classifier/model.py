"""Random Forest Failure Classification Model.

This module implements a Random Forest classifier for predicting specific
failure types (compressor, bearing, motor, etc.) for equipment.
"""

import logging
from typing import Dict, List

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import LabelEncoder
from sklearn.model_selection import cross_val_score

logger = logging.getLogger(__name__)


class FailureClassifier:
    """Random Forest classifier for failure type prediction.

    Features:
    - Multi-class failure type prediction
    - Feature importance extraction
    - Probability outputs for each failure type
    - Prediction explanation with contributing factors
    """

    def __init__(self, n_estimators: int = 100, max_depth: int = 10):
        """Initialize the classifier.

        Args:
            n_estimators: Number of trees in the forest
            max_depth: Maximum tree depth
        """
        self.model = RandomForestClassifier(
            n_estimators=n_estimators,
            max_depth=max_depth,
            class_weight="balanced",  # Handle imbalanced classes
            random_state=42,
            n_jobs=-1,  # Use all cores
        )
        self.label_encoder = LabelEncoder()
        self.feature_names = None
        self.class_names = None

    def train(self, X: pd.DataFrame, y: pd.Series, cv_folds: int = 5) -> Dict:
        """Train classifier with cross-validation.

        Args:
            X: Feature DataFrame
            y: Label Series
            cv_folds: Number of cross-validation folds

        Returns:
            Training metrics dictionary
        """
        self.feature_names = list(X.columns)

        # Encode labels
        y_encoded = self.label_encoder.fit_transform(y)
        self.class_names = list(self.label_encoder.classes_)

        logger.info(f"Training classifier with {len(X)} samples, {len(self.class_names)} classes")

        # Cross-validation
        cv_scores = cross_val_score(self.model, X, y_encoded, cv=cv_folds, scoring="accuracy", n_jobs=-1)

        logger.info(f"CV Accuracy: {cv_scores.mean():.3f} (+/- {cv_scores.std() * 2:.3f})")

        # Final training on all data
        self.model.fit(X, y_encoded)

        # Get feature importance
        importance = pd.DataFrame(
            {"feature": self.feature_names, "importance": self.model.feature_importances_}
        ).sort_values("importance", ascending=False)

        return {
            "cv_accuracy": float(cv_scores.mean()),
            "cv_std": float(cv_scores.std()),
            "n_samples": len(X),
            "n_classes": len(self.class_names),
            "classes": self.class_names,
            "feature_importance": importance.head(20).to_dict("records"),  # Top 20
        }

    def predict(self, X: pd.DataFrame) -> List[Dict]:
        """Predict failure type with probabilities.

        Args:
            X: Feature DataFrame

        Returns:
            List of prediction dictionaries with probabilities
        """
        if self.model is None:
            raise ValueError("Model not trained yet")

        # Get class probabilities
        proba = self.model.predict_proba(X)

        results = []
        for i, row_proba in enumerate(proba):
            # Create probability dict for each class
            class_proba = {self.class_names[j]: float(p) for j, p in enumerate(row_proba)}

            # Get top prediction
            top_class_idx = np.argmax(row_proba)

            results.append(
                {
                    "predicted_failure": self.class_names[top_class_idx],
                    "confidence": float(row_proba[top_class_idx]),
                    "all_probabilities": class_proba,
                }
            )

        return results

    def get_feature_importance(self, top_n: int = 20) -> pd.DataFrame:
        """Get feature importance ranking.

        Args:
            top_n: Number of top features to return

        Returns:
            DataFrame with feature importance
        """
        if self.model is None:
            raise ValueError("Model not trained yet")

        importance = pd.DataFrame(
            {"feature": self.feature_names, "importance": self.model.feature_importances_}
        ).sort_values("importance", ascending=False)

        return importance.head(top_n)

    def explain_prediction(self, X: pd.DataFrame, prediction_idx: int = 0) -> List[Dict]:
        """Explain a specific prediction using feature contributions.

        Args:
            X: Feature DataFrame
            prediction_idx: Index of prediction to explain

        Returns:
            List of feature contributions sorted by importance
        """
        if self.model is None:
            raise ValueError("Model not trained yet")

        # Get feature values and importance
        feature_values = X.iloc[prediction_idx]

        # Calculate SHAP-like contributions (simplified)
        contributions = []
        for i, (name, value) in enumerate(feature_values.items()):
            if name in self.feature_names:
                _idx = self.feature_names.index(name)
                importance = self.model.feature_importances_[i]

                # Normalize value to 0-1 scale (simplified)
                # In production, use actual SHAP values
                contribution = importance * (value if not pd.isna(value) else 0)

                contributions.append(
                    {
                        "feature": name,
                        "value": float(value if not pd.isna(value) else 0),
                        "importance": float(importance),
                        "contribution": float(contribution),
                    }
                )

        # Sort by absolute contribution
        contributions.sort(key=lambda x: abs(x["contribution"]), reverse=True)

        return contributions[:10]  # Top 10

    def save(self, path: str):
        """Save model to disk.

        Args:
            path: Path to save model
        """
        import joblib

        model_data = {
            "model": self.model,
            "label_encoder": self.label_encoder,
            "feature_names": self.feature_names,
            "class_names": self.class_names,
        }

        joblib.dump(model_data, path)
        logger.info(f"Model saved to {path}")

    @classmethod
    def load(cls, path: str) -> "FailureClassifier":
        """Load model from disk.

        Args:
            path: Path to load model from

        Returns:
            Loaded FailureClassifier instance
        """
        import joblib

        data = joblib.load(path)
        instance = cls()
        instance.model = data["model"]
        instance.label_encoder = data["label_encoder"]
        instance.feature_names = data["feature_names"]
        instance.class_names = data["class_names"]

        logger.info(f"Model loaded from {path}")

        return instance

    def is_trained(self) -> bool:
        """Check if model is trained.

        Returns:
            True if model is trained
        """
        return self.model is not None and self.feature_names is not None
