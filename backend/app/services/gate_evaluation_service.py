"""GateEvaluationService — single source of truth for phase promotion gates.

Queries phase_promotion_gates table, evaluates all gate types (threshold, boolean, count),
and returns pass/fail with details. Used by both:
  - PATCH /api/sites/{site_id}/phase (phase transition blocking)
  - PhasePromotionEvaluator (readiness surfacing)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from app.database.supabase_client import get_supabase_client

logger = logging.getLogger("sentinel.gate_evaluation")


@dataclass
class GateResult:
    gate_name: str
    gate_type: str
    passed: bool
    value: float | int | bool | None = None
    threshold: float | int | None = None
    operator: str | None = None
    description: str | None = None
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "rule": self.gate_name,
            "passed": self.passed,
            "value": self.value,
            "threshold": self.threshold,
            "operator": self.operator,
            "description": self.description,
            "error": self.error,
        }


@dataclass
class GateEvaluationResult:
    site_id: str
    from_phase: str
    to_phase: str
    gates_pass: bool
    results: list[GateResult] = field(default_factory=list)
    error: str | None = None


class GateEvaluationService:
    """Evaluates phase promotion gates from Supabase phase_promotion_gates table."""

    def __init__(self):
        self._supabase = None

    @property
    def supabase(self):
        if self._supabase is None:
            self._supabase = get_supabase_client()
        return self._supabase

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    async def evaluate_promotion(
        self,
        site_id: str,
        from_phase: str,
        to_phase: str,
    ) -> GateEvaluationResult:
        """Evaluate all gates for a phase transition. Returns pass/fail + details."""
        gates = self.get_promotion_gates(site_id, from_phase, to_phase)
        if not gates:
            # No gates defined = pass by default (backward compat)
            return GateEvaluationResult(
                site_id=site_id,
                from_phase=from_phase,
                to_phase=to_phase,
                gates_pass=True,
                results=[],
                error=None,
            )

        current_metrics = await self._fetch_current_metrics(site_id)
        results: list[GateResult] = []
        for gate in gates:
            result = self._evaluate_gate(gate, current_metrics)
            results.append(result)

        all_passed = all(r.passed for r in results)
        return GateEvaluationResult(
            site_id=site_id,
            from_phase=from_phase,
            to_phase=to_phase,
            gates_pass=all_passed,
            results=results,
        )

    def get_promotion_gates(
        self,
        site_id: str,
        from_phase: str,
        to_phase: str,
    ) -> list[dict[str, Any]]:
        """Fetch all enabled gates for a transition from Supabase."""
        try:
            result = (
                self.supabase.table("phase_promotion_gates")
                .select("gate_name, gate_type, threshold_value, operator, allowed_values, description")
                .eq("site_id", site_id)
                .eq("from_phase", from_phase)
                .eq("to_phase", to_phase)
                .eq("enabled", True)
                .execute()
            )
            return result.data or []
        except Exception as e:
            logger.error("Failed to fetch promotion gates for %s %s->%s: %s", site_id, from_phase, to_phase, e)
            return []

    # -------------------------------------------------------------------------
    # Gate evaluation
    # -------------------------------------------------------------------------

    def _evaluate_gate(
        self,
        gate: dict[str, Any],
        metrics: dict[str, Any],
    ) -> GateResult:
        """Evaluate a single gate against current metrics."""
        gate_name = gate["gate_name"]
        gate_type = gate["gate_type"]
        operator = gate["operator"]
        threshold = gate["threshold_value"]
        description = gate.get("description")

        try:
            current_value = self._resolve_metric(gate_name, metrics)
            passed = self._apply_operator(current_value, operator, threshold, gate.get("allowed_values"))

            return GateResult(
                gate_name=gate_name,
                gate_type=gate_type,
                passed=passed,
                value=current_value,
                threshold=threshold,
                operator=operator,
                description=description,
            )
        except Exception as e:
            logger.warning("Gate evaluation failed for %s: %s", gate_name, e)
            return GateResult(
                gate_name=gate_name,
                gate_type=gate_type,
                passed=False,
                error=str(e),
                description=description,
            )

    def _resolve_metric(self, gate_name: str, metrics: dict[str, Any]) -> float | int | bool | None:
        """Resolve a gate name to its current metric value."""
        if gate_name == "ml_hours_ingested":
            return metrics.get("ml_hours_ingested", 0.0)
        if gate_name == "bridge_connected":
            return metrics.get("bridge_connected", False)
        if gate_name == "anomaly_scores_writing":
            return metrics.get("anomaly_scores_writing", 0)
        if gate_name == "freshness_hours_max":
            return metrics.get("freshness_hours_max", 999.0)
        if gate_name == "match_coverage_min_pct":
            return metrics.get("match_coverage_min_pct", 0.0)
        if gate_name == "error_rate_max_pct":
            return metrics.get("error_rate_max_pct", 100.0)
        if gate_name == "consecutive_pass_days_min":
            return metrics.get("consecutive_pass_days_min", 0)
        if gate_name == "commissioning_all_gates_passed":
            return metrics.get("commissioning_all_gates_passed", False)
        if gate_name == "time_in_advisory_days":
            return metrics.get("time_in_advisory_days", 0)
        if gate_name == "recommendations_generated":
            return metrics.get("recommendations_generated", 0)
        if gate_name == "no_safety_violations_30d":
            return metrics.get("no_safety_violations_30d", False)
        if gate_name == "bridge_connected_uptime_pct":
            return metrics.get("bridge_connected_uptime_pct", 0.0)
        if gate_name == "approval_accuracy":
            return metrics.get("approval_accuracy", 0.0)
        if gate_name == "false_positive_rate":
            return metrics.get("false_positive_rate", 1.0)
        if gate_name == "recommendations_approved":
            return metrics.get("recommendations_approved", 0)
        if gate_name == "no_safety_violations_7d":
            return metrics.get("no_safety_violations_7d", False)
        if gate_name == "human_approved_autonomous":
            return metrics.get("human_approved_autonomous", False)
        # Unknown gate — return None (will fail with != true or >= 0)
        return None

    def _apply_operator(
        self,
        value: float | int | bool | None,
        operator: str,
        threshold: float | int | None,
        allowed_values: list[str] | None = None,
    ) -> bool:
        """Apply operator to value and threshold/allowed_values."""
        # Handle boolean operators
        if operator == "==true":
            return value is True
        if operator == "==false":
            return value is False

        # For threshold operators, None fails
        if value is None:
            return False

        # Threshold operators
        if operator == ">=":
            return float(value) >= float(threshold)
        if operator == "<=":
            return float(value) <= float(threshold)
        if operator == ">":
            return float(value) > float(threshold)
        if operator == "<":
            return float(value) < float(threshold)
        if operator == "==":
            return float(value) == float(threshold)
        if operator == "!=":
            return float(value) != float(threshold)
        if operator == "in":
            return str(value) in (allowed_values or [])

        # Count operators (value is count, threshold is minimum)
        if operator == ">" and threshold == 0:
            return int(value) > int(threshold)
        if operator == ">=":
            return float(value) >= float(threshold)

        return False

    # -------------------------------------------------------------------------
    # Metric fetching
    # -------------------------------------------------------------------------

    async def _fetch_current_metrics(self, site_id: str) -> dict[str, Any]:
        """Fetch current metric values for all gates."""
        from app.config.settings import settings
        from supabase import create_client

        client = create_client(settings.supabase_url, settings.supabase_service_role_key)

        metrics: dict[str, Any] = {}

        # Fetch site row for ml_hours_ingested + onboarding_phase (for time_in_advisory_days)
        site_row = (
            client.table("sites")
            .select("id, ml_hours_ingested, onboarding_phase, created_at")
            .eq("code", site_id)
            .limit(1)
            .execute()
        )

        if site_row.data:
            row = site_row.data[0]
            metrics["ml_hours_ingested"] = float(row.get("ml_hours_ingested") or 0.0)
            phase = row.get("onboarding_phase", "")
            metrics["time_in_advisory_days"] = self._days_in_phase(row.get("created_at"), row.get("onboarding_phase"))
            metrics["created_at"] = row.get("created_at")

        # Bridge connected — check ShadowModePollingService status
        metrics["bridge_connected"] = await self._check_bridge_connected(site_id)

        # Bridge connected uptime %
        metrics["bridge_connected_uptime_pct"] = await self._get_bridge_uptime_pct(site_id)

        # Anomaly scores writing — count in last 30 min
        metrics["anomaly_scores_writing"] = await self._count_recent_anomaly_scores(site_id, client)

        # Data freshness
        metrics["freshness_hours_max"] = await self._get_freshness_max(site_id, client)

        # Recommendations count
        site_uuid = site_row.data[0]["id"] if site_row.data else None
        metrics["recommendations_generated"] = self._count_recommendations(site_uuid, client)
        metrics["recommendations_approved"] = self._count_acknowledged_recommendations(site_uuid, client)

        # Safety violations
        metrics["no_safety_violations_30d"] = await self._check_no_safety_violations(site_id, days=30, client=client)
        metrics["no_safety_violations_7d"] = await self._check_no_safety_violations(site_id, days=7, client=client)

        # Adapter error rate
        metrics["error_rate_max_pct"] = await self._get_adapter_error_rate(site_id, client)

        # Match coverage
        metrics["match_coverage_min_pct"] = await self._get_match_coverage(site_id, client)

        # Consecutive pass days
        metrics["consecutive_pass_days_min"] = await self._get_consecutive_pass_days(site_id, client)

        # Commissioning gates passed
        metrics["commissioning_all_gates_passed"] = await self._check_commissioning_gates(site_id, client)

        return metrics

    def _days_in_phase(self, created_at: str | None, phase: str | None) -> int:
        """Calculate days site has been in its current phase."""
        if not created_at:
            return 0
        try:
            from datetime import datetime

            created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            now = datetime.now(tz=UTC)
            days = (now - created).days
            return max(0, days)
        except Exception:
            return 0

    async def _check_bridge_connected(self, site_id: str) -> bool:
        """Check if bridge is connected by querying log_sources.

        Queries log_sources rather than the in-process ShadowModePollingService
        singleton, because the scheduler runs polling in a subprocess and the
        in-process singleton has never polled (poll_count=0 always).
        """
        try:
            from app.config.settings import settings
            from supabase import create_client

            client = create_client(settings.supabase_url, settings.supabase_service_role_key)
            source_name = f"Shadow Bridge ({site_id})"
            resp = (
                client.table("log_sources")
                .select("last_sync_at, last_sync_status")
                .like("name", source_name)
                .eq("is_active", True)
                .order("last_sync_at", desc=True)
                .limit(1)
                .execute()
            )

            if not resp.data:
                return False

            last_sync = resp.data[0].get("last_sync_at")
            sync_status = resp.data[0].get("last_sync_status", "unknown")
            if not last_sync:
                return False

            last_sync_dt = datetime.fromisoformat(last_sync.replace("Z", "+00:00"))
            if last_sync_dt.tzinfo is None:
                last_sync_dt = last_sync_dt.replace(tzinfo=UTC)
            age_seconds = (datetime.now(tz=UTC) - last_sync_dt).total_seconds()
            healthy_threshold = 300.0  # 5 minutes

            return age_seconds <= healthy_threshold and sync_status in ("success", "pending")
        except Exception:
            return False

    async def _get_bridge_uptime_pct(self, site_id: str) -> float:
        """Get bridge uptime % from adapter_health_current."""
        try:
            result = (
                self.supabase.table("adapter_health_current")
                .select("uptime_24h_percent")
                .eq("site_id", site_id)
                .eq("adapter_name", "bridge")
                .execute()
            )
            if result.data:
                return float(result.data[0].get("uptime_24h_percent") or 0.0)
            return 0.0
        except Exception:
            return 0.0

    async def _count_recent_anomaly_scores(self, site_id: str, client) -> int:
        """Count equipment rows with non-null anomaly_score in operating_data, last 30 min."""
        try:
            site_row = client.table("sites").select("id").eq("code", site_id).limit(1).execute()
            site_uuid = site_row.data[0]["id"] if site_row.data else None
            if not site_uuid:
                return 0
            cutoff = datetime.now(tz=UTC) - timedelta(minutes=30)
            # Query equipment table for rows with recent anomaly_score in operating_data
            # Use operating_data ? 'anomaly_score' JSONB existence check
            rows = (
                client.table("equipment")
                .select("id", count="exact")
                .eq("site_id", site_uuid)
                .not_.is_("operating_data", "null")
                .gte("updated_at", cutoff.isoformat())
                .execute()
            )
            # Filter to those with actual anomaly_score in operating_data
            if hasattr(rows, "count"):
                # Total equipment updated in window — need to count those with anomaly_score
                pass
            total = len(rows.data or [])
            # Count equipment with non-null anomaly_score in operating_data
            has_score = (
                client.table("equipment")
                .select("id")
                .eq("site_id", site_uuid)
                .not_.is_("operating_data", "null")
                .gte("updated_at", cutoff.isoformat())
                .execute()
            )
            count = sum(
                1 for r in (has_score.data or []) if r.get("operating_data", {}).get("anomaly_score") is not None
            )
            return count
        except Exception as e:
            logger.debug("anomaly_scores_writing check failed: %s", e)
            return 0

    async def _get_freshness_max(self, site_id: str, client) -> float:
        """Get max data age across all sources in data_freshness."""
        try:
            result = client.table("data_freshness").select("age_seconds").eq("site_id", site_id).execute()
            if result.data:
                return max((r.get("age_seconds") or 0) / 3600.0 for r in result.data)
            return 0.0
        except Exception:
            return 999.0

    def _count_recommendations(self, site_uuid: str | None, client) -> int:
        """Count all recommendations for site."""
        if not site_uuid:
            return 0
        try:
            rows = client.table("recommendations").select("id", count="exact").eq("site_id", site_uuid).execute()
            return rows.count if hasattr(rows, "count") else len(rows.data or [])
        except Exception:
            return 0

    def _count_acknowledged_recommendations(self, site_uuid: str | None, client) -> int:
        """Count recommendations with status != 'pending' (approved/acknowledged)."""
        if not site_uuid:
            return 0
        try:
            rows = (
                client.table("recommendations")
                .select("id", count="exact")
                .eq("site_id", site_uuid)
                .neq("status", "pending")
                .execute()
            )
            return rows.count if hasattr(rows, "count") else len(rows.data or [])
        except Exception:
            return 0

    async def _check_no_safety_violations(self, site_id: str, days: int, client) -> bool:
        """Check if no safety violations in last N days."""
        try:
            site_row = client.table("sites").select("id").eq("code", site_id).limit(1).execute()
            site_uuid = site_row.data[0]["id"] if site_row.data else None
            if not site_uuid:
                return False
            cutoff = datetime.now(tz=UTC) - timedelta(days=days)
            rows = (
                client.table("alerts")
                .select("id", count="exact")
                .eq("site_id", site_uuid)
                .eq("severity", "critical")
                .gte("created_at", cutoff.isoformat())
                .execute()
            )
            count = rows.count if hasattr(rows, "count") else len(rows.data or [])
            return count == 0
        except Exception:
            return False

    async def _get_adapter_error_rate(self, site_id: str, client) -> float:
        """Get adapter error rate % from adapter_health_history."""
        try:
            cutoff = datetime.now(tz=UTC) - timedelta(hours=1)
            rows = (
                client.table("adapter_health")
                .select("is_healthy")
                .eq("site_id", site_id)
                .gte("timestamp", cutoff.isoformat())
                .execute()
            )
            if not rows.data:
                return 0.0
            healthy = sum(1 for r in rows.data if r.get("is_healthy"))
            total = len(rows.data)
            return round((total - healthy) / total * 100, 2) if total > 0 else 0.0
        except Exception:
            return 0.0

    async def _get_match_coverage(self, site_id: str, client) -> float:
        """Get equipment match coverage % — proportion of discovered vs mapped points."""
        try:
            # Resolve site code to UUID for equipment queries
            site_row = client.table("sites").select("id").eq("code", site_id).limit(1).execute()
            site_uuid = site_row.data[0]["id"] if site_row.data else None
            if not site_uuid:
                return 0.0

            result = client.table("equipment").select("id").eq("site_id", site_uuid).execute()
            total_equipment = len(result.data or [])
            if total_equipment == 0:
                return 0.0
            # Map coverage: equipment with non-empty network_info (BACnet point mapping)
            mapped = (
                client.table("equipment")
                .select("id")
                .eq("site_id", site_uuid)
                .not_.is_("network_info", "null")
                .execute()
            )
            # Count those where network_info is not empty dict
            mapped_data = [r for r in (mapped.data or [])]
            mapped_count = sum(1 for r in mapped_data if r.get("id"))
            # Re-query with filter for non-empty network_info
            non_empty = (
                client.table("equipment")
                .select("id", "network_info")
                .eq("site_id", site_uuid)
                .not_.is_("network_info", "null")
                .execute()
            )
            real_mapped = len([r for r in (non_empty.data or []) if r.get("network_info") and r["network_info"] != {}])
            return round(real_mapped / total_equipment * 100, 1) if total_equipment > 0 else 0.0
        except Exception:
            return 0.0

    async def _get_consecutive_pass_days(self, site_id: str, client) -> int:
        """Count consecutive days where all health checks passed."""
        try:
            cutoff = datetime.now(tz=UTC) - timedelta(days=30)
            rows = (
                client.table("adapter_health")
                .select("timestamp, is_healthy")
                .eq("site_id", site_id)
                .gte("timestamp", cutoff.isoformat())
                .order("timestamp", desc=True)
                .execute()
            )
            if not rows.data:
                return 0
            # Group by date, check if each day had all healthy
            from collections import defaultdict

            by_date: dict[str, list[bool]] = defaultdict(list)
            for row in rows.data:
                ts = row.get("timestamp", "")
                date = ts[:10] if ts else ""
                by_date[date].append(row.get("is_healthy", False))
            consecutive = 0
            for date in sorted(by_date.keys(), reverse=True):
                daily = by_date[date]
                if all(daily):
                    consecutive += 1
                else:
                    break
            return consecutive
        except Exception:
            return 0

    async def _check_commissioning_gates(self, site_id: str, client) -> bool:
        """Check if all commissioning gates passed (placeholder — always True for now)."""
        # TODO: Wire to commissioning gate service
        return True


# Module-level singleton
_gate_evaluation_service: GateEvaluationService | None = None


def get_gate_evaluation_service() -> GateEvaluationService:
    global _gate_evaluation_service
    if _gate_evaluation_service is None:
        _gate_evaluation_service = GateEvaluationService()
    return _gate_evaluation_service
