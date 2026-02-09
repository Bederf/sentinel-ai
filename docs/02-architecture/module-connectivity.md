---
title: "Module Connectivity & Cross-System Integration"
type: "architecture"
status: "approved"
version: "1.0.0"
created: "2026-02-09"
updated: "2026-02-09"
author: "Sentinel Development Team"
tags: ["modules", "integration", "architecture", "multi-module", "coordination"]
domain: "general"
audience: "product-managers|developers|operators"
complexity: "intermediate"
estimated_read_time: 20
---

# Module Connectivity & Cross-System Integration

## Overview

The SENTINEL BMS Intelligence Platform uses a **bolt-on module architecture** where clients activate only the modules they need and pay per module. When multiple modules are active together, the system automatically creates **cross-module integration links** that enable sophisticated coordination behaviors.

This document explains:
1. How each module connects to other modules (integration graph)
2. How system behavior changes when modules are combined
3. Concrete examples showing emergent behaviors as modules are added

For foundational module information, see [Module System](module-system.md). For implementation details on auto-integration, see [Module Registry](../13-modules/module-registry.md).

### Key Principle: Emergent Behavior

The system's capabilities **exponentially increase** as modules are added. A single HVAC module provides basic temperature control. Add Energy and you get load shedding coordination. Add Security and you get occupancy-based optimization. Add Solar and you get renewable-aware pre-cooling.

---

## Module Catalog

### 17 Total Modules Across 5 Categories

| Module | Category | Description | Capabilities | Cost |
|--------|----------|-------------|--------------|------|
| **control** | Core | Device & scene control | Remote command execution, safety validation | Included |
| **assets** | Core | Asset lifecycle management | Baseline assessment, inspection scheduling, repair tracking | Included |
| **simbiot** | Core | BMS onboarding & integration | Wizard-driven setup, auto-discovery, point mapping | Included |
| **integrations** | Core | BMS connectivity | Niagara, BACnet, Modbus, data quality monitoring | Included |
| **notifications** | Core | Alert delivery | Telegram, email, SMS dispatch with cooldown | Included |
| **hvac** | Building Systems | HVAC control & monitoring | Zone temperature control, setpoint management, comfort optimization | Paid Add-on |
| **energy** | Building Systems | Power & load management | Generator/UPS/ATS monitoring, load shedding, demand response | Paid Add-on |
| **lighting** | Building Systems | DALI lighting control | Scene management, daylight harvesting, occupancy-based dimming | Paid Add-on |
| **security** | Building Systems | Access & occupancy | Badge event tracking, zone occupancy, occupancy-based automation | Paid Add-on |
| **solar** | Building Systems | Solar PV & BESS | Generation monitoring, dispatch optimization, NRS 097 compliance | Paid Add-on |
| **fire** | Building Systems | Fire safety systems | Detection, notification, zone segregation | Paid Add-on |
| **access** | Building Systems | Access control | Door locks, reader integration, audit trail | Paid Add-on |
| **water** | Operations | Water metering | Consumption monitoring, leak detection, trending | Paid Add-on |
| **sustainability** | Operations | ESG & carbon tracking | Carbon emissions, energy efficiency, green certifications | Paid Add-on |
| **contracts** | Operations | Commercial management | SLA tracking, budget management, profitability analysis | Paid Add-on |
| **ml** | Intelligence | Fleet machine learning | LSTM forecasting, anomaly detection, cross-site patterns | Paid Add-on |
| **{future}** | Intelligence | Custom integrations | Template for partner integrations | Paid Add-on |

---

## Integration Catalog

### 12 Cross-Module Integration Links

When both source and target modules are active, the system automatically creates integration links. These links enable coordinated behavior across systems.

