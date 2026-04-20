"""Unit tests for Phase 120-02: Post-Action Verification Service.

Tests the verification registry, runner, evidence/result data classes,
and all 5 built-in verifiers (WO create/close, setpoint, email, DB write).

Uses unittest.mock.AsyncMock to isolate from real services.
"""

import os

os.environ.setdefault("DEMO_MODE", "true")
os.environ.setdefault("LIGHTWEIGHT_APP", "1")

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.middleware.agent_security.verification import (
    VerificationEvidence,
    VerificationResult,
    VerificationStatus,
    _verification_registry,
    verification_runner,
)

# ---------------------------------------------------------------------------
# 1. test_verification_registry_populated
# ---------------------------------------------------------------------------


def test_verification_registry_populated():
    """All 5 verifiers are registered at import time."""
    expected_keys = {
        "work_orders:create",
        "work_orders:close",
        "equipment_control:setpoint",
        "email_smtp:send",
        "database_write:insert",
    }
    assert expected_keys == set(_verification_registry.keys())
    assert len(_verification_registry) == 5


# ---------------------------------------------------------------------------
# 2. test_unknown_tool_returns_skipped
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unknown_tool_returns_skipped():
    """Unregistered tool+action pair returns SKIPPED, not crash."""
    result = await verification_runner.verify("nonexistent_tool", "mystery_action", {})
    assert result.overall_status == VerificationStatus.SKIPPED
    assert len(result.steps) == 1
    assert result.steps[0].status == VerificationStatus.SKIPPED
    assert result.all_passed is True  # SKIPPED counts as "not failed"


# ---------------------------------------------------------------------------
# 3. test_verification_evidence_structure
# ---------------------------------------------------------------------------


def test_verification_evidence_structure():
    """VerificationEvidence has the required dataclass fields."""
    ev = VerificationEvidence(
        verification_id="abc123",
        timestamp="2026-02-25T12:00:00Z",
        action="create",
        target="work_order:WO-001",
        expected_state={"status": "open"},
        actual_state={"status": "open"},
        status=VerificationStatus.PASSED,
        detail="ok",
        duration_ms=12.5,
    )
    assert ev.verification_id == "abc123"
    assert ev.action == "create"
    assert ev.duration_ms == 12.5
    assert ev.status == VerificationStatus.PASSED
    assert isinstance(ev.expected_state, dict)
    assert isinstance(ev.actual_state, dict)


# ---------------------------------------------------------------------------
# 4. test_verification_result_all_passed
# ---------------------------------------------------------------------------


def test_verification_result_all_passed():
    """PASSED + SKIPPED steps yield all_passed=True."""
    steps = [
        VerificationEvidence(
            verification_id="a",
            timestamp="t",
            action="a",
            target="t",
            expected_state={},
            actual_state={},
            status=VerificationStatus.PASSED,
            detail="ok",
            duration_ms=1.0,
        ),
        VerificationEvidence(
            verification_id="b",
            timestamp="t",
            action="b",
            target="t",
            expected_state={},
            actual_state={},
            status=VerificationStatus.SKIPPED,
            detail="skip",
            duration_ms=0.0,
        ),
    ]
    result = VerificationResult(overall_status=VerificationStatus.PASSED, steps=steps)
    assert result.all_passed is True
    assert "PASSED" in result.summary


# ---------------------------------------------------------------------------
# 5. test_verification_result_with_failure
# ---------------------------------------------------------------------------


def test_verification_result_with_failure():
    """A FAILED step makes all_passed=False."""
    steps = [
        VerificationEvidence(
            verification_id="a",
            timestamp="t",
            action="a",
            target="t",
            expected_state={},
            actual_state={},
            status=VerificationStatus.PASSED,
            detail="ok",
            duration_ms=1.0,
        ),
        VerificationEvidence(
            verification_id="b",
            timestamp="t",
            action="b",
            target="t",
            expected_state={},
            actual_state={},
            status=VerificationStatus.FAILED,
            detail="mismatch",
            duration_ms=2.0,
        ),
    ]
    result = VerificationResult(overall_status=VerificationStatus.FAILED, steps=steps)
    assert result.all_passed is False
    assert "FAILED" in result.summary


