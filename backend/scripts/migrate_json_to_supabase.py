#!/usr/bin/env python3
"""
Migrate JSON data to Supabase database.

This script reads the existing JSON files and inserts them into the Supabase database.
Run this once to seed the database with existing data.

Usage:
    cd backend && python3 -m scripts.migrate_json_to_supabase
"""

import json
import sys
from pathlib import Path
import uuid

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from supabase import create_client, Client  # noqa: E402
from dotenv import load_dotenv  # noqa: E402
import os  # noqa: E402

# Load environment
load_dotenv()

# Data directory
DATA_DIR = Path(__file__).parent.parent / "app" / "data"


def get_supabase() -> Client:
    """Get Supabase client."""
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise ValueError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set")
    return create_client(url, key)


def load_json(filename: str) -> list:
    """Load JSON file."""
    filepath = DATA_DIR / filename
    if filepath.exists():
        with open(filepath) as f:
            return json.load(f)
    return []


def generate_uuid(seed: str) -> str:
    """Generate deterministic UUID from seed for consistent IDs."""
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, seed))


def migrate_buildings(supabase: Client) -> dict:
    """Migrate sites.json to buildings table. Returns id mapping."""
    print("\n📦 Migrating buildings...")
    sites = load_json("sites.json")
    id_map = {}

    for site in sites:
        new_id = generate_uuid(site["id"])
        id_map[site["id"]] = new_id

        record = {
            "id": new_id,
            "code": site["id"],
            "name": site["name"],
            "address": site.get("address", ""),
            "region": site.get("region", ""),
            "type": site.get("type", "branch"),
            "sqm": site.get("sqm", 0),
            "floors": site.get("floors", 1),
            "year_built": site.get("year_built"),
            "latitude": site.get("latitude"),
            "longitude": site.get("longitude"),
            "contact_email": site.get("contact_email"),
            "contact_phone": site.get("contact_phone"),
            "operating_hours": site.get("operating_hours"),
            "occupancy_pattern": site.get("occupancy_pattern", "office"),
            "optimization_enabled": site.get("optimization_enabled", False),
            "optimization_status": site.get("optimization_status"),
            "optimization_settings": site.get("optimization_settings"),
            "optimization_history": site.get("optimization_history"),
            "last_recommendation": site.get("last_recommendation"),
        }

        try:
            supabase.table("buildings").upsert(record).execute()
            print(f"  ✓ {site['name']}")
        except Exception as e:
            print(f"  ✗ {site['name']}: {e}")

    print(f"  Migrated {len(sites)} buildings")
    return id_map


def migrate_equipment(supabase: Client, building_map: dict) -> dict:
    """Migrate equipment.json to equipment table. Returns id mapping."""
    print("\n⚙️ Migrating equipment...")
    equipment = load_json("equipment.json")
    id_map = {}
    count = 0

    for item in equipment:
        site_id = item.get("site_id")
        building_id = building_map.get(site_id)
        if not building_id:
            print(f"  ⚠ Skipping {item['id']}: no building for site {site_id}")
            continue

        new_id = generate_uuid(item["id"])
        id_map[item["id"]] = new_id

        # Combine capacity with unit if present
        capacity = item.get("rated_capacity", item.get("capacity"))
        if capacity and item.get("capacity_unit"):
            capacity = f"{capacity} {item['capacity_unit']}"

        record = {
            "id": new_id,
            "code": item["id"],
            "building_id": building_id,
            "name": item.get("name", ""),
            "type": item.get("type", "unknown"),
            "manufacturer": item.get("manufacturer"),
            "model": item.get("model"),
            "serial_number": item.get("serial_number"),
            "install_date": item.get("install_date"),
            "status": item.get("status", "normal"),
            "location": item.get("location"),
            "capacity": str(capacity) if capacity else None,
            "last_service": item.get("last_maintenance") or item.get("last_service"),
            "health_score": item.get("health_score"),
        }

        try:
            supabase.table("equipment").upsert(record).execute()
            count += 1
        except Exception as e:
            print(f"  ✗ {item['id']}: {e}")

    print(f"  Migrated {count} equipment items")
    return id_map


