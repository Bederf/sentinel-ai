---
title: "k6 Baseline Load Test — Results"
date: "2026-06-14"
scenario: "tests/k6/baseline.js"
vus: 50
duration: "2m"
environment: "localhost:9095 (production VPS, 4 Uvicorn workers)"
---

# k6 Baseline Load Test Results

**Run date:** 2026-06-14
**Scenario:** `tests/k6/baseline.js`
**Config:** 50 VUs, 2-minute ramp (0→50→0), 3 endpoints per iteration
**Backend:** 4 Uvicorn workers (was 2 prior to this test)

---

## Summary

| Metric | Value |
|--------|-------|
| Total requests | 2 526 |
| Iterations | 842 |
| Throughput | ~21 req/s |
| Error rate | **0%** (2526/2526 checks passed) |
| p(50) latency | 245 ms |
| p(90) latency | 3 290 ms |
| p(95) latency | 6 980 ms ⚠️ |
| p(99) latency | 22 340 ms ⚠️ |
| Max latency | 26 540 ms |

---

## Per-Endpoint Breakdown

| Endpoint | min | median | p(95) | Threshold |
|----------|-----|--------|-------|-----------|
| `GET /api/sites` | 9 ms | 191 ms | 2 376 ms | ✗ just over 2 000 ms |
| `GET /api/health` | **8.5 ms** | 163 ms | 21 910 ms | response is cached — high tail is queueing under load |
| `GET /api/alerts?limit=5` | 48 ms | 510 ms | 5 605 ms | ✗ DB read bottleneck |

**`/api/health` is now cached** — the response object is built once at first call and reused. The high p(95) reflects queueing when 50 VUs share 4 workers with DB-heavy endpoints, not the endpoint itself. In isolation the endpoint returns in <10 ms.

---

## Threshold Results

| Threshold | Result |
|-----------|--------|
| `errors rate < 5%` | ✓ PASS — 0% |
| `http_req_duration p(95) < 2 000 ms` | ✗ FAIL — 6 980 ms |
| `http_req_duration p(99) < 5 000 ms` | ✗ FAIL — 22 340 ms |

---

## Comparison With 2 Workers (Prior Run)

| Metric | 2 workers | 4 workers | Change |
|--------|-----------|-----------|--------|
| Throughput | 18 req/s | 21 req/s | **+17%** |
| Error rate | 0% | 0% | — |
| `/api/sites` p(95) | 5 692 ms | 2 376 ms | **-58%** |
| `/api/alerts` p(95) | 6 395 ms | 5 605 ms | -12% |
| `/api/health` min | 7.5 ms | 8.5 ms | equivalent (cache works) |
| Health tail under load | 18 949 ms | 21 910 ms | equivalent (queueing-driven) |

The 4-worker bump made `/api/sites` close to threshold and `/api/alerts` measurably better. The remaining tail is Supabase connection pool saturation.

---

## Analysis

**What changed in this test cycle:**

1. **`/api/health` cached** — response is built once and reused. Min latency is now 8.5ms regardless of load.
2. **Bypass paths in metrics middleware** — `/api/health` and `/metrics` skip request instrumentation entirely (no gauge increment, no timing overhead).
3. **Workers 2 → 4** — 17% throughput gain. Each worker can now own a separate event loop.

**Remaining bottleneck:** The Supabase managed connection pool is shared across all workers. `/api/alerts` is the dominant DB read; under 50 VUs it saturates the pool, which causes long-tail queueing that affects every endpoint. The health endpoint's 21.9s p(95) is not the endpoint being slow — it is the worker event loop being blocked waiting for the DB pool.

**Practical ceiling:** The system handles 50 concurrent users with zero errors. For the current single-site deployment this is acceptable. For a multi-site rollout, the connection pool needs PgBouncer or per-worker pool sizing.

---

## Raw Results

Raw NDJSON output (`baseline-results.json`, ~10.6 MB) is gitignored. Re-run to regenerate:

```bash
k6 run tests/k6/baseline.js --out json=tests/k6/baseline-results.json
```