| Integration ID | Source → Target | Trigger Condition | Action | Business Value |
|---|---|---|---|---|
| **hvac_energy_loadshed** | Energy → HVAC | Generator power active | Raise HVAC setpoints +2°C | Reduce cooling load during expensive peak periods |
| **security_hvac_occupancy** | Security → HVAC | Badge occupancy changes | Adjust zone setpoint by ±1-2°C based on occupancy | Comfort-aware energy savings (empty zone +2°C, low occ +1°C) |
| **security_lighting_occupancy** | Security → Lighting | Badge occupancy changes | Adjust lighting level based on occupancy | Lighting energy savings (empty 20%, low 50%, normal 100%) |
| **energy_lighting_loadshed** | Energy → Lighting | Generator power active | Reduce lighting to 50% | Reduce energy draw during peak/load shedding |
| **hvac_energy_demand** | Energy → HVAC | Peak demand warning | Pre-cool building, then reduce cooling | Thermal battery effect: shift cooling to off-peak hours |
| **energy_solar_generation** | Solar → Energy | Solar generation update | Include PV in total energy accounting | Accurate net energy calculations (grid + PV - consumption) |
| **solar_generator_coordination** | Solar → Energy | Generator start requested | Check if solar+BESS can serve load | Avoid expensive generator start when renewable generation available |
| **ml_hvac_predictive** | ML → HVAC | Failure prediction | Generate maintenance alert + auto-schedule inspection | Prevent HVAC failures before they occur |
| **ml_energy_anomaly** | ML → Energy | Anomaly detected | Alert + anomaly details | Detect equipment degradation, energy waste, demand anomalies |
| **sustainability_energy_carbon** | Sustainability → Energy | Carbon tracking enabled | Include carbon intensity in recommendations | Optimize for emissions (shift loads to low-carbon hours) |
| **sustainability_solar_green** | Sustainability → Solar | ESG reporting enabled | Attribute generation to green energy targets | Track renewable contribution to sustainability goals |
| **sustainability_water_monitoring** | Sustainability → Water | ESG enabled | Include water metrics in carbon footprint | Comprehensive environmental impact reporting |

### Auto-Integration Mechanism

Integration links are created **automatically** when both source and target modules are activated:

1. User activates a module via API: `POST /api/modules/activate`
2. System scans `INTEGRATION_DEFINITIONS` for all links where this module is source or target
3. If the other module is already active, creates a `CrossModuleLink` object automatically
4. Stores link in `site_modules.json` and enables in production
5. Link can be manually disabled via `POST /api/modules/site/{site}/integration/{link_id}/toggle`

**Enable/Disable Auto-Integration:**
- Global setting: `auto_integration: true` in `site_modules.json`
- When disabled, links are created but not activated (stored in `proposed_links`)

---

## Incremental Behavior Scenarios

This section shows how platform capabilities **evolve** as modules are added, using concrete examples.

### Scenario 1: HVAC Only

**Active Modules:** HVAC  
**Cross-Module Links:** None  
**Activation Date:** Year 1

#### Capabilities
- Zone-by-zone temperature control
- Manual setpoint adjustment (18-26°C)
- Temperature trending and health scoring
- Comfort complaints workflow

#### AI Recommendations
- Simple HVAC-only: "Raise zone setpoint to 22°C" (no coordination with other systems)
- No awareness of energy cost, solar generation, or occupancy

#### Example: "Too Hot at Desk 25"
**Action:** Increase AHU discharge temp by 2°C (affects entire zone, may help or harm others in same zone)

---

### Scenario 2: HVAC + Energy

**Active Modules:** HVAC, Energy  
**New Cross-Module Links:** `hvac_energy_loadshed`, `hvac_energy_demand`  
**Activation Date:** Year 1, Q2

#### New Capabilities Added
- **Load Shedding Coordination:** When on generator power, automatically raise HVAC setpoints +2°C to reduce cooling demand
- **Demand Response:** Pre-cool building 1 hour before peak demand period, then reduce cooling during peak
- **Cost-Aware Optimization:** Considers time-of-use tariff (peak vs off-peak pricing)

#### AI Recommendations Now Include
- Energy cost in HVAC decisions
- Generator status and fuel cost
- Load shedding schedule awareness
- Coordination: "Pre-cool to 20°C now (off-peak cheap), then raise to 24°C at peak (avoid expensive cooling)"

#### Example: Load Shedding Event
**Scenario:** Eskom announces stage 6 load shedding (Site will lose grid power 3:00-5:00 PM)

**System Behavior:**
1. Energy module detects load shedding schedule
2. HVAC module receives coordination request
3. HVAC raises setpoint +2°C (22°C → 24°C) at 2:45 PM to pre-cool
4. At 3:00 PM when generator takes load, setpoint already at +2°C above normal, reducing generator demand by ~15%

**Business Value:** Reduced generator fuel burn (cost savings) + Improved load shedding compliance

---

### Scenario 3: HVAC + Energy + Lighting

**Active Modules:** HVAC, Energy, Lighting (with DALI support)  
**New Cross-Module Links:** `energy_lighting_loadshed`  
**Activation Date:** Year 1, Q3

#### New Capabilities Added
- **Three-Way Load Optimization:** When on generator, reduce both HVAC (setpoint +2°C) AND Lighting (50%)
- **Coordinated Load Shedding:** System prioritizes which loads to shed in sequence based on impact

