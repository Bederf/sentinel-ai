"""
Survival Model - Cox Proportional Hazards for equipment failure prediction.

Implements:
- Cox PH model training with lifelines
- Hazard ratio calculation
- Survival probability prediction at 30/60/90 days
- Remaining useful life estimation
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    import pandas as pd

logger = logging.getLogger(__name__)


class SurvivalModel:
    """Cox Proportional Hazards model for failure prediction."""

    def __init__(self, penalizer: float = 0.1):
        """
        Initialize Cox PH model.

        Args:
            penalizer: L2 regularization strength
        """
        try:
            from lifelines import CoxPHFitter
        except ImportError:
            raise ImportError("lifelines is required. Install with: pip install lifelines")

        self.model = CoxPHFitter(penalizer=penalizer)
        self.feature_cols = None
        self.baseline_survival = None
        self._is_fitted = False

    def train(self, data, duration_col: str = "duration", event_col: str = "event") -> dict:
        """
        Train Cox PH model.

        Args:
            data: DataFrame with duration, event, and feature columns
            duration_col: Column name for time-to-event
            event_col: Column name for event indicator (1=failure, 0=censored)

        Returns:
            Training metrics including c-index
        """
        # Exclude ID column and identify features
        exclude_cols = ["equipment_id", "equipment_type", duration_col, event_col]
        self.feature_cols = [c for c in data.columns if c not in exclude_cols]

        # Prepare training data
        training_data = data[[duration_col, event_col, *self.feature_cols]].copy()

        # Check for constant columns
        constant_cols = training_data[self.feature_cols].nunique()
        constant_cols = constant_cols[constant_cols == 1].index.tolist()
        if constant_cols:
            logger.warning(f"Removing constant columns: {constant_cols}")
            self.feature_cols = [c for c in self.feature_cols if c not in constant_cols]
            training_data = training_data[[duration_col, event_col, *self.feature_cols]]

        # Check minimum samples
        if len(training_data) < 10:
            raise ValueError(f"Insufficient data: {len(training_data)} samples (need at least 10)")

        # Check for events
        if training_data[event_col].sum() < 2:
            raise ValueError(f"Insufficient events: {training_data[event_col].sum()} (need at least 2)")

        # Fit model
        logger.info(f"Training Cox PH model with {len(training_data)} samples, {len(self.feature_cols)} features")
        self.model.fit(training_data, duration_col=duration_col, event_col=event_col, show_progress=False)

        # Store baseline survival function
        self.baseline_survival = self.model.baseline_survival_
        self._is_fitted = True

        # Calculate metrics
        try:
            from lifelines.utils import concordance_index

            predictions = self.model.predict_partial_hazard(training_data)
            c_index = concordance_index(
                training_data[duration_col],
                -predictions,  # Negative for hazard ranking
                training_data[event_col],
            )
        except Exception as e:
            logger.warning(f"Could not calculate c-index: {e}")
            c_index = 0.5  # Random baseline

        return {
            "c_index": float(c_index),
            "n_samples": len(training_data),
            "n_events": int(training_data[event_col].sum()),
            "n_features": len(self.feature_cols),
            "summary": self.model.summary.to_dict(),
        }

    def get_hazard_ratios(self) -> pd.DataFrame:
        """
        Get hazard ratios for all features.

        Returns:
            DataFrame with feature, hazard_ratio, p_value, ci_lower, ci_upper
        """
        if not self._is_fitted:
            raise ValueError("Model must be trained before getting hazard ratios")

        try:
            import pandas as pd
        except ImportError:
            raise ImportError("pandas is required")

        summary = self.model.summary

        # Handle different column name formats in lifelines versions
        ci_lower_col = None
        ci_upper_col = None
        for col in summary.columns:
            if "lower" in col.lower() and "95" in col:
                ci_lower_col = col
            if "upper" in col.lower() and "95" in col:
                ci_upper_col = col

        # Extract confidence intervals
        ci_lower_vals = summary[ci_lower_col].values if ci_lower_col else None
        ci_upper_vals = summary[ci_upper_col].values if ci_upper_col else None

        hazard_ratios = pd.DataFrame(
            {
                "feature": self.feature_cols,
                "hazard_ratio": np.exp(self.model.params_.values),
                "coef": self.model.params_.values,
                "p_value": summary["p"].values,
                "ci_lower": np.exp(ci_lower_vals) if ci_lower_vals is not None else None,
                "ci_upper": np.exp(ci_upper_vals) if ci_upper_vals is not None else None,
            }
        ).sort_values("hazard_ratio", ascending=False)

        return hazard_ratios

    def predict_survival_probability(self, features, times: list[int] | None = None) -> pd.DataFrame:
        """
        Predict survival probability at specific times.

        Args:
            features: DataFrame of equipment features
            times: List of time points in days (default: [30, 60, 90])

        Returns:
            DataFrame with survival_Xd and failure_prob_Xd columns
        """
        if not self._is_fitted:
            raise ValueError("Model must be trained before prediction")

        if times is None:
            times = [30, 60, 90]

        # Predict survival function
        survival_funcs = self.model.predict_survival_function(features)

        # Find closest available time points
        try:
            import pandas as pd
        except ImportError:
            raise ImportError("pandas is required")

        results = pd.DataFrame()
        for t in times:
            # Find closest available time point
            if t in survival_funcs.index:
                results[f"survival_{t}d"] = survival_funcs.loc[t]
            else:
                # Find closest - use Series for abs operation
                time_diffs = pd.Series(survival_funcs.index).sub(t).abs()
                closest_time = survival_funcs.index[time_diffs.idxmin()]
                results[f"survival_{t}d"] = survival_funcs.loc[closest_time]

        # Failure probability = 1 - survival
        for t in times:
            results[f"failure_prob_{t}d"] = 1 - results[f"survival_{t}d"]

        return results

    def predict_remaining_life(self, features) -> np.ndarray:
        """
        Predict median remaining useful life.

        Args:
            features: DataFrame of equipment features

        Returns:
            Array of RUL values in days
        """
        if not self._is_fitted:
            raise ValueError("Model must be trained before prediction")

        # Get survival function for each equipment
        survival_funcs = self.model.predict_survival_function(features)

        rul = []
        for col in survival_funcs.columns:
            sf = survival_funcs[col]

            # Find time where survival probability drops below 50%
            below_50 = sf[sf < 0.5]
            if len(below_50) > 0:
                median_survival = below_50.index[0]
            else:
                # Still has >50% survival at end of observation
                median_survival = sf.index[-1] * 1.5  # Extrapolate
            rul.append(median_survival)

        return np.array(rul)

    def get_partial_hazard(self, features) -> np.ndarray:
        """
        Get partial hazard (risk score relative to baseline).

        Args:
            features: DataFrame of equipment features

        Returns:
            Array of hazard ratios
        """
        if not self._is_fitted:
            raise ValueError("Model must be trained before prediction")

        return self.model.predict_partial_hazard(features).values

    def save(self, path: str):
        """
        Save model to disk.

        Args:
            path: Path to save model (without extension)
        """
        import joblib

        model_data = {
            "model": self.model,
            "feature_cols": self.feature_cols,
            "baseline_survival": self.baseline_survival,
            "is_fitted": self._is_fitted,
            "saved_at": datetime.now().isoformat(),
        }

        Path(path).parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(model_data, path)
        logger.info(f"Saved survival model to {path}")

    @classmethod
    def load(cls, path: str) -> SurvivalModel:
        """
        Load model from disk.

        Args:
            path: Path to saved model file

        Returns:
            Loaded SurvivalModel instance
        """
        import joblib

        model_data = joblib.load(path)

        instance = cls()
        instance.model = model_data["model"]
        instance.feature_cols = model_data["feature_cols"]
        instance.baseline_survival = model_data.get("baseline_survival")
        instance._is_fitted = model_data.get("is_fitted", True)

        logger.info(f"Loaded survival model from {path}")
        return instance