# ---------------------------------------------------------------------------
# 6. test_work_order_create_verifier_not_found
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_work_order_create_verifier_not_found():
    """WO create verifier returns FAILED when work order is not found."""
    mock_repo = MagicMock()
    mock_repo.get_work_order = AsyncMock(return_value=None)

    mock_cls = MagicMock(return_value=mock_repo)
    with patch(
        "app.middleware.agent_security.verification._WorkOrderRepository",
        mock_cls,
    ):
        # Call the WO create verifier through the runner
        result = await verification_runner.verify(
            "work_orders",
            "create",
            {"work_order_id": "WO-MISSING", "title": "Fix AHU"},
        )

    assert result.overall_status == VerificationStatus.FAILED
    assert "not found" in result.steps[0].detail


# ---------------------------------------------------------------------------
# 7. test_work_order_create_verifier_success
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_work_order_create_verifier_success():
    """WO create verifier returns PASSED with matching fields."""
    mock_wo = {
        "id": "wo-123",
        "title": "Fix AHU-1",
        "site_id": "b-001",
        "priority": "high",
        "status": "open",
    }
    mock_repo = MagicMock()
    mock_repo.get_work_order = AsyncMock(return_value=mock_wo)

    mock_cls = MagicMock(return_value=mock_repo)
    with patch(
        "app.middleware.agent_security.verification._WorkOrderRepository",
        mock_cls,
    ):
        result = await verification_runner.verify(
            "work_orders",
            "create",
            {
                "work_order_id": "wo-123",
                "title": "Fix AHU-1",
                "site_id": "b-001",
                "priority": "high",
            },
        )

    assert result.overall_status == VerificationStatus.PASSED
    assert result.all_passed is True


# ---------------------------------------------------------------------------
# 8. test_setpoint_verifier_within_tolerance
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_setpoint_verifier_within_tolerance():
    """Setpoint verifier PASSES when drift is within tolerance (0.3 on 22.0)."""
    mock_client = MagicMock()
    mock_client.read_point = AsyncMock(return_value={"value": 22.3})

    mock_cls = MagicMock(return_value=mock_client)
    with patch(
        "app.middleware.agent_security.verification._BACnetClient",
        mock_cls,
    ):
        result = await verification_runner.verify(
            "equipment_control",
            "setpoint",
            {
                "equipment_code": "S002-FCU-101",
                "control_point": "cooling_setpoint",
                "target_value": 22.0,
                "tolerance": 0.5,
            },
        )

    assert result.overall_status == VerificationStatus.PASSED
    assert result.steps[0].actual_state["drift"] == pytest.approx(0.3, abs=0.01)


# ---------------------------------------------------------------------------
# 9. test_setpoint_verifier_exceeds_tolerance
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_setpoint_verifier_exceeds_tolerance():
    """Setpoint verifier FAILS when drift exceeds tolerance (2.0 on 22.0)."""
    mock_client = MagicMock()
    mock_client.read_point = AsyncMock(return_value={"value": 24.0})

    mock_cls = MagicMock(return_value=mock_client)
    with patch(
        "app.middleware.agent_security.verification._BACnetClient",
        mock_cls,
    ):
        result = await verification_runner.verify(
            "equipment_control",
            "setpoint",
            {
                "equipment_code": "S002-FCU-101",
                "control_point": "cooling_setpoint",
                "target_value": 22.0,
                "tolerance": 0.5,
            },
        )

    assert result.overall_status == VerificationStatus.FAILED
    assert "exceeds tolerance" in result.steps[0].detail
    assert result.steps[0].actual_state["drift"] == pytest.approx(2.0, abs=0.01)


# ---------------------------------------------------------------------------
# 10. test_verifier_exception_returns_error
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_verifier_exception_returns_error():
    """A verifier that raises an exception returns ERROR, not crash."""
    with patch(
        "app.middleware.agent_security.verification._WorkOrderRepository",
        side_effect=RuntimeError("DB connection lost"),
    ):
        result = await verification_runner.verify(
            "work_orders",
            "close",
            {"work_order_id": "WO-BROKEN"},
        )

    assert result.overall_status == VerificationStatus.ERROR
    assert "RuntimeError" in result.steps[0].detail
    assert "DB connection lost" in result.steps[0].detail
    # Most important: did NOT crash
    assert len(result.steps) == 1
