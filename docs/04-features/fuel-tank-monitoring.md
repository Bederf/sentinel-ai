---
title: "Fuel Tank Monitoring & Theft Detection"
type: "feature"
status: "implemented"
version: "1.0.0"
created: "2026-03-11"
updated: "2026-03-11"
author: "SENTINEL Development Team"
tags: ["fuel", "theft-detection", "mqtt", "generator", "monitoring", "alerts"]
domain: "fuel"
audience: "developers"
complexity: "intermediate"
estimated_read_time: 12
phase: "148-150"
milestone: "v48.0"
---

# Fuel Tank Monitoring & Theft Detection

MQTT-based fuel tank telemetry ingestion with 7-event classification (theft, leak, low fuel, refill, temperature, sensor fault, generator runtime), configurable thresholds, derived calculations (days-to-empty, consumption anomaly), and Sentry alert pipeline for critical conditions.

**Demo Site:** Sandton City Office Tower (site-002) — 1x above-ground diesel tank (S002-TANK-EXT-001), linked to generator S002-GEN-B1-001

## Overview

v48.0 delivers fuel monitoring across 3 phases (5 plans):

| Phase | Focus | Features |
|-------|-------|----------|
| 148 (Backend) | MQTT ingestion + data model | FuelTelemetry model, MQTT listener, FuelStore (3-tier), TANK equipment type, seed data |
| 149 (Backend) | Event processing | FuelEventProcessor (7 rules), derived calculations, generator session tracking, thresholds |
| 150 (Backend + Frontend) | API + dashboard + alerts | 6 REST endpoints, FuelAlertService, FuelDashboard with tank cards + trend charts |

## System Architecture

