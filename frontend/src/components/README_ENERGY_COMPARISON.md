# ActualVsSentinelEnergyCard Component

## Overview

The `ActualVsSentinelEnergyCard` component displays a side-by-side comparison of actual energy consumption vs AI-optimized SENTINEL predictions for a building site.

**Features:**
- ✅ 2-column layout: Actual (left) vs SENTINEL (right)
- ✅ System breakdown: HVAC, Lighting, Power with percentages
- ✅ Primary metrics: Total kWh, Cost (R/day), Carbon (kg CO₂)
- ✅ Comparison band: Daily savings, progress to target, AI confidence
- ✅ Auto-refresh every 30 seconds
- ✅ Loading states with skeleton
- ✅ Error handling with fallback

## Usage

### Basic Usage

```tsx
import { ActualVsSentinelEnergyCard } from '@/components/ActualVsSentinelEnergyCard'

export function Dashboard() {
  return (
    <ActualVsSentinelEnergyCard siteId="site-002" />
  )
}
```

### Props

```typescript
interface ActualVsSentinelEnergyCardProps {
  siteId: string  // Required: Site identifier (e.g., "site-002", "site-005")
}
```

## API Requirements

The component expects three backend endpoints to be implemented:

### 1. GET `/api/energy/comparison-summary`

Returns a complete comparison of actual vs SENTINEL predictions.

**Query Parameters:**
- `site_id` (string): Site identifier

**Response:**
```json
{
  "actual": {
    "total_kwh": 2450,
    "total_cost_zar": 12250,
    "carbon_kg": 892,
    "hvac_kwh": 1200,
    "hvac_percent": 49,
    "lighting_kwh": 850,
    "lighting_percent": 35,
    "power_kwh": 400,
    "power_percent": 16,
    "timestamp": "2026-02-15T10:30:00Z"
  },
  "sentinel": {
    "total_kwh": 1980,
    "total_cost_zar": 9900,
    "carbon_kg": 720,
    "hvac_kwh": 950,
    "hvac_percent": 48,
    "lighting_kwh": 650,
    "lighting_percent": 33,
    "power_kwh": 380,
    "power_percent": 19,
    "timestamp": "2026-02-15T10:30:00Z"
  },
  "daily_savings_zar": 2350,
  "daily_savings_percent": 19.2,
  "progress_to_target_percent": 80,
  "ai_confidence_percent": 92
}
```

### 2. GET `/api/energy/actual` (Optional)

Returns detailed actual energy data for a period.

**Query Parameters:**
- `site_id` (string): Site identifier
- `days` (integer, optional): Number of days to retrieve (default: 30)

**Response:**
```json
{
  "site_id": "site-002",
  "period_days": 30,
  "period_start": "2026-01-16",
  "period_end": "2026-02-15",
  "metrics": [
    {
      "total_kwh": 2450,
      "total_cost_zar": 12250,
      "carbon_kg": 892,
      "hvac_kwh": 1200,
      "hvac_percent": 49,
      "lighting_kwh": 850,
      "lighting_percent": 35,
      "power_kwh": 400,
      "power_percent": 16,
      "timestamp": "2026-02-15T10:30:00Z"
    }
    // ... more data points
  ]
}
```

### 3. GET `/api/energy/prediction` (Optional)

Returns SENTINEL AI predicted energy data.

**Query Parameters:**
- `site_id` (string): Site identifier
- `scenario` (string): One of `sentinel_optimized`, `standard_ems`, `baseline`
- `days` (integer, optional): Number of days (default: 30)

**Response:** Same structure as `/api/energy/actual`

## API Client Usage

Use the energy API client module for type-safe API calls:

```tsx
import {
  fetchEnergyComparisonSummary,
  fetchEnergyActual,
  fetchEnergyPrediction,
  calculateSavingsPercent,
  calculateCarbonOffset,
} from '@/lib/api/energy'

// Fetch comparison summary (main use case)
const comparison = await fetchEnergyComparisonSummary('site-002')

// Fetch individual datasets
const actual = await fetchEnergyActual('site-002', 30)
const prediction = await fetchEnergyPrediction('site-002', 'sentinel_optimized', 30)

// Calculate derived metrics
const savingsPercent = calculateSavingsPercent(2450, 1980)  // 19.2%
const carbonOffset = calculateCarbonOffset(470)  // kg CO₂ saved
```

## Component Styling

The component uses CSS variables for theme consistency:

```css
--color-sentinel-bg-panel        /* Main panel background */
--color-sentinel-bg-secondary    /* Secondary/section background */
--color-sentinel-border          /* Border color */
--color-sentinel-text-primary    /* Primary text */
--color-sentinel-text-secondary  /* Secondary text */
--color-sentinel-text-disabled   /* Disabled text */
--color-sentinel-green           /* Success/positive (SENTINEL color) */
--color-sentinel-blue            /* Primary action (HVAC) */
--color-sentinel-amber           /* Warning (Lighting) */
--color-sentinel-red             /* Danger (Power) */
```

