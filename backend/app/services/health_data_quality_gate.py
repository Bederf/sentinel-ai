"""
Health Data Quality Gate — mode-specific confidence classification.

Phase 109B: Health Assessment Timeline

Evaluates data sufficiency for a single equipment's health assessment.
Four gates are checked against mode-specific thresholds:

  1. Data freshness (minutes since last reading)
  2. Snapshot density (snapshots per 24 hours)
  3. Valid point ratio (fraction of non-null readings)
  4. Baseline recency (days since last baseline capture)

Confidence classification:
  - high:   all gates pass
  - medium: exactly 1 gate fails
  - low:    2 or more gates fail → assessment_state = 'degraded_data'

NOTE: This is SEPARATE from Phase 109's QualityGateEvaluator which
evaluates recommendation quality across 14 metrics. This gate evaluates
health assessment data sufficiency for a single equipment.
"""

import logging

from app.models.health_rating import HealthDataQualityResult

logger = logging.getLogger(__name__)

# Mode-specific gate thresholds
_GATE_THRESHOLDS = {
    "simulation": {
        "freshness_max_minutes": 1440,  # 24 hours
        "min_snapshots_24h": 4,
        "min_valid_point_ratio": 0.90,
        "max_baseline_age_days": 30,
    },
    "shadow_live": {
        "freshness_max_minutes": 120,  # 2 hours
        "min_snapshots_24h": 20,
        "min_valid_point_ratio": 0.98,
        "max_baseline_age_days": 14,
    },
    "live_control": {
        "freshness_max_minutes": 30,  # 30 minutes
        "min_snapshots_24h": 44,
        "min_valid_point_ratio": 0.995,
        "max_baseline_age_days": 7,
    },
}

TOTAL_GATES = 4


class HealthDataQualityGate:
    """Evaluates data quality for health assessment confidence.

    Each of the four gates is checked against mode-specific thresholds.
    The number of failures determines the confidence level.
    """

    def evaluate(
        self,
        mode: str,
        freshness_minutes: float,
        snapshot_count_24h: int,
        valid_point_ratio: float,
        baseline_age_days: int,
    ) -> HealthDataQualityResult:
        """Evaluate data quality gates for the given mode.

        Args:
            mode: Ingestion mode — 'simulation', 'shadow_live', or 'live_control'.
            freshness_minutes: Minutes since last sensor data arrived.
            snapshot_count_24h: Number of health snapshots in last 24 hours.
            valid_point_ratio: Fraction of valid (non-null) data points (0.0-1.0).
            baseline_age_days: Days since the last baseline was captured.

        Returns:
            HealthDataQualityResult with gate counts and confidence/state.
        """
        thresholds = _GATE_THRESHOLDS.get(mode)
        if thresholds is None:
            logger.warning(f"Unknown ingestion mode '{mode}', falling back to 'simulation' thresholds")
            thresholds = _GATE_THRESHOLDS["simulation"]

        # Check each gate
        failures = 0

        if freshness_minutes > thresholds["freshness_max_minutes"]:
            failures += 1

        if snapshot_count_24h < thresholds["min_snapshots_24h"]:
            failures += 1

        if valid_point_ratio < thresholds["min_valid_point_ratio"]:
            failures += 1

        if baseline_age_days > thresholds["max_baseline_age_days"]:
            failures += 1

        gates_passed = TOTAL_GATES - failures

        # Confidence classification
        if failures == 0:
            confidence = "high"
        elif failures == 1:
            confidence = "medium"
        else:
            confidence = "low"

        # Assessment state
        assessment_state = "degraded_data" if confidence == "low" else "normal"

        return HealthDataQualityResult(
            freshness_minutes=freshness_minutes,
            snapshot_count_24h=snapshot_count_24h,
            valid_point_ratio=valid_point_ratio,
            baseline_age_days=baseline_age_days,
            gates_passed=gates_passed,
            gates_total=TOTAL_GATES,
            confidence=confidence,
            assessment_state=assessment_state,
        )
