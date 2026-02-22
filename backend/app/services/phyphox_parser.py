"""
phyphox CSV/JSON Parser (Phase 41-03)

Parse phyphox experiment exports (CSV/JSON files) to extract sensor data.
Supports acceleration time-series and spectrum data.
Includes FFT computation for time-domain data.

Reference: https://phyphox.org/wiki/
"""

import csv
import io
import json
import logging
from typing import Dict, Any, List, Optional

import numpy as np

logger = logging.getLogger(__name__)


class PhyphoxParser:
    """Parse phyphox experiment exports (CSV/JSON)."""

    def parse_export(self, data: bytes, filename: str) -> Dict[str, Any]:
        """
        Parse phyphox export file.

        Args:
            data: File content bytes
            filename: Original filename (for format detection)

        Returns:
            Parsed sensor data with computed features
        """
        if filename.endswith(".json"):
            return self._parse_json(data)
        elif filename.endswith(".csv"):
            return self._parse_csv(data)
        else:
            # Try to detect format
            try:
                return self._parse_json(data)
            except Exception:
                return self._parse_csv(data)

    def _parse_csv(self, data: bytes) -> Dict[str, Any]:
        """Parse phyphox CSV export."""
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            text = data.decode("latin-1")

        reader = csv.reader(io.StringIO(text))
        rows = list(reader)

        # phyphox CSV format: first row is headers
        headers = rows[0] if rows else []
        data_rows = rows[1:] if len(rows) > 1 else []

        # Detect measurement type from headers
        if any("Acceleration" in h or "acc" in h.lower() for h in headers):
            return self._parse_acceleration_csv(headers, data_rows)
        elif any("Frequency" in h or "freq" in h.lower() for h in headers):
            return self._parse_spectrum_csv(headers, data_rows)
        else:
            return self._parse_generic_csv(headers, data_rows)

    def _parse_acceleration_csv(self, headers: List[str], rows: List[List[str]]) -> Dict[str, Any]:
        """Parse acceleration time-series data."""
        # Find column indices
        time_idx = next((i for i, h in enumerate(headers) if "time" in h.lower()), 0)
        x_idx = next((i for i, h in enumerate(headers) if "x" in h.lower()), 1)
        y_idx = next((i for i, h in enumerate(headers) if "y" in h.lower()), 2)
        z_idx = next((i for i, h in enumerate(headers) if "z" in h.lower()), 3)

        times = []
        acc_x, acc_y, acc_z = [], [], []

        for row in rows:
            try:
                times.append(float(row[time_idx]))
                acc_x.append(float(row[x_idx]))
                acc_y.append(float(row[y_idx]))
                acc_z.append(float(row[z_idx]))
            except (ValueError, IndexError):
                continue

        if not times:
            return {
                "measurement_type": "vibration",
                "source": "csv_export",
                "error": "No valid data rows parsed",
                "confidence": 0.0,
            }

        # Compute features
        acc_x_arr = np.array(acc_x)
        acc_y_arr = np.array(acc_y)
        acc_z_arr = np.array(acc_z)
        acc_total = np.sqrt(acc_x_arr**2 + acc_y_arr**2 + acc_z_arr**2)

        # Compute spectrum via FFT
        if len(times) > 10:
            dt = np.mean(np.diff(times))
            sample_rate = 1.0 / dt if dt > 0 else 500
            spectrum = self._compute_spectrum(acc_total, sample_rate)
        else:
            spectrum = {}

        duration = max(times) - min(times) if times else 0
        sample_rate_calc = 1.0 / np.mean(np.diff(times)) if len(times) > 1 else 0

        return {
            "measurement_type": "vibration",
            "source": "csv_export",
            "duration_s": float(duration),
            "sample_count": len(times),
            "sample_rate_hz": float(sample_rate_calc),
            "rms_x_ms2": float(np.sqrt(np.mean(acc_x_arr**2))),
            "rms_y_ms2": float(np.sqrt(np.mean(acc_y_arr**2))),
            "rms_z_ms2": float(np.sqrt(np.mean(acc_z_arr**2))),
            "rms_total_ms2": float(np.sqrt(np.mean(acc_total**2))),
            "peak_total_ms2": float(np.max(np.abs(acc_total))),
            **spectrum,  # Add spectrum data (peak_frequencies_hz, dominant_frequency_hz, etc.)
            "raw_data": {
                "time": times[:100],  # First 100 samples for preview
                "acc_total": acc_total[:100].tolist(),
            },
            "confidence": 0.9,  # High confidence for CSV data
        }

    def _compute_spectrum(self, signal: np.ndarray, sample_rate: float) -> Dict[str, Any]:
        """Compute frequency spectrum via FFT."""
        n = len(signal)

        # Remove DC component (mean)
        signal_centered = signal - np.mean(signal)

        # Apply Hanning window to reduce spectral leakage
        window = np.hanning(n)
        signal_windowed = signal_centered * window

        # Compute FFT
        fft = np.fft.rfft(signal_windowed)
        freqs = np.fft.rfftfreq(n, 1 / sample_rate)
        magnitudes = np.abs(fft) * 2 / n

        # Find peaks
        peak_indices = self._find_peaks(magnitudes)
        peak_freqs = freqs[peak_indices].tolist()
        peak_amps = magnitudes[peak_indices].tolist()

        # Dominant frequency (skip DC at index 0)
        if len(magnitudes) > 1:
            dominant_idx = np.argmax(magnitudes[1:]) + 1
            dominant_freq = float(freqs[dominant_idx])
            dominant_amp = float(magnitudes[dominant_idx])
        else:
            dominant_freq = 0.0
            dominant_amp = 0.0

        # Determine spectrum shape
        spectrum_shape = self._classify_spectrum_shape(magnitudes, peak_indices)

        return {
            "peak_frequencies_hz": peak_freqs[:10],  # Top 10 peaks
            "peak_amplitudes_ms2": peak_amps[:10],
            "dominant_frequency_hz": dominant_freq,
            "dominant_amplitude_ms2": dominant_amp,
            "frequency_resolution_hz": float(freqs[1] - freqs[0]) if len(freqs) > 1 else 0,
            "spectrum_shape": spectrum_shape,
        }

    def _find_peaks(self, data: np.ndarray, threshold_ratio: float = 0.1) -> np.ndarray:
        """Find peaks in spectrum data."""
        threshold = np.max(data) * threshold_ratio
        peaks = []
        for i in range(1, len(data) - 1):
            if data[i] > data[i - 1] and data[i] > data[i + 1] and data[i] > threshold:
                peaks.append(i)

        # Sort by amplitude (descending) and return indices
        if peaks:
            peaks_sorted = sorted(peaks, key=lambda i: data[i], reverse=True)
            return np.array(peaks_sorted)
        return np.array([])

    def _classify_spectrum_shape(self, magnitudes: np.ndarray, peak_indices: np.ndarray) -> str:
        """Classify the spectrum shape based on peak distribution."""
        if len(peak_indices) == 0:
            return "random"

        # Calculate energy concentration
        if len(magnitudes) > 0:
            total_energy = np.sum(magnitudes**2)
            peak_energy = np.sum(magnitudes[peak_indices] ** 2) if len(peak_indices) > 0 else 0
            concentration = peak_energy / total_energy if total_energy > 0 else 0

            if concentration > 0.8:
                # Most energy in peaks - check for harmonics
                if len(peak_indices) >= 3:
                    return "harmonic"
                else:
                    return "narrowband"
            elif concentration > 0.5:
                return "narrowband"
            else:
                return "broadband"

        return "random"

    def _parse_json(self, data: bytes) -> Dict[str, Any]:
        """Parse phyphox JSON export."""
        content = json.loads(data.decode("utf-8"))

        # phyphox JSON structure varies by experiment
        # Common structure has 'sets' with data arrays
        if "sets" in content:
            return self._parse_phyphox_json_sets(content)

        return {"measurement_type": "unknown", "source": "json_export", "raw_content": content, "confidence": 0.5}

    def _parse_phyphox_json_sets(self, content: Dict) -> Dict[str, Any]:
        """Parse phyphox JSON with sets structure."""
        sets = content.get("sets", [])

        # Look for acceleration data
        for data_set in sets:
            name = data_set.get("name", "").lower()
            if "acc" in name or "linear" in name:
                # Found acceleration data
                data_values = data_set.get("data", [])
                if data_values:
                    # Process similar to CSV
                    return {
                        "measurement_type": "vibration",
                        "source": "json_export",
                        "data_points": len(data_values),
                        "raw_set": data_set,
                        "confidence": 0.7,
                    }

        return {"measurement_type": "unknown", "source": "json_export", "sets_found": len(sets), "confidence": 0.5}

    def _parse_spectrum_csv(self, headers: List[str], rows: List[List[str]]) -> Dict[str, Any]:
        """Parse pre-computed spectrum CSV (frequency vs amplitude)."""
        freq_idx = next((i for i, h in enumerate(headers) if "freq" in h.lower()), 0)
        amp_idx = next((i for i, h in enumerate(headers) if "amp" in h.lower() or "mag" in h.lower()), 1)

        freqs, amps = [], []
        for row in rows:
            try:
                freqs.append(float(row[freq_idx]))
                amps.append(float(row[amp_idx]))
            except (ValueError, IndexError):
                continue

        if not freqs:
            return {
                "measurement_type": "spectrum",
                "source": "csv_export",
                "error": "No valid data rows parsed",
                "confidence": 0.0,
            }

        freqs_arr = np.array(freqs)
        amps_arr = np.array(amps)
        peak_indices = self._find_peaks(amps_arr)

        return {
            "measurement_type": "spectrum",
            "source": "csv_export",
            "peak_frequencies_hz": freqs_arr[peak_indices].tolist()[:10],
            "peak_amplitudes": amps_arr[peak_indices].tolist()[:10],
            "dominant_frequency_hz": float(freqs_arr[np.argmax(amps_arr)]),
            "dominant_amplitude": float(np.max(amps_arr)),
            "frequency_range_hz": {"min": float(freqs_arr.min()), "max": float(freqs_arr.max())},
            "confidence": 0.9,
        }

    def _parse_generic_csv(self, headers: List[str], rows: List[List[str]]) -> Dict[str, Any]:
        """Parse unknown CSV format."""
        return {
            "measurement_type": "unknown",
            "source": "csv_export",
            "headers": headers,
            "row_count": len(rows),
            "sample_data": rows[:5],
            "confidence": 0.3,
        }


# Singleton instance
_parser_instance: Optional[PhyphoxParser] = None


def get_phyphox_parser() -> PhyphoxParser:
    """Get or create the singleton parser instance."""
    global _parser_instance
    if _parser_instance is None:
        _parser_instance = PhyphoxParser()
    return _parser_instance
