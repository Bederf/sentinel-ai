---
title: "Phase 141: Auto-Dashboard Generator"
type: "spec"
status: "approved"
version: "1.0.0"
created: "2026-03-01"
updated: "2026-03-01"
author: "Sentinel Development Team"
tags: ["dashboard", "onboarding", "equipment-classification", "monitoring", "automation"]
related: ["../03-api-reference/dashboard-generator-api.md", "../02-architecture/event-bus-architecture.md", "../02-architecture/module-system.md"]
domain: "general"
audience: "developers"
complexity: "intermediate"
estimated_read_time: 10
---

# Phase 141: Auto-Dashboard Generator

Automatically generates tailored dashboard configurations when equipment is discovered or a site is onboarded. Classifies equipment into 25 categories, produces dashboard cards from 15 templates, creates monitoring rules from 21 defaults, calculates health scoring weights, suggests add-on modules with savings hints, and builds AI chat context.

## Overview

When a new site is connected to SENTINEL via the BMS Connection Wizard or Niagara discovery, the operator should not need to manually configure dashboard cards, monitoring thresholds, or health weights. The auto-dashboard generator inspects the discovered equipment list, classifies each item by type prefix, and produces a complete dashboard configuration in a single call.

```
Equipment Discovery ──> classify_equipment() ──> DashboardGenerator.generate_for_site()
                                                        |
                                                        +── dashboard_cards (15 templates)
                                                        +── monitoring_rules (21 defaults)
                                                        +── health_weights (normalised)
                                                        +── module_suggestions (7 add-ons)
                                                        +── ai_context (natural language)
```

## Equipment Classification

### EquipmentClass enum (25 categories)

| Domain | Classes |
|--------|---------|
| HVAC | chiller, ahu, fcu, vav, boiler, cooling_tower, pump |
| Electrical | generator, ups, transformer, ats |
| Solar/BESS | solar_inverter, bess, solar_panel |
| Metering | meter_energy, meter_water, meter_gas |
| Lighting | lighting, pir |
| Security | access_point, cctv |
| Fire | fire_panel, fire_detector |
| Vertical transport | elevator |
| Fallback | unknown |

### Prefix-to-class mapping (37 prefixes)

Classification uses the SENTINEL equipment naming convention `{SITE}-{TYPE}-{LOCATION}-{NUM}`. The type segment is extracted from the equipment code after stripping the site prefix. The prefix map is sorted longest-first so `MTR-R-SOLAR` matches before `MTR`.

```python
classify_equipment("S002-CHILLER-B1-001")  # -> EquipmentClass.CHILLER
classify_equipment("S002-INV-R-001")       # -> EquipmentClass.SOLAR_INVERTER
classify_equipment("S002-MTR-R-SOLAR")     # -> EquipmentClass.METER_ENERGY
classify_equipment("S002-MTR-W-001")       # -> EquipmentClass.METER_WATER
```

If an explicit `type` field is provided on the equipment dict, the classifier tries that first before falling back to prefix extraction.

## Dashboard Cards

### Always-present cards

Every generated dashboard includes two overview cards regardless of equipment:

1. **Building Health Score** -- gauge, priority 1
2. **Active Alerts** -- KPI, priority 2

### Equipment-specific card templates (15)

| Equipment class | Card | Type | Domain | Priority |
|-----------------|------|------|--------|----------|
| chiller | Chiller Status | status_grid | hvac | 10 |
| chiller | Chiller Efficiency Trend | chart | hvac | 20 |
| ahu | AHU Status | status_grid | hvac | 15 |
| fcu | Zone Temperatures | kpi | hvac | 25 |
| vav | VAV Box Status | status_grid | hvac | 30 |
| generator | Backup Power Status | status_grid | electrical | 8 |
| ups | UPS Battery Status | kpi | electrical | 12 |
| solar_inverter | Solar Generation | gauge | solar | 5 |
| solar_inverter | Solar Daily Curve | chart | solar | 18 |
| bess | Battery Storage | gauge | solar | 6 |
| meter_energy | Energy Consumption | kpi | energy | 3 |
| meter_water | Water Consumption | kpi | water | 22 |
| lighting | Lighting Status | status_grid | lighting | 28 |
| pir | Occupancy | kpi | occupancy | 26 |
| access_point | Access Events | list | security | 32 |
| fire_panel | Fire System Status | status_grid | fire | 2 |
| elevator | Elevator Status | status_grid | vertical_transport | 35 |

Cards are sorted by priority (lower number = higher position). When more than one unit of a type exists, the card title includes the count (e.g., "Chiller Status (3)"). When more than 10 units exist, compact mode is enabled.

## Monitoring Rules

21 default monitoring rules across 8 equipment classes. Each rule defines a metric, condition, threshold, severity, evaluation window, and cooldown.

