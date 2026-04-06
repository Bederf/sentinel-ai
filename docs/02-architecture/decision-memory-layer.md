---
title: "Decision Memory Layer"
type: "architecture"
status: "draft"
version: "1.0.0"
created: "2026-03-31"
updated: "2026-03-31"
tags: ["sentinel", "documentation"]
related: []
domain: "bms"
audience: "all"
complexity: "intermediate"
estimated_read_time: 10
---

# Decision Memory Layer

**Phase 145** | **Status**: Implemented

## Overview

Decision Memory stores outcomes of diagnostic and control decisions so SENTINEL
learns from experience. Every resolved incident makes the next one faster.

```
Event → Reasoning → Action → Outcome
                                ↓
                        Decision Memory
                                ↓
                         Pattern Extraction
                                ↓
              Next similar event → Known cause + proven fix
```

## How It Works

### 1. Record Decision

When the AI diagnoses a fault or recommends an action:

```python
await svc.record_decision(
    event_type="temperature_deviation",
    equipment_id="S002-CHILLER-B1-001",
    equipment_type="CHILLER",
    site_id="site-002",
    diagnosis="condenser fouling",
    action_type="tube_cleaning",
)
```

### 2. Record Outcome

After the action is taken and results are observed:

```python
await svc.record_outcome(
    record_id="DM-20260305-a1b2c3d4",
    outcome=DecisionOutcome.RESOLVED,
    outcome_details="Pressure normalized after cleaning",
)
```

### 3. Automatic Pattern Extraction

When 3+ records share the same event_type + equipment_type + diagnosis with
≥50% success rate, a `DecisionPattern` is created:

```python
DecisionPattern(
    event_type="temperature_deviation",
    equipment_type="CHILLER",
    likely_diagnosis="condenser fouling",
    diagnosis_confidence=0.85,       # = success_rate
    recommended_action="tube_cleaning",
    total_occurrences=10,
    resolved_count=8,
    success_rate=0.80,
    avg_resolution_time_minutes=120,
)
```

### 4. Query Patterns

Next time a similar event occurs:

```python
pattern = await svc.get_recommended_action("temperature_deviation", "CHILLER")
# Returns: "condenser fouling → tube_cleaning (85% confidence, 10 occurrences)"
```

## AI Prompt Integration

Patterns are formatted for injection into AI prompts:

```
Historical Patterns:
  - temperature_deviation on CHILLER: likely condenser fouling
    (confidence 85%, 8/10 resolved). Action: tube_cleaning. Avg resolution: 120 min.

Recent Similar Decisions:
  - [resolved] S002-CHILLER-B1-001: condenser fouling -> tube_cleaning
    Note: Pressure normalized after cleaning
```

## Decision Record Fields

| Field | Description |
|-------|-------------|
| event_type | What triggered the decision |
| equipment_id/type | Which asset |
| diagnosis | Root cause determined |
| diagnosis_confidence | 0.0-1.0 |
| diagnosis_source | ai_reasoning, technician, ml_model, historical_match |
| action_type | setpoint_change, work_order, equipment_restart, etc. |
| outcome | resolved, partially_resolved, ineffective, worsened, pending |
| resolution_time_minutes | Time from action to resolution |
| season | summer, autumn, winter, spring (SA southern hemisphere) |
| time_of_day | morning, afternoon, evening, night |
| signals_snapshot | Telemetry at time of event |

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/decisions/record` | Record a new decision |
| PUT | `/api/decisions/{id}/outcome` | Record outcome |
| GET | `/api/decisions/history` | Decision history with filters |
| GET | `/api/decisions/patterns` | Learned patterns |
| GET | `/api/decisions/patterns/match` | Find matching patterns |
| GET | `/api/decisions/recommend` | Get recommended action |
| GET | `/api/decisions/stats` | Decision memory statistics |
| GET | `/api/decisions/{id}` | Specific decision record |

## Key Files

- `backend/app/models/decision_memory.py` — DecisionRecord, DecisionPattern, DecisionOutcome
- `backend/app/services/decision_memory_service.py` — Recording, pattern extraction, querying
- `backend/app/data/decision_memory/` — JSON storage (records + patterns)
- `backend/app/api/decision_memory.py` — API router
- `backend/tests/services/test_decision_memory.py` — 16 tests
- `backend/tests/services/test_phase145_wiring.py` — 16 wiring tests

## Wiring (Active)

- **HybridContext**: `_gather_decision_memory()` pulls learned patterns and recent similar
  decisions into the AI prompt (Step 6 in `query()` flow). Only includes verified outcomes
  with ≥50% success rate. Never overrides live telemetry or safety policy.

## Pattern Extraction Rules

- **Threshold**: 3+ records required before creating a pattern
- **Success rate**: Must be ≥50% to create a pattern
- **Grouping**: event_type + equipment_type + diagnosis
- **Auto-update**: Patterns updated automatically when new outcomes are recorded
- **Cross-site**: Patterns apply across sites unless limited

## Integration Points

- **Event Intelligence**: Events trigger decisions (via correlation_id)
- **HybridContext**: Decision patterns enriched into AI context
- **AI Optimizer**: `format_for_prompt()` injects history into Claude prompts
- **Sentry Bot**: Technician outcome reports feed back into decision memory
- **Work Orders**: WO completion triggers outcome recording