#### AI Recommendations Now Include
- Coordinated load reduction strategies
- Comfort vs energy trade-offs across HVAC + Lighting
- Occupancy-aware strategies (empty floors → aggressive dimming)

#### Example: Three-Way Load Reduction
**Scenario:** UPS battery at 40%, generator available but expensive

**System Behavior (Coordinated):**
1. Reduce HVAC: setpoint +1°C (less aggressive than full 2°C)
2. Reduce Lighting: dim to 60% (less aggressive than 50%)
3. Monitor result: UPS charging speed increases
4. If still insufficient, apply full reductions

**Benefit:** More nuanced control than all-or-nothing shedding

---

### Scenario 4: HVAC + Energy + Lighting + Security

**Active Modules:** HVAC, Energy, Lighting, Security (Access Control with badge readers)  
**New Cross-Module Links:** `security_hvac_occupancy`, `security_lighting_occupancy`  
**Activation Date:** Year 1, Q4

#### New Capabilities Added
- **Occupancy-Based Optimization:** Badge entry/exit events automatically adjust zone comfort
- **Adaptive Setpoints:** Different setpoints for empty vs occupied zones
- **Proportional Control:** Setpoint adjusts based on occupancy level

#### Occupancy Thresholds
| Occupancy | HVAC Setpoint Adjustment | Lighting Level |
|-----------|-------------------------|-----------------|
| Empty (0 people) | +2.0°C | 20% (night mode) |
| Low (1-3 people) | +1.0°C | 50% (energy saving) |
| Normal (>3 people) | 0°C (baseline) | 100% (comfort) |

#### AI Recommendations Now Include
- Badge-aware automation triggers
- "Office unoccupied for 15 min → relax HVAC, dim lights"
- Predictive: "Meeting room reserved 2:00-3:00 PM → pre-condition at 1:45 PM"

#### Example: Floor 1 North Wing Vacancy
**Scenario:** 10:30 AM, floor occupancy drops to zero (everyone in meeting)

**System Behavior (Automatic):**
1. Security module detects zero exits, zero entries for 5 min
2. HVAC: Raise zone setpoint 22°C → 24°C (saves ~25% cooling)
3. Lighting: Dim zone 100% → 20% (saves ~80% lighting)
4. System logs action in audit trail
5. At 11:00 AM when meeting ends, first badge entry triggers reset to normal setpoints

**Business Value:**
- **Energy Savings:** 20-30% reduction in empty zones during business hours
- **Comfort:** Occupied zones still at full comfort (different setpoints per zone)
- **Automation:** Zero manual intervention needed

---

### Scenario 5: HVAC + Energy + Lighting + Security + Solar

**Active Modules:** HVAC, Energy, Lighting, Security, Solar (with BESS)  
**New Cross-Module Links:** `energy_solar_generation`, `solar_generator_coordination`  
**Activation Date:** Year 2, Q1

#### New Capabilities Added
- **Solar-Aware Optimization:** Pre-cool during solar generation peaks (10 AM - 2 PM)
- **Generator Avoidance:** When solar+BESS can serve load, avoid expensive generator start
- **TOU Arbitrage:** Buy cheap solar generation, sell peak energy via BESS discharge
- **Renewable Pre-Cooling:** Use abundant solar generation to pre-cool thermally, reduce evening cooling

#### AI Recommendations Now Include
- Solar generation forecasts (weather-based)
- BESS state of charge and dispatch commands
- Renewable energy attribution (track carbon-free supply)
- Coordinated: "Solar generation peak 11 AM-1 PM: pre-cool building now using free renewable energy"

#### Example: Solar-Aware Pre-Cooling
**Scenario:** Summer day, solar forecast 5.2 kW generation 11 AM-1 PM, afternoon load shedding 6-8 PM

**System Behavior (Coordinated):**
1. **11:00 AM:** Solar generation ramps up to 5.2 kW
   - HVAC: Pre-cool zone setpoint 20°C (aggressive)
   - Lighting: Daylight harvesting at 40% (uses solar gain)
   - BESS: Charge at 3 kW (use excess solar)
2. **1:00 PM:** Solar generation drops
   - HVAC: Raise setpoint to 22°C
   - Lighting: Resume normal
3. **6:00 PM:** Load shedding begins
   - HVAC: Reduce to 24°C (pre-cooling benefit now active)
   - BESS: Discharge 4 kW to cover peak load
   - Generator: Not needed (solar + BESS + reduced load cover demand)

