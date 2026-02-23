"""Quality Gate Evaluator Service — Phase 109: Recommendation Quality Gate.

Evaluates collected metrics against QualityGatePolicy thresholds and returns
enforcement actions. Collects metrics from existing services:
- MonitoringService (freshness, error rate, match coverage, provenance)
- CommissioningService (gates, truth check, consecutive pass days)
- MVVerificationService (accuracy, rollback, comfort violations)
- MLFeedbackService (feedback capture rate, label lag)
- MLOps alerts (drift critical alerts)

The evaluator never recomputes metrics — it aggregates from existing services.
"""

import logging
from datetime import datetime
from typing import Dict, Optional

from app.services.quality_gate_policy import (
    METRIC_REASON_CODES,
    EnforcementAction,
    GateStatus,
    MetricRuleResult,
    QualityGatePolicy,
    QualityGateResult,
    ReasonCode,
    RuleState,
)

logger = logging.getLogger(__name__)

# Confidence cap for CAP_CONFIDENCE enforcement
CONFIDENCE_CAP = 0.59

# Default metric values per mode category.
# simulation defaults produce PASS (lenient).
# live defaults produce FAIL (fail-closed).
_SIMULATION_DEFAULTS: Dict[str, float] = {
    "freshness_minutes": 60.0,
    "ingest_error_rate_pct_1h": 0.0,
    "match_coverage_pct": 100.0,
    "manual_source_pct": 0.0,
    "unmatched_points_pct": 0.0,
    "commissioning_all_gates_passed": 1.0,
    "truth_check_pass_rate_pct": 100.0,
    "consecutive_pass_days": 10.0,
    "mv_accuracy_7d_pct": 90.0,
    "comfort_violation_rate_7d_pct": 0.0,
    "rollback_rate_7d_pct": 0.0,
    "feedback_capture_rate_7d_pct": 100.0,
    "label_lag_p95_hours": 1.0,
    "drift_critical_alerts_24h": 0.0,
}

_LIVE_DEFAULTS: Dict[str, float] = {
    "freshness_minutes": 9999.0,
    "ingest_error_rate_pct_1h": 100.0,
    "match_coverage_pct": 0.0,
    "manual_source_pct": 100.0,
    "unmatched_points_pct": 100.0,
    "commissioning_all_gates_passed": 0.0,
    "truth_check_pass_rate_pct": 0.0,
    "consecutive_pass_days": 0.0,
    "mv_accuracy_7d_pct": 0.0,
    "comfort_violation_rate_7d_pct": 100.0,
    "rollback_rate_7d_pct": 100.0,
    "feedback_capture_rate_7d_pct": 0.0,
    "label_lag_p95_hours": 9999.0,
    "drift_critical_alerts_24h": 100.0,
}

# Enforcement mapping: (mode, gate_status) -> EnforcementAction
_ENFORCEMENT_MAP: Dict[tuple, EnforcementAction] = {
    ("simulation", GateStatus.PASS): EnforcementAction.NORMAL,
    ("simulation", GateStatus.WARN): EnforcementAction.NORMAL,
    ("simulation", GateStatus.FAIL): EnforcementAction.CAP_CONFIDENCE,
    ("shadow_live", GateStatus.PASS): EnforcementAction.NORMAL,
    ("shadow_live", GateStatus.WARN): EnforcementAction.NORMAL,
    ("shadow_live", GateStatus.FAIL): EnforcementAction.SUPPRESS_TIER3,
    ("live_control", GateStatus.PASS): EnforcementAction.NORMAL,
    ("live_control", GateStatus.WARN): EnforcementAction.SUPPRESS_TIER3,
    ("live_control", GateStatus.FAIL): EnforcementAction.BLOCK_WRITES,
}


