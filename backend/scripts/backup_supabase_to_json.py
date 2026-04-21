#!/usr/bin/env python3
"""Legacy JSON export helper.

JSON files are no longer used as SENTINEL backups.
The authoritative backup path is PostgreSQL logical backup.

This script is retained only for exceptional one-off export/archive work and
is disabled by default.

Usage:
    python3 scripts/backup_supabase_to_json.py
"""

import json
import os
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import psycopg2
import psycopg2.extras

# Resolve paths
SCRIPT_DIR = Path(__file__).parent
BACKEND_DIR = SCRIPT_DIR.parent
REPO_ROOT = BACKEND_DIR.parent
JSON_BACKUP_ROOT = REPO_ROOT / "backups" / "json" / "manual"

# Load DATABASE_URL from .env
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:55322/postgres")

BUILDING_ID = "d73a5a5f-6de5-4081-8c46-411954013156"
BUILDING_CODE = "site-002"


def json_serializer(obj):
    """Handle non-serializable types."""
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, UUID):
        return str(obj)
    if isinstance(obj, memoryview):
        return obj.tobytes().decode("utf-8", errors="replace")
    if isinstance(obj, bytes):
        return obj.decode("utf-8", errors="replace")
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


def query_table(cur, table: str, where: str = "", params: tuple = ()) -> list[dict]:
    """Query a table and return rows as list of dicts."""
    sql = f"SELECT * FROM {table}"
    if where:
        sql += f" WHERE {where}"
    sql += " ORDER BY 1"  # order by first column
    try:
        cur.execute(sql, params)
        columns = [desc[0] for desc in cur.description]
        rows = cur.fetchall()
        return [dict(zip(columns, row, strict=False)) for row in rows]
    except Exception as e:
        print(f"  SKIP {table}: {e}")
        cur.connection.rollback()
        return []


def save_json(data: list | dict, filepath: Path):
    """Save data to JSON file."""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2, default=json_serializer)
    count = len(data) if isinstance(data, list) else 1
    print(f"  -> {filepath.relative_to(REPO_ROOT)} ({count} rows)")