**Business Value:**
- **Renewable Attribution:** 100% renewable-powered conditioning
- **Generator Avoidance:** Save R150-200 per load shedding event (fuel cost)
- **Comfort:** Building pre-cooled by solar, not expensive grid/generator

---

### Scenario 6: Full Site Deployment (Sandton Data Centre Example)

**Active Modules:** All 14 (Control, Assets, SIMBIOT, Integrations, Notifications, HVAC, Energy, Lighting, Security, Solar, Water, ML, Sustainability, Contracts)  
**Active Cross-Module Links:** All 12 integrations + ML coordination  
**Real Configuration:** `/backend/app/data/modules/site_modules.json` (site-002)

#### Site Profile
- **Site:** Sandton Data Centre (site-002)
- **Size:** 3 floors, 4,500 sqm
- **Equipment:** 156 units across 10 subsystems
- **BMS:** Siemens Desigo CC V5.0 with 4,850 data points

#### Active Integrations (All 12)
1. Energy → HVAC Load Shedding ✅
2. Security → HVAC Occupancy ✅
3. Security → Lighting Occupancy ✅
4. Energy → Lighting Load Shedding ✅
5. Energy → HVAC Demand Response ✅
6. Solar → Energy Generation ✅
7. Solar → Energy Generator Coordination ✅
8. Water → Sustainability Monitoring ✅
9. ML → HVAC Predictive ✅
10. ML → Energy Anomaly ✅
11. Sustainability → Energy Carbon ✅
12. Sustainability → Solar Green ✅

#### Emergent System Behavior

**Example 1: Summer Afternoon Scenario**
- **1:00 PM:** High occupancy, solar generation 8.2 kW, ambient temp 32°C
- **System Response:**
  - HVAC: Pre-cool to 18°C using solar generation
  - Security: Occupancy high → Lighting 100%, HVAC baseline
  - Lighting: Daylight harvesting active (lux 800+)
  - Solar: BESS charging (store excess generation)
  - ML: Predicts afternoon peak demand → Alerts if chiller trending to failure state
  - Sustainability: Carbon: Zero (all renewable)

**Example 2: Evening Load Shedding Event**
- **5:00 PM:** Load shedding stage 4, occupancy 40%, solar ending (2.1 kW)
- **System Response:**
  1. Energy: Detects load shedding schedule
  2. HVAC: Setpoint +2°C (from solar-cooled state 18°C → 20°C)
  3. Lighting: Empty zones dim to 20% (occupancy-based)
  4. Security: Occupancy tracking optimizes per-zone
  5. Solar: BESS discharge at 3 kW (cover load during peak shed)
  6. ML: Anomaly detection flags if chiller load unusual
  7. Sustainability: Carbon tracking (monitors generator carbon)
  8. Water: Cooling tower flow optimized based on pre-cooling

**Example 3: Predictive Maintenance Trigger**
- **10:00 AM:** ML model detects CHILLER anomaly (bearing degradation pattern)
- **System Response:**
  1. ML: Generates failure prediction (95% confidence, 14 days to failure)
  2. HVAC: Auto-generates work order + schedules inspection
  3. Assets: Baseline assessment prepared
  4. Contracts: SLA check - warranty coverage confirmed
  5. Notifications: Telegram alert to facilities team
  6. Security: Track technician badges during repair
  7. Sustainability: Log repair impact on carbon
  8. Sustainability: Update asset lifecycle costs

#### Upsell Opportunities at This Site
| Adding Module | New Value | Cost Justification |
|---|---|---|
| ML (Predictive) | Prevent 2-3 equipment failures/year | ROI in first failure prevented |
| Solar+BESS | Avoid ~80 load shedding events/year × R150 = R12K savings | 18-month payback |
| Water Monitoring | Leak detection saves R50K+ annually (cooling tower leaks) | Immediate ROI |
| Sustainability | ESG certification, carbon reporting for procurement | Compliance + brand value |
| Contracts | SLA tracking, profitability analytics | Prevent contract losses |

---

## AI/ML Multi-Module Patterns

### Pattern 1: AI Optimizer Equipment Categorization

**Service:** `backend/app/services/ai_optimizer.py`

#### How It Works
The system doesn't assume all buildings have the same equipment. Instead, it:

1. **Categorizes Equipment by Type:**
   - HVAC: CHILLER, AHU, FCU, VAV, SPLIT, CT (Cooling Tower), CRAC
   - Lighting: DALI, LUM (Luminaires)
   - Power: GEN (Generator), TX (Transformer), UPS, ATS, MSB, MTR, FDR, PFC
   - Solar/BESS: SOL (Solar array), BAT (Battery)
   - Security: ACC (Access), CCTV
   - Fire: FIRE_SENSOR, FIRE_ALARM

