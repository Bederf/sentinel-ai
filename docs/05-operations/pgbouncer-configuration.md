# PgBouncer Connection Pooling

> **Status**: Deployed 2026-06-14
> **Service**: `pgbouncer.service`
> **Port**: 6432
> **Mode**: transaction pooling
> **Pool size**: 20

## Why PgBouncer

Sentinel's background workers (ML inference, data sync, telemetry aggregation, correlation, BESS dispatch, compiler, scheduler) create direct `psycopg2.connect()` calls to PostgreSQL. At scale, this connection churn exhausts PostgreSQL's `max_connections` (100).

PgBouncer sits between workers and PostgreSQL, reusing a small pool of persistent connections.

## Architecture

```
Background workers                  API layer
      │                                │
      │ psycopg2.connect()             │ Supabase REST (httpx)
      │                                │
      ▼                                ▼
  PgBouncer (:6432)              Kong (:55321)
      │                                │
      │ pooled connections             │
      ▼                                ▼
  ┌──────────────────────────────────────┐
  │       PostgreSQL (:55322)            │
  │       max_connections = 100          │
  └──────────────────────────────────────┘
```

The API layer (FastAPI → Supabase REST → PostgREST) routes through Supabase's own managed connections. PgBouncer is only used by background worker services that call `psycopg2.connect()` directly.

## Connection Strings

| Use | URL |
|-----|-----|
| Workers (pooled) | `postgresql://postgres:postgres@127.0.0.1:6432/postgres` |
| Workers (direct, fallback) | `postgresql://postgres:postgres@127.0.0.1:55322/postgres` |
| Supabase internal | `postgresql://postgres:postgres@127.0.0.1:55322/postgres` |

### Environment Variables

- `DATABASE_URL` — now points to PgBouncer (`:6432`)
- `DATABASE_URL_DIRECT` — preserves the original direct PostgreSQL URL (`:55322`) for emergency use
- `PGBOUNCER_URL` — explicitly set for workers that check this var first (`ml_registry_sync`, `signal_replay_tool`)

## Configuration

**File**: `/etc/pgbouncer/pgbouncer.ini`

Key settings:

```ini
[databases]
postgres = host=127.0.0.1 port=55322 dbname=postgres user=postgres password=postgres

[pgbouncer]
listen_addr = 127.0.0.1
listen_port = 6432
auth_type = trust
pool_mode = transaction
default_pool_size = 20
max_client_conn = 100
reserve_pool_size = 5
reserve_pool_timeout = 3
server_reset_query = DISCARD ALL
server_idle_timeout = 600
server_lifetime = 3600
```

## Operational Commands

```bash
# Status
systemctl status pgbouncer

# Restart (after config change)
sudo systemctl restart pgbouncer

# Pool statistics
psql -h 127.0.0.1 -p 6432 -U postgres -d pgbouncer -c "SHOW POOLS;"
psql -h 127.0.0.1 -p 6432 -U postgres -d pgbouncer -c "SHOW STATS;"
psql -h 127.0.0.1 -p 6432 -U postgres -d pgbouncer -c "SHOW SERVERS;"
psql -h 127.0.0.1 -p 6432 -U postgres -d pgbouncer -c "SHOW CLIENTS;"
```

## Known Limitations

### Transaction Pooling (`pool_mode = transaction`)

This mode does **not** support session-level PostgreSQL features:

| Feature | Works? | Notes |
|---------|--------|-------|
| `SELECT`, `INSERT`, `UPDATE`, `DELETE` | ✅ | |
| `CREATE TEMP TABLE` | ❌ | Temp tables dropped after transaction |
| `LISTEN` / `NOTIFY` | ❌ | Requires persistent session |
| `SET session` variables | ❌ | Reset by `DISCARD ALL` |
| Named cursors | ❌ | Require session persistence |
| Prepared statements | ❌ | Reset by `DISCARD ALL` |
| `conn.autocommit = True` | ✅ | Each statement is its own transaction |

All current worker services use simple `SELECT`/`INSERT`/`UPDATE` patterns with `autocommit = True` and are compatible.

### Supavisor (Supabase Built-in Pooler)

The Supabase CLI includes a Supavisor pooler, configured via `supabase/config.toml`:

```toml
[db.pooler]
enabled = false
port = 55329
pool_mode = "transaction"
default_pool_size = 20
```

This is **disabled** in favor of standalone PgBouncer. Supavisor is designed for Supabase's multi-tenant cloud architecture and requires complex tenant/SNI configuration for local use.

## Migration History

| Date | Phase | Changes |
|------|-------|---------|
| 2026-06-14 | Phase 1 | Installed PgBouncer, configured transaction pooling at :6432 |
| 2026-06-14 | Phase 2 | Migrated `ml_registry_sync.py` — validated autocommit upsert pattern |
| 2026-06-14 | Phase 2 | Migrated `signal_replay_tool.py` — validated correlation pipeline |
| 2026-06-14 | Phase 3 | Updated `DATABASE_URL` in `.env` to point to PgBouncer — all workers migrated |

## Files Changed

- `backend/.env` — `DATABASE_URL` → `:6432`, added `DATABASE_URL_DIRECT`
- `backend/app/services/ml_registry_sync.py` — `PGBOUNCER_URL` fallback
- `backend/app/services/signal_replay_tool.py` — `PGBOUNCER_URL` fallback
- `/etc/pgbouncer/pgbouncer.ini` — new config
- `/etc/pgbouncer/userlist.txt` — trust auth (localhost only)
- `/etc/sentinel/backend.env` — added `PGBOUNCER_URL`