def migrate_sensors(supabase: Client, equipment_map: dict) -> dict:
    """Migrate sensors.json to sensors table."""
    print("\n📊 Migrating sensors...")
    sensors = load_json("sensors.json")
    id_map = {}
    count = 0
    skipped = 0

    # Valid sensor types from schema
    valid_types = {"temperature", "humidity", "pressure", "flow", "energy", "vibration"}

    for sensor in sensors:
        equipment_id = sensor.get("equipment_id")
        db_equipment_id = equipment_map.get(equipment_id)
        if not db_equipment_id:
            skipped += 1
            continue

        # Map sensor type to valid type
        sensor_type = sensor.get("type", "temperature").lower()
        if sensor_type not in valid_types:
            # Try to map common types
            type_mapping = {
                "analog": "temperature",
                "digital": "temperature",
                "power": "energy",
                "current": "energy",
                "voltage": "energy",
                "speed": "flow",
                "rpm": "flow",
                "level": "pressure",
            }
            sensor_type = type_mapping.get(sensor_type, "temperature")

        new_id = generate_uuid(sensor["id"])
        id_map[sensor["id"]] = new_id

        record = {
            "id": new_id,
            "code": sensor["id"],
            "equipment_id": db_equipment_id,
            "type": sensor_type,
            "unit": sensor.get("unit", ""),
            "location": sensor.get("location"),
            "min_value": sensor.get("min_value"),
            "max_value": sensor.get("max_value"),
            "current_value": sensor.get("current_value") or sensor.get("value"),
        }

        try:
            supabase.table("sensors").upsert(record).execute()
            count += 1
        except Exception:
            skipped += 1

    print(f"  Migrated {count} sensors (skipped {skipped})")
    return id_map


def migrate_alerts(supabase: Client, building_map: dict, equipment_map: dict):
    """Migrate alerts.json to alerts table."""
    print("\n🚨 Migrating alerts...")
    alerts = load_json("alerts.json")
    count = 0

    for alert in alerts:
        site_id = alert.get("site_id")
        building_id = building_map.get(site_id)
        equipment_id = equipment_map.get(alert.get("equipment_id"))

        if not building_id:
            continue

        new_id = generate_uuid(alert.get("id", f"alert-{count}"))

        record = {
            "id": new_id,
            "building_id": building_id,
            "equipment_id": equipment_id,
            "type": alert.get("type", "system"),
            "title": alert.get("title", alert.get("message", "Alert")),
            "message": alert.get("message", ""),
            "severity": alert.get("severity", "info"),
            "status": alert.get("status", "active"),
            "created_at": alert.get("timestamp") or alert.get("created_at"),
            "acknowledged_at": alert.get("acknowledged_at"),
            "acknowledged_by": alert.get("acknowledged_by"),
        }

        try:
            supabase.table("alerts").upsert(record).execute()
            count += 1
        except Exception as e:
            print(f"  ✗ Alert: {e}")

    print(f"  Migrated {count} alerts")


