"""Self-bootstrapping SQL migration runner with checksum validation.

Idempotent: safe to run on fresh Supabase and on restarts.
Skips already-locked files. Raises on checksum drift.
"""

from __future__ import annotations

import hashlib
import logging
import os
import sys
from pathlib import Path

# Ensure backend is on path when imported as module
_backend_path = Path(__file__).parent.parent.parent
if str(_backend_path) not in sys.path:
    sys.path.insert(0, str(_backend_path))

logger = logging.getLogger("sentinel.migrations")

MIGRATIONS_DIR = Path(__file__).parent.parent.parent.parent / "supabase" / "migrations"
LOCK_TABLE = "_migration_lock"


def compute_checksum(path: Path) -> str:
    return hashlib.md5(path.read_bytes(), usedforsecurity=False).hexdigest()


def get_db_connection():
    conn_str = os.environ.get("DATABASE_URL")
    if not conn_str:
        raise RuntimeError("DATABASE_URL not set")
    import psycopg2

    return psycopg2.connect(conn_str)


def ensure_lock_table(conn):
    with conn.cursor() as cur:
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS {LOCK_TABLE} (
                filename TEXT PRIMARY KEY,
                applied_at TIMESTAMPTZ DEFAULT NOW(),
                checksum TEXT
            );
        """)
    conn.commit()


def get_applied_filenames(conn) -> set[str]:
    with conn.cursor() as cur:
        cur.execute(f"SELECT filename FROM {LOCK_TABLE}")
        return {row[0] for row in cur.fetchall()}


def _upsert_lock(conn, filename: str, checksum: str):
    with conn.cursor() as cur:
        cur.execute(
            f"""
            INSERT INTO {LOCK_TABLE} (filename, checksum, applied_at)
            VALUES (%s, %s, NOW())
            ON CONFLICT (filename) DO NOTHING
        """,
            (filename, checksum),
        )
    conn.commit()


def apply_migration(conn, path: Path, dry_run: bool = False) -> bool:
    filename = path.name
    current_checksum = compute_checksum(path)

    with conn.cursor() as cur:
        cur.execute(f"SELECT checksum FROM {LOCK_TABLE} WHERE filename = %s", (filename,))
        row = cur.fetchone()
        stored_checksum = row[0] if row else None

    if stored_checksum is not None:
        if stored_checksum != current_checksum:
            raise RuntimeError(
                f"MIGRATION DRIFT DETECTED: {filename} was previously applied "
                f"but contents have changed. checksum was={stored_checksum}, now={current_checksum}. "
                f"DO NOT modify applied migrations. Create a new migration instead."
            )
        logger.debug("Skipping %s — already applied", filename)
        return False

    if dry_run:
        logger.info("[DRY RUN] Would apply: %s", filename)
        return False

    sql = path.read_text()
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()

    _upsert_lock(conn, filename, current_checksum)
    logger.info("Applied: %s", filename)
    return True


def run_pending_migrations(dry_run: bool = False) -> list[str]:
    """Run pending migrations. Returns list of applied filenames."""
    conn = get_db_connection()
    ensure_lock_table(conn)

    applied = []
    files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    locked = get_applied_filenames(conn)

    for path in files:
        if path.name in locked:
            logger.debug("Skipping %s — already locked", path.name)
            continue

        logger.info("[DRY RUN] Would apply: %s" if dry_run else "Applying: %s", path.name)

        filename = path.name
        current_checksum = compute_checksum(path)

        with conn.cursor() as cur:
            cur.execute(f"SELECT checksum FROM {LOCK_TABLE} WHERE filename = %s", (filename,))
            row = cur.fetchone()
            stored_checksum = row[0] if row else None

        if stored_checksum is not None:
            if stored_checksum != current_checksum:
                raise RuntimeError(
                    f"MIGRATION DRIFT DETECTED: {filename} was previously applied but contents have changed."
                )
            logger.debug("Skipping %s — already applied", filename)
            continue

        if dry_run:
            logger.info("[DRY RUN] Would apply: %s", filename)
            continue

        sql = path.read_text()
        try:
            needs_autocommit = "CONCURRENTLY" in sql.upper()
            if needs_autocommit:
                conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute(sql)
            if needs_autocommit:
                conn.autocommit = False
            else:
                conn.commit()
            _upsert_lock(conn, filename, current_checksum)
            logger.info("Applied: %s", filename)
            applied.append(filename)
        except Exception as e:
            if not needs_autocommit:
                conn.rollback()
            raise RuntimeError(f"Migration failed: {filename}: {e}") from e

    conn.close()
    return applied


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run SQL migrations")
    parser.add_argument("--dry-run", action="store_true", help="Log actions without executing")
    args = parser.parse_args()

    dry_run = os.getenv("MIGRATION_DRY_RUN", "false").lower() == "true" or args.dry_run

    applied = run_pending_migrations(dry_run=dry_run)
    if applied:
        print(f"Applied: {applied}")
    else:
        print("No pending migrations")