2. **Builds Site-Specific Equipment Inventory:**
   ```
   Building A: HVAC + DALI + Generators + Meters (6 HVAC + 48 DALI + 1 GEN + 4 MTR)
   Building B: HVAC + Standard Lighting + UPS (8 HVAC + 32 STD_LUM + 1 UPS)
   Building C: HVAC + DALI + Security + Fire (10 HVAC + 60 DALI + 40 ACC + 12 FIRE)
   ```

3. **Filters to Controllable Equipment:**
   - Only includes devices with writable points
   - Excludes read-only sensors and monitors

4. **Generates Site-Specific AI Prompts:**
   - Tells Claude exactly what equipment exists
   - Claude only recommends actions for available equipment
   - No hallucinations (recommending non-existent equipment)

#### Example: Different Sites Get Different Recommendations

**Building A (HVAC + DALI + Generators):**
```
AI Recommendation: "CHILLER setpoint 22°C, AHU damper 60%, DALI zone 1 60%, 
avoid generator start (solar available). Estimated energy cost R45/hour."
```

**Building B (HVAC + Standard Lighting + UPS):**
```
AI Recommendation: "FCU setpoint 24°C, UPS eco mode (off-peak). 
Standard lighting: no control available."
```

**Building C (HVAC + DALI + Security):**
```
AI Recommendation: "HVAC setpoint +1°C (occupancy low), DALI zone 1-3 dim 50% 
(empty floors), ACC readers enabling zone isolation for fire safety."
```

### Pattern 2: Cross-System Analyzer Data Fusion

**Service:** `backend/app/services/cross_system_analyzer.py`

#### Multi-System Diagnosis Example: "Too Hot at Desk 25"

**Input Data Fusion:**
- HVAC: Zone 2 temp 24.5°C, setpoint 22°C, AHU discharge 16°C
- VAV: Damper 40%, airflow 80 cfm (below 120 cfm target)
- Lighting: DALI zone lux 920 (high), lamp output 100%
- Security: Occupancy 2 people in zone 2
- Solar: Solar gain on façade 850 W/m²

**Analysis:**
1. **Thermal Imbalance:** Zone warm (24.5°C > 22°C setpoint)
2. **Insufficient Airflow:** VAV damper only 40%, airflow 80 cfm (bottleneck)
3. **High Heat Load:** Lux 920 = high solar gain (800+ = sun-facing wall)
4. **Demand vs Supply:** Occupancy 2 = low → damper not opening much

**Coordinated Recommendation:**
```
Short-term (immediate):
  1. Dim DALI zone 1 to 30% → reduce light heat load (-200W)
  2. Lower FCU discharge temp from 16°C to 14°C (aggressive)
  3. Open VAV damper to 80% (manual override) → 150 cfm airflow

Medium-term (next 2 hours):
  1. Rebalance VAV damper curve for this zone
  2. Install solar blind on façade (permanent fix)

Root Cause: Solar heat gain + insufficient airflow = occupant discomfort
```

**Benefit:** Coordinated cross-system fix vs single-system patch

### Pattern 3: Security Occupancy Service Coordination

**Service:** `backend/app/services/security_occupancy_service.py`

#### Badge-Driven Automation

**How It Works:**
1. Security module tracks badge entries/exits (access control)
2. Calculates occupancy per zone (entries - exits, 2-hour window)
3. Compares to occupancy thresholds
4. Triggers HVAC and Lighting adjustments automatically

#### Occupancy Calculation Example (Floor 1 North Wing)

```
10:00 AM: 8 entries → occupancy = 8
10:30 AM: 8 entries, 6 exits → occupancy = 2 (everyone in meeting)
10:35 AM: No change (meeting ongoing)
11:00 AM: 6 entries → occupancy = 8 (meeting ends)
```

#### Triggered Actions (By Occupancy Level)

**Empty Zone (0 people):**
- HVAC: Setpoint +2.0°C (22°C → 24°C)
- Lighting: Dim 20% (night mode)
- Schedule: Reduce polling frequency (save API calls)

**Low Occupancy (1-3 people):**
- HVAC: Setpoint +1.0°C (22°C → 23°C)
- Lighting: 50% (energy saving, still comfortable)

