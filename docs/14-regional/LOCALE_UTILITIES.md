---
title: "South African Locale Utilities"
type: "guide"
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

# South African Locale Utilities

**Location:** `frontend/src/lib/locale.ts`
**Status:** ✅ Active (Phase 085+)

---

## Overview

Comprehensive localization for South African English (en-ZA) with formatting utilities for:
- Currency (ZAR - South African Rand)
- Numbers (space separators, comma decimals)
- Energy, power, water, and CO₂ metrics
- Date/time (24-hour format, Africa/Johannesburg timezone)

---

## Quick Reference

### Currency
```typescript
import { formatCurrencyZAR } from '@/lib/locale';

formatCurrencyZAR(50000)              // "R50 000"
formatCurrencyZAR(50000.50, 0, 2)     // "R50 000,50"
formatCurrencyZAR(1234.567, 2, 2)     // "R1 234,57"
```

### Numbers
```typescript
import { formatNumber } from '@/lib/locale';

formatNumber(1234.56)                 // "1 234,56"
formatNumber(1000)                    // "1 000"
formatNumber(99.999, 0, 2)            // "100,00"
```

### Percentages
```typescript
import { formatPercentage } from '@/lib/locale';

formatPercentage(92.3)                // "92,3%"
formatPercentage(100)                 // "100,0%"
formatPercentage(45.678, 2)           // "45,68%"
```

### Energy
```typescript
import { formatEnergy } from '@/lib/locale';

formatEnergy(1234.56)                 // "1,23 kWh"
formatEnergy(1500000)                 // "1,50 MWh"
formatEnergy(500)                     // "500,00 Wh"
```

### Power
```typescript
import { formatPower } from '@/lib/locale';

formatPower(45.5)                     // "45,5 kW"
formatPower(1500)                     // "1,50 MW"
```

### CO₂ Emissions
```typescript
import { formatCO2 } from '@/lib/locale';

formatCO2(1234.56)                    // "1,23 t CO₂"
formatCO2(500)                        // "500,00 kg CO₂"
```

### Water
```typescript
import { formatWater } from '@/lib/locale';

formatWater(1500)                     // "1,50 m³"
formatWater(500)                      // "500 ℓ"
```

---

## Constants

### Locale Settings
```typescript
import { LOCALE } from '@/lib/locale';

LOCALE.code       // "en-ZA"
LOCALE.currency   // "ZAR"
LOCALE.timezone   // "Africa/Johannesburg"
LOCALE.dateFormat // "DD MMM YYYY"
LOCALE.timeFormat // "24h"
```

### South African Regions
```typescript
import { REGIONS } from '@/lib/locale';

REGIONS['Gauteng']         // "Gauteng"
REGIONS['Western Cape']    // "Western Cape"
REGIONS['KwaZulu-Natal']   // "KwaZulu-Natal"
// ... 9 provinces total
```

### Major Cities
```typescript
import { CITIES } from '@/lib/locale';

CITIES['Johannesburg']     // "Johannesburg"
CITIES['Cape Town']        // "Cape Town"
CITIES['Durban']           // "Durban"
// ... 10 major cities
```

### Calendar Names
```typescript
import { DAY_NAMES, MONTH_NAMES } from '@/lib/locale';

DAY_NAMES.short    // ["Sun", "Mon", "Tue", ...]
DAY_NAMES.long     // ["Sunday", "Monday", "Tuesday", ...]

MONTH_NAMES.short  // ["Jan", "Feb", "Mar", ...]
MONTH_NAMES.long   // ["January", "February", "March", ...]
```

### UI Labels
```typescript
import { UI_LABELS } from '@/lib/locale';

UI_LABELS.dashboard        // "Dashboard"
UI_LABELS.consumption      // "Consumption"
UI_LABELS.savings          // "Savings"
UI_LABELS.generation       // "Generation"
// ... 20+ common labels
```

---

## Usage Examples

### Dashboard KPI Card
```typescript
import { formatCurrencyZAR } from '@/lib/locale';

export function PotentialSavingsKPI({ amount }: { amount: number }) {
  return (
    <div>
      <p>Potential Savings</p>
      <p className="text-2xl font-bold">
        {formatCurrencyZAR(amount, 0, 0)}
      </p>
    </div>
  );
}

// Renders as: "R50 000" (not "ZAR50000")
```

### Energy Consumption Card
```typescript
import { formatEnergy } from '@/lib/locale';

export function EnergyMetric({ kwh }: { kwh: number }) {
  return (
    <div>
      <p>Daily Consumption</p>
      <p>{formatEnergy(kwh)}</p>
    </div>
  );
}

// Renders as: "1,23 kWh" or "1,50 MWh"
```

### Sustainability Metrics
```typescript
import { formatCO2 } from '@/lib/locale';

export function CarbonSavings({ kg }: { kg: number }) {
  return (
    <div>
      <p>CO₂ Saved This Year</p>
      <p>{formatCO2(kg)}</p>
    </div>
  );
}

// Renders as: "1,23 t CO₂" or "500,00 kg CO₂"
```

### Water Savings
```typescript
import { formatWater } from '@/lib/locale';

export function WaterUsage({ litres }: { litres: number }) {
  return (
    <p>Water: {formatWater(litres)}</p>
  );
}

// Renders as: "1,50 m³" or "500 ℓ"
```

---

## Function Signatures

```typescript
// Currency formatting
formatCurrencyZAR(
  amount: number,
  minimumFractionDigits?: number,  // default: 0
  maximumFractionDigits?: number   // default: 0
): string

// Number formatting
formatNumber(
  value: number,
  minimumFractionDigits?: number,  // default: 0
  maximumFractionDigits?: number   // default: 2
): string

// Percentage formatting
formatPercentage(
  value: number,
  decimalPlaces?: number           // default: 1
): string

// Metric formatting (auto-scales)
formatEnergy(kwh: number): string      // Wh, kWh, or MWh
formatPower(kw: number): string        // kW or MW
formatCO2(kg: number): string          // kg CO₂ or t CO₂
formatWater(litres: number): string    // ℓ or m³
```

---

## Date & Time

For date/time formatting, use existing utilities:

```typescript
import { formatDate, formatDateTime, formatTime } from '@/lib/timeFormat';

formatDate('2026-02-15')           // "15 Feb 2026"
formatDateTime('2026-02-15T14:30') // "15 Feb 2026, 14:30"
formatTime('2026-02-15T14:30')     // "14:30"
```

All use `en-ZA` locale with Africa/Johannesburg timezone.

---

## Formatting Rules (en-ZA)

| Category | Format | Example |
|----------|--------|---------|
| Currency | R prefix, space 1000s | R1 234,56 |
| Number | Space 1000s, comma decimal | 1 234,56 |
| Percentage | Comma decimal, % suffix | 92,3% |
| Date | DD MMM YYYY | 15 Feb 2026 |
| Time | HH:MM (24h) | 14:30 |
| Energy | Auto-scale (W/kWh/MWh) | 1,23 kWh |
| CO₂ | Auto-scale (kg/t) | 1,23 t CO₂ |

---

## See Also
- `frontend/src/lib/timeFormat.ts` - Date/time utilities (already en-ZA)
- `frontend/src/components/Dashboard.tsx` - Uses locale utilities
- `docs/12-development/DASHBOARD_FIXES_PHASE_085.md` - Implementation notes
