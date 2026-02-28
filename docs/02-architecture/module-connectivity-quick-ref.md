---
title: "Module Connectivity - Quick Reference"
type: "reference"
status: "approved"
version: "1.0.0"
created: "2026-02-09"
updated: "2026-02-09"
author: "Sentinel Development Team"
tags: ["modules", "integration", "quick-reference", "cheat-sheet", "optimization", "profiles"]
domain: "general"
audience: "all"
complexity: "beginner"
estimated_read_time: 8
---

# Module Connectivity - Quick Reference

**TL;DR:** The SENTINEL platform uses bolt-on modules that automatically coordinate when multiple modules are active. Each coordination link is called an "integration."  Recently added: **Profile-Based Optimization** — align recommendations with business priorities.

---

## Profile-Based Optimization (NEW)

The system now supports three optimization profiles that align AI recommendations with business priorities:

| Profile | Focus | Best For | Target Savings |
|---------|-------|----------|-----------------|
| **Asset Sweating** | Maximize equipment utilization | Leased facilities, older equipment | 30-40% energy |
| **Comfort First** | Tight environment control | Offices, hospitals, premium buildings | 15-20% energy |
| **Cost Saving** | Minimize operational spend | Light commercial, load shedding | 50-60% energy |

**How It Works:**
1. Operator selects active profile per site → `PUT /api/optimization/settings/{site_id}`
2. AI Optimizer receives profile weights in prompt → injects business priorities
3. Multi-objective scoring ranks recommendations → best match profile weights
4. Three control tiers determine approval → Monitor / Require Approval / Auto-Execute
5. System learns from rejections → auto-creates constraints after 3 rejections

**Real Example:** Same building state, 3 different profiles get 3 different recommendations:
- **Asset Sweating:** "Run CHILLER 24/7 at 18°C (max utilization, bearing maintenance OK)"
- **Comfort First:** "Maintain 21.5±0.5°C (tight control, fast HVAC response)"
- **Cost Saving:** "HVAC +2°C, empty zones +3°C, use BESS not generator (minimize cost)"

**Approval Workflow:**
- Tier 1 (Monitor): Display only, no execution
- Tier 2 (Approve): High-risk actions require operator approval
- Tier 3 (Auto): Low-risk auto-execute, high-risk approval required

See [Profile-Based Optimization Architecture](profile-based-optimization.md) for full details.

---

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
| **Profile active** | AI recommendations update | Align with business priorities | Cost profile: +3°C setback, avoid generator |

## By the Numbers

| Metric | Value |
|--------|-------|
| **Total Module Types** | 27 (15 base + 7 control + 5 standalone) |
| **Non-deactivatable (Base)** | 15 (7 platform + 8 building systems) |
| **Cross-Module Integrations** | 12 |
| **Optimization Profiles** | 3 |
| **Control Tiers** | 3 (Monitor, Approve, Auto-Execute) |
| **API Endpoints** | 70+ (including 17 recommendation endpoints) |
| **Site-002 Active Modules** | 27 (all base + most add-ons) |
| **Site-002 Active Integrations** | 12 of 12 |
| **Profile Recommendation Accuracy** | >85% |
| **Energy Savings (Full Stack, Cost Profile)** | 50-60% |
| **Energy Savings (Comfort Profile)** | 15-20% |
| **Equipment Monitored (site-002)** | 156 units |
| **Data Points (site-002)** | 4,850 |

## How Integrations & Profiles Work Together

```
1. User activates Module B
   ↓
2. System checks: "Is Module A active?" → Auto-integrate if YES
   ↓
3. User selects active profile for site (Asset / Comfort / Cost)
   ↓
4. AI Optimizer runs with profile weights injected
   ↓
5. Multi-objective scoring ranks recommendations (profile-aligned)
   ↓
6. Control tier decides: Auto-execute, Require approval, or Display only
   ↓
7. If approved/auto-executed: Track outcome accuracy
   ↓
8. Learn from rejections: 3+ similar rejections → auto-create constraints
```
11111111
## Upsell Progression (with Profiles)

```
HVAC Only
↓ (+Energy) + Cost Profile
HVAC + Energy = 15% energy savings (comfort-aware)
                or 35% savings (aggressive cost profile)
↓ (+Lighting)
HVAC + Energy + Lighting = 23% savings (comfort) or 50% (cost)
↓ (+Security)
HVAC + Energy + Lighting + Security = 35% savings (comfort) or 55% (cost)
↓ (+Solar)
... + Solar = 50% savings (comfort) or 60% (cost)
↓ (+ML)
Full Stack = 60% savings (comfort) or 70% (cost) + predictive maintenance
```

**Profiles multiply module value:** Adding profiles unlocks 10-20% additional savings through business-aligned optimization.

## Key Scenarios