**Normal Occupancy (>3 people):**
- HVAC: Setpoint 0°C offset (baseline 22°C)
- Lighting: 100% (full comfort)

#### Real-World Example: Lunchtime Scenario

```
11:45 AM: 40-person open office → HVAC baseline, Lighting 100%
12:00 PM: Lunch break, occupancy drops to 5 → HVAC +1.5°C, Lighting 70%
12:30 PM: Everyone back, occupancy 40 → Reset to baseline
```

**Energy Saved:** ~18% reduction during lunch (shared facilities effect)

### Pattern 4: Hybrid AI Service Tiered Routing

**Service:** `backend/app/services/hybrid_ai_service.py`

#### Two-Tier AI Architecture

**Tier 1 - Ollama (LOCAL, FREE):**
- Running locally at `http://localhost:11434`
- Model: `phi3:mini` or `llama3.2:1b`
- Latency: <500ms
- Cost: Zero (running on-site)

**Tier 2 - Claude API (CLOUD, PAID):**
- Running at `https://api.anthropic.com`
- Model: `claude-opus-4-6`
- Latency: 2-5s
- Cost: ~$0.01-0.05 per request

#### Routing Decision Matrix

| Query Type | Complexity | Tier | Examples |
|---|---|---|---|
| Status Query | Low | 1 | "What's the chiller status?" |
| Simple Lookup | Low | 1 | "Show me HVAC history" |
| Data Retrieval | Low | 1 | "List alerts from last hour" |
| Configuration | Low | 1 | "Set zone 1 to 22°C" |
| Diagnosis | High | 2 | "Why is zone 1 overheating?" |
| Control Action | High | 2 | "Pre-cool building for load shedding" |
| Reasoning | High | 2 | "Should we fix CHILLER now or wait?" |
| Optimization | High | 2 | "Optimize HVAC+Lighting for load shedding" |

#### Cost Savings Example (100 queries/day)

```
All Claude (Tier 2):  100 queries × $0.02 = $2.00/day = $730/year
Hybrid (Tier 1+2):   80 queries × $0.00 + 20 × $0.02 = $0.40/day = $146/year
Savings:             84% cost reduction
```

### Pattern 5: Fleet ML Aggregation

**Service:** `backend/ml/fleet/aggregator.py`

#### Cross-Site Pattern Detection

**What It Does:**
- Aggregates equipment failure patterns across ALL sites
- Strips site identifiers (privacy-preserving)
- Identifies global trends and benchmarks
- Enables predictive maintenance at scale

#### Fleet Analytics Example (CHILLER Fleet)

```
Equipment Type: CHILLER
Total Units Across Fleet: 45 units at 15 sites
Average Health Score: 68.5%
Fleet MTBF: 245 days

Failure Patterns (Anonymized):
  - Compressor failure: 8 units (18%), avg age 8.2 years
  - Bearing wear: 12 units (27%), avg age 6.1 years
  - Refrigerant leak: 5 units (11%), avg age 4.7 years

Benchmarking:
  - Site-002 health: 78% (ABOVE fleet avg +9.5%)
  - Site-005 health: 52% (BELOW fleet avg -16.5%) ← Risk site

Predictive Maintenance Opportunities:
  - 6 chillers at risk of bearing failure in next 60 days
  - Estimated fleet maintenance cost: R450K
  - Estimated failure cost if delayed: R1.2M
  - ROI on maintenance: 2.7x
```

#### Benchmarking Use Case: "Compare Our Chiller to Others"

**User Query:** "How does our CHILLER health compare to the fleet?"

**Hybrid AI Response:**
```
Your chiller: 78% health, 6.1 years old, last service 8 months ago
Fleet average: 68.5% health, 6.8 years old, typical service interval 12 months

Analysis:
  ✓ ABOVE AVERAGE health (78% vs 68.5%)
  ✓ Well-maintained (8-month service vs 12-month typical)
  ⚠ Fleet trend: bearing wear accelerating (27% of fleet showing signs)
  
Recommendation: Continue current maintenance schedule. 
Replace if bearing vibration increases OR if fleet bearing failure rate hits 35%.
Estimated remaining life: 2.1 years (fleet avg: 1.8 years).
```

---

## Configuration & API

### Site Module Configuration

**File:** `/backend/app/data/modules/site_modules.json`