class QualityGateEvaluator:
    """Evaluates quality gate metrics and determines enforcement actions.

    Usage:
        evaluator = QualityGateEvaluator()
        metrics = await evaluator.collect_metrics("S002")
        result = evaluator.evaluate("simulation", metrics)
        recommendation = evaluator.apply_enforcement(result, recommendation)
    """

    def __init__(self) -> None:
        self._policy = QualityGatePolicy()

    def evaluate(self, mode: str, metrics: Dict[str, float], site_id: str = "unknown") -> QualityGateResult:
        """Evaluate metrics against quality gate thresholds for a mode.

        Pure function — no IO. Takes pre-collected metrics and returns
        the overall gate status with enforcement action.

        Args:
            mode: Ingestion mode ('simulation', 'shadow_live', 'live_control')
            metrics: Dict of metric_name -> float value
            site_id: Site identifier for Prometheus metric labels

        Returns:
            QualityGateResult with overall status, per-metric results, and enforcement
        """
        thresholds = self._policy.get_thresholds(mode)
        rule_results: list[MetricRuleResult] = []
        failed_rules: list[str] = []
        warn_rules: list[str] = []
        reason_codes: list[ReasonCode] = []

        for metric_name, threshold in thresholds.items():
            value = metrics.get(metric_name, 0.0)
            state = threshold.evaluate(value)

            # Determine reason code (only for failures)
            reason_code = None
            if state == RuleState.FAIL:
                reason_code = METRIC_REASON_CODES.get(metric_name, ReasonCode.QUALITY_GATE_BLOCK)
                failed_rules.append(metric_name)
                reason_codes.append(reason_code)
            elif state == RuleState.WARN:
                warn_rules.append(metric_name)

            rule_results.append(
                MetricRuleResult(
                    metric=metric_name,
                    value=value,
                    state=state,
                    threshold=threshold,
                    reason_code=reason_code,
                )
            )

        # Overall gate: FAIL if any fail, WARN if any warn + zero fail, else PASS
        if failed_rules:
            overall = GateStatus.FAIL
        elif warn_rules:
            overall = GateStatus.WARN
        else:
            overall = GateStatus.PASS

        # Enforcement by mode + gate status
        enforcement = _ENFORCEMENT_MAP.get((mode, overall), EnforcementAction.NORMAL)

        result = QualityGateResult(
            overall=overall,
            rule_results=rule_results,
            failed_rules=failed_rules,
            warn_rules=warn_rules,
            enforcement=enforcement,
            reason_codes=reason_codes,
            mode=mode,
        )

        # Audit log
        self._audit_log(result)

        # Prometheus metrics instrumentation (best-effort, never blocks business logic)
        try:
            from app.api.metrics import (
                sentinel_quality_gate_evaluations_total,
                sentinel_quality_gate_enforcement,
            )

            sentinel_quality_gate_evaluations_total.labels(site_id=site_id, status=result.overall.value).inc()

            # Set active enforcement level to 1, others to 0
            for level in ("normal", "cap_confidence", "suppress_tier3", "block_writes"):
                sentinel_quality_gate_enforcement.labels(site_id=site_id, enforcement=level).set(
                    1 if result.enforcement.value == level else 0
                )
        except Exception:
            pass  # Metrics are best-effort, never block business logic

        return result

    def apply_enforcement(self, result: QualityGateResult, recommendation: dict) -> dict:
        """Apply enforcement action to a recommendation dict.

        Modifies the recommendation in-place and returns it.

        Args:
            result: QualityGateResult from evaluate()
            recommendation: Recommendation dict to modify

        Returns:
            Modified recommendation dict
        """
        recommendation["quality_gate_status"] = result.overall.value
        recommendation["enforcement_action"] = result.enforcement.value

        if result.enforcement == EnforcementAction.CAP_CONFIDENCE:
            original_confidence = recommendation.get("confidence", 1.0)
            effective = min(original_confidence, CONFIDENCE_CAP)
            recommendation["effective_confidence"] = effective
            recommendation["quality_penalty"] = round(original_confidence - effective, 4)

        elif result.enforcement == EnforcementAction.SUPPRESS_TIER3:
            recommendation["max_action"] = "pending_approval"
            # Never allow auto_execute in suppressed mode
            if recommendation.get("action") == "auto_execute":
                recommendation["action"] = "pending_approval"

        elif result.enforcement == EnforcementAction.BLOCK_WRITES:
            recommendation["action"] = "log_only"
            recommendation["blocked"] = True
            recommendation["block_reasons"] = [rc.value for rc in result.reason_codes]

        return recommendation

    async def collect_metrics(self, site_id: Optional[str] = None) -> Dict[str, float]:
        """Aggregate metrics from existing services.

        Collects from MonitoringService, CommissioningService, MVVerificationService,
        MLFeedbackService, and MLOps alerts. Uses try/except per source with
        fail-closed defaults for live modes.

        Args:
            site_id: Site/building identifier. If None in live modes, all metrics
                     default to FAIL values (fail-closed).

        Returns:
            Dict of metric_name -> float value
        """
        from app.config.settings import IngestionMode, settings

        mode = settings.resolved_ingestion_mode
        is_simulation = mode == IngestionMode.SIMULATION

        # Start with defaults based on mode
        defaults = _SIMULATION_DEFAULTS if is_simulation else _LIVE_DEFAULTS
        metrics: Dict[str, float] = dict(defaults)

        # Fail-closed: no site_id in live modes means all metrics stay at FAIL defaults
        if not site_id and not is_simulation:
            logger.warning("collect_metrics called without site_id in live mode — fail-closed")
            return metrics

        # a) MonitoringService
        try:
            from app.services.monitoring_service import MonitoringService

            monitoring = MonitoringService()
            snapshot = await monitoring.get_snapshot(building_id=site_id)

            metrics["freshness_minutes"] = snapshot.ingestion.freshness_hours * 60.0
            metrics["ingest_error_rate_pct_1h"] = snapshot.ingestion.error_rate * 100.0
            metrics["match_coverage_pct"] = snapshot.ingestion.match_coverage * 100.0
            metrics["unmatched_points_pct"] = 100.0 - metrics["match_coverage_pct"]

            # Provenance: manual_source_pct
            prov = snapshot.ingestion.provenance_summary
            live_count = prov.get("live_protocol", 0)
            manual_count = prov.get("file_manual", 0)
            total_sources = live_count + manual_count
            if total_sources > 0:
                metrics["manual_source_pct"] = (manual_count / total_sources) * 100.0
            else:
                metrics["manual_source_pct"] = 0.0

            # Commissioning from snapshot
            if snapshot.commissioning is not None:
                metrics["commissioning_all_gates_passed"] = 1.0 if snapshot.commissioning.all_gates_passed else 0.0
                metrics["consecutive_pass_days"] = float(snapshot.commissioning.consecutive_pass_days)
        except Exception as e:
            logger.warning(f"Failed to collect monitoring metrics: {e}")

        # b) Truth check from CommissioningService
        try:
            from app.services.commissioning_service import CommissioningService

            comm_svc = CommissioningService()
            if hasattr(comm_svc, "_truth_checks") and site_id:
                truth_data = comm_svc._truth_checks.get(site_id)
                if truth_data and isinstance(truth_data, dict):
                    pass_rate = truth_data.get("pass_rate", 1.0)
                    metrics["truth_check_pass_rate_pct"] = pass_rate * 100.0
        except Exception as e:
            logger.debug(f"Failed to collect truth check metrics: {e}")

        # c) MVVerificationService
        try:
            from app.services.mv_verification_service import MVVerificationService

            mv_svc = MVVerificationService()
            if site_id:
                summary = mv_svc.get_verification_summary(site_id)
                avg_acc = summary.get("average_accuracy")
                if avg_acc is not None:
                    metrics["mv_accuracy_7d_pct"] = avg_acc * 100.0

                total_verifications = summary.get("total_verifications", 0)
                rollbacks = summary.get("rollbacks_recommended", 0)
                if total_verifications > 0:
                    metrics["rollback_rate_7d_pct"] = (rollbacks / total_verifications) * 100.0
                else:
                    # No verifications: use default (safe for simulation, fail for live)
                    pass
        except Exception as e:
            logger.warning(f"Failed to collect M&V metrics: {e}")

        # d) MLFeedbackService
        try:
            from app.services.ml_feedback_service import MLFeedbackService

            fb_svc = MLFeedbackService()
            fb_summary = fb_svc.get_feedback_summary()

            total_records = fb_summary.total_feedback_records
            predictions_evaluated = fb_summary.predictions_evaluated
            if predictions_evaluated > 0:
                metrics["feedback_capture_rate_7d_pct"] = min(
                    (total_records / max(predictions_evaluated, 1)) * 100.0, 100.0
                )

            # label_lag_p95_hours: estimate from avg_prediction_accuracy timing
            # Since we don't have precise timing, use a heuristic
            if fb_summary.avg_prediction_accuracy > 0:
                # Better accuracy implies tighter feedback loop
                metrics["label_lag_p95_hours"] = max(1.0, 48.0 * (1.0 - fb_summary.avg_prediction_accuracy))
        except Exception as e:
            logger.warning(f"Failed to collect ML feedback metrics: {e}")

        # e) Drift critical alerts (from audit log)
        try:
            from app.services.audit_logger import AuditLogger

            audit = AuditLogger()
            from datetime import timedelta

            cutoff = datetime.now() - timedelta(hours=24)
            entries = audit.get_logs(start_time=cutoff, limit=500)
            drift_count = sum(
                1
                for e in entries
                if e.metadata.get("event_type") == "drift_critical"
                or (hasattr(e, "action") and "drift" in str(getattr(e, "action", "")).lower())
            )
            metrics["drift_critical_alerts_24h"] = float(drift_count)
        except Exception as e:
            logger.debug(f"Failed to collect drift alert metrics: {e}")

        return metrics

    def _audit_log(self, result: QualityGateResult) -> None:
        """Log quality gate evaluation to audit trail."""
        try:
            from app.services.audit_logger import AuditLogger

            audit = AuditLogger()
            from app.models.audit_log import AuditResultType

            audit_result = AuditResultType.SUCCESS if result.overall == GateStatus.PASS else AuditResultType.FAILED
            audit.log_system_event(
                event_type="quality_gate_evaluated",
                user="system",
                result=audit_result,
                metadata={
                    "mode": result.mode,
                    "overall": result.overall.value,
                    "enforcement": result.enforcement.value,
                    "failed_rules": result.failed_rules,
                    "warn_rules": result.warn_rules,
                    "reason_codes": [rc.value for rc in result.reason_codes],
                },
            )
        except Exception as e:
            logger.debug(f"Failed to audit log quality gate evaluation: {e}")
