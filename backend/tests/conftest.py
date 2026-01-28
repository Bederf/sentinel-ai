"""
Pytest configuration and fixtures for BMS Intelligence backend tests.
"""

import pytest
import json
import asyncio
from pathlib import Path
from typing import AsyncGenerator, Generator
from unittest.mock import Mock, AsyncMock, patch

from fastapi.testclient import TestClient
from httpx import AsyncClient

from app.main import app
from app.services.device_abstraction import DeviceManager
from app.services.safety_interlocks import SafetyEngine
from app.services.audit_logger import AuditLogger
from app.models.device import Device, DevicePoint
from app.models.safety_rules import SafetyRule

# Test data directory
TEST_DATA_DIR = Path(__file__).parent.parent / "app" / "data"
FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def test_client() -> Generator[TestClient, None, None]:
    """FastAPI test client for synchronous tests."""
    with TestClient(app) as client:
        yield client


@pytest.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    """Async HTTP client for async tests."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client


@pytest.fixture
def mock_devices_data() -> list[dict]:
    """Load mock devices data from JSON file."""
    mock_devices_file = TEST_DATA_DIR / "mock_devices.json"
    if mock_devices_file.exists():
        with open(mock_devices_file) as f:
            return json.load(f)
    return []


@pytest.fixture
def mock_safety_rules_data() -> list[dict]:
    """Load safety rules data from JSON file."""
    safety_rules_file = TEST_DATA_DIR / "safety_rules.json"
    if safety_rules_file.exists():
        with open(safety_rules_file) as f:
            return json.load(f)
    return []


@pytest.fixture
async def device_manager(mock_devices_data: list[dict]) -> DeviceManager:
    """Device manager fixture with test devices."""
    manager = DeviceManager()
    await manager.initialize(mock_devices_data)
    yield manager
    # Cleanup if needed
    await manager.shutdown()


@pytest.fixture
async def safety_engine(mock_safety_rules_data: list[dict]) -> SafetyEngine:
    """Safety engine fixture with test rules."""
    engine = SafetyEngine()
    await engine.initialize(mock_safety_rules_data)
    yield engine
    # Reset engine state
    engine.rules = {}
    engine._initialized = False


@pytest.fixture
def audit_logger() -> AuditLogger:
    """Audit logger fixture."""
    logger = AuditLogger()
    yield logger
    # Cleanup audit logs if needed
    logger.logs.clear()


@pytest.fixture
def sample_device() -> dict:
    """Sample device data for testing."""
    return {
        "id": "test-device-001",
        "name": "Test Chiller",
        "device_type": "HVAC_CHILLER",
        "protocol": "mock",
        "location": "Test Location",
        "site_id": "test-site-001",
        "description": "Test device for unit tests",
        "points": {
            "setpoint": {
                "name": "setpoint",
                "point_type": "analog_output",
                "description": "Temperature setpoint",
                "unit": "°C",
                "min_value": 16.0,
                "max_value": 28.0,
                "default_value": 22.0,
                "writable": True,
                "priority": 8,
            },
            "status": {
                "name": "status",
                "point_type": "binary_output",
                "description": "Device status",
                "unit": "",
                "default_value": True,
                "writable": True,
                "priority": 8,
            },
        },
        "metadata": {
            "manufacturer": "Test Manufacturer",
            "model": "Test Model",
        },
    }


@pytest.fixture
def sample_safety_rule() -> dict:
    """Sample safety rule data for testing."""
    return {
        "id": "test-rule-001",
        "name": "Test Temperature Range",
        "type": "TEMPERATURE_RANGE",
        "device_type": "HVAC_CHILLER",
        "device_id": None,
        "point_name": "setpoint",
        "severity": "BLOCK",
        "enabled": True,
        "min_value": 16.0,
        "max_value": 28.0,
        "description": "Test temperature range rule",
    }


@pytest.fixture
def sample_site() -> dict:
    """Sample site data for testing."""
    return {
        "id": "test-site-001",
        "name": "Test Site",
        "location": "Test Location",
        "region": "Gauteng",
        "type": "office",
        "equipment_count": 5,
        "alert_count": 2,
        "status": "normal",
    }


@pytest.fixture
def sample_equipment() -> dict:
    """Sample equipment data for testing."""
    return {
        "id": "test-equipment-001",
        "name": "Test Chiller",
        "type": "chiller",
        "site_id": "test-site-001",
        "site_name": "Test Site",
        "status": "online",
        "last_reading": {
            "timestamp": "2025-01-28T10:00:00Z",
            "value": 22.5,
            "unit": "°C",
        },
    }


@pytest.fixture
def sample_audit_log() -> dict:
    """Sample audit log entry for testing."""
    return {
        "id": "test-audit-001",
        "timestamp": "2025-01-28T10:00:00Z",
        "action": "DEVICE_CONTROL",
        "user": "test-operator",
        "device_id": "test-device-001",
        "point_name": "setpoint",
        "old_value": 21.5,
        "new_value": 22.0,
        "result": "SUCCESS",
        "safety_validation": {
            "rules_checked": ["temperature_range"],
            "passed_rules": ["temperature_range"],
            "failed_rules": [],
        },
        "metadata": {},
    }


@pytest.fixture
def mock_claude_api():
    """Mock Claude API responses."""
    with patch("app.services.claude_service.anthropic.Anthropic") as mock:
        mock_instance = Mock()
        mock.return_value = mock_instance
        
        # Mock streaming response
        async def mock_stream(*args, **kwargs):
            class MockMessage:
                delta = Mock()
                delta.text = "Test AI response"
                type = "content_block_delta"
            
            yield MockMessage()
        
        mock_instance.messages.stream.return_value = mock_stream()
        yield mock_instance


@pytest.fixture(autouse=True)
def reset_services():
    """Reset service state before each test."""
    # This runs before each test
    yield
    # Cleanup after each test if needed


@pytest.fixture
def disable_background_scheduler():
    """Disable background scheduler during tests."""
    with patch("app.services.background_scheduler.scheduler_service.start") as mock_start:
        with patch("app.services.background_scheduler.scheduler_service.stop") as mock_stop:
            yield mock_start, mock_stop
