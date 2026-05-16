---
title: "AI Optimization Pipeline"
type: "technical"
status: "updated"
version: "2.0.0"
created: "2026-05-16"
---

# AI Optimization Pipeline

## Architecture

The AI Optimization pipeline (`AIOptimizerService`) generates holistic building optimization recommendations. It runs on a 30-minute cycle gated by a multi-signal condition-change detector.

## Pipeline Stages

### 1. Data Collection (`_gather_current_conditions`)

| Source | Data |
|--------|------|
| Bridge telemetry | Power (total_kw, hvac_kw, lighting_kw, solar_kw) |
| Device manager | Equipment status, zone temperatures |
| IPMVP tables | Energy baseline for comparison |
| Tariff config | TOU bands and rates |
| Site modules | Active module types |
| Equipment table | Health scores, statuses, ages |

### 2. Carbon Context (`_gather_carbon_context`)

Calculated from existing electrical telemetry using Eskom 2024 published grid intensity (0.9 kgCO2/kWh):

- `building_kgco2_hour` = grid_import_kw × 0.9
- `renewable_fraction_pct` = solar_kw / total_kw
- `solar_offset_kgco2_hour` = solar_kw × 0.9
- `carbon_vs_baseline_kgco2` = variance from IPMVP baseline

Injected into LLM prompt as `CARBON & ESG` block.

### 3. LLM Analysis (`_analyze_with_claude`)

Prompt includes:
- Equipment inventory with health scores
- Current telemetry (power, chiller, AHU, security)
- Carbon/ESG context
- Tariff rates and TOU schedule
- Site operating hours
- Decision memory (success rates from past actions)
- Active optimization profile (cost_saving, comfort_first, balanced, asset_preservation)
- Pre-computed waste flags from FCU state tracker

LLM returns JSON with recommendations, each including:\
`saving` (text, parsed to `expected_impact.cost_zar`)\
`carbon_saving` (text, e.g. "1.2 kgCO2 this evening")

### 4. Condition-Change Gate (Scheduler)

Before calling the LLM, the scheduler checks 5 signals from bridge telemetry:

| Signal | Threshold | Triggers |
|--------|-----------|----------|
| Power delta | >5% change in total_kw | Yes |
| Tariff band | Peak/Standard/Off-peak transition | Yes |
| Occupancy | Crosses 10%, 50%, or 80% threshold | Yes |
| Outdoor temp | >3°C change | Yes |
| Occupied hours | First cycle after 07:00 weekday | Yes |

If none triggered, the LLM call is skipped. The 30-minute interval provides a minimum cadence regardless.

### 5. Recommendation Filtering

- **Cap**: Max 3 recommendations per cycle
- **DALI filter**: Removes DALI controller recommendations (handled autonomously)
- **Safety validation**: Checks control points against safety interlocks
- **Quality gate**: Flags low-confidence recs but doesn't block
- **Deduplication**: 48-hour window per equipment+action combo

### 6. Phase Gating

| Phase | Generation | UI Display | Approve/Reject |
|-------|-----------|------------|----------------|
| Shadow | ❌ No | N/A | N/A |
| Advisory | ✅ Yes | "Review and apply manually in BMS" | ❌ Hidden |
| Supervised | ✅ Yes | Full card with Approve/Reject | ✅ Visible |
| Auto | ✅ Yes | Full card with auto-execute status | ❌ Hidden |

### 7. Notification

Recommendations are sent via the Sentry bot (Telegram). In advisory mode, notification text uses "advisory — apply manually" language.

## Daily Volume

Expected: **5-8 recommendations per day** with the current gating:

- 07:00 SAST — occupied hours start → 1 recommendation
- 07:00-10:00 peak tariff → 1-2
- 10:00 standard tariff → 0-1
- 14:00-18:00 afternoon → 1-2
- 18:00 off-peak + building emptying → 1-2

## Key Files

| File | Purpose |
|------|---------|
| `backend/app/services/ai_optimizer.py` | Core optimizer service |
| `backend/app/services/background_scheduler.py` | Scheduling + condition gate |
| `backend/app/services/context_precompute_service.py` | FCU waste pre-computation |
| `backend/app/services/fcu_state_tracker.py` | Zone-level FCU tracking |
| `backend/app/services/health_snapshot_service.py` | Health scoring |
| `backend/app/database/repositories/recommendation_repository.py` | Persistence |

## Related

- [Health Scoring System](health-scoring-system.md)
- [Equipment Naming Convention](../02-architecture/EQUIPMENT_NAMING.md)
- [Phase Policy](109C-site-002-mode-policy-dry-run.md)
