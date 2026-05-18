---
title: "Dashboard Energy Intensity Badge"
type: "reference"
status: "approved"
version: "1.1.0"
created: "2026-05-17"
updated: "2026-05-17"
tags: ["energy", "benchmark", "eui", "dashboard"]
domain: "frontend"
audience: "developers"
complexity: "intermediate"
estimated_read_time: 5
---

# Dashboard Energy Intensity Badge

## Overview

The Dashboard Energy Analytics panel displays an energy efficiency badge that compares site consumption against South African commercial office standards. The badge shows annual energy intensity (kWh/m²/year) with classification.

## Calculation Methodology

### Formula

```
Annual Energy Intensity (kWh/m²/yr) = (total_kWh / days) × 365 / floor_area_m²
```

Where:
- `total_kWh`: Sum of energy consumption over the period
- `days`: Number of days in the data series
- `floor_area_m²`: Site floor area from `sites.sqm` field

### Site-Specific Values

| Site | Floor Area | Desks | Area per Desk | Source |
|------|-----------|-------|---------------|--------|
| S002 | 9,000 m² | 300 | 30 m²/desk | Building config (includes circulation, meeting rooms, common areas) |

**Note:** 30 m² per desk includes circulation, meeting rooms, and common areas — not just workstation footprint.

### SA Commercial Office Benchmarks (Annual)

| Rating | Annual kWh/m²/yr | Source |
|--------|------------------|--------|
| Efficient | < 120 | Green Star SA 5-6★ office |
| Typical | 120-170 | SANS 10400-XA compliant baseline |
| High | > 170 | Pre-2011 stock / inefficient |

**Reference:** GBCSA Green Star SA, SANS 10400-XA Energy Usage in Buildings

### Example Calculation (S002)

Given:
- Annual consumption: 823,970 kWh/year
- Floor area: 9,000 m²

```
Annual Energy Intensity = 823,970 kWh/yr ÷ 9,000 m² = 91.5 kWh/m²/yr

Classification: Efficient (< 120 kWh/m²/yr)
```

**Note:** The calculation uses annual intensity to align with industry-standard benchmarks. Monthly comparisons against annual thresholds caused a 12x classification error in earlier versions.

## Frontend Implementation

**File:** `frontend/src/components/Dashboard.tsx` (Energy Analytics panel header)

```typescript
// Lines 337-357
const energyIntensity = useMemo(() => {
  if (!energyData.length) return null;
  const totalKwh = energyData.reduce((sum, d) => sum + (d.total_kwh || 0), 0);
  const days = energyData.length;
  const dailyKwh = days > 0 ? totalKwh / days : 0;

  // Get sqm from selected site or sum of all sites
  let totalSqm = 0;
  if (energyFilterSiteId) {
    const site = buildingsList.find((s: Site) => s.id === energyFilterSiteId);
    totalSqm = site?.sqm || 5000; // fallback
  } else {
    totalSqm = buildingsList.reduce((sum: number, s: Site) => sum + (s.sqm || 0), 0) || 5000;
  }

  const annualKwh = dailyKwh * 365;
  const intensity = totalSqm > 0 ? (annualKwh / totalSqm) : 0;

  // SA office benchmarks (annual kWh/m²): efficient < 120, typical < 170
  const classification = intensity < 120 ? 'Efficient' : intensity < 170 ? 'Typical' : 'High';
  const classificationColor = intensity < 120 ? 'var(--color-sentinel-green)' : intensity < 170 ? 'var(--color-sentinel-amber)' : 'var(--color-sentinel-red)';

  return { intensity: Math.round(intensity), classification, classificationColor };
}, [energyData, energyFilterSiteId, buildingsList]);
```

## Important Notes

1. **Annual vs Monthly:** The calculation uses annual energy intensity (kWh/m²/year) to align with industry-standard benchmarks (Green Star SA, SANS 10400-XA). Earlier versions incorrectly compared monthly consumption against annual thresholds.

2. **Floor Area Source:** Floor area is pulled from `sites.sqm` in the database. For S002, this is 9,000 m² including circulation, meeting rooms, and common areas (30 m² per desk × 300 desks).

3. **Sandton Context:** High HVAC loads are expected due to glass curtain wall exposure. 77% HVAC load at 35% occupancy indicates oversupply opportunity.

4. **Data Freshness:** The badge appears alongside a timestamp showing data freshness ("Just now", "2 min ago", etc.) to prevent stale data from appearing live.

## Validation

If the badge shows unexpected values:

1. Check `totalKwh` (sum of energy data points)
2. Check `days` (period length in data series)
3. Verify `totalSqm` from `buildingsList` matches actual floor area
4. Confirm calculation uses annual formula: `(dailyKwh * 365) / sqm`
5. Verify benchmarks are annual thresholds: 120/170 kWh/m²/yr

## Client Conversation

**Question:** "Is 91 kWh/m²/year good for an office building?"

**Response:** "Yes — that's Green Star efficient territory (< 120 kWh/m²/yr). For context, SANS 10400-XA baseline is 170 kWh/m²/yr, so you're running 47% more efficient than code-minimum. The badge classification is based on annual energy intensity aligned with SA commercial office benchmarks."
