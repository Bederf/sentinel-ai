---
title: "Frontend Navigation Architecture"
type: "architecture"
status: "approved"
version: "1.0.0"
created: "2026-02-23"
updated: "2026-02-23"
author: "Sentinel Development Team"
tags: ["frontend", "navigation", "sidebar", "tabs", "modules", "lazy-loading"]
related: ["system-overview.md", "module-system.md"]
domain: "general"
audience: "developers"
complexity: "intermediate"
estimated_read_time: 8
---

# Frontend Navigation Architecture

Two-level navigation system: a minimal global sidebar for platform-level views and a scrollable, module-gated tab bar inside the building detail page for site-specific views.

## Design Principles

1. **Sidebar is global**: Only platform-level items that apply regardless of which site is selected.
2. **Building tabs are contextual**: All site-specific views are accessible from the building detail page after clicking a site card.
3. **Module-gated**: Tabs only appear when the corresponding module is active for the selected site.
4. **Lazy-loaded**: Tab components load on demand via `React.lazy()` to keep initial bundle small.

## Sidebar (Global)

The sidebar contains 4 navigation items plus an expandable Info section:

| Item | Icon | Notes |
|------|------|-------|
| **Dashboard** | LayoutDashboard | Default view, always visible |
| **AI Chat** | MessageSquare | Hybrid AI chat interface |
| **SIMBIOT** | Database | Data source browser, always visible |
| **Settings** | Settings | Admin/demo users only |

The sidebar collapses to icons on small screens and supports a mobile hamburger overlay.

**Source:** `frontend/src/lib/navigation.ts` (`BASE_NAV_ITEMS`)

## Building Detail Tabs (Contextual)

When a user clicks a site card on the Dashboard, the `SiteDetail` component renders with a scrollable tab bar. The first tab is "Overview" (the original site detail content), followed by module-gated feature tabs.

### Tab Inventory

| Tab | Component | Module Gate | Notes |
|-----|-----------|-------------|-------|
| **Overview** | (inline) | always | KPIs, Equipment, Alerts, Energy, Predictions |
| System Health | `SystemHealthPage` | always | |
| Control | `ControlDashboard` | `control` | |
| Digital Twin | `DigitalTwin` | always | |
| Audit Logs | `ControlAuditTrail` | always | |
| Tech Chat | `TechnicianPortalGated` | `maintenance` | |
| Loadshedding | `OptimizationPage` | `energy` | |
| Lighting | `LightingPage` | `lighting` | |
| Occupancy | `OccupancyPanel` | `lighting` | |
| Occ. Analytics | `OccupancyAnalyticsPage` | `lighting` | |
| Energy Correlation | `OccupancyEnergyCorrelationPage` | `lighting` | |
| Solar & BESS | `SolarDashboard` | `solar` | |
| AEGIS | `AegisConsolePage` | `solar` | |
| Security | `SecurityDashboard` | `security` | |
| Water | `WaterPanel` | `water` | |
| ESG | `ESGPage` | `sustainability` | |
| Asset Workflow | `AssetWorkflowDashboard` | `assets` | |
| Contracts | `ContractManagementPage` | `contracts` | |
| Profitability | `ProfitabilityDashboardPage` | `contracts` | |
| Budget | `BudgetReportPage` | `contracts` | |
| Fleet ML | `FleetInsights` | `ml` | |
| ML Metrics | `MLMetrics` | `ml` | |
| Simulation | `SimulationDashboard` | `ml` | Admin only |

A typical site with 4-5 active modules shows ~10-12 tabs, not all 23.

**Source:** `frontend/src/lib/navigation.ts` (`BUILDING_TAB_ITEMS`)

## Module Gating

Tabs are filtered at render time using the `useModules()` hook:

```typescript
BUILDING_TAB_ITEMS.filter((tab) => {
  if (tab.requiredModule && !isModuleActive(tab.requiredModule)) return false;
  if (tab.requiredRole === "admin" && userRole !== "admin") return false;
  return true;
})
```

Module types map to the `site_modules` configuration. See [Module System](module-system.md) for details on module activation.

## Lazy Loading

All tab components except Overview use `React.lazy()` with `<Suspense>` boundaries:

```typescript
const SystemHealthPage = lazy(() => import("./SystemHealthPage"));
const ControlDashboard = lazy(() =>
  import("./ControlDashboard").then(m => ({ default: m.ControlDashboard }))
);
```

Components with only named exports use the `.then(m => ({ default: m.X }))` wrapper pattern, since `React.lazy()` requires a default export.

Each lazy tab renders inside its own `<Suspense>` with a loading spinner fallback.

## Key Files

| File | Role |
|------|------|
| `frontend/src/lib/navigation.ts` | Navigation configuration: `BASE_NAV_ITEMS`, `BUILDING_TAB_ITEMS`, types |
| `frontend/src/components/Sidebar.tsx` | Global sidebar component (~350 lines) |
| `frontend/src/components/SiteDetail.tsx` | Building detail page with tab bar and lazy content |
| `frontend/src/App.tsx` | Top-level view routing (fallback paths preserved) |
| `frontend/src/index.css` | `.scrollbar-hide` utility for horizontal tab scroll |

## Scrollable Tab Bar

The tab bar uses `overflow-x-auto` with hidden scrollbar for clean horizontal scrolling:

```css
.scrollbar-hide {
  -ms-overflow-style: none;
  scrollbar-width: none;
}
.scrollbar-hide::-webkit-scrollbar {
  display: none;
}
```

Active tab uses amber highlight (`bg-amber-500/10`, `text-amber-400`, `border-amber-500`). Inactive tabs use subtle hover effects.

## View Type Compatibility

The `View` type union in `navigation.ts` is preserved for backward compatibility with `App.tsx` view routing and `ViewGuard`. Views that moved to building tabs are still valid `View` values -- they're just no longer reachable from the sidebar. This allows gradual cleanup without breaking existing code paths.

## Related

- [Module System](module-system.md) -- module activation and gating
- [System Overview](system-overview.md) -- high-level architecture
