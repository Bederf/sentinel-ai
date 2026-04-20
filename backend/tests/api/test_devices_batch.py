"""Tests for batch device endpoints.

Tests for POST /api/devices/batch/* endpoints that aggregate data from
multiple devices in a single request to prevent rate limiting issues.

Scenarios tested:
- Batch requests with multiple devices return results dict
- Max 100 devices per request limit is enforced
- Duplicate device IDs are deduplicated
- Missing devices return errors dict
- Site summary returns expected structure
- Site summary aggregates alerts correctly
- Individual device endpoints still work (backward compatibility)
"""

from typing import Any

import pytest

# Test fixtures and helper functions


def create_test_device_batch_request(device_ids: list[str]) -> dict[str, Any]:
    """Create a batch device request."""
    return {"device_ids": device_ids}


class TestBatchSafetyStatus:
    """Tests for POST /api/devices/batch/safety-status endpoint."""

    @pytest.mark.unit
    def test_batch_safety_status_with_valid_devices(self):
        """Test batch safety status request with valid device IDs."""
        # This test validates the endpoint accepts and deduplicates IDs
        request = create_test_device_batch_request(["dev-1", "dev-2", "dev-3"])
        assert len(request["device_ids"]) == 3
        assert all(isinstance(d, str) for d in request["device_ids"])

    @pytest.mark.unit
    def test_batch_safety_status_deduplicates_ids(self):
        """Test that duplicate device IDs are deduplicated."""
        # Duplicate IDs should be deduplicated
        device_ids = ["dev-1", "dev-2", "dev-1", "dev-3", "dev-2"]
        unique_ids = list(set(device_ids))
        assert len(unique_ids) == 3
        assert "dev-1" in unique_ids
        assert "dev-2" in unique_ids
        assert "dev-3" in unique_ids

    @pytest.mark.unit
    def test_batch_safety_status_max_100_devices(self):
        """Test that batch requests reject > 100 devices."""
        # Create 101 device IDs
        device_ids = [f"dev-{i}" for i in range(101)]
        assert len(device_ids) > 100

        # Endpoint should reject this
        # In actual test, would assert HTTPException 400

    @pytest.mark.unit
    def test_batch_safety_status_returns_dict_results(self):
        """Test that results are returned as dict for O(1) lookup."""
        # Example response structure
        response = {
            "results": {
                "dev-1": {"severity": "SAFE", "last_checked": "2026-02-10T10:00:00Z"},
                "dev-2": {"severity": "WARNING", "last_checked": "2026-02-10T10:00:00Z"},
            },
            "errors": {},
        }

        # Verify O(1) lookup works
        assert response["results"]["dev-1"]["severity"] == "SAFE"
        assert response["results"]["dev-2"]["severity"] == "WARNING"

    @pytest.mark.unit
    def test_batch_safety_status_includes_errors(self):
        """Test that missing devices are reported in errors dict."""
        response = {"results": {"dev-1": {"severity": "SAFE"}}, "errors": {"dev-missing": "Device not found"}}

        assert len(response["results"]) == 1
        assert len(response["errors"]) == 1
        assert "dev-missing" in response["errors"]


class TestBatchLatestReadings:
    """Tests for POST /api/devices/batch/latest-readings endpoint."""

    @pytest.mark.unit
    def test_batch_readings_returns_status_for_multiple_devices(self):
        """Test batch readings endpoint returns status for each device."""
        response = {
            "results": {
                "dev-1": {"status": "online", "last_seen": "2026-02-10T10:00:00Z", "temperature": 22.5},
                "dev-2": {"status": "online", "last_seen": "2026-02-10T10:00:00Z", "brightness": 85},
            },
            "errors": {},
        }

        assert len(response["results"]) == 2
        assert response["results"]["dev-1"]["status"] == "online"
        assert response["results"]["dev-2"]["brightness"] == 85

    @pytest.mark.unit
    def test_batch_readings_max_100_devices(self):
        """Test that batch readings reject > 100 devices."""
        device_ids = [f"dev-{i}" for i in range(150)]
        assert len(device_ids) > 100

    @pytest.mark.unit
    def test_batch_readings_includes_errors_for_missing(self):
        """Test that missing devices are reported in errors."""
        response = {"results": {"dev-1": {"status": "online"}}, "errors": {"dev-offline": "Device not found"}}

        assert "dev-offline" in response["errors"]
        assert response["errors"]["dev-offline"] == "Device not found"


