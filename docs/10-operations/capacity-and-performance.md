---
title: "Capacity and Performance"
type: "operations"
status: "approved"
version: "1.0.0"
created: "2026-06-14"
updated: "2026-06-14"
author: "SENTINEL Platform Team"
tags: ["performance", "capacity", "k6", "scaling", "load-testing"]
domain: "operations"
audience: "developer"
complexity: "intermediate"
estimated_read_time: 6
---

# Capacity and Performance

## Validated Baseline (2026-06-14)

Load test: 50 virtual users, 2-minute ramp, 3 endpoints per iteration.  
Environment: production VPS (`localhost:9095`), live Supabase backend, 4 Uvicorn workers.  
Full results: `baseline-summary.md` (in this directory).

| Metric | Value |
|--------|-------|
| Peak concurrent users tested | 50 VUs |
| Total requests | 2 526 |
| Throughput | ~21 req/s |
| Error rate | **0%** |
| p(50) latency | 245 ms |
| p(90) latency | 3 290 ms |
| p(95) latency | 6 980 ms |
| p(99) latency | 22 340 ms |

---

## Per-Endpoint Latency

| Endpoint | min | median | p(95) | Notes |
|----------|-----|--------|-------|-------|
| `GET /api/sites` | 9 ms | 191 ms | 2 376 ms | Just over threshold; metadata + Redis |
| `GET /api/health` | **8.5 ms** | 163 ms | n/a (cached) | Response cached at first call — tail is queueing, not endpoint |
| `GET /api/alerts` | 48 ms | 510 ms | 5 605 ms | Primary bottleneck — DB read under concurrency |

---

## Infrastructure

| Layer | Current spec |
|-------|-------------|
| VPS | Contabo VPS, single instance |
| Backend | FastAPI + Uvicorn, 4 workers, systemd service |
| Database | Supabase (managed PostgreSQL) — shared connection pool |
| Cache | Redis (local) |
| Concurrency model | Async (httpx, asyncpg) |
| Replication | Streaming WAL replica on second VPS (DR standby — see BCP/DR doc) |

No load balancer. No blue/green. Single active instance per deployment.

---

## Observed Ceiling

The system handles **50 concurrent users with zero errors**. The p(95) latency threshold
(< 2 000 ms) is met only at low concurrency (≤ ~10 VUs based on endpoint medians).

**Root cause of tail latency:** Supabase's managed connection pool is shared across all
endpoints. At 50 VUs, `/api/alerts` DB reads saturate the pool and cause queueing —
visible in the wide spread between median (510 ms) and p(95) (5 605 ms). The health
endpoint is **not** affected by this at the endpoint level (response is cached); the
remaining tail reflects worker event-loop queueing under burst load, not the endpoint
itself.

---

## Scaling Path

The current deployment is single-site (S002). For multi-site rollout:

| Bottleneck | Mitigation |
|------------|-----------|
| Supabase connection pool saturation | Add PgBouncer between backend and Supabase |
| Single instance throughput | Horizontal scale behind a load balancer (nginx/Caddy) |
| DB read latency | Promote WAL replica to read replica; route GET queries there |
| Health check competes with DB | Make `/api/health` return cached status, not live DB ping |

None of these are required for the current single-site deployment. They become necessary
at ~5 concurrent sites or ~200 concurrent users.

---

## Uptime Monitoring

A k6 synthetic check polls `/api/health` every 60 seconds and writes results to the
`api_uptime_checks` Supabase table (`load_tests/synthetic_uptime_check.js`). This gives
a continuous latency SLI series independent of load tests.

---

## Re-running the Baseline

```bash
# From repo root
k6 run tests/k6/baseline.js --out json=tests/k6/baseline-results.json
# Raw JSON is gitignored — update baseline-summary.md with the new numbers
```

Available scenarios:

| Script | VUs | Duration | Purpose |
|--------|-----|----------|---------|
| `tests/k6/baseline.js` | 50 | 2 min | Core API throughput and latency |
| `tests/k6/alarm-storm.js` | 10 | 40 s | Alert feed under burst read load |
| `tests/k6/recommendation-burst.js` | 20 | 40 s | Recommendation endpoint burst |
| `k6/scenarios/device-control.js` | 10→100 | 4 min | Control endpoint stress test |

---

## Related Docs

- [BCP/DR Procedures](../09-security/bcp-dr-procedures.md) — WAL replica, RTO/RPO
- [Monitoring Stack](monitoring-stack.md) — Prometheus, Grafana, Loki
- [CI/CD Pipeline](cicd-pipeline.md) — How to add load tests to the nightly pipeline
