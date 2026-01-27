#!/usr/bin/env python3
"""Test script for audit logging integration."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

import asyncio
from datetime import datetime
from app.services.device_abstraction import DeviceManager
from app.services.audit_logger import AuditLogger
from app.models.audit_log import AuditResultType

async def test_audit_integration():
    """Test audit logging integration with device abstraction."""
    print("Testing Audit Logging Integration...")

    # Initialize device manager
    device_manager = DeviceManager()

    # Load mock devices
    from pathlib import Path
    import json

    data_dir = Path(__file__).parent / "backend" / "app" / "data"
    mock_devices_file = data_dir / "mock_devices.json"

    if not mock_devices_file.exists():
        print("❌ Mock devices file not found")
        return

    with open(mock_devices_file) as f:
        devices_data = json.load(f)

    await device_manager.initialize(devices_data)
    print(f"Initialized device manager with {len(devices_data)} devices")

    # Get audit logger
    audit_logger = AuditLogger()

    # Test 1: Get initial audit logs
    print("\n1. Getting initial audit logs...")
    initial_logs = audit_logger.get_logs(limit=5)
    print(f"   Found {len(initial_logs)} audit log entries")

    # Test 2: Try to control a device (should fail if not connected)
    print("\n2. Testing device control with audit logging...")
    try:
        # Get first device
        devices = await device_manager.list_devices()
        if not devices:
            print("   No devices found")
            return

        device = devices[0]
        print(f"   Using device: {device.id} ({device.name})")

        # Try to write a value (will likely fail because device is not connected)
        # But it should still create an audit log entry
        success = await device_manager.write_device_value(
            device_id=device.id,
            point_name="setpoint",
            value=24.5,
            priority=8,
            user="test-user"
        )

        print(f"   Control result: {'Success' if success else 'Failed'}")

    except Exception as e:
        print(f"   Expected error (device not connected): {type(e).__name__}: {e}")

    # Test 3: Check audit logs after control attempt
    print("\n3. Checking audit logs after control attempt...")
    logs_after = audit_logger.get_logs(limit=10)
    print(f"   Found {len(logs_after)} total audit log entries")

    # Look for device control entries
    device_logs = [log for log in logs_after if log.device_id and log.action.value == "device_control"]
    print(f"   Found {len(device_logs)} device control audit entries")

    for i, log in enumerate(device_logs[:3]):  # Show first 3
        print(f"\n   Device Control Log {i+1}:")
        print(f"     Device: {log.device_id}")
        print(f"     Point: {log.point_name}")
        print(f"     User: {log.user}")
        print(f"     Result: {log.result.value}")
        print(f"     Old Value: {log.old_value}")
        print(f"     New Value: {log.new_value}")

    # Test 4: Generate demo audit data (simplified version)
    print("\n4. Generating demo audit data...")
    try:
        # Simplified demo data generation without FastAPI dependency
        from datetime import timedelta
        import random
        from app.models.audit_log import AuditResultType

        demo_devices = [
            "chiller-gateway-001",
            "ahu-level3-002",
            "lighting-lobby-003",
            "access-main-004",
            "fire-pump-005",
            "vav-office-006"
        ]

        demo_users = ["operator-1", "operator-2", "system", "scheduler", "admin"]
        demo_points = ["setpoint", "fan_speed", "brightness", "status", "mode"]

        entries_created = 0
        now = datetime.now()

        for days_ago in range(3):  # Generate for last 3 days (simpler)
            for _ in range(random.randint(3, 8)):  # 3-8 entries per day
                hours_ago = random.randint(0, 23)
                minutes_ago = random.randint(0, 59)
                timestamp = now - timedelta(days=days_ago, hours=hours_ago, minutes=minutes_ago)

                device_id = random.choice(demo_devices)
                user = random.choice(demo_users)
                point_name = random.choice(demo_points)
                old_value = random.randint(20, 25) if "setpoint" in point_name else random.randint(50, 100)
                new_value = old_value + random.randint(-5, 5)

                # Random result
                result_weights = {
                    AuditResultType.SUCCESS: 70,
                    AuditResultType.WARNING: 15,
                    AuditResultType.BLOCKED: 10,
                    AuditResultType.FAILED: 5
                }
                result = random.choices(
                    list(result_weights.keys()),
                    weights=list(result_weights.values())
                )[0]

                # Create safety validation based on result
                safety_validation = None
                error_message = None

                if result == AuditResultType.BLOCKED:
                    safety_validation = {
                        "rules_checked": ["temperature_range", "pressure_limits"],
                        "passed_rules": ["temperature_range"],
                        "failed_rules": ["pressure_limits"],
                        "details": "Pressure exceeds safe operating limits"
                    }
                    error_message = "Safety validation failed: Pressure limit exceeded"
                elif result == AuditResultType.WARNING:
                    safety_validation = {
                        "rules_checked": ["temperature_range", "minimum_runtime"],
                        "passed_rules": ["temperature_range"],
                        "warnings": ["minimum_runtime"],
                        "details": "Minimum runtime requirement not met (warning only)"
                    }
                elif result == AuditResultType.SUCCESS:
                    safety_validation = {
                        "rules_checked": ["temperature_range", "pressure_limits"],
                        "passed_rules": ["temperature_range", "pressure_limits"],
                        "details": "All safety checks passed"
                    }

                # Log the demo entry
                audit_logger.log_control_action(
                    device_id=device_id,
                    point_name=point_name,
                    user=user,
                    old_value=old_value,
                    new_value=new_value,
                    result=result,
                    safety_validation=safety_validation,
                    error_message=error_message,
                    metadata={
                        "demo_data": True,
                        "generated_at": timestamp.isoformat(),
                        "priority": random.randint(8, 16)
                    }
                )
                entries_created += 1

        # Force flush to disk
        audit_logger.flush()

        print(f"   Generated {entries_created} demo audit entries")

    except Exception as e:
        print(f"   Error generating demo data: {e}")

    # Test 5: Check audit statistics
    print("\n5. Getting audit statistics...")
    stats = audit_logger.get_stats()
    print(f"   Total entries: {stats['total_entries']}")
    print(f"   By action: {stats['by_action']}")
    print(f"   By result: {stats['by_result']}")
    print(f"   Recent activity (24h): {stats['recent_activity_count']}")

    # Test 6: Test filtering
    print("\n6. Testing audit log filtering...")
    filtered_logs = audit_logger.get_logs(
        result=AuditResultType.SUCCESS,
        limit=5
    )
    print(f"   Found {len(filtered_logs)} successful actions")

    # Force flush to ensure all logs are saved
    audit_logger.flush()

    print("\n✅ Audit logging integration test completed!")

if __name__ == "__main__":
    asyncio.run(test_audit_integration())