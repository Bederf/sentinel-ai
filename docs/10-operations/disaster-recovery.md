# Disaster Recovery

> **Status**: Updated 2026-06-16 from live primary and remote replica checks
> **Owner**: Infrastructure team
> **Review cadence**: Quarterly

## Executive Summary

| Question | Answer |
|----------|--------|
| What is protected? | SENTINEL PostgreSQL/Supabase data, backup artifacts, replication state, service configuration |
| Where is the main database? | This VPS: `supabase_db_bms-intelligence`, exposed locally on `127.0.0.1:55322` |
| Is there a local restore target? | Yes: `sentinel-postgres-backup-db`, exposed locally on `127.0.0.1:55432`, database `sentinel_backup` |
| Where is the replica? | Remote VPS: hot standby streaming from primary `10.99.0.2:55322` |
| Recovery paths | Restore local backup target, promote remote standby, restore logical dump, restore physical basebackup + WAL, rebuild primary from snapshot |
| Backup host | Remote standby VPS, so `pg_dump` and physical backup work do not load the production primary |
| PITR status | Available only through the remote basebackup + WAL archive path; logical dumps alone are daily/weekly restore points |
| Restore-test status | Backup creation is verified; end-to-end restore testing is not yet formally scheduled |

## Platform Boundary

The live production database checked on 2026-06-16 is a **self-hosted Supabase/PostgreSQL stack** running in Docker on the Sentinel VPS. It is not Supabase Cloud managed HA.

That distinction matters:

- Sentinel can control the local PostgreSQL container and the remote PostgreSQL standby.
- Standby promotion is technically possible, but only after fencing/isolation decisions are made.
- If Sentinel later moves to Supabase Cloud managed Postgres, this runbook must change. In that model, DR would primarily use Supabase-managed restore/failover plus application repointing, not local `pg_ctlcluster` promotion.

## Current Topology

This runbook is written from the primary SENTINEL VPS perspective.

```text
This VPS
  Production PostgreSQL/Supabase primary
  Container: supabase_db_bms-intelligence
  Direct endpoint: 127.0.0.1:55322
  Backend pooled endpoint: 127.0.0.1:6432
        |
        | daily logical dump + restore verification
        v
  Local restore target
  Container: sentinel-postgres-backup-db
  Endpoint: 127.0.0.1:55432
  Database: sentinel_backup
        |
        | async WAL streaming
        | primary network address: 10.99.0.2:55322
        v
Remote VPS
  PostgreSQL 17 hot standby
  Replication slot: standby1_slot
  WAL receiver: live, expected lag <100 MB
  Backup root: /var/backups/postgresql/17-main/
```

The remote VPS may describe itself as "this host is a hot-standby replica of `10.99.0.2:55322`". That is correct from the remote host perspective. In this repository's operational docs, "this VPS" means the production Sentinel host unless explicitly stated otherwise.

## Recovery Scenario Priority

Use this priority order during an incident:

1. **Application-layer failure only**: backend, PostgREST, PgBouncer, Supabase API, or Sentry integrations fail while PostgreSQL remains healthy. Recover services first; do not touch replication or backups.
2. **Primary database outage**: the production PostgreSQL container or host cannot serve writes. Fence or isolate the primary, then consider remote standby promotion.
3. **Logical corruption or bad data**: the database is online but data is wrong. Do not promote the standby blindly because the bad data may already have replicated. Restore into a clean target and reconcile.
4. **Remote backup/replica failure**: production is healthy but DR coverage is degraded. Rebuild the replica/backup path; do not disrupt production traffic.
5. **Full primary VPS loss**: promote or restore from the remote backup host, then rebuild the lost primary environment.

Scripts should implement this written runbook. They must not replace incident judgment.

## DR Status Page Requirements

The Settings/Operations UI should be read-only for DR status. It should not expose a one-click failover or restore button.

Minimum status fields:

