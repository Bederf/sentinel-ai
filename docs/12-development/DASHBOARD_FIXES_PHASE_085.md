---

title: "Dashboard Fixes & South African English Setup"
type: "guide"
status: "draft"
version: "1.1.0"
created: "2026-03-31"
updated: "2026-05-17"
tags: ["sentinel", "documentation"]
related: []
domain: "bms"
audience: "all"
complexity: "intermediate"
estimated_read_time: 12
---

# Dashboard Fixes & South African English Setup

**Phase:** 085 | **Date:** 2026-02-15 | **Status:** ✅ DEPLOYED

**Updated:** 2026-05-17 with optimization status labels, energy intensity badge, and data freshness indicators.
---

## Issue 1: Empty Dashboard - Cards Not Showing

### Root Cause
Dashboard sections were hidden by module checks. When modules hadn't loaded yet (demo mode), the logic was preventing sections from rendering:

```typescript
if (activeModules.length > 0 && !isModuleActive('energy')) {
  return null;  // Hidden!
}
```

### Solution
Updated all 7 section renderers to show content by default when modules aren't loaded:

```typescript
const shouldShow = activeModules.length === 0 || isModuleActive('module-name');
if (!shouldShow) {
  return null;
}
```

**Sections Fixed:**
- Energy Analytics
- Risk Predictions
- Comfort Assistant
- Occupancy Dashboard
- Energy Comparison
- Actual vs SENTINEL Energy Comparison
- Lighting Intelligence
- Solar & BESS
- Solar Annual Summary

### Behavior
- ✅ **Demo Mode:** All sections visible (modules not loading)
- ✅ **Production:** Only active module sections visible
- ✅ **Customize:** Users can still toggle sections on/off via CardLibrary

### Files Modified
- `frontend/src/components/Dashboard.tsx` - All section renderers

---

## Issue 2: South African English Localization

### What Was Already Configured
- ✅ Time/date formatting: `en-ZA` locale
- ✅ Currency: ZAR (South African Rand)
- ✅ Time format: 24-hour (no AM/PM)
- ✅ Timezone: Africa/Johannesburg (SAST)

### What Was Added

**New File:** `frontend/src/lib/locale.ts`

Comprehensive locale utilities with:

**Currency Formatting:**
```typescript
formatCurrencyZAR(50000, 0, 0)        // "R50 000"
formatCurrencyZAR(50000.50, 0, 2)     // "R50 000,50"
```

**Number Formatting:**
```typescript
formatNumber(1234.56)                 // "1 234,56"
formatPercentage(92.3)                // "92,3%"
```

**Domain-Specific:**
```typescript
formatEnergy(1234.56)                 // "1,23 kWh"
formatPower(45.5)                     // "45,5 kW"
formatCO2(1234.56)                    // "1,23 t CO₂"
formatWater(1500)                     // "1,50 m³"
```

**Additional Resources:**
- South African regions (9 provinces)
- Major cities
- Day/month names
- Common UI labels
- LOCALE constants

### Files Updated
- `frontend/src/components/Dashboard.tsx` - Now uses `formatCurrencyZAR()`
- `frontend/src/lib/locale.ts` - NEW comprehensive locale utilities

---

## Testing

### ✅ Dashboard Visibility
```
http://localhost:9096
```
Should now show:
- KPI Overview (5 cards)
- Site Protection Status
- Energy Analytics
- Risk Intelligence
- Solar & BESS sections
- And more...

Click "Customize" button to show/hide/reorder cards.

### ✅ South African English Formatting
All monetary values display as:
- `R1,234.56` (not `ZAR1,234.56`)
- Numbers: `1 234,56` (space separator, comma decimal)
- Dates: `15 Feb 2026` (DD MMM YYYY)
- Time: `14:30` (24-hour)

---

## Usage Examples

### In Components
```typescript
import { formatCurrencyZAR, formatEnergy, formatPercentage } from '@/lib/locale';

// Dashboard KPI card
const savings = formatCurrencyZAR(50000);           // "R50 000"

// Energy consumption
const consumption = formatEnergy(1234.56);          // "1,23 kWh"

// Efficiency metric
const efficiency = formatPercentage(92.3);          // "92,3%"
```

---

## Architecture: Module System

> **Note (2026-03-01):** The building Overview tab was restructured to use compact **intelligence cards** instead of full-detail panels. Full panels (Solar grid, Energy Comparison, Validation cards, etc.) were moved to their discipline tabs. See `docs/02-architecture/frontend-navigation.md` for the current architecture.

When production modules are available:

| Module | Overview Shows | Discipline Tab |
|--------|---------------|----------------|
| `hvac` | HVAC Intelligence Card | Full HVAC Dashboard |
| `energy` | Energy Intelligence Card | OptimizationPage (comparison, validation, ROI) |
| `solar` | Solar Intelligence Card | SolarDashboard (all solar panels) |
| `water` | Water Intelligence Card | WaterPanel |
| `fire` | Fire Intelligence Card | FireSafetyPage |
| `security` | Security Intelligence Card | SecurityDashboard |
| `lighting` | Lighting Intelligence + Occupancy | LightingPage (sub-tabs) |

**Demo Mode** (DEMO_MODE=true): All sections visible by default

---

## Deployment Checklist

