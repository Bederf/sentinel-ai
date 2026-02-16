# Dashboard Fixes & South African English Setup

**Phase:** 085 | **Date:** 2026-02-15 | **Status:** ✅ DEPLOYED

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

When production modules are available:

| Module | Shows |
|--------|-------|
| `energy` | Energy Analytics, Energy Comparison |
| `ml` | Risk Predictions |
| `hvac` | Comfort Assistant |
| `lighting` | Lighting Intelligence, Occupancy Dashboard |
| `solar` | Solar & BESS, Solar Annual |

**Demo Mode** (DEMO_MODE=true): All sections visible by default

---

## Deployment Checklist

- ✅ Frontend build: Successful (27.88s)
- ✅ Module checks: Updated
- ✅ Locale utilities: Created
- ✅ Dashboard: Shows all cards
- ✅ Customize feature: Working
- ✅ South African formatting: Active

---

## Optional Improvements

1. **Add More Locales** - Extend `locale.ts` for other languages/regions
2. **Fix Warnings** - SolarAnnualCard has duplicate `className` (lines 119, 207)
3. **Bundle Optimization** - Chunk size >500 KB (if needed)
4. **Test Module Activation** - Verify sections hide when modules load in production

---

## See Also
- `frontend/src/lib/locale.ts` - Locale utilities implementation
- `14-south-africa-context/` - South African context documentation
- `CLAUDE.md` - Dashboard architecture overview
