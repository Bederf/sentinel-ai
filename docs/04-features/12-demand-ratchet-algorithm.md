---
title: "Demand Ratchet Algorithm"
type: "feature"
status: "active"
version: "1.0.0"
created: "2026-05-24"
updated: "2026-05-24"
tags: ["demand-ratchet", "nmd", "peak-demand", "municipal-billing", "cost-optimization"]
domain: "energy"
audience: "developers", "operations"
complexity: "intermediate"
estimated_read_time: 5
---

# Demand Ratchet Algorithm

## Problem

City Power (and most SA municipalities) bills the **higher** of:
- (a) actual measured demand in the current month, or
- (b) the highest demand recorded in the previous **11 months** (the "ratchet")

This means a single demand spike can inflate billing demand for up to 12 months. The ratchet resets only when a full year passes without exceeding the previous peak.

## Algorithm

**Source:** `backend/app/services/demand_ratchet.py`

### 1. History Collection

Load trailing monthly peak demand records. In production these come from Supabase (`billing_demand` table); fallback uses seeded historical data for site-002:

```
Mar 2025: 1,620 kVA   →  Sep 2025: 1,580 kVA
Apr 2025: 1,540 kVA   →  Oct 2025: 1,650 kVA
May 2025: 1,480 kVA   →  Nov 2025: 1,720 kVA
Jun 2025: 1,510 kVA   →  Dec 2025: 1,780 kVA
Jul 2025: 1,560 kVA   →  Jan 2026: 1,850 kVA ← highest
Aug 2025: 1,530 kVA   →  Feb 2026: 1,760 kVA
```

### 2. Ratchet Calculation

```
trailing_months = history[-11:]           # last 11 months (exclude current)
ratchet_kva     = max(trailing peaks)     # highest of trailing 11 months
billing_kva     = max(current_peak, ratchet_kva)
```

### 3. Shaving Target

The goal is to **keep the current month's peak at or below the existing ratchet** to avoid resetting it higher:

```
shaving_target_kva = ratchet_kva                    # if ratchet exists
shaving_target_kva = NMD_limit_kva × 0.85           # if no ratchet yet (first year)
headroom_kva      = shaving_target_kva - current_peak
```

### 4. Spike Cost

If current peak exceeds the shaving target, the additional monthly cost is:

```
spike_cost_r = (current_peak - shaving_target) × demand_charge_rate
```

This quantifies the financial impact of not shaving.

### 5. Ratchet Expiry

The ratchet expires 12 months after the month that set it. Found by locating the trailing month whose peak equals `ratchet_kva`, then adding 12 months.

## Integration Points

| Service | Usage |
|---------|-------|
| `peak_demand.py` API | Returns ratchet status in demand status endpoint |
| `demand_aware_coordinator.py` | Uses ratchet target to inform shaving urgency |
| `solar_demand_service.py` | BESS discharge targets reference ratchet threshold |

## Key Constants

| Constant | Value | Description |
|----------|-------|-------------|
| `RATCHET_WINDOW_MONTHS` | 12 | Standard SA municipal ratchet window |
| Default shaving target (no ratchet) | `NMD × 0.85` | Conservative first-year target |

## Example

For site-002 (NMD = 1,820 kVA) in March 2026:
- Current month peak: 1,730 kVA
- Trailing 11-month ratchet: **1,850 kVA** (Jan 2026)
- Billing demand: `max(1,730, 1,850)` = **1,850 kVA**
- Ratchet active: **Yes** (1,850 > 1,730)
- Shaving target: **1,850 kVA** (defend below ratchet)
- Headroom: 1,850 - 1,730 = **120 kVA**
- Spike cost: 0 (within target)

If current peak hit 1,900 kVA:
- New billing demand: **1,900 kVA** (ratchet resets higher)
- Spike cost: (1,900 - 1,850) × demand_charge_rate
- Ratchet expiry extends another 12 months from Mar 2026
