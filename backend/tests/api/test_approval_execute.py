"""
Tests for POST /api/v1/approval/execute/{site_id} endpoint.

Phase 170-02: Control Actuation Loop — Approval Execution

Strategy: Mock at the service level (ApprovalService) rather than deep internal calls.
This tests the endpoint request/response contract and auth/RBAC logic without
needing to mock all internal dependencies.
"""

import pytest
import time
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch


@pytest.fixture
def mock_decision():
    """Sample low-risk decision (Tier 1, MEDIUM)."""
    return {
        "id": "dec-1",
        "site_id": "site-002",
        "device_id": "S002-FCU-L1-A",
        "point": "setpoint",
        "command_value": 22.0,
        "tier": 1,  # MEDIUM
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


@pytest.fixture
def mock_decision_critical():
    """High-risk decision (Tier 3, CRITICAL)."""
    return {
        "id": "dec-crit",
        "site_id": "site-002",
        "device_id": "S002-CHILLER-B1-001",
        "point": "enable",
        "command_value": False,
        "tier": 3,  # CRITICAL
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


@pytest.mark.asyncio
async def test_approval_returns_401_without_jwt(client):
    """Missing JWT token → 401 Unauthorized."""
    resp = await client.post(
        "/api/v1/approval/execute/site-002",
        json={"decision_id": "dec-1", "approval_outcome": "approved"},
        headers={},  # No Authorization header
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_approval_returns_403_for_viewer(client, auth_headers_auditor, mock_decision):
    """VIEWER/AUDITOR cannot approve → 403 Forbidden."""
    with patch(
        "app.database.repositories.parasite_decision_repository.ParasiteDecisionRepository.get_decision_by_id",
        new_callable=AsyncMock,
        return_value=mock_decision,
    ):
        with patch(
            "app.services.approval_service.ApprovalService.execute_decision_with_audit",
            new_callable=AsyncMock,
        ) as mock_execute:
            # Endpoint should reject before calling service
            resp = await client.post(
                "/api/v1/approval/execute/site-002",
                json={"decision_id": "dec-1", "approval_outcome": "approved"},
                headers=auth_headers_auditor,
            )
            assert resp.status_code == 403
            assert not mock_execute.called


@pytest.mark.asyncio
async def test_approval_returns_accepted_immediately(client, auth_headers_operator, mock_decision):
    """
    Correction #1: Verify response is NOT blocking on 30s verification.
    Must return ACCEPTED in < 500ms.
    """
    # Mock the service to return success
    mock_response = {
        "status": "ACCEPTED",
        "decision_id": "dec-1",
        "correlation_id": "corr-xyz",
        "message": "Command dispatched. Awaiting verification.",
        "estimated_verification_time_seconds": 30,
    }

    with patch(
        "app.services.approval_service.ApprovalService.execute_decision_with_audit",
        new_callable=AsyncMock,
        return_value=mock_response,
    ):
        with patch(
            "app.database.repositories.parasite_decision_repository.ParasiteDecisionRepository.get_decision_by_id",
            new_callable=AsyncMock,
            return_value=mock_decision,
        ):
            start = time.time()
            resp = await client.post(
                "/api/v1/approval/execute/site-002",
                json={"decision_id": "dec-1", "approval_outcome": "approved"},
                headers=auth_headers_operator,
            )
            elapsed = time.time() - start

            # Response must come back in < 500ms
            assert elapsed < 0.5, f"Response took {elapsed}s, expected < 0.5s"
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "ACCEPTED"
            assert "decision_id" in data
            assert "correlation_id" in data
            assert data["estimated_verification_time_seconds"] == 30


@pytest.mark.asyncio
async def test_approval_returns_404_not_found(client, auth_headers_operator):
    """Decision not found → 404 Not Found."""
    with patch(
        "app.database.repositories.parasite_decision_repository.ParasiteDecisionRepository.get_decision_by_id",
        new_callable=AsyncMock,
        return_value=None,  # Decision not found
    ):
        resp = await client.post(
            "/api/v1/approval/execute/site-002",
            json={"decision_id": "nonexistent", "approval_outcome": "approved"},
            headers=auth_headers_operator,
        )
        assert resp.status_code == 404


@pytest.mark.asyncio
async def test_approval_returns_403_operator_cannot_approve_critical(
    client, auth_headers_operator, mock_decision_critical
):
    """OPERATOR cannot approve Tier 3 (CRITICAL) → 403 Forbidden."""
    with patch(
        "app.database.repositories.parasite_decision_repository.ParasiteDecisionRepository.get_decision_by_id",
        new_callable=AsyncMock,
        return_value=mock_decision_critical,
    ):
        resp = await client.post(
            "/api/v1/approval/execute/site-002",
            json={"decision_id": "dec-crit", "approval_outcome": "approved"},
            headers=auth_headers_operator,
        )
        assert resp.status_code == 403


@pytest.mark.asyncio
async def test_approval_engineer_can_approve_critical(client, auth_headers_engineer, mock_decision_critical):
    """ENGINEER can approve Tier 3 (CRITICAL) → 200 OK."""
    mock_response = {
        "status": "ACCEPTED",
        "decision_id": "dec-crit",
        "correlation_id": "corr-xyz",
        "message": "Command dispatched. Awaiting verification.",
        "estimated_verification_time_seconds": 30,
    }

    with patch(
        "app.services.approval_service.ApprovalService.execute_decision_with_audit",
        new_callable=AsyncMock,
        return_value=mock_response,
    ):
        with patch(
            "app.database.repositories.parasite_decision_repository.ParasiteDecisionRepository.get_decision_by_id",
            new_callable=AsyncMock,
            return_value=mock_decision_critical,
        ):
            resp = await client.post(
                "/api/v1/approval/execute/site-002",
                json={"decision_id": "dec-crit", "approval_outcome": "approved"},
                headers=auth_headers_engineer,
            )
            assert resp.status_code == 200
            assert resp.json()["status"] == "ACCEPTED"


@pytest.mark.asyncio
async def test_approval_admin_can_approve_any_tier(client, auth_headers_admin, mock_decision_critical):
    """ADMIN can approve any tier → 200 OK."""
    mock_response = {
        "status": "ACCEPTED",
        "decision_id": "dec-crit",
        "correlation_id": "corr-xyz",
        "message": "Command dispatched. Awaiting verification.",
        "estimated_verification_time_seconds": 30,
    }

    with patch(
        "app.services.approval_service.ApprovalService.execute_decision_with_audit",
        new_callable=AsyncMock,
        return_value=mock_response,
    ):
        with patch(
            "app.database.repositories.parasite_decision_repository.ParasiteDecisionRepository.get_decision_by_id",
            new_callable=AsyncMock,
            return_value=mock_decision_critical,
        ):
            resp = await client.post(
                "/api/v1/approval/execute/site-002",
                json={"decision_id": "dec-crit", "approval_outcome": "approved"},
                headers=auth_headers_admin,
            )
            assert resp.status_code == 200
            assert resp.json()["status"] == "ACCEPTED"


@pytest.mark.asyncio
async def test_approval_endpoint_route_exists(client, auth_headers_operator):
    """Endpoint route is registered and reachable."""
    with patch(
        "app.database.repositories.parasite_decision_repository.ParasiteDecisionRepository.get_decision_by_id",
        new_callable=AsyncMock,
        return_value={"id": "dec-1", "site_id": "site-002", "tier": 1},
    ):
        with patch(
            "app.services.approval_service.ApprovalService.execute_decision_with_audit",
            new_callable=AsyncMock,
            return_value={
                "status": "ACCEPTED",
                "decision_id": "dec-1",
                "correlation_id": "corr-xyz",
                "message": "OK",
                "estimated_verification_time_seconds": 30,
            },
        ):
            # Should not raise 404 route not found
            resp = await client.post(
                "/api/v1/approval/execute/site-002",
                json={"decision_id": "dec-1", "approval_outcome": "approved"},
                headers=auth_headers_operator,
            )
            # Either 200 or some expected error (not 404)
            assert resp.status_code in [200, 422, 409, 500]
