"""Tests for Digital Twin SSE equipment status streaming endpoint.

Validates the SSE endpoint returns correct content-type, valid frames,
and handles ticket-based authentication in demo mode.
"""

import os
import pytest
from unittest.mock import patch

os.environ.setdefault("DEMO_MODE", "true")
os.environ.setdefault("TESTING", "true")


@pytest.mark.asyncio
async def test_status_ticket_returns_200():
    """POST /api/digital-twin/status/ticket returns a ticket in demo mode."""
    from httpx import AsyncClient, ASGITransport
    from tests.conftest import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/digital-twin/status/ticket")

    assert response.status_code == 200
    data = response.json()
    assert "ticket" in data
    assert len(data["ticket"]) > 0


@pytest.mark.asyncio
async def test_status_stream_returns_sse_content_type():
    """GET /api/digital-twin/status/stream returns text/event-stream content type."""
    from httpx import AsyncClient, ASGITransport
    from tests.conftest import app

    # First get a ticket
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        ticket_resp = await client.post("/api/digital-twin/status/ticket")
        ticket = ticket_resp.json()["ticket"]

    # Mock the streamer to return a single frame then stop
    async def mock_stream(site_id):
        yield 'data: {"type": "connected", "data": {}}\n\n'

    with patch("app.api.digital_twin.EquipmentStatusStreamer") as MockStreamer:
        instance = MockStreamer.return_value
        instance.stream_status = mock_stream

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(f"/api/digital-twin/status/stream?site_id=site-001&ticket={ticket}")

    assert response.status_code == 200
    assert "text/event-stream" in response.headers.get("content-type", "")


@pytest.mark.asyncio
async def test_status_stream_without_ticket_fails_in_non_demo():
    """GET /api/digital-twin/status/stream returns 401 without ticket (non-demo mode)."""
    from httpx import AsyncClient, ASGITransport
    from tests.conftest import app

    transport = ASGITransport(app=app)

    with patch.dict(os.environ, {"DEMO_MODE": "false"}):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/digital-twin/status/stream?site_id=site-001")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_status_stream_returns_valid_json_frames():
    """SSE stream should return parseable JSON data frames."""
    import json
    from httpx import AsyncClient, ASGITransport
    from tests.conftest import app

    transport = ASGITransport(app=app)

    # Get a ticket
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        ticket_resp = await client.post("/api/digital-twin/status/ticket")
        ticket = ticket_resp.json()["ticket"]

    # Mock streamer to return a proper frame
    frame_data = {
        "site_id": "site-001",
        "equipment_updates": [
            {
                "equipment_id": "eq-001",
                "code": "S002-AHU-B1-001",
                "type": "ahu",
                "health_score": 85.0,
                "status": "online",
                "power_kw": 12.5,
                "temperatures": None,
                "timestamp": "2026-03-14T10:00:00",
            }
        ],
        "predictions": [],
        "timestamp": "2026-03-14T10:00:00",
    }

    async def mock_stream(site_id):
        yield f"data: {json.dumps(frame_data)}\n\n"

    with patch("app.api.digital_twin.EquipmentStatusStreamer") as MockStreamer:
        instance = MockStreamer.return_value
        instance.stream_status = mock_stream

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(f"/api/digital-twin/status/stream?site_id=site-001&ticket={ticket}")

    assert response.status_code == 200
    # Parse the SSE data
    text = response.text
    assert "data:" in text
    # Extract JSON from SSE format
    for line in text.strip().split("\n"):
        if line.startswith("data:"):
            json_str = line[len("data:") :].strip()
            parsed = json.loads(json_str)
            assert "site_id" in parsed
            assert "equipment_updates" in parsed


@pytest.mark.asyncio
async def test_status_ticket_consumed_on_use():
    """Ticket should be single-use (consumed after first stream connection)."""
    from httpx import AsyncClient, ASGITransport
    from tests.conftest import app

    transport = ASGITransport(app=app)

    # Get a ticket
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        ticket_resp = await client.post("/api/digital-twin/status/ticket")
        ticket = ticket_resp.json()["ticket"]

    # Use the ticket once (mock stream)
    async def mock_stream(site_id):
        yield 'data: {"type": "connected"}\n\n'

    with patch("app.api.digital_twin.EquipmentStatusStreamer") as MockStreamer:
        instance = MockStreamer.return_value
        instance.stream_status = mock_stream

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            first = await client.get(f"/api/digital-twin/status/stream?site_id=site-001&ticket={ticket}")
            assert first.status_code == 200

            # Second use should fail (ticket consumed) -- in non-demo mode
            with patch.dict(os.environ, {"DEMO_MODE": "false"}):
                second = await client.get(f"/api/digital-twin/status/stream?site_id=site-001&ticket={ticket}")
                assert second.status_code == 401
