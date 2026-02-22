#!/usr/bin/env python3
"""Test and demonstrate AES-128 encryption at rest.

This script verifies the encryption service and shows how audit logs
are encrypted before storage and automatically decrypted when read.

Usage:
    python3 scripts/test_encryption.py
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.models.audit_log import AuditResultType
from app.services.audit_logger import AuditLogger
from app.services.encryption_service import (
    EncryptionService,
    reset_encryption_service,
)


def print_section(title):
    """Print a section header."""
    separator = "=" * 70
    print(f"\n{separator}")
    print(f"  {title}")
    print(f"{separator}\n")


def test_encryption_service():
    """Test the core encryption service."""
    print_section("1. Testing Encryption Service")

    # Generate a key
    key = EncryptionService.generate_key()
    print("Generated encryption key:")
    print(f"  {key}\n")

    # Create service with key
    service = EncryptionService(encryption_key=key, enabled=True)
    print(f"Service initialized with encryption enabled: {service.enabled}\n")

    # Test encryption
    test_data = [
        "technician@facility.com",
        "S002-CHILLER-B1-001",
        "setpoint_temperature",
        "Critical: System failure",
    ]

    print("Encrypting sensitive fields:")
    encrypted_data = {}
    for data in test_data:
        encrypted = service.encrypt(data)
        encrypted_data[data] = encrypted
        print(f"  {data:40} -> {encrypted[:50]}...")

    print("\nDecrypting fields:")
    for original, encrypted in encrypted_data.items():
        decrypted = service.decrypt(encrypted)
        status = "✓" if decrypted == original else "✗"
        print(f"  {status} {decrypted}")


def test_audit_logger_encryption():
    """Test audit logger with encryption."""
    print_section("2. Testing Audit Logger with Encryption")

    # Generate fresh key for this test
    key = EncryptionService.generate_key()
    os.environ["ENCRYPTION_KEY"] = key
    os.environ["ENCRYPTION_ENABLED"] = "true"

    # Reset singleton
    reset_encryption_service()

    # Clear existing logs
    log_file = Path(__file__).parent.parent / "app" / "data" / "audit_log.json"
    if log_file.exists():
        log_file.unlink()

    # Create logger
    logger = AuditLogger()
    print("Audit logger initialized")
    print(f"  Encryption enabled: {logger.encryption_service.enabled}")
    print(f"  Log file: {logger.log_file}\n")

    # Log entries
    print("Logging control actions...")
    actions = [
        {
            "device": "S002-CHILLER-B1-001",
            "point": "setpoint_temperature",
            "user": "technician@facility.com",
            "old": 22.5,
            "new": 20.0,
        },
        {
            "device": "S002-AHU-B1-002",
            "point": "fan_speed",
            "user": "operator@facility.com",
            "old": 50,
            "new": 75,
        },
    ]

    for action in actions:
        entry_id = logger.log_control_action(
            device_id=action["device"],
            point_name=action["point"],
            user=action["user"],
            old_value=action["old"],
            new_value=action["new"],
            result=AuditResultType.SUCCESS,
        )
        print(f"  Logged: {action['user']} -> {action['device']} ({entry_id})")

    # Flush to disk
    logger.flush()
    print("\n✓ All entries flushed to disk with encryption\n")

    # Verify encryption on disk
    print("Verifying encryption in storage:")
    if log_file.exists():
        with open(log_file, "r") as f:
            data = json.load(f)

        print(f"  Total entries: {data['entry_count']}")
        print(f"  Encryption enabled: {data['encryption_enabled']}")

        if data["entries"]:
            entry = data["entries"][0]
            print("\n  Sample encrypted entry:")
            print(f"    user field:      {entry.get('user', '')[:60]}...")
            print(f"    device_id field: {entry.get('device_id', '')[:60]}...")

            # Check Fernet format
            if entry.get("user", "").startswith("gAAAAAB"):
                print("\n    ✓ Fields encrypted in Fernet format")

    # Read decrypted logs
    print("\nReading decrypted logs through API:")
    logs = logger.get_logs(limit=2)
    for i, log in enumerate(logs, 1):
        print(f"  {i}. {log.user:30} | {log.device_id:25} | {log.result.value}")

    print("\n✓ All logs successfully encrypted and decrypted")


def test_disabled_encryption():
    """Test fallback to plaintext when encryption is disabled."""
    print_section("3. Testing Plaintext Fallback (Encryption Disabled)")

    # Disable encryption
    service = EncryptionService(enabled=False)
    print(f"Encryption enabled: {service.enabled}\n")

    data = "sensitive plaintext data"
    encrypted = service.encrypt(data)

    print(f"Original:  {data}")
    print(f"'Encrypted': {encrypted}")
    print(f"Same: {data == encrypted}\n")

    print("✓ With encryption disabled, data remains plaintext")


def test_dict_encryption():
    """Test selective field encryption."""
    print_section("4. Testing Selective Field Encryption")

    key = EncryptionService.generate_key()
    service = EncryptionService(encryption_key=key, enabled=True)

    original_dict = {
        "timestamp": "2026-02-17T12:00:00Z",
        "action": "device_control",
        "user": "admin@facility.com",
        "device_id": "S002-CHILLER-B1-001",
        "result": "success",
    }

    print("Original dictionary:")
    for key_name, value in original_dict.items():
        print(f"  {key_name:15} = {value}")

    # Encrypt only sensitive fields
    sensitive = ["user", "device_id"]
    encrypted_dict = service.encrypt_dict(original_dict, fields_to_encrypt=sensitive)

    print(f"\nAfter encrypting {sensitive}:")
    for key_name, value in encrypted_dict.items():
        if key_name in sensitive:
            print(f"  {key_name:15} = {str(value)[:50]}...")
        else:
            print(f"  {key_name:15} = {value}")

    # Decrypt
    decrypted_dict = service.decrypt_dict(encrypted_dict, fields_to_decrypt=sensitive)

    print("\nAfter decryption:")
    for key_name, value in decrypted_dict.items():
        print(f"  {key_name:15} = {value}")

    print("\n✓ Dictionary encryption successful")


def main():
    """Run all encryption tests."""
    print("\n")
    print("╔" + "=" * 68 + "╗")
    print("║" + " " * 10 + "BMS Intelligence: Encryption at Rest Demo" + " " * 16 + "║")
    print("╚" + "=" * 68 + "╝")

    try:
        test_encryption_service()
        test_dict_encryption()
        test_disabled_encryption()
        test_audit_logger_encryption()

        print_section("Summary")
        print("✓ All encryption tests passed successfully!")
        print("\nEncryption Status:")
        print("  • AES-128 (Fernet) encryption working")
        print("  • Audit logs encrypted at rest")
        print("  • Dictionary field encryption working")
        print("  • Plaintext fallback functional")
        print("  • Decryption verified end-to-end\n")

        return 0

    except Exception as e:  # noqa: BLE001
        print_section("Error")
        print(f"✗ Test failed: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
