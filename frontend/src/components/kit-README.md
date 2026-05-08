# SENTINEL UI Kit

Shared React components for SENTINEL dark-theme UI. All components use CSS custom properties (`var(--color-sentinel-*)`) for theming — no hardcoded colors.

## Components

| Component | File | Purpose |
|-----------|------|---------|
| `Panel` | `Panel.tsx` | Shared panel container. Background + border + optional header row with icon + title + actions slot. |
| `PageLoading` | `PageLoading.tsx` | Full-page loading spinner. Replaces all ad-hoc spinner divs. |
| `TabBar` | `TabBar.tsx` | Segmented tab switcher. `accentColor` prop sets active tab color. |
| `EmptyState` | `EmptyState.tsx` | Centered empty-state pattern. Icon + title + optional subtext + optional CTA. |
| `StatusBadge` | `StatusBadge.tsx` | Renders a status pill (online/warning/critical/degraded/etc.) with SENTINEL colors. |
| `KPICard` | `KPICard.tsx` | Stat panel card. Value + title + icon + optional delta/trend. Built-in tabular-nums. |
| `ScoreRing` | `ScoreRing.tsx` | Circular score indicator with ring + percentage display. Built-in tabular-nums. |

## Usage

```tsx
import { Panel } from './Panel';
import { EmptyState } from './EmptyState';
import { StatusBadge } from './StatusBadge';
import { KPICard } from './KPICard';
```

## Panel

```tsx
<Panel
  header={{
    icon: <Building2 className="h-5 w-5" />,
    title: "Site Protection Status",
    actions: <button>Refresh</button>,
    accentColor: "var(--color-sentinel-blue)",
  }}
>
  content
</Panel>
```

## EmptyState

```tsx
<EmptyState
  icon={Building2}
  title="No sites available"
  subtext="Sites will appear here once connected."
  cta={<button>Add Site</button>}
/>
```

## StatusBadge

```tsx
<StatusBadge status="online" label="Monitoring" />
// status: "online" | "warning" | "critical" | "degraded" | "offline" | "unknown"
```

## KPICard

```tsx
<KPICard
  title="Protected Sites"
  value={42}
  icon={<Building2 className="h-4 w-4" />}
  accentColor="blue"
  delta={3}
  deltaText="vs last week"
  tooltip="Total buildings under SENTINEL monitoring"
/>
```

## Typography Rules

- All numeric displays (currency, percentages, counts) must use `fontVariantNumeric: "tabular-nums"` inline style.
- IDs, codes, timestamps — prefer monospace font where visual clarity matters.
- Use SENTINEL CSS variables, never hardcoded hex/RGB.

## Color Variables

```css
--color-sentinel-bg-canvas      /* page background */
--color-sentinel-bg-panel       /* panel/card background */
--color-sentinel-bg-secondary    /* input/secondary background */
--color-sentinel-border          /* borders */
--color-sentinel-text-primary    /* primary text */
--color-sentinel-text-secondary  /* muted text */
--color-sentinel-text-disabled   /* disabled text */
--color-sentinel-blue            /* primary accent */
--color-sentinel-amber            /* warning/elevated accent */
--color-sentinel-green            /* success/positive */
--color-sentinel-red              /* error/critical */
```
