# AEGIS Phase 1 Entry Gate — BESS Live Dispatch Activation

**Version:** 1.0
**Status:** DRAFT — all items must be signed off before `aegis_bess_writer_enabled=True`

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
| C4 | Shadow period completed — minimum 14 days of blocked proposals with consistent dispatch patterns | Decision count + date range from `/api/parasite/aegis/dashboard` | [ ] |
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