def migrate_predictions(supabase: Client, building_map: dict, equipment_map: dict):
    """Migrate predictions.json to predictions table."""
    print("\n🔮 Migrating predictions...")
    predictions = load_json("predictions.json")
    count = 0

    for pred in predictions:
        equipment_id = equipment_map.get(pred.get("equipment_id"))
        site_id = pred.get("site_id")
        building_id = building_map.get(site_id)

        if not equipment_id or not building_id:
            continue

        new_id = generate_uuid(pred.get("id", f"pred-{count}"))

        # Convert confidence to text (high/medium/low)
        confidence_val = pred.get("confidence", 0.5)
        if isinstance(confidence_val, (int, float)):
            if confidence_val >= 0.8:
                confidence = "high"
            elif confidence_val >= 0.5:
                confidence = "medium"
            else:
                confidence = "low"
        else:
            confidence = str(confidence_val) if confidence_val else "medium"

        # Map status
        status = pred.get("status", "active")
        valid_statuses = {"active", "acknowledged", "resolved", "false_positive"}
        if status not in valid_statuses:
            status = "active"

        # Map severity
        severity = pred.get("severity", "medium")
        valid_severities = {"critical", "high", "medium", "low"}
        if severity not in valid_severities:
            severity = "medium"

        record = {
            "id": new_id,
            "code": pred.get("id", f"PRED-{count:04d}"),
            "equipment_id": equipment_id,
            "building_id": building_id,
            "prediction_type": pred.get("type", "maintenance"),
            "probability_percent": int(confidence_val * 100) if isinstance(confidence_val, float) else 50,
            "confidence": confidence,
            "predicted_failure_date": pred.get("predicted_date"),
            "timeframe_days": pred.get("timeframe_days"),
            "severity": severity,
            "status": status,
            "evidence": {"description": pred.get("description", ""), "reasoning": pred.get("reasoning")},
            "recommended_action": pred.get("recommendation") or pred.get("recommended_action"),
        }

        try:
            supabase.table("predictions").upsert(record).execute()
            count += 1
        except Exception as e:
            print(f"  ✗ Prediction: {e}")

    print(f"  Migrated {count} predictions")


def migrate_anomalies(supabase: Client, building_map: dict, equipment_map: dict):
    """Migrate anomalies.json to anomalies table."""
    print("\n🔍 Migrating anomalies...")
    anomalies = load_json("anomalies.json")
    count = 0

    for anomaly in anomalies:
        equipment_id = equipment_map.get(anomaly.get("equipment_id"))
        site_id = anomaly.get("site_id")
        building_id = building_map.get(site_id)

        if not building_id:
            continue

        new_id = generate_uuid(anomaly.get("id", f"anomaly-{count}"))

        # Map status to valid values
        status = anomaly.get("status", "active")
        valid_statuses = {"active", "investigating", "resolved", "false_positive"}
        if status not in valid_statuses:
            status = "active"

        # Map severity
        severity = anomaly.get("severity", "warning")
        valid_severities = {"info", "warning", "critical"}
        if severity not in valid_severities:
            severity = "warning"

        # Get detected_at from various possible field names
        detected_at = (
            anomaly.get("detected_at")
            or anomaly.get("detected_date")
            or anomaly.get("timestamp")
            or anomaly.get("start_date")
            or "2026-01-28"
        )

        record = {
            "id": new_id,
            "code": anomaly.get("id", f"ANOM-{count:04d}"),
            "equipment_id": equipment_id,
            "building_id": building_id,
            "type": anomaly.get("type", "unknown"),
            "severity": severity,
            "status": status,
            "detected_at": detected_at,
            "description": anomaly.get("description") or anomaly.get("root_cause") or "Anomaly detected",
            "root_cause": anomaly.get("root_cause"),
            "confidence": anomaly.get("confidence"),
        }

        try:
            supabase.table("anomalies").upsert(record).execute()
            count += 1
        except Exception as e:
            print(f"  ✗ Anomaly: {e}")

    print(f"  Migrated {count} anomalies")


def main():
    """Run the migration."""
    print("=" * 60)
    print("BMS Intelligence - JSON to Supabase Migration")
    print("=" * 60)

    supabase = get_supabase()
    print(f"\n✓ Connected to Supabase at {os.getenv('SUPABASE_URL')}")

    # Migrate in order of dependencies
    building_map = migrate_buildings(supabase)
    equipment_map = migrate_equipment(supabase, building_map)
    _sensor_map = migrate_sensors(supabase, equipment_map)
    migrate_alerts(supabase, building_map, equipment_map)
    migrate_predictions(supabase, building_map, equipment_map)
    migrate_anomalies(supabase, building_map, equipment_map)

    print("\n" + "=" * 60)
    print("✅ Migration complete!")
    print("=" * 60)
    print("\nNote: sensor_readings migration skipped (24MB file).")
    print("The system will continue to use JSON for time-series data.")


if __name__ == "__main__":
    main()
