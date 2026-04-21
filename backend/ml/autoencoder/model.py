"""
Autoencoder Model - Learn normal equipment operation and detect anomalies.

Architecture: LSTM Autoencoder
- Encoder: LSTM(64) → LSTM(32) → Dense(latent_dim)
- Decoder: RepeatVector → LSTM(32) → LSTM(64) → Dense(n_features)

Anomaly detection via reconstruction error:
- Train ONLY on normal data
- High reconstruction error = unusual/anomalous behavior
"""

import logging
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

# Lazy TensorFlow import
_tf = None
_keras = None


def _get_tf():
    """Lazy load TensorFlow."""
    global _tf, _keras
    if _tf is None:
        import tensorflow as tf

        _tf = tf
        _keras = tf.keras
        tf.get_logger().setLevel("ERROR")
    return _tf, _keras


class SensorAutoencoder:
    """LSTM Autoencoder for equipment anomaly detection."""

    def __init__(
        self,
        window_size: int = 24,
        n_features: int = 5,
        latent_dim: int = 16,
        lstm_units: tuple[int, int] = (64, 32),
        dropout_rate: float = 0.2,
    ):
        """
        Initialize autoencoder.

        Args:
            window_size: Input window size (default 24 hours)
            n_features: Number of sensor features
            latent_dim: Size of compressed representation
            lstm_units: Units per LSTM layer (encoder)
            dropout_rate: Dropout rate
        """
        self.window_size = window_size
        self.n_features = n_features
        self.latent_dim = latent_dim
        self.lstm_units = lstm_units
        self.dropout_rate = dropout_rate

        self.model = None
        self.encoder = None
        self.threshold = None
        self.threshold_percentile = 99

    def build(self):
        """Build the LSTM autoencoder architecture."""
        tf, keras = _get_tf()

        # Input
        inputs = keras.layers.Input(shape=(self.window_size, self.n_features))

        # === Encoder ===
        x = keras.layers.LSTM(
            self.lstm_units[0], return_sequences=True, kernel_regularizer=keras.regularizers.l2(0.001)
        )(inputs)
        x = keras.layers.BatchNormalization()(x)
        x = keras.layers.Dropout(self.dropout_rate)(x)

        x = keras.layers.LSTM(
            self.lstm_units[1], return_sequences=False, kernel_regularizer=keras.regularizers.l2(0.001)
        )(x)
        x = keras.layers.BatchNormalization()(x)

        # Latent space representation
        latent = keras.layers.Dense(self.latent_dim, activation="relu", name="latent")(x)

        # === Decoder ===
        x = keras.layers.RepeatVector(self.window_size)(latent)

        x = keras.layers.LSTM(
            self.lstm_units[1], return_sequences=True, kernel_regularizer=keras.regularizers.l2(0.001)
        )(x)
        x = keras.layers.BatchNormalization()(x)
        x = keras.layers.Dropout(self.dropout_rate)(x)

        x = keras.layers.LSTM(
            self.lstm_units[0], return_sequences=True, kernel_regularizer=keras.regularizers.l2(0.001)
        )(x)
        x = keras.layers.BatchNormalization()(x)

        # Output - reconstruct all features for each timestep
        outputs = keras.layers.TimeDistributed(keras.layers.Dense(self.n_features))(x)

        # Full autoencoder model
        self.model = keras.Model(inputs, outputs, name="autoencoder")
        self.model.compile(optimizer=keras.optimizers.Adam(learning_rate=0.001), loss="mse")

        # Encoder-only model (for latent space analysis)
        self.encoder = keras.Model(inputs, latent, name="encoder")

        logger.info(f"Built autoencoder: {self.lstm_units} → latent({self.latent_dim}) → {self.lstm_units[::-1]}")

        return self

    def train(
        self,
        X_train: np.ndarray,
        X_val: np.ndarray = None,
        epochs: int = 100,
        batch_size: int = 32,
        patience: int = 10,
        verbose: int = 1,
    ) -> dict[str, Any]:
        """
        Train autoencoder on NORMAL data only.

        The model learns to reconstruct normal patterns.
        During inference, anomalies will have high reconstruction error.

        Args:
            X_train: Normal operation windows (samples, window_size, features)
            X_val: Validation windows (optional)
            epochs: Maximum training epochs
            batch_size: Batch size
            patience: Early stopping patience
            verbose: Verbosity level

        Returns:
            Training history
        """
        if self.model is None:
            self.build()

        tf, keras = _get_tf()

        callbacks = [
            keras.callbacks.EarlyStopping(
                monitor="val_loss" if X_val is not None else "loss",
                patience=patience,
                restore_best_weights=True,
                verbose=verbose,
            ),
            keras.callbacks.ReduceLROnPlateau(
                monitor="val_loss" if X_val is not None else "loss", factor=0.5, patience=patience // 2, min_lr=1e-6
            ),
        ]

        # Autoencoder: input = output (reconstruct input)
        validation_data = (X_val, X_val) if X_val is not None else None

        history = self.model.fit(
            X_train,
            X_train,  # Reconstruct input
            validation_data=validation_data,
            epochs=epochs,
            batch_size=batch_size,
            callbacks=callbacks,
            verbose=verbose,
        )

        # Calibrate anomaly threshold on training data
        self._calibrate_threshold(X_train)

        logger.info(f"Training complete: loss={history.history['loss'][-1]:.6f}, threshold={self.threshold:.6f}")

        return history.history

    def _calibrate_threshold(self, X_normal: np.ndarray, percentile: float | None = None):
        """
        Calibrate anomaly threshold based on reconstruction errors on normal data.

        The threshold is set at the given percentile of normal reconstruction errors.
        Anything above this threshold during inference is considered anomalous.

        Args:
            X_normal: Normal operation data
            percentile: Percentile for threshold (default 99)
        """
        if percentile is None:
            percentile = self.threshold_percentile

        # Get reconstruction errors for normal data
        errors = self.get_reconstruction_error(X_normal)

        # Set threshold at percentile of normal errors
        self.threshold = float(np.percentile(errors, percentile))

        logger.info(
            f"Calibrated threshold at {percentile}th percentile: {self.threshold:.6f} "
            f"(min={errors.min():.6f}, max={errors.max():.6f}, mean={errors.mean():.6f})"
        )

    def get_reconstruction_error(self, X: np.ndarray) -> np.ndarray:
        """
        Calculate reconstruction error (MSE) for each window.

        Args:
            X: Input windows (samples, window_size, features)

        Returns:
            Array of reconstruction errors (samples,)
        """
        if self.model is None:
            raise ValueError("Model not built or loaded")

        reconstructed = self.model.predict(X, verbose=0)

        # Mean squared error per window
        errors = np.mean(np.square(X - reconstructed), axis=(1, 2))

        return errors

    def get_anomaly_score(self, X: np.ndarray) -> np.ndarray:
        """
        Get anomaly scores (reconstruction errors) for input windows.

        Higher score = more anomalous.

        Returns:
            Anomaly scores (samples,)
        """
        return self.get_reconstruction_error(X)

    def is_anomaly(self, X: np.ndarray, threshold: float | None = None) -> tuple[np.ndarray, np.ndarray]:
        """
        Detect anomalies in input windows.

        Args:
            X: Input windows
            threshold: Custom threshold (default: use calibrated)

        Returns:
            - Boolean array (True = anomaly)
            - Anomaly scores
        """
        if threshold is None:
            threshold = self.threshold

        if threshold is None:
            raise ValueError("Threshold not set. Train model or provide threshold.")

        scores = self.get_anomaly_score(X)
        anomalies = scores > threshold

        return anomalies, scores

    def get_latent_representation(self, X: np.ndarray) -> np.ndarray:
        """
        Get latent space representation for windows.

        Useful for visualization and clustering.

        Returns:
            Latent vectors (samples, latent_dim)
        """
        if self.encoder is None:
            raise ValueError("Model not built")

        return self.encoder.predict(X, verbose=0)

    def save(self, path: str):
        """Save model, encoder, and threshold."""
        if self.model is None:
            raise ValueError("No model to save")

        self.model.save(path)

        # Save threshold
        threshold_path = path.replace(".h5", "_threshold.npy")
        np.save(threshold_path, np.array([self.threshold, self.threshold_percentile]))

        logger.info(f"Saved autoencoder to {path}")

    @classmethod
    def load(cls, path: str) -> "SensorAutoencoder":
        """Load model from disk."""
        tf, keras = _get_tf()

        instance = cls.__new__(cls)
        instance.model = keras.models.load_model(path)

        # Load threshold
        threshold_path = path.replace(".h5", "_threshold.npy")
        try:
            threshold_data = np.load(threshold_path)
            instance.threshold = float(threshold_data[0])
            instance.threshold_percentile = float(threshold_data[1])
        except FileNotFoundError:
            instance.threshold = None
            instance.threshold_percentile = 99
            logger.warning("Threshold file not found, threshold not set")

        # Infer parameters
        input_shape = instance.model.input_shape
        instance.window_size = input_shape[1]
        instance.n_features = input_shape[2]

        # Rebuild encoder from loaded model
        latent_layer = instance.model.get_layer("latent")
        instance.encoder = keras.Model(instance.model.input, latent_layer.output)
        instance.latent_dim = latent_layer.output_shape[-1]

        logger.info(f"Loaded autoencoder from {path}")
        return instance

    def summary(self) -> str:
        """Get model summary as string."""
        if self.model is None:
            return "Model not built"

        import io

        stream = io.StringIO()
        self.model.summary(print_fn=lambda x: stream.write(x + "\n"))
        return stream.getvalue()

    def get_config(self) -> dict[str, Any]:
        """Get model configuration."""
        return {
            "window_size": self.window_size,
            "n_features": self.n_features,
            "latent_dim": self.latent_dim,
            "lstm_units": self.lstm_units,
            "dropout_rate": self.dropout_rate,
            "threshold": self.threshold,
            "threshold_percentile": self.threshold_percentile,
        }
