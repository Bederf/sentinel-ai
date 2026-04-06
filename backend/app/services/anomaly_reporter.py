"""
Anomaly Report Generator (Phase 41-03)

Generate human-readable reports from anomaly detection results.
Formats reports for Telegram/Sentry delivery and service record storage.

Reference: backend/app/services/sentry_integration for message patterns
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class AnomalyReporter:
    """Generate human-readable reports from anomaly detection results."""

    SEVERITY_EMOJI = {"normal": "✅", "low": "⚠️", "medium": "🟠", "high": "🔴", "critical": "🔴"}

    DEFECT_DESCRIPTIONS = {
        "outer_race": "Outer race bearing defect - likely pitting or spalling on outer race",
        "inner_race": "Inner race bearing defect - damage to inner race surface",
        "ball": "Ball/roller defect - damage to rolling elements",
        "cage": "Cage defect - damage to bearing cage/retainer",
        "engine_knock": "Engine knock detected - combustion timing or mechanical issue",
        "imbalance": "Rotor imbalance - uneven mass distribution on rotating component",
        "misalignment": "Shaft misalignment - angular or parallel misalignment",
        "looseness": "Mechanical looseness - loose mounting or worn components",
        "combustion": "Combustion knock - detonation or pre-ignition issue",
        "rod_bearing": "Rod bearing knock - connecting rod bearing wear",
        "main_bearing": "Main bearing knock - crankshaft main bearing issue",
        "valve_train": "Valve train noise - valve or rocker arm issue",
    }

    RECOMMENDATIONS = {
        "outer_race": [
            "Schedule bearing replacement within 2-4 weeks",
            "Monitor vibration levels daily",
            "Check for contamination or lubrication issues",
        ],
        "inner_race": [
            "Schedule bearing replacement within 1-2 weeks",
            "Reduce load if possible",
            "Check shaft alignment",
        ],
        "ball": ["Schedule bearing replacement soon", "Investigate cause - contamination, overload, or misalignment"],
        "cage": ["Schedule bearing replacement", "Check lubrication - cage damage often from inadequate lubrication"],
        "imbalance": [
            "Check for loose or missing components",
            "Verify coupling condition",
            "Schedule dynamic balancing",
        ],
        "misalignment": ["Check coupling alignment", "Inspect mounting bolts", "Verify foundation condition"],
        "looseness": [
            "Check all mounting bolts",
            "Inspect foundation/base plate",
            "Look for cracked welds or worn mounts",
        ],
        "engine_knock": [
            "Check fuel quality and octane rating",
            "Inspect ignition timing",
            "Check for carbon buildup",
            "Investigate if knock occurs under load or at idle",
        ],
        "combustion": [
            "Check fuel quality",
            "Verify injection timing",
            "Inspect injectors for wear",
            "Check compression",
        ],
        "rod_bearing": [
            "Reduce load immediately",
            "Check oil pressure and level",
            "Schedule urgent inspection",
            "Do not operate at high load",
        ],
        "main_bearing": [
            "STOP engine - do not operate",
            "Critical bearing damage suspected",
            "Schedule emergency inspection",
            "Check for metal in oil",
        ],
        "valve_train": ["Check valve clearances", "Inspect rocker arms and pushrods", "Check for broken valve springs"],
    }

    def generate_report(
        self, analysis_result: dict[str, Any], equipment_id: str, equipment_name: str | None = None
    ) -> str:
        """
        Generate a Telegram-friendly report from analysis results.

        Args:
            analysis_result: Result from phyphox_handler with anomalies
            equipment_id: Equipment identifier
            equipment_name: Optional human-readable name

        Returns:
            Formatted string for Telegram
        """
        anomalies = analysis_result.get("anomalies", {})
        detected = anomalies.get("detected", [])
        severity = anomalies.get("severity", "normal")

        emoji = self.SEVERITY_EMOJI.get(severity, "❓")
        equipment_label = equipment_name or equipment_id

        # Check for mechanical faults in the raw analysis
        mechanical_fault = None
        if "mechanical_fault" in analysis_result:
            mechanical_fault = analysis_result["mechanical_fault"]
        elif detected:
            # Check if any detected anomaly is a mechanical fault
            for anomaly in detected:
                if anomaly.get("type") in ("imbalance", "misalignment", "looseness"):
                    mechanical_fault = anomaly
                    break

        if not detected and not mechanical_fault:
            return f"""📊 **Sensor Analysis Complete**

