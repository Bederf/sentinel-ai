---
title: "Module Connectivity - Quick Reference"
type: "reference"
status: "approved"
version: "1.0.0"
created: "2026-02-09"
updated: "2026-02-09"
author: "Sentinel Development Team"
tags: ["modules", "integration", "quick-reference", "cheat-sheet"]
domain: "general"
audience: "all"
complexity: "beginner"
estimated_read_time: 5
---

# Module Connectivity - Quick Reference

**TL;DR:** The SENTINEL platform uses bolt-on modules that automatically coordinate when multiple modules are active. Each coordination link is called an "integration."

## The 12 Cross-Module Integrations at a Glance

| When This Happens | Then This Happens | Why | Example |
|---|---|---|---|
| **Generator on** | HVAC +2°C, Lighting 50% | Reduce load during expensive power | Eskom stage 4 shed: save 35% energy |
| **Zone empty** | HVAC +2°C, Lights 20% | Save energy, comfort not needed | Lunch break: 20% HVAC savings |
| **Zone low occ** | HVAC +1°C, Lights 50% | Reduced comfort for few people | 1-2 people in office: 15% savings |
| **Peak demand** | HVAC pre-cools then reduces | Use thermal mass, shift load off-peak | Pre-cool at 10am, relax at 4pm peak |
| **Solar generating** | Include in energy balance | Accurate grid import/export | Solar 5kW reduces grid import 5kW |
| **Solar+BESS can serve load** | Don't start generator | Avoid expensive fuel | Afternoon shed: solar+BESS cover load |
| **CHILLER failing (ML)** | Create work order, schedule inspection | Prevent breakdown, plan repair | Bear 95% confidence: 14 days to failure |
| **Energy anomaly (ML)** | Alert ops with details | Catch degradation early | Unplanned peak: +2kW demand, investigate |
| **High carbon intensity** | Adjust energy usage | Optimize for lower-carbon hours | Night generation = clean grid |
| **Green energy targets** | Track renewable attribution | ESG reporting | 100% renewable-cooled zones |
| **Water consumption high** | Flag for sustainability report | Track ESG impact | Cooling tower leak: 200L/day extra |

## By the Numbers

| Metric | Value |
|--------|-------|
| **Total Modules** | 17 |
| **Cross-Module Integrations** | 12 |
| **Site-002 Active Modules** | 14 of 14 |
| **Site-002 Active Integrations** | 12 of 12 |
| **Energy Savings (Full Stack)** | 50-60% |
| **Equipment Monitored (site-002)** | 156 units |
| **Data Points (site-002)** | 4,850 |

## How Integrations Are Created

```
1. User activates Module B
   ↓
2. System checks: "Is Module A active?"
   ↓
3. If YES: "Create integration link A→B"
   ↓
4. Integration starts working automatically
   ↓
5. When Module A detects trigger condition
   → Module B automatically takes action
```

**Auto-Integration:** Enabled by default. Integrations created automatically when both modules are active.

## Upsell Progression

```
HVAC Only
↓ (+Energy)
HVAC + Energy = 15% energy savings + load shedding awareness
↓ (+Lighting)
HVAC + Energy + Lighting = 23% energy savings + 3-way load shed
↓ (+Security)
HVAC + Energy + Lighting + Security = 35% energy savings + occupancy automation
↓ (+Solar)
HVAC + Energy + Lighting + Security + Solar = 50% energy savings + renewable-aware
↓ (+ML)
Full Stack = 60% energy savings + predictive maintenance (prevent 2-3 failures/year)
```

## Key Scenarios

### Scenario 1: Load Shedding Event

```
Eskom announces stage 4 (5-7 PM)
  → Energy module detects schedule
  → HVAC raises setpoint +2°C (pre-cool strategy starts)
  → Lighting dims in empty zones
  → At 5 PM when grid drops:
     - HVAC already at +2°C = lower demand
     - Generator kicks in (lower load)
     - BESS discharging (covers load)
  → Result: 35% energy reduction vs normal day
```

### Scenario 2: Occupancy Drop

```
3:00 PM - 40 people in open office
  → 3:15 PM - Everyone leaves (meeting)
  → Security module detects 0 occupancy
  → HVAC: setpoint 22°C → 24°C
  → Lighting: 100% → 20%
  → 3:45 PM - Meeting ends
  → HVAC: 24°C → 22°C
  → Lighting: 20% → 100%
  → Energy saved during meeting: ~18%
```

### Scenario 3: Predictive Maintenance

```
ML model runs overnight
  → Detects CHILLER bearing wear trend
  → Confidence: 95%, Time to failure: 14 days
  → Creates work order automatically
  → HVAC module gets alert
  → Assets module schedules inspection
  → Notifications alert ops team
  → Result: Repair scheduled before failure (avoid emergency, save R50K)
```

## For Product Managers

**Sell modules by value:**
- Energy: "Control your load shedding response" (cost savings)
- Security: "Occupancy-aware HVAC & Lighting" (comfort + energy)
- Solar: "Renewable-powered conditioning" (ESG + cost savings)
- ML: "Predict equipment failures" (prevent downtime)

**Stacking order matters:**
- Energy + HVAC = 15% savings
- Energy + HVAC + Lighting = 23% savings
- Energy + HVAC + Lighting + Security = 35% savings

## For Developers

**Adding an integration?** See [Developer Guide: Adding Module Integrations](../12-development/adding-module-integrations.md).

**Debugging integrations?** See [Module Integration API Reference](../03-api-reference/module-integration-api.md).

**Understanding patterns?** See [Module Connectivity & Cross-System Integration](module-connectivity.md).

## Quick Links

- 📊 **Full Integration Catalog** → [Module Connectivity](module-connectivity.md) (Integration Catalog section)
- 📈 **Module Activation Scenarios** → [Module Connectivity](module-connectivity.md) (Incremental Behavior Scenarios)
- 🤖 **AI/ML Coordination** → [Module Connectivity](module-connectivity.md) (AI/ML Multi-Module Patterns)
- 🔌 **API Endpoints** → [Module Integration API Reference](../03-api-reference/module-integration-api.md)
- 👨‍💻 **How to Add Integrations** → [Developer Guide](../12-development/adding-module-integrations.md)
- 📚 **Module Architecture** → [Module System](module-system.md)
- 🎨 **Visual Diagram** → [module-connectivity.mmd](diagrams/module-connectivity.mmd)

---

**More Information?** This is the executive summary. For detailed scenarios, code examples, and API specs, see the full [Module Connectivity documentation](module-connectivity.md).

**Document Control**

| Revision | Date | Change | Author |
|----------|------|--------|--------|
| 1.0 | 2026-02-09 | Initial publication | Sentinel Team |
