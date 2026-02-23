"""Tests for POPIA privacy request workflow endpoints."""

import uuid

import pytest


@pytest.mark.asyncio
async def test_create_and_fetch_privacy_request(client):
    """Create privacy request and fetch it by id."""
    payload = {
        "request_type": "access",
        "channel": "api",
        "details": f"Export my data for review {uuid.uuid4()}",
    }
    create_resp = await client.post("/api/privacy/requests", json=payload)
    assert create_resp.status_code == 200
    created = create_resp.json()
    assert created["request_type"] == "access"
    assert created["status"] == "pending"

    request_id = created["request_id"]
    get_resp = await client.get(f"/api/privacy/requests/{request_id}")
    assert get_resp.status_code == 200
    loaded = get_resp.json()
    assert loaded["request_id"] == request_id
    assert loaded["due_at"]


@pytest.mark.asyncio
async def test_update_privacy_request_status(client):
    """Update status should move request to fulfilled with closure timestamp."""
    create_resp = await client.post(
        "/api/privacy/requests",
        json={"request_type": "deletion", "channel": "api", "details": "Delete my historical profile data"},
    )
    assert create_resp.status_code == 200
    request_id = create_resp.json()["request_id"]

    update_resp = await client.post(
        f"/api/privacy/requests/{request_id}/status",
        json={"status": "fulfilled", "outcome_summary": "Processed and completed"},
    )
    assert update_resp.status_code == 200
    updated = update_resp.json()
    assert updated["status"] == "fulfilled"
    assert updated["closed_at"] is not None


@pytest.mark.asyncio
async def test_privacy_metrics_and_retention_status(client):
    """Metrics and retention status endpoints should respond with summary objects."""
    metrics_resp = await client.get("/api/privacy/requests-metrics")
    assert metrics_resp.status_code == 200
    metrics = metrics_resp.json()
    assert "total_requests" in metrics
    assert "sla_compliance_percent" in metrics

    retention_resp = await client.get("/api/privacy/retention/status")
    assert retention_resp.status_code == 200
    retention = retention_resp.json()
    assert "categories" in retention
    assert "records_overdue" in retention
