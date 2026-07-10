# AI Recommendation System — Architecture & Pipeline

> **Last Updated:** 2026-07-10  
> **System:** SENTINEL Autonomous Building Operator  
> **Core Service:** `backend/app/services/ai_optimizer.py` (~5400 lines)

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Pipeline Architecture](#2-pipeline-architecture)
3. [Layer 0: Telemetry & Data Gathering](#3-layer-0-telemetry--data-gathering)
4. [Layer 1: Safety & Policy Gates](#4-layer-1-safety--policy-gates)
5. [Layer 2: Pre-Computed Waste Opportunities](#5-layer-2-pre-computed-waste-opportunities)
6. [Layer 3: The LLM Optimizer (5-Layer Prompt)](#6-layer-3-the-llm-optimizer-5-layer-prompt)
7. [Layer 4: Rule-Based Recommendations](#7-layer-4-rule-based-recommendations)
8. [Layer 5: Zone-Scope Decomposition](#8-layer-5-zone-scope-decomposition)
9. [Layer 6: Quality Gates & Post-Processing](#9-layer-6-quality-gates--post-processing)
10. [Layer 7: Tier Routing (Confidence-Based)](#10-layer-7-tier-routing-confidence-based)
11. [Layer 8: Progression Engine (SAE Trust Ladder)](#11-layer-8-progression-engine-sae-trust-ladder)
12. [Layer 9: Execution & Control](#12-layer-9-execution--control)
13. [Layer 10: M&V Verification & Feedback Loop](#13-layer-10-mv-verification--feedback-loop)
14. [Data Flow Diagrams](#14-data-flow-diagrams)
15. [Key Services Reference](#15-key-services-reference)

---

## 1. System Overview

The SENTINEL AI Recommendation System is a **multi-layered pipeline** that transforms raw building telemetry into actionable, trust-ranked control recommendations. It combines:

- **LLM-based reasoning** (Anthropic Claude via `model_gateway.py`) for holistic building analysis
- **Rule-based policies** for deterministic safety-critical decisions (after-hours, fault conditions)
- **Zone-scope decomposers** for per-zone HVAC and lighting control
- **Quality gates** for data credibility validation before recommendations reach operators
- **Tier routing** to match recommendation confidence to appropriate control authority
- **Progression engine** (SAE-style trust ladder) that evolves site autonomy from shadow → fully autonomous based on evidence

### Design Principles

| Principle | Implementation |
|-----------|---------------|
| **Safety-first** | Fault gates, served-zone gates, and operating-state gates fire before any LLM invocation |
| **Evidence-based trust** | No site reaches autonomous execution without proven accuracy over time |
| **Human-in-the-loop** | Tier 2 (supervised) requires operator approval; Tier 3 (auto-execute) only after class readiness proves reliability |
| **Fail-closed** | All gates default to blocking until explicitly satisfied. Unknown equipment types are not optimized |
| **Deterministic overrides** | Rules (after-hours, fault, occupancy conflict) take precedence over LLM output |

---

## 2. Pipeline Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                        TELEMETRY INGESTION LAYER                                 │
│  BACnet Bridge │ DALI │ Security │ Weather API │ Energy Pricing │ Site Profile  │
└──────────────────────────┬──────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                    1. CURRENT CONDITIONS (enriched dict)                         │
│  site_aggregate │ electrical │ fused_occupancy │ zone_occupancy │ weather ...    │
└──────────────────────────────────┬──────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                    2. SAFETY & POLICY GATES (early exits)                        │
│                                                                                  │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────────┐   ┌──────────────┐  │
│  │ Operating-   │──▶│  Fault Gate  │──▶│  Served-Zone     │──▶│ Occupancy    │  │
│  │ State Gate   │   │              │   │  Gate            │   │ Fusion       │  │
│  └──────────────┘   └──────────────┘   └──────────────────┘   └──────────────┘  │
│        │                  │                    │                      │          │
│        ▼                  ▼                    ▼                      ▼          │
│  Advisory recs      Suppressed         Zone-level            Fused verdict        │
│  (shut down)        equipment          constraints           (0-100%)             │
└──────────────────────────────────┬──────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                   3. PRE-COMPUTED WASTE OPPORTUNITIES                            │
│  (context_precompute_service + ML predictions)                                   │
│                                                                                  │
│  • After-hours HVAC running       • Over-lit unoccupied zones                    │
│  • Free cooling opportunity       • Chiller staging mismatch                     │
│  • FCU/coil valve hunting         • Setpoint deadband violations                 │
│  • Solar/BESS dispatch windows    • Peak demand threshold breaches               │
│  • ML anomaly/forecast context    • Pinned/frozen signal warnings                │
└──────────────────────────────────┬──────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                   4. LLM OPTIMIZER (5-Layer Prompt → Claude)                     │
│                                                                                  │
│  ┌────────────────────────────────────────────────────────────────────────────┐ │
│  │  LAYER 1: Active Goal — time, occupancy, profile, tariff                   │ │
│  │  LAYER 2: Waste Opportunities — pre-computed triggers                      │ │
│  │  LAYER 2b: Full Building Telemetry — live sensor snapshot                  │ │
│  │  LAYER 3: Learned Patterns — decision memory, success rates                │ │
│  │  LAYER 4: Constraints & Module Permissions                                 │ │
│  │  LAYER 5: Task Instruction — WHAT to do, FORMAT rules                     │ │
│  └────────────────────────────────────────────────────────────────────────────┘ │
│                                    │                                             │
│                                    ▼                                             │
│                         Claude (model_gateway)                                   │
│                                    │                                             │
│                                    ▼                                             │
│                     Parsed recommendations + no_action_reasons                   │
└──────────────────────────────────┬──────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                   5. RULE-BASED ANALYSIS (appended to LLM output)                │
│                                                                                  │
│  • Zone-scope HVAC decomposer  → per-FCU/vav setback recs                       │
│  • Lighting rule engine        → dimming / daylight harvesting                  │
│  • Cross-system coordinator    → combined HVAC + lighting savings               │
└──────────────────────────────────┬──────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                   6. QUALITY GATES (pre-execution validation)                    │
│                                                                                  │
│  ┌────────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │ Pinned Signal  │  │ Telemetry    │  │ Data Quality │  │ Telemetry Age    │  │
│  │ Detector       │  │ Completeness │  │ Scores       │  │ (freshness)      │  │
│  └────────────────┘  └──────────────┘  └──────────────┘  └──────────────────┘  │
│                                                                                  │
│  Each gate can BLOCK, WARN, or PASS. Blocked recs never reach operator.          │
└──────────────────────────────────┬──────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                   7. TIER ROUTING (action assignment)                            │
│                                                                                  │
│  Confidence Range    Tier      Action (supervised)    Action (auto_execute)      │
│  ───────────────    ─────     ───────────────────    ─────────────────────      │
│  < 0.30             BLOCKED   blocked                blocked                     │
│  0.30 – 0.60        Tier 1    advisory               advisory                    │
│  0.60 – 0.85        Tier 2    pending_approval       pending_approval            │
│  ≥ 0.85             Tier 3    pending_approval       auto_execute                │
│                                                                                  │
│  Thresholds reweighted by class readiness (progression engine).                  │
│  FCU confidence capped at 0.60 (advisory max).                                   │
└──────────────────────────────────┬──────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                   8. PERSISTENCE & LIFECYCLE                                     │
│                                                                                  │
│  • Saved to `recommendations` table with action, tier, confidence               │
│  • Operator can approve (→ execution) or reject (→ rejection learning)          │
│  • Executed recs enter M&V verification pipeline                                │
│  • Validation outcomes update progression engine class readiness                │
└─────────────────────────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                   9. PROGRESSION ENGINE (SAE Trust Ladder)                       │
│                                                                                  │
│  Level 0 ─── Shadow     ─── Observe only, no output                             │
│  Level 1 ─── Advisory   ─── Recommendations visible, no execution               │
│  Level 2 ─── Supervised ─── Tier 2 pending_approval, human must approve         │
│  Level 3 ─── Autonomous ─── Tier 3 auto_executes proven-safe actions            │
│                                                                                  │
│  Per-class readiness tracked: evidence_count, accuracy_7d/30d,                   │
│  consecutive_successes/failures, operator_overrides, demotion_history            │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Layer 0: Telemetry & Data Gathering

### Entry Point

```
AIOptimizerService.analyze_building(site_id, current_conditions=None)
```

### Data Sources

| Source | Method | Data |
|--------|--------|------|
| **BACnet Bridge** | `device_manager.list_devices_by_site()` | All equipment with live point values |
| **Site Aggregate** | `_gather_current_conditions()` | `site_aggregate`, `electrical`, `indoor_temp`, `outdoor_temp`, `humidity` |
| **Weather** | `weather_service.get_weather_forecast()` | 4-hour forecast: temp, humidity, conditions |
| **Energy Pricing** | `_get_energy_prices()` | TOU rates: peak, standard, off-peak |
| **Occupancy Fusion** | `security_occupancy_service.get_fused_occupancy()` | Fused 0-100% from badge + CO2 + PIR + schedule |
| **DALI Lighting** | `lighting_service.get_all_zones()` | Per-zone occupancy, dim level, lux, faults |
| **ML Models** | `_gather_ml_context()` | Anomaly scores, load forecasts, health trends |
| **Decision Memory** | `decision_memory_service` | Past outcomes, feedback rates, success patterns |
| **Work Orders** | `work_order_repository` | Active urgent/critical WOs for equipment |

### The `current_conditions` Dict

Every downstream layer reads from this single enriched dictionary:

```python
{
    "timestamp": "2026-07-10T10:00:00+02:00",
    "site_aggregate": {
        "total_occupancy": 0,
        "occupied_zones": 0,
        "zone_count": 20,
    },
    "electrical": {
        "hvac_kw": 68.73,
        "total_kw": 80.92,
        "solar_kw": 12.5,
        "bess_soc": 86,          # BESS state of charge
        "bess_dispatching": False,
    },
    "indoor_temp": 22.0,
    "outdoor_temp": 14.5,
    "humidity": 55,
    "indoor_avg_temp": 22.0,
    "zone_occupancy": {"Zone-L12-N": 60, "Zone-L11-S": 0},
    "_fused_occupancy": FusedOccupancy(occupancy_percent=0, ...),
    "_plant_enable_mappings": {"S002-AHU-B1-001": "AHU-1_Enable", ...},
    "_fault_gate_context": {...},
    "_served_zone_gate_context": {...},
}
```

### Site Profile

The site profile (`sites` table + `optimization_settings`) provides building-specific configuration:

```python
{
    "id": "site-002",
    "name": "Sandton City Office Tower",
    "type": "commercial",
    "sqm": 12000,
    "floors": 12,
    "region": "Gauteng",
    "operating_hours": {"start": "08:00", "end": "18:00"},
    "optimization_enabled": True,
    "site_peak_kw": 750.0,
}
```

---

## 4. Layer 1: Safety & Policy Gates

These gates execute **before** any LLM or rule-based optimization. They are deterministic and fail-closed.

### 4.1 Operating-State Gate

**File:** `ai_optimizer.py` → `_append_after_hours_zero_occupancy_advisory()` (line 3731)

**Purpose:** Detect when HVAC is running despite the building being closed/empty.

**Logic:**

```
IF outside operating hours
AND aggregate occupancy is zero (or ≤1 incidental)
AND HVAC load > site-specific threshold (default: site_peak_kw × 0.0033)
THEN → emit shutdown/setback advisory, SKIP full optimization
```

**Occupancy conflict path:**

```
IF outside operating hours
AND aggregate occupancy is zero
AND fused occupancy says "occupied" (CO₂ conflict)
AND aggregate is truly zero (NOT incidental)
THEN → emit zone-scope advisory instead of blanket shutdown
     → "Block blanket site HVAC shutdown; switch off only verified-empty zones"
```

**Key threshold:** `after_hours_hvac_threshold = max(2.5, site_peak_kw × 0.0033)`

When this gate fires, the function returns immediately with a policy recommendation — the LLM is never invoked.

### 4.2 Fault Gate

**File:** `ai_optimizer.py` → `_load_fault_gate_context()` (line 4613)

**Purpose:** Remove equipment with active critical/high alerts or urgent work orders from optimization scope.

**Logic:**
1. Query active alerts and work orders for the site
2. For any equipment with `severity == critical|high` OR urgent work order → mark as suppressed
3. Filter suppressed equipment from the inventory passed to the LLM
4. Generate advisory recommendations for suppressed equipment ("Cannot optimize — alert active")

**Injected into prompt:** Suppressed equipment codes are listed so the LLM doesn't reference them.

### 4.3 Served-Zone Gate

**File:** `ai_optimizer.py` → `_load_served_zone_gate_context()` (line 4161)

**Purpose:** When all zones served by an AHU/FCU are verified empty, suppress runtime-tuning recommendations for that equipment.

**Logic:**
1. Check each AHU's served zones for occupancy telemetry
2. If all served zones report empty AND telemetry is fresh ⇒ suppress AHU runtime tuning
3. If any served zone is occupied OR telemetry is stale ⇒ allow optimization

### 4.4 Quality Gate Evaluator (Data Credibility)

**File:** `quality_gate_evaluator.py`, `quality_gate_policy.py`

**Purpose:** Before the optimizer runs, validate that telemetry is credible.

| Gate | What It Checks |
|------|---------------|
| `pinned_signal_pct` | % of sensor signals that appear frozen (no variance) |
| `telemetry_freshness` | Age of newest telemetry per equipment type |
| `data_completeness` | % of expected points reporting values |
| `data_quality_score` | Aggregate data quality 0-100 |

If `pinned_signal_pct >= threshold` (varies by site mode: 0.50 shadow, 0.35 advisory, 0.25 supervised), the optimizer run is blocked or demoted.

---

## 5. Layer 2: Pre-Computed Waste Opportunities

**File:** `context_precompute_service.py`

**Purpose:** Before the LLM sees the data, the system pre-computes known waste patterns and injects them into the prompt as concrete triggers.

### Detected Patterns

| Pattern | Trigger Logic |
|---------|--------------|
| After-hours HVAC running | Non-zero HVAC load × building closed × zero occupancy |
| Free cooling opportunity | Outdoor temp ≤ indoor temp − 3°C × HVAC running |
| Over-lit unoccupied zone | Lux > 500 × occupancy < 10% × dim level > 50% |
| FCU valve hunting | Valve position oscillation detected in recent window |
| Chiller staging mismatch | Number of chillers running × load < single chiller capacity |
| Peak demand breach | Current kW > 90% of NMD limit |
| Solar curtailment | Solar generation < capacity × irradiance > 80% |
| BESS dispatch window | TOU peak × SOC > 50% × not currently dispatching |

### ML Model Context

Also injected: anomaly alerts, load forecasts, equipment health trends, and occupancy predictions from the ML pipeline (`ml/`).

---

## 6. Layer 3: The LLM Optimizer (5-Layer Prompt)

**File:** `ai_optimizer.py` → `_build_optimization_prompt()` (line 3164)

This is the core reasoning engine. It constructs a structured prompt sent to Claude via `model_gateway.py`.

### The 5-Layer Prompt Structure

```
┌═══════════════════════════════════════════════════════════════┐
│  LAYER 1 — ACTIVE GOAL                                        │
│  "Current time: Thursday 10:00 SAST — Occupied hours          │
│   Live occupancy: 0% (but CO₂ conflict detected)              │
│   Active profile: COST SAVING                                 │
│   Current tariff: R3.01/kWh (peak)"                           │
├───────────────────────────────────────────────────────────────┤
│  LAYER 2 — WASTE OPPORTUNITIES (pre-computed)                 │
│  • Free cooling: outdoor 14.5°C vs indoor 22.0°C             │
│  • HVAC load 68.73 kW = 84.9% of site load (above 75%)       │
│  • Solar generation 12.5 kW at 78% capacity                   │
├───────────────────────────────────────────────────────────────┤
│  LAYER 2b — FULL BUILDING TELEMETRY                           │
│  "S002-AHU-B1-001: sat_setpoint=18°C, plant_enable=1          │
│   S002-CHILLER-B1-001: chilled_water_setpoint=7.3°C           │
│   S002-FCU-101: room_temp=22°C, setpoint=22°C, fan=2"         │
├───────────────────────────────────────────────────────────────┤
│  LAYER 3 — LEARNED PATTERNS                                    │
│  • This time-of-day: avg HVAC load 65 kW, free cooling 3/5   │
│  • Feedback: HVAC actions 54% success rate, R-1.41 avg       │
│  • Decision memory: "2026-07-05 free cooling → R-39.37"      │
├───────────────────────────────────────────────────────────────┤
│  LAYER 4 — CONSTRAINTS & MODULE PERMISSIONS                   │
│  • Allowed action types: hvac_setpoint_change, lighting_dim   │
│  • Blocked equipment codes: [] (none faulted)                 │
│  • Write whitelist: plant_enable, sat_setpoint, damper        │
├───────────────────────────────────────────────────────────────┤
│  LAYER 5 — TASK INSTRUCTION                                    │
│  "Find efficiency opportunities. Format as JSON array.         │
│   Use ONLY exact point names from SIMBIOT control points.      │
│   No writable point → point=null advisory (NOT no_action).     │
│   HVAC load >75% + no recommendation = failure."               │
└───────────────────────────────────────────────────────────────┘
```

### Data Sections Injected Between Layers

| Section | Content | Source |
|---------|---------|--------|
| Building context | Name, type, size, floors, operating hours | `site` dict |
| Current conditions | Indoor/outdoor temp, humidity, occupancy, equipment status | `current_conditions` |
| Weather forecast | 4-hour temperature + condition forecast | `weather_service` |
| Energy pricing | Current rate, peak/standard/off-peak | `pricing_engine` |
| Equipment inventory | All equipment by type (HVAC, lighting, power, solar, BESS, meter) | `equipment_inventory` |
| Available control points | All writable points by equipment | Device model + point_asset_mappings |
| Verified SIMBIOT writable | Canonical writable points from SIMBIOT mappings | `point_asset_mappings` DB |
| Zone context | Per-zone occupancy, daylight, over-lit status | Lighting service |

### Model Gateway

```python
response = await model_gateway.chat(
    model="claude-sonnet-4-20250514",
    messages=[{"role": "user", "content": prompt}],
    max_tokens=4000,
)
```

The response is parsed as JSON with `recommendations[]` array and `no_action_reasons[]`.

### Post-Processing

After LLM response:
1. Parse JSON (with error recovery for malformed responses)
2. Validate equipment codes against known inventory
3. Map action_type from system field (19 domain types)
4. Score and rank by profile weights
5. Apply confidence caps (FCU max 0.60)

---

## 7. Layer 4: Rule-Based Recommendations

**Files:** `zone_scope_decomposer.py`, `lighting_service.py`

### Zone-Scope HVAC Decomposer

After the LLM generates building-level recs, the zone decomposer generates **per-zone** HVAC recommendations:

```
LLM: "Shut down HVAC in unoccupied areas"
                          ↓
Zone decomposer:
  ┌─ S002-FCU-101 (Zone L1-A): room_temp=22, occupancy=0% → setpoint=18°C (setback)
  ├─ S002-FCU-102 (Zone L1-B): room_temp=23, occupancy=0% → setpoint=18°C (setback)
  ├─ S002-VAV-001 (Zone L1-C): occupancy=60% → no change
  └─ S002-FCU-201 (Zone L2-A): room_temp=21, occupancy=0% → setpoint=18°C (setback)
```

### Lighting Rule Engine

| Rule | Logic |
|------|-------|
| Unoccupied zone dimming | Occupancy < 10% → dim to 30% or scene "Standby" |
| Daylight harvesting | Lux > 500 on occupied zone → dim until lux ≈ 400 |
| Cross-system savings | Combine HVAC setback + lighting dim in same zone |

### Coordinated Optimization Planner

**File:** `coordinated_optimization_planner.py`

Combines HVAC and lighting actions into cross-system recommendations with combined savings estimates:

```python
{
    "zone_id": "Zone-L11-S",
    "hvac_action": "Setback setpoint to 18°C",
    "lighting_action": "Dim to 30% (Tridonic native)",
    "sentinel_action": "Pre-cool before tariff peak",
    "combined_savings_kw": 2.4,
}
```

---

## 8. Layer 5: Zone-Scope Decomposition

**File:** `zone_scope_decomposer.py`

**Purpose:** Convert building-level policy recs ("shut down empty zones") into per-equipment executable recs.

### Flow

```
Policy recommendation (after-hours shutdown)
  ↓
For each zone with occupancy data:
  ↓
  If zone empty → generate FCU setback rec with specific setpoint
  If zone occupied → skip (comfort preservation)
  ↓
Merge zone recs with LLM recs
  ↓
Return combined recommendation list
```

---

## 9. Layer 6: Quality Gates & Post-Processing

**File:** `quality_gate_evaluator.py`

After recommendations are generated but before they're persisted, quality gates validate the data supporting each recommendation:

### Gate Matrix

| Gate | Block Threshold | Warn Threshold | Checks |
|------|----------------|---------------|--------|
| `telemetry_freshness` | > 60 min stale | > 30 min stale | Latest BACnet read |
| `pinned_signal_pct` | ≥ 0.50 (shadow) / 0.35 (advisory) / 0.25 (supervised) | ≥ half of block | Frozen sensor ratio |
| `data_completeness` | < 60% expected points | < 80% | Point coverage |
| `data_quality_score` | < 40/100 | < 60/100 | Aggregate quality |

### Post-LLM Quality Gate

**File:** `ai_optimizer.py` → `_apply_quality_gate()` (called after `_analyze_with_claude`)

Validates each recommendation:
- Equipment code exists in inventory
- Point name is writable (or explicitly point=null advisory)
- Confidence is within expected range
- No contradictory recommendations for same equipment

---

## 10. Layer 7: Tier Routing (Confidence-Based)

**File:** `optimization_tier_router.py`

### Routing Matrix

| Confidence | Routing Tier | `supervised` action | `auto_execute` action |
|-----------|-------------|-------------------|---------------------|
| < 0.30 | BLOCKED | `blocked` | `blocked` |
| 0.30 – 0.60 | Tier 1 (Advisory) | `advisory` | `advisory` |
| 0.60 – 0.85 (tier2) / 1.00 (tier3) | Tier 2 (Approval) | `pending_approval` | `pending_approval` |
| ≥ threshold | Tier 3 (Auto) | `pending_approval` | `auto_execute` |

### Threshold Reweighting (Phase B)

When `class_readiness` is provided (from progression engine), thresholds shift based on the recommendation class's trust level:

| Trust Level | Tier 1 Min | Tier 2 Min | Tier 3 Min |
|------------|-----------|-----------|-----------|
| 1 (Advisory) | 0.30 | 0.60 | 1.00 (unreachable) |
| 2 (Supervised) | 0.30 | 0.60 | 0.60 |
| 3 (Autonomous) | 0.30 | 0.60 | 0.75 |

### FCU Confidence Cap

All FCU recommendations have confidence capped at 0.60 (advisory max). Rationale: per-FCU sensors often lack precision, and FCU-level auto-execution risk is high without zone-level verification.

```python
if equipment_type in ("fcu", "FCU"):
    confidence = min(confidence, 0.60)
```

---

## 11. Layer 8: Progression Engine (SAE Trust Ladder)

**File:** `progression_engine_service.py`

The progression engine implements an SAE-style autonomy ladder for building operations:

| Level | Name | Behavior |
|-------|------|----------|
| 0 | Shadow | Observe only. Recommendations tracked but not displayed. ML runs in shadow mode. |
| 1 | Advisory | Recommendations visible to operator. No execution path. Tier 2/3 unreachable. |
| 2 | Supervised | Tier 2 recommendations require operator approval. Tier 3 blocked. |
| 3 | Autonomous | Tier 3 recommendations auto-execute. Tier 2 still pending_approval. |

### Per-Class Readiness

Each recommendation class (e.g., `hvac_setpoint_change`, `lighting_dim`, `bess_dispatch`) has independent readiness tracked:

```python
{
    "class_name": "hvac_setpoint_change",
    "current_trust_level": 2,          # 0-3
    "evidence_count": 47,               # validated recommendations
    "accuracy_pct_7d": 0.82,            # rolling 7-day accuracy
    "accuracy_pct_30d": 0.79,           # rolling 30-day accuracy
    "consecutive_successes": 5,
    "consecutive_failures": 0,
    "last_demotion_at": None,           # 7-day cool-off
    "demotion_reason": None,
}
```

### Promotion Gates

A class promotes to the next level when:

| Promotion | Requirements |
|-----------|-------------|
| Shadow → Advisory | Minimum 10 validated recs + accuracy > 0.70 |
| Advisory → Supervised | Minimum 30 validated recs + accuracy > 0.75 + no recent demotion |
| Supervised → Autonomous | Minimum 100 validated recs + accuracy > 0.80 + consecutive 10 successes |

### Demotion Triggers

| Trigger | Condition | Action |
|---------|-----------|--------|
| Accuracy drop (L3) | accuracy_30d < 0.60 | Demote to Level 2 |
| Accuracy drop (L2) | accuracy_30d < 0.50 | Demote to Level 1 |
| Consecutive failures | 5 in a row | Demote one level |
| Equipment damage | Operator-reported | Demote to Level 0 |
| Comfort violation | Occupant complaint | Demote to Level 1 |

Cool-off: 7 days before a demoted class can be reconsidered for re-promotion.

### Override

Operators can manually set `operator_override_level` per class, bypassing the automatic progression for that class. Audited.

---

## 12. Layer 9: Execution & Control

**File:** `execution_service.py`, `sentinel_write_whitelist.py`, `device_control_service.py`

### Write Whitelist

**File:** `sentinel_write_whitelist.py`

Every autonomous write passes through the whitelist defined in `data/policies/sentinel_write_whitelist.json`:

| Equipment Type | Allowed Writable Points |
|---------------|----------------------|
| AHU | `plant_enable`, `sat_setpoint`, `damper_position`, `fan_speed_setpoint`, `ahu_on_off` |
| CHILLER | `chilled_water_setpoint`, `chiller_stage`, `chiller_on_off` |
| VAV | `zone_temperature_setpoint`, `damper_position`, `vav_flow_setpoint` |
| FCU | `temperature_setpoint`, `fcu_mode`, `fcu_on_off` |
| DALI | `brightness`, `dimming_level`, `dali_scene` |
| BESS | `bess_dispatch`, `bess_charge_limit`, `bess_discharge_limit` |

### Execution Flow

```
Operator approves recommendation (or auto-execute for Tier 3)
  ↓
Validate: recommendation still valid? confidence still above threshold?
  ↓
Check write whitelist: is equipment.point allowed?
  ↓
Check SIMBIOT mapping: is there a verified point_asset_mapping?
  ↓
Execute via device_control_service.write_value(device_id, point, value)
  ↓
Log outcome → M&V verification pipeline
```

---

## 13. Layer 10: M&V Verification & Feedback Loop

### Measurement & Verification

**File:** `mv_verification_service.py`

After a recommendation is executed, M&V tracks the actual delta:

```
Before: setpoint = 22°C, room_temp stable at 22°C
Action: setpoint → 20°C
After:  room_temp stabilizes at 20.5°C (actual delta = -1.5°C)
Accuracy: predicted_delta{-2.0°C} vs actual_delta{-1.5°C} = 0.83
```

### Decision Memory

**File:** `decision_memory_service.py`

Every outcome (success, failure, negative savings, operator rejection) is stored and surfaces in future LLM prompts:

```python
{
    "equipment_id": "S002-AHU-B1-001",
    "action_type": "sat_setpoint_increase",
    "outcome": "negative_savings",
    "cost_impact": -39.37,
    "time_of_day": "14:00",
    "day_of_week": "Tuesday",
}
```

### Rejection Learning

**File:** `rejection_learning_service.py`

When an operator rejects a recommendation, the rejection reason is learned:
- "too risky for this equipment type" → lower confidence for similar recs
- "wrong time of day" → suppress during that time window
- "occupant complained" → mark as comfort risk

### Class Readiness Update

After validation, the progression engine recalculates rolling accuracy and checks demotion/promotion triggers:

```python
engine = ProgressionEngineService()
await engine.record_validation(
    recommendation_id="rec-123",
    actual_delta={"temperature_c": -1.5},
    operator_feedback="accepted",
)
# → auto-recomputes class readiness for hvac_setpoint_change
```

---

## 14. Data Flow Diagrams

### 14.1 Full Optimization Cycle

```
┌──────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐
│ Scheduler │────▶│  Gate    │────▶│  LLM     │────▶│  Rules   │
│ (15 min)  │     │  Layer   │     │  Opt     │     │  Engine  │
└──────────┘     └──────────┘     └──────────┘     └──────────┘
                                                     │
                                                     ▼
               ┌──────────┐     ┌──────────┐     ┌──────────┐
               │ Execution│◀────│  Tier    │◀────│  Quality │
               │          │     │  Router  │     │  Gates   │
               └────┬─────┘     └──────────┘     └──────────┘
                    │
                    ▼
               ┌──────────┐     ┌──────────┐     ┌──────────┐
               │  M&V     │────▶│ Decision │────▶│ Progress │
               │  Verify  │     │  Memory  │     │  Engine  │
               └──────────┘     └──────────┘     └──────────┘
```

### 14.2 Decision Tree (per optimization cycle)

```
analyze_building(site_id)
│
├── Load site profile, equipment inventory, current conditions
│
├── Operating-State Gate
│   ├── IF outside hours + zero occupancy + HVAC running
│   │   → Return shutdown advisory (skip LLM)
│   │
│   ├── IF outside hours + zero agg occupancy + fused conflict
│   │   → Return zone-scope conflict advisory (skip LLM)
│   │
│   └── ELSE → continue
│
├── Fault Gate
│   ├── IF equipment has critical alert
│   │   → Suppress from optimization, create advisory
│   └── Continue with filtered inventory
│
├── Pre-compute waste opportunities
│
├── Build 5-layer LLM prompt
│
├── Call Claude via model_gateway
│   ├── Success → parse JSON recommendations
│   └── Failure → fall back to rule-only recommendations
│
├── Append rule-based recommendations (zone scope, lighting)
│
├── Apply quality gates (pinned signals, freshness, completeness)
│   ├── GATE FAIL → demote / block affected recommendations
│   └── PASS → continue
│
├── Score & rank by profile weights
│
├── Tier routing (confidence → action: advisory/approval/auto)
│
├── Persist recommendations to DB
│
└── Return OptimizationRecommendation
```

### 14.3 Recommendation Lifecycle

```
DRAFT ──→ PENDING ──→ APPROVED ──→ EXECUTING ──→ EXECUTED ──→ VERIFIED
  │          │            │                             │
  │          │            ├── REJECTED                  │
  │          │            │     ↓                       │
  │          │            │  Rejection Learning         │
  │          │            │                             │
  │          │            └── EXPIRED (timeout)         │
  │          │                                          │
  │          └── DISCARDED (gate fail)                  │
  │                                                     │
  └── FAILED (parsing error)
```

---

## 15. Key Services Reference

| Service | File | Role |
|---------|------|------|
| `AIOptimizerService` | `ai_optimizer.py` | Core orchestrator: gates, prompt, LLM, rules |
| `ProgressionEngineService` | `progression_engine_service.py` | SAE trust ladder, class readiness, demotion |
| `OptimizationTierRouter` | `optimization_tier_router.py` | Confidence → action tier routing |
| `QualityGateEvaluator` | `quality_gate_evaluator.py` | Pre-execution data quality validation |
| `SentinelWriteWhitelist` | `sentinel_write_whitelist.py` | Point-level write permission gating |
| `ZoneScopeDecomposer` | `zone_scope_decomposer.py` | Per-zone HVAC recommendation generation |
| `ContextPrecomputeService` | `context_precompute_service.py` | Pre-computed waste opportunity detection |
| `DecisionMemoryService` | `decision_memory_service.py` | Past outcome storage for LLM context |
| `CoordinatedOptimizationPlanner` | `coordinated_optimization_planner.py` | Cross-system HVAC+lighting coordination |
| `MVVerificationService` | `mv_verification_service.py` | Post-execution delta tracking |
| `RejectionLearningService` | `rejection_learning_service.py` | Learning from operator rejections |
| `PinnedSignalDetector` | `pinned_signal_detector.py` | Frozen/broken sensor detection |
| `OccupancyFusionService` | `occupancy_fusion_service.py` | Multi-signal occupancy fusion |
| `ModelGateway` | `model_gateway.py` | LLM provider abstraction layer |
| `RecommendationService` | `recommendation_service.py` | CRUD + lifecycle management |
| `ProfileService` | `profile_service.py` | Optimization profile (cost savings / comfort) |
| `ExecutionService` | `execution_service.py` | Device write execution |
| `BackgroundScheduler` | `background_scheduler.py` | Cron-driven optimization cycles |

---

## Appendices

### A. Environment-Specific Behavior

| Setting | Shadow | Advisory | Supervised | Autonomous |
|---------|--------|----------|------------|------------|
| Recommendations persisted | No | Yes | Yes | Yes |
| Operator visible | No | Yes | Yes | Yes |
| Tier 3 auto-execute | No | No (blocked) | No (→ approval) | Yes |
| Tier 2 approval | No | No (blocked) | Yes (required) | Yes (required) |
| FCU confidence cap | 0.60 | 0.60 | 0.60 | 0.60 |
| Min evidence for promotion | — | 10 | 30 | 100 |

### B. Key Configuration Constants

```python
# ai_optimizer.py
AFTER_HOURS_INCIDENTAL_OCCUPANCY_MAX_PCT = 15.0  # % of zones
FCU_CONFIDENCE_CAP = 0.60

# optimization_tier_router.py
_THRESHOLDS_BY_LEVEL = {
    1: (0.30, 0.60, 1.00),  # Advisory: tier3 unreachable
    2: (0.30, 0.60, 0.60),  # Supervised: tier2 = tier3 threshold
    3: (0.30, 0.60, 0.75),  # Autonomous: tier3 requires 0.75
}

# quality_gate_policy.py
PINNED_SIGNAL_MAX_PCT = {
    "shadow": 0.50, "advisory": 0.35, "supervised": 0.25,
}
TELEMETRY_FRESHNESS_MAX_MINUTES = 60
DATA_COMPLETENESS_MIN_PCT = 0.60
```

### C. Action Types

The `action_type` field in recommendations maps to 19 domain types:

| action_type | Example |
|------------|---------|
| `hvac_setpoint_change` | Raise/lower temperature setpoint |
| `hvac_mode_change` | Switch AHU from auto to manual |
| `hvac_plant_enable` | Enable/disable AHU plant |
| `hvac_fan_speed` | Adjust fan speed on FCU/AHU |
| `hvac_valve_position` | Adjust valve position |
| `hvac_damper_position` | Adjust VAV damper |
| `lighting_dim` | Dim/turn off lighting |
| `lighting_scene` | Apply lighting scene |
| `bess_dispatch` | Charge/discharge battery |
| `solar_curtail` | Curtail solar inverter |
| `generator_start` | Start/stop generator |
| `demand_response` | Load shed event |
| `peak_shaving` | Peak demand reduction |
| `free_cooling` | Economizer mode |
| `schedule_adjust` | Change operating schedule |
| `occupancy_setback` | HVAC setback for unoccupied |
| `valve_protection` | Minimum position to prevent seizure |
| `chiller_staging` | Add/remove chiller stage |
| `pump_speed` | Adjust VFD pump speed |

---

> **Related Docs:** [`docs/02-architecture/`](../02-architecture/) | [`CLAUDE_DATABASE.md`](../../CLAUDE_DATABASE.md) | [`docs/03-api-reference/recommendations.md`](./recommendations.md)