**Structure:**
```json
{
  "site-002": {
    "site_id": "site-002",
    "site_name": "Sandton Data Centre",
    "active_modules": [
      {
        "instance_id": "sandton-hvac-001",
        "module_type": "hvac",
        "status": "active",
        "config": {}
      },
      ...
    ],
    "cross_module_links": [
      {
        "link_id": "sandton-hvac_energy_loadshed",
        "source_module": "energy",
        "target_module": "hvac",
        "integration_type": "hvac_energy_loadshed",
        "enabled": true
      },
      ...
    ],
    "auto_integration": true,
    "ai_enabled": true
  }
}
```

### Module Integration API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/modules/site/{site_id}/integrations` | GET | Query active integrations |
| `/api/modules/activate` | POST | Activate a new module (triggers auto-integration) |
| `/api/modules/site/{site_id}/deactivate/{module_type}` | POST | Deactivate module (disables related links) |
| `/api/modules/site/{site_id}/integration/{link_id}/toggle` | POST | Manually enable/disable specific link |
| `/api/modules/site/{site_id}/integration/{link_id}/telemetry` | GET | Get integration performance metrics |
| `/api/modules/site/{site_id}/integration-summary` | GET | Summary of all active integrations |

**Reference:** See `/backend/app/api/modules.py` for full 22-endpoint API

---

## Building-Specific Equipment Variations

Different buildings have different equipment, and the AI Optimizer adapts accordingly.

### Example: Three Buildings with Different Configurations

#### Building A: Premium Data Centre
```
HVAC:     6 units (CHILLER, 2× AHU, 2× FCU, 1× VAV)
Lighting: 48 DALI luminaires (Tridonic DALI-2)
Power:    1× GEN (100 kW Diesel), 1× ATS, 1× UPS (40 kVA), 4× MTR
Solar:    25 kW PV array, 30 kWh BESS
Security: 40× Access readers, 12× CCTV cameras
Total Equipment: 112 units
```

**AI Optimization Example:**
```
"CHILLER to 20°C (solar generation high), AHU dampers 70%, 
DALI zones 1-4 at 30% (lux sufficient), UPS eco mode (off-peak), 
generator standby (solar+BESS covering load). Estimated energy cost R12/hour."
```

#### Building B: Standard Office
```
HVAC:     4 units (CHILLER, 1× AHU, 2× FCU)
Lighting: 32 standard luminaires (non-controllable)
Power:    No generator, 1× UPS (10 kVA), 2× MTR
Solar:    None
Security: 8× Access readers, 4× CCTV cameras
Total Equipment: 48 units
```

**AI Optimization Example:**
```
"FCU setpoint 23°C (balance comfort/energy), UPS eco mode (off-peak). 
Lighting: no control available (standard fixtures). 
Note: No solar or generator available. Recommend solar retrofit for 15% savings."
```

#### Building C: Hybrid Mixed-Use
```
HVAC:     8 units (CHILLER, 1× AHU, 4× FCU, 2× VAV, 1× CRAC)
Lighting: 60 DALI + 40 standard (mixed)
Power:    1× GEN (50 kW), 1× ATS, 3× MTR
Solar:    10 kW PV (no BESS)
Security: 60× Access readers (complex multi-zone)
Fire:     12× Detectors, 4× Zones
Total Equipment: 198 units (largest)
```

**AI Optimization Example:**
```
"HVAC: CHILLER 21°C (load shedding prep), CRAC for server room isolated, 
FCU/VAV coordinated by zone occupancy. DALI zones 1-8 at occupancy-based levels, 
standard lighting unchanged. Generator startup avoided (solar + BESS + demand reduction sufficient). 
Security zones A-D locked during load shedding. Estimated energy cost R34/hour."
```

---

## Multi-Module Coordination Examples

### Example 1: Complete Load Shedding Workflow

**Scenario:** Eskom stage 4 load shedding, 5:00-7:00 PM

**Modules Involved:** Energy, HVAC, Lighting, Security, Solar, ML, Sustainability

**Workflow:**