### Data Flow

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│ ESP32 Fuel Node  │────▶│ MQTT Broker      │────▶│ FuelMqttListener│
│ (Hydrostatic     │     │ sentinel/fuel/   │     │ (3 topics:      │
│  Level Sensor)   │     │  {node_id}/level │     │  level/events/  │
└─────────────────┘     └──────────────────┘     │  status)        │
                                                  └────────┬────────┘
                                                           │
                                                           ▼
                                                  ┌────────────────┐
                                                  │ FuelStore      │
                                                  │ (Supabase →    │
                                                  │  Redis → JSON) │
                                                  └────────┬───────┘
                                                           │
                                              ┌────────────┼────────────┐
                                              ▼            ▼            ▼
                                     ┌──────────────┐ ┌──────────┐ ┌──────────────┐
                                     │ FuelEvent    │ │ Event Bus│ │ Fuel API     │
                                     │ Processor    │ │ fuel.*   │ │ 6 endpoints  │
                                     │ (7 rules)   │ │ events   │ │ /api/fuel/*  │
                                     └──────┬───────┘ └────┬─────┘ └──────────────┘
                                            │              │              ▲
                                            └──────┬───────┘              │
                                                   ▼                      │
                                          ┌────────────────┐    ┌────────┴───────┐
                                          │ FuelAlert      │    │ FuelDashboard  │
                                          │ Service        │    │ (React UI)     │
                                          │ → Notification │    │ Tank cards,    │
                                          │   Pipeline     │    │ trend charts   │
                                          └────────────────┘    └────────────────┘
```

### MQTT Topics

| Topic | Payload | Frequency |
|-------|---------|-----------|
| `sentinel/fuel/{node_id}/level` | Telemetry (level %, temp, mA, generator state) | ~30s |
| `sentinel/fuel/{node_id}/events` | Discrete events (switch triggers, alarms) | On event |
| `sentinel/fuel/{node_id}/status` | Node health (uptime, signal, battery) | ~5min |

## Event Types

FuelEventProcessor classifies telemetry into 7 event types:

| Event Type | Trigger | Severity | Notification |
|------------|---------|----------|-------------|
| `theft_alert` | Rapid level drop exceeding `THEFT_RATE_THRESHOLD_LPM` | CRITICAL | WhatsApp/Telegram |
| `leak_detected` | Sustained slow loss over `LEAK_SUSTAINED_MINUTES` | CRITICAL | WhatsApp/Telegram |
| `low_fuel` | Level below `LOW_ALERT_PCT_1` (WARNING) or `LOW_ALERT_PCT_2` (CRITICAL) | WARNING/CRITICAL | WhatsApp/Telegram |
| `temp_alert` | Temperature exceeds `FUEL_TEMP_HIGH_C` | WARNING | WhatsApp/Telegram |
| `sensor_fault` | Reading outside 4-20 mA range (3.5-21.0 mA) | WARNING | WhatsApp/Telegram |
| `refill_detected` | Significant level increase between readings | INFO | Logged only |
| `runtime_complete` | Generator stops (True→False transition) | INFO | Logged only |

### Derived Calculations

Computed on every telemetry cycle:

- **days_to_empty** — Linear projection from current level and consumption rate
- **consumption_rate_lph** — Litres per hour based on recent readings
- **consumption_anomaly** — Deviation from generator spec consumption
- **runtime_remaining_hrs** — Estimated runtime at current consumption rate

## Configuration

### Settings (backend/app/config/settings.py)

| Setting | Default | Description |
|---------|---------|-------------|
| `FUEL_MONITORING_ENABLED` | `true` | Gates API router and event bus wiring |
| `FUEL_EVENT_PROCESSOR_ENABLED` | `true` | Gates event processor startup |
| `LOW_ALERT_PCT_1` | `25` | First low fuel warning threshold (%) |
| `LOW_ALERT_PCT_2` | `10` | Critical low fuel threshold (%) |
| `THEFT_RATE_THRESHOLD_LPM` | `2.0` | Minimum litres/min drop rate for theft alert |
| `LEAK_SUSTAINED_MINUTES` | `30` | Duration of slow loss before leak alert |
| `FUEL_TEMP_HIGH_C` | `60.0` | High temperature alert threshold |
| `FUEL_TEMP_LOW_C` | `-10.0` | Low temperature alert threshold |
| `FUEL_SENSOR_MA_LOW` | `3.5` | Sensor fault lower bound (mA) |
| `FUEL_SENSOR_MA_HIGH` | `21.0` | Sensor fault upper bound (mA) |

Per-tank thresholds in `FuelTankConfig` override global defaults.

## Module System

Fuel monitoring registers two module types:

| Module | Type | Description |
|--------|------|-------------|
| `fuel_monitoring` | Base building system | Read-only monitoring, tank telemetry, dashboard |
| `fuel_alerts` | Control add-on | Alert routing to WhatsApp/Telegram |

Both are registered in `module_registry.py` and seeded for site-002 in `site_modules.json`.

## API Endpoints

All endpoints under `/api/fuel/`, gated by `FUEL_MONITORING_ENABLED`.

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/fuel/tanks` | List tanks with latest telemetry (query: `site_id`) |
| GET | `/api/fuel/tanks/{tank_id}` | Single tank detail with derived fields |
| GET | `/api/fuel/tanks/{tank_id}/history` | Time-series telemetry (query: `hours`, default 24) |
| GET | `/api/fuel/events` | Fuel events list (query: `site_id`, `event_type`, `limit`) |
| GET | `/api/fuel/generator-runtime` | Generator runtime sessions |
| GET | `/api/fuel/refill-log` | Refill events |

## Frontend Dashboard

The Fuel tab appears on the building detail page (SiteDetail) when `fuel_monitoring` module is active.

### Components

| Component | Location | Description |
|-----------|----------|-------------|
| `FuelDashboard` | `components/fuel/FuelDashboard.tsx` | Main page: summary stats, tank grid, events feed, refill/runtime tables |
| `FuelTankCard` | `components/fuel/FuelTankCard.tsx` | Tank level gauge (color-coded), temperature, days-to-empty, status badge |
| `FuelTrendChart` | `components/fuel/FuelTrendChart.tsx` | Tremor AreaChart, 24h/7d/30d toggle, tank selector, temperature overlay |

### Dashboard Sections

1. **Summary stats row** — Total tanks, warning count, critical count, avg days-to-empty
2. **Tank cards grid** — One card per tank with level gauge, temp, days-to-empty
3. **Trend chart** — Level % over time with period toggle
4. **Recent events feed** — Last 10 fuel events with type badges
5. **Refill log table** — Date, tank, litres added, previous/new level
6. **Generator runtime table** — Session start/end, duration, fuel consumed, anomaly flag

Data refreshes every 30 seconds via polling.

## Key Files

### Backend

| File | Purpose |
|------|---------|
| `backend/app/models/fuel.py` | FuelTelemetry, FuelEvent, FuelTankConfig, FuelEventType |
| `backend/app/services/fuel_store.py` | 3-tier persistence (Supabase → Redis → JSON) |
| `backend/app/services/fuel_event_processor.py` | 7 detection rules, derived calculations, generator session tracking |
| `backend/app/services/fuel_alert_service.py` | Event→notification routing (CRITICAL/WARNING → broadcast) |
| `backend/app/services/fuel_mqtt_listener.py` | MQTT subscriber for 3 fuel topics |
| `backend/app/api/fuel.py` | 6 REST endpoints |
| `backend/app/config/settings.py` | 10 fuel-related settings |

### Frontend

| File | Purpose |
|------|---------|
| `frontend/src/components/fuel/FuelDashboard.tsx` | Main dashboard page |
| `frontend/src/components/fuel/FuelTankCard.tsx` | Tank level card component |
| `frontend/src/components/fuel/FuelTrendChart.tsx` | Trend chart with period toggle |
| `frontend/src/lib/api.ts` | `fuelApi` client (5 functions) |
| `frontend/src/lib/moduleRegistry.ts` | fuel_monitoring + fuel_alerts types |
| `frontend/src/lib/navigation.ts` | Fuel building tab definition |

### Tests

| File | Tests | Coverage |
|------|-------|----------|
| `backend/tests/services/test_fuel_store.py` | 15 | Store CRUD, persistence fallback |
| `backend/tests/services/test_fuel_mqtt_listener.py` | 9 | MQTT subscription, message parsing |
| `backend/tests/services/test_fuel_event_processor.py` | 27 | All 7 rules (positive + negative + boundary) |
| `backend/tests/services/test_fuel_alert_service.py` | 23 | Severity mapping, notification routing |
| `backend/tests/api/test_fuel_api.py` | 12 | All 6 endpoints |

**Total: 86 fuel tests**

## Future Work

- **Supabase tables** — Create `fuel_telemetry` and `fuel_events` tables (currently JSON fallback)
- **PLC/Modbus-MQTT bridge** — Commercial deployment with underground tanks via PLC
- **ML forecasting** — Consumption prediction model (needs training data)
- **Multi-tank topology** — Support multiple generators sharing one tank