Equipment: {equipment_label}
Result: {emoji} No anomalies detected

Vibration levels appear normal. Continue regular maintenance schedule."""

        # Build report for detected anomalies
        lines = [
            "📊 **Sensor Analysis Complete**",
            "",
            f"Equipment: {equipment_label}",
            f"Result: {emoji} **{severity.upper()} - Anomaly Detected**",
            "",
        ]

        # Report mechanical faults
        if mechanical_fault:
            fault_type = mechanical_fault.get("type", "unknown")
            confidence = mechanical_fault.get("confidence", 0)
            description = self.DEFECT_DESCRIPTIONS.get(fault_type, f"Mechanical fault: {fault_type}")

            lines.append(f"**Finding:** {description}")
            lines.append(f"Confidence: {confidence:.0%}")
            if mechanical_fault.get("frequency_hz"):
                lines.append(f"Frequency: {mechanical_fault['frequency_hz']:.1f} Hz")
            lines.append("")

            # Recommendations
            recs = self.RECOMMENDATIONS.get(fault_type, ["Schedule inspection"])
            lines.append("**Recommended Actions:**")
            for rec in recs:
                lines.append(f"• {rec}")
            lines.append("")

        # Report detected anomalies from bearing/knock detection
        for anomaly in detected:
            atype = anomaly.get("type", "unknown")
            subtype = anomaly.get("subtype")
            confidence = anomaly.get("confidence", 0)
            freq = anomaly.get("frequency_hz")

            # Skip if same as mechanical fault already reported
            if mechanical_fault and atype == mechanical_fault.get("type"):
                continue

            # Description
            desc_key = subtype or atype
            description = self.DEFECT_DESCRIPTIONS.get(desc_key, f"Unknown anomaly: {atype}")

            lines.append(f"**Finding:** {description}")
            lines.append(f"Confidence: {confidence:.0%}")
            if freq:
                lines.append(f"Frequency: {freq:.1f} Hz")
            lines.append("")

            # Recommendations
            recs = self.RECOMMENDATIONS.get(desc_key, ["Schedule inspection"])
            lines.append("**Recommended Actions:**")
            for rec in recs:
                lines.append(f"• {rec}")
            lines.append("")

        return "\n".join(lines)

    def generate_summary_for_service_record(self, analysis_result: dict[str, Any]) -> dict[str, Any]:
        """
        Generate structured summary for storage in service record.

        Args:
            analysis_result: Full analysis result

        Returns:
            Summary dict for database storage
        """
        anomalies = analysis_result.get("anomalies", {})
        detected = anomalies.get("detected", [])
        mechanical_fault = analysis_result.get("mechanical_fault")

        # Collect all anomaly types
        anomaly_types = [a.get("type") for a in detected]
        if mechanical_fault:
            anomaly_types.append(mechanical_fault.get("type"))

        # Determine if followup needed
        severity = anomalies.get("severity", "normal")
        requires_followup = severity in ("medium", "high", "critical")

        # If we have a main bearing knock, always critical
        if any(t == "main_bearing" for t in anomaly_types):
            requires_followup = True

        return {
            "has_anomalies": len(detected) > 0 or mechanical_fault is not None,
            "severity": severity,
            "anomaly_types": list(set(anomaly_types)),  # Deduplicate
            "max_confidence": anomalies.get("confidence", 0),
            "requires_followup": requires_followup,
            "mechanical_fault_detected": mechanical_fault is not None,
        }

    def generate_baseline_report(self, analysis_result: dict[str, Any], equipment_name: str, condition: str) -> str:
        """
        Generate report for baseline capture.

        Args:
            analysis_result: Analysis result
            equipment_name: Equipment name
            condition: Condition at capture (good/fair/poor)

        Returns:
            Formatted string for Telegram
        """
        condition_emoji = {"good": "🟢", "fair": "🟡", "poor": "🟠", "unknown": "⚪"}

        emoji = condition_emoji.get(condition, "⚪")
        rms = analysis_result.get("rms_total_ms2", analysis_result.get("rms_value", "N/A"))
        dominant_freq = analysis_result.get("dominant_frequency_hz", "N/A")

        lines = [
            "📊 **Baseline Captured**",
            "",
            f"Equipment: {equipment_name}",
            f"Condition: {emoji} {condition.upper()}",
            "",
            "**Recorded Values:**",
        ]

        if isinstance(rms, (int, float)):
            lines.append(f"• RMS Vibration: {rms:.3f} m/s²")
        else:
            lines.append(f"• RMS Vibration: {rms}")

        if isinstance(dominant_freq, (int, float)):
            lines.append(f"• Dominant Frequency: {dominant_freq:.1f} Hz")
        else:
            lines.append(f"• Dominant Frequency: {dominant_freq}")

        peak_freqs = analysis_result.get("peak_frequencies_hz", [])
        if peak_freqs:
            lines.append(f"• Peak Frequencies: {', '.join(f'{f:.0f}Hz' for f in peak_freqs[:5])}")

        lines.extend(
            [
                "",
                "✅ Future readings will be compared against this baseline.",
                "💡 Re-capture baseline after major service.",
            ]
        )

        return "\n".join(lines)

    def generate_comparison_report(self, comparison_result: dict[str, Any], equipment_name: str) -> str:
        """
        Generate report comparing current reading to baseline.

        Args:
            comparison_result: Result from BaselineComparator
            equipment_name: Equipment name

        Returns:
            Formatted string for Telegram
        """
        status = comparison_result.get("overall_status", "normal")
        deviations = comparison_result.get("deviations", [])
        alerts = comparison_result.get("alerts", [])

        emoji = self.SEVERITY_EMOJI.get(status, "❓")

        lines = [
            "📊 **Baseline Comparison**",
            "",
            f"Equipment: {equipment_name}",
            f"Status: {emoji} {status.upper()}",
            "",
        ]

        # Report deviations
        if deviations:
            lines.append("**Changes from Baseline:**")
            for dev in deviations:
                metric = dev.get("metric", "unknown")
                if "change_pct" in dev:
                    lines.append(f"• {metric}: {dev['change_pct']:+.1f}%")
                elif "change_db" in dev:
                    lines.append(f"• {metric}: {dev['change_db']:+.1f} dB")
                elif "count" in dev:
                    lines.append(f"• {metric}: {dev['count']} detected")
            lines.append("")

        # Report alerts
        if alerts:
            lines.append("**Alerts:**")
            for alert in alerts:
                severity = alert.get("severity", "warning")
                message = alert.get("message", "")
                alert_emoji = self.SEVERITY_EMOJI.get(severity, "⚠️")
                lines.append(f"{alert_emoji} {message}")
            lines.append("")

        # Summary
        if status == "normal":
            lines.append("✅ Within acceptable range of baseline.")
        elif status == "warning":
            lines.append("⚠️ Monitor closely - values deviating from baseline.")
        else:
            lines.append("🔴 Significant deviation - schedule inspection.")

        return "\n".join(lines)


# Singleton instance
_reporter_instance: AnomalyReporter | None = None


def get_anomaly_reporter() -> AnomalyReporter:
    """Get or create the singleton reporter instance."""
    global _reporter_instance
    if _reporter_instance is None:
        _reporter_instance = AnomalyReporter()
    return _reporter_instance