### Scenario 1: Load Shedding with Cost Profile

```
Eskom stage 4 (5-7 PM) announced
  → Energy module detects schedule
  → Cost Profile: Activate aggressive pre-cooling
  → HVAC raises setpoint +3°C (Cost profile threshold)
  → Lighting dims in empty zones
  → 4:45 PM: Pre-cooling complete
  → At 5 PM when grid drops:
     - HVAC already at +3°C = 40% lower demand
     - Generator kicked in (light load)
     - BESS discharging (covers remaining)
  → Result: 40% energy reduction + generator cost savings R200
```

### Scenario 2: Occupancy Drop with Comfort Profile

```
3:00 PM - 40 people, Comfort Profile active
  → 3:15 PM - Everyone leaves (meeting)
  → Security module detects 0 occupancy
  → Comfort Profile: Gradual adjustment (avoid sudden change)
  → HVAC: 22°C → 21°C (only -1°C, not aggressive)
  → Lighting: 100% → 60% (not 20% like Cost would do)
  → 3:45 PM - Meeting ends
  → Fast response: Back to 22°C and 100% within 5 min
  → Result: Comfort maintained + modest energy savings 8%
```

### Scenario 3: Predictive Maintenance

```
ML model runs overnight
  → Detects CHILLER bearing wear trend
  → Confidence: 95%, Time to failure: 14 days
  → Creates work order automatically
  → HVAC module gets alert
  → Assets module schedules inspection
  → Recommendations avoid aggressive cooling (protect bearing)
  → Notifications alert ops team
  → Result: Repair scheduled before failure (avoid R300K emergency)
```

## For Product Managers

**Sell modules and profiles together:**
- Base: "Control your building operations" (HVAC module)
- +Energy: "Optimize load shedding response" (15% savings with Comfort, 35% with Cost profile)
- +Lighting: "Smart lighting control per zone" (add 8-15% savings)
- +Security: "Occupancy-aware optimization" (add 5-10% savings)
- +Solar: "Renewable-powered conditioning" (add 15-20% savings, ESG benefit)
- +Profiles: "Choose your optimization priority" (unlock 10-20% additional savings through profile selection)

**Stacking value with profiles:**
- Energy + HVAC (Cost Profile) = 35% savings
- Energy + HVAC + Lighting (Cost Profile) = 50% savings
- Energy + HVAC + Lighting + Security (Cost Profile) = 55% savings
- Full Stack (Cost Profile) = 60%+ savings

**Customer journey:** Start with Comfort profile (safe), graduate to Cost after 3 months of learning.

## For Developers

**Adding an integration?** See [Developer Guide: Adding Module Integrations](../12-development/adding-module-integrations.md).

**Building with profiles?** See [Profile-Based Optimization Architecture](profile-based-optimization.md) (Services, Data Models, Control Tiers).

**Debugging integrations?** See [Module Integration API Reference](../03-api-reference/module-integration-api.md).

**Profile API?** See [Recommendations API Reference](../03-api-reference/recommendations-api.md).

**Understanding patterns?** See [Module Connectivity & Cross-System Integration](module-connectivity.md).

## Quick Links

- 🎯 **Profile System** → [Profile-Based Optimization Architecture](profile-based-optimization.md) (Complete guide)
- 📊 **Full Integration Catalog** → [Module Connectivity](module-connectivity.md) (Integration Catalog section)
- 📈 **Module Activation Scenarios** → [Module Connectivity](module-connectivity.md) (Incremental Behavior Scenarios)
- 🤖 **AI/ML Coordination** → [Module Connectivity](module-connectivity.md) (AI/ML Multi-Module Patterns)
- 🔌 **API Endpoints** → [Module Integration API Reference](../03-api-reference/module-integration-api.md)
- 💡 **Recommendation API** → [Recommendations API Reference](../03-api-reference/recommendations-api.md)
- 👨‍💻 **How to Add Integrations** → [Developer Guide](../12-development/adding-module-integrations.md)
- 📚 **Module Architecture** → [Module System](module-system.md)
- 🎨 **Visual Diagram** → [module-connectivity.mmd](diagrams/module-connectivity.mmd)

---

**More Information?** This is the executive summary. For detailed scenarios, code examples, and API specs:
- **Modules:** See [Module Connectivity documentation](module-connectivity.md)
- **Profiles:** See [Profile-Based Optimization Architecture](profile-based-optimization.md)
- **APIs:** See [Recommendations API Reference](../03-api-reference/recommendations-api.md)

---

**Document Control**

| Revision | Date | Change | Author |
|----------|------|--------|--------|
| 1.1 | 2026-02-09 | Add Profile-Based Optimization (Phase 72) | Sentinel Team |
| 1.0 | 2026-02-09 | Initial publication | Sentinel Team |
