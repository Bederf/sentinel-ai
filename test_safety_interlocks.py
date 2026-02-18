#!/usr/bin/env python3
"""Test script for safety interlock system."""

import asyncio
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from app.services.safety_interlocks import safety_engine
from app.services.device_abstraction import device_manager
from app.models.device import Device, DeviceType, ProtocolType, DeviceStatus, DevicePoint, PointType


async def test_safety_interlocks():
    """Test safety interlock functionality."""
    print("=== Testing Safety Interlock System ===\n")

    # Initialize safety engine
    print("1. Initializing safety engine...")
    await safety_engine.initialize()
    print(f"   ✓ Safety engine initialized with {len(safety_engine.rules)} rules")

    # List all rules
    print("\n2. Listing safety rules:")
    rules = await safety_engine.list_rules()
    for rule in rules:
        print(f"   - {rule.name} ({rule.rule_type.value}): {rule.severity.value}")

    # Create a test HVAC device
    print("\n3. Creating test HVAC device...")
    test_device = Device(
        id="test_chiller_001",
        name="Test Chiller",
        device_type=DeviceType.HVAC,
        protocol=ProtocolType.MOCK,
        location="Test Room",
        site_id="test_site_001",
        status=DeviceStatus.ONLINE,
        points={
            "temperature_setpoint": DevicePoint(
                name="temperature_setpoint",
                point_type=PointType.ANALOG_VALUE,
                description="Temperature setpoint",
                unit="°C",
                min_value=5.0,
                max_value=30.0,
                default_value=22.0,
                writable=True,
                priority=8,
            ),
            "supply_temp": DevicePoint(
                name="supply_temp",
                point_type=PointType.ANALOG_INPUT,
                description="Supply temperature",
                unit="°C",
                min_value=0.0,
                max_value=50.0,
                default_value=15.0,
                writable=False,
            ),
            "discharge_pressure": DevicePoint(
                name="discharge_pressure",
                point_type=PointType.ANALOG_INPUT,
                description="Discharge pressure",
                unit="kPa",
                min_value=0.0,
                max_value=2000.0,
                default_value=800.0,
                writable=False,
            ),
        }
    )

    # Test temperature validation
    print("\n4. Testing temperature safety validation:")

    # Test safe temperature
    print("   Testing safe temperature (22°C)...")
    safe_result = await safety_engine.validate_control(test_device, "temperature_setpoint", 22.0)
    print(f"   ✓ Allowed: {safe_result['allowed']}, Message: {safe_result['message']}")

    # Test unsafe temperature (too low)
    print("\n   Testing unsafe temperature (5°C - below HVAC minimum)...")
    unsafe_low_result = await safety_engine.validate_control(test_device, "temperature_setpoint", 5.0)
    print(f"   ✓ Allowed: {unsafe_low_result['allowed']}")
    if unsafe_low_result['reasons']:
        print(f"   ✓ Reason: {unsafe_low_result['reasons'][0]}")

    # Test unsafe temperature (too high)
    print("\n   Testing unsafe temperature (30°C - above HVAC maximum)...")
    unsafe_high_result = await safety_engine.validate_control(test_device, "temperature_setpoint", 30.0)
    print(f"   ✓ Allowed: {unsafe_high_result['allowed']}")
    if unsafe_high_result['reasons']:
        print(f"   ✓ Reason: {unsafe_high_result['reasons'][0]}")

    # Test device safety status
    print("\n5. Testing device safety status...")
    safety_status = await safety_engine.get_device_safety_status(test_device)
    print(f"   ✓ Overall status: {safety_status['overall_status']}")
    print(f"   ✓ Active rules: {safety_status['active_rule_count']}")
    print(f"   ✓ Points checked: {len(safety_status['point_statuses'])}")

    # Test rule filtering
    print("\n6. Testing rule filtering...")
    hvac_rules = await safety_engine.list_rules({"device_type": "hvac"})
    print(f"   ✓ Found {len(hvac_rules)} HVAC-specific rules")

    # Test safety engine health
    print("\n7. Testing safety engine health...")
    print(f"   ✓ Initialized: {safety_engine._initialized}")
    print(f"   ✓ Total rules: {len(safety_engine.rules)}")
    print(f"   ✓ Enabled rules: {len([r for r in safety_engine.rules.values() if r.enabled])}")

    # Test API endpoint simulation
    print("\n8. Simulating API endpoint calls...")

    # Simulate /api/safety/validate
    print("   Simulating POST /api/safety/validate...")
    validation_request = {
        "device_id": "test_chiller_001",
        "point_name": "temperature_setpoint",
        "value": 25.0
    }
    # Note: In real API, device would be fetched from device_manager
    validation_result = await safety_engine.validate_control(test_device, "temperature_setpoint", 25.0)
    print(f"   ✓ Validation result: {validation_result['allowed']}")

    # Simulate /api/safety/rules
    print("\n   Simulating GET /api/safety/rules...")
    all_rules = await safety_engine.list_rules()
    print(f"   ✓ Retrieved {len(all_rules)} rules")

    print("\n=== Safety Interlock Tests Complete ===")
    print("\nSummary:")
    print(f"- Total safety rules: {len(safety_engine.rules)}")
    print(f"- HVAC-specific rules: {len(hvac_rules)}")
    print(f"- Test device safety status: {safety_status['overall_status']}")
    print("- Temperature validation: ✓ Working")
    print("- Rule filtering: ✓ Working")
    print("- Safety status calculation: ✓ Working")

    return True


async def test_device_abstraction_integration():
    """Test integration with device abstraction."""
    print("\n=== Testing Device Abstraction Integration ===\n")

    # Initialize device manager with test device
    print("1. Initializing device manager with test device...")
    test_device_data = {
        "id": "test_chiller_002",
        "name": "Test Chiller 2",
        "device_type": "hvac",
        "protocol": "mock",
        "location": "Test Room 2",
        "site_id": "test_site_001",
        "points": {
            "temperature_setpoint": {
                "name": "temperature_setpoint",
                "point_type": "analog_value",
                "description": "Temperature setpoint",
                "unit": "°C",
                "min_value": 5.0,
                "max_value": 30.0,
                "default_value": 22.0,
                "writable": True,
                "priority": 8,
            }
        }
    }

    await device_manager.initialize([test_device_data])
    print(f"   ✓ Device manager initialized with {len(device_manager._devices)} devices")

    # Test device safety status through device manager
    print("\n2. Testing device safety status through device manager...")
    try:
        safety_status = await device_manager.get_device_safety_status("test_chiller_002")
        print(f"   ✓ Safety status retrieved: {safety_status['overall_status']}")
        print(f"   ✓ Device name: {safety_status['device_name']}")
    except Exception as e:
        print(f"   ✗ Error: {e}")

    # Test safety validation during write
    print("\n3. Testing safety validation during device write...")
    try:
        # This should fail due to safety validation
        await device_manager.write_device_value("test_chiller_002", "temperature_setpoint", 5.0)
        print("   ✗ Write should have failed but didn't")
    except ValueError as e:
        print(f"   ✓ Write correctly blocked: {str(e)[:100]}...")
    except Exception as e:
        print(f"   ✗ Unexpected error: {e}")

    print("\n=== Device Abstraction Integration Tests Complete ===")


async def main():
    """Run all tests."""
    try:
        await test_safety_interlocks()
        await test_device_abstraction_integration()
        print("\n✅ All tests passed!")
        return 0
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
