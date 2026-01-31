"""
LSTM Model - Time-series forecasting for equipment sensors.

Architecture: 3-layer LSTM (128-64-32) with dropout and batch normalization.
Predicts sensor values at 24h, 48h, and 72h horizons.
"""

import logging
from typing import Tuple, List, Optional, Dict, Any
import numpy as np

logger = logging.getLogger(__name__)

# Lazy import TensorFlow to avoid slow startup
_tf = None
_keras = None


def _get_tf():
    """Lazy load TensorFlow."""
    global _tf, _keras
    if _tf is None:
        import tensorflow as tf
        _tf = tf
        _keras = tf.keras

        # Suppress TF warnings
        tf.get_logger().setLevel("ERROR")

    return _tf, _keras


class SensorLSTM:
    """LSTM model for sensor time-series forecasting."""

    def __init__(
        self,
        window_size: int = 168,
        n_features: int = 1,
        n_outputs: int = 3,
        lstm_units: Tuple[int, int, int] = (128, 64, 32),
        dropout_rate: float = 0.2,
        learning_rate: float = 0.001
    ):
        """
        Initialize LSTM model.

        Args:
            window_size: Number of input timesteps (default 168 = 7 days hourly)
            n_features: Number of input features
            n_outputs: Number of forecast horizons (default 3 = 24h, 48h, 72h)
            lstm_units: Units per LSTM layer (default 128-64-32)
            dropout_rate: Dropout rate between layers
            learning_rate: Adam optimizer learning rate
        """
        self.window_size = window_size
        self.n_features = n_features
        self.n_outputs = n_outputs
        self.lstm_units = lstm_units
        self.dropout_rate = dropout_rate
        self.learning_rate = learning_rate
        self.model = None
        self.history = None

    def build(self):
        """Build the LSTM model architecture."""
        tf, keras = _get_tf()

        model = keras.Sequential([
            # Input layer
            keras.layers.InputLayer(input_shape=(self.window_size, self.n_features)),

            # First LSTM layer - return sequences for stacking
            keras.layers.LSTM(
                self.lstm_units[0],
                return_sequences=True,
                kernel_regularizer=keras.regularizers.l2(0.001)
            ),
            keras.layers.BatchNormalization(),
            keras.layers.Dropout(self.dropout_rate),

            # Second LSTM layer
            keras.layers.LSTM(
                self.lstm_units[1],
                return_sequences=True,
                kernel_regularizer=keras.regularizers.l2(0.001)
            ),
            keras.layers.BatchNormalization(),
            keras.layers.Dropout(self.dropout_rate),

            # Third LSTM layer - return final state only
            keras.layers.LSTM(
                self.lstm_units[2],
                return_sequences=False,
                kernel_regularizer=keras.regularizers.l2(0.001)
            ),
            keras.layers.BatchNormalization(),
            keras.layers.Dropout(self.dropout_rate),

            # Dense layers
            keras.layers.Dense(32, activation="relu"),
            keras.layers.Dropout(self.dropout_rate / 2),

            # Output layer: predict values at each horizon
            keras.layers.Dense(self.n_outputs)
        ])

        model.compile(
            optimizer=keras.optimizers.Adam(learning_rate=self.learning_rate),
            loss="mse",
            metrics=["mae"]
        )

        self.model = model
        logger.info(f"Built LSTM model: {self.lstm_units} units, {self.n_features} features")

        return self

    def train(
        self,
        X_train: np.ndarray,
        y_train: np.ndarray,
        X_val: np.ndarray = None,
        y_val: np.ndarray = None,
        epochs: int = 100,
        batch_size: int = 32,
        patience: int = 10,
        verbose: int = 1
    ) -> Dict[str, Any]:
        """
        Train the LSTM model.

        Args:
            X_train: Training input of shape (samples, window_size, features)
            y_train: Training targets of shape (samples, n_outputs)
            X_val: Validation input (optional)
            y_val: Validation targets (optional)
            epochs: Maximum training epochs
            batch_size: Batch size
            patience: Early stopping patience
            verbose: Verbosity level (0=silent, 1=progress, 2=detailed)

        Returns:
            Training history dictionary
        """
        if self.model is None:
            self.build()

        tf, keras = _get_tf()

        callbacks = [
            keras.callbacks.EarlyStopping(
                monitor="val_loss" if X_val is not None else "loss",
                patience=patience,
                restore_best_weights=True,
                verbose=verbose
            ),
            keras.callbacks.ReduceLROnPlateau(
                monitor="val_loss" if X_val is not None else "loss",
                factor=0.5,
                patience=patience // 2,
                min_lr=1e-6,
                verbose=verbose
            )
        ]

        validation_data = (X_val, y_val) if X_val is not None else None

        history = self.model.fit(
            X_train, y_train,
            validation_data=validation_data,
            epochs=epochs,
            batch_size=batch_size,
            callbacks=callbacks,
            verbose=verbose
        )

        self.history = history.history

        # Log final metrics
        final_loss = history.history["loss"][-1]
        final_mae = history.history["mae"][-1]
        logger.info(
            f"Training complete: loss={final_loss:.4f}, mae={final_mae:.4f}, "
            f"epochs={len(history.history['loss'])}"
        )

        return self.history

    def predict(self, X: np.ndarray) -> np.ndarray:
        """
        Make predictions.

        Args:
            X: Input of shape (samples, window_size, features)

        Returns:
            Predictions of shape (samples, n_outputs)
        """
        if self.model is None:
            raise ValueError("Model not built or loaded")

        return self.model.predict(X, verbose=0)

    def evaluate(
        self,
        X_test: np.ndarray,
        y_test: np.ndarray
    ) -> Dict[str, float]:
        """
        Evaluate model on test data.

        Returns:
            Dictionary with loss and MAE metrics
        """
        if self.model is None:
            raise ValueError("Model not built or loaded")

        loss, mae = self.model.evaluate(X_test, y_test, verbose=0)
        return {"loss": loss, "mae": mae}

    def save(self, path: str):
        """Save model to disk."""
        if self.model is None:
            raise ValueError("No model to save")

        self.model.save(path)
        logger.info(f"Saved LSTM model to {path}")

    @classmethod
    def load(cls, path: str) -> "SensorLSTM":
        """Load model from disk."""
        tf, keras = _get_tf()

        instance = cls.__new__(cls)
        instance.model = keras.models.load_model(path)

        # Infer parameters from loaded model
        input_shape = instance.model.input_shape
        instance.window_size = input_shape[1]
        instance.n_features = input_shape[2]
        instance.n_outputs = instance.model.output_shape[1]

        logger.info(f"Loaded LSTM model from {path}")
        return instance

    def summary(self) -> str:
        """Get model summary as string."""
        if self.model is None:
            return "Model not built"

        import io
        stream = io.StringIO()
        self.model.summary(print_fn=lambda x: stream.write(x + "\n"))
        return stream.getvalue()

    def get_config(self) -> Dict[str, Any]:
        """Get model configuration."""
        return {
            "window_size": self.window_size,
            "n_features": self.n_features,
            "n_outputs": self.n_outputs,
            "lstm_units": self.lstm_units,
            "dropout_rate": self.dropout_rate,
            "learning_rate": self.learning_rate
        }