## Integration Points

### On Dashboard (Main View)
```tsx
import { ActualVsSentinelEnergyCard } from '@/components/ActualVsSentinelEnergyCard'

export function Dashboard() {
  return (
    <div className="grid grid-cols-1 gap-4">
      <ActualVsSentinelEnergyCard siteId={selectedSiteId} />
      {/* Other dashboard components */}
    </div>
  )
}
```

### On SolarDashboard (Energy-Focused View)
```tsx
// In SolarDashboard.tsx, add as Row 0
<div className="grid grid-cols-1 gap-4 mb-4">
  <ActualVsSentinelEnergyCard siteId={selectedSiteId} />
</div>
```

### On SiteDetail (Per-Site Analysis)
```tsx
// Create expandable section
<div className="space-y-4">
  <button onClick={() => setShowEnergyComparison(!showEnergyComparison)}>
    Energy Comparison
  </button>
  {showEnergyComparison && (
    <ActualVsSentinelEnergyCard siteId={siteId} />
  )}
</div>
```

## Data Flow

```
Component Mount
    ↓
useEffect: fetchEnergyComparisonSummary()
    ↓
Try API: GET /api/energy/comparison-summary?site_id=X
    ↓
Success? → Render comparison
    ↓
Error? → Show error state / Return mock data for demo
    ↓
Auto-refresh every 30 seconds
```

## Responsive Behavior

- **Desktop (≥768px):** 2-column grid (Actual | SENTINEL side-by-side)
- **Mobile (<768px):** Stacks vertically (Actual top, SENTINEL below)

This is controlled by Tailwind's `md:` breakpoint in grid classes.

## Loading States

1. **Initial Load:** Skeleton loader with placeholder boxes
2. **Error:** Icon + error message with fallback to mock data
3. **Success:** Full component with data

## Auto-Refresh

The component fetches fresh data every 30 seconds using `setInterval`. The interval is cleaned up on unmount.

To adjust refresh rate, modify the interval in the `useEffect`:
```tsx
const interval = setInterval(loadData, 15000)  // 15 seconds instead
```

## Mock Data

For development without backend APIs, the component includes mock data:

```typescript
{
  actual: { total_kwh: 2450, total_cost_zar: 12250, ... },
  sentinel: { total_kwh: 1980, total_cost_zar: 9900, ... },
  daily_savings_zar: 2350,
  daily_savings_percent: 19.2,
  progress_to_target_percent: 80,
  ai_confidence_percent: 92,
}
```

This allows the component to render and be tested before backend APIs are ready.

## Future Enhancements

1. **24-hour trend chart:** Add mini stacked line chart showing hourly comparison
2. **System-level deep dive:** Click system to see HVAC/Lighting/Power optimization details
3. **Historical comparison:** Toggle between daily/weekly/monthly views
4. **Custom targets:** Allow users to set energy reduction targets
5. **Export data:** Download comparison as CSV/PDF

## Related Components

- `SolarAnnualCard` - Annual solar simulation comparison
- `BESSStatusPanel` - Battery storage monitoring (pattern reference)
- `EnergyChart` - Historical energy consumption visualization
- `EnergyComparisonPanel` - Lighting-only demo (legacy)

## Testing

```tsx
import { render, screen, waitFor } from '@testing-library/react'
import { ActualVsSentinelEnergyCard } from '@/components/ActualVsSentinelEnergyCard'

describe('ActualVsSentinelEnergyCard', () => {
  it('renders loading state', () => {
    render(<ActualVsSentinelEnergyCard siteId="site-002" />)
    expect(screen.getByText(/actual/i)).toBeInTheDocument()
  })

  it('displays comparison data', async () => {
    render(<ActualVsSentinelEnergyCard siteId="site-002" />)
    await waitFor(() => {
      expect(screen.getByText('2450')).toBeInTheDocument() // Actual kWh
      expect(screen.getByText('1980')).toBeInTheDocument() // SENTINEL kWh
    })
  })

  it('shows savings in comparison band', async () => {
    render(<ActualVsSentinelEnergyCard siteId="site-002" />)
    await waitFor(() => {
      expect(screen.getByText(/19.2%/)).toBeInTheDocument()
      expect(screen.getByText(/2350/)).toBeInTheDocument()
    })
  })
})
```

## Troubleshooting

**Component not rendering:**
- Check `siteId` prop is provided
- Check CSS variables are defined in theme
- Check API endpoint returns correct structure

**Data not updating:**
- Check browser console for fetch errors
- Verify API endpoint is accessible
- Check CORS headers if API is remote

**Styling issues:**
- Verify Sentinel theme colors are loaded
- Check Tailwind CSS is compiled
- Verify responsive breakpoints match your layout

## Support

For issues or enhancements, refer to:
- Pattern reference: `BESSStatusPanel.tsx` (solar/BESS monitoring pattern)
- API client: `frontend/src/lib/api/energy.ts`
- Integration: See "Integration Points" section above
