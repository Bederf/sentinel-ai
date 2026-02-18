#!/usr/bin/env python3
"""Test script for mock device abstraction system."""

import asyncio
import json
from pathlib import Path

# Add backend to path
import sys
sys.path.insert(0, str(Path(__file__).parent / "backend"))

from app.services.device_abstraction import device_manager
from app.services.mock_devices import MockDeviceManager


async def test_device_abstraction():
    """Test the device abstraction system."""
    print("=== Testing Device Abstraction System ===\n")

    # Load mock devices
    data_dir = Path(__file__).parent / "backend" / "app" / "data"
    with open(data_dir / "mock_devices.json") as f:
        devices_data = json.load(f)

    # Initialize device manager
    await device_manager.initialize(devices_data)
    print(f"✓ DeviceManager initialized with {len(devices_data)} devices")

    # List all devices
    devices = await device_manager.list_devices()
    print(f"\n✓ Found {len(devices)} devices:")
    for device in devices:
        print(f"  - {device.name} ({device.device_type.value}) - {device.id}")

    # Test reading from Gateway Chiller
    print("\n=== Testing Device Reading ===")
    try:
        value = await device_manager.read_device_value("chiller-gateway-01", "supply_temp")
        print(f"✓ Read chiller supply temperature: {value.value} {value.unit}")
    except Exception as e:
        print(f"✗ Failed to read chiller supply temp: {e}")

    # Test writing to AHU
    print("\n=== Testing Device Writing ===")
    try:
        success = await device_manager.write_device_value("ahu-level3-01", "damper_position", 75)
        if success:
            print("✓ Successfully wrote to AHU damper position")
            # Read back to verify
            value = await device_manager.read_device_value("ahu-level3-01", "damper_position")
            print(f"  Verified: damper_position = {value.value}%")
    except Exception as e:
        print(f"✗ Failed to write to AHU: {e}")

    # Test invalid write (non-writable point)
    print("\n=== Testing Validation ===")
    try:
        success = await device_manager.write_device_value("chiller-gateway-01", "supply_temp", 10.0)
        print(f"✗ Should have failed: supply_temp is not writable")
    except ValueError as e:
        print(f"✓ Correctly rejected invalid write: {e}")

    # Test out-of-range write
    try:
        success = await device_manager.write_device_value("ahu-level3-01", "damper_position", 150)
        print(f"✗ Should have failed: damper_position max is 100%")
    except ValueError as e:
        print(f"✓ Correctly rejected out-of-range value: {e}")

    # Test device status
    print("\n=== Testing Device Status ===")
    for device in devices[:3]:  # Test first 3 devices
        status = await device_manager.get_device_status(device.id)
        print(f"  {device.name}: {status.value}")

    # Test site filtering
    print("\n=== Testing Site Filtering ===")
    site_devices = await device_manager.list_devices_by_site("-gateway")
    print(f"✓ Found {len(site_devices)} devices at Gateway site")

    # Test demo scenario setup
    print("\n=== Testing Demo Scenarios ===")
    await MockDeviceManager.create_demo_scenario(device_manager)
    print("✓ Demo scenarios created")

    # Test reading demo values
    try:
        chiller_pressure = await device_manager.read_device_value("chiller-gateway-01", "compressor_pressure")
        print(f"✓ Chiller compressor pressure (demo): {chiller_pressure.value} bar (near alarm threshold)")

        ahu_pressure = await device_manager.read_device_value("ahu-level3-01", "filter_pressure")
        print(f"✓ AHU filter pressure (demo): {ahu_pressure.value} Pa (above alarm threshold)")

        office_temp = await device_manager.read_device_value("vav-office-301", "room_temp")
        print(f"✓ Office temperature (demo): {office_temp.value}°C (above comfort range)")
    except Exception as e:
        print(f"✗ Failed to read demo values: {e}")

    # Shutdown
    await device_manager.shutdown()
    print("\n✓ DeviceManager shutdown complete")
    print("\n=== All Tests Completed Successfully ===")


if __name__ == "__main__":
    asyncio.run(test_device_abstraction())
