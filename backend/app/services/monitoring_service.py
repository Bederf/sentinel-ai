"""Monitoring Service — Phase 108: Monitoring Hardening.

Pure aggregation service. Collects KPIs from existing repos/services,
evaluates alert rules, and returns a unified MonitoringSnapshot.

Data sources:
- IntegrationRepository: quality metrics, integration health, log sources
- AuditLogger: control action counts (shadow, blocked, approved, safety)
- CommissioningService: scorecard summary
- Settings: ingestion mode

Alert deduplication:
- stale_data, high_error_rate, low_coverage alerts are consumed from
  integration health (already generated in api/integration.py:620-678).
- Only json_in_live and truth_check_fail are evaluated here (new rules).
- 10-minute cooldown per rule to prevent spam.
"""

import logging
import uuid
from datetime import datetime, timedelta

from app.config.settings import IngestionMode, settings
from app.database.repositories.integration_repository import IntegrationRepository
from app.models.audit_log import AuditActionType, AuditResultType
from app.models.integration import ConnectionType
from app.models.monitoring import (
    CommissioningSnapshot,
    ControlKPIs,
    IngestionKPIs,
    MonitoringAlert,
    MonitoringSnapshot,
    TrendBucket,
)
from app.services.audit_logger import AuditLogger

logger = logging.getLogger(__name__)

# Live-protocol connection types (real BMS data)
_LIVE_PROTOCOLS = {
    ConnectionType.API.value,
    ConnectionType.SFTP.value,
    ConnectionType.DATABASE.value,
    ConnectionType.NIAGARA_BACNET.value,
}

# File/manual connection types (non-live provenance)
_FILE_MANUAL = {
    ConnectionType.FILE_DROP.value,
    ConnectionType.MANUAL_UPLOAD.value,
}


