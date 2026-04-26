# Agent Prompt: WAVE 2 — Auto-Run Database Migrations

**Objective:** Build a self-bootstrapping migration runner that applies pending SQL migrations on startup, with checksum validation, dry-run support, and hard failure on error. The runner must be fully idempotent — safe to run on a fresh Supabase instance and on restarts.

---

## Background

### Current State

Migrations live in `supabase/migrations/` as raw SQL files with two naming conventions:
- **Numbered prefix:** `001_initial_schema.sql` → `101_*.sql` — sequential, applied once
- **Dated prefix:** `20260414_001_rename_buildings_to_sites.sql` — Phase 183+ pattern

Migrations are manually applied by a DBA before deployment. The goal is to eliminate that manual step.

### Migration Directory Structure

```
supabase/migrations/
├── 001_initial_schema.sql
├── 002_equipment_ext.sql
├── ...
├── 101_*.sql
├── 20260414_001_rename_buildings_to_sites.sql
├── 20260426_001_data_freshness.sql
├── 20260427_001_api_uptime.sql
└── (future migrations added here)
```

---

## Core Requirements

### 1. Bootstrap the Lock Table First

On any startup, the runner must create the lock table if it doesn't exist:

```sql
CREATE TABLE IF NOT EXISTS _migration_lock (
    filename TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ DEFAULT NOW(),
    checksum TEXT
);
```

This makes the runner self-bootstrapping on a fresh Supabase instance. No separate setup step required.

### 2. Lexicographic Sort — Explicit `sorted(glob())`

Always use lexicographic sort explicitly. Never rely on filesystem iteration order:

```python
import glob
import os

migrations_dir = Path(__file__).parent.parent / "supabase" / "migrations"
files = sorted(migrations_dir.glob("*.sql"))  # sorted() — explicit, not os.listdir()
```

**Why:** Filesystem iteration order is not guaranteed. `sorted()` with lexicographic ordering ensures `001_` through `101_` apply in correct sequence. Dated migrations (`20260414_`, `20260426_`) will sort after numeric ones — correct behavior.

### 3. Checksum Validation — Warn on Drift

On each startup, compare stored checksum vs actual file MD5:

```python
import hashlib

def compute_checksum(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()

def applied_checksum(filename: str) -> str | None:
    row = db.query("SELECT checksum FROM _migration_lock WHERE filename = %s", (filename,))
    return row.checksum if row else None

def apply_migration(path: Path) -> None:
    stored = applied_checksum(path.name)
    current = compute_checksum(path)

    if stored is not None and stored != current:
        # Previously applied file has been modified — developer error
        raise RuntimeError(
            f"MIGRATION DRIFT DETECTED: {path.name} was previously applied "
            f"but contents have changed. checksum was={stored}, now={current}. "
            f"DO NOT modify applied migrations. Create a new migration instead."
        )

    # Apply the migration
    sql = path.read_text()
    db.execute(sql)

    # Record with checksum
    db.execute(
        "INSERT INTO _migration_lock (filename, checksum) VALUES (%s, %s)",
        (path.name, current)
    )
```

### 4. Dry-Run Mode — Log Without Executing

Support two dry-run activation methods:

**Environment variable:**
```bash
MIGRATION_DRY_RUN=true python -m uvicorn app.main:app
```

**CLI flag:**
```bash
python -m app.migrations.runner --dry-run
```

In dry-run mode, the runner logs what would be applied without executing any SQL:

```
[DRY RUN] Would apply: 20260426_001_data_freshness.sql
[DRY RUN] Would apply: 20260427_001_api_uptime.sql
[DRY RUN] Would skip: 001_initial_schema.sql (already applied)
[DRY RUN] Would skip: 101_*.sql (already applied)
```

Dry-run must still connect to the database to read `_migration_lock` — this validates the DB connection is working without modifying state.

### 7. Baseline Flag — Mark Existing Migrations as Applied

When deploying to an already-provisioned Supabase (production), all migrations 001→101 + dated files have already been applied manually. The runner must not re-apply them — instead it must mark them all as already-applied in one step.

**Activation:** `--baseline` CLI flag or `MIGRATION_BASELINE=true` env var

**Behavior:**
```bash
# First deployment to existing production Supabase:
python -m app.migrations --baseline

# Output:
# [BASELINE] Marking 127 migration files as already applied
# [BASELINE] 001_initial_schema.sql → d41d8cd98f (skipped)
# [BASELINE] 002_equipment_ext.sql → a1b2c3d4e5 (skipped)
# ...
# [BASELINE] 20260427_001_api_uptime.sql → f9e8d7c6b5 (skipped)
# [BASELINE] Done. 127 migrations marked. Subsequent startups will skip all.
```

