"""Integration tests for drift→trust in readiness endpoint (Phase 240 M2.3).

Tests that GET /readiness includes trust_confidence, trust_breakdown, and
equipment_findings for operator visibility.
"""

import os

import pytest

# Skip these tests if not in TESTING mode
pytestmark = pytest.mark.skipif(
    not os.getenv("TESTING"),
    reason="Integration tests only run with TESTING=true",
)


@pytest.mark.asyncio
async def test_readiness_endpoint_includes_trust_confidence(client, supabase_client):
    """GET /readiness returns trust_confidence score."""
    # Ensure site-002 exists in testing environment
    site_id = "site-002"

    # Call readiness endpoint
    response = client.get(
        f"/api/sites/{site_id}/readiness",
        headers={"Authorization": "Bearer test_token"},
    )

    assert response.status_code == 200
    data = response.json()

    # Verify trust_confidence is present
    assert "trust_confidence" in data
    assert isinstance(data["trust_confidence"], (int, float))
    assert 0.0 <= data["trust_confidence"] <= 1.0


@pytest.mark.asyncio
async def test_readiness_endpoint_includes_trust_breakdown(client, supabase_client):
    """GET /readiness returns trust_breakdown with formula."""
    site_id = "site-002"

    response = client.get(
        f"/api/sites/{site_id}/readiness",
        headers={"Authorization": "Bearer test_token"},
    )

    assert response.status_code == 200
    data = response.json()

    # Verify trust_breakdown structure
    assert "trust_breakdown" in data
    breakdown = data["trust_breakdown"]
    assert "base_trust" in breakdown
    assert "drift_penalty" in breakdown
    assert "formula" in breakdown
    assert breakdown["formula"] == "base_trust * (1.0 - drift_penalty)"


@pytest.mark.asyncio
async def test_readiness_endpoint_includes_equipment_findings(client, supabase_client):
    """GET /readiness returns equipment_findings array."""
    site_id = "site-002"

    response = client.get(
        f"/api/sites/{site_id}/readiness",
        headers={"Authorization": "Bearer test_token"},
    )

    assert response.status_code == 200
    data = response.json()

    # Verify equipment_findings is present and is a list
    assert "equipment_findings" in data
    assert isinstance(data["equipment_findings"], list)

    # Each finding should have required fields
    for finding in data["equipment_findings"]:
        assert "equipment_id" in finding
        assert "equipment_type" in finding
        assert "drift_verdict" in finding
        assert "finding_type" in finding


@pytest.mark.asyncio
async def test_readiness_includes_satisfied_and_not_satisfied(client):
    """GET /readiness includes gate breakdown alongside trust metrics."""
    site_id = "site-002"

    response = client.get(
        f"/api/sites/{site_id}/readiness",
        headers={"Authorization": "Bearer test_token"},
    )

    assert response.status_code == 200
    data = response.json()

    # Verify both gate breakdown AND trust metrics are present
    assert "satisfied" in data
    assert "not_satisfied" in data
    assert "trust_confidence" in data
    assert "trust_breakdown" in data

    # satisfied/not_satisfied should be lists of gate results
    assert isinstance(data["satisfied"], list)
    assert isinstance(data["not_satisfied"], list)

    # Each gate result should have structure
    for gate in data["satisfied"] + data["not_satisfied"]:
        assert "gate" in gate
        assert "passed" in gate