class MonitoringService:
    """Aggregates ingestion, control, and commissioning KPIs into a single snapshot."""

    # Class-level cooldown tracker: rule_id → last_fired_at
    _alert_cooldowns: dict[str, datetime] = {}
    _COOLDOWN_MINUTES = 10

    def __init__(self) -> None:
        self._integration_repo = IntegrationRepository()
        self._audit_logger = AuditLogger()

    async def get_snapshot(self, site_id: str | None = None) -> MonitoringSnapshot:
        """Build a unified monitoring snapshot."""
        mode = settings.resolved_ingestion_mode
        is_live = settings.is_live_mode

        ingestion = self._collect_ingestion_kpis(site_id)
        control = self._collect_control_kpis()
        commissioning = await self._collect_commissioning(site_id, mode)
        alerts = self._evaluate_alert_rules(ingestion, control, commissioning, mode, is_live, site_id)
        trend = self._build_trend_buckets(control)

        # Phase 109: Quality gate evaluation using already-collected KPIs
        quality_gate = self._evaluate_quality_gate(ingestion, commissioning, mode, site_id)

        return MonitoringSnapshot(
            ingestion_mode=mode.value,
            is_live=is_live,
            site_id=site_id,
            ingestion=ingestion,
            control=control,
            commissioning=commissioning,
            alerts=alerts,
            trend_24h=trend,
            checked_at=datetime.utcnow().isoformat(),
            quality_gate=quality_gate,
        )

    # ------------------------------------------------------------------
    # Ingestion KPIs
    # ------------------------------------------------------------------

    def _collect_ingestion_kpis(self, site_id: str | None = None) -> IngestionKPIs:
        """Pull quality metrics and integration health from the integration repo."""
        try:
            health = self._integration_repo.get_integration_health(site_id)
        except Exception:
            health = {
                "total_points_mapped": 0,
                "unmatched_points": 0,
            }

        total_points = health.get("total_points_mapped") or 0
        unmatched = health.get("unmatched_points") or 0

        # Quality metrics need a site_id; fall back to defaults if absent
        freshness = 9999.0
        error_rate = 0.0
        match_coverage = 0.0

        if site_id:
            try:
                qm = self._integration_repo.get_quality_metrics(site_id)
                freshness = 0.0 if qm.get("data_freshness_hours") is None else qm.get("data_freshness_hours")
                error_rate = 0.0 if qm.get("error_rate") is None else qm.get("error_rate")
                match_coverage = 0.0 if qm.get("match_coverage") is None else qm.get("match_coverage")
            except Exception:
                # Fallback: derive freshness from integration_health last_sync
                health = self._integration_repo.get_integration_health(site_id)
                last_sync = health.get("last_sync")
                if last_sync:
                    try:
                        if isinstance(last_sync, str):
                            ls_dt = datetime.fromisoformat(last_sync.replace("Z", "+00:00").replace("+00:00", ""))
                        else:
                            ls_dt = last_sync
                        # Strip tzinfo to get naive UTC datetime for consistent arithmetic
                        if ls_dt.tzinfo is not None:
                            ls_dt = ls_dt.replace(tzinfo=None)
                        freshness = (datetime.utcnow() - ls_dt).total_seconds() / 3600
                    except Exception:
                        pass
        else:
            # Global: derive match_coverage from health data
            if total_points > 0:
                matched = total_points - unmatched
                match_coverage = round(matched / total_points * 100, 1)

        provenance = self._get_provenance_summary(site_id)

        return IngestionKPIs(
            freshness_hours=round(freshness, 2),
            error_rate=round(error_rate, 2),
            unmatched_points=unmatched,
            total_points=total_points,
            match_coverage=round(match_coverage, 1),
            provenance_summary=provenance,
        )

    # ------------------------------------------------------------------
    # Control KPIs
    # ------------------------------------------------------------------

    def _collect_control_kpis(self) -> ControlKPIs:
        """Count audit log entries by result type in the last 24 hours."""
        cutoff = datetime.now() - timedelta(hours=24)

        shadow = 0
        blocked = 0
        approved = 0
        safety_violations = 0

        try:
            entries = self._audit_logger.get_logs(start_time=cutoff, limit=1000)
            for entry in entries:
                if entry.result == AuditResultType.SHADOW:
                    shadow += 1
                elif entry.result == AuditResultType.BLOCKED:
                    blocked += 1
                elif entry.result == AuditResultType.SUCCESS and entry.action == AuditActionType.DEVICE_CONTROL:
                    approved += 1

                if entry.action == AuditActionType.SAFETY_VALIDATION and entry.result == AuditResultType.FAILED:
                    # Only count CRITICAL-level safety rejections as violations for policy gating.
                    # WARNING-level and older entries (escalation_level=None) are excluded.
                    if entry.escalation_level and entry.escalation_level.lower() == "critical":
                        safety_violations += 1
        except Exception as e:
            logger.warning(f"Failed to collect control KPIs from audit log: {e}")

        return ControlKPIs(
            shadow_writes_24h=shadow,
            blocked_writes_24h=blocked,
            approved_writes_24h=approved,
            safety_violations_24h=safety_violations,
        )

    # ------------------------------------------------------------------
    # Commissioning
    # ------------------------------------------------------------------

    async def _collect_commissioning(
        self,
        site_id: str | None,
        mode: IngestionMode,
    ) -> CommissioningSnapshot | None:
        """Run commissioning scorecard if not in SIMULATION mode.

        Per adjustment #3: if is_live_mode and site_id is missing,
        return None (don't silently run commissioning on None).
        """
        if mode == IngestionMode.SIMULATION:
            return None

        if not site_id:
            return None

        try:
            from app.services.commissioning_service import CommissioningService

            svc = CommissioningService()
            scorecard = await svc.run_scorecard(site_id)

            gates_passed = sum(1 for g in scorecard.gates if g.passed)
            gates_total = len(scorecard.gates)
            blocking = [g.id.value for g in scorecard.gates if not g.passed]

            return CommissioningSnapshot(
                gates_passed=gates_passed,
                gates_total=gates_total,
                all_gates_passed=scorecard.all_gates_passed,
                consecutive_pass_days=scorecard.consecutive_pass_days,
                can_promote=scorecard.can_promote,
                blocking_gates=blocking,
            )
        except Exception as e:
            logger.warning(f"Failed to collect commissioning snapshot: {e}")
            return None

    # ------------------------------------------------------------------
    # Alert rules
    # ------------------------------------------------------------------

    def _evaluate_alert_rules(
        self,
        ingestion: IngestionKPIs,
        control: ControlKPIs,
        commissioning: CommissioningSnapshot | None,
        mode: IngestionMode,
        is_live: bool,
        site_id: str | None = None,
    ) -> list[MonitoringAlert]:
        """Evaluate monitoring alert rules.

        Consumes existing integration health alerts (stale_data, high_error_rate,
        low_coverage) instead of re-evaluating them. Only evaluates the 2 new rules:
        - json_in_live: file/manual provenance detected in live mode
        - truth_check_fail: can't promote despite consecutive pass days
        """
        alerts: list[MonitoringAlert] = []
        now = datetime.utcnow()

        # Pull existing integration health alerts (dedup adjustment #6)
        try:
            health = self._integration_repo.get_integration_health(site_id)
            # Re-create the same alert logic from api/integration.py
            # to surface them in our snapshot without calling the API endpoint
            self._import_integration_alerts(alerts, health, now)
        except Exception as e:
            logger.debug(f"Could not pull integration health alerts: {e}")

        # Rule: json_in_live — file/manual provenance in live mode
        if is_live and ingestion.provenance_summary.get("file_manual", 0) > 0:
            self._maybe_add_alert(
                alerts,
                rule="json_in_live",
                severity="critical",
                message=(
                    f"File/manual data sources detected in {mode.value} mode. "
                    f"{ingestion.provenance_summary['file_manual']} source(s) "
                    f"using non-live provenance."
                ),
                now=now,
            )

        # Rule: truth_check_fail — can't promote despite meeting day threshold
        if commissioning is not None and not commissioning.can_promote and commissioning.consecutive_pass_days >= 2:
            self._maybe_add_alert(
                alerts,
                rule="truth_check_fail",
                severity="warning",
                message=(
                    f"Commissioning has {commissioning.consecutive_pass_days} "
                    f"consecutive pass days but cannot promote. "
                    f"Blocking gates: {', '.join(commissioning.blocking_gates) or 'truth check'}."
                ),
                now=now,
            )

        return alerts

    def _import_integration_alerts(
        self,
        alerts: list[MonitoringAlert],
        health: dict,
        now: datetime,
    ) -> None:
        """Import stale_data, high_error_rate, low_coverage from integration health data.

        Mirrors the logic in api/integration.py:620-678 but with cooldown.
        """
        # Stale data
        last_sync = health.get("last_sync")
        if last_sync:
            try:
                if isinstance(last_sync, str):
                    ls_dt = datetime.fromisoformat(last_sync.replace("Z", "+00:00").replace("+00:00", ""))
                else:
                    ls_dt = last_sync
                if ls_dt.tzinfo is not None:
                    ls_dt = ls_dt.replace(tzinfo=None)
                hours_since = (datetime.utcnow() - ls_dt).total_seconds() / 3600
                if hours_since > 24:
                    severity = "critical" if hours_since >= 48 else "warning"
                    self._maybe_add_alert(
                        alerts,
                        rule="stale_data",
                        severity=severity,
                        message=f"Data is {int(hours_since)} hours old.",
                        now=now,
                    )
            except (ValueError, TypeError):
                pass

        # High error rate
        errors = health.get("recent_errors_count", 0)
        active = health.get("active_sources", 0)
        if errors > 0 and active > 0:
            ratio = errors / active
            if ratio > 0.1:
                severity = "critical" if ratio >= 0.25 else "warning"
                self._maybe_add_alert(
                    alerts,
                    rule="high_error_rate",
                    severity=severity,
                    message=f"{errors} sync failures in the last 24 hours.",
                    now=now,
                )

        # Low match coverage
        total = health.get("total_points_mapped", 0)
        unmatched = health.get("unmatched_points", 0)
        if total > 0:
            match_rate = (total - unmatched) / total * 100
            if match_rate < 50:
                severity = "critical" if match_rate < 25 else "warning"
                self._maybe_add_alert(
                    alerts,
                    rule="low_coverage",
                    severity=severity,
                    message=f"Match coverage is {match_rate:.0f}%. {unmatched} points unmatched.",
                    now=now,
                )

    def _maybe_add_alert(
        self,
        alerts: list[MonitoringAlert],
        rule: str,
        severity: str,
        message: str,
        now: datetime,
    ) -> None:
        """Add alert only if cooldown window has elapsed for this rule."""
        last_fired = self._alert_cooldowns.get(rule)
        if last_fired and (now - last_fired).total_seconds() < self._COOLDOWN_MINUTES * 60:
            return

        self._alert_cooldowns[rule] = now
        alerts.append(
            MonitoringAlert(
                id=str(uuid.uuid4()),
                rule=rule,
                severity=severity,
                message=message,
                timestamp=now.isoformat(),
            )
        )

    # ------------------------------------------------------------------
    # Trend buckets
    # ------------------------------------------------------------------

    def _build_trend_buckets(self, control: ControlKPIs) -> list[TrendBucket]:
        """Generate 24 hourly trend buckets.

        Shadow writes are binned by hour from audit log.
        Freshness/error_rate are repeated from current values (no per-bucket
        time-series storage yet), so `derived=True` marks those fields.
        """
        now = datetime.utcnow()
        cutoff = now - timedelta(hours=24)

        # Bin shadow writes by hour
        shadow_by_hour: dict[str, int] = {}
        try:
            entries = self._audit_logger.get_logs(start_time=cutoff, limit=1000)
            for entry in entries:
                if entry.result == AuditResultType.SHADOW:
                    hour_key = entry.timestamp.strftime("%Y-%m-%dT%H:00:00")
                    shadow_by_hour[hour_key] = shadow_by_hour.get(hour_key, 0) + 1
        except Exception:
            pass

        buckets: list[TrendBucket] = []
        for i in range(24):
            bucket_time = cutoff + timedelta(hours=i)
            hour_key = bucket_time.strftime("%Y-%m-%dT%H:00:00")
            buckets.append(
                TrendBucket(
                    hour=hour_key,
                    freshness_hours=0.0,  # derived — no per-bucket history
                    error_rate=0.0,  # derived — no per-bucket history
                    shadow_writes=shadow_by_hour.get(hour_key, 0),
                    derived=True,
                )
            )

        return buckets

    # ------------------------------------------------------------------
    # Quality gate (Phase 109)
    # ------------------------------------------------------------------

    def _evaluate_quality_gate(
        self,
        ingestion: "IngestionKPIs",
        commissioning: "CommissioningSnapshot | None",
        mode: "IngestionMode",
        site_id: "str | None",
    ) -> dict | None:
        """Evaluate quality gate using already-collected KPIs.

        Maps existing snapshot data to the 14 quality gate metrics to avoid
        double-collecting. Returns a dict with overall status, enforcement,
        and per-rule details.
        """
        try:
            from app.services.quality_gate_evaluator import _SIMULATION_DEFAULTS, QualityGateEvaluator

            evaluator = QualityGateEvaluator()
            mode_str = mode.value

            # Map already-collected KPIs to quality gate metrics
            metrics = dict(_SIMULATION_DEFAULTS)  # start with safe defaults

            # Ingestion KPIs
            metrics["freshness_minutes"] = ingestion.freshness_hours * 60.0
            metrics["ingest_error_rate_pct_1h"] = ingestion.error_rate * 100.0
            metrics["match_coverage_pct"] = ingestion.match_coverage * 100.0
            metrics["unmatched_points_pct"] = 100.0 - metrics["match_coverage_pct"]

            # Provenance
            prov = ingestion.provenance_summary
            live_count = prov.get("live_protocol", 0)
            manual_count = prov.get("file_manual", 0)
            total_sources = live_count + manual_count
            if total_sources > 0:
                metrics["manual_source_pct"] = (manual_count / total_sources) * 100.0
            else:
                metrics["manual_source_pct"] = 0.0

            # Commissioning
            if commissioning is not None:
                metrics["commissioning_all_gates_passed"] = 1.0 if commissioning.all_gates_passed else 0.0
                metrics["consecutive_pass_days"] = float(commissioning.consecutive_pass_days)

            result = evaluator.evaluate(mode_str, metrics)

            return {
                "overall_status": result.overall.value,
                "enforcement_action": result.enforcement.value,
                "mode": mode_str,
                "failed_rules": result.failed_rules,
                "warn_rules": result.warn_rules,
                "reason_codes": [rc.value for rc in result.reason_codes],
                "evaluated_at": result.evaluated_at,
            }
        except Exception as e:
            logger.warning(f"Quality gate evaluation failed in monitoring snapshot: {e}")
            return None

    # ------------------------------------------------------------------
    # Provenance summary
    # ------------------------------------------------------------------

    def _get_provenance_summary(self, site_id: str | None = None) -> dict[str, int]:
        """Bucket log sources by connection type into live_protocol vs file_manual."""
        result = {"live_protocol": 0, "file_manual": 0}

        try:
            sources = self._integration_repo.get_log_sources(site_id=site_id, is_active=True)
            for source in sources:
                conn_type = source.get("connection_type", "")
                if conn_type in _LIVE_PROTOCOLS:
                    result["live_protocol"] += 1
                elif conn_type in _FILE_MANUAL:
                    result["file_manual"] += 1
                # Unknown types are not counted (intentional)
        except Exception as e:
            logger.debug(f"Could not query log sources for provenance: {e}")

        return result