**Implementation:**
```python
def run_baseline(migrations_dir: Path, dry_run: bool = False) -> int:
    """Mark all existing .sql files as applied without executing them."""
    from app.migrations.runner import compute_checksum, _upsert_lock

    files = sorted(migrations_dir.glob("*.sql"))
    count = 0

    for path in files:
        checksum = compute_checksum(path)
        if dry_run:
            logger.info("[BASELINE] Would mark: %s", path.name)
        else:
            _upsert_lock(path.name, checksum)
            logger.info("[BASELINE] Marked: %s", path.name)
        count += 1

    return count

# CLI addition in __main__:
if args.baseline or os.getenv("MIGRATION_BASELINE", "false").lower() == "true":
    count = run_baseline(MIGRATIONS_DIR, dry_run=args.dry_run)
    print(f"Baselined {count} migrations.")
    return
```

**IMPORTANT:** Run `--baseline` once on first deployment to any existing Supabase instance. After that, normal startup (without `--baseline`) will skip all files already in `_migration_lock`.

---

## Startup Integration — Fail Fast, Don't Degrade

**WARNING: Do not wire the runner into `startup_event()` until baseline has been confirmed on the target Supabase.**

On a provisioned Supabase, a runner with an empty `_migration_lock` will attempt to re-apply `001_initial_schema.sql` through all 127 migrations — causing duplicate table errors, constraint conflicts, and potential data corruption.

**Correct deployment sequence:**
```
PRE-DEPLOYMENT (production):
1. python supabase/migrations/_baseline.py         ← marks all existing files as locked
2. psql "$DATABASE_URL" -c "SELECT COUNT(*) FROM _migration_lock;"  ← must equal migration file count
3. Deploy Wave 2 — runner wired into startup_event
4. Subsequent startups: runner applies only new migrations added after baseline
```

**On a fresh Supabase (dev/test):** Baseline is not needed — runner will auto-create `_migration_lock` and apply all migrations on first boot.

**The migration runner is called in `startup_event()`** before APScheduler starts and before any route is registered. On failure, the app must halt — not start in a degraded state.

**Correct order in `app_lifespan()`:**
```python
async def app_lifespan(app: FastAPI):
    # 1. Security validations
    _validate_security_config()

    # 2. Database migrations — BEFORE anything else touches the DB
    run_migrations_if_needed()  # raises RuntimeError on failure → app halts

    # 3. Redis, event bus, background scheduler
    await _init_redis()
    await _init_event_bus()

    # 4. APScheduler starts here — safe because DB schema is correct
    scheduler_service.start()

    # ... rest of startup
```

**Wrong order (do not do this):**
- Start scheduler first, then run migrations → scheduler jobs may hit uninitialized columns
- Degrade gracefully on migration failure → partial schema + running app = harder to debug

### 6. Idempotency — Safe to Re-Run

If the runner is executed twice in a row (e.g., restart during migration):
- Already-locked files are skipped (check `_migration_lock` first)
- Transaction per file: if file A applies but file B fails, file A stays locked
- On retry: only remaining unapplied files run

```python
def run_pending_migrations():
    for path in sorted(glob("*.sql")):
        if path.name in _get_locked_filenames():
            logger.debug("Skipping %s — already applied", path.name)
            continue

        logger.info("Applying: %s", path.name)
        apply_migration(path)  # commits atomically within try/except
```

---

## Implementation Plan

### Step 0 (One-Time, Pre-Deployment): Run the Baseline Seed

**Before the migration runner goes live on any Supabase instance — especially production — run the baseline seed.**

This marks all 127 existing migration files as already-applied in `_migration_lock`, so the runner never attempts to re-apply them.

**File:** `supabase/migrations/_baseline.py`