| Equipment class | Rule | Metric | Condition | Threshold | Severity |
|-----------------|------|--------|-----------|-----------|----------|
| chiller | High Load | load_pct | > 85% | warning | warning |
| chiller | Overload | load_pct | > 95% | critical | critical |
| chiller | Efficiency Degraded | cop | < 3.0 | warning | warning |
| chiller | Supply Temp High | supply_temp | > 8.0 | warning | warning |
| ahu | Filter DP Warning | filter_dp | > 250 Pa | warning | warning |
| ahu | Filter DP Critical | filter_dp | > 400 Pa | critical | critical |
| ahu | Supply Temp Deviation | supply_temp_deviation | > 3.0 | warning | warning |
| fcu | Zone Temp Warning | zone_temp | > 26 C | warning | warning |
| fcu | Zone Temp Critical | zone_temp | > 28 C | critical | critical |
| generator | Fuel Low | fuel_level_pct | < 30% | warning | warning |
| generator | Fuel Critical | fuel_level_pct | < 10% | critical | critical |
| generator | Runtime High | continuous_runtime_hours | > 8h | warning | warning |
| solar_inverter | Underperforming | performance_ratio | < 0.75 | warning | warning |
| solar_inverter | Fault | fault_code | != 0 | critical | critical |
| bess | Battery Low | soc_pct | < 20% | warning | warning |
| bess | Battery Critical | soc_pct | < 10% | critical | critical |
| bess | Temp High | battery_temp_c | > 45 C | critical | critical |
| meter_water | Leak Detected | flow_rate | > 0.5 | warning | warning |
| meter_water | Consumption Spike | consumption_ratio | > 3.0x | warning | warning |
| fire_panel | Alarm Active | alarm_active | = 1 | critical | critical |
| fire_panel | Detector Fault | detector_fault_count | > 0 | warning | warning |

Rules are instantiated per site and deduplicated by equipment class (one set of rules per class, not per individual unit).

## Health Scoring Weights

Each equipment class has a base weight reflecting its criticality to building operations. When multiple units of the same class exist, weights scale by square root (diminishing returns). Weights are normalised to sum to 100.

**Base weights (top 5):**

| Class | Base weight |
|-------|-------------|
| chiller | 15 |
| fire_panel | 15 |
| generator | 12 |
| ups | 10 |
| ahu | 10 |

## Module Suggestions

7 add-on modules are suggested based on discovered equipment classes:

| Trigger equipment | Suggested module | Savings hint |
|-------------------|------------------|--------------|
| chiller | hvac_control | 5-15% chiller energy reduction |
| solar_inverter | solar | Maximize self-consumption |
| bess | solar | 10-20% peak demand reduction |
| lighting | lighting | 20-40% lighting energy reduction |
| pir | lighting | 15-25% energy savings in unoccupied zones |
| meter_water | water | 5-15% water cost savings |
| access_point | security | Improved security posture |

Suggestions are deduplicated by module name. Each suggestion includes the equipment class that triggered it and the number of matching equipment items.

## AI Chat Context

The generator produces a natural-language summary grouping equipment by domain (HVAC, Electrical, Solar/BESS, Energy, Water, Lighting, Occupancy, Security, Fire, Elevators). This text is injected into Claude's system prompt so the AI knows what equipment the building contains without querying the database at chat time.

## Event-Driven Auto-Trigger

The dashboard generator subscribes to two events on the SENTINEL event bus (Phase 139):

| Event | Handler | Behaviour |
|-------|---------|-----------|
| `system.site_onboarded` | `auto_generate_dashboard` | Generates full dashboard, emits `system.dashboard_generated` and `system.module_suggested` chained events |
| `system.equipment_discovered` | `handle_equipment_change` | Regenerates dashboard for the affected site |

Subscriber registration order in `startup/events.py`:

1. `register_default_subscribers()` (Phase 139)
2. `register_n8n_subscribers()` (Phase 140)
3. `register_sentry_subscribers()` (Phase 140)
4. `register_dashboard_gen_subscribers()` (Phase 141)

## Equipment Loading (3-tier fallback)

When no equipment list is provided to the API, the generator loads equipment using the standard SENTINEL fallback pattern:

1. **Tier 1: Supabase** -- `equipment_repository.get_by_building_code(site_id)`
2. **Tier 2: JSON files** -- `data/buildings/{site_id}/equipment/*.json` with key normalisation (`id` to `code`, `equipment_type` to `type`)
3. **Tier 3: Empty list** -- graceful degradation, generates only the two overview cards

## Files

| File | Description |
|------|-------------|
| `backend/app/services/dashboard_generator.py` | Core engine: classification, card/rule/weight/suggestion/context generation (1093 lines) |
| `backend/app/api/dashboard_generator.py` | 4 REST endpoints (191 lines) |
| `backend/app/services/dashboard_gen_subscriber.py` | Event bus subscriber (151 lines) |
| `backend/app/startup/events.py` | Subscriber registration wiring |

## API Endpoints

See [Dashboard Generator API](../03-api-reference/dashboard-generator-api.md) for full endpoint reference.

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/dashboard-generator/generate/{site_id}` | Full dashboard config generation |
| POST | `/api/dashboard-generator/preview/{site_id}` | Preview mode for BMS Connection Wizard |
| POST | `/api/dashboard-generator/classify` | Equipment classification only |
| GET | `/api/dashboard-generator/suggestions/{site_id}` | Module upgrade suggestions |

## Related Documentation

- [Dashboard Generator API Reference](../03-api-reference/dashboard-generator-api.md) -- endpoint details and request/response schemas
- [Event Bus Architecture](../02-architecture/event-bus-architecture.md) -- pub/sub event system used for auto-triggering
- [Module System](../02-architecture/module-system.md) -- module activation and add-on architecture
- [Niagara BMS Connection Wizard](niagara-connection-wizard.md) -- discovery flow that feeds the generator