| Field | Why it matters |
|-------|----------------|
| Primary DB role | Confirms whether this host is primary or standby via `pg_is_in_recovery()` |
| Remote replica state | Shows streaming status, replay timestamp, slot health, and stale WAL alerts |
| Current RPO exposure | Translates lag into operator language, for example "current data loss exposure: ~4 minutes" |
| Estimated RTO | Uses latest dump/basebackup size and last measured restore speed; must be labelled estimate until drilled |
| Latest logical dump | Shows timestamp, size, and exit status |
| Latest physical basebackup | Shows timestamp, size, and retention coverage |
| WAL archive health | Shows whether WAL is still being received and whether archive coverage reaches the oldest retained basebackup |
| Last restore test | Shows timestamp, target, duration, and result |
| Restore-test freshness | Must go red if the last successful restore test is older than 7 days |
| Open DR gaps | Shows restore-test missing, stale backup, failed replication checks, or alert-only controls |

Backup existence is not enough. A green status requires a recent successful restore test.

The measured restore duration is **database-layer time only**. It does not include the full incident chain:

1. Declare incident and freeze writes.
2. Validate restore target or choose the remote recovery path.
3. Stop or redirect affected services.
4. Restore or promote the database target.
5. Repoint connection strings and secrets.
6. Restart dependent services.
7. Run post-recovery validation and smoke tests.

Operators must not treat the measured local restore duration as full customer-facing RTO.

Current local implementation:

- API: `GET /api/system/dr-status`
- Evidence file: `backups/logs/postgres_backup_refresh_status.json`
- Settings surface: System Health & Backup panel shows DR readiness, RPO exposure, measured database-layer restore duration, and local restore-target size/table count.
- Freshness gate: local restore evidence older than 7 days is critical.
- Integrity gate: critical restored tables must have row-count evidence and non-zero rows.

## Backup And Replication Controls

| Control | Location | Schedule | Retention | Notes |
|---------|----------|----------|-----------|-------|
| Streaming standby | Remote VPS | Continuous | N/A | Async streaming from `10.99.0.2:55322` using `standby1_slot` |
| Local logical backup + restore target | Primary VPS | Daily at 02:45 SAST | Local retention policy | `sentinel-postgres-backup-refresh.timer` runs a dump and restores it into `sentinel-postgres-backup-db` |
| Replication health check | Remote VPS root cron | Every 5 minutes | Latest alert state | Checks WAL receiver, lag `<100 MB`, and primary slot health; writes alert to `/tmp/pg_replication_alert` |
| Logical dumps | Remote VPS | Daily + weekly | Last 30 dump-sets | Managed by Debian `pg_backupcluster`; custom `pg_dump` format for every DB plus config snapshot |
| Physical basebackup | Remote VPS | Weekly | Last 3 | Compressed physical restore base for WAL replay/PITR path |
| WAL archive | Remote VPS | Continuous, live-streamed | Pruned to oldest retained basebackup | Enables near-continuous recovery when paired with retained basebackup |
| VPS snapshots | Provider | Provider-defined | Provider-defined | Last-resort infrastructure restore path |

Backup artifact root on the remote VPS:

```text
/var/backups/postgresql/17-main/
```

`pg_backupcluster` creates UTC timestamped dump directories and runs `expiredumps 30`. That keeps the 30 most recent dump-sets, not a fixed number of days.

## Recovery Objectives

| Scenario | Expected RPO | Expected RTO | Confidence |
|----------|--------------|--------------|------------|
| Primary outage, standby healthy | Replication lag, usually seconds to low minutes | Minutes after promotion and app repointing | Medium; promotion procedure still needs a formal drill |
| Primary DB corruption requiring same-host restore | Latest local successful dump | Minutes to restore target; production reconcile depends scope | Medium; local restore target verified 2026-06-16 |
| Logical corruption caught after replication | Last known-good logical dump or PITR target if WAL path is valid | Low minutes to hours depending restore scope | Medium |
| Remote replica failure, primary healthy | No primary data loss | Hours to rebuild standby and re-enable backups | Medium |
| Full primary VPS loss, remote backup host healthy | Replication lag or latest backup point | Hours, depending promote/repoint/rebuild path | Medium |
| Primary and remote backup host both lost | Provider snapshot/off-host copy only | Unknown | Low unless off-host copy is verified |

These are operational estimates, not contractual SLA values.

## Scenario A: Primary Database Failure

Use this when the production PostgreSQL/Supabase container on this VPS is unavailable and the remote standby is healthy.

### Split-Brain Guardrail

Do not promote the remote standby based only on "the primary is unreachable from the remote VPS" or "the primary is unreachable from this shell".

