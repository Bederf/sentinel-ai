"""
Engine Knock Detector (Phase 41-03)

Detect engine knock from audio spectrum data.
Engine knock manifests as low-frequency impacts with harmonics,
typically caused by:
- Detonation/pre-ignition
- Mechanical damage (rod knock, main bearing)
- Valve train issues

Reference: SAE papers on engine knock detection
"""

import logging
from typing import Dict, Any, List, Optional


logger = logging.getLogger(__name__)


class KnockDetector:
    """Detect engine knock from audio spectrum data."""

    # Engine knock characteristics
    KNOCK_FREQUENCY_RANGE = (5, 50)  # Hz - low frequency impacts
    KNOCK_HARMONIC_RANGE = (50, 200)  # Hz - harmonics of knock

    # Typical knock frequencies by engine type
    ENGINE_KNOCK_PROFILES = {
        "diesel_4cyl": {
            "knock_range": (10, 40),
            "typical_freq": 20,  # Half-order at 1500 RPM
        },
        "diesel_6cyl": {
            "knock_range": (15, 50),
            "typical_freq": 25,  # For 1500 RPM
        },
        "generator": {
            "knock_range": (10, 50),
            "typical_freq": 25,  # 1500 RPM SA standard
        },
    }

    def analyze(self, spectrum_data: Dict[str, Any], engine_type: str = "generator") -> Dict[str, Any]:
        """
        Analyze audio spectrum for engine knock.

        Args:
            spectrum_data: Spectrum from phyphox (peaks, frequencies)
            engine_type: Type of engine for profile selection

        Returns:
            Knock detection result
        """
        result = {
            "knock_detected": False,
            "knock_frequency": None,
            "knock_type": None,
            "confidence": 0.0,
            "analysis_details": {},
        }

        peak_freqs = spectrum_data.get("peak_frequencies_hz", [])
        peak_amps = spectrum_data.get("peak_amplitudes_db", spectrum_data.get("peak_amplitudes", []))

        if not peak_freqs:
            result["error"] = "No peak frequencies in spectrum data"
            return result

        # Ensure we have matching amplitudes
        if len(peak_amps) < len(peak_freqs):
            peak_amps = list(peak_amps) + [50.0] * (len(peak_freqs) - len(peak_amps))

        result["analysis_details"]["total_peaks"] = len(peak_freqs)

        # Get engine profile
        profile = self.ENGINE_KNOCK_PROFILES.get(engine_type, self.ENGINE_KNOCK_PROFILES["generator"])
        knock_range = profile["knock_range"]

        # Look for low frequency peaks (engine knock signature)
        low_freq_peaks = [(f, a) for f, a in zip(peak_freqs, peak_amps) if knock_range[0] <= f <= knock_range[1]]

        result["analysis_details"]["peaks_in_knock_range"] = len(low_freq_peaks)

        if not low_freq_peaks:
            result["analysis_details"]["note"] = "No peaks in knock frequency range"
            return result

        # Knock typically shows as strong low frequency + harmonics
        best_knock = None
        best_confidence = 0.0

        for knock_freq, knock_amp in low_freq_peaks:
            harmonic_evidence = self._check_harmonics(knock_freq, peak_freqs, peak_amps)

            if harmonic_evidence["count"] >= 2:  # At least 2 harmonics
                confidence = self._calculate_knock_confidence(knock_amp, peak_amps, harmonic_evidence)

                if confidence > best_confidence:
                    best_confidence = confidence
                    best_knock = {
                        "frequency": knock_freq,
                        "amplitude": knock_amp,
                        "harmonics": harmonic_evidence,
                        "confidence": confidence,
                    }

        if best_knock and best_knock["confidence"] > 0.3:
            result["knock_detected"] = True
            result["knock_frequency"] = best_knock["frequency"]
            result["confidence"] = best_knock["confidence"]
            result["knock_type"] = self._classify_knock_type(best_knock["frequency"], profile)
            result["analysis_details"] = {
                "fundamental": best_knock["frequency"],
                "harmonics": best_knock["harmonics"]["harmonics"],
                "amplitude": best_knock["amplitude"],
                "harmonic_count": best_knock["harmonics"]["count"],
            }

        return result

    def _check_harmonics(self, fundamental: float, freqs: List[float], amps: List[float]) -> Dict[str, Any]:
        """Check for harmonic series indicating knock."""
        harmonics = []
        for n in range(2, 8):  # Check up to 7th harmonic
            expected = fundamental * n
            for f, a in zip(freqs, amps):
                if abs(f - expected) < expected * 0.1:  # 10% tolerance
                    harmonics.append({"n": n, "freq": f, "amp": a})
                    break

        return {"count": len(harmonics), "harmonics": harmonics}

    def _calculate_knock_confidence(
        self, knock_amp: float, all_amps: List[float], harmonic_evidence: Dict[str, Any]
    ) -> float:
        """Calculate confidence that knock is present."""
        # Base: amplitude prominence (percentile)
        if all_amps:
            amp_percentile = sum(1 for a in all_amps if a < knock_amp) / len(all_amps)
        else:
            amp_percentile = 0.5

        # Harmonic boost (more harmonics = more confidence)
        harmonic_boost = min(0.4, harmonic_evidence["count"] * 0.1)

        # Harmonic decay pattern (knock harmonics typically decay smoothly)
        decay_boost = 0.0
        if harmonic_evidence["harmonics"]:
            harmonic_amps = [h["amp"] for h in harmonic_evidence["harmonics"]]
            if len(harmonic_amps) >= 2:
                # Check if harmonics decay (expected for knock)
                decay_count = sum(1 for i in range(len(harmonic_amps) - 1) if harmonic_amps[i] >= harmonic_amps[i + 1])
                decay_ratio = decay_count / (len(harmonic_amps) - 1)
                decay_boost = decay_ratio * 0.2
            else:
                decay_boost = 0.1

        return min(1.0, amp_percentile * 0.5 + harmonic_boost + decay_boost)

    def _classify_knock_type(self, frequency: float, profile: Dict) -> str:
        """Classify the type of knock based on frequency."""
        typical = profile["typical_freq"]

        if frequency < typical * 0.5:
            return "main_bearing"  # Very low - likely main bearing
        elif frequency < typical * 0.8:
            return "rod_bearing"  # Moderately low - rod bearing
        elif frequency < typical * 1.2:
            return "combustion"  # Near expected - combustion knock
        else:
            return "valve_train"  # Higher frequency - valve train

    def analyze_severity(
        self, knock_result: Dict[str, Any], baseline: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Analyze knock severity based on detection results and baseline.

        Args:
            knock_result: Result from analyze()
            baseline: Previous baseline knock measurement

        Returns:
            Severity assessment with recommendations
        """
        if not knock_result.get("knock_detected"):
            return {"severity": "none", "recommendation": "No knock detected - continue normal operation"}

        confidence = knock_result.get("confidence", 0)
        knock_type = knock_result.get("knock_type", "unknown")

        # Severity based on confidence and type
        severity_map = {
            "main_bearing": "critical",  # Always critical
            "rod_bearing": "high",
            "combustion": "medium" if confidence < 0.7 else "high",
            "valve_train": "low" if confidence < 0.5 else "medium",
        }

        severity = severity_map.get(knock_type, "medium")

        # Recommendations by severity
        recommendations = {
            "critical": [
                "STOP engine immediately",
                "Do not operate until inspected",
                "Schedule emergency maintenance",
                "Check oil pressure and level",
            ],
            "high": [
                "Reduce load immediately",
                "Schedule urgent inspection",
                "Monitor oil pressure",
                "Check for metal in oil",
            ],
            "medium": [
                "Monitor closely during operation",
                "Schedule inspection within 1 week",
                "Check fuel quality",
                "Verify ignition timing",
            ],
            "low": ["Continue monitoring", "Note in service log", "Re-test after next service"],
        }

        return {
            "severity": severity,
            "knock_type": knock_type,
            "confidence": confidence,
            "recommendations": recommendations.get(severity, []),
            "action_required": severity in ("critical", "high"),
        }


# Singleton instance
_detector_instance: Optional[KnockDetector] = None


def get_knock_detector() -> KnockDetector:
    """Get or create the singleton detector instance."""
    global _detector_instance
    if _detector_instance is None:
        _detector_instance = KnockDetector()
    return _detector_instance