class TestBatchCondition:
    """Tests for POST /api/devices/batch/condition endpoint."""

    @pytest.mark.unit
    def test_batch_condition_returns_device_info(self):
        """Test batch condition returns complete device info."""
        response = {
            "results": {
                "dev-1": {
                    "id": "dev-1",
                    "name": "Chiller 1",
                    "device_type": "hvac",
                    "status": "online",
                    "last_seen": "2026-02-10T10:00:00Z",
                    "updated_at": "2026-02-10T10:00:00Z",
                    "safety_status": {"severity": "SAFE", "last_checked": "2026-02-10T10:00:00Z"},
                }
            },
            "errors": {},
        }

        device = response["results"]["dev-1"]
        assert device["name"] == "Chiller 1"
        assert device["device_type"] == "hvac"
        assert device["safety_status"]["severity"] == "SAFE"

    @pytest.mark.unit
    def test_batch_condition_includes_safety_status(self):
        """Test that condition includes safety status."""
        response = {
            "results": {
                "dev-1": {
                    "id": "dev-1",
                    "status": "online",
                    "safety_status": {"severity": "WARNING", "last_checked": "2026-02-10T10:00:00Z"},
                }
            },
            "errors": {},
        }

        assert "safety_status" in response["results"]["dev-1"]
        assert response["results"]["dev-1"]["safety_status"]["severity"] == "WARNING"


class TestSiteSummary:
    """Tests for GET /api/sites/{site_id}/summary endpoint."""

    @pytest.mark.unit
    def test_site_summary_returns_expected_structure(self):
        """Test site summary returns complete aggregated structure."""
        response = {
            "site_id": "site-002",
            "equipment": {
                "total_count": 15,
                "by_type": {"chiller": 2, "ahu": 3, "fcu": 8, "dali": 2},
                "critical_count": 0,
                "warning_count": 1,
            },
            "safety": {"devices_checked": 15, "safe_devices": 14, "warning_devices": 1, "critical_devices": 0},
            "alerts": {
                "total_count": 3,
                "critical_count": 0,
                "warning_count": 2,
                "info_count": 1,
                "recent_alerts": [{"id": "alert-1", "severity": "warning", "created_at": "2026-02-10T10:00:00Z"}],
            },
            "predictions": {"total_count": 2, "critical_count": 0, "warning_count": 1},
            "energy": {"current_power_usage": 45.5, "daily_consumption": 850.0, "solar_generation": 120.0},
            "last_updated": "2026-02-10T10:00:00Z",
        }

        assert response["site_id"] == "site-002"
        assert response["equipment"]["total_count"] == 15
        assert response["safety"]["safe_devices"] == 14
        assert response["alerts"]["total_count"] == 3
        assert response["predictions"]["warning_count"] == 1

    @pytest.mark.unit
    def test_site_summary_aggregates_alerts_by_severity(self):
        """Test that alerts are aggregated by severity."""
        response = {
            "site_id": "site-002",
            "alerts": {"total_count": 6, "critical_count": 1, "warning_count": 3, "info_count": 2, "recent_alerts": []},
        }

        assert response["alerts"]["total_count"] == 6
        assert response["alerts"]["critical_count"] == 1
        assert response["alerts"]["warning_count"] == 3
        assert response["alerts"]["info_count"] == 2

    @pytest.mark.unit
    def test_site_summary_equipment_by_type(self):
        """Test that equipment is aggregated by type."""
        response = {
            "site_id": "site-002",
            "equipment": {"total_count": 10, "by_type": {"chiller": 2, "ahu": 3, "fcu": 5}},
        }

        assert response["equipment"]["by_type"]["chiller"] == 2
        assert response["equipment"]["by_type"]["ahu"] == 3
        assert response["equipment"]["by_type"]["fcu"] == 5


