"""
Bearing Defect Analyzer (Phase 41-03)

Detect bearing defects from vibration spectrum data.
Analyzes frequency peaks for characteristic bearing defect signatures:
- Outer race defects (BPFO)
- Inner race defects (BPFI)
- Ball/roller defects (BSF)
- Cage defects (FTF)

Also detects mechanical faults:
- Imbalance (1x RPM dominant)
- Misalignment (2x RPM dominant)
- Looseness (multiple harmonics)

Reference: ISO 10816 vibration severity standards
"""

import logging
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


class BearingAnalyzer:
    """Detect bearing defects from vibration spectrum data."""

    # Typical bearing defect frequency ratios (relative to shaft RPM)
    # These are approximate - real values depend on bearing geometry
    DEFECT_FREQUENCY_RATIOS = {
        "outer_race": 0.4,  # BPFO - Ball Pass Frequency Outer
        "inner_race": 0.6,  # BPFI - Ball Pass Frequency Inner
        "ball": 0.23,  # BSF - Ball Spin Frequency
        "cage": 0.4,  # FTF - Fundamental Train Frequency
    }

    # Equipment frequency profiles (SA 50Hz standard)
    # RPM can be overridden from equipment.specs.rpm in database
    EQUIPMENT_FREQUENCY_RANGES = {
        # Generators - SA uses 50Hz, so 1500 RPM (4-pole) or 3000 RPM (2-pole)
        "generator": {"rpm_default": 1500, "rpm_range": (1000, 3600), "bearing_band": (100, 5000)},
        "generator_4pole": {"rpm_default": 1500, "rpm_range": (1400, 1600), "bearing_band": (100, 5000)},
        "generator_2pole": {"rpm_default": 3000, "rpm_range": (2900, 3100), "bearing_band": (200, 8000)},
        # Other equipment
        "pump": {"rpm_default": 1450, "rpm_range": (1000, 3000), "bearing_band": (80, 4000)},
        "motor": {"rpm_default": 1450, "rpm_range": (1000, 3600), "bearing_band": (100, 5000)},
        "chiller": {"rpm_default": 1750, "rpm_range": (1000, 3000), "bearing_band": (100, 6000)},
        "fan": {"rpm_default": 900, "rpm_range": (500, 1500), "bearing_band": (50, 3000)},
        "ahu": {"rpm_default": 1000, "rpm_range": (500, 1500), "bearing_band": (50, 4000)},
    }

    # Fault signatures relative to 1x RPM frequency
    FAULT_SIGNATURES = {
        "imbalance": {"freq_ratio": 1.0, "description": "Strong 1x peak - rotor imbalance"},
        "misalignment": {"freq_ratio": 2.0, "description": "Strong 2x peak - shaft misalignment"},
        "looseness": {"freq_ratios": [0.5, 1.0, 2.0, 3.0], "description": "Multiple harmonics - mechanical looseness"},
        "electrical": {
            "freq_ratio": 2.0,
            "sidebands": True,
            "description": "Line frequency sidebands - electrical fault",
        },
    }

    def analyze(
        self, spectrum_data: dict[str, Any], equipment_type: str = "motor", shaft_rpm: float | None = None
    ) -> dict[str, Any]:
        """
        Analyze vibration spectrum for bearing defects.

        Args:
            spectrum_data: Spectrum from phyphox (peaks, frequencies)
            equipment_type: Type of equipment
            shaft_rpm: Known shaft RPM (optional, will estimate if not provided)

        Returns:
            Bearing analysis result with defect detection
        """
        result = {
            "defect_detected": False,
            "defect_type": None,
            "defect_frequency": None,
            "confidence": 0.0,
            "mechanical_fault": None,
            "analysis_details": {},
        }

        # Get peak frequencies from spectrum
        peak_freqs = spectrum_data.get("peak_frequencies_hz", [])
        peak_amps = spectrum_data.get("peak_amplitudes_ms2", spectrum_data.get("peak_amplitudes", []))

        if not peak_freqs:
            result["error"] = "No peak frequencies in spectrum data"
            return result

        # Ensure we have matching amplitudes
        if len(peak_amps) < len(peak_freqs):
            # Pad with default values
            peak_amps = list(peak_amps) + [0.1] * (len(peak_freqs) - len(peak_amps))

        # Get equipment frequency range
        eq_range = self.EQUIPMENT_FREQUENCY_RANGES.get(equipment_type, self.EQUIPMENT_FREQUENCY_RANGES["motor"])
        bearing_band = eq_range["bearing_band"]

        # Filter peaks within bearing frequency band
        bearing_peaks = [(f, a) for f, a in zip(peak_freqs, peak_amps, strict=False) if bearing_band[0] <= f <= bearing_band[1]]

        result["analysis_details"]["total_peaks"] = len(peak_freqs)
        result["analysis_details"]["peaks_in_bearing_band"] = len(bearing_peaks)

        # Estimate shaft RPM from dominant low frequency if not provided
        if shaft_rpm is None:
            shaft_rpm = self._estimate_shaft_rpm(peak_freqs, eq_range["rpm_range"])

        result["analysis_details"]["estimated_rpm"] = shaft_rpm
        shaft_freq = shaft_rpm / 60  # Hz
        result["analysis_details"]["shaft_frequency_hz"] = shaft_freq

        # First check for mechanical faults (imbalance, misalignment, looseness)
        mechanical = self._check_mechanical_faults(peak_freqs, peak_amps, shaft_freq)
        if mechanical:
            result["mechanical_fault"] = mechanical

        # Now check for bearing defects
        if bearing_peaks:
            defect_result = self._check_bearing_defects(bearing_peaks, shaft_freq, peak_freqs)
            if defect_result.get("defect_detected"):
                result.update(defect_result)

        return result

    def _estimate_shaft_rpm(self, peak_freqs: list[float], rpm_range: tuple) -> float:
        """Estimate shaft RPM from dominant frequency."""
        min_rpm, max_rpm = rpm_range
        min_freq, max_freq = min_rpm / 60, max_rpm / 60

        # Find dominant frequency in expected range
        for freq in sorted(peak_freqs):
            if min_freq <= freq <= max_freq:
                return freq * 60

        # Default to midpoint
        return (min_rpm + max_rpm) / 2

    def _check_mechanical_faults(
        self, peak_freqs: list[float], peak_amps: list[float], shaft_freq: float
    ) -> dict[str, Any] | None:
        """Check for imbalance, misalignment, looseness."""
        faults_found = []

        # Check for imbalance (strong 1x)
        for freq, amp in zip(peak_freqs, peak_amps, strict=False):
            if abs(freq - shaft_freq) < shaft_freq * 0.1:  # Within 10% of 1x
                # Check if this is dominant
                if amp > 0 and amp >= 0.5 * max(peak_amps):
                    faults_found.append(
                        {
                            "type": "imbalance",
                            "frequency_hz": freq,
                            "amplitude": amp,
                            "confidence": min(1.0, amp / max(peak_amps)),
                        }
                    )

        # Check for misalignment (strong 2x)
        for freq, amp in zip(peak_freqs, peak_amps, strict=False):
            if abs(freq - 2 * shaft_freq) < shaft_freq * 0.1:  # Within 10% of 2x
                if amp > 0 and amp >= 0.3 * max(peak_amps):
                    faults_found.append(
                        {
                            "type": "misalignment",
                            "frequency_hz": freq,
                            "amplitude": amp,
                            "confidence": min(1.0, amp / max(peak_amps)),
                        }
                    )

        # Check for looseness (multiple harmonics 0.5x, 1x, 2x, 3x)
        harmonic_count = 0
        for ratio in [0.5, 1.0, 2.0, 3.0]:
            expected = shaft_freq * ratio
            for freq in peak_freqs:
                if abs(freq - expected) < expected * 0.1:
                    harmonic_count += 1
                    break

        if harmonic_count >= 3:
            faults_found.append(
                {"type": "looseness", "harmonic_count": harmonic_count, "confidence": harmonic_count / 4.0}
            )

        if faults_found:
            # Return highest confidence fault
            return max(faults_found, key=lambda f: f.get("confidence", 0))

        return None

    def _check_bearing_defects(
        self, bearing_peaks: list[tuple], shaft_freq: float, all_freqs: list[float]
    ) -> dict[str, Any]:
        """Check for bearing defect frequencies."""
        result = {
            "defect_detected": False,
            "defect_type": None,
            "defect_frequency": None,
            "confidence": 0.0,
            "analysis_details": {},
        }

        # Calculate expected defect frequencies
        expected_defects = {}
        for defect_type, ratio in self.DEFECT_FREQUENCY_RATIOS.items():
            expected_defects[defect_type] = shaft_freq * ratio * 60  # Convert to Hz

        # Check for matches
        matches = []
        for defect_type, expected_freq in expected_defects.items():
            # Defect frequencies appear at higher multiples
            for multiplier in range(1, 5):
                check_freq = expected_freq * multiplier
                # Look for peaks near expected frequency (within 10%)
                for peak_freq, peak_amp in bearing_peaks:
                    tolerance = check_freq * 0.1
                    if abs(peak_freq - check_freq) < tolerance:
                        # Check for harmonics (2x, 3x of defect freq)
                        harmonic_count = self._count_harmonics(peak_freq, all_freqs)
                        confidence = self._calculate_confidence(peak_amp, [a for _, a in bearing_peaks], harmonic_count)
                        matches.append(
                            {
                                "defect_type": defect_type,
                                "expected_freq": check_freq,
                                "actual_freq": peak_freq,
                                "amplitude": peak_amp,
                                "harmonics": harmonic_count,
                                "confidence": confidence,
                                "multiplier": multiplier,
                            }
                        )

        if matches:
            # Take highest confidence match
            best_match = max(matches, key=lambda x: x["confidence"])
            if best_match["confidence"] > 0.3:  # Minimum threshold
                result["defect_detected"] = True
                result["defect_type"] = best_match["defect_type"]
                result["defect_frequency"] = best_match["actual_freq"]
                result["confidence"] = best_match["confidence"]
                result["analysis_details"]["matches"] = matches[:5]  # Top 5 matches

        return result

    def _count_harmonics(self, fundamental: float, all_freqs: list[float], max_harmonic: int = 5) -> int:
        """Count harmonic frequencies present."""
        count = 0
        for n in range(2, max_harmonic + 1):
            harmonic = fundamental * n
            for freq in all_freqs:
                if abs(freq - harmonic) < harmonic * 0.05:  # 5% tolerance
                    count += 1
                    break
        return count

    def _calculate_confidence(self, peak_amp: float, all_amps: list[float], harmonic_count: int) -> float:
        """Calculate confidence score for defect detection."""
        # Base confidence from amplitude prominence
        if all_amps and peak_amp > 0:
            all_amps_arr = np.array(all_amps)
            mean_amp = np.mean(all_amps_arr)
            std_amp = np.std(all_amps_arr) if len(all_amps_arr) > 1 else mean_amp
            if std_amp > 0:
                z_score = (peak_amp - mean_amp) / std_amp
                amplitude_confidence = min(1.0, max(0.0, z_score / 3))
            else:
                amplitude_confidence = 0.5
        else:
            amplitude_confidence = 0.5

        # Boost for harmonics (strong indicator of rotating machinery defect)
        harmonic_boost = min(0.3, harmonic_count * 0.1)

        return min(1.0, amplitude_confidence + harmonic_boost)


# Singleton instance
_analyzer_instance: BearingAnalyzer | None = None


def get_bearing_analyzer() -> BearingAnalyzer:
    """Get or create the singleton analyzer instance."""
    global _analyzer_instance
    if _analyzer_instance is None:
        _analyzer_instance = BearingAnalyzer()
    return _analyzer_instance
