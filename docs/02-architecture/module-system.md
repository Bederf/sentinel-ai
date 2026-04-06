---
title: "SENTINEL Module System"
type: "architecture"
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

# SENTINEL Module System

## Overview

SENTINEL uses a bolt-on module architecture with 27 module types across 4 categories. Every deployment ships with all modules — clients activate or deactivate paid add-ons per site. Base modules (15) are always on. The sidebar and building tabs dynamically reflect which add-ons are active.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    SENTINEL Platform                         │
├─────────────────────────────────────────────────────────────┤
│  Base Platform (7, always on — cannot disable)              │
│  ┌─────┐ ┌────┐ ┌──────────┐ ┌──────────┐ ┌───────┐       │
│  │ KPI │ │ ML │ │ Notifs   │ │ Integr.  │ │SIMBIOT│       │
│  └─────┘ └────┘ └──────────┘ └──────────┘ └───────┘       │
│  ┌─────────┐ ┌────────┐                                    │
│  │ Logging │ │ Assets │                                    │
│  └─────────┘ └────────┘                                    │
├─────────────────────────────────────────────────────────────┤
│  Base Building Systems (8, always on — SIMBIOT-data-driven) │
│  ┌──────┐ ┌────────┐ ┌──────────┐ ┌───────┐ ┌───────┐     │
│  │ HVAC │ │ Energy │ │ Lighting │ │ Solar │ │ Water │     │
│  └──────┘ └────────┘ └──────────┘ └───────┘ └───────┘     │
│  ┌──────┐ ┌──────────┐ ┌──────────────┐                    │
│  │ Fire │ │ Security │ │ Digital Twin │                    │
│  └──────┘ └──────────┘ └──────────────┘                    │
├─────────────────────────────────────────────────────────────┤
│  Control Add-ons (7, per-discipline — gate write features)  │
│  ┌────────────┐ ┌──────────────┐ ┌────────────────┐        │
│  │hvac_control│ │energy_control│ │lighting_control│        │
│  └────────────┘ └──────────────┘ └────────────────┘        │
│  ┌─────────────┐ ┌─────────────┐ ┌────────────────┐        │
│  │solar_control│ │water_control│ │security_control│        │
│  └─────────────┘ └─────────────┘ └────────────────┘        │
│  ┌────────────────────┐                                     │
│  │digital_twin_control│                                     │
│  └────────────────────┘                                     │
├─────────────────────────────────────────────────────────────┤
│  Standalone Add-ons (5, toggleable)                         │
│  ┌─────────────┐ ┌───────────┐ ┌────────────┐              │
│  │ Maintenance │ │ Financial │ │ Compliance │              │
│  └─────────────┘ └───────────┘ └────────────┘              │
│  ┌────────────┐ ┌──────────┐                                │
│  │ Simulation │ │ Fleet ML │                                │
│  └────────────┘ └──────────┘                                │
└─────────────────────────────────────────────────────────────┘
```

## Module Categories

### Base Platform (7, always on)

Cannot be disabled. They are the platform infrastructure.

| Module | Type Key | Description |
|--------|----------|-------------|
| **KPI** | `kpi` | Portfolio & site-level KPI scorecards |
| **ML** | `ml` | AI intelligence — LSTM, Autoencoder, RF, Cox models |
| **Notifications** | `notifications` | Alert delivery (Telegram, email, SMS) |
| **Integrations** | `integrations` | BMS connectivity & health monitoring |
| **SIMBIOT** | `simbiot` | BMS onboarding, auto-discovery, point mapping |
| **Logging** | `logging` | Audit trail, equipment diagnostics, event logs |
| **Assets** | `assets` | Asset lifecycle management, inspections |

### Base Building Systems (8, always on)

Tabs in building detail are SIMBIOT-data-driven — they show when SIMBIOT has data for that discipline, not based on module toggles.

| Module | Type Key | Building Tab | Description |
|--------|----------|-------------|-------------|
| **HVAC** | `hvac` | HVAC | Zone control, AHU monitoring, chiller management |
| **Energy** | `energy` | Energy | Generator/UPS/ATS monitoring, load shedding |
| **Lighting** | `lighting` | Lighting | DALI-2 monitoring, occupancy data layers |
| **Solar** | `solar` | Solar & BESS | PV monitoring, BESS state, generation tracking |
| **Water** | `water` | Water | Consumption monitoring, leak detection |
| **Fire** | `fire` | Fire | Fire safety (always read-only, no control toggle) |
| **Security** | `security` | Security | Access control, CCTV, zone occupancy |
| **Digital Twin** | `digital_twin` | Digital Twin | 3D/2D spatial visualization |

### Control Add-ons (7, toggleable)

Each control add-on gates write features within its discipline's building tab. The tab itself is always visible (monitoring is base); control features inside the tab are hidden when the `{x}_control` add-on is off.

| Module | Type Key | Controls Within Tab |
|--------|----------|---------------------|
| **HVAC Control** | `hvac_control` | Setpoints, scheduling, automation rules |
| **Energy Control** | `energy_control` | Peak shaving, load shedding, generator management |
| **Lighting Control** | `lighting_control` | DALI scenes, daylight harvesting, occupancy automation |
| **Solar Control** | `solar_control` | AEGIS dispatch, BESS arbitrage, load shifting |
| **Water Control** | `water_control` | Valve automation, leak response |
| **Security Control** | `security_control` | Door lock commands, access schedules |
| **Digital Twin Control** | `digital_twin_control` | Write actions from twin interface |

### Standalone Add-ons (5, toggleable)

| Module | Type Key | UI Location | Description |
|--------|----------|-------------|-------------|
| **Maintenance** | `maintenance` | Sidebar item | Work orders, preventive scheduling, tech chat |
| **Financial** | `financial` | Sidebar item | Contracts, profitability, budget, SLA |
| **Compliance** | `compliance` | Sidebar item | Carbon Tax, Green Star, SANS certification, ESG |
| **Simulation** | `simulation` | Building tab | What-if scenarios, ROI modelling |
| **Fleet ML** | `fleet_ml` | Sidebar item | Cross-portfolio analytics, multi-site benchmarking |

## Sidebar Navigation (10 Items)

| Item | View | Condition |
|------|------|-----------|
| Dashboard | `dashboard` | Always visible |
| AI Chat | `ai-chat` | Always visible |
| System Health | `integrations` | Always visible |
| Logs | `logs` | Always visible |
| SIMBIOT | `simbiot` | Admin only |
| Settings | `settings` | Admin only |
| Maintenance | `maintenance` | `maintenance` add-on active |
| Financial | `financial` | `financial` add-on active |
| Compliance | `compliance` | `compliance` add-on active |
| Fleet ML | `fleet-ml` | `fleet_ml` add-on active |

**Source:** `frontend/src/lib/navigation.ts` — `BASE_NAV_ITEMS`, `ADMIN_NAV_ITEMS`, `ADDON_NAV_ITEMS`

## Building Detail Tabs (10)

| Tab | Data Source | Control Gating | Notes |
|-----|-------------|----------------|-------|
| Overview | All systems | — | Always shows (KPIs, intelligence cards per discipline, occupancy, lighting). Full panels moved to discipline tabs. |
| HVAC | HVAC data points | `hvac_control` | Setpoints, scheduling, rules |
| Energy | Energy data points | `energy_control` | Peak shaving, load shedding |
| Lighting | Lighting + occupancy | `lighting_control` | Sub-tabs: Lighting, Occupancy, Analytics, Correlation |
| Solar & BESS | Solar data points | `solar_control` | Sub-tabs: Dashboard, AEGIS (AEGIS only when `solar_control` active) |
| Water | Water data points | `water_control` | Valve automation |
| Fire | Fire data points | None | Always read-only, no control toggle |
| Security | Security data points | `security_control` | Door commands, schedules |
| Digital Twin | All systems | `digital_twin_control` | Write actions gated |
| Simulation | — | — | Only if `simulation` add-on active |

**Source:** `frontend/src/lib/navigation.ts` (`BUILDING_TAB_ITEMS`)

## Settings Page (3 Sections)

### Platform Section
7 status indicators (no toggles) — `kpi`, `ml`, `notifications`, `integrations`, `simbiot`, `logging`, `assets`

### Building Systems Section
8 cards, each showing monitoring status (always on) with optional control toggle inside:
- HVAC → `hvac_control` toggle
- Energy → `energy_control` toggle
- Lighting → `lighting_control` toggle
- Solar → `solar_control` toggle
- Water → `water_control` toggle
- Security → `security_control` toggle
- Fire → no toggle (always read-only)
- Digital Twin → `digital_twin_control` toggle

### Add-ons Section
5 on/off toggles — `maintenance`, `financial`, `compliance`, `simulation`, `fleet_ml`

## Cross-Module Integrations

When multiple modules are active, SENTINEL automatically creates cross-module intelligence. See [Module Connectivity & Cross-System Integration](module-connectivity.md) for detailed integration patterns.

| Source | Target | Integration |
|--------|--------|-------------|
| Energy | Lighting | Load shedding dims lights |
| Energy | HVAC | Load shedding raises setpoints |
| Solar | Energy | Solar generation offsets grid demand |
| Solar | Energy | Solar/generator coordination |
| Security | HVAC | Occupancy-based HVAC (empty zone: +2.0C) |
| Security | Lighting | Occupancy-based lighting (empty: 20%) |
| ML | HVAC | Predictive maintenance triggers |
| ML | Energy | Anomaly detection alerts |
| Compliance | Energy | Carbon intensity tracking |
| Compliance | Solar | Green energy attribution |

## Configuration

### Per-Site Module Config

File: `backend/app/data/modules/site_modules.json`

```json
{
  "site-002": {
    "site_id": "site-002",
    "site_name": "Sandton City Office Tower",
    "active_modules": [
      {
        "instance_id": "site-002-hvac-001",
        "site_id": "site-002",
        "module_type": "hvac",
        "status": "active",
        "activated_at": "2025-01-15T08:00:00Z",
        "config": {},
        "health_score": 100.0
      }
    ],
    "cross_module_links": [],
    "ai_enabled": true,
    "auto_integration": true
  }
}
```

### Module Activation API

```
POST /api/modules/activate
  { site_id, site_name, module_type, config? }

