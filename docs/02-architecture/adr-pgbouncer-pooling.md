---
title: "ADR-006 — PgBouncer Transaction Pooling for Worker Services"
status: "accepted"
date: 2026-06-14
authors: ["Sentinel Platform Team"]
---

# Decision Record: PgBouncer Transaction Pooling

## Context

Sentinel background workers (ML inference, data sync, telemetry aggregation, correlation, BESS dispatch, compiler, scheduler) create direct `psycopg2.connect()` calls to PostgreSQL. At production scale, each worker process opens a fresh connection, does work, and closes it. This pattern creates connection churn that exhausts PostgreSQL's `max_connections` (currently 100).

The web API layer routes through Supabase REST (PostgREST), which manages its own connections. The risk is isolated to the background processing tier — 18 raw `psycopg2.connect()` calls across 9+ service files.

## Options Considered

### Option 1: Supavisor (Supabase Built-in Pooler)

Supavisor is a multi-tenant Elixir-based pooler distributed with the Supabase CLI.

- **Pros**: Native Supabase integration, supports transaction + session pooling, auto-configured by Supabase CLI.
- **Cons**: Consumed 25 backend connections for its own pool before serving any clients. Requires tenant/SNI configuration for local use — `require_user` + encrypted password management in `_supavisor.users` table. Designed for Supabase's cloud multi-tenant architecture, not single-tenant local deployments. Complex failure mode: tenant not found errors when SNI hostname isn't provided.

### Option 2: PgBouncer (Standalone)

PgBouncer is a lightweight, single-purpose connection pooler for PostgreSQL.

- **Pros**: 1.7 MB resident memory, simple text-based config (`pgbouncer.ini`), well-understood operational model, supports `transaction` pooling mode, `DISCARD ALL` on connection reuse. Debian package (`pgbouncer 1.18.0`) available via apt. systemd-integrated out of the box.
- **Cons**: Separate process to manage (though trivial — one systemd unit). Does not support SCRAM-SHA-256 auth in v1.18 (mitigated by `auth_type = trust` on localhost).

### Option 3: Application-level pooling (psycopg2 pool / SQLAlchemy)

Add pooling inside each worker process using `psycopg2.pool` or SQLAlchemy `create_engine()`.

- **Pros**: No external dependency. Pool is per-process.
- **Cons**: Each uvicorn worker (4) + each scheduler process maintains its own pool — multiplies rather than consolidates connections. No cross-process sharing. Requires code changes in all 9+ service files.

## Decision

**Accept PgBouncer with transaction pooling.**

PgBouncer runs as a systemd service on port 6432, proxying to PostgreSQL on port 55322. All background workers route through it.

Rationale:
- Simplest operational model (one config file, one systemd unit, 1.7 MB memory)
- Transaction pooling is correct for workers that use `autocommit = True` and no session-level features
- `DISCARD ALL` on connection reuse prevents session state leakage
- 20-pool default handles current worker fleet with headroom
- Existing `pool_mode = transaction` validates via `SHOW POOLS` and `SHOW STATS`

## Consequences

**Positive:**
- Worker connections share a pool of 20 persistent server connections instead of opening per-call connections
- Existing worker code requires zero changes — only the `DATABASE_URL` changes from `:55322` to `:6432`
- PgBouncer exporter provides Prometheus metrics for pool utilization, wait times, client/server counts

**Negative:**
- `transaction` pooling breaks session-level features (temporary tables, LISTEN/NOTIFY, prepared statements, SET session variables). Verified that no current workers use these.
- PgBouncer 1.18 does not support SCRAM-SHA-256; authentication is trust-based (acceptable on localhost only)
- One additional surface to monitor (mitigated by pgbouncer_exporter + Prometheus)

## Related

- Implementation: `docs/05-operations/pgbouncer-configuration.md`
- Migration phases: 3-phase rollout (standalone install → pilot worker → fleet-wide)
- Supavisor config preserved at `supabase/config.toml` with `[db.pooler] enabled = false`
