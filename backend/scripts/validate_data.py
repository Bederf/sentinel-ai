#!/usr/bin/env python3
"""
Data Validation Script for BMS Intelligence Platform.

Validates JSON data integrity, referential relationships,
and ensures anomaly data aligns with sensor readings.

Usage:
    python validate_data.py
"""

import json
import sys
from pathlib import Path

# Data directory
DATA_DIR = Path(__file__).parent.parent / "app" / "data"


def load_json(filename: str) -> list[dict] | dict:
    """Load JSON file from data directory."""
    filepath = DATA_DIR / filename
    if filepath.exists():
        with open(filepath) as f:
            return json.load(f)
    return []


def validate_sites() -> tuple[bool, list[str]]:
    """Validate sites.json structure."""
    errors = []
    sites = load_json("sites.json")

    if not sites:
        errors.append("sites.json is empty or missing")
        return False, errors

    required_fields = ["id", "name", "address", "region", "type", "sqm", "floors"]
    site_ids = set()

    for i, site in enumerate(sites):
        for field in required_fields:
            if field not in site:
                errors.append(f"Site {i}: missing required field '{field}'")

        if "id" in site:
            if site["id"] in site_ids:
                errors.append(f"Duplicate site ID: {site['id']}")
            site_ids.add(site["id"])

    if len(errors) == 0:
        print(f"  ✓ sites.json: {len(sites)} sites validated")

    return len(errors) == 0, errors


def validate_equipment() -> tuple[bool, list[str], set]:
    """Validate equipment.json structure and site references."""
    errors = []
    equipment = load_json("equipment.json")
    sites = load_json("sites.json")

    if not equipment:
        errors.append("equipment.json is empty or missing")
        return False, errors, set()

    site_ids = {s["id"] for s in sites}
    equipment_ids = set()

    required_fields = ["id", "site_id", "type", "name", "manufacturer", "model"]

    for i, eq in enumerate(equipment):
        for field in required_fields:
            if field not in eq:
                errors.append(f"Equipment {i}: missing required field '{field}'")

        if "id" in eq:
            if eq["id"] in equipment_ids:
                errors.append(f"Duplicate equipment ID: {eq['id']}")
            equipment_ids.add(eq["id"])

        if "site_id" in eq and eq["site_id"] not in site_ids:
            errors.append(f"Equipment {eq.get('id', i)}: references non-existent site '{eq['site_id']}'")

    if len(errors) == 0:
        print(f"  ✓ equipment.json: {len(equipment)} items validated")

    return len(errors) == 0, errors, equipment_ids


def validate_sensors(equipment_ids: set) -> tuple[bool, list[str], set]:
    """Validate sensors.json structure and equipment references."""
    errors = []
    sensors = load_json("sensors.json")

    if not sensors:
        errors.append("sensors.json is empty or missing")
        return False, errors, set()

    sensor_ids = set()

    required_fields = ["id", "equipment_id", "site_id", "type", "unit", "name"]

    for i, sensor in enumerate(sensors):
        for field in required_fields:
            if field not in sensor:
                errors.append(f"Sensor {i}: missing required field '{field}'")

        if "id" in sensor:
            if sensor["id"] in sensor_ids:
                errors.append(f"Duplicate sensor ID: {sensor['id']}")
            sensor_ids.add(sensor["id"])

        if "equipment_id" in sensor and sensor["equipment_id"] not in equipment_ids:
            errors.append(f"Sensor {sensor.get('id', i)}: references non-existent equipment '{sensor['equipment_id']}'")

    if len(errors) == 0:
        print(f"  ✓ sensors.json: {len(sensors)} sensors validated")

    return len(errors) == 0, errors, sensor_ids


def validate_readings(sensor_ids: set) -> tuple[bool, list[str]]:
    """Validate readings.json structure and sensor references."""
    errors = []
    readings = load_json("readings.json")

    if not readings:
        errors.append("readings.json is empty or missing")
        return False, errors

    # Sample validation (don't check every reading for performance)
    sample_size = min(1000, len(readings))
    import random

    random.seed(42)
    sample = random.sample(readings, sample_size)

    missing_sensors = set()

    for reading in sample:
        if "sensor_id" not in reading:
            errors.append("Reading missing sensor_id")
        elif reading["sensor_id"] not in sensor_ids:
            missing_sensors.add(reading["sensor_id"])

        if "timestamp" not in reading:
            errors.append("Reading missing timestamp")

        if "value" not in reading:
            errors.append("Reading missing value")

    if missing_sensors:
        errors.append(f"Readings reference {len(missing_sensors)} non-existent sensors")

    if len(errors) == 0:
        print(f"  ✓ readings.json: {len(readings):,} readings validated (sampled {sample_size})")

    return len(errors) == 0, errors


