# AEGIS Control Gates — Definitive Reference

**Last Updated:** 2026-05-23
**Phase:** 213
**Status:** Documentation

---

## Overview

AEGIS BESS dispatch control flows through **4 gate tiers**. All tiers must pass before physical writes occur.

```
TIER 1          TIER 2           TIER 3           TIER 4
Site Mode  →  AEGIS Bridge  →  Policy Gates  →  Phase Gates
(supervised+)   (writer flag)     (promotion)       (0A/0B/1)
```

---

## Tier 1: Site Mode Policy Gates

Site operational mode determines execution eligibility.

| Stage | Execution | Approval | Shadow Mode |
|-------|-----------|----------|-------------|
| `commissioning` | **BLOCKED** | N/A | N/A |
| `shadow_live` | **BLOCKED** | N/A | `shadow_mode=True` |
| `advisory` | **BLOCKED** | N/A | Recommendations visible only |
| `supervised` | ALLOWED | Tier 2 required | N/A |
| `automatic` | ALLOWED | None | N/A |

**Source:** `site-002-mode-policy.json`

---

## Tier 2: AEGIS Bridge Gates

Software-level enable/disable for BESS writes.

| Gate | Flag | Default | Phase 0 | Phase 1 |
|------|------|---------|---------|---------|
| Master writer | `aegis_bess_writer_enabled` | `False` | `False` | **`True`** |
| Shadow dispatch | `shadow_mode` | `False` | `False` | N/A |
| Write status | `write_status` | `blocked_by_gate` | `blocked_by_gate` | `active` |

**Source:** `modbus_bess_writer.py`, `aegis_bridge.py`

---

## Tier 3: Policy Promotion Gates

Thresholds for stage-to-stage promotion within site mode policy.

### Stage Transition Matrix

| Gate | shadow_live | advisory | supervised | automatic |
|------|-------------|----------|------------|-----------|
| `freshness_hours_max` | 2.0h | 1.0h | 0.5h | 0.25h |
| `match_coverage_min_pct` | 95% | 97% | 98% | 99% |
| `error_rate_max_pct` | 1.0% | 1.0% | 0.5% | 0.1% |
| `file_manual_sources_max` | 0 | 0 | 0 | 0 |
| `conflict_events_max_24h` | — | 0 | 0 | 0 |
| `commissioning_all_gates_passed` | true | true | true | true |
| `consecutive_pass_days_min` | 2 | 2 | 2 | 2 |
| `quality_gate_allowed` | pass/warn | pass/warn | **pass** | **pass** |
| `min_dwell_hours` | 12h | 24h | 24h | — |

**Exit Demotion Thresholds** (if violated, demote to fallback stage):

| Gate | shadow_live | advisory | supervised |
|------|------------|----------|------------|
| `freshness_hours_max` | 4.0h | 3.0h | 2.0h |
| `match_coverage_min_pct` | 90% | 92% | 95% |
| `error_rate_max_pct` | 2.0% | 1.5% | 1.0% |
| `file_manual_sources_max` | 0 | 0 | 0 |
| `conflict_events_max_24h` | — | — | 1 |
| `min_violation_hours` | 2h | 2h | 1h |

**Source:** `site_mode_policy_service.py`, `site-002-mode-policy.json`

---

## Tier 4: AEGIS Phase Gates

Operational phases for AEGIS deployment.

| Gate | Phase 0A (Simulation) | Phase 0B (Live-Read) | Phase 1 (Write) |
|------|----------------------|----------------------|-----------------|
| Duration | 14 consecutive days | 14 consecutive days | Continuous |
| Tripwires >24h | 0 unresolved | 0 unresolved | 0 unresolved |
| `avg_response_time_s` | < 300s | < 300s | < 300s |
| Modbus write validation | N/A | N/A | **Required** |
| COV readback verification | N/A | N/A | **Required** |
| `aegis_bess_writer_enabled` | `False` | `False` | **`True`** |

**Source:** `TODO.md` (AEGIS Agent Operationalization)

---

## Phase 1 Activation Checklist

All items must be complete before setting `aegis_bess_writer_enabled=True`:

```
□ Phase 0A PASS — 14 consecutive simulation days documented
□ Phase 0B PASS — 14 consecutive live-read days documented
□ docs/06-safety-compliance/aegis-phase1-entry-gate.md signed off
□ Change window scheduled
□ Rollback plan approved
□ Set aegis_bess_writer_enabled=true in config
□ Notify operations team
□ Monitor first 24h closely
```

---

## Rollback Procedure

If AEGIS exhibits unexpected behavior after Phase 1 activation:

```
1. Set aegis_bess_writer_enabled=false (immediate stop)
2. Review modbus_audit/ logs for anomaly patterns
3. Demote site to shadow_live if safety concern
4. File incident report in 01-Control/incidents.md
5. Await Phase 1 re-entry approval after root cause resolved
```

---

## File Map

| File | Purpose |
|------|---------|
| `backend/app/services/aegis_bridge.py` | Dispatch → Recommendation pipeline |
| `backend/app/services/modbus_bess_writer.py` | Modbus TCP write + readback |
| `backend/app/services/site_mode_policy_service.py` | Stage promotion/demotion logic |
| `backend/app/services/phase_promotion_evaluator.py` | Gate evaluation engine |
| `backend/app/data/policies/site-002-mode-policy.json` | Stage threshold config |
| `backend/app/data/policies/site-002-mode-policy-state.json` | Persisted state |
| `docs/06-safety-compliance/AEGIS_PHASE_STATUS.md` | Current gate status dashboard |

---

## Related Docs

- `docs/06-safety-compliance/aegis-phase1-entry-gate.md` — Phase 1 sign-off checklist
- `sentinel-vault/00-GSD-Phases/Phase-213-*.md` — This phase documentation
