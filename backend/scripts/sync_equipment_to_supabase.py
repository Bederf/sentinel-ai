#!/usr/bin/env python3
"""Sync Supabase equipment table to match JSON equipment files.

Deletes all S002-% equipment from Supabase (and dependent rows in
work_orders, predictions, alerts) and re-inserts from the 90 JSON
equipment files in backend/app/data/buildings/site-002/equipment/.

This updates the authoritative Postgres state only.

Usage:
    cd backend && python scripts/sync_equipment_to_supabase.py
"""

import json
import os
from pathlib import Path

import psycopg2
import psycopg2.extras

# Resolve paths
SCRIPT_DIR = Path(__file__).parent
BACKEND_DIR = SCRIPT_DIR.parent
EQUIPMENT_DIR = BACKEND_DIR / "app" / "data" / "sites" / "site-002" / "equipment"
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@127.0.0.1:55322/postgres",
)

BUILDING_ID = "d73a5a5f-6de5-4081-8c46-411954013156"


def load_equipment_files() -> list[dict]:
    """Load all JSON equipment files and return insert-ready dicts."""
    records = []
    for path in sorted(EQUIPMENT_DIR.glob("*.json")):
        with open(path) as f:
            data = json.load(f)

        code = path.stem  # e.g. S002-AHU-B1-001
        name = data.get("name", code)
        eq_type = data.get("equipment_type", "unknown")
        health = data.get("health_score", 100)
        metadata = json.dumps({"source": "onboarding_discovery"})

        records.append(
            {
                "code": code,
                "site_id": BUILDING_ID,
                "name": name,
                "type": eq_type,
                "status": "normal",
                "health_score": health,
                "operating_data": "{}",
                "network_info": "{}",
                "device_info": "{}",
                "metadata": metadata,
            }
        )

    return records


def main():
    print(f"Connecting to: {DATABASE_URL.split('@')[1] if '@' in DATABASE_URL else DATABASE_URL}")
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        # ── Step 1: Count existing S002 equipment ──
        cur.execute("SELECT count(*) as cnt FROM equipment WHERE code LIKE 'S002-%%'")
        existing = cur.fetchone()["cnt"]
        print(f"\nExisting S002 equipment: {existing}")

        # ── Step 2: Delete dependent rows ──
        dependent_tables = [
            ("work_orders", "equipment_id"),
            ("predictions", "equipment_id"),
            ("alerts", "equipment_id"),
        ]

        for table, col in dependent_tables:
            cur.execute(f"DELETE FROM {table} WHERE {col} IN (SELECT id FROM equipment WHERE code LIKE 'S002-%%')")
            print(f"  Deleted {cur.rowcount} rows from {table}")

        # ── Step 3: Delete all S002 equipment ──
        cur.execute("DELETE FROM equipment WHERE code LIKE 'S002-%%'")
        print(f"  Deleted {cur.rowcount} equipment records")

        # ── Step 4: Insert from JSON files ──
        records = load_equipment_files()
        print(f"\nInserting {len(records)} equipment records from JSON...")

        insert_sql = """
            INSERT INTO equipment (
                site_id, code, name, type, status, health_score,
                operating_data, network_info, device_info
            ) VALUES (
                %(site_id)s, %(code)s, %(name)s, %(type)s, %(status)s,
                %(health_score)s,
                %(operating_data)s::jsonb, %(network_info)s::jsonb, %(device_info)s::jsonb
            )
        """

        for rec in records:
            cur.execute(insert_sql, rec)

        print(f"  Inserted {len(records)} records")

        # ── Step 5: Verify ──
        cur.execute("SELECT count(*) as cnt FROM equipment WHERE code LIKE 'S002-%%'")
        final_count = cur.fetchone()["cnt"]

        cur.execute(
            "SELECT type, count(*) as cnt FROM equipment WHERE code LIKE 'S002-%%' GROUP BY type ORDER BY cnt DESC"
        )
        type_counts = cur.fetchall()

        print(f"\n{'=' * 50}")
        print(f"Final S002 equipment count: {final_count}")
        print("\nBy type:")
        for row in type_counts:
            print(f"  {row['type']:25s} {row['cnt']}")

        # ── Step 6: Commit ──
        conn.commit()
        print("\n✓ Committed successfully")

        print("\n✓ Done!")

    except Exception as e:
        conn.rollback()
        print(f"\n✗ Error: {e}")
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
