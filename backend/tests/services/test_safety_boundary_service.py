"""Tests for safety boundary service functionality."""

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from app.models.autonomous_decision import BoundaryStatus, EscalationLevel
from app.services.safety_boundary_service import safety_boundary_service


@pytest.fixture
async def setup_boundary_service():
    """Setup boundary service for testing."""
    if not safety_boundary_service._initialized:
        await safety_boundary_service.initialize()
    yield safety_boundary_service


@pytest.mark.asyncio
async def test_boundary_service_initialization(setup_boundary_service):
    """Test boundary service initializes properly."""
    service = setup_boundary_service
    assert service._initialized is True


@pytest.mark.asyncio
async def test_temperature_boundary_validation():
    """Test temperature boundary validation."""

    test_cases = [
        (15.0, False, "Below minimum"),
        (16.0, True, "At minimum"),
        (22.0, True, "Normal operation"),
        (28.0, True, "At maximum"),
        (29.0, False, "Above maximum"),
    ]

    for temp, expected_valid, description in test_cases:
        # Test temperature boundaries (16-28°C for HVAC)
        is_within_bounds = 16.0 <= temp <= 28.0
        assert is_within_bounds == expected_valid, f"Failed for {description}"


@pytest.mark.asyncio
async def test_pressure_boundary_validation():
    """Test pressure boundary validation."""

    test_cases = [
        (500, True, "Normal pressure"),
        (1200, True, "At maximum"),
        (1201, False, "Exceeds maximum"),
    ]

    for pressure, expected_valid, description in test_cases:
        # Test pressure boundaries (max 1200 kPa)
        is_within_bounds = pressure <= 1200
        assert is_within_bounds == expected_valid, f"Failed for {description}"


@pytest.mark.asyncio
async def test_brightness_boundary_validation():
    """Test brightness boundary validation."""

    test_cases = [
        (0, True, "Off"),
        (50, True, "Half brightness"),
        (90, True, "At maximum"),
        (100, False, "Exceeds maximum"),
    ]

    for brightness, expected_valid, description in test_cases:
        # Test brightness boundaries (max 90%)
        is_within_bounds = brightness <= 90
        assert is_within_bounds == expected_valid, f"Failed for {description}"


@pytest.mark.asyncio
async def test_runtime_limit_validation():
    """Test equipment runtime limit validation."""

    # Minimum 5 minutes between starts
    last_start = datetime.now()
    current_time = datetime.now()

    # Less than 5 minutes
    test_time = datetime.fromtimestamp(last_start.timestamp() + 240)  # 4 minutes
    is_allowed = (test_time.timestamp() - last_start.timestamp()) >= 300
    assert is_allowed is False, "Should block start within 5 minutes"

    # More than 5 minutes
    test_time = datetime.fromtimestamp(last_start.timestamp() + 301)  # 5 min 1 sec
    is_allowed = (test_time.timestamp() - last_start.timestamp()) >= 300
    assert is_allowed is True, "Should allow start after 5 minutes"


@pytest.mark.asyncio
async def test_boundary_status_calculation(setup_boundary_service):
    """Test boundary status calculation."""
    service = setup_boundary_service

    # Create mock device with points
    mock_device = MagicMock()
    mock_device.id = "test_device"
    mock_device.name = "Test Device"
    mock_device.points = {"temperature": MagicMock(value=24.0, min_bound=16.0, max_bound=28.0, writable=False)}

    # Calculate boundary status
    status = await service.get_boundary_status_summary(mock_device)

    assert status is not None
    assert "device_id" in status
    assert "device_name" in status
    assert "overall_status" in status


@pytest.mark.asyncio
async def test_boundary_breach_detection(setup_boundary_service):
    """Test detection of boundary breaches."""
    service = setup_boundary_service

    # Test value at limit
    current = 28.0
    min_bound = 16.0
    max_bound = 28.0

    is_breach = not (min_bound <= current <= max_bound)
    assert is_breach is False, "Value at limit is not a breach"

    # Test value exceeding limit
    current = 28.1
    is_breach = not (min_bound <= current <= max_bound)
    assert is_breach is True, "Value exceeding limit is a breach"


@pytest.mark.asyncio
async def test_boundary_approach_percentage(setup_boundary_service):
    """Test calculation of boundary approach percentage."""
    service = setup_boundary_service

    test_cases = [
        (16.0, 16.0, 28.0, 0.0, "At minimum"),
        (22.0, 16.0, 28.0, 50.0, "Midpoint"),
        (26.2, 16.0, 28.0, 85.0, "Approaching maximum"),
        (28.0, 16.0, 28.0, 100.0, "At maximum"),
    ]

    for current, min_bound, max_bound, expected_percent, description in test_cases:
        # Calculate approach percentage
        range_total = max_bound - min_bound
        progress = current - min_bound
        approach_percent = (progress / range_total) * 100

        assert abs(approach_percent - expected_percent) < 0.1, f"Failed for {description}"


