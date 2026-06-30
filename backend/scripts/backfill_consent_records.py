"""Backfill consent records from JSON to Supabase.
Writes a temp SQL file and executes with psql.
Idempotent — skips records that already exist.
"""

import json
import logging
import os
import subprocess
import tempfile
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

DATA_FILE = Path(__file__).parent.parent / "app" / "data" / "consent_records.json"
DB_URL = os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:6432/postgres")


def _json_safe(val):
    if val is None:
        return "null"
    return json.dumps(val)


def backfill() -> int:
    if not DATA_FILE.exists():
        logger.warning("No consent_records.json found at %s", DATA_FILE)
        return 0

    data = json.loads(DATA_FILE.read_text())
    records = data.get("records", [])
    if not records:
        logger.info("No records in consent_records.json")
        return 0

    # Get existing IDs
    out = subprocess.run(
        ["psql", DB_URL, "-tAc", "SELECT record_id::text FROM public.consent_records"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    existing_ids = set(out.stdout.strip().split("\n")) if out.stdout.strip() else set()

    lines = []
    inserted = 0
    skipped = 0

    for rec in records:
        rid = rec.get("record_id", "")
        if rid and rid in existing_ids:
            skipped += 1
            continue

        lines.append(
            f"INSERT INTO public.consent_records "
            f"(record_id, data_subject_id, platform, consent_type, consent_given, "
            f"consent_text, given_at, expires_at, withdrawn_at, ip_address, metadata) VALUES ("
            f"'{rid}'::uuid, "
            f"'{rec['data_subject_id']}', "
            f"'{rec['platform']}', "
            f"'{rec['consent_type']}', "
            f"{str(rec['consent_given']).lower()}, "
            f"'{rec['consent_text'].replace(chr(39), chr(39) + chr(39))}', "
            f"'{rec['given_at']}'::timestamptz, "
            + (f"'{rec['expires_at']}'::timestamptz" if rec.get("expires_at") else "NULL")
            + ", "
            + (f"'{rec['withdrawn_at']}'::timestamptz" if rec.get("withdrawn_at") else "NULL")
            + ", "
            + (f"'{rec['ip_address']}'" if rec.get("ip_address") else "NULL")
            + f", '{_json_safe(rec.get('metadata', {}))}'::jsonb"
            f");"
        )
        inserted += 1

    if not lines:
        logger.info("All %d records already exist in Supabase", skipped)
        return 0

    with tempfile.NamedTemporaryFile(mode="w", suffix=".sql", delete=False) as f:
        f.write("BEGIN;\n")
        for line in lines:
            f.write(line + "\n")
        f.write("COMMIT;\n")
        sql_path = f.name

    try:
        result = subprocess.run(
            ["psql", DB_URL, "-f", sql_path],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            logger.error("Backfill failed: %s", result.stderr.strip()[:500])
            return 1
        logger.info("Backfill: %d inserted, %d skipped", inserted, skipped)
    finally:
        Path(sql_path).unlink(missing_ok=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(backfill())