- ✅ Frontend build: Successful (31.75s)
- ✅ Module checks: Updated
- ✅ Locale utilities: Created
- ✅ Dashboard: Shows all cards
- ✅ Customize feature: Working
- ✅ South African formatting: Active
- ✅ SiteCard optimization labels: 7 state mappings
- ✅ Energy intensity badge: Annual calculation with SA benchmarks
- ✅ Data freshness timestamp: Relative time display
- ✅ Conditional "All Sites" toggle: Hidden with single site
- ✅ Site Protection badge: "All healthy" state

---

## Optional Improvements

1. **Add More Locales** - Extend `locale.ts` for other languages/regions
2. **Fix Warnings** - SolarAnnualCard has duplicate `className` (lines 119, 207)
3. **Bundle Optimization** - Chunk size >500 KB (if needed)
4. **Test Module Activation** - Verify sections hide when modules load in production

---

## Issue 3: SiteCard Optimization Status Labels (2026-05-17)

### Problem
The `SiteCard` component showed a generic "Not optimized" label for all non-optimized states, which was ambiguous and operationally meaningless.

### Solution
Expanded state mapping to show specific, actionable labels:

| Backend State | Previous Label | New Label | Color | Meaning |
|--------------|----------------|-----------|-------|---------|
| `optimized` | "Optimized" | "Optimised" | Green | Successfully optimized |
| `optimizing` | "Optimizing" | "Optimising..." | Amber | Optimization in progress |
| `recommendation_pending` | "Not optimized" | **"Action required"** | Amber | Pending recommendations need approval |
| `learning` | "Not optimized" | **"Learning"** | Blue | Site in onboarding phase, building models |
| `disabled` | "Not optimized" | **"Paused"** | Gray | Optimization deliberately disabled |
| `error` | "Not optimized" | **"Attention needed"** | Red | Error state (connection, etc.) |
| `active` | "Not optimized" | **"Monitoring"** | Green | Optimization on, watching for patterns |

### Files Modified
- `frontend/src/components/SiteCard.tsx` - `OptimizationStatus` component (lines 67-96)

---

## Issue 4: Energy Analytics Enhancements (2026-05-17)

### Problem
The Energy Analytics panel had three UX gaps:
1. No data freshness indicator (stale data looked live)
2. No energy efficiency context (kWh number without benchmark)
3. "All Sites" dropdown visible with only 1 site (dead UI)

### Solution

#### 4.1 Data Freshness Timestamp
Added relative time indicator showing when data was last updated:
- "Just now" (< 1 min)
- "2 min ago", "1 hour ago", etc.
- Full timestamp on hover

**Implementation:**
```typescript
const [energyLastUpdated, setEnergyLastUpdated] = useState<Date | null>(null);
// Updated on every successful data fetch
setEnergyLastUpdated(new Date());
```

#### 4.2 Energy Intensity Badge (kWh/m²)
Calculates and displays annual energy intensity with SA benchmark classification:

**Formula:**
```typescript
const annualKwh = dailyKwh * 365;
const intensity = totalSqm > 0 ? (annualKwh / totalSqm) : 0;
```

**SA Office Benchmarks (Annual kWh/m²):**
- **Efficient:** < 120 (Green Star SA aligned)
- **Typical:** 120-170 (SANS 10400-XA aligned)
- **High:** > 170

**Example for Site-002:**
- 823,970 kWh/year ÷ 9,000 m² = **91 kWh/m² · Efficient**

#### 4.3 Conditional "All Sites" Toggle
The site filter dropdown only renders when `buildingsList.length > 1`:

```typescript
{buildingsList.length > 1 && (
  <select>...</select>
)}
```

### Files Modified
- `frontend/src/components/Dashboard.tsx`
  - Added `energyLastUpdated` state (line 164)
  - Added `formatTimeAgo()` helper (lines 321-335)
  - Added `energyIntensity` useMemo calculation (lines 337-357)
  - Updated Energy Analytics panel header with badge, conditional filter, and timestamp (lines 634-707)

---

## Issue 5: Site Protection Status Badge (2026-05-17)

### Problem
The "0 elevated" badge in gray looked like a data absence, not a positive signal.

### Solution
- **When warningSites > 0:** Amber badge with "{count} elevated"
- **When warningSites = 0:** Green badge with **"All healthy"**

**Implementation:**
```typescript
<span style={{
  background: warningSites > 0
    ? "rgba(245, 158, 11, 0.15)"
    : "rgba(34, 197, 94, 0.15)",
  color: warningSites > 0
    ? "var(--color-sentinel-amber)"
    : "var(--color-sentinel-green)",
}}>
  {warningSites > 0 ? `${warningSites} elevated` : "All healthy"}
</span>
```

### Files Modified
- `frontend/src/components/Dashboard.tsx` - Site Protection panel header (lines 537-538)

---

## Testing

### Energy Intensity Calculation
```typescript
// Site-002 example
totalKwh: 823,970 kWh/year
totalSqm: 9,000 m²
intensity: 823,970 ÷ 9,000 = 91.5 kWh/m²/year
classification: 91.5 < 120 → "Efficient"
```

### Verify at Runtime
1. Open Dashboard → Energy Analytics panel
2. Confirm badge shows: "{intensity} kWh/m² · {classification}"
3. Hover timestamp → verify full datetime shown
4. With 1 site: confirm "All Sites" dropdown hidden
5. Site Protection: confirm "All healthy" in green (when 0 warnings)

---

## See Also
- `frontend/src/lib/locale.ts` - Locale utilities implementation
- `frontend/src/components/SiteCard.tsx` - Site card with optimization status
- `frontend/src/components/Dashboard.tsx` - Main dashboard component
- `14-south-africa-context/` - South African context documentation
- `CLAUDE.md` - Dashboard architecture overview