def validate_anomalies(equipment_ids: set, sensor_ids: set) -> tuple[bool, list[str]]:
    """Validate anomalies.json structure and references."""
    errors = []
    anomalies = load_json("anomalies.json")

    if not anomalies:
        errors.append("anomalies.json is empty or missing")
        return False, errors

    required_fields = [
        "id",
        "equipment_id",
        "site_id",
        "type",
        "severity",
        "detected_date",
        "predicted_failure",
        "confidence",
        "root_cause",
        "repair_cost_zar",
        "damage_cost_zar",
    ]

    anomaly_ids = set()

    for i, anomaly in enumerate(anomalies):
        for field in required_fields:
            if field not in anomaly:
                errors.append(f"Anomaly {i}: missing required field '{field}'")

        if "id" in anomaly:
            if anomaly["id"] in anomaly_ids:
                errors.append(f"Duplicate anomaly ID: {anomaly['id']}")
            anomaly_ids.add(anomaly["id"])

        if "equipment_id" in anomaly and anomaly["equipment_id"] not in equipment_ids:
            errors.append(
                f"Anomaly {anomaly.get('id', i)}: references non-existent equipment '{anomaly['equipment_id']}'"
            )

        if "affected_sensor" in anomaly and anomaly["affected_sensor"] not in sensor_ids:
            errors.append(
                f"Anomaly {anomaly.get('id', i)}: references non-existent sensor '{anomaly['affected_sensor']}'"
            )

        # Validate cost logic
        if anomaly.get("repair_cost_zar", 0) >= anomaly.get("damage_cost_zar", 0):
            errors.append(f"Anomaly {anomaly.get('id', i)}: repair cost should be less than damage cost")

    if len(errors) == 0:
        print(f"  ✓ anomalies.json: {len(anomalies)} anomalies validated")

    return len(errors) == 0, errors


def validate_alerts(equipment_ids: set) -> tuple[bool, list[str]]:
    """Validate alerts.json structure and references."""
    errors = []
    alerts = load_json("alerts.json")

    if not alerts:
        errors.append("alerts.json is empty or missing")
        return False, errors

    required_fields = ["id", "equipment_id", "site_id", "type", "severity", "status", "title", "message", "created_at"]

    alert_ids = set()

    for i, alert in enumerate(alerts):
        for field in required_fields:
            if field not in alert:
                errors.append(f"Alert {i}: missing required field '{field}'")

        if "id" in alert:
            if alert["id"] in alert_ids:
                errors.append(f"Duplicate alert ID: {alert['id']}")
            alert_ids.add(alert["id"])

        if "equipment_id" in alert and alert["equipment_id"] not in equipment_ids:
            errors.append(f"Alert {alert.get('id', i)}: references non-existent equipment '{alert['equipment_id']}'")

    if len(errors) == 0:
        print(f"  ✓ alerts.json: {len(alerts)} alerts validated")

    return len(errors) == 0, errors


def validate_anomaly_sensor_alignment() -> tuple[bool, list[str]]:
    """Verify anomaly data aligns with actual sensor readings."""
    errors = []
    warnings = []

    anomalies = load_json("anomalies.json")
    readings = load_json("readings.json")

    if not anomalies or not readings:
        return True, []  # Skip if data missing

    # Index readings by sensor
    sensor_readings: dict[str, list[dict]] = {}
    for r in readings:
        sid = r["sensor_id"]
        if sid not in sensor_readings:
            sensor_readings[sid] = []
        sensor_readings[sid].append(r)

    for anomaly in anomalies:
        sensor_id = anomaly.get("affected_sensor")
        if not sensor_id:
            continue

        readings_list = sensor_readings.get(sensor_id, [])
        if not readings_list:
            warnings.append(f"Anomaly {anomaly['id']}: no readings for sensor {sensor_id}")
            continue

        # Get first and last readings
        readings_list.sort(key=lambda r: r["timestamp"])
        first_value = readings_list[0]["value"]
        last_value = readings_list[-1]["value"]

        # Verify trend direction
        current = anomaly.get("current_value")
        baseline = anomaly.get("baseline_value")
        trend = anomaly.get("trend")

        if trend == "increasing" and last_value < first_value * 0.9:
            warnings.append(f"Anomaly {anomaly['id']}: claims increasing trend but readings show decrease")

        if trend == "decreasing" and last_value > first_value * 1.1:
            warnings.append(f"Anomaly {anomaly['id']}: claims decreasing trend but readings show increase")

    if warnings:
        for w in warnings:
            print(f"  ⚠ {w}")
    else:
        print("  ✓ Anomaly-sensor alignment verified")

    return len(errors) == 0, errors


def main():
    """Run all validations."""
    print("\n" + "=" * 50)
    print("BMS Intelligence Data Validation")
    print("=" * 50 + "\n")

    all_valid = True
    all_errors = []

    # Validate each data file
    print("Validating data files...\n")

    valid, errors = validate_sites()
    all_valid = all_valid and valid
    all_errors.extend(errors)

    valid, errors, equipment_ids = validate_equipment()
    all_valid = all_valid and valid
    all_errors.extend(errors)

    valid, errors, sensor_ids = validate_sensors(equipment_ids)
    all_valid = all_valid and valid
    all_errors.extend(errors)

    valid, errors = validate_readings(sensor_ids)
    all_valid = all_valid and valid
    all_errors.extend(errors)

    valid, errors = validate_anomalies(equipment_ids, sensor_ids)
    all_valid = all_valid and valid
    all_errors.extend(errors)

    valid, errors = validate_alerts(equipment_ids)
    all_valid = all_valid and valid
    all_errors.extend(errors)

    print("\nValidating data alignment...\n")

    valid, errors = validate_anomaly_sensor_alignment()
    all_valid = all_valid and valid
    all_errors.extend(errors)

    # Summary
    print("\n" + "=" * 50)
    if all_valid:
        print("✓ ALL VALIDATIONS PASSED")
    else:
        print("✗ VALIDATION FAILED")
        print(f"\nErrors ({len(all_errors)}):")
        for error in all_errors[:20]:  # Show first 20 errors
            print(f"  - {error}")
        if len(all_errors) > 20:
            print(f"  ... and {len(all_errors) - 20} more errors")
    print("=" * 50 + "\n")

    return 0 if all_valid else 1


if __name__ == "__main__":
    sys.exit(main())
