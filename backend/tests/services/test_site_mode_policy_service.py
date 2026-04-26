"""Unit tests for SiteModePolicyService dry-run stage evaluation."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.site_mode_policy_service import SiteModePolicyService


def _base_policy() -> dict:
    return {
        "site_id": "site-002",
        "version": "test-v1",
        "dry_run": True,
        "default_stage": "shadow_live",
        "stage_order": ["commissioning", "shadow_live", "advisory", "supervised", "automatic"],
        "repromotion_stability_hours": 24,
        "stages": {
            "shadow_live": {
                "next_stage": "advisory",
                "promotion": {
                    "min_dwell_hours": 0,
                    "entry_thresholds": {
                        "freshness_hours_max": 2.0,
                        "match_coverage_min_pct": 95.0,
                        "error_rate_max_pct": 1.0,
                        "file_manual_sources_max": 0,
                        "commissioning_all_gates_passed": True,
                        "consecutive_pass_days_min": 2,
                        "quality_gate_allowed": ["pass", "warn"],
                    },
                },
            },
            "advisory": {
                "next_stage": "supervised",
                "promotion": {
                    "min_dwell_hours": 0,
                    "entry_thresholds": {
                        "freshness_hours_max": 1.0,
                        "match_coverage_min_pct": 97.0,
                        "error_rate_max_pct": 1.0,
                        "file_manual_sources_max": 0,
                        "conflict_events_max_24h": 0,
                        "commissioning_all_gates_passed": True,
                        "consecutive_pass_days_min": 2,
                        "quality_gate_allowed": ["pass", "warn"],
                    },
                },
            },
            "supervised": {
                "next_stage": "automatic",
                "promotion": {
                    "min_dwell_hours": 0,
                    "entry_thresholds": {
                        "freshness_hours_max": 0.5,
                        "match_coverage_min_pct": 98.0,
                        "error_rate_max_pct": 0.5,
                        "file_manual_sources_max": 0,
                        "conflict_events_max_24h": 0,
                        "commissioning_all_gates_passed": True,
                        "consecutive_pass_days_min": 2,
                        "quality_gate_allowed": ["pass"],
                    },
                },
            },
            "automatic": {
                "fallback_stage": "supervised",
                "fail_closed": {
                    "freshness_hours_max": 1.0,
                    "match_coverage_min_pct": 97.0,
                    "file_manual_sources_max": 0,
                    "conflict_events_max_24h": 0,
                    "quality_gate_allowed": ["pass"],
                },
            },
        },
    }


def _write_policy(tmp_path: Path, policy: dict) -> None:
    policy_path = tmp_path / "site-002-mode-policy.json"
    policy_path.write_text(json.dumps(policy, indent=2), encoding="utf-8")


def _snapshot(
    *,
    freshness_hours: float,
    coverage: float,
    error_rate: float,
    file_manual_sources: int = 0,
    blocked_writes_24h: int = 0,
    safety_violations_24h: int = 0,
    commissioning_all_gates_passed: bool = True,
    consecutive_pass_days: int = 2,
    can_promote: bool = True,
    quality_gate_status: str = "pass",
):
    return SimpleNamespace(
        ingestion=SimpleNamespace(
            freshness_hours=freshness_hours,
            match_coverage=coverage,
            error_rate=error_rate,
            provenance_summary={"file_manual": file_manual_sources},
        ),
        control=SimpleNamespace(
            blocked_writes_24h=blocked_writes_24h,
            safety_violations_24h=safety_violations_24h,
        ),
        commissioning=SimpleNamespace(
            all_gates_passed=commissioning_all_gates_passed,
            consecutive_pass_days=consecutive_pass_days,
            can_promote=can_promote,
        ),
        quality_gate={"overall_status": quality_gate_status, "failed_rules": []},
        ingestion_mode="shadow_live",
    )


@pytest.mark.asyncio
async def test_promotes_shadow_live_to_advisory(tmp_path):
    policy = _base_policy()
    _write_policy(tmp_path, policy)

    svc = SiteModePolicyService(policy_dir=tmp_path)
    svc._monitoring.get_snapshot = AsyncMock(
        return_value=_snapshot(freshness_hours=0.2, coverage=99.0, error_rate=0.2),
    )

    result = await svc.evaluate_site("site-002")

    assert result["decision"] == "would_promote"
    assert result["state_before"] == "shadow_live"
    assert result["state_after"] == "advisory"


@pytest.mark.asyncio
async def test_automatic_fail_closed_would_demote_and_stop_writes(tmp_path):
    policy = _base_policy()
    policy["default_stage"] = "automatic"
    _write_policy(tmp_path, policy)

    state_path = tmp_path / "site-002-mode-policy-state.json"
    state_path.write_text(
        json.dumps({"site_id": "site-002", "current_stage": "automatic"}, indent=2),
        encoding="utf-8",
    )

    svc = SiteModePolicyService(policy_dir=tmp_path)
    svc._monitoring.get_snapshot = AsyncMock(
        return_value=_snapshot(
            freshness_hours=2.5,
            coverage=99.0,
            error_rate=0.2,
            blocked_writes_24h=1,
            quality_gate_status="fail",
        ),
    )

    result = await svc.evaluate_site("site-002")

    assert result["decision"] == "would_fail_closed_demote"
    assert result["state_before"] == "automatic"
    assert result["state_after"] == "supervised"
    assert result["write_action"] == "stop_writes"


@pytest.mark.asyncio
async def test_repromotion_stability_blocks_automatic_promotion(tmp_path):
    policy = _base_policy()
    _write_policy(tmp_path, policy)

    now = datetime(2026, 2, 21, 12, 0, 0, tzinfo=UTC)
    demoted_at = now - timedelta(hours=1)
    state_path = tmp_path / "site-002-mode-policy-state.json"
    state_path.write_text(
        json.dumps(
            {
                "site_id": "site-002",
                "current_stage": "supervised",
                "candidate_stage": None,
                "candidate_since": None,
                "violation_stage": None,
                "violation_since": None,
                "last_demoted_at": demoted_at.isoformat(),
                "last_evaluated_at": None,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    svc = SiteModePolicyService(policy_dir=tmp_path, clock=lambda: now)

    svc._monitoring.get_snapshot = AsyncMock(
        return_value=_snapshot(
            freshness_hours=0.2,
            coverage=99.0,
            error_rate=0.1,
            blocked_writes_24h=0,
            safety_violations_24h=0,
            quality_gate_status="pass",
        ),
    )

    result = await svc.evaluate_site("site-002")

    assert result["decision"] == "hold", (
        f"Expected 'hold' but got '{result['decision']}'. "
        f"Reasons: {result.get('reasons')}, "
        f"evaluated_at={result.get('evaluated_at')}, "
        f"last_demoted_at={demoted_at.isoformat()}, now={now.isoformat()}"
    )
    assert result["state_before"] == "supervised"
    assert result["state_after"] == "supervised"
    assert any("repromotion_stability" in reason for reason in result["reasons"])