```python
"""One-time baseline seed — marks all existing .sql files as applied.

Run ONCE before first production deployment of Wave 2.
Never run again after baseline is set.

Usage:
    python supabase/migrations/_baseline.py

Prerequisites:
    - SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY env vars set
    - Target Supabase instance already has all migrations applied manually
"""

import hashlib
import os
import sys
from pathlib import Path

import psycopg2

MIGRATIONS_DIR = Path(__file__).parent  # supabase/migrations/
LOCK_TABLE = "_migration_lock"


def compute_checksum(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def get_db_connection():
    conn_str = os.environ.get("DATABASE_URL")
    if not conn_str:
        # Fallback to Supabase connection params
        conn_str = f"postgresql://postgres:{os.environ['SUPABASE_SERVICE_ROLE_KEY']}@127.0.0.1:55322/postgres"
    return psycopg2.connect(conn_str)


def create_lock_table_if_not_exists(conn):
    with conn.cursor() as cur:
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS {LOCK_TABLE} (
                filename TEXT PRIMARY KEY,
                applied_at TIMESTAMPTZ DEFAULT NOW(),
                checksum TEXT
            );
        """)
    conn.commit()


def get_already_locked(conn) -> set[str]:
    with conn.cursor() as cur:
        cur.execute(f"SELECT filename FROM {LOCK_TABLE}")
        return {row[0] for row in cur.fetchall()}


def upsert_lock(conn, filename: str, checksum: str):
    with conn.cursor() as cur:
        cur.execute(f"""
            INSERT INTO {LOCK_TABLE} (filename, checksum, applied_at)
            VALUES (%s, %s, NOW())
            ON CONFLICT (filename) DO NOTHING
        """, (filename, checksum))
    conn.commit()


def run_baseline():
    conn = get_db_connection()
    create_lock_table_if_not_exists(conn)

    locked = get_already_locked(conn)
    files = sorted(MIGRATIONS_DIR.glob("*.sql"))

    baselined = 0
    skipped = 0

    for path in files:
        if path.name in locked:
            print(f"  [SKIP] {path.name} — already locked")
            skipped += 1
            continue

        checksum = compute_checksum(path)
        upsert_lock(conn, path.name, checksum)
        print(f"  [BASELINE] {path.name} → {checksum[:8]}...")
        baselined += 1

    conn.close()

    print(f"\nBaseline complete: {baselined} marked, {skipped} already locked")
    print(f"Run 'SELECT COUNT(*) FROM {LOCK_TABLE};' to verify row count matches migration file count")
    return baselined


if __name__ == "__main__":
    print("SENTINEL Migration Baseline Seed")
    print("=" * 40)
    print(f"Migrations dir: {MIGRATIONS_DIR}")
    print(f"Target: {os.environ.get('DATABASE_URL', 'Supabase via env vars')}")
    print()
    run_baseline()
```

**Validation after running:**
```bash
# Count lock table rows
psql "$DATABASE_URL" -c "SELECT COUNT(*) FROM _migration_lock;"

# Compare to migration file count
ls supabase/migrations/*.sql | wc -l

# These numbers must match exactly before deploying Wave 2
```

**CRITICAL SEQUENCING:**
```
1. python supabase/migrations/_baseline.py     ← Run once, manually, on production Supabase
2. Verify row count == file count
3. Deploy Wave 2 (runner wired into startup_event)
```

**Do NOT wire the migration runner into `startup_event()` until step 2 is confirmed.** Skipping the baseline on a provisioned Supabase will cause the runner to attempt re-applying `001_initial_schema.sql` on startup — duplicate table errors and likely a 2am recovery.

---

## Step 1: Create the Migration Runner Module

**File:** `backend/app/migrations/runner.py`

```python
"""Self-bootstrapping SQL migration runner with checksum validation."""

from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger("sentinel.migrations")


def compute_checksum(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def get_applied_filenames(client: httpx.AsyncClient) -> set[str]:
    """Return set of already-applied migration filenames from _migration_lock."""
    try:
        resp = client.post(
            f"{settings.supabase_url}/rest/v1/rpc/exec_sql",
            json={"sql": "SELECT filename FROM _migration_lock"},
            headers={
                "apikey": settings.supabase_service_role_key,
                "Authorization": f"Bearer {settings.supabase_service_role_key}",
            },
        )
        return {row["filename"] for row in resp.json()}
    except Exception:
        return set()


def ensure_lock_table(client: httpx.AsyncClient) -> None:
    """Create _migration_lock if it doesn't exist (self-bootstrapping)."""
    client.post(
        f"{settings.supabase_url}/rest/v1/rpc/exec_sql",
        json={
            "sql": """
            CREATE TABLE IF NOT EXISTS _migration_lock (
                filename TEXT PRIMARY KEY,
                applied_at TIMESTAMPTZ DEFAULT NOW(),
                checksum TEXT
            );
            """
        },
        headers={...},
    )


def run_migrations_if_needed(dry_run: bool = False) -> list[str]:
    """Run pending migrations. Returns list of applied filenames."""
    # ... full implementation per sections above
    pass
```

### Step 2: Integrate into `startup_event()`

**File:** `backend/app/startup/events.py`

