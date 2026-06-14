"""Tests for Trust Ladder phase promotion evaluator."""

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
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
    chain.filter.return_value = chain
    chain.order.return_value = chain
    chain.limit.return_value = chain
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
    """All shadow_live gates pass → eligible and promoted."""
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
        patch("httpx.AsyncClient") as mock_httpx,
        patch("app.services.notification_service.notification_service.send_alert_direct", AsyncMock()),
    ):
        mock_httpx_cm = AsyncMock()
        mock_httpx.return_value = mock_httpx_cm
        mock_httpx_cm.__aenter__.return_value = mock_httpx_cm
        patch_resp = MagicMock(spec=httpx.Response, status_code=200)
        patch_resp.raise_for_status = MagicMock()
        mock_httpx_cm.patch = AsyncMock(return_value=patch_resp)

        result = await evaluator.evaluate_site("site-002", "shadow_live")

    assert result.eligible is True
    assert result.promoted is True
    assert result.from_phase == "shadow_live"
    assert result.to_phase == "advisory"
    assert result.reason is None
    assert len(result.gates) == 3
    assert all(g.passed for g in result.gates)


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
    """All advisory gates pass → eligible and promoted."""
    client, chains = _make_supabase(
        {
            "sites": [{"id": "uuid-001", "ml_hours_ingested": 600.0}],
            "audit_log": [],
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

    with (
        patch.object(evaluator, "_ensure_config", AsyncMock()),
        patch("supabase.create_client", return_value=client),
        patch("httpx.AsyncClient") as mock_httpx,
        patch("app.services.notification_service.notification_service.send_alert_direct", AsyncMock()),
    ):
        mock_httpx_cm = AsyncMock()
        mock_httpx.return_value = mock_httpx_cm
        mock_httpx_cm.__aenter__.return_value = mock_httpx_cm
        patch_resp = MagicMock(spec=httpx.Response, status_code=200)
        patch_resp.raise_for_status = MagicMock()
        mock_httpx_cm.patch = AsyncMock(return_value=patch_resp)

        result = await evaluator.evaluate_site("site-002", "advisory")

    assert result.eligible is True
    assert result.promoted is True
    assert result.from_phase == "advisory"
    assert result.to_phase == "supervised"
    assert all(g.passed for g in result.gates)


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


# ── 5. promotes via API, not direct DB ─────────────────────────────────


@pytest.mark.asyncio
async def test_promotion_calls_api_not_direct_db(evaluator):
    """Promotion must call PATCH /api/sites/{site_id}/phase, not write DB directly."""
    client, chains = _make_supabase(
        {
            "sites": [{"id": "uuid-001", "ml_hours_ingested": 100.0}],
            "equipment_analytics": [],
        }
    )
    chains["equipment_analytics"].execute.return_value.count = 2

    api_called = False
    api_payload = None
    api_headers = None

    async def _capture_patch(url, **kwargs):
        nonlocal api_called, api_payload, api_headers
        api_called = True
        api_payload = kwargs.get("json")
        api_headers = kwargs.get("headers")
        resp = MagicMock(spec=httpx.Response, status_code=200)
        resp.raise_for_status = MagicMock()
        return resp

    with (
        patch.object(evaluator, "_ensure_config", AsyncMock()),
        patch("supabase.create_client", return_value=client),
        patch("app.services.simbiot_service.simbiot_service.get_site_status", AsyncMock(return_value={"status": "ok"})),
        patch("httpx.AsyncClient") as mock_httpx,
        patch("app.services.notification_service.notification_service.send_alert_direct", AsyncMock()),
    ):
        mock_httpx_cm = AsyncMock()
        mock_httpx.return_value = mock_httpx_cm
        mock_httpx_cm.__aenter__.return_value = mock_httpx_cm
        mock_httpx_cm.patch = AsyncMock(side_effect=_capture_patch)

        await evaluator.evaluate_site("site-002", "shadow_live")

    assert api_called, "PATCH API was not called for promotion"
    assert api_payload is not None
    assert api_payload.get("phase") == "advisory"
    assert api_payload.get("changed_by") == "phase_promotion_evaluator"
    assert api_headers is not None
    assert api_headers.get("X-Internal-Service") == "test-internal-key"


# ── 6. sends Telegram notification ─────────────────────────────────────


@pytest.mark.asyncio
async def test_promotion_sends_telegram_notification(evaluator):
    """Telegram notification should be sent on successful promotion."""
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
        patch("httpx.AsyncClient") as mock_httpx,
        patch(
            "app.services.notification_service.notification_service.send_alert_direct", side_effect=_capture_telegram
        ),
    ):
        mock_httpx_cm = AsyncMock()
        mock_httpx.return_value = mock_httpx_cm
        mock_httpx_cm.__aenter__.return_value = mock_httpx_cm
        patch_resp = MagicMock(spec=httpx.Response, status_code=200)
        patch_resp.raise_for_status = MagicMock()
        mock_httpx_cm.patch = AsyncMock(return_value=patch_resp)

        await evaluator.evaluate_site("site-002", "shadow_live")

    assert telegram_called, "Telegram notification was not sent"
    assert telegram_kwargs is not None
    assert "Phase Promotion" in telegram_kwargs.get("title", "")
    assert "shadow_live" in telegram_kwargs.get("body", "")
    assert "advisory" in telegram_kwargs.get("body", "")


# ── 7. logs to phase_transition_log (via API) ──────────────────────────


@pytest.mark.asyncio
async def test_promotion_logs_to_phase_transition_log(evaluator):
    """API endpoint should log transition to phase_transition_log table."""
    client, chains = _make_supabase(
        {
            "sites": [{"id": "uuid-001", "ml_hours_ingested": 100.0}],
            "equipment_analytics": [],
        }
    )
    chains["equipment_analytics"].execute.return_value.count = 1

    api_payload = None

    async def _capture_patch(url, **kwargs):
        nonlocal api_payload
        api_payload = kwargs.get("json")
        resp = MagicMock(spec=httpx.Response, status_code=200)
        resp.raise_for_status = MagicMock()
        return resp

    with (
        patch.object(evaluator, "_ensure_config", AsyncMock()),
        patch("supabase.create_client", return_value=client),
        patch("app.services.simbiot_service.simbiot_service.get_site_status", AsyncMock(return_value={"status": "ok"})),
        patch("httpx.AsyncClient") as mock_httpx,
        patch("app.services.notification_service.notification_service.send_alert_direct", AsyncMock()),
    ):
        mock_httpx_cm = AsyncMock()
        mock_httpx.return_value = mock_httpx_cm
        mock_httpx_cm.__aenter__.return_value = mock_httpx_cm
        mock_httpx_cm.patch = AsyncMock(side_effect=_capture_patch)

        await evaluator.evaluate_site("site-002", "shadow_live")

    assert api_payload is not None
    import json

    reason = json.loads(api_payload["reason"])
    assert reason["trigger"] == "auto_promotion"
    assert reason["from_phase"] == "shadow_live"
    assert "gate_results" in reason
    assert len(reason["gate_results"]) == 3


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
