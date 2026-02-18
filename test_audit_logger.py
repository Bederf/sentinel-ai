#!/usr/bin/env python3
"""Test script for audit logger service."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from app.services.audit_logger import AuditLogger
from app.models.audit_log import AuditResultType
from datetime import datetime, timedelta

def test_audit_logger():
    """Test basic audit logger functionality."""
    print("Testing Audit Logger...")

    # Get singleton instance
    logger = AuditLogger()

    # Log some control actions
    print("Logging control actions...")
    entry_id1 = logger.log_control_action(
        device_id="chiller-001",
        point_name="setpoint",
        user="operator-1",
        old_value=22.5,
        new_value=24.0,
        result=AuditResultType.SUCCESS,
        safety_validation={"temperature_range": "16-28°C", "passed": True},
        metadata={"priority": 8, "reason": "energy_saving"}
    )

    entry_id2 = logger.log_control_action(
        device_id="ahu-002",
        point_name="fan_speed",
        user="system",
        old_value=75,
        new_value=60,
        result=AuditResultType.BLOCKED,
        safety_validation={"minimum_flow": "50%", "passed": False},
        error_message="Safety validation failed: Minimum flow requirement not met",
        metadata={"priority": 13}
    )

    # Log a safety validation
    print("Logging safety validation...")
    entry_id3 = logger.log_safety_validation(
        device_id="chiller-001",
        user="safety-system",
        validation_result={
            "rules_checked": ["temperature_range", "pressure_limits"],
            "passed_rules": ["temperature_range"],
            "failed_rules": ["pressure_limits"],
            "details": "Pressure exceeds safe operating limits"
        },
        result=AuditResultType.WARNING
    )

    # Log a system event
    print("Logging system event...")
    entry_id4 = logger.log_system_event(
        event_type="system_startup",
        user="system",
        result=AuditResultType.SUCCESS,
        metadata={"version": "1.0.0", "components": ["api", "scheduler"]}
    )

    # Force flush to disk
    logger.flush()

    # Test querying logs
    print("\nQuerying logs...")
    logs = logger.get_logs(limit=10)
    print(f"Retrieved {len(logs)} logs")

    for i, log in enumerate(logs[:3]):  # Show first 3
        print(f"\nLog {i+1}:")
        print(f"  Action: {log.action}")
        print(f"  Device: {log.device_id}")
        print(f"  User: {log.user}")
        print(f"  Result: {log.result}")
        print(f"  Time: {log.timestamp}")

    # Test filtering
    print("\nTesting filters...")
    device_logs = logger.get_logs(device_id="chiller-001")
    print(f"Found {len(device_logs)} logs for chiller-001")

    blocked_logs = logger.get_logs(result=AuditResultType.BLOCKED)
    print(f"Found {len(blocked_logs)} blocked actions")

    # Test stats
    print("\nGetting statistics...")
    stats = logger.get_stats()
    print(f"Total entries: {stats['total_entries']}")
    print(f"By action: {stats['by_action']}")
    print(f"By result: {stats['by_result']}")
    print(f"Recent activity (24h): {stats['recent_activity_count']}")

    print("\n✅ Audit logger test completed successfully!")

if __name__ == "__main__":
    test_audit_logger()
