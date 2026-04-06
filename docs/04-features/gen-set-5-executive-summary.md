---
title: "Gen Set 5 — Diagnostic Assessment & Cost-Benefit Analysis"
type: "spec"
status: "draft"
version: "1.0.0"
created: "2026-03-31"
updated: "2026-03-31"
tags: ["sentinel", "documentation"]
related: []
domain: "bms"
audience: "all"
complexity: "intermediate"
estimated_read_time: 10
---

# Gen Set 5 — Diagnostic Assessment & Cost-Benefit Analysis
## Executive Summary for Ntaote Moshoeshoe, TP, and Jimmy

**Equipment:** Gen Set 5 (100kW Diesel Generator) — site-002, Sandton City
**Current Issue:** R611,820.75 repair quote from Diesel Electric — requires validation before approval
**Proposed Approach:** Use SENTINEL's diagnostic AI to confirm repair scope and validate cost-benefit
**Timeline:** 30-minute field assessment, then 1-week analysis

---

## The Problem We're Solving

Gen Set 5 has **failed 8 times in 4 years** with a recurring pattern:
- 2023: Speed controller fails → Valve clearance needed
- 2024: Speed controller replaced (didn't fix root cause) → Fuel pump leaks → Rewiring
- 2025: Speed controller issues continue → Fuel pump blocked → Injectors removed

**Pattern suggests:** Fuel system contamination cascading to speed controller failures, NOT just component defects.

**The Quote (R611K):** Diesel Electric is recommending a comprehensive overhaul (fuel system, governor, engine tuning) but we need to validate this diagnosis before spending R611,820.75.

---

## Solution: 3-Phase Diagnostic Approach

### 🎯 Phase 41-03 (30 minutes in field)
**What:** Technician records vibration & audio data using free phyphox app on smartphone
**Where:** Gen Set 5 during normal operation
**Why:** SENTINEL's AI analyzes the recordings to identify exact fault signatures:
- ✅ Is fuel cavitation happening? (audio spectrum analysis)
- ✅ Is governor hunting/oscillating? (vibration analysis)
- ✅ Are injectors misfiring? (combustion knock detection)
- ✅ Is bearing wear significant? (vibration baseline)

**Outcome:** Baseline measurements + fault fingerprint → confirms/challenges Diesel Electric diagnosis

---

### 💰 Phase 44 (Analysis & Cost-Benefit)
**What:** SENTINEL calculates remaining useful life (RUL) for each subsystem
**Output:**
- Is the R611K repair justified? (evidence-based decision)
- What is Gen Set 5's health score now vs post-repair? (0-100 scale)
- How many years until critical failure if we DON'T repair? (RUL estimate)

**Decision Rule:**
- ✅ If fuel cavitation + speed control + engine wear ALL confirmed → **Approve R611K**
- ⚠️ If only 2-3 issues confirmed → **Negotiate scope reduction** (save R100-200K)
- ❌ If core issues NOT confirmed → **Request alternative diagnosis** from Diesel Electric

---

### ✔️ Phase 46 (Post-Repair Validation)
**What:** After Diesel Electric completes repair, capture identical measurements
**Why:** Validate that the R611K repair actually worked
**Output:** Effectiveness score (target >85% improvement)

**If effective:** Gen Set 5 baseline established for ongoing condition monitoring
**If ineffective:** Trigger warranty service from Diesel Electric

---

## Implementation: What We Need from You

### 1️⃣ Schedule Field Visit (This Week)
- **Who:** Ntaote (or TP/Jimmy — anyone familiar with Gen Set 5)
- **Duration:** 30 minutes during normal operations
- **Requirements:**
  - Android smartphone with phyphox app (free)
  - Pen + paper for manual readings
  - Access to Gen Set 5 in running state

### 2️⃣ Capture Phyphox Data
- 4 accelerometer recordings (engine, fuel pump, governor, radiator)
- 3 audio spectrum recordings (engine bay, injectors, bearing area)
- Manual sensor readings (fuel pressure, oil temp, RPM, voltage, etc.)

**We provide:** Detailed technician checklist (5-page field guide)

### 3️⃣ Send Data to SENTINEL
- Export phyphox files as CSV/JSON
- Email to: [SENTINEL data endpoint]
- Include manual readings form

### 4️⃣ Receive Cost-Benefit Report
- **Timeline:** 1 week after data received
- **Includes:**
  - Root cause analysis (is fuel cavitation really the problem?)
  - RUL estimates per subsystem
  - Recommendation: Approve / Negotiate / Reject the R611K quote
  - Supporting evidence from SENTINEL analysis

---

## Why This Matters

**Scenario A: Approve R611K without SENTINEL validation**
- Risk: Repair doesn't address root cause → Same failures in 12-18 months → Wasted R611K + lost productivity
- Possible: Diesel Electric's diagnosis is incomplete (e.g., only replaced components, didn't purge fuel system)

**Scenario B: Use SENTINEL diagnostic first**
- Confirm: Fuel cavitation + speed control + engine issues are real → R611K justified ✅
- Challenge: If only 1-2 issues confirmed → Negotiate scope reduction → Save R150-250K
- Protect: Post-repair validation ensures Gen Set 5 actually fixed before sign-off

**Expected Value:** R50-150K savings + data-driven decision instead of gut feel

---

## What You Get After This

1. **Baseline Measurements:** Captured for future condition monitoring
2. **Cost-Benefit Report:** Data-driven recommendation on R611K repair
3. **Diagnostic Insight:** Exact root causes (not guesses) for Gen Set 5 failures
4. **Post-Repair Validation:** Proof that repair actually worked (Phase 46)
5. **Ongoing Monitoring:** Gen Set 5 added to SENTINEL for monthly condition checks using phyphox

---

## Next Step

**Action for Ntaote:**
1. Confirm your availability for 30-minute field visit (this week or next)
2. Let us know when Gen Set 5 is available for measurement (should be running for best data)
3. We'll prepare detailed technician checklist + phyphox setup guide

**Contact:** Send confirmation to [SENTINEL contact] with dates/times

**Questions?** Ask SENTINEL AI chat: "How does Gen Set 5 diagnostic work?" — full technical details available

---

## Technical Documents Available

For deeper technical details:
- **Full Protocol:** `/docs/04-features/gen-set-5-baseline-protocol.md` (20 pages, all measurement locations)
- **Quick Start:** `/docs/04-features/gen-set-5-quick-start-checklist.md` (field checklist)
- **Failure Analysis:** Historical pattern breakdown + root cause assessment

---

**Prepared by:** SENTINEL AI Diagnostic Team
**Date:** 2026-02-12
**Equipment:** S002-GEN-G-005 (Gen Set 5)
**Status:** Ready for field deployment — awaiting Ntaote's confirmation

---

## Bottom Line

> **Before approving R611,820.75, spend 30 minutes capturing phyphox data to confirm Diesel Electric's diagnosis is correct. SENTINEL will tell you exactly what's wrong, whether the repair scope is justified, and validate it actually worked post-repair.**

**This 30-minute assessment could save R100K+ and eliminate the recurring failures permanently.**

Expected timeline: 30-min field visit → 1-week analysis → Cost-benefit recommendation
