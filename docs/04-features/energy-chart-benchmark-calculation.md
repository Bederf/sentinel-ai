---
title: "EnergyChart Benchmark Calculation"
type: "reference"
status: "approved"
version: "1.0.0"
created: "2026-05-17"
updated: "2026-05-17"
tags: ["energy", "benchmark", "eui", "dashboard"]
domain: "frontend"
audience: "developers"
complexity: "intermediate"
estimated_read_time: 5
---

# EnergyChart Benchmark Calculation

## Overview

The EnergyChart component displays an energy efficiency benchmark badge that compares site consumption against South African commercial office standards.

## Calculation Methodology

### Formula

```
kWh/m²/month = (total_kWh / days) × 30 / floor_area_m²
```

### Site-Specific Values

| Site | Floor Area (GLA) | Source |
|------|-----------------|--------|
| S002 | 5,400 m² | Building metadata |

**Note:** GLA (Gross Lettable Area) is used, not gross building area. This is the occupied/usable space.

### SA Commercial Office Benchmarks

| Rating | Annual (kWh/m²/yr) | Monthly (kWh/m²/mo) | Source |
|--------|-------------------|---------------------|--------|
| Efficient | 120 | 10.0 | Green Star 5-6★ office |
| Typical | 170 | 14.2 | SANS 10400-XA compliant baseline |
| Poor | 230 | 19.2 | Pre-2011 stock |

**Reference:** GBCSA Green Star SA, SANS 10400-XA Energy Usage in Buildings

### Example Calculation (S002)

Given:
- 30-day consumption: 43,157 kWh
- Floor area: 5,400 m²

```
Monthly kWh = 43,157 kWh
kWh/m²/month = 43,157 / 5,400 = 7.99 kWh/m²/month

Classification: Efficient (≤ 10.0 kWh/m²/month)
```

## Frontend Implementation

**File:** `frontend/src/components/EnergyChart.tsx`

```typescript
// Lines 227-237
const BENCHMARK_EFFICIENT = 10.0  // 120/12
const BENCHMARK_TYPICAL = 14.2    // 170/12
const BENCHMARK_POOR = 19.2       // 230/12

const areaSqm = 5400 // S002 GLA (not gross building area)
```

## Important Notes

1. **Annual vs Monthly:** Always convert annual benchmarks to monthly by dividing by 12. Comparing monthly consumption against annual thresholds is a units mismatch error.

2. **GLA vs Gross Area:** Use Gross Lettable Area (occupied space), not total building footprint. For S002: 5,400 m² GLA.

3. **Sandton Context:** High HVAC loads are expected due to glass curtain wall exposure. 77% HVAC load at 35% occupancy indicates oversupply opportunity.

4. **TODO:** Pull site-specific floor area from building metadata API rather than hardcoding.

## Validation

If the badge shows unexpected values:

1. Check `grandTotal` (kWh consumed)
2. Check `days` (period length)
3. Verify `areaSqm` matches building GLA
4. Confirm thresholds are monthly (not annual)

## Client Conversation

**Peter Marshall asks:** "Is 8 kWh/m²/month good?"

**Response:** "Yes — that's Green Star efficient territory. But with 35% occupancy and 77% HVAC load, we're cooling 300 seats for 106 people. That's a 65% oversupply opportunity SENTINEL will surface once optimisation credits are restored."
