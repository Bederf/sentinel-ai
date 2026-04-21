"""
Equipment Condition Scorer (Phase 41-03)

Generate unified condition score (0-100) for technicians.
Combines vibration, audio, and baseline comparison into pass/fail assessment.

Score bands:
- 80-100: GOOD (RUN) - Normal operation
- 60-79: FAIR (WATCH) - Monitor closely
- 40-59: POOR (PLAN SERVICE) - Schedule maintenance
- 0-39: CRITICAL (ACT NOW) - Immediate attention

Weights are configurable per asset class.
"""

import logging
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)


class ConditionGrade(StrEnum):
    """Equipment condition grade."""

    GOOD = "good"  # 80-100: Normal operation
    FAIR = "fair"  # 60-79: Monitor closely
    POOR = "poor"  # 40-59: Schedule service
    CRITICAL = "critical"  # 0-39: Immediate attention


class ConditionScorer:
    """Calculate equipment condition score from sensor readings."""

    # Default scoring weights (can be overridden per asset class)
    DEFAULT_WEIGHTS = {
        "vibration_rms": 0.30,  # RMS level vs baseline
        "vibration_peaks": 0.25,  # Harmonic structure health
        "audio_noise": 0.15,  # Noise floor level
        "frequency_stability": 0.15,  # Frequency consistency
        "baseline_deviation": 0.15,  # Change from baseline
    }

    # Asset-class specific weights
    ASSET_WEIGHTS = {
        "generator": {
            "vibration_rms": 0.35,
            "vibration_peaks": 0.25,
            "audio_noise": 0.15,
            "frequency_stability": 0.15,
            "baseline_deviation": 0.10,
        },
        "chiller": {
            "vibration_rms": 0.25,
            "vibration_peaks": 0.20,
            "audio_noise": 0.20,
            "frequency_stability": 0.15,
            "baseline_deviation": 0.20,
        },
        "pump": {
            "vibration_rms": 0.35,
            "vibration_peaks": 0.30,
            "audio_noise": 0.10,
            "frequency_stability": 0.10,
            "baseline_deviation": 0.15,
        },
        "ahu": {
            "vibration_rms": 0.30,
            "vibration_peaks": 0.20,
            "audio_noise": 0.20,
            "frequency_stability": 0.15,
            "baseline_deviation": 0.15,
        },
    }

    # Reference values for common equipment (SA standards)
    REFERENCE_PROFILES = {
        "generator_cummins_200kva": {
            "shaft_freq_hz": 25,
            "harmonics_hz": [50, 75, 100],
            "healthy_rms_range_ms2": (0.5, 3.0),  # m/s²
            "warning_rms_ms2": 5.0,
            "critical_rms_ms2": 10.0,
            "healthy_harmonic_ratio": (0.3, 0.7),  # 2nd/1st harmonic
        },
        "generator_default": {
            "shaft_freq_hz": 25,  # 1500 RPM SA standard
            "harmonics_hz": [50, 75],
            "healthy_rms_range_ms2": (0.5, 4.0),
            "warning_rms_ms2": 6.0,
            "critical_rms_ms2": 12.0,
        },
        "chiller_screw": {
            "shaft_freq_hz": 50,  # Variable, depends on compressor
            "harmonics_hz": [100, 150],
            "healthy_rms_range_ms2": (0.3, 2.5),
            "warning_rms_ms2": 4.0,
            "critical_rms_ms2": 8.0,
        },
        "pump_centrifugal": {
            "shaft_freq_hz": 24,  # ~1450 RPM
            "harmonics_hz": [48, 72],
            "healthy_rms_range_ms2": (0.2, 2.0),
            "warning_rms_ms2": 3.5,
            "critical_rms_ms2": 7.0,
        },
        "ahu_fan": {
            "shaft_freq_hz": 16,  # ~1000 RPM
            "harmonics_hz": [32, 48],
            "healthy_rms_range_ms2": (0.1, 1.5),
            "warning_rms_ms2": 3.0,
            "critical_rms_ms2": 6.0,
        },
    }

    def calculate_score(
        self,
        reading: dict[str, Any],
        baseline: dict[str, Any] | None = None,
        equipment_profile: str = "generator_default",
        asset_class: str = "generator",
    ) -> dict[str, Any]:
        """
        Calculate condition score (0-100) from sensor reading.

        Args:
            reading: Current sensor reading
            baseline: Optional baseline for comparison
            equipment_profile: Profile key for reference values
            asset_class: Asset class for weight selection

        Returns:
            {
                'score': 85,
                'grade': 'good',
                'pass': True,
                'components': {...},
                'recommendations': [...]
            }
        """
        profile = self.REFERENCE_PROFILES.get(equipment_profile, self.REFERENCE_PROFILES["generator_default"])
        weights = self.ASSET_WEIGHTS.get(asset_class, self.DEFAULT_WEIGHTS)

        components = {}
        recommendations = []

        # 1. Vibration RMS score (0-100)
        rms = reading.get("rms_total_ms2") or reading.get("rms_value", 0)
        rms_score = self._score_rms(rms, profile)
        components["vibration_rms"] = {"value": rms, "score": rms_score}
        if rms_score < 60:
            recommendations.append("Vibration levels elevated - check mounting and bearings")
        elif rms_score < 80:
            recommendations.append("Vibration slightly elevated - monitor on next visit")

        # 2. Vibration peak structure score
        peaks = reading.get("peak_frequencies_hz", [])
        peak_score = self._score_harmonic_structure(peaks, profile)
        components["vibration_peaks"] = {"peaks": peaks[:5], "score": peak_score}
        if peak_score < 60:
            recommendations.append("Abnormal frequency peaks detected - investigate")
        elif peak_score < 80:
            recommendations.append("Minor frequency anomalies - monitor")

        # 3. Baseline deviation score (if baseline available)
        if baseline:
            baseline_score = self._score_baseline_deviation(reading, baseline)
            components["baseline_deviation"] = {"score": baseline_score}
            if baseline_score < 60:
                recommendations.append("Significant change from baseline - compare with onboarding readings")
            elif baseline_score < 80:
                recommendations.append("Minor deviation from baseline - track trend")
        else:
            baseline_score = 80  # Neutral if no baseline
            components["baseline_deviation"] = {"score": baseline_score, "note": "No baseline available"}

        # 4. Audio noise score (placeholder - use default if not available)
        audio_level = reading.get("overall_level_db")
        if audio_level is not None:
            audio_score = self._score_audio_level(audio_level)
            components["audio_noise"] = {"value": audio_level, "score": audio_score}
        else:
            audio_score = 80  # Neutral if not available
            components["audio_noise"] = {"score": audio_score, "note": "No audio data"}

        # 5. Frequency stability (placeholder)
        freq_variance = reading.get("frequency_variance")
        if freq_variance is not None:
            stability_score = self._score_frequency_stability(freq_variance)
            components["frequency_stability"] = {"variance": freq_variance, "score": stability_score}
        else:
            stability_score = 80  # Neutral if not available
            components["frequency_stability"] = {"score": stability_score, "note": "No variance data"}

        # Calculate weighted score
        total_score = (
            rms_score * weights["vibration_rms"]
            + peak_score * weights["vibration_peaks"]
            + baseline_score * weights["baseline_deviation"]
            + audio_score * weights["audio_noise"]
            + stability_score * weights["frequency_stability"]
        )

        # Determine grade
        if total_score >= 80:
            grade = ConditionGrade.GOOD
        elif total_score >= 60:
            grade = ConditionGrade.FAIR
        elif total_score >= 40:
            grade = ConditionGrade.POOR
        else:
            grade = ConditionGrade.CRITICAL

        # Pass/fail for technicians (simple threshold)
        pass_fail = total_score >= 60

        # Add grade-specific recommendations
        if grade == ConditionGrade.CRITICAL:
            recommendations.insert(0, "CRITICAL: Immediate inspection required")
        elif grade == ConditionGrade.POOR:
            recommendations.insert(0, "Schedule maintenance within 2 weeks")

        return {
            "score": round(total_score),
            "grade": grade.value,
            "pass": pass_fail,
            "components": components,
            "weights": weights,
            "recommendations": recommendations,
            "action_required": grade in (ConditionGrade.POOR, ConditionGrade.CRITICAL),
        }

    def _score_rms(self, rms: float, profile: dict) -> float:
        """Score RMS vibration level (0-100)."""
        if rms <= 0:
            return 80  # No data

        healthy_max = profile["healthy_rms_range_ms2"][1]
        warning = profile["warning_rms_ms2"]
        critical = profile["critical_rms_ms2"]

        if rms <= healthy_max:
            return 100
        elif rms <= warning:
            # Linear interpolation between healthy max and warning
            ratio = (rms - healthy_max) / (warning - healthy_max)
            return 100 - (ratio * 40)  # 100 -> 60
        elif rms <= critical:
            ratio = (rms - warning) / (critical - warning)
            return 60 - (ratio * 40)  # 60 -> 20
        else:
            return max(0, 20 - (rms - critical) * 2)

    def _score_harmonic_structure(self, peaks: list, profile: dict) -> float:
        """Score whether peaks match expected harmonics (0-100)."""
        if not peaks:
            return 50  # No data

        shaft_freq = profile["shaft_freq_hz"]
        expected = [shaft_freq, *profile.get("harmonics_hz", [])]

        # Count how many expected frequencies are present
        matches = 0
        unexpected = 0
        for peak in peaks[:10]:  # Top 10 peaks
            is_expected = any(abs(peak - e) / e < 0.05 for e in expected if e > 0)
            if is_expected:
                matches += 1
            else:
                unexpected += 1

        # Score based on matches vs unexpected
        match_ratio = matches / len(expected) if len(expected) > 0 else 0.5

        unexpected_penalty = min(30, unexpected * 10)

        return max(0, min(100, match_ratio * 100 - unexpected_penalty))

    def _score_baseline_deviation(self, reading: dict, baseline: dict) -> float:
        """Score deviation from baseline (0-100)."""
        current_rms = reading.get("rms_total_ms2") or reading.get("rms_value", 0)
        baseline_rms = baseline.get("vibration_rms_ms2", current_rms)

        if baseline_rms == 0 or current_rms == 0:
            return 80  # No valid comparison

        change_pct = abs((current_rms - baseline_rms) / baseline_rms) * 100

        if change_pct <= 10:
            return 100
        elif change_pct <= 30:
            return 80
        elif change_pct <= 50:
            return 60
        elif change_pct <= 100:
            return 40
        else:
            return 20

    def _score_audio_level(self, level_db: float) -> float:
        """Score audio noise level (0-100)."""
        # Typical industrial equipment: 70-90 dB normal, >100 dB concern
        if level_db < 80:
            return 100
        elif level_db < 90:
            return 85
        elif level_db < 100:
            return 70
        elif level_db < 110:
            return 50
        else:
            return 30

    def _score_frequency_stability(self, variance: float) -> float:
        """Score frequency stability (0-100)."""
        # Lower variance = more stable = better
        if variance < 0.5:
            return 100
        elif variance < 1.0:
            return 85
        elif variance < 2.0:
            return 70
        elif variance < 5.0:
            return 50
        else:
            return 30

    def format_for_telegram(self, result: dict[str, Any], equipment_name: str) -> str:
        """
        Format condition score for Telegram.

        Args:
            result: Result from calculate_score()
            equipment_name: Equipment name

        Returns:
            Formatted string for Telegram
        """
        grade_emoji = {"good": "🟢", "fair": "🟡", "poor": "🟠", "critical": "🔴"}

        action_emoji = {"good": "RUN", "fair": "WATCH", "poor": "PLAN SERVICE", "critical": "ACT NOW"}

        emoji = grade_emoji.get(result["grade"], "❓")
        action = action_emoji.get(result["grade"], "UNKNOWN")
        pass_text = "✅ PASS" if result["pass"] else "❌ FAIL"

        lines = [
            "📊 **Condition Assessment**",
            "",
            f"Equipment: {equipment_name}",
            f"Score: {emoji} **{result['score']}/100** ({result['grade'].upper()})",
            f"Action: **{action}**",
            f"Result: {pass_text}",
        ]

        # Show component scores
        if result.get("components"):
            lines.append("")
            lines.append("**Component Scores:**")
            for name, comp in result["components"].items():
                if "score" in comp:
                    score = comp["score"]
                    score_bar = "█" * int(score / 10) + "░" * (10 - int(score / 10))
                    lines.append(f"• {name.replace('_', ' ').title()}: [{score_bar}] {score:.0f}")

        if result["recommendations"]:
            lines.append("")
            lines.append("**Recommendations:**")
            for rec in result["recommendations"][:5]:  # Max 5 recommendations
                lines.append(f"• {rec}")

        if result["action_required"]:
            lines.append("")
            lines.append("⚠️ **Action Required** - Schedule inspection")

        return "\n".join(lines)


# Singleton instance
_scorer_instance: ConditionScorer | None = None


def get_condition_scorer() -> ConditionScorer:
    """Get or create the singleton scorer instance."""
    global _scorer_instance
    if _scorer_instance is None:
        _scorer_instance = ConditionScorer()
    return _scorer_instance
