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

import asyncio
import logging
from datetime import datetime

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
_SIMULATION_DEFAULTS: dict[str, float] = {
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

_LIVE_DEFAULTS: dict[str, float] = {
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
_ENFORCEMENT_MAP: dict[tuple, EnforcementAction] = {
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

    _last_audit_signature: str | None = None
    _last_audit_logged_at: datetime | None = None
    _audit_heartbeat_minutes: int = 60

    def __init__(self) -> None:
        self._policy = QualityGatePolicy()

    def evaluate(self, mode: str, metrics: dict[str, float], site_id: str = "unknown") -> QualityGateResult:
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
                sentinel_quality_gate_enforcement,
                sentinel_quality_gate_evaluations_total,
            )

            sentinel_quality_gate_evaluations_total.labels(site_id=site_id, status=result.overall.value).inc()

            # Set active enforcement level to 1, others to 0
            for level in ("normal", "cap_confidence", "suppress_tier3", "block_writes"):
                sentinel_quality_gate_enforcement.labels(site_id=site_id, enforcement=level).set(
                    1 if result.enforcement.value == level else 0
                )
        except Exception:
            pass  # Metrics are best-effort, never block business logic

        # Phase 160: Per-rule governance metrics
        try:
            from app.services.governance_metrics_collector import governance_metrics

            for rule_result in rule_results:
                governance_metrics.record_quality_gate_rule(rule_result.metric, rule_result.state.value)
        except Exception:
            pass

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

    async def collect_metrics(self, site_id: str | None = None) -> dict[str, float]:
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
        metrics: dict[str, float] = dict(defaults)

        # Fail-closed: no site_id in live modes means all metrics stay at FAIL defaults
        if not site_id and not is_simulation:
            logger.warning("collect_metrics called without site_id in live mode — fail-closed")
            return metrics

        # Collect from all sources concurrently with individual timeouts.
        # Each source is independent — one failure must not block others.
        # Uses asyncio.wait_for per source (3-5s timeout each).

        async def _collect_monitoring():
            from app.services.monitoring_service import MonitoringService

            monitoring = MonitoringService()
            snapshot = await asyncio.wait_for(monitoring.get_snapshot(site_id=site_id), timeout=5.0)
            metrics["freshness_minutes"] = snapshot.ingestion.freshness_hours * 60.0
            metrics["ingest_error_rate_pct_1h"] = snapshot.ingestion.error_rate * 100.0
            # match_coverage is already a percentage (0-100) from MonitoringService
            metrics["match_coverage_pct"] = snapshot.ingestion.match_coverage
            metrics["unmatched_points_pct"] = 100.0 - snapshot.ingestion.match_coverage
            prov = snapshot.ingestion.provenance_summary
            live_count = prov.get("live_protocol", 0)
            manual_count = prov.get("file_manual", 0)
            total_sources = live_count + manual_count
            if total_sources > 0:
                metrics["manual_source_pct"] = (manual_count / total_sources) * 100.0
            else:
                metrics["manual_source_pct"] = 0.0
            if snapshot.commissioning is not None:
                metrics["commissioning_all_gates_passed"] = 1.0 if snapshot.commissioning.all_gates_passed else 0.0
                metrics["consecutive_pass_days"] = float(snapshot.commissioning.consecutive_pass_days)

        async def _collect_truth_check():
            from app.services.commissioning_service import CommissioningService

            comm_svc = CommissioningService()
            if hasattr(comm_svc, "_truth_checks") and site_id:
                truth_data = comm_svc._truth_checks.get(site_id)
                if truth_data is not None:
                    # TruthCheckResult object — use agreement_pct directly
                    agreement_pct = getattr(truth_data, "agreement_pct", None)
                    if agreement_pct is not None:
                        metrics["truth_check_pass_rate_pct"] = agreement_pct

        async def _collect_mv():
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

        async def _collect_ml_feedback():
            from app.services.ml_feedback_service import MLFeedbackService

            fb_svc = MLFeedbackService()
            fb_summary = fb_svc.get_feedback_summary()
            total_records = fb_summary.total_feedback_records
            predictions_evaluated = fb_summary.predictions_evaluated
            if predictions_evaluated > 0:
                metrics["feedback_capture_rate_7d_pct"] = min(
                    (total_records / max(predictions_evaluated, 1)) * 100.0, 100.0
                )
            if fb_summary.avg_prediction_accuracy > 0:
                metrics["label_lag_p95_hours"] = max(1.0, 48.0 * (1.0 - fb_summary.avg_prediction_accuracy))

        async def _collect_drift_alerts():
            from datetime import timedelta

            from app.services.audit_logger import AuditLogger

            audit = AuditLogger()
            cutoff = datetime.now() - timedelta(hours=24)
            entries = audit.get_logs(start_time=cutoff, limit=500)
            drift_count = sum(
                1
                for e in entries
                if e.metadata.get("event_type") == "drift_critical"
                or (hasattr(e, "action") and "drift" in str(getattr(e, "action", "")).lower())
            )
            metrics["drift_critical_alerts_24h"] = float(drift_count)

        # Run all collectors concurrently; each wrapped in try/except
        collectors = [
            ("monitoring", _collect_monitoring),
            ("truth_check", _collect_truth_check),
            ("mv_verification", _collect_mv),
            ("ml_feedback", _collect_ml_feedback),
            ("drift_alerts", _collect_drift_alerts),
        ]

        async def _safe_collect(name: str, coro_fn):
            try:
                await asyncio.wait_for(coro_fn(), timeout=5.0)
            except TimeoutError:
                logger.warning(f"Quality gate collector '{name}' timed out (5s)")
            except Exception as e:
                logger.warning(f"Failed to collect {name} metrics: {e}")

        await asyncio.gather(*[_safe_collect(name, fn) for name, fn in collectors])

        return metrics

    def _audit_log(self, result: QualityGateResult) -> None:
        """Log quality gate evaluation to audit trail."""
        try:
            from app.services.audit_logger import AuditLogger

            audit = AuditLogger()
            from app.models.audit_log import AuditResultType

            # Collapse repetitive quality-gate logs unless state meaningfully changes.
            signature = (
                f"{result.mode}|{result.overall.value}|{result.enforcement.value}|"
                f"{','.join(sorted(result.failed_rules))}|{','.join(sorted(result.warn_rules))}"
            )
            now = datetime.utcnow()
            if (
                self.__class__._last_audit_signature == signature
                and self.__class__._last_audit_logged_at is not None
                and (now - self.__class__._last_audit_logged_at).total_seconds()
                < self.__class__._audit_heartbeat_minutes * 60
            ):
                return

            # Do not mark non-blocking quality gate outcomes as hard failures.
            if result.overall == GateStatus.PASS:
                audit_result = AuditResultType.SUCCESS
            elif result.enforcement.value == "block_writes":
                audit_result = AuditResultType.FAILED
            else:
                audit_result = AuditResultType.WARNING

            detail = (
                f"Quality gate {result.overall.value}; enforcement={result.enforcement.value}; "
                f"failed_rules={len(result.failed_rules)}; warn_rules={len(result.warn_rules)}"
            )
            audit.log_system_event(
                event_type="quality_gate_evaluated",
                user="system",
                result=audit_result,
                error_message=detail if audit_result != AuditResultType.SUCCESS else None,
                metadata={
                    "mode": result.mode,
                    "overall": result.overall.value,
                    "enforcement": result.enforcement.value,
                    "failed_rules": result.failed_rules,
                    "warn_rules": result.warn_rules,
                    "reason_codes": [rc.value for rc in result.reason_codes],
                },
            )
            self.__class__._last_audit_signature = signature
            self.__class__._last_audit_logged_at = now
        except Exception as e:
            logger.debug(f"Failed to audit log quality gate evaluation: {e}")
