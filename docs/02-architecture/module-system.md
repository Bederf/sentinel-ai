# SENTINEL Module System

## Overview

SENTINEL uses a bolt-on module architecture. Every deployment ships with all modules — clients activate or deactivate modules per site based on what they need and pay for. The sidebar dynamically reflects which modules are active.

## Architecture

```
┌─────────────────────────────────────────────────┐
│                SENTINEL Platform                 │
├─────────────────────────────────────────────────┤
│  Always On (cannot disable)                     │
│  ┌───────────┐ ┌──────────┐ ┌──────────┐       │
│  │ Dashboard │ │ AI Chat  │ │ Settings │       │
│  └───────────┘ └──────────┘ └──────────┘       │
├─────────────────────────────────────────────────┤
│  Base AI (included with platform)               │
│  • Claude + Ollama hybrid routing               │
│  • RAG knowledge base                           │
│  • AI Optimizer recommendations                 │
│  • Health scoring (threshold-based)             │
│  • Predictive alerts (threshold-based)          │
├─────────────────────────────────────────────────┤
│  Core Modules (toggleable, typically always on) │
│  ┌─────────┐ ┌────────┐ ┌────────┐ ┌────────┐ │
│  │ Control │ │ Assets │ │SIMBIOT │ │Integr. │ │
│  └─────────┘ └────────┘ └────────┘ └────────┘ │
├─────────────────────────────────────────────────┤
│  Building System Modules (per building)         │
│  ┌──────┐ ┌────────┐ ┌──────────┐ ┌──────────┐│
│  │ HVAC │ │ Energy │ │ Lighting │ │ Security ││
│  └──────┘ └────────┘ └──────────┘ └──────────┘│
│  ┌───────┐ ┌───────────────┐ ┌───────────┐    │
│  │ Solar │ │Sustainability │ │ Contracts │    │
│  └───────┘ └───────────────┘ └───────────┘    │
├─────────────────────────────────────────────────┤
│  Intelligence Module (paid add-on)              │
│  ┌──────────────────────────────────────────┐  │
│  │ ML: LSTM + Autoencoder + Cox + RF        │  │
│  │ Fleet Learning | MLOps | Retraining      │  │
│  └──────────────────────────────────────────┘  │
├─────────────────────────────────────────────────┤
│  Internal (admin only)                          │
│  ┌────────────┐                                 │
│  │ Simulation │                                 │
│  └────────────┘                                 │
└─────────────────────────────────────────────────┘
```

## Module Categories

### Always On

These cannot be disabled. They are the platform itself.

| View | Description |
|------|-------------|
| **Dashboard** | System overview with KPIs, alerts, equipment health |
| **AI Chat** | Conversational AI assistant (Claude + Ollama hybrid) |
| **Settings** | System configuration, notification preferences |

### Base AI (Included)

Every SENTINEL installation includes these AI capabilities regardless of active modules:

| Capability | Description |
|------------|-------------|
| **AI Chat** | Natural language queries about building data |
| **Hybrid AI Routing** | Simple queries → Ollama (free), complex → Claude (paid). 40% cost savings |
| **RAG Knowledge Base** | Document search to enrich chat answers with domain knowledge |
| **AI Optimizer** | Generates energy/comfort recommendations for active equipment |
| **Health Scoring** | Threshold-based equipment health calculation |
| **Predictive Alerts** | Threshold-based alerts ("health dropped below 70%") |

### Core Modules

Typically always active for any connected building, but can be disabled if a client doesn't need them.

| Module | Type Key | Sidebar Items | Description |
|--------|----------|---------------|-------------|
| **Control** | `control` | Control, Control Audit | Remote device control with safety interlocks and audit logging |
| **Assets** | `assets` | Asset Workflow | Equipment lifecycle management, baseline assessment, inspections |
| **SIMBIOT** | `simbiot` | SIMBIOT | BMS connection wizard, auto-discovery, point mapping |
| **Integrations** | `integrations` | Integrations | BMS integration health monitoring, sync tracking |
| **Notifications** | `notifications` | *(none - configured in Settings)* | External alert channels (Telegram, email, SMS). Dashboard alerts always work. |

