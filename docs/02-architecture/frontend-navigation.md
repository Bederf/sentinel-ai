---
title: "Frontend Navigation Architecture"
type: "architecture"
status: "approved"
version: "2.0.0"
created: "2026-02-23"
updated: "2026-02-28"
author: "Sentinel Development Team"
tags: ["frontend", "navigation", "sidebar", "tabs", "modules", "lazy-loading"]
related: ["system-overview.md", "module-system.md"]
domain: "general"
audience: "developers"
complexity: "intermediate"
estimated_read_time: 8
---

# Frontend Navigation Architecture

Two-level navigation system: a global sidebar (10 items) for platform-level views and a discipline-specific tab bar (10 tabs) inside the building detail page for site-specific views.

## Design Principles

1. **Sidebar is global**: Platform-level items that apply regardless of which site is selected.
2. **Building tabs are contextual**: All site-specific discipline views are accessible from the building detail page.
3. **SIMBIOT-data-driven**: Building tabs show when SIMBIOT has data for a discipline, not based on module toggles.
4. **Control gating**: Write features within tabs are gated by per-discipline `{x}_control` add-ons.
5. **Lazy-loaded**: Tab components load on demand via `React.lazy()` to keep initial bundle small.

## Sidebar (Global — 10 Items)

The sidebar has 3 groups:

### Always Visible (4)

| Item | Icon | View |
|------|------|------|
| **Dashboard** | LayoutDashboard | `dashboard` |
| **AI Chat** | MessageSquare | `ai-chat` |
| **System Health** | Activity | `integrations` |
| **Logs** | FileText | `logs` |

### Admin Only (2)

| Item | Icon | View | Condition |
|------|------|------|-----------|
| **SIMBIOT** | Plug | `simbiot` | Admin or demo mode |
| **Settings** | Settings | `settings` | Admin or demo mode |

### Conditional Add-ons (4)

| Item | Icon | View | Required Module |
|------|------|------|-----------------|
| **Maintenance** | Wrench | `maintenance` | `maintenance` |
| **Financial** | DollarSign | `financial` | `financial` |
| **Compliance** | Shield | `compliance` | `compliance` |
| **Fleet ML** | Brain | `fleet-ml` | `fleet_ml` |

The sidebar collapses to icons on small screens and supports a mobile hamburger overlay.

**Source:** `frontend/src/lib/navigation.ts` (`BASE_NAV_ITEMS`, `ADMIN_NAV_ITEMS`, `ADDON_NAV_ITEMS`)

## Building Detail Tabs (10 Discipline Tabs)

When a user clicks a site card on the Dashboard, the `SiteDetail` component renders with a tab bar. Overview is always first, followed by discipline-specific tabs.

### Tab Inventory

| Tab | Component | Control Gate | Notes |
|-----|-----------|-------------|-------|
| **Overview** | (inline) | — | KPIs, Equipment, Alerts, Energy, Predictions |
| **HVAC** | `ControlDashboard` | `hvac_control` | Setpoints, scheduling, rules |
| **Energy** | `OptimizationPage` | `energy_control` | Peak shaving, load shedding |
| **Lighting** | Sub-tabs: LightingPage, OccupancyPanel, OccupancyAnalyticsPage, OccupancyEnergyCorrelationPage | `lighting_control` | 4 sub-tabs |
| **Solar & BESS** | Sub-tabs: SolarDashboard, AegisConsolePage | `solar_control` | AEGIS sub-tab only when `solar_control` active |
| **Water** | `WaterPanel` | `water_control` | Valve automation |
| **Fire** | `FireSafetyPage` | None | Always read-only |
| **Security** | `SecurityDashboard` | `security_control` | Door commands, schedules |
| **Digital Twin** | `DigitalTwin` | `digital_twin_control` | Write actions gated |
| **Simulation** | `SimulationDashboard` | — | Only when `simulation` add-on active |

**Source:** `frontend/src/lib/navigation.ts` (`BUILDING_TAB_ITEMS`)

## Tab Filtering

The Simulation tab is hidden when its required module is inactive:

```typescript
BUILDING_TAB_ITEMS
  .filter((tab) => {
    if (tab.requiredModule && !isModuleActive(tab.requiredModule)) return false;
    return true;
  })
```

## Lazy Loading

All tab components except Overview use `React.lazy()` with `<Suspense>` boundaries:

```typescript
const ControlDashboard = lazy(() =>
  import("./ControlDashboard").then(m => ({ default: m.ControlDashboard }))
);
const OptimizationPage = lazy(() =>
  import("../pages/OptimizationPage").then(m => ({ default: m.OptimizationPage }))
);
```

Components with only named exports use the `.then(m => ({ default: m.X }))` wrapper pattern, since `React.lazy()` requires a default export.

## Key Files

| File | Role |
|------|------|
| `frontend/src/lib/navigation.ts` | Navigation config: `BASE_NAV_ITEMS`, `ADMIN_NAV_ITEMS`, `ADDON_NAV_ITEMS`, `BUILDING_TAB_ITEMS` |
| `frontend/src/components/Sidebar.tsx` | Global sidebar (3 groups: base + admin + addon) |
| `frontend/src/components/SiteDetail.tsx` | Building detail page with 10-tab bar and lazy content |
| `frontend/src/App.tsx` | Top-level view routing (10 sidebar views) |

## View Type

The `View` type union in `navigation.ts` has 10 values matching the sidebar items:

```typescript
export type View =
  | 'dashboard' | 'ai-chat' | 'integrations' | 'logs'
  | 'simbiot' | 'settings'
  | 'maintenance' | 'financial' | 'compliance' | 'fleet-ml';
```

Building-specific views (HVAC, Energy, Lighting, etc.) are no longer sidebar `View` values — they live as `BuildingTabId` values within the building detail page.

## Related

- [Module System](module-system.md) — module activation and gating
- [Module Matrix Contract](../13-modules/module-matrix.md) — canonical alignment document
