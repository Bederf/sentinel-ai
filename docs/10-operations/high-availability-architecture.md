---
title: "High Availability Architecture"
type: "architecture"
status: "approved"
version: "1.0.0"
created: "2026-06-23"
updated: "2026-06-23"
tags: ["sentinel", "ha", "failover", "redundancy", "disaster-recovery"]
domain: "operations"
audience: "platform-team, security, bank-it"
complexity: "intermediate"
estimated_read_time: 10
---

# High Availability Architecture

## Design Decision

SENTINEL uses a **single active instance** topology with **database-level redundancy** and **graceful degradation** for read paths. This is an intentional architectural choice for BMS workloads where:

- Building operations never depend on Sentinel availability (BMS runs independently)
- Site deployments are typically single-building with modest throughput
- Multi-region active-active adds complexity without proportional BMS benefit

## Degradation Matrix

| Component | Failure Mode | Impact | Recovery |
|-----------|-------------|--------|----------|
| Application (FastAPI) | Service crash | Web UI/API unavailable | systemd auto-restart (<30s) |
| Database (PostgreSQL) | Primary outage | Write operations blocked | Promote standby (DR runbook) |
| Database (PostgreSQL) | Replica failure | DR coverage degraded | Rebuild replica (non-disruptive) |
| Redis cache | Flush/restart | Cache miss, reads fall to DB | Auto-rebuilds on next query |
| LLM (Ollama) | Model unload | Inference fails, no cloud fallback | Auto-reload on next request |
| Network (internet) | Connectivity loss | Notifications delayed | Local operations continue |
| SIMBIOT bridge | Connection lost | Telemetry stale | Store-and-forward on reconnect |

## Three-Tier Read Fallback

Read paths degrade gracefully through three tiers:

1. **Supabase (primary)** — canonical data store
2. **Redis (cache)** — hot read cache with TTL-based expiry
3. **JSON files (cold)** — static fallback for critical config

This ensures dashboards and status endpoints remain readable even when the primary database is degraded.

## Recovery Flow

```
Failure detected
    ↓
L1: Auto-restart (systemd/container health checks)
    ↓
L2: Service-level recovery (restart container, verify /health)
    ↓
L3: DR invocation — Database failover
    ├── Fence primary (pg_ctl promote or STONITH)
    ├── Promote standby
    └── Re-point application to new primary
    ↓
L4: Full rebuild — Restore from backup + WAL archive
    ↓
Verification: /health endpoint, auth, read/write test, monitoring pipeline
```

## Failover Guardrails

| Condition | Action |
|-----------|--------|
| Primary unreachable + standby healthy | Promote standby, repoint app |
| Primary degraded (high load, slow queries) | Do not failover — scale or optimize first |
| Logical corruption suspected | Do not promote standby (corruption may have replicated). Restore from clean backup. |
| Split-brain risk | Verify primary is truly isolated before promotion |

## Known Gaps

- Single application instance — no active-active or blue/green
- No load balancer — all traffic hits one backend
- Redis single-node — no cluster mode
- Failover is manual (per DR runbook) — not automated
- DR exercise not yet executed (template prepared)
