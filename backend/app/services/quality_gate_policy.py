"""Quality Gate Policy Registry — Phase 109: Recommendation Quality Gate.

Defines threshold registry (14 metrics x 3 ingestion modes) for recommendation
quality gating. Each metric has a MetricThreshold with pass/warn/fail bounds
and direction semantics. The QualityGatePolicy is a frozen registry: thresholds
are class-level constants and never mutated at runtime.

Metrics sourced from existing services:
- MonitoringService: freshness, error rate, match coverage, provenance
- CommissioningService: gates passed, truth check, consecutive pass days
- MVVerificationService: accuracy, rollback rate, comfort violations
- MLFeedbackService: feedback capture rate, label lag
- MLOps alerts: drift critical alerts
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class RuleState(StrEnum):
    """Evaluation result for a single metric threshold."""

    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"
    NA = "na"


class GateStatus(StrEnum):
    """Overall quality gate status (aggregate of all rule states)."""

    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


class EnforcementAction(StrEnum):
    """Action applied to recommendations based on gate status + mode."""

    NORMAL = "normal"
    CAP_CONFIDENCE = "cap_confidence"
    SUPPRESS_TIER3 = "suppress_tier3"
    BLOCK_WRITES = "block_writes"


class ReasonCode(StrEnum):
    """Machine-readable reason for quality gate failures."""

    QUALITY_GATE_BLOCK = "quality_gate_block"
    DATA_FRESHNESS_FAIL = "data_freshness_fail"
    INGEST_ERROR_RATE_FAIL = "ingest_error_rate_fail"
    MATCH_COVERAGE_FAIL = "match_coverage_fail"
    JSON_IN_LIVE_FAIL = "json_in_live_fail"
    COMMISSIONING_FAIL = "commissioning_fail"
    TRUTH_CHECK_FAIL = "truth_check_fail"
    MV_ACCURACY_FAIL = "mv_accuracy_fail"
    FEEDBACK_COVERAGE_FAIL = "feedback_coverage_fail"
    DRIFT_CRITICAL_FAIL = "drift_critical_fail"


# ---------------------------------------------------------------------------
# Metric -> ReasonCode mapping
# ---------------------------------------------------------------------------

METRIC_REASON_CODES: dict[str, ReasonCode] = {
    "freshness_minutes": ReasonCode.DATA_FRESHNESS_FAIL,
    "ingest_error_rate_pct_1h": ReasonCode.INGEST_ERROR_RATE_FAIL,
    "match_coverage_pct": ReasonCode.MATCH_COVERAGE_FAIL,
    "manual_source_pct": ReasonCode.JSON_IN_LIVE_FAIL,
    "commissioning_all_gates_passed": ReasonCode.COMMISSIONING_FAIL,
    "truth_check_pass_rate_pct": ReasonCode.TRUTH_CHECK_FAIL,
    "mv_accuracy_7d_pct": ReasonCode.MV_ACCURACY_FAIL,
    "feedback_capture_rate_7d_pct": ReasonCode.FEEDBACK_COVERAGE_FAIL,
    "drift_critical_alerts_24h": ReasonCode.DRIFT_CRITICAL_FAIL,
    # Remaining metrics map to the generic code
    "unmatched_points_pct": ReasonCode.QUALITY_GATE_BLOCK,
    "consecutive_pass_days": ReasonCode.QUALITY_GATE_BLOCK,
    "comfort_violation_rate_7d_pct": ReasonCode.QUALITY_GATE_BLOCK,
    "rollback_rate_7d_pct": ReasonCode.QUALITY_GATE_BLOCK,
    "label_lag_p95_hours": ReasonCode.QUALITY_GATE_BLOCK,
}


# ---------------------------------------------------------------------------
# MetricThreshold dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MetricThreshold:
    """Threshold definition for a single quality metric.

    Direction semantics:
    - lower_is_better: value <= pass_bound -> PASS, <= warn_bound -> WARN, else FAIL
    - higher_is_better: value >= pass_bound -> PASS, >= warn_bound -> WARN, else FAIL

    When na=True, evaluate() always returns NA regardless of value.
    When warn_bound is None, there is no WARN band (pass or fail directly).
    """

    pass_bound: float | None = None
    warn_bound: float | None = None
    direction: str = "lower_is_better"
    na: bool = False

    def evaluate(self, value: float) -> RuleState:
        """Evaluate a metric value against this threshold."""
        if self.na:
            return RuleState.NA

        if self.direction == "lower_is_better":
            if self.pass_bound is not None and value <= self.pass_bound:
                return RuleState.PASS
            if self.warn_bound is not None and value <= self.warn_bound:
                return RuleState.WARN
            return RuleState.FAIL

        # higher_is_better
        if self.pass_bound is not None and value >= self.pass_bound:
            return RuleState.PASS
        if self.warn_bound is not None and value >= self.warn_bound:
            return RuleState.WARN
        return RuleState.FAIL


# ---------------------------------------------------------------------------
# QualityGatePolicy — frozen threshold registry
# ---------------------------------------------------------------------------


class QualityGatePolicy:
    """Frozen registry of quality gate thresholds (14 metrics x 3 modes).

    Usage:
        policy = QualityGatePolicy()
        thresholds = policy.get_thresholds("simulation")
        result = thresholds["freshness_minutes"].evaluate(1200)
    """

    # Class-level threshold registry: (metric, mode) -> MetricThreshold
    THRESHOLDS: dict[tuple, MetricThreshold] = {
        # ===================================================================
        # SIMULATION mode
        # ===================================================================
        ("freshness_minutes", "simulation"): MetricThreshold(
            pass_bound=1440, warn_bound=4320, direction="lower_is_better"
        ),
        ("ingest_error_rate_pct_1h", "simulation"): MetricThreshold(
            pass_bound=15, warn_bound=25, direction="lower_is_better"
        ),
        ("match_coverage_pct", "simulation"): MetricThreshold(
            pass_bound=60, warn_bound=40, direction="higher_is_better"
        ),
        ("manual_source_pct", "simulation"): MetricThreshold(na=True),
        ("unmatched_points_pct", "simulation"): MetricThreshold(
            pass_bound=40, warn_bound=60, direction="lower_is_better"
        ),
        ("commissioning_all_gates_passed", "simulation"): MetricThreshold(na=True),
        ("truth_check_pass_rate_pct", "simulation"): MetricThreshold(na=True),
        ("consecutive_pass_days", "simulation"): MetricThreshold(na=True),
        ("mv_accuracy_7d_pct", "simulation"): MetricThreshold(
            pass_bound=50, warn_bound=40, direction="higher_is_better"
        ),
        ("comfort_violation_rate_7d_pct", "simulation"): MetricThreshold(
            pass_bound=20, warn_bound=35, direction="lower_is_better"
        ),
        ("rollback_rate_7d_pct", "simulation"): MetricThreshold(
            pass_bound=15, warn_bound=25, direction="lower_is_better"
        ),
        ("feedback_capture_rate_7d_pct", "simulation"): MetricThreshold(
            pass_bound=70, warn_bound=50, direction="higher_is_better"
        ),
        ("label_lag_p95_hours", "simulation"): MetricThreshold(
            pass_bound=72, warn_bound=120, direction="lower_is_better"
        ),
        ("drift_critical_alerts_24h", "simulation"): MetricThreshold(
            pass_bound=2, warn_bound=None, direction="lower_is_better"
        ),
        # ===================================================================
        # SHADOW_LIVE mode
        # ===================================================================
        ("freshness_minutes", "shadow_live"): MetricThreshold(
            pass_bound=120, warn_bound=360, direction="lower_is_better"
        ),
        ("ingest_error_rate_pct_1h", "shadow_live"): MetricThreshold(
            pass_bound=3, warn_bound=5, direction="lower_is_better"
        ),
        ("match_coverage_pct", "shadow_live"): MetricThreshold(
            pass_bound=90, warn_bound=80, direction="higher_is_better"
        ),
        ("manual_source_pct", "shadow_live"): MetricThreshold(
            pass_bound=0, warn_bound=None, direction="lower_is_better"
        ),
        ("unmatched_points_pct", "shadow_live"): MetricThreshold(
            pass_bound=10, warn_bound=20, direction="lower_is_better"
        ),
        ("commissioning_all_gates_passed", "shadow_live"): MetricThreshold(
            pass_bound=1, warn_bound=None, direction="higher_is_better"
        ),
        ("truth_check_pass_rate_pct", "shadow_live"): MetricThreshold(
            pass_bound=98, warn_bound=95, direction="higher_is_better"
        ),
        ("consecutive_pass_days", "shadow_live"): MetricThreshold(
            pass_bound=2, warn_bound=1, direction="higher_is_better"
        ),
        ("mv_accuracy_7d_pct", "shadow_live"): MetricThreshold(
            pass_bound=75, warn_bound=65, direction="higher_is_better"
        ),
        ("comfort_violation_rate_7d_pct", "shadow_live"): MetricThreshold(
            pass_bound=8, warn_bound=12, direction="lower_is_better"
        ),
        ("rollback_rate_7d_pct", "shadow_live"): MetricThreshold(
            pass_bound=5, warn_bound=8, direction="lower_is_better"
        ),
        ("feedback_capture_rate_7d_pct", "shadow_live"): MetricThreshold(
            pass_bound=90, warn_bound=80, direction="higher_is_better"
        ),
        ("label_lag_p95_hours", "shadow_live"): MetricThreshold(
            pass_bound=24, warn_bound=36, direction="lower_is_better"
        ),
        ("drift_critical_alerts_24h", "shadow_live"): MetricThreshold(
            pass_bound=0, warn_bound=1, direction="lower_is_better"
        ),
        # ===================================================================
        # LIVE_CONTROL mode
        # ===================================================================
        ("freshness_minutes", "live_control"): MetricThreshold(
            pass_bound=15, warn_bound=60, direction="lower_is_better"
        ),
        ("ingest_error_rate_pct_1h", "live_control"): MetricThreshold(
            pass_bound=1, warn_bound=2, direction="lower_is_better"
        ),
        ("match_coverage_pct", "live_control"): MetricThreshold(
            pass_bound=98, warn_bound=95, direction="higher_is_better"
        ),
        ("manual_source_pct", "live_control"): MetricThreshold(
            pass_bound=0, warn_bound=None, direction="lower_is_better"
        ),
        ("unmatched_points_pct", "live_control"): MetricThreshold(
            pass_bound=2, warn_bound=5, direction="lower_is_better"
        ),
        ("commissioning_all_gates_passed", "live_control"): MetricThreshold(
            pass_bound=1, warn_bound=None, direction="higher_is_better"
        ),
        ("truth_check_pass_rate_pct", "live_control"): MetricThreshold(
            pass_bound=98, warn_bound=None, direction="higher_is_better"
        ),
        ("consecutive_pass_days", "live_control"): MetricThreshold(
            pass_bound=2, warn_bound=None, direction="higher_is_better"
        ),
        ("mv_accuracy_7d_pct", "live_control"): MetricThreshold(
            pass_bound=85, warn_bound=75, direction="higher_is_better"
        ),
        ("comfort_violation_rate_7d_pct", "live_control"): MetricThreshold(
            pass_bound=3, warn_bound=5, direction="lower_is_better"
        ),
        ("rollback_rate_7d_pct", "live_control"): MetricThreshold(
            pass_bound=2, warn_bound=4, direction="lower_is_better"
        ),
        ("feedback_capture_rate_7d_pct", "live_control"): MetricThreshold(
            pass_bound=97, warn_bound=93, direction="higher_is_better"
        ),
        ("label_lag_p95_hours", "live_control"): MetricThreshold(
            pass_bound=6, warn_bound=12, direction="lower_is_better"
        ),
        ("drift_critical_alerts_24h", "live_control"): MetricThreshold(
            pass_bound=0, warn_bound=None, direction="lower_is_better"
        ),
        # ===================================================================
        # COMMISSIONING mode — lenient (system is learning)
        # ===================================================================
        ("freshness_minutes", "commissioning"): MetricThreshold(
            pass_bound=1440, warn_bound=4320, direction="lower_is_better"
        ),
        ("ingest_error_rate_pct_1h", "commissioning"): MetricThreshold(
            pass_bound=15, warn_bound=25, direction="lower_is_better"
        ),
        ("match_coverage_pct", "commissioning"): MetricThreshold(
            pass_bound=60, warn_bound=40, direction="higher_is_better"
        ),
        ("manual_source_pct", "commissioning"): MetricThreshold(na=True),
        ("unmatched_points_pct", "commissioning"): MetricThreshold(
            pass_bound=40, warn_bound=60, direction="lower_is_better"
        ),
        ("commissioning_all_gates_passed", "commissioning"): MetricThreshold(na=True),
        ("truth_check_pass_rate_pct", "commissioning"): MetricThreshold(na=True),
        ("consecutive_pass_days", "commissioning"): MetricThreshold(na=True),
        ("mv_accuracy_7d_pct", "commissioning"): MetricThreshold(
            pass_bound=50, warn_bound=40, direction="higher_is_better"
        ),
        ("comfort_violation_rate_7d_pct", "commissioning"): MetricThreshold(
            pass_bound=20, warn_bound=35, direction="lower_is_better"
        ),
        ("rollback_rate_7d_pct", "commissioning"): MetricThreshold(na=True),
        ("feedback_capture_rate_7d_pct", "commissioning"): MetricThreshold(
            pass_bound=70, warn_bound=50, direction="higher_is_better"
        ),
        ("label_lag_p95_hours", "commissioning"): MetricThreshold(
            pass_bound=72, warn_bound=120, direction="lower_is_better"
        ),
        ("drift_critical_alerts_24h", "commissioning"): MetricThreshold(
            pass_bound=2, warn_bound=None, direction="lower_is_better"
        ),
        # ===================================================================
        # ADVISORY mode — moderate (recommendations visible, no auto-control)
        # ===================================================================
        ("freshness_minutes", "advisory"): MetricThreshold(pass_bound=240, warn_bound=720, direction="lower_is_better"),
        ("ingest_error_rate_pct_1h", "advisory"): MetricThreshold(
            pass_bound=5, warn_bound=10, direction="lower_is_better"
        ),
        ("match_coverage_pct", "advisory"): MetricThreshold(pass_bound=80, warn_bound=65, direction="higher_is_better"),
        ("manual_source_pct", "advisory"): MetricThreshold(pass_bound=5, warn_bound=10, direction="lower_is_better"),
        ("unmatched_points_pct", "advisory"): MetricThreshold(
            pass_bound=20, warn_bound=35, direction="lower_is_better"
        ),
        ("commissioning_all_gates_passed", "advisory"): MetricThreshold(
            pass_bound=1, warn_bound=None, direction="higher_is_better"
        ),
        ("truth_check_pass_rate_pct", "advisory"): MetricThreshold(na=True),
        ("consecutive_pass_days", "advisory"): MetricThreshold(na=True),
        ("mv_accuracy_7d_pct", "advisory"): MetricThreshold(pass_bound=65, warn_bound=55, direction="higher_is_better"),
        ("comfort_violation_rate_7d_pct", "advisory"): MetricThreshold(
            pass_bound=12, warn_bound=20, direction="lower_is_better"
        ),
        ("rollback_rate_7d_pct", "advisory"): MetricThreshold(na=True),
        ("feedback_capture_rate_7d_pct", "advisory"): MetricThreshold(
            pass_bound=75, warn_bound=60, direction="higher_is_better"
        ),
        ("label_lag_p95_hours", "advisory"): MetricThreshold(pass_bound=48, warn_bound=72, direction="lower_is_better"),
        ("drift_critical_alerts_24h", "advisory"): MetricThreshold(
            pass_bound=1, warn_bound=3, direction="lower_is_better"
        ),
        # ===================================================================
        # SUPERVISED mode — fairly strict (human-in-loop, active control)
        # ===================================================================
        ("freshness_minutes", "supervised"): MetricThreshold(pass_bound=30, warn_bound=90, direction="lower_is_better"),
        ("ingest_error_rate_pct_1h", "supervised"): MetricThreshold(
            pass_bound=2, warn_bound=4, direction="lower_is_better"
        ),
        ("match_coverage_pct", "supervised"): MetricThreshold(
            pass_bound=95, warn_bound=90, direction="higher_is_better"
        ),
        ("manual_source_pct", "supervised"): MetricThreshold(
            pass_bound=0, warn_bound=None, direction="lower_is_better"
        ),
        ("unmatched_points_pct", "supervised"): MetricThreshold(
            pass_bound=5, warn_bound=10, direction="lower_is_better"
        ),
        ("commissioning_all_gates_passed", "supervised"): MetricThreshold(
            pass_bound=1, warn_bound=None, direction="higher_is_better"
        ),
        ("truth_check_pass_rate_pct", "supervised"): MetricThreshold(
            pass_bound=98, warn_bound=95, direction="higher_is_better"
        ),
        ("consecutive_pass_days", "supervised"): MetricThreshold(na=True),
        ("mv_accuracy_7d_pct", "supervised"): MetricThreshold(
            pass_bound=80, warn_bound=70, direction="higher_is_better"
        ),
        ("comfort_violation_rate_7d_pct", "supervised"): MetricThreshold(
            pass_bound=5, warn_bound=8, direction="lower_is_better"
        ),
        ("rollback_rate_7d_pct", "supervised"): MetricThreshold(
            pass_bound=3, warn_bound=5, direction="lower_is_better"
        ),
        ("feedback_capture_rate_7d_pct", "supervised"): MetricThreshold(
            pass_bound=95, warn_bound=85, direction="higher_is_better"
        ),
        ("label_lag_p95_hours", "supervised"): MetricThreshold(
            pass_bound=12, warn_bound=24, direction="lower_is_better"
        ),
        ("drift_critical_alerts_24h", "supervised"): MetricThreshold(
            pass_bound=0, warn_bound=1, direction="lower_is_better"
        ),
        # ===================================================================
        # AUTOMATIC mode — strictest (full autonomy)
        # ===================================================================
        ("freshness_minutes", "automatic"): MetricThreshold(pass_bound=15, warn_bound=60, direction="lower_is_better"),
        ("ingest_error_rate_pct_1h", "automatic"): MetricThreshold(
            pass_bound=1, warn_bound=2, direction="lower_is_better"
        ),
        ("match_coverage_pct", "automatic"): MetricThreshold(
            pass_bound=98, warn_bound=95, direction="higher_is_better"
        ),
        ("manual_source_pct", "automatic"): MetricThreshold(pass_bound=0, warn_bound=None, direction="lower_is_better"),
        ("unmatched_points_pct", "automatic"): MetricThreshold(pass_bound=2, warn_bound=5, direction="lower_is_better"),
        ("commissioning_all_gates_passed", "automatic"): MetricThreshold(
            pass_bound=1, warn_bound=None, direction="higher_is_better"
        ),
        ("truth_check_pass_rate_pct", "automatic"): MetricThreshold(
            pass_bound=98, warn_bound=None, direction="higher_is_better"
        ),
        ("consecutive_pass_days", "automatic"): MetricThreshold(na=True),
        ("mv_accuracy_7d_pct", "automatic"): MetricThreshold(
            pass_bound=85, warn_bound=75, direction="higher_is_better"
        ),
        ("comfort_violation_rate_7d_pct", "automatic"): MetricThreshold(
            pass_bound=3, warn_bound=5, direction="lower_is_better"
        ),
        ("rollback_rate_7d_pct", "automatic"): MetricThreshold(pass_bound=2, warn_bound=4, direction="lower_is_better"),
        ("feedback_capture_rate_7d_pct", "automatic"): MetricThreshold(
            pass_bound=97, warn_bound=93, direction="higher_is_better"
        ),
        ("label_lag_p95_hours", "automatic"): MetricThreshold(pass_bound=6, warn_bound=12, direction="lower_is_better"),
        ("drift_critical_alerts_24h", "automatic"): MetricThreshold(
            pass_bound=0, warn_bound=None, direction="lower_is_better"
        ),
    }

    # All 14 metric names (ordered for consistent iteration)
    METRIC_NAMES: list[str] = [
        "freshness_minutes",
        "ingest_error_rate_pct_1h",
        "match_coverage_pct",
        "manual_source_pct",
        "unmatched_points_pct",
        "commissioning_all_gates_passed",
        "truth_check_pass_rate_pct",
        "consecutive_pass_days",
        "mv_accuracy_7d_pct",
        "comfort_violation_rate_7d_pct",
        "rollback_rate_7d_pct",
        "feedback_capture_rate_7d_pct",
        "label_lag_p95_hours",
        "drift_critical_alerts_24h",
    ]

    MODES: list[str] = [
        "simulation",
        "commissioning",
        "shadow_live",
        "advisory",
        "supervised",
        "automatic",
        "live_control",
    ]

    def get_thresholds(self, mode: str) -> dict[str, MetricThreshold]:
        """Get all 14 metric thresholds for a given mode.

        Args:
            mode: One of 'simulation', 'shadow_live', 'live_control'

        Returns:
            Dict mapping metric name to MetricThreshold
        """
        return {name: self.THRESHOLDS[(name, mode)] for name in self.METRIC_NAMES if (name, mode) in self.THRESHOLDS}

    def get_metric_threshold(self, metric: str, mode: str) -> MetricThreshold:
        """Get threshold for a specific metric and mode.

        Args:
            metric: Metric name (e.g. 'freshness_minutes')
            mode: Ingestion mode (e.g. 'live_control')

        Returns:
            MetricThreshold for the given metric/mode combination

        Raises:
            KeyError: If metric/mode combination not found
        """
        key = (metric, mode)
        if key not in self.THRESHOLDS:
            raise KeyError(f"No threshold defined for metric={metric}, mode={mode}")
        return self.THRESHOLDS[key]


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass
class MetricRuleResult:
    """Evaluation result for a single metric."""

    metric: str
    value: float
    state: RuleState
    threshold: MetricThreshold
    reason_code: ReasonCode | None = None


@dataclass
class QualityGateResult:
    """Aggregate result of evaluating all quality gate metrics."""

    overall: GateStatus
    rule_results: list[MetricRuleResult]
    failed_rules: list[str]
    warn_rules: list[str]
    enforcement: EnforcementAction
    reason_codes: list[ReasonCode]
    mode: str
    evaluated_at: str = ""

    def __post_init__(self):
        if not self.evaluated_at:
            self.evaluated_at = datetime.utcnow().isoformat()