Network partitions can make a healthy primary appear unreachable from one side while it continues accepting writes from another path. Promotion requires an explicit fencing decision:

- Confirm the old primary is stopped, powered off, or network-isolated from all application writers.
- Confirm application writers have been paused or redirected.
- Record who approved the fencing decision and the exact time.
- Only then promote the remote standby.

Until fencing is confirmed, keep the remote host read-only and treat the event as degraded availability, not failover.

### Detection

On the primary VPS:

```bash
docker ps --format "{{.Names}}\t{{.Status}}\t{{.Ports}}" | grep supabase_db_bms-intelligence
docker exec supabase_db_bms-intelligence psql -U postgres -d postgres -tAc "select pg_is_in_recovery();"
pg_isready -h 127.0.0.1 -p 55322
```

On the remote VPS:

```bash
sudo -u postgres psql -d postgres -tAc "select pg_is_in_recovery(), now() - pg_last_xact_replay_timestamp();"
cat /tmp/pg_replication_alert 2>/dev/null || true
```

### Recovery

1. Confirm the primary is actually failed and cannot still accept writes.
2. Isolate or stop the failed primary to avoid split brain.
3. Promote the remote standby:

   ```bash
   sudo pg_ctlcluster 17 main promote
   ```

4. Repoint Sentinel database connection settings to the promoted database host.
5. Restart dependent services:

   ```bash
   sudo systemctl restart sentinel-backend
   sudo systemctl restart postgrest 2>/dev/null || true
   ```

6. Validate:

   ```bash
   curl -s http://127.0.0.1:9095/api/health
   ```

7. Rebuild a new standby from the promoted primary before considering DR complete.

## Scenario B: Logical Corruption Or Bad Data

Use this when data was deleted, overwritten, or corrupted and that bad state may already have replicated.

Do not immediately promote the standby if corruption has already reached it. Pick the restore point first.

### Recovery From Local Restore Target

Use the local target when the latest local dump is good enough and the production host is still available.

Local target:

```text
127.0.0.1:55432
database: sentinel_backup
container: sentinel-postgres-backup-db
```

Validation examples:

```bash
docker exec sentinel-postgres-backup-db psql -U postgres -d sentinel_backup -tAc \
  "select count(*) from information_schema.tables where table_schema='public';"

docker exec sentinel-postgres-backup-db psql -U postgres -d sentinel_backup -tAc \
  "select 'sites=' || count(*) from public.sites
   union all select 'recommendations=' || count(*) from public.recommendations
   union all select 'audit_log=' || count(*) from public.audit_log
   union all select 'work_orders=' || count(*) from public.work_orders;"
```

Restore refresh command:

```bash
sudo systemctl start sentinel-postgres-backup-refresh.service
```

The service uses the backup container's PostgreSQL 17 restore tools and the container's configured admin role. This avoids host `pg_restore` version mismatch and protected Supabase-schema permission errors.

The refresh service writes restore evidence to:

```text
backups/logs/postgres_backup_refresh_status.json
```

That file feeds `/api/system/dr-status` and the Settings DR readiness card.

The evidence includes critical table row counts for:

- `sites`
- `recommendations`
- `work_orders`
- `technicians`
- `equipment`
- `alerts`
- `audit_log`
- `adapter_health`
- `site_module_configs`
- `system_settings`

If any required table is missing from the evidence or has zero rows, `/api/system/dr-status` reports the local restore target as critical.

### Recovery From Logical Dump

1. Identify the corruption window.
2. Choose a known-good dump directory under:

   ```text
   /var/backups/postgresql/17-main/
   ```

3. Restore into a clean target database, not directly over production.
4. Extract the affected tables or rows.
5. Reconcile back into production after application-level validation.

Logical dump RPO is the selected dump timestamp.

### Recovery From Basebackup + WAL

Use this when a point between logical dumps is required and the retained basebackup plus WAL archive covers the target time.

1. Select the newest basebackup before the target recovery time.
2. Restore it to a clean PostgreSQL 17 cluster.
3. Configure recovery to replay WAL to the target timestamp.
4. Validate row counts and application health before repointing services.

This is the PITR path. It must be drilled before being treated as a guaranteed operational control.

