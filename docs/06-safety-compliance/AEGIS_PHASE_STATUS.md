# AEGIS Phase Status Dashboard

**Last Updated:** 2026-05-23T13:06:21Z
**Site:** site-002 (Sandton City)

---

## Current State

| Parameter | Value | Source |
|-----------|-------|--------|
| Site Mode | `advisory` | site-002-mode-policy-state.json |
| Candidate Stage | `supervised` | site-002-mode-policy-state.json |
| Candidate Since | 2026-05-23T12:39:06Z | ~27min ago |
| AEGIS Writer | **DISABLED** | settings.aegis_bess_writer_enabled=False |
| Phase | Phase 0 | AEGIS operationalization |

---

## Tier 1: Site Mode Status

| Stage | Current | Eligible | Days in Stage |
|-------|---------|----------|---------------|
| `commissioning` | — | No | — |
| `shadow_live` | — | No | — |
| `advisory` | **ACTIVE** | N/A | ~27min (dwell started 12:39) |
| `supervised` | **CANDIDATE** | After 24h dwell | Pending |
| `automatic` | — | After supervised + 24h | Pending |

**Promotion Progress:**
- advisory → supervised requires 24h dwell
- Currently at ~27 minutes
- Est. promotion: 2026-05-24T12:39:06Z

---

## Tier 2: AEGIS Bridge Gates

| Gate | Status | Value |
|------|--------|-------|
| `aegis_bess_writer_enabled` | **OFF** | `False` |
| `aegis_phase` | Phase 0 | 0A/0B pending |

---

## Tier 3: Promotion Gate Thresholds

Target for `advisory → supervised`:

| Gate | Threshold | Current | Status |
|------|-----------|---------|--------|
| `freshness_hours_max` | ≤ 1.0h | ? | Query API |
| `match_coverage_min_pct` | ≥ 97.0% | ? | Query API |
| `error_rate_max_pct` | ≤ 1.0% | ? | Query API |
| `file_manual_sources_max` | 0 | ? | Query API |
| `conflict_events_max_24h` | 0 | ? | Query API |
| `commissioning_all_gates_passed` | true | ? | Query API |
| `consecutive_pass_days_min` | ≥ 2 | ? | Query API |
| `quality_gate_allowed` | pass/warn | ? | Query API |
| `min_dwell_hours` | ≥ 24h | ~0.5h | **IN PROGRESS** |

---

## Tier 4: Phase Gates

| Phase | Status | Days Complete | Requirements Met |
|-------|--------|--------------|-----------------|
| Phase 0A (Simulation) | **PENDING** | 0/14 | Not started |
| Phase 0B (Live-Read) | **PENDING** | 0/14 | Not started |
| Phase 1 (Write) | **BLOCKED** | — | Requires 0A + 0B |

---

## Gate-to-Write Flow

```
TODAY                          FUTURE (Phase 1)
─────────────────────────────────────────────────
advisory stage                supervised or automatic
aegis_bess_writer_enabled=False    aegis_bess_writer_enabled=True
                                   Recommendation → Modbus write
                                   COV readback verification
```

---

## Next Actions

1. **Wait for advisory → supervised promotion** (~24h from 12:39)
2. **Run Phase 0A simulation** — 14 days of simulated dispatch
3. **Run Phase 0B live-read** — 14 days of actual sensor reading
4. **Phase 1 entry gate** — all checklists signed off
5. **Enable `aegis_bess_writer_enabled=True`**

---

## Quick Reference

```bash
# Check current site stage
cat backend/app/data/policies/site-002-mode-policy-state.json | jq .current_stage

# Check aegis writer status
grep aegis_bess_writer_enabled backend/app/config/settings.py

# Check promotion candidate
cat backend/app/data/policies/site-002-mode-policy-state.json | jq .candidate_stage
```

---

## Related Docs

- `AEGIS_CONTROL_GATES.md` — Full gate matrix
- `docs/06-safety-compliance/aegis-phase1-entry-gate.md` — Phase 1 sign-off
