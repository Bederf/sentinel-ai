# Mode-by-Mode Write Policy & Rollout Checklist

> **Version:** 1.0 | **Last Updated:** 2026-02-22
> **Status:** Pre-live_control — use this as the gate for first production write

---

## 1. Mode-by-Mode Write Policy Table

**Policy goal:** In live_control, Tier 3 writes only happen when the quality gate is PASS and safety rules pass at execution time.

### simulation

| Gate result | Allowed tiers | Device writes | Extra controls | What happens |
|-------------|--------------|---------------|----------------|--------------|
| PASS | Tier 1, 2, 3 | Yes (simulated) | None | Full pipeline runs |
| WARN | Tier 1, 2, 3 | Yes (simulated) | None | Full pipeline runs |
| FAIL | Tier 1 only | No | CAP_CONFIDENCE forces confidence <= 0.59 | Everything becomes advisory |

### shadow_live

| Gate result | Allowed tiers | Device writes | Extra controls | What happens |
|-------------|--------------|---------------|----------------|--------------|
| PASS | Tier 1, 2, 3 | No | Still run SafetyEngine and COV as dry run | Full pipeline runs but no writes |
| WARN | Tier 1, 2, 3 | No | Same as above | Full pipeline runs but no writes |
| FAIL | Tier 1, 2 only | No | SUPPRESS_TIER3 | Tier 3 disabled, approvals still visible |

### live_control

| Gate result | Allowed tiers | Device writes | Extra controls | What happens |
|-------------|--------------|---------------|----------------|--------------|
| PASS | Tier 1, 2, 3 | Yes | Double safety check, COV verify, rollback enabled, rate limits | Full pipeline including Tier 3 auto-execute |
| WARN | Tier 1, 2 only | Tier 2 only after human approval | SUPPRESS_TIER3 | No auto-execute, approval queue still works |
| FAIL | Tier 1 only | No | BLOCK_WRITES | No writes at all |

### Tight rule to add

**In live_control, treat any metric state NA as FAIL**, even if the metric is marked NA in other modes.

Reason: the threshold table already blocks JSON fallback data in live_control and you want fail-closed for missing signals. If a service is down and cannot provide a metric value, that is a FAIL, not a "not applicable."

---

## 2. Shadow_live to Live_control Rollout Checklist

### A. Pre-checks

#### 1. Quality gate behaves as contract

- [ ] Gate returns PASS / WARN / FAIL correctly for all 14 metrics
- [ ] Enforcement matches the write policy table above
- [ ] Reason codes emitted and logged

#### 2. Safety rules behave as contract

- [ ] `validate_control_change` blocks out-of-range writes
- [ ] INTERLOCK rules block or disable controls as designed
- [ ] Boundary approach escalation emits events at 50%, 75%, 85%, 95%

#### 3. COV and rollback behave as contract

- [ ] `verify_write` catches mismatches
- [ ] Rollback restores original value
- [ ] Rate limiting blocks more than 10 rollbacks per hour

#### 4. Audit trail is complete

- [ ] Every decision writes to `parasite_decisions` and `audit_log`
- [ ] Includes: mode, site_id, device_id, point_name, proposed_value, current_value, rule IDs hit, gate snapshot ID

---

### B. Shadow_live Acceptance Gates

Run shadow_live for **14 consecutive days** on the target site with stable data ingest.

**Pass criteria:**

- [ ] `freshness_minutes` PASS for 95% of evaluations
- [ ] `ingest_error_rate_pct_1h` stays PASS
- [ ] `match_coverage_pct` stays PASS
- [ ] `manual_source_pct` == 0 always
- [ ] `truth_check_pass_rate_pct` PASS
- [ ] `drift_critical_alerts_24h` == 0 for at least 7 consecutive days
- [ ] `rollback_rate_7d_pct` PASS in the M&V service
- [ ] `feedback_capture_rate_7d_pct` >= 90 and `label_lag_p95_hours` <= 24

**If any day hits quality gate FAIL:**
1. Reset the consecutive pass day counter
2. Investigate the reason code
3. Fix root cause, not thresholds

---

### C. Live_control Phased Launch

#### Phase 1: live_control with Tier 3 suppressed (7 days)

- Force SUPPRESS_TIER3 even on PASS for 7 days
- Allow Tier 2 approvals only
- Confirm COV and rollback under real device response times

**Exit criteria:**
- [ ] COV verification pass rate > 98%
- [ ] Rollback rate < 2%
- [ ] Comfort violation rate stays < 3%
- [ ] No drift critical alerts

#### Phase 2: Allow Tier 3 for LOW risk only

- LOW risk + confidence >= 0.90 for first week
- Keep whitelist of device types and points
- Add cooldown after rollback per equipment

**Exit criteria:**
- [ ] Auto-rollback rate < 2%
- [ ] Outcome accuracy within 20% for sampled actions
- [ ] Rejection repeat rate drops week-on-week

#### Phase 3: Allow Tier 3 for MEDIUM risk

- Same as Phase 2 but include MEDIUM
- Keep HIGH and CRITICAL locked to Tier 2 max permanently

---

### D. Kill Switch and Incident Playbook

**Required before first write.**

#### Kill switches

| Switch | Scope | Effect |
|--------|-------|--------|
| Global | All sites | BLOCK_WRITES now |
| Per-site | Single site | BLOCK_WRITES for site_id |
| Per-equipment | Single device | Block device_id |
| Auto-downgrade | Automatic | WARN -> suppress Tier 3, FAIL -> block writes |

#### Incident steps

1. Flip site kill switch
2. Dump last 50 `parasite_decisions` for the site
3. Check gate reason codes
4. Check SafetyEngine hits
5. Check COV failures and device latency
6. Apply cooldown or blocklist
7. Write post-incident note in `audit_log`

---

## 3. Two Gaps to Fix Next

### Gap 1: Oscillation control beyond rate limits

Rate limits alone are not enough. Add:
- Cooldown minutes per equipment after any rollback
- Escalating cooldown on repeat rollbacks in 24h

### Gap 2: Desk agent restart persistence

Move active WO session state from in-memory to Redis or Supabase:
- Key: `user_id` + `sr_code`
- Fields: `active_sr_code`, `collected_items`, `last_prompt`

---

## Related Documents

- [Agent Contract](agent-contract.md) — Clean agent specs, tool permissions, workflows, caching plan
- [Agent Contract Appendix](agent-contract-appendix.md) — 42-entry quality gate threshold table, 6 safety rule types, full ParasiteDecision schema
- [AI Recommendation Agent Full Spec](ai-recommendation-agent-spec.md) — Detailed PARASITE reference
- [Sentry Desk Complaint Agent Full Spec](../05-integrations/sentry-desk-complaint-agent-spec.md) — Detailed Sentry reference

## Implementation References

- **Model:** `backend/app/models/parasite_decision.py` — `ParasiteDecision` dataclass with 21 new audit fields
- **Repository:** `backend/app/database/repositories/parasite_decision_repository.py` — Supabase + JSON fallback with serialization guard
- **Call sites:** `approval_service.py` (5 calls), `tier_routing_engine.py` (1 call), `cov_monitor_service.py` (2 lifecycle updates)