## Scenario C: Remote Replica Or Backup Host Failure

Primary remains online, but the remote standby, WAL stream, or backup jobs fail.

### Detection

On the remote VPS:

```bash
systemctl status postgresql@17-main
systemctl list-timers 'pg*d*ump*'
cat /tmp/pg_replication_alert 2>/dev/null || true
```

On the primary VPS:

```bash
docker exec supabase_db_bms-intelligence psql -U postgres -d postgres -tAc \
  "select application_name, client_addr, state, sync_state from pg_stat_replication;"
```

### Recovery

1. Restart PostgreSQL or the failed WAL/backup service on the remote VPS.
2. If the standby is no longer trustworthy, rebuild it from the primary using a fresh basebackup.
3. Recreate or reuse replication slot `standby1_slot`.
4. Re-enable the cron health check and backup timers.
5. Confirm a new logical dump and WAL stream are both current.

### WAL Watchdog Mode

The remote VPS currently has `/opt/sentinel-bridge/scripts/check_wal_streaming.sh` running every 5 minutes. It checks:

1. `pg_receivewal@17-main.service` is active.
2. Replication slot `pg_receivewal_service` is active.
3. The newest WAL archive file is less than 15 minutes old.

It writes `/tmp/pg_receivewal_alert` on failure and clears it on recovery.

Action threshold: if `/tmp/pg_receivewal_alert` exists or WAL archive freshness exceeds 15 minutes, the remote WAL/PITR path is degraded. If the condition persists for more than one cron interval after service restart, treat the near-continuous RPO claim as unavailable and fall back to the newest verified dump/basebackup path until WAL streaming is confirmed healthy.

This is intentionally alert-only. If self-healing is enabled later, it must be deployed on the remote VPS and should:

- restart `pg_receivewal@17-main.service` only after a failed health check,
- write an incident line before and after restart,
- avoid deleting WAL files,
- alert if restart does not clear `/tmp/pg_receivewal_alert`,
- preserve the existing alert-file contract so this primary VPS can ingest the same status later.

## Scenario D: Full Primary VPS Loss

If this VPS is gone but the remote backup host is healthy:

1. Promote the remote standby if it is consistent and current.
2. Repoint application DNS, VPN, and database connection settings to the promoted host.
3. Restore application services from code and configuration backups.
4. Run the recovery validation checklist.
5. Build a replacement standby/backup host.

If both the primary VPS and the remote backup host are lost, recovery depends on provider snapshots or any separately verified off-host copy. This is the largest remaining DR gap.

## Scenario E: Backup Creation Failure

Logical dumps can fail on a hot standby while WAL is being replayed.

Known conflict types:

- Vacuum/snapshot conflicts: mitigated with `hot_standby_feedback = on`.
- Relation-lock conflicts: mitigated by increasing `max_standby_streaming_delay` from `30s` to `10min`.

Both settings are SIGHUP/reload settings. They do not require a PostgreSQL restart.

The relation-lock root cause on the primary is still unidentified. The longer standby delay window outlasts the observed conflict, but it does not remove the primary-side source.

## Validation Checklist

After any recovery event:

- [ ] PostgreSQL accepts connections.
- [ ] Correct role confirmed with `pg_is_in_recovery()`.
- [ ] Backend health endpoint returns 200.
- [ ] PostgREST/Supabase API path responds.
- [ ] PgBouncer is healthy if used by the app.
- [ ] Local restore target `sentinel-postgres-backup-db` has a recent successful restore.
- [ ] Critical row counts in `postgres_backup_refresh_status.json` are present and non-zero for required tables.
- [ ] Sentry bots reconnect and can read/write expected DB-backed state.
- [ ] BACnet/Niagara bridge reconnects without stale database credentials.
- [ ] Grafana datasource reconnects to the active database path.
- [ ] Latest telemetry is visible.
- [ ] Latest AI recommendation/advisory queries work.
- [ ] Telegram notification path works.
- [ ] Supabase JWT/service-role keys and application DB connection strings are confirmed current.
- [ ] Secrets changed during recovery are rotated or recorded in the secret rotation log.
- [ ] Remote replication is re-established.
- [ ] Backup timers are enabled and have recent successful runs.
- [ ] `/tmp/pg_replication_alert` is clear on the remote VPS.
- [ ] `/tmp/pg_receivewal_alert` is clear on the remote VPS.
- [ ] Restore evidence is recorded in the DR exercise log.

