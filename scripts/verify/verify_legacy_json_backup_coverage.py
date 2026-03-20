#!/usr/bin/env python3
"""Verify legacy JSON backup files map to live Postgres tables.

This script does not treat JSON as authoritative.
It exists only to help decide whether the legacy JSON backup folder can be
archived after confirming that each JSON file corresponds to data that exists
in the current local Supabase/Postgres database.

Checks performed:
- each `*.json` file in backend/app/data/supabase_backup
- matching table name across non-system schemas
- live row count for the matching table
- row count in the JSON file itself

Important:
- JSON row counts are not required to match live DB row counts exactly
  because the legacy exports are often site-scoped snapshots
- the key archival question is table coverage, not strict count parity
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import psycopg2


REPO_ROOT = Path(__file__).resolve().parents[2]
LEGACY_JSON_DIR = REPO_ROOT / "backend" / "app" / "data" / "supabase_backup"
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@127.0.0.1:55322/postgres",
)
SYSTEM_SCHEMAS = {"pg_catalog", "information_schema", "pg_toast"}


def load_json_row_count(path: Path) -> int:
    with open(path) as handle:
        payload = json.load(handle)
    if isinstance(payload, list):
        return len(payload)
    if isinstance(payload, dict):
        return 1
    return 0


def find_matching_tables(cur, table_name: str) -> list[tuple[str, str]]:
    cur.execute(
        """
        SELECT table_schema, table_name
        FROM information_schema.tables
        WHERE table_name = %s
          AND table_schema NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
        ORDER BY
          CASE WHEN table_schema = 'public' THEN 0 ELSE 1 END,
          table_schema,
          table_name
        """,
        (table_name,),
    )
    return [(schema, name) for schema, name in cur.fetchall() if schema not in SYSTEM_SCHEMAS]


def count_table_rows(cur, schema: str, table: str) -> int:
    cur.execute(f'SELECT COUNT(*) FROM "{schema}"."{table}"')
    return int(cur.fetchone()[0])


def main() -> int:
    if not LEGACY_JSON_DIR.exists():
        print(f"Legacy JSON directory not found: {LEGACY_JSON_DIR}", file=sys.stderr)
        return 2

    json_files = sorted(LEGACY_JSON_DIR.glob("*.json"))
    if not json_files:
        print(f"No legacy JSON files found in: {LEGACY_JSON_DIR}")
        return 0

    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    missing: list[str] = []

    print("Legacy JSON backup coverage check")
    print(f"JSON dir: {LEGACY_JSON_DIR}")
    print(f"Files found: {len(json_files)}")
    print()
    print("file | json_rows | matched_table | live_db_rows | status")
    print("-" * 88)

    for path in json_files:
        table_name = path.stem
        json_rows = load_json_row_count(path)
        matches = find_matching_tables(cur, table_name)

        if not matches:
            missing.append(table_name)
            print(f"{path.name} | {json_rows} | - | - | MISSING")
            continue

        schema, matched_table = matches[0]
        db_rows = count_table_rows(cur, schema, matched_table)
        status = "OK"
        if len(matches) > 1:
            status = f"OK (multiple matches: {', '.join(f'{s}.{t}' for s, t in matches)})"

        print(f"{path.name} | {json_rows} | {schema}.{matched_table} | {db_rows} | {status}")

    print()
    if missing:
        print("Missing table mappings:")
        for name in missing:
            print(f"- {name}")
        return 1

    print("All legacy JSON backup files map to live database tables.")
    print("Counts are informational only; legacy JSON exports are not expected to match live row counts exactly.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
