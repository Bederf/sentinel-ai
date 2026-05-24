---
title: "Demand-Aware Coordinator"
type: "feature"
status: "active"
version: "1.0.0"
created: "2026-05-24"
updated: "2026-05-24"
tags: ["coordinator", "peak-shaving", "nmd", "multi-module", "bess", "hvac", "demand-management"]
domain: "energy"
audience: "developers", "operations"
complexity: "intermediate"
estimated_read_time: 8
---

# Demand-Aware Coordinator

## Overview

**Source:** `backend/app/services/demand_aware_coordinator.py`

Cross-module orchestrator for peak demand shaving. Runs independently every 5 minutes to monitor NMD headroom and coordinate actions across active modules (BESS, HVAC, Energy, Lighting).

**Module-agnostic** — discovers available modules at runtime via the module registry and adapts its shaving plan accordingly.

## Algorithm

### 1. Demand Assessment

Poll `SolarDemandService.get_current_demand()` to get:
- `current_demand_kw`
- `nmd_limit_kva` (from Supabase `buildings.nmd_limit_kva`, fallback 1,820 kVA)
- `demand_trend` (rising/stable/falling)

```
headroom_kw      = nmd_limit - current_demand
headroom_percent = headroom_kw / nmd_limit × 100
```

### 2. Urgency Classification

| Headroom | Urgency | Priority | Action |
|----------|---------|----------|--------|
| < 5% | **critical** | CRITICAL | Emergency shaving — restore to 20% headroom |
| 5-15% | **warning** | HIGH | Emergency shaving — restore to 20% headroom |
| 15-25% | **caution** | MEDIUM | Preventive shaving — restore to 25% headroom |
| ≥ 25% | **normal** | LOW | TOU guidance only (if SOLAR module active) |

### 3. Required Reduction

**Emergency** (headroom < 15%):
```
target_headroom_kw  = nmd_limit × 0.20    # 20% safety buffer
required_reduction  = current_demand - target_headroom_kw
```

**Preventive** (headroom 15-25%):
```
target_headroom_kw  = nmd_limit × 0.25    # 25% safety buffer
required_reduction  = current_demand - target_headroom_kw
```

### 4. Multi-Module Dispatch Priority

Once `required_reduction_kw` is known, the rule-based planner dispatches in priority order:

| Priority | Module | Action | Capacity | Notes |
|----------|--------|--------|----------|-------|
| 1st | **SOLAR** (BESS) | Discharge 100-200 kW | 100-200 kW | Immediate, ~60 min duration |
| 2nd | **HVAC** | Increase setpoint 1-3°C | ~30 kW/°C | Comfort tolerance 2-3°C |
| 3rd | **ENERGY** | Defer pumps/compressors | ~25 kW | Non-critical equipment |
| 4th | **LIGHTING** | Dim to 60-80% | Moderate | Only if still needed |

Each module contributes up to its capacity until `required_reduction_kw` is met. The plan is routed to the approval workflow for human confirmation.

### 5. Normal Mode (TOU Arbitrage)

When headroom ≥ 25% and SOLAR module is active, the coordinator generates TOU arbitrage guidance via `SolarArbitrageEngine` instead of shaving.

## BESS Threshold Shaving

**Source:** `backend/app/services/solar_demand_service.py:793`

The real-time BESS shaving engine runs independently (event-driven, not part of the 5-min coordinator cycle):

| Condition | Action | Priority |
|-----------|--------|----------|
| `demand > 95% NMD` | Max BESS discharge: `min(BESS_RATED_POWER, demand - (NMD × 0.85))` | **critical** |
| `demand > 85% NMD` | BESS discharge: `min(BESS_RATED_POWER, demand - (NMD × 0.85))` | **high** |
| `demand > 85% NMD × 0.9` and rising | BESS on standby | **medium** |
| Below threshold | No action | **low** |

BESS peak shaving **always preempts TOU arbitrage** — when demand approaches NMD, the battery prioritizes shaving over energy trading.

## Data Flow

```
┌─────────────────┐     every 5 min     ┌──────────────────────────┐
│  SolarDemand    │◄───────────────────│  DemandAwareCoordinator  │
│  Service        │    get_current_     │                          │
│  (demand data)  │    demand()         │  evaluate_current_state  │
└─────────────────┘                     └──────────┬───────────────┘
                                                    │
                                      ┌─────────────┴─────────────┐
                                      │                           │
                                      ▼                           ▼
                              ┌───────────────┐         ┌──────────────────┐
                              │  Module       │         │  Approval        │
                              │  Registry     │         │  Service         │
                              │  (discover    │         │  (human approval │
                              │   active mods)│         │   routing)       │
                              └───────────────┘         └──────────────────┘
                                      │
                            ┌─────────┴─────────┐
                            │                   │
                            ▼                   ▼
                    ┌──────────────┐    ┌──────────────┐
                    │  AI Optimizer │    │  Rule-based  │
                    │  (demand-aware│    │  Planner     │
                    │   shaving)    │    │  (fallback)  │
                    └──────────────┘    └──────────────┘
```

## Configuration

NMD limit is sourced from `buildings.nmd_limit_kva` in Supabase. Fallback values:
- site-002 (Sandton City): 1,820 kVA
- Other sites: seeded during SIMBIOT onboarding from municipal bill data

## Related

- [Peak Demand Management API](../03-api-reference/peak-demand-api.md) — REST endpoints
- [Demand Ratchet Algorithm](12-demand-ratchet-algorithm.md) — 12-month rolling peak calculation
- [Demand Response Guide](demand-response-guide.md) — DDMP curtailable load signal