def main():
    if os.getenv("ALLOW_LEGACY_JSON_EXPORT", "").strip() != "1":
        raise SystemExit(
            "Legacy JSON export is disabled. JSON files are no longer used as backups. "
            "Use scripts/backup/postgres_logical_backup.sh for operational backups."
        )

    print(f"Connecting to: {DATABASE_URL.split('@')[1] if '@' in DATABASE_URL else DATABASE_URL}")
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = JSON_BACKUP_ROOT / f"supabase_export_{timestamp}"
    backup_dir.mkdir(parents=True, exist_ok=True)
    print(f"Backup timestamp: {timestamp}")
    print(f"Backup dir: {backup_dir}")
    print()

    # =========================================================================
    # Tables filtered by site_id
    # =========================================================================
    site_id_tables = [
        "alerts",
        "anomalies",
        "predictions",
        "recommendations",
        "work_orders",
        "equipment",
        "hvac_zones",
        "hvac_zone_history",
        "desks",
        "zones",
        "complaints",
        "inspection_tasks",
        "inspection_results",
        "inspection_deficiencies",
        "inspection_measurements",
        "inspection_schedules",
        "service_records",
        "occupancy_history",
        "occupancy_control_actions",
        "energy_consumption_history",
        "lighting_energy",
        "dali_controllers",
        "dali_luminaires",
        "dali_sensors",
        "dali_zones",
        "dali_zone_mapping",
        "cost_validations",
        "power_meter_validations",
        "budget_alerts",
        "budgets",
        "condition_assessments",
        "compliance_audits",
        "compliance_log",
        "security_access_zones",
        "security_badge_events",
        "security_cameras",
        "security_doors",
        "security_occupancy",
        "security_anomalies",
        "water_consumption",
        "water_alerts",
        "fire_zones",
        "fire_alarms",
        "fire_dampers",
        "fire_equipment_tracking",
        "emergency_light_testing",
        "electrical_compliance",
        "solar_annual_simulations",
        "solar_annual_tasks",
        "solar_daily_aggregates",
        "solar_hourly_snapshots",
        "workflow_events",
        "parasite_decisions",
        "baseline_comparisons",
        "asset_baseline_assessments",
        "equipment_baselines",
        "element_baselines",
        "audit_log",
    ]

    print("=== Tables with site_id filter ===")
    for table in site_id_tables:
        # Check if table has site_id column
        cur.execute(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s AND column_name = 'site_id'
        """,
            (table,),
        )
        if cur.fetchone():
            data = query_table(cur, table, "site_id = %s", (BUILDING_ID,))
            if data:
                save_json(data, backup_dir / f"{table}.json")
            else:
                print(f"  {table}: 0 rows (skipping file)")
        else:
            print(f"  {table}: no site_id column, checking site_id...")
            # Try site_id
            cur.execute(
                """
                SELECT column_name FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = %s AND column_name = 'site_id'
            """,
                (table,),
            )
            if cur.fetchone():
                data = query_table(cur, table, "site_id = %s", (BUILDING_CODE,))
                if data:
                    save_json(data, backup_dir / f"{table}.json")
                else:
                    print(f"  {table}: 0 rows (skipping file)")
            else:
                print(f"  {table}: no site_id or site_id column (skip)")

    # =========================================================================
    # Tables filtered by equipment_id (equipment belonging to site-002)
    # =========================================================================
    print()
    print("=== Getting site-002 equipment IDs ===")
    cur.execute("SELECT id FROM equipment WHERE site_id = %s", (BUILDING_ID,))
    equipment_ids = [row[0] for row in cur.fetchall()]
    print(f"  Found {len(equipment_ids)} equipment items")

    equipment_id_tables = [
        "equipment_sensor_readings",
        "equipment_elements",
        "equipment_knowledge",
        "equipment_notes_history",
        "sensor_anomalies",
        "sensor_recordings",
        "service_observations",
        "service_readings",
        "service_attachments",
        "asset_run_reports",
        "point_asset_mappings",
    ]

    if equipment_ids:
        print()
        print("=== Tables with equipment_id filter ===")
        for table in equipment_id_tables:
            cur.execute(
                """
                SELECT column_name FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = %s AND column_name = 'equipment_id'
            """,
                (table,),
            )
            if cur.fetchone():
                # Use ANY array for efficiency
                data = query_table(cur, table, "equipment_id = ANY(%s)", (equipment_ids,))
                if data:
                    save_json(data, backup_dir / f"{table}.json")
                else:
                    print(f"  {table}: 0 rows (skipping file)")
            else:
                print(f"  {table}: no equipment_id column (skip)")

    # =========================================================================
    # Building record itself
    # =========================================================================
    print()
    print("=== Building record ===")
    data = query_table(cur, "sites", "id = %s", (BUILDING_ID,))
    if data:
        save_json(data, backup_dir / "sites.json")

    # =========================================================================
    # Energy centre and related electrical infrastructure
    # =========================================================================
    print()
    print("=== Energy centre / electrical infrastructure ===")
    energy_tables = [
        ("energy_centres", "site_id"),
        ("generators", "site_id"),
        ("generator_groups", "site_id"),
        ("generator_run_history", "site_id"),
        ("diesel_tanks", "site_id"),
        ("transformers", "site_id"),
        ("lv_switchboards", "site_id"),
        ("mv_incomers", "site_id"),
        ("power_meters", "site_id"),
        ("feeders", "site_id"),
        ("pfc_banks", "site_id"),
        ("ups_systems", "site_id"),
        ("ats_units", "site_id"),
        ("bess_containers", "site_id"),
        ("solar_plants", "site_id"),
        ("solar_inverters", "site_id"),
        ("solar_meters", "site_id"),
        ("solar_bess", "site_id"),
        ("solar_sites", "site_id"),
        ("solar_readings", "site_id"),
    ]

    for table, col in energy_tables:
        cur.execute(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s AND column_name = %s
        """,
            (table, col),
        )
        if cur.fetchone():
            data = query_table(cur, table, f"{col} = %s", (BUILDING_ID,))
            if data:
                save_json(data, backup_dir / f"{table}.json")
            else:
                print(f"  {table}: 0 rows")
        else:
            # Try site_id
            cur.execute(
                """
                SELECT column_name FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = %s AND column_name = 'site_id'
            """,
                (table,),
            )
            if cur.fetchone():
                data = query_table(cur, table, "site_id = %s", (BUILDING_CODE,))
                if data:
                    save_json(data, backup_dir / f"{table}.json")
                else:
                    print(f"  {table}: 0 rows")
            else:
                print(f"  {table}: no {col}/site_id column")

    # =========================================================================
    # Global tables (not site-specific but needed for full restore)
    # =========================================================================
    print()
    print("=== Global reference tables ===")
    global_tables = [
        "ml_models",
        "model_thresholds",
        "health_score_weights",
        "safety_rules",
        "site_modules",
        "site_module_configs",
        "technicians",
        "site_technicians",
        "feature_definitions",
        "alarm_code_mappings",
        "alarm_taxonomy",
        "severity_mappings",
        "inspection_checklist_templates",
        "system_settings",
    ]

    for table in global_tables:
        data = query_table(cur, table)
        if data:
            save_json(data, backup_dir / f"{table}.json")
        else:
            print(f"  {table}: 0 rows")

    # =========================================================================
    # Summary
    # =========================================================================
    print()
    manifest = {
        "timestamp": timestamp,
        "export_type": "secondary_json_snapshot",
        "source_of_truth": "local_supabase_postgres",
        "building_id": BUILDING_ID,
        "building_code": BUILDING_CODE,
    }
    save_json(manifest, backup_dir / "export_manifest.json")

    backup_files = list(backup_dir.glob("*.json"))
    total_size = sum(f.stat().st_size for f in backup_files)
    print("=== BACKUP COMPLETE ===")
    print(f"  Files: {len(backup_files)}")
    print(f"  Size: {total_size / 1024:.1f} KB")
    print(f"  Location: {backup_dir}")

    conn.close()


if __name__ == "__main__":
    main()
