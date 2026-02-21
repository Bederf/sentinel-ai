#!/usr/bin/env python3
"""Backfill recommendations from JSON fallback into Supabase.

One-time migration script. Reads backend/app/data/recommendations.json
and batch-inserts into the recommendations table (created by migration 102).

Usage:
    cd backend && python -m scripts.backfill_recommendations_to_supabase
"""

import json
import sys
from pathlib import Path

import psycopg2
from psycopg2.extras import execute_values

# JSON source
DATA_FILE = Path(__file__).parent.parent / "app" / "data" / "recommendations.json"

# Local Supabase connection
DB_DSN = "host=127.0.0.1 port=55322 dbname=postgres user=postgres password=postgres"

BATCH_SIZE = 100

COLUMNS = [
    "id",
    "site_id",
    "timestamp",
    "action_type",
    "risk_level",
    "target_equipment",
    "action",
    "reason",
    "expected_impact",
    "confidence",
    "confidence_score",
    "profile",
    "multi_objective_score",
    "status",
    "requires_approval",
    "approved_by",
    "approval_reason",
    "executed_at",
    "execution_result",
    "rejection_reason",
]


def load_json() -> list[dict]:
    """Load recommendation records from JSON file."""
    with open(DATA_FILE) as f:
        data = json.load(f)
    recs = data.get("recommendations", {})
    # JSON stores as {id: {...}}, flatten to list
    return list(recs.values())


def to_row(rec: dict) -> tuple:
    """Convert a recommendation dict to a tuple matching COLUMNS order."""
    return (
        rec.get("id"),
        rec.get("site_id", ""),
        rec.get("timestamp"),
        rec.get("action_type", ""),
        rec.get("risk_level", "medium"),
        rec.get("target_equipment", ""),
        json.dumps(rec.get("action", {})),
        rec.get("reason", ""),
        json.dumps(rec.get("expected_impact", {})),
        rec.get("confidence", "medium"),
        float(rec.get("confidence_score", 0.0)),
        rec.get("profile", ""),
        float(rec.get("multi_objective_score", 0.0)),
        rec.get("status", "pending"),
        bool(rec.get("requires_approval", False)),
        rec.get("approved_by"),
        rec.get("approval_reason"),
        rec.get("executed_at"),
        json.dumps(rec["execution_result"]) if rec.get("execution_result") else None,
        rec.get("rejection_reason"),
    )


def main():
    if not DATA_FILE.exists():
        print(f"ERROR: {DATA_FILE} not found")
        sys.exit(1)

    records = load_json()
    print(f"Loaded {len(records)} recommendations from JSON")

    conn = psycopg2.connect(DB_DSN)
    cur = conn.cursor()

    # Check how many already exist (idempotent re-runs)
    cur.execute("SELECT count(*) FROM recommendations")
    existing = cur.fetchone()[0]
    if existing > 0:
        print(f"Table already has {existing} rows. Skipping duplicates via ON CONFLICT.")

    col_list = ", ".join(COLUMNS)
    placeholders = ", ".join(["%s"] * len(COLUMNS))

    inserted = 0
    skipped = 0
    errors = 0

    for i in range(0, len(records), BATCH_SIZE):
        batch = records[i : i + BATCH_SIZE]
        rows = []
        for rec in batch:
            try:
                rows.append(to_row(rec))
            except Exception as e:
                print(f"  SKIP bad record {rec.get('id', '?')}: {e}")
                errors += 1

        if not rows:
            continue

        try:
            sql = f"""
                INSERT INTO recommendations ({col_list})
                VALUES %s
                ON CONFLICT (id) DO NOTHING
            """
            execute_values(cur, sql, rows, template=f"({placeholders})")
            batch_inserted = cur.rowcount
            inserted += batch_inserted
            skipped += len(rows) - batch_inserted
            conn.commit()
            print(f"  Batch {i // BATCH_SIZE + 1}: {batch_inserted} inserted, {len(rows) - batch_inserted} skipped")
        except Exception as e:
            conn.rollback()
            print(f"  ERROR in batch {i // BATCH_SIZE + 1}: {e}")
            errors += len(rows)

    cur.close()
    conn.close()

    print(f"\nDone: {inserted} inserted, {skipped} skipped (duplicates), {errors} errors")
    print(f"Total in JSON: {len(records)}")


if __name__ == "__main__":
    main()
