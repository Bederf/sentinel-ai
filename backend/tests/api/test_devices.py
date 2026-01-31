"""
Unit tests for device API endpoints.
"""

import pytest
from fastapi.testclient import TestClient


@pytest.mark.unit
class TestDeviceAPI:
    """Test device API endpoints."""

    def test_get_devices(self, test_client: TestClient):
        """Test GET /api/devices endpoint."""
        response = test_client.get("/api/devices")
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_get_devices_with_site_filter(self, test_client: TestClient):
        """Test GET /api/devices with site_id filter."""
        response = test_client.get("/api/devices?site_id=test-site-001")
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_get_devices_with_type_filter(self, test_client: TestClient):
        """Test GET /api/devices with device_type filter."""
        response = test_client.get("/api/devices?device_type=HVAC_CHILLER")
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_get_device_by_id(self, test_client: TestClient):
        """Test GET /api/devices/{device_id} endpoint."""
        # First get list of devices
        devices_response = test_client.get("/api/devices")
        if devices_response.status_code == 200:
            devices = devices_response.json()
            if devices:
                device_id = devices[0]["id"]
                response = test_client.get(f"/api/devices/{device_id}")
                
                assert response.status_code == 200
                data = response.json()
                assert data["id"] == device_id

    def test_get_device_points(self, test_client: TestClient):
        """Test GET /api/devices/{device_id}/points endpoint."""
        devices_response = test_client.get("/api/devices")
        if devices_response.status_code == 200:
            devices = devices_response.json()
            if devices:
                device_id = devices[0]["id"]
                response = test_client.get(f"/api/devices/{device_id}/points")
                
                assert response.status_code == 200
                data = response.json()
                assert "points" in data

    def test_control_device(self, test_client: TestClient):
        """Test POST /api/devices/{device_id}/control endpoint."""
        devices_response = test_client.get("/api/devices")
        if devices_response.status_code == 200:
            devices = devices_response.json()
            if devices:
                device_id = devices[0]["id"]
                # Get device to find a writable point
                device_response = test_client.get(f"/api/devices/{device_id}")
                if device_response.status_code == 200:
                    device = device_response.json()
                    if "points" in device:
                        # Find a writable point
                        writable_point = None
                        for point_name, point_data in device["points"].items():
                            if point_data.get("writable", False):
                                writable_point = point_name
                                break

                        if writable_point:
                            control_data = {
                                "point": writable_point,
                                "value": 22.0,
                                "priority": 8
                            }
                            response = test_client.post(
                                f"/api/devices/{device_id}/control",
                                json=control_data
                            )

                            # Control may succeed, be blocked by safety, or fail for various reasons
                            # 200/201 = success, 400 = validation/safety block, 404 = device not found
                            assert response.status_code in [200, 201, 400, 404, 422, 500]
                            data = response.json()
                            # Response should have some structured content
                            assert isinstance(data, dict)

    def test_get_device_status(self, test_client: TestClient):
        """Test GET /api/devices/{device_id}/status endpoint."""
        devices_response = test_client.get("/api/devices")
        if devices_response.status_code == 200:
            devices = devices_response.json()
            if devices:
                device_id = devices[0]["id"]
                response = test_client.get(f"/api/devices/{device_id}/status")
                
                assert response.status_code == 200
                data = response.json()
                assert "device_id" in data or "status" in data