```python
from app.migrations.runner import run_migrations_if_needed

async def startup_event(app: FastAPI):
    # ... existing security validations ...

    # === Run database migrations (fail-fast) ===
    try:
        dry_run = os.getenv("MIGRATION_DRY_RUN", "false").lower() == "true"
        applied = run_migrations_if_needed(dry_run=dry_run)
        if dry_run:
            logger.warning("MIGRATION DRY RUN — no files were applied")
        else:
            logger.info("Migrations applied: %s", applied)
    except Exception as e:
        logger.critical("Migration failed: %s. Halting startup.", e)
        raise RuntimeError(f"Migration failure: {e}") from e

    # ... continue with Redis, event bus, scheduler ...
```

### Step 3: CLI Entry Point

**File:** `backend/app/migrations/__main__.py`

```python
"""Run migration runner directly: python -m app.migrations --dry-run"""

import argparse
from app.migrations.runner import run_migrations_if_needed

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run SQL migrations")
    parser.add_argument("--dry-run", action="store_true", help="Log actions without executing")
    args = parser.parse_args()

    dry_run = os.getenv("MIGRATION_DRY_RUN", "false").lower() == "true" or args.dry_run

    applied = run_migrations_if_needed(dry_run=dry_run)
    if applied:
        print(f"Applied: {applied}")
    else:
        print("No pending migrations")
```

### Step 4: Test the Runner

**Test 1: Fresh Supabase instance** — lock table created on first run, all migrations applied
**Test 2: Re-run** — all files skipped (already locked), no changes
**Test 3: Dry-run** — logs what would apply, DB connection validated, no state change
**Test 4: Checksum drift** — modify a previously-applied file, runner raises `RuntimeError("MIGRATION DRIFT DETECTED")`
**Test 5: Failure mid-run** — file A applies, file B fails → file A stays locked, restart applies only B

---

## Migration Discovery

Find all SQL files in `supabase/migrations/`:

```python
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).parent.parent.parent / "supabase" / "migrations"

def get_migration_files() -> list[Path]:
    """Return sorted list of all .sql files (lexicographic, not filesystem order)."""
    return sorted(MIGRATIONS_DIR.glob("*.sql"))
```

**Sort order validation:**
- `001_*.sql` through `101_*.sql` — correct lex order
- `20260414_*.sql` sorts after `101_*.sql` in lex order — correct
- `20260426_001_*.sql` sorts after `20260414_*.sql` — correct

---

## Error Handling

| Scenario | Behavior |
|----------|----------|
| DB not reachable | `RuntimeError("Cannot connect to Supabase")` — startup halts |
| SQL syntax error in file | File fails, exception raised, startup halts |
| File already locked | Skip silently (idempotent) |
| Checksum drift | `RuntimeError("MIGRATION DRIFT DETECTED")` — startup halts |
| Duplicate primary key in lock table | Shouldn't happen — check before insert |

---

## Acceptance Criteria

- [ ] `_baseline.py` exists at `supabase/migrations/_baseline.py`
- [ ] `_baseline.py` runs without error on target Supabase (verified: row count == file count)
- [ ] `_migration_lock` table created automatically on first run (no manual setup)
- [ ] `--baseline` flag marks all existing migration files as applied without executing
- [ ] All pending migrations applied on startup in lexicographic order
- [ ] Checksum stored on apply; mismatch on subsequent run raises error
- [ ] Dry-run mode logs actions without executing
- [ ] Startup halts if any migration fails (no degraded state)
- [ ] Re-run is idempotent (already-locked files skipped)
- [ ] All 6 test scenarios pass (including baseline)
- [ ] Existing manually-applied migrations (001–101 + dated) are recognized as already applied

---

## Estimated Effort

**Total: ~6 hours**
- Runner module (`runner.py`): 1.5 hours
- Startup integration: 0.5 hours
- CLI entry point: 0.5 hours
- Tests (5 scenarios): 2 hours
- Error handling polish: 1 hour
- Documentation: 0.5 hours

---

**Test 6: Baseline on existing Supabase** — `--baseline` marks all 127 existing files as applied without executing any; subsequent normal startup skips all files

---

## Notes

- **Transaction per file:** Wrap each migration in a transaction so partial failures are isolated
- **Logging:** Include `logger.info` for each file applied, `logger.debug` for skipped files
- **Supabase RPC limitation:** The `exec_sql` RPC approach works but has limits. If you hit `PGRST208` errors (DDL not allowed via REST), switch to direct `psycopg2` connection for DDL statements.
- **Existing applied migrations:** Before marking a file as "already applied," the runner should verify the `_migration_lock` row exists. If the lock table exists but a migration file isn't locked, it means it was applied before the runner existed — apply it to be safe, not skip it.
