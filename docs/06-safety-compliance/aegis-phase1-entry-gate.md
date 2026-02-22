---
title: "AEGIS phase 1 entry gate for BESS live dispatch activation"
type: "audit"
status: "draft"
version: "1.1.0"
created: "2026-02-22"
updated: "2026-02-22"
tags: ["aegis", "phase-1", "safety", "compliance", "bess"]
related: ["../10-operations/aegis-phase0-daily-ops.md", "../05-integrations/aegis-site-002-discovery.md"]
domain: "compliance"
audience: "safety-engineers"
complexity: "intermediate"
estimated_read_time: 15
---

# AEGIS Phase 1 Entry Gate — BESS Live Dispatch Activation

**Version:** 1.1
**Status:** DRAFT — all items must be signed off before `aegis_bess_writer_enabled=True`

---

## Prerequisites: Phase 0A and 0B Completion

Both prerequisite phases must pass before Phase 1 items are evaluated. Evidence from 0A and 0B must be kept separate — simulation results do not satisfy live-read criteria.

### Phase 0A — Simulation (14 days, data_mode=simulation)

| # | Criterion | Evidence | Pass |
|---|-----------|----------|------|
| 0A1 | 14 consecutive clean days — zero `illegal_state_detected` | Tracker CSV rows 1-14, all `illegal_state_detected=no` | [ ] |
| 0A2 | Zero unresolved tripwires older than 24h across entire run | Tracker CSV, all `oldest_tripwire_age_min < 1440` | [ ] |
| 0A3 | All audit fields present on every sampled decision | Tracker CSV, all `all_required_fields_present=yes` | [ ] |
| 0A4 | Dispatch patterns match expected tariff/SoC behaviour — peak discharge, off-peak charge, idle mid-day | Dashboard screenshots from days 1, 7, 14 | [ ] |
| 0A5 | No `phase1_blocker=yes` on any day | Tracker CSV complete | [ ] |

### Phase 0B — Live-Read (14 days, data_mode=live-read)

| # | Criterion | Evidence | Pass |
|---|-----------|----------|------|
| 0B1 | All 0A criteria met on live telemetry (0B1-0B5 mirror 0A1-0A5) | Separate tracker CSV with `data_mode=live-read` | [ ] |
| 0B2 | Real BESS SoC/temperature/power values plausible — no stuck sensors, no out-of-range | 3 sample decisions showing real values within equipment spec | [ ] |
| 0B3 | Constraint triggers match actual equipment limits — temp ceiling, SoC floor, frequency bounds | At least 1 constraint trigger observed and correctly handled | [ ] |
| 0B4 | Tier 2 approval SLA < 5 min average on real data | Tracker `avg_response_time_s` column, 14-day mean | [ ] |
| 0B5 | `pending_over_30m = 0` on at least 12 of 14 days | Tracker CSV | [ ] |

---

## A. Hardware Readiness

| # | Item | Evidence | Pass |
|---|------|----------|------|
| A1 | Modbus TCP wiring verified — inverter IPs reachable from SENTINEL host (`ping` + Modbus read test) | Screenshot of successful register read | [ ] |
| A2 | Write latency measured end-to-end (register write → COV readback < 500 ms p95) | Latency log extract (min 50 samples) | [ ] |
| A3 | BESS isolator location documented — physical lockout/tagout procedure available on-site | Photo + SOP reference | [ ] |
| A4 | UPS on SENTINEL server confirmed — minimum 15 min hold-up for graceful shutdown | UPS model + runtime test result | [ ] |

---

## B. Safety Path

| # | Item | Evidence | Pass |
|---|------|----------|------|
| B1 | COV write/readback path tested — write setpoint, confirm readback within tolerance | Test log showing 10 successful COV cycles | [ ] |
| B2 | Auto-rollback path tested — simulate failed COV, confirm rollback executes and original value restored | Rollback event in decision audit log | [ ] |
| B3 | NRS 097 disconnect protection active on all inverters — anti-islanding verified | Inverter configuration export | [ ] |
| B4 | Fire alarm interlock tested — BESS transitions to safe state on fire alarm activation | Test report with alarm trigger timestamp | [ ] |
| B5 | Temperature envelope enforced — charge blocked > 40 C, discharge blocked > 44 C | Constraint log showing temperature blocks | [ ] |

---

## C. Operations Readiness

| # | Item | Evidence | Pass |
|---|------|----------|------|
| C1 | Tier 2 approval SLA met during shadow period — average response time < 5 min | AEGIS dashboard screenshot (avg_response_time_s) | [ ] |
| C2 | Named Tier 2 approver + backup confirmed with OPERATOR role in SENTINEL | User list showing role assignments | [ ] |
| C3 | AEGIS dashboard reviewed — no tripwire alerts in last 7 days | Dashboard screenshot showing clean 7d window | [ ] |
| C4 | Shadow period completed — Phase 0A (14d simulation) + Phase 0B (14d live-read) both passed | Completed tracker CSVs with `data_mode` column | [ ] |
| C5 | Dispatch decision tree reviewed against actual load patterns — tariff bands, SoC thresholds, and power limits validated | Review meeting minutes | [ ] |

---

## D. Compliance and Audit

| # | Item | Evidence | Pass |
|---|------|----------|------|
| D1 | Audit extract reviewed — all `parasite_decisions` records have: `correlation_id`, `contributing_factors`, `write_status`, `approval_outcome`, `command_hash` | Query output showing field completeness | [ ] |
| D2 | SSEG compliance rules active — export limit enforced, City Power reporting template configured | SSEG settings export + test dispatch at limit | [ ] |
| D3 | Insurance conditions reviewed — warranty cycle limits (daily charge/discharge count) configured in constraints | Constraint config showing cycle cap | [ ] |
| D4 | Huawei FusionSolar cloud override authority clarified — SENTINEL vs cloud priority documented | Written confirmation from integrator | [ ] |

---

## Sign-off

| Role | Name | Date | Signature |
|------|------|------|-----------|
| Site Facilities Manager | | | |
| Controls Engineer | | | |
| SENTINEL Ops Lead | | | |

---

## Post-Activation: First 24h Monitoring Checklist

After setting `aegis_bess_writer_enabled=True`:

- [ ] Continuous AEGIS dashboard monitoring (minimum 2 operators rotating)
- [ ] COV success rate > 95% (check `/api/parasite/health`)
- [ ] No tripwire alerts fired (`aegis.tripwire.gate_fail`, `aegis.tripwire.repeated_hash`)
- [ ] Review first 10 write decisions manually — verify setpoint, power, SoC all within expected ranges
- [ ] Confirm Huawei FusionSolar cloud shows consistent state with SENTINEL commands
- [ ] End-of-day debrief: document any anomalies, adjust constraints if needed

---

**Next review date:** _To be scheduled after shadow period completion_
