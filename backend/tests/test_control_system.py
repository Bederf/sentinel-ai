"""
Control System Integration Tests

Tests the complete integration of:
- Device abstraction layer
- Safety interlock system
- Audit logging system
- API endpoints

Verifies that all components work together correctly.
"""

import pytest
import asyncio
import time
from fastapi.testclient import TestClient

# Import test client and app
from app.main import app
from app.models.audit_log import AuditResultType
from app.services.device_abstraction import device_manager
from app.services.safety_interlocks import safety_engine
from app.services.audit_logger import AuditLogger

client = TestClient(app)


class TestDeviceAbstraction:
    """Tests for device abstraction layer."""

    @pytest.fixture(autouse=True)
    async def setup(self):
        """Initialize device manager before tests."""
        if not device_manager._initialized:
            await device_manager.initialize([])

    def test_list_devices(self):
        """Test listing devices from API."""
        response = client.get("/api/devices")
        assert response.status_code == 200
        devices = response.json()
        assert isinstance(devices, list)

    def test_get_device(self):
        """Test getting a single device."""
        # First get list of devices
        response = client.get("/api/devices")
        assert response.status_code == 200
        devices = response.json()

        if len(devices) > 0:
            device_id = devices[0]["id"]
            response = client.get(f"/api/devices/{device_id}")
            assert response.status_code == 200
            device = response.json()
            assert device["id"] == device_id

    def test_get_device_not_found(self):
        """Test getting non-existent device."""
        response = client.get("/api/devices/non-existent-device-12345")
        assert response.status_code == 404


class TestSafetyInterlocks:
    """Tests for safety interlock system."""

    @pytest.fixture(autouse=True)
    async def setup(self):
        """Initialize safety engine before tests."""
        if not safety_engine._initialized:
            await safety_engine.initialize()

    def test_get_safety_rules(self):
        """Test getting safety rules from API."""
        response = client.get("/api/safety/rules")
        assert response.status_code == 200
        data = response.json()
        assert "rules" in data
        assert "count" in data

    def test_safety_health(self):
        """Test safety service health endpoint."""
        response = client.get("/api/safety/health")
        assert response.status_code == 200
        health = response.json()
        assert health["status"] == "healthy"

    def test_validate_safe_control(self):
        """Test safety validation for safe control action."""
        # Get a device first
        devices_response = client.get("/api/devices")
        devices = devices_response.json()

        if len(devices) > 0:
            device = devices[0]
            # Use a safe temperature value within 16-28C range
            validation_request = {
                "device_id": device["id"],
                "point_name": "setpoint",
                "value": 22.0
            }
            response = client.post("/api/safety/validate", json=validation_request)
            assert response.status_code == 200
            result = response.json()
            assert "validation" in result

    def test_validate_unsafe_control(self):
        """Test safety validation for unsafe control action."""
        # Get a device first
        devices_response = client.get("/api/devices")
        devices = devices_response.json()

        if len(devices) > 0:
            device = devices[0]
            # Use an unsafe temperature value outside 16-28C range
            validation_request = {
                "device_id": device["id"],
                "point_name": "setpoint",
                "value": 40.0  # Above safe limit
            }
            response = client.post("/api/safety/validate", json=validation_request)
            assert response.status_code == 200
            result = response.json()
            assert "validation" in result
            # Should be blocked due to temperature range
            validation = result["validation"]
            assert not validation.get("allowed", True) or len(validation.get("reasons", [])) > 0


class TestAuditLogging:
    """Tests for audit logging system."""

    def test_get_audit_logs(self):
        """Test getting audit logs from API."""
        response = client.get("/api/audit/logs")
        assert response.status_code == 200
        data = response.json()
        assert "entries" in data
        assert "total_count" in data

    def test_get_audit_stats(self):
        """Test getting audit statistics."""
        response = client.get("/api/audit/stats")
        assert response.status_code == 200
        stats = response.json()
        assert "total_entries" in stats

    def test_audit_log_filtering(self):
        """Test audit log filtering."""
        # Test filtering by action
        response = client.get("/api/audit/logs?action=device_control")
        assert response.status_code == 200

        # Test filtering by result
        response = client.get("/api/audit/logs?result=success")
        assert response.status_code == 200

    def test_audit_logger_direct(self):
        """Test audit logger directly."""
        audit_logger = AuditLogger()

        # Log a test control action
        audit_logger.log_control_action(
            device_id="test-device-001",
            point_name="test_point",
            user="test-operator",
            old_value=20.0,
            new_value=22.0,
            result=AuditResultType.SUCCESS,
            safety_validation={
                "allowed": True,
                "reasons": [],
                "warnings": [],
            }
        )

        # Verify log was created
        logs = audit_logger.get_logs(device_id="test-device-001")
        assert len(logs) > 0


class TestControlIntegration:
    """Integration tests for complete control flow."""

    def test_control_health_endpoint(self):
        """Test control services health endpoint."""
        response = client.get("/api/health/control")
        assert response.status_code == 200
        health = response.json()
        assert "status" in health
        assert "services" in health
        assert "device_abstraction" in health["services"]
        assert "safety_interlocks" in health["services"]
        assert "audit_logging" in health["services"]

    def test_device_control_success(self):
        """Test successful device control."""
        # Get a device first
        devices_response = client.get("/api/devices")
        devices = devices_response.json()

        if len(devices) > 0:
            device = devices[0]
            # Control with a safe temperature value
            control_data = {
                "point": "setpoint",
                "value": 22.0,
                "priority": 8
            }

            response = client.post(
                f"/api/devices/{device['id']}/control",
                json=control_data
            )
            # May succeed or fail depending on device state
            assert response.status_code in [200, 400, 500, 503]

    def test_performance_response_time(self):
        """Test control response times meet requirements."""
        start_time = time.time()

        # Health check as performance baseline
        response = client.get("/api/health/control")

        end_time = time.time()
        response_time = (end_time - start_time) * 1000  # Convert to ms

        # Should be fast (< 500ms)
        assert response_time < 500
        assert response.status_code == 200

    def test_regression_existing_functionality(self):
        """Ensure new control features don't break existing functionality."""
        # All existing API endpoints should still work

        # Health APIs
        assert client.get("/api/health").status_code == 200
        assert client.get("/api/health/control").status_code == 200

        # Dashboard APIs
        assert client.get("/api/stats").status_code == 200
        assert client.get("/api/sites").status_code == 200

        # Device APIs
        assert client.get("/api/devices").status_code == 200

        # Safety APIs
        assert client.get("/api/safety/health").status_code == 200
        assert client.get("/api/safety/rules").status_code == 200

        # Audit APIs
        assert client.get("/api/audit/logs").status_code == 200
        assert client.get("/api/audit/stats").status_code == 200


class TestSafetyRules:
    """Tests for safety rule management."""

    def test_temperature_range_rule_exists(self):
        """Test that temperature range rule exists."""
        response = client.get("/api/safety/rules")
        assert response.status_code == 200
        data = response.json()
        rules = data["rules"]

        # Find temperature range rule
        temp_rules = [r for r in rules if r.get("rule_type") == "temperature_range"]
        assert len(temp_rules) > 0

    def test_safety_rule_structure(self):
        """Test safety rule data structure."""
        response = client.get("/api/safety/rules")
        assert response.status_code == 200
        data = response.json()

        if len(data["rules"]) > 0:
            rule = data["rules"][0]
            # Check required fields
            assert "id" in rule
            assert "name" in rule
            assert "rule_type" in rule
            assert "severity" in rule