### Building System Modules

Activated based on what building systems exist and what the client pays for.

| Module | Type Key | Sidebar Items | Description |
|--------|----------|---------------|-------------|
| **HVAC** | `hvac` | Tech Chat | HVAC fault diagnosis, zone-aware optimization |
| **Energy** | `energy` | Optimization | Load shedding AI, generator/UPS management |
| **Lighting** | `lighting` | Occupancy | DALI-2 lighting control, occupancy heatmaps |
| **Security** | `security` | Security | Access control, CCTV, occupancy tracking |
| **Solar** | `solar` | Solar & BESS | PV monitoring, battery storage, NRS 097 compliance |
| **Sustainability** | `sustainability` | ESG | Carbon tracking, ESG reporting, green building cert |
| **Contracts** | `contracts` | Contracts | Contract management, SLA tracking, profitability |

### Intelligence Module

Advanced ML capabilities — paid add-on for clients who want predictive intelligence beyond threshold-based alerts.

| Module | Type Key | Sidebar Items | Description |
|--------|----------|---------------|-------------|
| **ML** | `ml` | Fleet ML, ML Metrics | 4-model ensemble (LSTM, Autoencoder, Cox Survival, Random Forest), fleet learning, MLOps monitoring, automated retraining |

### Internal

Admin-only views for development and testing.

| View | Required Role | Description |
|------|---------------|-------------|
| **Simulation** | admin | 24-hour building lifecycle simulation |

## Cross-Module Integrations

When multiple modules are active, SENTINEL automatically creates cross-module intelligence:

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
| Sustainability | Energy | Carbon intensity tracking |
| Sustainability | Solar | Green energy attribution |

Cross-module links are defined in `site_modules.json` under `cross_module_links`.

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
        "instance_id": "sandton-control-001",
        "site_id": "site-002",
        "module_type": "control",
        "status": "active",
        "activated_at": "2025-01-15T08:00:00Z",
        "config": { ... },
        "health_score": 100.0
      }
    ],
    "cross_module_links": [ ... ],
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

- `BASE_NAV_ITEMS` — always visible (Dashboard, Chat, Settings)
- `ADDON_NAV_ITEMS` — visible when `requiredModule` is active
- `INTERNAL_NAV_ITEMS` — visible when user has `requiredRole`

The sidebar reads active modules from `ModuleContext` and filters addon items accordingly. Users can reorder addon items (persisted in localStorage).

## Example Configurations

### Full Package (Demo - site-002)

All 13 modules active: control, assets, simbiot, integrations, notifications, contracts, energy, lighting, hvac, solar, security, sustainability, ml

### Basic BMS (Energy + HVAC only)

7 modules: control, assets, simbiot, integrations, notifications, energy, hvac

Sidebar shows: Dashboard, Chat, Settings, Control, Control Audit, Asset Workflow, SIMBIOT, Integrations, Optimization, Tech Chat

### Office Building (HVAC + Lighting + Security)

8 modules: control, assets, simbiot, integrations, notifications, hvac, lighting, security

Adds: Occupancy, Security views. Cross-module: Security→HVAC occupancy, Security→Lighting occupancy

## Key Files

| File | Purpose |
|------|---------|
| `backend/app/models/module_registry.py` | `ModuleType` enum, data models |
| `backend/app/services/module_registry_service.py` | Module activation, cross-module links, recommendations |
| `backend/app/data/modules/site_modules.json` | Per-site module configuration |
| `frontend/src/lib/moduleRegistry.ts` | Frontend types, API client, icons/colors |
| `frontend/src/lib/navigation.ts` | Sidebar items with module gating |
| `frontend/src/contexts/ModuleContext.tsx` | React context for module state |
| `frontend/src/components/Sidebar.tsx` | Sidebar renders based on active modules |