```
T-30 min (before load shed):
  1. Energy module detects load shedding alert
  2. HVAC: Initiate gentle pre-cooling (setpoint 20°C)
  3. Lighting: Begin occupancy-based reductions (empty zones already at 20%)
  4. Solar: Store remaining generation in BESS (4 kW remaining → battery)
  5. ML: Flag if any equipment trending to failure (avoid during shed)
  6. Sustainability: Log planned carbon offset (BESS discharge = 0 carbon)

T-5 min:
  1. HVAC: Reduce to full +2°C setpoint (24°C)
  2. Lighting: Non-occupied zones at 20%, occupied at 50%
  3. Security: Verify occupancy levels (reduce if meeting ending)
  4. Generator: Check fuel level, confirm ready
  5. Notifications: Alert ops team "Load shed ready"

T-0 (Shed starts):
  1. Energy: Detect grid loss, switch to generator
  2. HVAC: Fully active +2°C setpoint (from pre-cooled state)
  3. Lighting: Maximize reduction based on occupancy
  4. Solar: BESS discharging (3 kW for ~1.5 hours)
  5. ML: Disable heavy predictions (reduce computation load)
  6. Sustainability: Start logging carbon (generator = carbon-intensive)

T+120 min (Shed ends):
  1. Energy: Switch back to grid
  2. HVAC: Gradually normalize setpoints (22°C)
  3. Lighting: Restore to normal
  4. Solar: BESS charging (if still daylight)
  5. ML: Resume full analysis
  6. Sustainability: Log shed duration impact on carbon
```

**Measurable Outcomes:**
- Energy savings: 35% reduction during 2-hour shed
- Comfort maintained: Occupied zones never exceeded 24°C
- Generator fuel saved: 15 liters (pre-cooling effect)
- Carbon: Renewable energy mitigated 40% of generator emissions

---

## Developer Guide: Adding New Integrations

### How to Add a Cross-Module Integration

**Step 1: Define Integration Type**

Add to `INTEGRATION_DEFINITIONS` in `/backend/app/models/module_registry.py`:

```python
"new_integration_id": {
    "name": "Human-Readable Name",
    "description": "What this integration does",
    "source": ModuleType.SOURCE_MODULE,
    "target": ModuleType.TARGET_MODULE,
    "trigger": "condition_that_activates_this",
    "action": "action_to_perform",
}
```

**Step 2: Implement Integration Logic**

Create service method in target module's service:

```python
# backend/app/services/{target_module}_service.py

async def on_integration_{source}_{target}(self, trigger_data: Dict) -> None:
    """Handle {source} → {target} integration"""
    # Implement coordination logic
    pass
```

**Step 3: Register Handler**

In the service's `__init__`:

```python
self.integration_handlers = {
    "new_integration_id": self.on_integration_source_target,
}
```

**Step 4: Test Cross-Module Behavior**

```python
# tests/integration/test_module_coordination.py

async def test_new_integration():
    # Activate both modules
    # Trigger condition
    # Assert action occurred in target module
```

**Step 5: Update Documentation**

- Add to integration catalog in this file
- Add scenario showing new behavior
- Update API reference if new endpoints added

---

## Success Metrics: Module Adoption Impact

### Business Metrics

| Metric | HVAC Only | +Energy | +Energy+Light | +Energy+Light+Security | +Solar | +ML |
|--------|-----------|---------|---------------|----------------------|--------|-----|
| **Energy Cost/sqm** | R2.40/hr | R2.05/hr (-15%) | R1.85/hr (-23%) | R1.55/hr (-35%) | R1.20/hr (-50%) | R0.95/hr (-60%) |
| **Load Shed Prep Time** | 45 min | 20 min | 15 min | 10 min | 5 min | Automatic |
| **Occupancy Adaptation** | Manual | No | Partial | Full | Full | Predictive |
| **Renewable Integration** | None | None | None | None | Full | Optimized |
| **Maintenance Proactive** | 10% | 10% | 10% | 10% | 10% | 45% |
| **Downtime/Month** | 4.2 hrs | 3.8 hrs | 3.2 hrs | 2.1 hrs | 1.5 hrs | 0.3 hrs |

### Technical Metrics

| Metric | Target |
|--------|--------|
| Integration Link Activation | <500ms after both modules active |
| Cross-System Coordination Latency | <200ms (query + action) |
| AI Optimizer Equipment Accuracy | >98% (categorization) |
| Fleet ML Aggregation Accuracy | >92% (pattern detection) |
| Auto-Recovery Success Rate | >95% (from detected anomalies) |

---

## See Also

- [Module System](module-system.md) - Foundational module architecture
- [Module Registry](../13-modules/module-registry.md) - Implementation details
- [AI Recommendation System](../08-ai-ml/ai-recommendation-system.md) - Zone-aware optimization
- [Hybrid AI Router](../08-ai-ml/hybrid-ai-router.md) - Ollama vs Claude routing
- [Solar & BESS Module](../04-features/34-solar-bess-module.md) - Solar integration details
- [Service Feedback System](../04-features/service-feedback-system.md) - Equipment health integration

---

**Document Control**

| Revision | Date | Change | Author |
|----------|------|--------|--------|
| 1.0 | 2026-02-09 | Initial publication | Sentinel Team |
