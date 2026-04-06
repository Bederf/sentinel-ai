---
title: "PostgreSQL Logical Backup"
type: "guide"
status: "draft"
version: "1.0.0"
created: "2026-03-31"
updated: "2026-03-31"
tags: ["sentinel", "documentation"]
related: []
domain: "bms"
audience: "all"
complexity: "intermediate"
estimated_read_time: 10
---

# PostgreSQL Logical Backup

SENTINEL now uses PostgreSQL logical backup as the only operational backup for the local Supabase database.

This replaces the old JSON export backup path. Legacy JSON backup files may still exist for verification and archival, but they are no longer an operational backup mechanism.

If you want a dedicated local standby backup database as well, use the restore and refresh scripts below. The live source of truth is still the main local Supabase/Postgres instance. The standby database is a restore target, not a second live source of truth.

## Script

- Backup script: [postgres_logical_backup.sh](/opt/bms-intelligence/scripts/backup/postgres_logical_backup.sh)
- Restore script: [restore_postgres_backup.sh](/opt/bms-intelligence/scripts/restore/restore_postgres_backup.sh)
- Backup + standby refresh script: [refresh_backup_target_db.sh](/opt/bms-intelligence/scripts/backup/refresh_backup_target_db.sh)
- Standby cluster init script: [init_backup_postgres_cluster.sh](/opt/bms-intelligence/scripts/backup/init_backup_postgres_cluster.sh)
- Service wrapper: [backup_service.py](/opt/bms-intelligence/backend/app/services/backup_service.py)

## Output Structure

- [backups/postgres/daily](/opt/bms-intelligence/backups/postgres/daily)
- [backups/postgres/manual](/opt/bms-intelligence/backups/postgres/manual)
- [backups/logs](/opt/bms-intelligence/backups/logs)

Each backup run creates a timestamped folder containing:

- `globals.sql`
- `<database>.dump`
- `<database>.schema.sql`
- `backup.env`

## Default Local Connection

The script defaults to the current local Supabase/Postgres endpoint:

- host: `127.0.0.1`
- port: `55322`
- user: `postgres`
- database: `postgres`

These can be overridden with standard PostgreSQL environment variables such as `PGHOST`, `PGPORT`, `PGUSER`, and `PGPASSWORD`.

## Manual Run

From the repo root:

```bash
scripts/backup/postgres_logical_backup.sh manual
```

Or for scheduled daily mode:

```bash
scripts/backup/postgres_logical_backup.sh daily
```

## Scheduled Daily Run

The repo now includes a simple scheduled wrapper and `systemd` timer files:

- [run_postgres_backup_daily.sh](/opt/bms-intelligence/scripts/backup/run_postgres_backup_daily.sh)
- [sentinel-postgres-backup.service](/opt/bms-intelligence/infra/systemd/sentinel-postgres-backup.service)
- [sentinel-postgres-backup.timer](/opt/bms-intelligence/infra/systemd/sentinel-postgres-backup.timer)

Default schedule:

- daily at `02:15` SAST

To install on the NVIDIA node:

```bash
sudo cp /opt/bms-intelligence/infra/systemd/sentinel-postgres-backup.service /etc/systemd/system/
sudo cp /opt/bms-intelligence/infra/systemd/sentinel-postgres-backup.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now sentinel-postgres-backup.timer
sudo systemctl status sentinel-postgres-backup.timer
```

To run the same scheduled path manually:

```bash
/opt/bms-intelligence/scripts/backup/run_postgres_backup_daily.sh
```

To inspect logs:

```bash
journalctl -u sentinel-postgres-backup.service -n 100
tail -n 100 /opt/bms-intelligence/backups/logs/postgres-backup-systemd.log
```

## Dedicated Backup Database

To maintain a separate local backup Postgres database from the logical dumps, set:

- `TARGET_PGHOST`
- `TARGET_PGPORT`
- `TARGET_PGUSER`
- `TARGET_PGPASSWORD`
- `TARGET_DATABASE`

Defaults in the restore script are:

- host: `127.0.0.1`
- port: `55432`
- user: `postgres`
- database: `sentinel_backup`

Manual refresh flow:

```bash
/opt/bms-intelligence/scripts/backup/refresh_backup_target_db.sh
```

Manual restore of the latest backup into the backup target:

```bash
/opt/bms-intelligence/scripts/restore/restore_postgres_backup.sh latest
```

The repo also includes optional `systemd` units for this standby refresh:

- [sentinel-postgres-backup-db.service](/opt/bms-intelligence/infra/systemd/sentinel-postgres-backup-db.service)
- [sentinel-postgres-backup-refresh.service](/opt/bms-intelligence/infra/systemd/sentinel-postgres-backup-refresh.service)
- [sentinel-postgres-backup-refresh.timer](/opt/bms-intelligence/infra/systemd/sentinel-postgres-backup-refresh.timer)

## Standalone Backup Database With systemd

This repo now includes a dedicated systemd service for a standalone backup PostgreSQL instance.

Default standby instance:

- data dir: `/opt/bms-intelligence/backups/postgres/standby-data`
- host: `127.0.0.1`
- port: `55432`
- user: `postgres`
- database refreshed from dumps: `sentinel_backup`

Install and start it:

```bash
sudo cp /opt/bms-intelligence/infra/systemd/sentinel-postgres-backup-db.service /etc/systemd/system/
sudo cp /opt/bms-intelligence/infra/systemd/sentinel-postgres-backup-refresh.service /etc/systemd/system/
sudo cp /opt/bms-intelligence/infra/systemd/sentinel-postgres-backup-refresh.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now sentinel-postgres-backup-db.service
sudo systemctl enable --now sentinel-postgres-backup-refresh.timer
```

The first start initializes the standalone cluster automatically using the local PostgreSQL 15 binaries found at:

`/usr/lib/postgresql/15/bin`

You can then refresh the backup database manually with:

```bash
/opt/bms-intelligence/scripts/backup/refresh_backup_target_db.sh
```

## Configuration

- `SENTINEL_BACKUP_DATABASES`
  Comma-separated database list. Default: `postgres`
- `SENTINEL_BACKUP_SCHEMAS`
  Optional comma-separated schema list. If omitted, all schemas are included.
- `SENTINEL_REQUIRED_EXTENSIONS`
  Recorded in `backup.env` for later restore verification.
- `BACKUP_RETENTION_DAYS`
  Retention window for each mode directory. Default: `14`

## Current App Behavior

The Settings/System Health backup button now triggers the PostgreSQL logical backup path instead of the old JSON exporter.

## Legacy JSON Backup Verification

Before archiving the old JSON backup folder, verify that every legacy JSON file maps to a live table in the local Supabase/Postgres database:

```bash
python3 /opt/bms-intelligence/scripts/verify/verify_legacy_json_backup_coverage.py
```

Legacy JSON backup location:

- [backend/app/data/supabase_backup](/opt/bms-intelligence/backend/app/data/supabase_backup)

The legacy JSON export helper is now disabled by default:

- [backup_supabase_to_json.py](/opt/bms-intelligence/backend/scripts/backup_supabase_to_json.py)

If that script is used for a one-off historical export, it must be explicitly opted into and must not be treated as an operational backup.