POST /api/modules/site/{site_id}/deactivate/{module_type}

GET  /api/modules/site/{site_id}/active
GET  /api/modules/site/{site_id}/check/{module_type}
GET  /api/modules/site/{site_id}/integration
GET  /api/modules/site/{site_id}/telemetry
```

### Frontend Navigation Gating

File: `frontend/src/lib/navigation.ts`

- `BASE_NAV_ITEMS` — always visible (Dashboard, AI Chat, System Health, Logs)
- `ADMIN_NAV_ITEMS` — admin only (SIMBIOT, Settings)
- `ADDON_NAV_ITEMS` — visible when `requiredModule` is active (Maintenance, Financial, Compliance, Fleet ML)

The sidebar reads active modules from `ModuleContext` and filters addon items accordingly.

## Example Configurations

### Full Package (Demo - site-002)

All 27 modules active (15 base always on + all 12 add-ons enabled).

### Basic BMS (Energy + HVAC only)

15 base modules + `hvac_control`, `energy_control`. Sidebar: Dashboard, AI Chat, System Health, Logs, SIMBIOT, Settings.

### Office Building (HVAC + Lighting + Security)

15 base + `hvac_control`, `lighting_control`, `security_control`, `maintenance`. Sidebar adds: Maintenance. Building tabs show control features in HVAC, Lighting, Security tabs.

## Key Files

| File | Purpose |
|------|---------|
| `backend/app/models/module_registry.py` | `ModuleType` enum (27), `MODULE_DEFINITIONS` |
| `backend/app/services/module_registry_service.py` | Module activation, `NON_DEACTIVATABLE_MODULES` (15) |
| `backend/app/data/modules/site_modules.json` | Per-site module configuration |
| `frontend/src/lib/moduleRegistry.ts` | Frontend types, API client, icons/colors |
| `frontend/src/lib/mandatoryModules.ts` | `MANDATORY_MODULES` (15 base modules) |
| `frontend/src/lib/navigation.ts` | Sidebar items + building tab definitions |
| `frontend/src/contexts/ModuleContext.tsx` | React context for module state |
| `frontend/src/components/Sidebar.tsx` | Sidebar renders based on active modules |
| `frontend/src/components/Settings.tsx` | 3-section settings page |
| `frontend/src/components/SiteDetail.tsx` | 10-tab building detail page |
