# Disaster Recovery — Database Backup And Replication Summary

> **Status as of 2026-06-16**: verified live, not just configured.

This summary describes the **remote backup VPS**. From that host's perspective, it is a hot-standby replica of the production primary at `10.99.0.2:55322`.

For the main Sentinel operations runbook, see [docs/10-operations/disaster-recovery.md](10-operations/disaster-recovery.md).

## Architecture

The remote VPS is a PostgreSQL 17 hot standby of the primary at `10.99.0.2:55322`. It currently has 0 lag and is monitored every 5 minutes. Backups run on the standby specifically to avoid loading the production primary.

## Backup Artifacts

Backup root:

```text
/var/backups/postgresql/17-main/
```

Approximate total size at verification time: `~7.4 GB`.

| Artifact | Schedule | Retention | Last verified |
|----------|----------|-----------|---------------|
| Logical dumps (`pg_dump`) | Daily + weekly | Last 30 dump-sets | OK, `310 MB` |
| Physical basebackup | Weekly | Last 3 | OK, `597 MB` compressed |
| WAL archive | Continuous, live-streamed | Auto-pruned to oldest retained basebackup | 0 lag |

## RPO And RTO

| Path | RPO | RTO |
|------|-----|-----|
| Logical dump only | Worst case about 24h, depending selected dump | Low minutes by size estimate |
| Physical basebackup + WAL replay | Seconds to low minutes when WAL stream is current | Low minutes by size estimate |

RTO has not been formally drilled. Current values are size-based estimates only.

## Known Residual Risks

1. Root cause of the June 4 WAL-streaming crash is unknown. Active alerting is now in place through `/opt/sentinel-bridge/scripts/check_wal_streaming.sh`, but it is alert-only and does not auto-restart `pg_receivewal`.
2. Logical dumps can still intermittently fail from primary-side lock conflicts. `max_standby_streaming_delay = 10min` mitigates the observed failure, but does not eliminate the primary-side lock source.
3. The `postgres` role on the remote host is not superuser. SQL-level `CHECKPOINT` or `pg_reload_conf()` can be rejected during an incident; use `systemctl reload/start` or the approved administrative path.
4. Backup creation is verified, but backup restoration has not been tested end to end.

## Immediate Follow-Ups

- Add a scheduled restore-verification job.
- Decide whether WAL streaming / `pg_receivewal` should remain alert-only or add self-healing restart logic.
- Record the first successful restore test as DR evidence.