## Known Gaps

1. **Restore has not been formally drilled**: backup creation is verified, but end-to-end restore evidence is missing.
2. **WAL receiver alerting is alert-only by design**: `/opt/sentinel-bridge/scripts/check_wal_streaming.sh` now checks `pg_receivewal@17-main.service`, slot activity, and archive freshness every 5 minutes, but self-healing restart has not been deployed on the remote VPS.
3. **Logical dump conflicts can still happen**: the 10-minute standby delay mitigates observed relation-lock conflicts, but the primary-side lock source remains unidentified.
4. **Remote postgres role is not superuser**: incident commands that require `CHECKPOINT` or `pg_reload_conf()` must use `systemctl reload/start` or an administrative path.
5. **Dual-site loss is not fully covered**: if both the primary VPS and remote backup host are lost, recovery depends on provider snapshots or separately verified off-host copies.
6. **No DR status page yet**: operators do not yet have a single read-only view of RPO exposure, RTO estimate, backup integrity, WAL health, and restore-test freshness.
7. **No fencing automation**: standby promotion still depends on a manual isolation decision to avoid split brain.
8. **Old local backup directories have mixed ownership**: retention cleanup can warn on old `nobody:nogroup` backup directories. Current refresh is non-fatal, but old directories should be cleaned up separately.
9. **No full-chain RTO drill yet**: current local timing measures only dump plus restore. It excludes incident declaration, write freeze, service repointing, secrets, restarts, and smoke tests.
10. **Secrets are a single point of failure**: `.env`, bridge tokens, Supabase service keys, Cloudflare tunnel credentials, MQTT passwords, and WireGuard keys exist only on the live server. No encrypted offsite bundle exists. Loss of the primary VPS means loss of all runtime secrets. A secrets-bundle workflow script exists at `infrastructure/secrets-bundle.sh` (age-encrypted tar, push to any offsite destination) but has not yet been run.
11. **Infrastructure configuration is not fully captured as code**: systemd unit files, Cloudflare tunnel ingress rules, Caddy reverse-proxy config, MQTT ACLs, and Mosquitto listener config are now versioned in `infrastructure/systemd/`, `infrastructure/cloudflared/`, `infrastructure/caddy/`, and `infrastructure/mosquitto/`, but these snapshots must be kept in sync with live changes. A bootstrap script at `infrastructure/bootstrap.sh` can rebuild the system layer from these configs.
12. **No infra-config drift detection**: there is no automated check that the live systemd units, Caddyfile, or Cloudflare tunnel config match what is versioned in `infrastructure/`. After any manual change to these files on the server, the `infrastructure/` copy must be updated manually or drift will compound.

## Scheduler Lock Behavior

The backend runs with two uvicorn workers for API responsiveness. APScheduler jobs are guarded by an exclusive process lock at:

```text
/tmp/sentinel-background-scheduler.lock
```

Only the lock holder starts background jobs. Other workers skip scheduler startup. This is an OS advisory file lock; if the lock-holding worker process exits or crashes, the kernel releases the lock with the file descriptor. A replacement worker can then acquire it on startup. There is no TTL because stale locks are not expected after process death; the failure mode to watch is a live but wedged scheduler worker, which requires process restart.

## Related Documents

- [Database backup and replication summary](../disaster-recovery-db-backup-summary.md)
- [PostgreSQL logical backup note](operations-notes/postgres-logical-backup.md)
- [BCP/DR procedures](../09-security/bcp-dr-procedures.md)
- [Infra bootstrap script](../infrastructure/bootstrap.sh) — bare VPS to running system
- [Secrets bundle workflow](../infrastructure/secrets-bundle.sh) — encrypted offsite secrets archive
- [Systemd unit files](../infrastructure/systemd/) — service definitions for restore
- [Cloudflare tunnel config](../infrastructure/cloudflared/) — ingress routing rules
- [Caddy reverse-proxy config](../infrastructure/caddy/Caddyfile) — TLS and routing
- [Mosquitto MQTT config](../infrastructure/mosquitto/) — broker ACLs and listener
