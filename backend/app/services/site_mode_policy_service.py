"""Site mode policy dry-run evaluator.

Loads a per-site onboarding policy, evaluates current monitoring metrics against
deterministic stage thresholds, and logs would-promote/would-demote actions.

Important:
- Dry-run only: no write execution, no ingestion-mode mutation.
- Persists dry-run state for dwell windows and anti-flapping stability checks.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.services.monitoring_service import MonitoringService

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return None


class SiteModePolicyService:
    """Evaluates deterministic site onboarding thresholds in dry-run mode."""

    def __init__(self, policy_dir: Path | None = None, *, clock=None) -> None:
        self._policy_dir = policy_dir or (Path(__file__).resolve().parent.parent / "data" / "policies")
        self._monitoring = MonitoringService()
        self._clock = clock or _utcnow

    def _policy_path(self, site_id: str) -> Path:
        return self._policy_dir / f"{site_id}-mode-policy.json"

    def _state_path(self, site_id: str) -> Path:
        return self._policy_dir / f"{site_id}-mode-policy-state.json"

    def load_policy(self, site_id: str) -> dict[str, Any]:
        """Load policy JSON for a site."""
        path = self._policy_path(site_id)
        if not path.exists():
            raise FileNotFoundError(f"Policy not found for {site_id}: {path}")
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data

    def _load_state(self, site_id: str, policy: dict[str, Any]) -> dict[str, Any]:
        """Load or initialize persisted dry-run state."""
        path = self._state_path(site_id)
        default_stage = policy.get("default_stage", "commissioning")
        default = {
            "site_id": site_id,
            "current_stage": default_stage,
            "candidate_stage": None,
            "candidate_since": None,
            "violation_stage": None,
            "violation_since": None,
            "last_demoted_at": None,
            "last_evaluated_at": None,
        }

        if not path.exists():
            return default

        try:
            with path.open("r", encoding="utf-8") as fh:
                loaded = json.load(fh)
            if not isinstance(loaded, dict):
                return default
            state = {**default, **loaded}
        except Exception:
            return default

        stages = set(policy.get("stage_order", []))
        if state.get("current_stage") not in stages:
            state["current_stage"] = default_stage
            state["candidate_stage"] = None
            state["candidate_since"] = None
            state["violation_stage"] = None
            state["violation_since"] = None
        return state

    def _save_state(self, site_id: str, state: dict[str, Any]) -> None:
        """Persist dry-run state to disk."""
        path = self._state_path(site_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as fh:
            json.dump(state, fh, indent=2)

    @staticmethod
    def _hours_since(iso_value: str | None, now: datetime) -> float:
        dt = _parse_iso(iso_value)
        if not dt:
            return 0.0
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return max(0.0, (now - dt).total_seconds() / 3600.0)

    @staticmethod
    def _extract_metrics(snapshot: Any) -> dict[str, Any]:
        """Map monitoring snapshot fields to policy metric keys."""
        quality_gate = snapshot.quality_gate or {}
        commissioning = snapshot.commissioning

        return {
            "freshness_hours": float(snapshot.ingestion.freshness_hours),
            "match_coverage_pct": float(snapshot.ingestion.match_coverage),
            "error_rate_pct": float(snapshot.ingestion.error_rate),
            "file_manual_sources": int(snapshot.ingestion.provenance_summary.get("file_manual", 0)),
            "conflict_events_24h": int(snapshot.control.blocked_writes_24h + snapshot.control.safety_violations_24h),
            "commissioning_all_gates_passed": bool(commissioning.all_gates_passed) if commissioning else False,
            "consecutive_pass_days": int(commissioning.consecutive_pass_days) if commissioning else 0,
            "truth_check_passed": bool(commissioning.can_promote) if commissioning else False,
            "quality_gate_status": str(quality_gate.get("overall_status", "unknown")),
            "quality_gate_failed_rules": list(quality_gate.get("failed_rules", [])),
        }

    @staticmethod
    def _evaluate_thresholds(thresholds: dict[str, Any], metrics: dict[str, Any]) -> list[dict[str, Any]]:
        """Evaluate threshold dict and return per-rule pass/fail detail."""
        checks: list[dict[str, Any]] = []

        for key, expected in thresholds.items():
            passed = False
            actual = None
            comparator = "eq"

            if key == "freshness_hours_max":
                actual = metrics["freshness_hours"]
                comparator = "<="
                passed = actual <= float(expected)
            elif key == "match_coverage_min_pct":
                actual = metrics["match_coverage_pct"]
                comparator = ">="
                passed = actual >= float(expected)
            elif key == "error_rate_max_pct":
                actual = metrics["error_rate_pct"]
                comparator = "<="
                passed = actual <= float(expected)
            elif key == "file_manual_sources_max":
                actual = metrics["file_manual_sources"]
                comparator = "<="
                passed = actual <= int(expected)
            elif key == "conflict_events_max_24h":
                actual = metrics["conflict_events_24h"]
                comparator = "<="
                passed = actual <= int(expected)
            elif key == "commissioning_all_gates_passed":
                actual = metrics["commissioning_all_gates_passed"]
                comparator = "=="
                passed = bool(actual) is bool(expected)
            elif key == "consecutive_pass_days_min":
                actual = metrics["consecutive_pass_days"]
                comparator = ">="
                passed = actual >= int(expected)
            elif key == "truth_check_required":
                actual = metrics["truth_check_passed"]
                comparator = "is_true"
                passed = True if not bool(expected) else bool(actual)
            elif key == "quality_gate_allowed":
                allowed = [str(v) for v in expected] if isinstance(expected, list) else [str(expected)]
                actual = metrics["quality_gate_status"]
                comparator = "in"
                passed = actual in allowed
                expected = allowed
            else:
                actual = "unknown_metric"
                comparator = "unsupported"
                passed = False

            checks.append(
                {
                    "rule": key,
                    "passed": passed,
                    "actual": actual,
                    "expected": expected,
                    "comparator": comparator,
                }
            )

        return checks

    @staticmethod
    def _failed_rules(checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [c for c in checks if not c["passed"]]

    async def evaluate_site(self, site_id: str) -> dict[str, Any]:
        """Evaluate onboarding policy for a site and persist dry-run state."""
        now = self._clock()
        policy = self.load_policy(site_id)
        state = self._load_state(site_id, policy)

        snapshot = await self._monitoring.get_snapshot(site_id=site_id)
        metrics = self._extract_metrics(snapshot)

        stages = policy.get("stages", {})
        current_stage = state.get("current_stage", policy.get("default_stage", "commissioning"))
        stage_cfg = stages.get(current_stage, {})

        decision = "hold"
        target_stage = current_stage
        reasons: list[str] = []
        entry_checks: list[dict[str, Any]] = []
        exit_checks: list[dict[str, Any]] = []
        fail_closed_checks: list[dict[str, Any]] = []
        write_action = "none"

        # 1) Automatic stage fail-closed
        fail_closed_cfg = stage_cfg.get("fail_closed", {}) if current_stage == "automatic" else {}
        if fail_closed_cfg:
            fail_closed_checks = self._evaluate_thresholds(fail_closed_cfg, metrics)
            failed = self._failed_rules(fail_closed_checks)
            if failed:
                decision = "would_fail_closed_demote"
                target_stage = stage_cfg.get("fallback_stage", "supervised")
                reasons = [f"fail_closed:{f['rule']}" for f in failed]
                write_action = "stop_writes"

                state["current_stage"] = target_stage
                state["candidate_stage"] = None
                state["candidate_since"] = None
                state["violation_stage"] = None
                state["violation_since"] = None
                state["last_demoted_at"] = _iso(now)

        # 2) Exit thresholds for non-automatic stages
        if decision == "hold":
            exit_cfg = stage_cfg.get("exit", {})
            if exit_cfg:
                exit_thresholds = exit_cfg.get("thresholds", {})
                exit_checks = self._evaluate_thresholds(exit_thresholds, metrics)
                failed_exit = self._failed_rules(exit_checks)
                if failed_exit:
                    if state.get("violation_stage") != current_stage:
                        state["violation_stage"] = current_stage
                        state["violation_since"] = _iso(now)
                    violation_hours = self._hours_since(state.get("violation_since"), now)
                    min_violation_hours = float(exit_cfg.get("min_violation_hours", 0))
                    if violation_hours >= min_violation_hours:
                        decision = "would_demote"
                        target_stage = exit_cfg.get("demote_to", stage_cfg.get("fallback_stage", current_stage))
                        reasons = [f"exit:{f['rule']}" for f in failed_exit]
                        state["current_stage"] = target_stage
                        state["candidate_stage"] = None
                        state["candidate_since"] = None
                        state["violation_stage"] = None
                        state["violation_since"] = None
                        state["last_demoted_at"] = _iso(now)
                    else:
                        reasons = [f"exit_violation_dwell:{violation_hours:.2f}/{min_violation_hours:.2f}h"]
                else:
                    state["violation_stage"] = None
                    state["violation_since"] = None

        # 3) Promotion thresholds + dwell windows + re-promotion stability
        if decision == "hold":
            promotion_cfg = stage_cfg.get("promotion", {})
            next_stage = stage_cfg.get("next_stage")
            if promotion_cfg and next_stage:
                entry_thresholds = promotion_cfg.get("entry_thresholds", {})
                entry_checks = self._evaluate_thresholds(entry_thresholds, metrics)
                failed_entry = self._failed_rules(entry_checks)

                if failed_entry:
                    if state.get("candidate_stage") == next_stage:
                        state["candidate_stage"] = None
                        state["candidate_since"] = None
                    reasons = [f"entry:{f['rule']}" for f in failed_entry]
                else:
                    # anti-flapping: re-promotion stability window after any demotion
                    required_stability = float(policy.get("repromotion_stability_hours", 24))
                    hours_since_demote = self._hours_since(state.get("last_demoted_at"), now)
                    if state.get("last_demoted_at") and hours_since_demote < required_stability:
                        reasons = [f"repromotion_stability:{hours_since_demote:.2f}/{required_stability:.2f}h"]
                        if state.get("candidate_stage") == next_stage:
                            state["candidate_stage"] = None
                            state["candidate_since"] = None
                    else:
                        if state.get("candidate_stage") != next_stage:
                            state["candidate_stage"] = next_stage
                            state["candidate_since"] = _iso(now)

                        candidate_hours = self._hours_since(state.get("candidate_since"), now)
                        min_dwell = float(promotion_cfg.get("min_dwell_hours", 0))
                        if candidate_hours >= min_dwell:
                            decision = "would_promote"
                            target_stage = next_stage
                            reasons = [f"promotion:{current_stage}->{next_stage}"]
                            state["current_stage"] = target_stage
                            state["candidate_stage"] = None
                            state["candidate_since"] = None
                            state["violation_stage"] = None
                            state["violation_since"] = None
                        else:
                            reasons = [f"promotion_dwell:{candidate_hours:.2f}/{min_dwell:.2f}h"]

        state["last_evaluated_at"] = _iso(now)
        self._save_state(site_id, state)

        return {
            "site_id": site_id,
            "policy_version": policy.get("version"),
            "dry_run": bool(policy.get("dry_run", True)),
            "evaluated_at": _iso(now),
            "snapshot_ingestion_mode": snapshot.ingestion_mode,
            "state_before": current_stage,
            "state_after": state.get("current_stage"),
            "decision": decision,
            "target_stage": target_stage,
            "write_action": write_action,
            "reasons": reasons,
            "metrics": metrics,
            "entry_checks": entry_checks,
            "exit_checks": exit_checks,
            "fail_closed_checks": fail_closed_checks,
            "state_path": str(self._state_path(site_id)),
            "policy_path": str(self._policy_path(site_id)),
        }
