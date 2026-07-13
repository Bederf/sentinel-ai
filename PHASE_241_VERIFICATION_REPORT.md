# Phase 241 Verification Report — M2.4 Drift-Driven Retraining

**Date**: 2026-07-13
**Status**: COMPLETE
**Commits**: `fda9eb75` (Plan 1), `7fb1d02b` (Plan 2)

## What M2.4 adds

Drift is now a repair trigger, not just a punishment. DRIFT_DETECTED enqueues
retraining; the queue processor retrains through the existing Phase 239 path
(baseline persistence + audit); the next drift evaluation reads the new
baseline; trust recovers; the operator re-promotes via the existing readiness
engine. No automatic re-promotion (human-authority invariant preserved).

## Test Results (targeted only — no full-suite runs, per CPU constraint)

| Suite | Result |
|-------|--------|
| Plan 1: test_retraining_queue.py | 17/17 |
| Plan 2: test_retraining_queue_processor.py | 14/14 |
| Phase 240: test_sustained_drift_demotion.py | 20/20 |
| Phase 240: test_drift_trust_integration.py | 26/26 |
| M2.1: test_readiness_orchestrator.py | 7/7 |
| Phase 239: baselines/detector/scheduler/calculator | 58/58 |
| **Total** | **142/142** |

## Recovery Loop Demonstration (real DB, mocked training)

```
1. enqueue on DRIFT_DETECTED         -> queue row created
2. duplicate enqueue                  -> deduped (None)
3. processor run (mocked training)    -> status=completed, attempts=1,
   trigger_retraining called with the entry's exact coordinates
4. post-retrain drift re-evaluation   -> site-scoped verdict path runs;
   site-005 returns insufficient_data (honest fail-closed: site-005 has no
   measured accuracy rows of its own — cross-site borrowing now prevented)
5. test rows cleaned up
```

## Acceptance Criteria

- AC-1 ✅ Drift-triggered enqueue — producer hook on feature drift (metrics.py)
  + verdict job enqueues on DRIFT_DETECTED; age-based trigger retained
- AC-2 ✅ Queue governance — dedupe, 24h rate-limit, timestamped transitions
- AC-3 ✅ Queue processor — 30-min job, one entry per run (CPU throttle),
  pending→running→completed/failed/escalated
- AC-4 ✅ Recovery path — demonstrated end-to-end (mocked training per spec)
- AC-5 ✅ Fail-closed retries — max 3; permanent errors escalate immediately;
  training-lock contention re-pends without burning the entry
- AC-6 ✅ Operator visibility — equipment_findings carry "retraining":
  pending/running/escalated
- AC-7 ✅ No regression — 142 targeted tests, zero failures, zero full-suite runs

## Pre-existing gaps found and fixed during Phase 241

1. **No global training lock** — trigger_retraining had three concurrent caller
   paths (feedback job, API, monitoring triggers); concurrent 50-epoch trainings
   were the source of the system CPU pressure. Fixed: module-level lock, all
   paths serialize (Plan 1).
2. **detect_model_drift had no production caller** — 761k drift_detection_log
   rows, zero with a verdict; the Phase 240 demotion watcher and readiness
   drift gates could never see real verdicts. Fixed: hourly drift verdict
   evaluation job (Plan 2).
3. **Phase 240 demotion watcher never registered at startup** — defined but
   never wired. Fixed: registered in startup/events.py (Plan 2).
4. **drift_detection_log.equipment_id column missing** — every readiness drift
   lookup errored (42703) and fail-closed to UNEVALUABLE. Fixed: migration 240.
5. **Migration 236 partially applied** — ml_training_audit_log table and the
   ml_model_baselines immutability trigger were missing from the live DB.
   Fixed: migration re-applied, all objects verified present.
6. **Verdict casing mismatch** — detect_model_drift emits lowercase verdicts;
   consumers match uppercase. Fixed: verdict job uppercases on write.

## Deployment note

The three new/rewired scheduler jobs (drift verdict evaluation, queue
processor, sustained-drift demotion) register at startup — they go live on the
next `sudo systemctl restart sentinel-backend` (wait 30s before health polling).

## Next: M2.5 Champion/Challenger

- Validate retrained model against incumbent before activation
- UNEVALUABLE-triggered retraining (deliberately excluded from M2.4)
- Retraining priority weighting by equipment criticality