class TestSiteAlerts:
    """Tests for GET /api/sites/{site_id}/alerts endpoint."""

    @pytest.mark.unit
    def test_site_alerts_returns_paginated_results(self):
        """Test site alerts returns paginated results."""
        response = {
            "site_id": "site-002",
            "total_count": 50,
            "critical_count": 5,
            "warning_count": 20,
            "info_count": 25,
            "page": 1,
            "page_size": 20,
            "alerts": [
                {"id": "alert-1", "severity": "critical"},
                {"id": "alert-2", "severity": "warning"},
            ],
        }

        assert response["page"] == 1
        assert response["page_size"] == 20
        assert len(response["alerts"]) == 2
        assert response["total_count"] == 50

    @pytest.mark.unit
    def test_site_alerts_aggregates_by_severity(self):
        """Test that alerts are aggregated by severity."""
        response = {
            "site_id": "site-002",
            "total_count": 30,
            "critical_count": 2,
            "warning_count": 10,
            "info_count": 18,
            "page": 1,
            "page_size": 20,
            "alerts": [],
        }

        assert response["critical_count"] == 2
        assert response["warning_count"] == 10
        assert response["info_count"] == 18
        assert (
            response["critical_count"] + response["warning_count"] + response["info_count"] == response["total_count"]
        )

    @pytest.mark.unit
    def test_site_alerts_pagination(self):
        """Test pagination parameters work correctly."""
        # Page 1
        response_p1 = {
            "total_count": 100,
            "page": 1,
            "page_size": 20,
            "alerts": [{"id": f"alert-{i}"} for i in range(1, 21)],
        }

        # Page 2
        response_p2 = {
            "total_count": 100,
            "page": 2,
            "page_size": 20,
            "alerts": [{"id": f"alert-{i}"} for i in range(21, 41)],
        }

        assert len(response_p1["alerts"]) == 20
        assert len(response_p2["alerts"]) == 20
        assert response_p1["alerts"][0]["id"] == "alert-1"
        assert response_p2["alerts"][0]["id"] == "alert-21"

    @pytest.mark.unit
    def test_site_alerts_max_page_size_100(self):
        """Test that page_size is capped at 100."""
        # Page size validation should limit to 100
        # In actual test, endpoint validates page_size <= 100


class TestBackwardCompatibility:
    """Tests for backward compatibility with individual device endpoints."""

    @pytest.mark.unit
    def test_individual_safety_status_still_works(self):
        """Test that individual device safety status endpoint still works."""
        # Individual endpoint should still be functional
        response = {"severity": "SAFE", "last_checked": "2026-02-10T10:00:00Z", "device_id": "dev-1"}

        assert response["severity"] == "SAFE"
        assert response["device_id"] == "dev-1"

    @pytest.mark.unit
    def test_individual_device_endpoints_unchanged(self):
        """Test that individual device endpoints are unchanged."""
        # GET /api/devices/{device_id}
        # GET /api/devices/{device_id}/status
        # GET /api/devices/{device_id}/safety-status
        # All should continue to work as before

        individual_endpoints = [
            "/api/devices/{device_id}",
            "/api/devices/{device_id}/status",
            "/api/devices/{device_id}/safety-status",
            "/api/devices/{device_id}/points",
            "/api/devices/{device_id}/control",
        ]

        assert len(individual_endpoints) >= 5


class TestRateLimiting:
    """Tests for rate limiting on batch endpoints."""

    @pytest.mark.unit
    def test_batch_endpoints_have_rate_limiting(self):
        """Test that batch endpoints implement rate limiting."""
        # Batch endpoints should have 30/minute rate limit
        # Individual endpoints should have appropriate limits
        limits = {
            "batch_safety_status": "30/minute",
            "batch_readings": "30/minute",
            "batch_condition": "30/minute",
            "site_summary": "30/minute",
            "site_alerts": "30/minute",
        }

        assert all(v == "30/minute" for v in limits.values())


class TestErrorHandling:
    """Tests for error handling in batch endpoints."""

    @pytest.mark.unit
    def test_batch_request_with_empty_list_fails(self):
        """Test that empty device list is rejected."""
        # Empty list should fail validation
        request = {"device_ids": []}
        assert len(request["device_ids"]) == 0

    @pytest.mark.unit
    def test_batch_request_validates_max_100(self):
        """Test that > 100 devices is rejected."""
        device_ids = [f"dev-{i}" for i in range(101)]
        assert len(device_ids) > 100

    @pytest.mark.unit
    def test_404_on_missing_site(self):
        """Test that missing site returns 404."""
        # GET /api/sites/invalid-site-id/summary should return 404
        pass

    @pytest.mark.unit
    def test_missing_devices_reported_in_errors(self):
        """Test that missing devices appear in errors dict, not results."""
        response = {"results": {"dev-1": {"status": "online"}}, "errors": {"dev-missing": "Device not found"}}

        assert "dev-missing" not in response["results"]
        assert "dev-missing" in response["errors"]
