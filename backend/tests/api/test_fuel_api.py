"""Tests for Fuel API endpoints (Phase 150).

Tests all 6 fuel API routes using TestClient with mocked FuelStore
and data files.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.fuel import router
from app.models.fuel import FuelTankConfig, FuelTelemetry

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def app():
    """Create a FastAPI app with fuel router."""
    _app = FastAPI()
    _app.include_router(router)
    return _app


@pytest.fixture
def client(app):
    """TestClient for fuel API."""
    return TestClient(app)


@pytest.fixture
def sample_tank_config():
    return FuelTankConfig(
        tank_id="S002-TANK-EXT-001",
        site_id="site-002",
        generator_id="S002-GEN-B1-001",
        capacity_litres=5000,
        tank_height_mm=2000,
        low_alert_pct_1=30.0,
        low_alert_pct_2=15.0,
        theft_rate_threshold_lpm=2.0,
        consumption_spec_lph=45.0,
    )


@pytest.fixture
def sample_telemetry():
    return FuelTelemetry(
        node_id="ESP32-FUEL-001",
        site_id="site-002",
        tank_id="S002-TANK-EXT-001",
        generator_id="S002-GEN-B1-001",
        fuel_level_pct=72.5,
        fuel_level_litres=3625.0,
        fuel_temp_c=25.0,
        consumption_rate_lph=12.5,
        days_to_empty=12.1,
        ts=1710100000,
        received_at=datetime(2026, 3, 11, 10, 0, 0, tzinfo=UTC),
    )


def _mock_store(tank_config=None, telemetry=None):
    """Build a mock FuelStore."""
    store = MagicMock()
    configs = [tank_config] if tank_config else []
    store.get_all_tanks.return_value = configs
    store.get_tank_config.return_value = tank_config
    store.get_latest_telemetry = AsyncMock(return_value=telemetry)
    return store


# ---------------------------------------------------------------------------
# GET /api/fuel/tanks
# ---------------------------------------------------------------------------


class TestListTanks:
    def test_returns_empty_list_when_no_tanks(self, client):
        with patch("app.api.fuel._get_fuel_store", return_value=_mock_store()):
            resp = client.get("/api/fuel/tanks")
        assert resp.status_code == 200
        data = resp.json()
        assert data["tanks"] == []
        assert data["count"] == 0

    def test_returns_tanks_with_telemetry(self, client, sample_tank_config, sample_telemetry):
        with patch("app.api.fuel._get_fuel_store", return_value=_mock_store(sample_tank_config, sample_telemetry)):
            resp = client.get("/api/fuel/tanks")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        tank = data["tanks"][0]
        assert tank["tank_id"] == "S002-TANK-EXT-001"
        assert tank["latest_telemetry"]["fuel_level_pct"] == 72.5

    def test_filters_by_site_id(self, client, sample_tank_config, sample_telemetry):
        store = _mock_store(sample_tank_config, sample_telemetry)
        with patch("app.api.fuel._get_fuel_store", return_value=store):
            resp = client.get("/api/fuel/tanks?site_id=site-002")
        assert resp.status_code == 200
        store.get_all_tanks.assert_called_once_with(site_id="site-002")


# ---------------------------------------------------------------------------
# GET /api/fuel/tanks/{tank_id}
# ---------------------------------------------------------------------------


class TestGetTank:
    def test_returns_tank_detail(self, client, sample_tank_config, sample_telemetry):
        with patch("app.api.fuel._get_fuel_store", return_value=_mock_store(sample_tank_config, sample_telemetry)):
            resp = client.get("/api/fuel/tanks/S002-TANK-EXT-001")
        assert resp.status_code == 200
        data = resp.json()
        assert data["tank_id"] == "S002-TANK-EXT-001"
        assert data["latest_telemetry"]["fuel_level_pct"] == 72.5

    def test_404_for_unknown_tank(self, client):
        with patch("app.api.fuel._get_fuel_store", return_value=_mock_store()):
            resp = client.get("/api/fuel/tanks/UNKNOWN-TANK")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/fuel/tanks/{tank_id}/history
# ---------------------------------------------------------------------------


class TestTankHistory:
    def test_returns_history(self, client, sample_tank_config, tmp_path):
        store = _mock_store(sample_tank_config)
        records = [
            {"tank_id": "S002-TANK-EXT-001", "ts": 9999999999, "fuel_level_pct": 70.0},
            {"tank_id": "S002-TANK-EXT-001", "ts": 9999999998, "fuel_level_pct": 71.0},
        ]
        telemetry_file = tmp_path / "telemetry.json"
        with open(telemetry_file, "w") as fh:
            for r in records:
                fh.write(json.dumps(r) + "\n")

        with (
            patch("app.api.fuel._get_fuel_store", return_value=store),
            patch("app.api.fuel._TELEMETRY_FILE", telemetry_file),
        ):
            resp = client.get("/api/fuel/tanks/S002-TANK-EXT-001/history?hours=24")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 2

    def test_404_for_unknown_tank(self, client):
        with patch("app.api.fuel._get_fuel_store", return_value=_mock_store()):
            resp = client.get("/api/fuel/tanks/UNKNOWN/history")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/fuel/events
# ---------------------------------------------------------------------------


class TestListEvents:
    def test_returns_events(self, client, tmp_path):
        events_file = tmp_path / "events.json"
        events = [
            {"event_type": "theft_alert", "site_id": "site-002", "tank_id": "T1", "ts": 100},
            {"event_type": "low_fuel", "site_id": "site-002", "tank_id": "T1", "ts": 200},
        ]
        with open(events_file, "w") as fh:
            for e in events:
                fh.write(json.dumps(e) + "\n")

        with patch("app.api.fuel._EVENTS_FILE", events_file):
            resp = client.get("/api/fuel/events")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 2
        # Most recent first
        assert data["events"][0]["ts"] == 200

    def test_filters_by_event_type(self, client, tmp_path):
        events_file = tmp_path / "events.json"
        events = [
            {"event_type": "theft_alert", "site_id": "site-002", "ts": 100},
            {"event_type": "low_fuel", "site_id": "site-002", "ts": 200},
        ]
        with open(events_file, "w") as fh:
            for e in events:
                fh.write(json.dumps(e) + "\n")

        with patch("app.api.fuel._EVENTS_FILE", events_file):
            resp = client.get("/api/fuel/events?event_type=theft_alert")
        assert resp.status_code == 200
        assert resp.json()["count"] == 1

    def test_empty_when_no_file(self, client, tmp_path):
        missing_file = tmp_path / "nonexistent.json"
        with patch("app.api.fuel._EVENTS_FILE", missing_file):
            resp = client.get("/api/fuel/events")
        assert resp.status_code == 200
        assert resp.json()["count"] == 0


# ---------------------------------------------------------------------------
# GET /api/fuel/generator-runtime
# ---------------------------------------------------------------------------


class TestGeneratorRuntime:
    def test_returns_runtime_sessions(self, client, tmp_path):
        events_file = tmp_path / "events.json"
        events = [
            {"event_type": "runtime_complete", "site_id": "site-002", "ts": 100, "payload": {}},
            {"event_type": "theft_alert", "site_id": "site-002", "ts": 200},
        ]
        with open(events_file, "w") as fh:
            for e in events:
                fh.write(json.dumps(e) + "\n")

        with patch("app.api.fuel._EVENTS_FILE", events_file):
            resp = client.get("/api/fuel/generator-runtime")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        assert data["sessions"][0]["event_type"] == "runtime_complete"


# ---------------------------------------------------------------------------
# GET /api/fuel/refill-log
# ---------------------------------------------------------------------------


class TestRefillLog:
    def test_returns_refill_events(self, client, tmp_path):
        events_file = tmp_path / "events.json"
        events = [
            {"event_type": "refill_detected", "site_id": "site-002", "ts": 300},
            {"event_type": "theft_alert", "site_id": "site-002", "ts": 200},
            {"event_type": "refill_detected", "site_id": "site-002", "ts": 100},
        ]
        with open(events_file, "w") as fh:
            for e in events:
                fh.write(json.dumps(e) + "\n")

        with patch("app.api.fuel._EVENTS_FILE", events_file):
            resp = client.get("/api/fuel/refill-log")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 2
        assert data["refills"][0]["ts"] == 300
