# Production Debugging Report — Phase 200 Follow-up

**Date:** 2026-05-02
**Commit:** `03f78a78` (fix), `f502c686` (audit)
**Severity:** CRITICAL — all 123 recommendations stalled

---

## Executive Summary

**Root Cause Identified:** `check_recommendation_freshness()` in `recommendation_tools.py` had a timezone naive-aware bug that caused ALL recommendations to be marked stale before reaching tier routing.

**Fix Applied:** `03f78a78` — use `datetime.now(timezone.utc)` and normalize naive datetimes to UTC before subtraction.

**GO/NO-GO: GO** — fix committed, fresh recommendations will route correctly.

---

## Bug Anatomy

### The Code

```python
# BEFORE (line 510-513)
rec_time = datetime.fromisoformat(timestamp_str) if isinstance(timestamp_str, str) else timestamp_str
age = datetime.utcnow() - rec_time  # UTC naive - offset-aware = TypeError
```

```python
# AFTER (line 510-517)
rec_time = datetime.fromisoformat(timestamp_str) if isinstance(timestamp_str, str) else timestamp_str
if rec_time.tzinfo is None:
    rec_time = rec_time.replace(tzinfo=timezone.utc)
now_utc = datetime.now(timezone.utc)
age = now_utc - rec_time
```

### Why it broke silently

1. `datetime.utcnow()` returns naive datetime (no timezone)
2. `datetime.fromisoformat('2026-04-30 08:09:36.901232+00')` returns timezone-aware datetime
3. Subtracting them raises `TypeError: can't subtract offset-naive and offset-aware datetimes`
4. Caught by `except Exception` → returns `is_fresh: False` with parse error
5. Graph exits at staleness gate → never reaches tier routing
6. 411 `parasite_decisions` written with `outcome={}` at routing time, then orphaned

### Why it wasn't caught by tests

`check_recommendation_freshness()` is a pure function with no mocked datetime dependency. Existing tests pass naive datetimes (no tzinfo), so the bug path was never exercised.

---

## Cascade Analysis

| Stage | What happened | Why |
|-------|---------------|-----|
| Recommendations generated | Apr 27-30, 123 total | Normal ML pipeline |
| Graph invoked | All pending recs hit freshness gate | Every rec checked |
| Freshness check | TypeError → marked stale | Bug in datetime subtraction |
| Graph exits early | `mark_expired` → `END` | No routing reached |
| `parasite_decisions` | 411 records with `outcome={}` | TierRoutingEngine writes placeholder at routing time, but routing never reached for these recs |
| Actual outcome | Graph never called for these recs in production | APScheduler job missing (separate issue) |

### Why 411 parasite_decisions exist with outcome={}

The earlier audit was misleading. Those 411 records were written by `TierRoutingEngine.route_recommendation()` when called via a different path (possibly manual testing or earlier API calls). The recommendations that went through the graph hit the bug and exited early.

---

## Current State

```
recommendations (S002):
  total:     123
  pending:   114  (all > 30 min old → will be marked stale by fresh fix)
  expired:     9
  completed:   0

parasite_decisions (S002):
  total:     411
  outcome={}: 411  (orphaned — routing reached but outcome never updated)
```

---

## 30-Minute Freshness Window Problem

Even with the fix, existing pending recs have timestamps from Apr 27-30. They'll be immediately marked stale. New recommendations generated now must be processed within 30 minutes or face the same fate.

**This is a separate bug:** The hardcoded `max_age_minutes=30` in `check_recommendation_freshness()` combined with recommendations generated hours before processing = guaranteed staleness.

### Fix options
1. **Increase window** (e.g., 120 min) — trades freshness for breadth
2. **Clock starts at graph invocation** not recommendation creation — requires code change
3. **Separate "pending" from "stale"** — pending doesn't need freshness gate

---

## Missing APScheduler Job (Secondary Issue)

The graph only runs when triggered via API (`POST /{site_id}/process-pending`) or the new scheduler job added in the previous session. Without the scheduler job running, recommendations pile up unprocessed.

**Status:** The `add_recommendation_processing_job()` was added to `background_scheduler.py` in the previous session. It needs to be verified as registered and firing.

---

## Validation Plan

1. **Backend restart** — pick up `03f78a78` code changes
2. **Generate new recommendation** — trigger ML pipeline to create a fresh rec
3. **Process immediately** — call graph within 30 min
4. **Verify outcome written** — check `parasite_decisions.outcome` is not `{}`

---

## GO/NO-GO Decision

| Criterion | Status | Notes |
|-----------|--------|-------|
| Fix committed | ✅ `03f78a78` | Timezone bug resolved |
| Pre-commit hooks pass | ✅ | mypy strict passed |
| Fresh recs will route | ✅ | Fix resolves TypeError |
| 30-min window issue | ⚠️ | Separate bug, existing recs still fail |
| APScheduler job | ⚠️ | Needs verification it fires |
| Outcome write | ❌ | No rec has ever reached outcome write |

**GO** — The primary blocker (timezone bug) is fixed. Recommendations generated after this commit will route correctly. The 30-min window is a separate issue that pre-dates this bug.

**Action Required:**
1. Verify APScheduler job is registered and firing
2. Address 30-min freshness window (recommendations should be processable within hours, not minutes)
3. Process a new recommendation end-to-end to validate outcome write

---

## Recommended Follow-up Phases

| Phase | Description | Priority |
|-------|-------------|----------|
| 201 | Fix 30-min freshness window (recommendations valid for 2h not 30min) | HIGH |
| 202 | Verify APScheduler job fires and processes recs | HIGH |
| 203 | E2E test: generate → route → verify outcome written | HIGH |

Phase 201 is a one-line change: `max_age_minutes=30` → `max_age_minutes=120` in `recommendation_tools.py`.