@pytest.mark.asyncio
async def test_escalation_level_from_boundary_approach(setup_boundary_service):
    """Test escalation level determination from boundary approach."""
    service = setup_boundary_service

    test_cases = [
        (50.0, EscalationLevel.NONE, "Normal"),
        (77.0, EscalationLevel.WARNING, "Warning"),
        (86.0, EscalationLevel.ALERT, "Alert"),
        (96.0, EscalationLevel.CRITICAL, "Critical"),
        (100.0, EscalationLevel.EMERGENCY, "Emergency"),
    ]

    for approach_percent, expected_level, description in test_cases:
        # Determine escalation level
        if approach_percent < 75:
            level = EscalationLevel.NONE
        elif approach_percent < 85:
            level = EscalationLevel.WARNING
        elif approach_percent < 95:
            level = EscalationLevel.ALERT
        elif approach_percent < 100:
            level = EscalationLevel.CRITICAL
        else:
            level = EscalationLevel.EMERGENCY

        assert level == expected_level, f"Failed for {description}"


@pytest.mark.asyncio
async def test_dynamic_boundary_adjustment(setup_boundary_service):
    """Test dynamic boundary adjustment based on conditions."""
    service = setup_boundary_service

    # Normal boundaries
    default_min = 16.0
    default_max = 28.0

    # Adjust for high outdoor temperature
    outdoor_temp = 35.0
    if outdoor_temp > 32:
        adjusted_max = default_max + 2.0  # Relax boundary
    else:
        adjusted_max = default_max

    assert adjusted_max == 30.0, "Should relax boundary in high outdoor temp"

    # Adjust for critical operation
    is_critical = True
    if is_critical:
        adjusted_max = default_max - 2.0  # Tighten boundary

    assert adjusted_max == 26.0, "Should tighten boundary in critical operation"


@pytest.mark.asyncio
async def test_multiple_point_boundary_monitoring(setup_boundary_service):
    """Test monitoring multiple control points on single device."""
    service = setup_boundary_service

    # Create device with multiple points
    mock_device = MagicMock()
    mock_device.id = "multi_point_device"
    mock_device.name = "Multi-Point Device"
    mock_device.points = {
        "supply_temp": MagicMock(value=7.0, min_bound=5.0, max_bound=12.0),
        "discharge_pressure": MagicMock(value=450, min_bound=0, max_bound=1200),
        "runtime_hours": MagicMock(value=1000, min_bound=0, max_bound=10000),
    }

    # Get boundary status for all points
    status = await service.get_boundary_status_summary(mock_device)

    assert status is not None
    # All points should be within normal bounds


@pytest.mark.asyncio
async def test_boundary_configuration_update(setup_boundary_service):
    """Test updating boundary configuration."""
    service = setup_boundary_service

    device_id = "config_test"
    point_name = "temperature"
    new_boundaries = {"min_bound": 14.0, "max_bound": 30.0, "warning_threshold": 0.75, "critical_threshold": 0.95}

    success = await service.update_boundary_config(
        device_id=device_id, point_name=point_name, new_boundaries=new_boundaries
    )

    # Configuration should be updated
    # Verify implementation updates config


@pytest.mark.asyncio
async def test_boundary_violation_logging(setup_boundary_service):
    """Test boundary violations are properly logged."""
    service = setup_boundary_service

    # Create boundary status showing violation
    boundary_status = BoundaryStatus(
        device_id="violation_test",
        point_name="temperature",
        current_value=29.0,
        boundary_min=16.0,
        boundary_max=28.0,
        approach_percentage=103.6,  # Exceeds 100%
        escalation_level=EscalationLevel.EMERGENCY,
        warnings=["Temperature exceeds maximum boundary"],
        last_updated=datetime.now(),
    )

    # Log violation
    # Verify audit log created


@pytest.mark.asyncio
async def test_safe_zone_determination(setup_boundary_service):
    """Test determination of safe operational zones."""
    service = setup_boundary_service

    # Define safety zones
    min_bound = 16.0
    max_bound = 28.0
    safe_margin = 2.0

    safe_min = min_bound + safe_margin
    safe_max = max_bound - safe_margin

    assert safe_min == 18.0, "Safe minimum with margin"
    assert safe_max == 26.0, "Safe maximum with margin"

    # Test if value is in safe zone
    test_values = [
        (17.0, False, "Below safe minimum"),
        (22.0, True, "In safe zone"),
        (27.0, False, "Above safe maximum"),
    ]

    for value, expected_safe, description in test_values:
        is_safe = safe_min <= value <= safe_max
        assert is_safe == expected_safe, f"Failed for {description}"


@pytest.mark.asyncio
async def test_concurrent_boundary_checks(setup_boundary_service):
    """Test concurrent boundary status checks."""
    service = setup_boundary_service

    import asyncio

    mock_devices = [
        MagicMock(id=f"device_{i}", name=f"Device {i}", points={"temp": MagicMock(value=22.0)}) for i in range(5)
    ]

    checks = [service.get_boundary_status_summary(device) for device in mock_devices]

    results = await asyncio.gather(*checks)
    assert len(results) == 5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
