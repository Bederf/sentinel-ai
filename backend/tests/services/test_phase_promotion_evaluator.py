"""Tests for Trust Ladder phase promotion evaluator."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

# Pre-import modules patched via string paths — these are imported inside
# method bodies so not in the parent namespace by default
import app.services.notification_service  # noqa: F401
from app.services.phase_promotion_evaluator import (
    GateResult,
    PhasePromotionEvaluator,
    get_phase_promotion_evaluator,
)


@pytest.fixture
def evaluator():
    """Fresh evaluator with pre-set config (no _ensure_config)."""
    ev = PhasePromotionEvaluator()
    ev._internal_key = "test-internal-key"
    ev._backend_url = "http://127.0.0.1:9095"
    return ev


def _make_table_chain(data: list | None = None, count: int = 0):
    """Build a mock table query chain where all methods return self.

    This ensures multiple .select().eq().limit().execute() calls on the
    same table all get consistent data.
    """
    chain = MagicMock()
    chain.select.return_value = chain
    chain.eq.return_value = chain
    chain.neq.return_value = chain
    chain.gte.return_value = chain
    chain.is_.return_value = chain
    chain.ilike.return_value = chain
    chain.in_.return_value = chain
    chain.or_.return_value = chain
    chain.filter.return_value = chain
    chain.order.return_value = chain
    chain.limit.return_value = chain
    chain.update.return_value = chain
    chain.insert.return_value = chain
    result = MagicMock()
    result.data = data or []
    result.count = count
    chain.execute.return_value = result
    return chain


def _make_supabase(tables: dict[str, list | None] = None):
    """Factory: returns a mock supabase client where each table() returns a chain.

    ``tables`` maps table name → execute data (list of dicts) or None for empty.
    """
    client = MagicMock()
    chains = {}

    for name, data in (tables or {}).items():
        chain = _make_table_chain(data=data or [], count=len(data or []))
        chains[name] = chain

    def _table(name):
        if name not in chains:
            chains[name] = _make_table_chain(data=[], count=0)
        return chains[name]

    client.table.side_effect = _table
    return client, chains


# ── 1. shadow_live → advisory: all gates pass ──────────────────────────


@pytest.mark.asyncio
async def test_promotion_shadow_to_advisory_all_gates_pass(evaluator):
    """All shadow_live gates pass → readiness is surfaced, phase unchanged."""
    client, chains = _make_supabase(
        {
            "sites": [{"id": "uuid-001", "ml_hours_ingested": 85.0}],
            "equipment_analytics": [],
        }
    )
    # anomaly_scores_writing → 1 recent anomaly
    chains["equipment_analytics"].execute.return_value.count = 1

    with (
        patch.object(evaluator, "_ensure_config", AsyncMock()),
        patch("supabase.create_client", return_value=client),
        patch("app.services.simbiot_service.simbiot_service.get_site_status", AsyncMock(return_value={"status": "ok"})),
        patch("app.services.notification_service.notification_service.send_alert_direct", AsyncMock()),
    ):
        result = await evaluator.evaluate_site("site-002", "shadow_live")

    assert result.eligible is True
    assert result.promoted is False
    assert result.from_phase == "shadow_live"
    assert result.to_phase == "advisory"
    assert result.reason == "ready_for_manual_promotion"
    assert len(result.gates) == 3
    assert all(g.passed for g in result.gates)
    chains["sites"].update.assert_called()


# ── 2. shadow_live blocked: insufficient ML hours ──────────────────────


@pytest.mark.asyncio
async def test_promotion_shadow_blocked_insufficient_hours(evaluator):
    """Insufficient ml_hours → not eligible, not promoted."""
    client, _ = _make_supabase(
        {
            "sites": [{"id": "uuid-001", "ml_hours_ingested": 30.0}],
        }
    )

    with (
        patch.object(evaluator, "_ensure_config", AsyncMock()),
        patch("supabase.create_client", return_value=client),
    ):
        result = await evaluator.evaluate_site("site-002", "shadow_live")

    assert result.eligible is False
    assert result.promoted is False
    assert len(result.gates) == 3
    assert result.gates[0].passed is False
    assert result.gates[0].gate.startswith("ml_hours_ingested")


# ── 3. advisory → supervised: all gates pass ───────────────────────────


@pytest.mark.asyncio
async def test_promotion_advisory_to_supervised_all_gates_pass(evaluator):
    """All advisory gates pass → readiness is surfaced, phase unchanged."""
    client, chains = _make_supabase(
        {
            "sites": [{"id": "uuid-001", "ml_hours_ingested": 600.0}],
            "audit_log": [],
            "equipment": [
                {"code": "S002-AHU-B01", "type": "ahu"},
                {"code": "S002-AHU-R01", "type": "ahu"},
                {"code": "S002-CHILLER-B01", "type": "chiller"},
                {"code": "S002-FCU-001", "type": "fcu"},
            ],
            "site_modules": [
                {"module_type": "hvac_control", "status": "active", "licensed": True},
            ],
            "site_adapter_config": [
                {
                    "protocol": "bridge",
                    "connection_config": {
                        "base_url": "http://10.99.0.1:8080",
                        "supports_writes": True,
                        "write_enabled": False,
                        "token": "test-token",
                    },
                },
            ],
            "point_asset_mappings": [
                {"id": f"mapping-{idx}", "extracted_asset_id": equipment}
                for idx, equipment in enumerate(
                    [
                        "S002-AHU-B01",
                        "S002-AHU-B01",
                        "S002-AHU-B01",
                        "S002-AHU-R01",
                        "S002-AHU-R01",
                        "S002-AHU-R01",
                        "S002-CHILLER-B01",
                        "S002-CHILLER-B01",
                        "S002-FCU-001",
                        "S002-FCU-001",
                    ],
                    start=1,
                )
            ],
        }
    )

    # Build a recommendations chain that returns different counts based on
    # which query pattern is used
    rec_chain = _make_table_chain(count=12)  # default → 12 (generated)
    ack_sub = _make_table_chain(count=3)  # neq("status", "pending") → 3
    rec_chain.neq.side_effect = lambda f, v: ack_sub if v == "pending" else rec_chain
    chains["recommendations"] = rec_chain

    # audit_log → 0 errors
    chains["audit_log"].execute.return_value = MagicMock(data=[], count=0)
    chains["point_asset_mappings"].execute.return_value.count = 10

    with (
        patch.object(evaluator, "_ensure_config", AsyncMock()),
        patch("supabase.create_client", return_value=client),
        patch("httpx.options") as mock_options,
        patch("app.services.notification_service.notification_service.send_alert_direct", AsyncMock()),
    ):
        mock_options.return_value = MagicMock(status_code=405, headers={"allow": "POST"})
        result = await evaluator.evaluate_site("site-002", "advisory")

    assert result.eligible is True
    assert result.promoted is False
    assert result.from_phase == "advisory"
    assert result.to_phase == "supervised"
    assert result.reason == "ready_for_manual_promotion"
    assert all(g.passed for g in result.gates)


@pytest.mark.asyncio
async def test_promotion_advisory_to_supervised_blocked_without_verified_controls(evaluator):
    """Advisory cannot move to supervised until control mappings are verified."""
    client, chains = _make_supabase(
        {
            "sites": [{"id": "uuid-005", "ml_hours_ingested": 600.0}],
            "equipment": [
                {"code": "S005-AHU-201", "type": "ahu"},
                {"code": "S005-CHILLER-B01", "type": "chiller"},
            ],
            "point_asset_mappings": [],
        }
    )

    rec_chain = _make_table_chain(count=12)
    ack_sub = _make_table_chain(count=3)
    rec_chain.neq.side_effect = lambda f, v: ack_sub if v == "pending" else rec_chain
    chains["recommendations"] = rec_chain
    chains["point_asset_mappings"].execute.return_value.count = 0

    with (
        patch.object(evaluator, "_ensure_config", AsyncMock()),
        patch("supabase.create_client", return_value=client),
    ):
        result = await evaluator.evaluate_site("site-005", "advisory")

    assert result.eligible is False
    failed = {gate.gate: gate for gate in result.gates if not gate.passed}
    assert "verified_writable_control_points >= 10" in failed
    assert "controllable_equipment_control_coverage >= 0.75" in failed


# ── 4. advisory blocked: no acknowledgements ────────────────────────────


@pytest.mark.asyncio
async def test_promotion_advisory_blocked_no_acknowledgements(evaluator):
    """No recommendation acknowledgements → blocked."""
    client, chains = _make_supabase(
        {
            "sites": [{"id": "uuid-001", "ml_hours_ingested": 550.0}],
        }
    )

    # Generated → 12, acknowledged → 0
    rec_chain = _make_table_chain(count=12)
    ack_sub = _make_table_chain(count=0)
    rec_chain.neq.side_effect = lambda f, v: ack_sub if v == "pending" else rec_chain
    chains["recommendations"] = rec_chain

    with (
        patch.object(evaluator, "_ensure_config", AsyncMock()),
        patch("supabase.create_client", return_value=client),
    ):
        result = await evaluator.evaluate_site("site-002", "advisory")

    assert result.eligible is False
    assert result.promoted is False
    ack_gate = [g for g in result.gates if "acknowledged" in g.gate]
    assert len(ack_gate) == 1
    assert ack_gate[0].passed is False
    assert ack_gate[0].value == 0


# ── 5. writes readiness only, never calls phase PATCH ──────────────────


@pytest.mark.asyncio
async def test_promotion_writes_readiness_not_phase_patch(evaluator):
    """Gate pass must write readiness metadata, not PATCH the site phase."""
    client, chains = _make_supabase(
        {
            "sites": [{"id": "uuid-001", "ml_hours_ingested": 100.0}],
            "equipment_analytics": [],
        }
    )
    chains["equipment_analytics"].execute.return_value.count = 2

    with (
        patch.object(evaluator, "_ensure_config", AsyncMock()),
        patch("supabase.create_client", return_value=client),
        patch("app.services.simbiot_service.simbiot_service.get_site_status", AsyncMock(return_value={"status": "ok"})),
        patch("httpx.AsyncClient") as mock_httpx,
        patch("app.services.notification_service.notification_service.send_alert_direct", AsyncMock()),
    ):
        result = await evaluator.evaluate_site("site-002", "shadow_live")

    assert result.eligible is True
    assert result.promoted is False
    mock_httpx.assert_not_called()
    chains["sites"].update.assert_called_once()
    payload = chains["sites"].update.call_args.args[0]
    assert payload["phase_promotion_ready"] is True
    assert payload["phase_promotion_target"] == "advisory"
    assert payload["phase_promotion_readiness"]["ready"] is True
    assert payload["phase_promotion_readiness"]["from_phase"] == "shadow_live"
    assert payload["phase_promotion_readiness"]["to_phase"] == "advisory"
    assert "onboarding_phase" not in payload
    chains["phase_promotion_readiness_log"].insert.assert_called_once()


# ── 6. sends Telegram notification ─────────────────────────────────────


@pytest.mark.asyncio
async def test_promotion_sends_telegram_notification(evaluator):
    """Telegram notification should be sent when readiness is surfaced."""
    client, chains = _make_supabase(
        {
            "sites": [{"id": "uuid-001", "ml_hours_ingested": 100.0}],
            "equipment_analytics": [],
        }
    )
    chains["equipment_analytics"].execute.return_value.count = 2

    telegram_called = False
    telegram_kwargs = None

    async def _capture_telegram(**kwargs):
        nonlocal telegram_called, telegram_kwargs
        telegram_called = True
        telegram_kwargs = kwargs

    with (
        patch.object(evaluator, "_ensure_config", AsyncMock()),
        patch("supabase.create_client", return_value=client),
        patch("app.services.simbiot_service.simbiot_service.get_site_status", AsyncMock(return_value={"status": "ok"})),
        patch(
            "app.services.notification_service.notification_service.send_alert_direct", side_effect=_capture_telegram
        ),
    ):
        await evaluator.evaluate_site("site-002", "shadow_live")

    assert telegram_called, "Telegram notification was not sent"
    assert telegram_kwargs is not None
    assert "Phase Readiness" in telegram_kwargs.get("title", "")
    assert "shadow_live" in telegram_kwargs.get("body", "")
    assert "advisory" in telegram_kwargs.get("body", "")
    assert "No phase change was applied automatically" in telegram_kwargs.get("body", "")


# ── 7. logs readiness distinctly from phase transitions ────────────────


@pytest.mark.asyncio
async def test_promotion_logs_to_readiness_log(evaluator):
    """Evaluator should log readiness, not a phase transition."""
    client, chains = _make_supabase(
        {
            "sites": [{"id": "uuid-001", "ml_hours_ingested": 100.0}],
            "equipment_analytics": [],
        }
    )
    chains["equipment_analytics"].execute.return_value.count = 1

    with (
        patch.object(evaluator, "_ensure_config", AsyncMock()),
        patch("supabase.create_client", return_value=client),
        patch("app.services.simbiot_service.simbiot_service.get_site_status", AsyncMock(return_value={"status": "ok"})),
        patch("app.services.notification_service.notification_service.send_alert_direct", AsyncMock()),
    ):
        await evaluator.evaluate_site("site-002", "shadow_live")

    chains["phase_promotion_readiness_log"].insert.assert_called_once()
    payload = chains["phase_promotion_readiness_log"].insert.call_args.args[0]
    assert payload["site_id"] == "site-002"
    assert payload["from_phase"] == "shadow_live"
    assert payload["to_phase"] == "advisory"
    assert payload["met"] is True
    assert payload["recorded_by"] == "phase_promotion_evaluator"
    assert len(payload["gate_results"]) == 3
    assert "phase_transition_log" not in chains


# ── 8. does not double-promote ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_promotion_does_not_double_promote(evaluator):
    """Already-promoted site at target phase should not trigger another promotion."""
    client, _ = _make_supabase(
        {
            "sites": [{"id": "uuid-001", "ml_hours_ingested": 100.0}],
        }
    )

    with (
        patch.object(evaluator, "_ensure_config", AsyncMock()),
        patch("supabase.create_client", return_value=client),
    ):
        result = await evaluator.evaluate_site("site-002", "automatic")

    assert result.eligible is False
    assert result.promoted is False
    assert "no_promotion_gates_defined" in (result.reason or "")


# ── 9. evaluator runs hourly via scheduler ─────────────────────────────


def test_evaluator_runs_hourly_via_scheduler():
    """Scheduler job id and interval must match spec."""
    from apscheduler.triggers.interval import IntervalTrigger

    job_id = "phase_promotion_evaluator"
    trigger = IntervalTrigger(hours=1)
    kwargs = {
        "func": object(),
        "trigger": trigger,
        "id": job_id,
        "max_instances": 1,
        "coalesce": True,
    }

    assert kwargs["id"] == job_id
    assert kwargs["coalesce"] is True
    assert kwargs["max_instances"] == 1
    assert kwargs["trigger"].interval == timedelta(hours=1)

    ev = get_phase_promotion_evaluator()
    assert hasattr(ev, "evaluate_all_sites")
    assert callable(ev.evaluate_all_sites)


# ── 10. GateResult captures value and threshold ────────────────────────


def test_gate_result_captures_value_and_threshold():
    """GateResult must record gate name, pass/fail, value, and threshold."""
    result = GateResult(
        gate="ml_hours_ingested >= 72",
        passed=True,
        value=85.3,
        threshold=72.0,
    )

    assert result.gate == "ml_hours_ingested >= 72"
    assert result.passed is True
    assert result.value == 85.3
    assert result.threshold == 72.0

    d = result.to_dict()
    assert d["gate"] == "ml_hours_ingested >= 72"
    assert d["passed"] is True
    assert d["value"] == 85.3
    assert d["threshold"] == 72.0


@pytest.mark.asyncio
async def test_recommendations_generated_gate_counts_ai_optimizer_visible_rows(evaluator):
    """Promotion gate count uses source=ai_optimizer and excludes shadow rows."""
    client, chains = _make_supabase({"recommendations": [{"id": "rec-1"}]})
    chains["recommendations"].execute.return_value.count = 1

    result = await evaluator._evaluate_single_gate(
        client=client,
        site_id="site-002",
        site_uuid="uuid-001",
        site_id_for_queries="site-002",
        gate="recommendations_generated >= 1",
        ml_hours=0.0,
        now=datetime.now(tz=UTC),
    )

    assert result.passed is True
    assert call("source", "ai_optimizer") in chains["recommendations"].eq.call_args_list
    assert call("shadow_mode", False) in chains["recommendations"].eq.call_args_list


# ── 11. False positive rate gate ───────────────────────────────────────


@pytest.mark.asyncio
async def test_false_positive_rate_gate_passes(evaluator):
    """false_positive_rate <= 0.10 gate computes correctly."""
    client, chains = _make_supabase(
        {
            "sites": [{"id": "uuid-001", "ml_hours_ingested": 2500.0, "human_approved_autonomous": True}],
            "parasite_decisions": [],
        }
    )

    # Build recommendations chain that branches per query:
    #   eq("status","approved")  → count 30
    #   eq("status","rejected")  → count 3
    #   neq("status","pending")  → count 50 (total non-pending)
    #   default                  → count 50
    approved = _make_table_chain(count=30)
    rejected = _make_table_chain(count=3)
    non_pending = _make_table_chain(count=50)

    rec_chain = _make_table_chain(count=50)
    rec_chain.eq.side_effect = lambda f, v: rejected if v == "rejected" else approved if v == "approved" else rec_chain
    rec_chain.neq.side_effect = lambda f, v: non_pending if v == "pending" else rec_chain
    chains["recommendations"] = rec_chain

    # no_safety_violations_7d → pass
    chains["parasite_decisions"].execute.return_value = MagicMock(data=[], count=0)

    with (
        patch.object(evaluator, "_ensure_config", AsyncMock()),
        patch("supabase.create_client", return_value=client),
    ):
        result = await evaluator.evaluate_site("site-002", "supervised")

    fpr_gate = [g for g in result.gates if "false_positive" in g.gate]
    assert len(fpr_gate) == 1
    assert fpr_gate[0].passed is True
    assert fpr_gate[0].value == 0.06


# ── 12. human_approved_autonomous gate ──────────────────────────────────


@pytest.mark.asyncio
async def test_human_approved_autonomous_gate_blocks(evaluator):
    """supervised → automatic blocked when human_approved_autonomous is False."""
    client, chains = _make_supabase(
        {
            "sites": [{"id": "uuid-001", "ml_hours_ingested": 2500.0, "human_approved_autonomous": False}],
            "parasite_decisions": [],
        }
    )

    # All other gates pass (approval_accuracy, FPR, recs_approved)
    approved = _make_table_chain(count=30)
    rejected = _make_table_chain(count=0)
    non_pending = _make_table_chain(count=50)

    rec_chain = _make_table_chain(count=50)
    rec_chain.eq.side_effect = lambda f, v: rejected if v == "rejected" else approved if v == "approved" else rec_chain
    rec_chain.neq.side_effect = lambda f, v: non_pending if v == "pending" else rec_chain
    chains["recommendations"] = rec_chain

    # no_safety_violations_7d → pass
    chains["parasite_decisions"].execute.return_value = MagicMock(data=[], count=0)

    with (
        patch.object(evaluator, "_ensure_config", AsyncMock()),
        patch("supabase.create_client", return_value=client),
    ):
        result = await evaluator.evaluate_site("site-002", "supervised")

    human_gate = [g for g in result.gates if "human_approved" in g.gate]
    assert len(human_gate) == 1
    assert human_gate[0].passed is False
    assert human_gate[0].value is False
    assert result.eligible is False
