---
title: "Module Matrix Contract"
type: "architecture"
status: "approved"
version: "2.0.0"
created: "2026-02-20"
updated: "2026-02-28"
author: "Sentinel Development Team"
tags: ["modules", "contract", "alignment", "simbiot"]
domain: "general"
audience: "developers"
complexity: "intermediate"
estimated_read_time: 10
---

# Module Matrix Contract

This document is the canonical module contract used for planning and implementation alignment.

## Authoritative Sources

- Backend enum universe: `backend/app/models/module_registry.py` (`ModuleType`)
- Backend non-deactivatable rules: `backend/app/services/module_registry_service.py` (`NON_DEACTIVATABLE_MODULES`)
- API projection: `GET /api/modules/available` from `MODULE_DEFINITIONS`
- Frontend module type union: `frontend/src/lib/moduleRegistry.ts` (`ModuleType`)
- Frontend mandatory list: `frontend/src/lib/mandatoryModules.ts` (`MANDATORY_MODULES`)

## Official Module Matrix (27 Types)

### Base Platform (7, always on)

| Module ID | Description | Non-deactivatable |
|---|---|---:|
| `kpi` | KPI Dashboard & scorecards | Yes |
| `ml` | AI & ML intelligence | Yes |
| `notifications` | Alert delivery (Telegram, email, SMS) | Yes |
| `integrations` | BMS connectivity & health monitoring | Yes |
| `simbiot` | BMS onboarding & point mapping | Yes |
| `logging` | Audit trail, equipment diagnostics, event logs | Yes |
| `assets` | Asset lifecycle management | Yes |

### Base Building Systems (8, always on — tabs driven by SIMBIOT data)

| Module ID | Description | Non-deactivatable |
|---|---|---:|
| `hvac` | HVAC monitoring & zone control | Yes |
| `energy` | Energy centre & power distribution | Yes |
| `lighting` | Lighting & occupancy monitoring | Yes |
| `solar` | Solar PV & BESS monitoring | Yes |
| `water` | Water consumption & leak monitoring | Yes |
| `fire` | Fire safety (always read-only) | Yes |
| `security` | Access control, CCTV, occupancy | Yes |
| `digital_twin` | 3D/2D spatial visualization | Yes |

### Control Add-ons (7, toggleable per building system)

| Module ID | Gates | Description |
|---|---|---|
| `hvac_control` | HVAC tab control features | Setpoints, scheduling, automation rules |
| `energy_control` | Energy tab control features | Peak shaving, load shedding, generator management |
| `lighting_control` | Lighting tab control features | DALI scenes, daylight harvesting, occupancy automation |
| `solar_control` | Solar tab control features + AEGIS | AEGIS dispatch, BESS arbitrage, load shifting |
| `water_control` | Water tab control features | Valve automation, leak response |
| `security_control` | Security tab control features | Door lock commands, access schedules |
| `digital_twin_control` | Digital Twin write actions | Write actions from twin interface |

### Standalone Add-ons (5, toggleable)

| Module ID | Description | Sidebar Item |
|---|---|---|
| `maintenance` | Work orders, preventive scheduling, tech chat | Maintenance |
| `financial` | Contracts, profitability, budget, SLA, tenant sub-billing | Financial |
| `compliance` | Carbon Tax, Green Star, SANS certification | Compliance |
| `simulation` | What-if scenarios, ROI modelling | Building tab |
| `fleet_ml` | Cross-portfolio analytics, multi-site benchmarking | Fleet ML |

## Consistency Checks

### Check A: Backend Enum vs Frontend `ModuleType`
- Rule: sets must be exactly equal.
- Current status: `PASS` — both have 27 types.

### Check B: Backend Non-deactivatable vs Frontend Mandatory
- Rule: frontend mandatory list must equal backend non-deactivatable set.
- Current status: `PASS`.
- Both have 15 modules: `kpi`, `ml`, `notifications`, `integrations`, `simbiot`, `logging`, `assets`, `hvac`, `energy`, `lighting`, `solar`, `water`, `fire`, `security`, `digital_twin`.

### Check C: Enum Coverage in `MODULE_DEFINITIONS`
- Rule: all modules expected to be visible via `/api/modules/available` must exist in `MODULE_DEFINITIONS`.
- Current status: `PASS` — all 27 enum values have definitions.

### Check D: Settings Page Coverage
- Rule: every module type has explicit treatment in Settings page.
- Current status: `PASS`.
- Platform section: 7 status indicators (no toggles).
- Building Systems section: 8 cards with optional control toggle inside.
- Add-ons section: 5 on/off toggles.

## Key Architecture Rules

1. **No cascade dependencies.** Each control add-on is independent — deactivating `hvac_control` does not affect `energy_control`.
2. **Base modules cannot be deactivated.** All 15 base modules (platform + building systems) are always on.
3. **Building tabs are SIMBIOT-data-driven.** Tab visibility is based on whether SIMBIOT has data for that discipline, NOT on module toggles.
4. **Control toggles gate write features within tabs.** The tab is always visible if data exists; control features inside the tab are hidden when `{x}_control` is off.
5. **Fire has no control toggle.** Fire safety is always read-only.
6. **Occupancy is a data layer.** It feeds lighting and HVAC, not its own module.
7. **Simulation is a building tab**, not a sidebar item. Shown only when `simulation` add-on is active.

## Acceptance Criteria for Alignment

A release is `PASS` only if all are true:

1. Backend enum and frontend `ModuleType` are equal sets (27).
2. Backend non-deactivatable and frontend mandatory sets are equal (15).
3. Every module intended for `/api/modules/available` has a `MODULE_DEFINITIONS` entry.
4. Settings UI has explicit treatment for each module type.
5. Sidebar shows: 4 always-visible + 2 admin-only + 4 conditional add-on items.
6. Building detail shows 10 discipline tabs (overview + 9 system tabs).

## Quick Verification Commands

```bash
cd /opt/bms-intelligence

python3 - <<'PY'
import re
from pathlib import Path

backend = Path('backend/app/models/module_registry.py').read_text()
frontend = Path('frontend/src/lib/moduleRegistry.ts').read_text()
mandatory = Path('frontend/src/lib/mandatoryModules.ts').read_text()

start = backend.index('class ModuleType')
end = backend.index('class ModuleStatus')
backend_enum = set(re.findall(r'^\s*[A-Z_]+\s*=\s*"([a-z_]+)"', backend[start:end], re.M))

u_start = frontend.index('export type ModuleType')
u_end = frontend.index('export type ModuleStatus')
frontend_enum = set(re.findall(r"'([a-z_]+)'", frontend[u_start:u_end]))

m_start = mandatory.index('MANDATORY_MODULES')
m_end = mandatory.index('];', m_start)
frontend_mandatory = set(re.findall(r"'([a-z_]+)'", mandatory[m_start:m_end]))

print(f'Backend enum count: {len(backend_enum)}')
print(f'Frontend enum count: {len(frontend_enum)}')
print(f'Frontend mandatory count: {len(frontend_mandatory)}')
print('backend-only:', sorted(backend_enum - frontend_enum))
print('frontend-only:', sorted(frontend_enum - backend_enum))
PY
```
