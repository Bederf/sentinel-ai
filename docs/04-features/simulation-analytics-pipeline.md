---
title: "Simulation Analytics Pipeline"
type: "guide"
status: "approved"
version: "1.0.0"
created: "2026-02-06"
updated: "2026-02-06"
author: "Sentinel Development Team"
tags: ["simulation", "analytics", "optimization", "profiles"]
domain: "general"
audience: "developers"
complexity: "intermediate"
estimated_read_time: 8
---

# Simulation Analytics Pipeline

Persists simulation events to JSONL log files and analyzes them through optimization profile lenses (asset sweating, comfort first, cost saving). Data stays in log files for offline analysis - no auto-feedback into the system.

## Overview

Every lifecycle simulation run automatically:

1. **Logs** all events to a JSONL file (one JSON line per event)
2. **Records** run metadata (scenario, timing, event counts) to a JSON file
3. **Generates** an analysis report scored against three optimization profiles

The pipeline is file-based (no database dependency), grep-able, and Grafana/Loki compatible.

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                    Lifecycle Orchestrator                        │
│  start() ──► SimulationLogger.start_run()                       │
│  events  ──► SimulationLogger.on_event()  ──► JSONL append      │
│  stop()  ──► SimulationLogger.end_run()   ──► finalize metadata │
│                                            ──► trigger analysis  │
└──────────────────────────────────────────────────────────────────┘
                              │
                              ▼
         ┌────────────────────────────────────────┐
         │        simulation_logs/ directory       │
         │                                        │
         │  {run_id}_events.jsonl   ← event data  │
         │  {run_id}_meta.json      ← run info    │
         │  {run_id}_analysis.json  ← report      │
         └────────────────────────────────────────┘
                              │
                              ▼
         ┌────────────────────────────────────────┐
         │          SimulationAnalyzer             │
         │                                        │
         │  compute_metrics() ── aggregate stats   │
         │  score_profile()   ── weighted scoring  │
         │  analyze_run()     ── full report       │
         └────────────────────────────────────────┘
                              │
                  ┌───────────┼───────────┐
                  ▼           ▼           ▼
          ┌────────────┐ ┌────────────┐ ┌────────────┐
          │   Asset    │ │  Comfort   │ │    Cost    │
          │  Sweating  │ │   First    │ │   Saving   │
          └────────────┘ └────────────┘ └────────────┘
```

## Optimization Profiles

Profiles are defined in `backend/app/data/optimization_profiles.json`. Each profile assigns weights (summing to 1.0) across five dimensions:

| Dimension | Asset Sweating | Comfort First | Cost Saving |
|-----------|---------------|---------------|-------------|
| Runtime | 0.35 | 0.10 | 0.10 |
| Comfort | 0.10 | 0.40 | 0.15 |
| Cost | 0.15 | 0.10 | 0.35 |
| Maintenance | 0.10 | 0.20 | 0.10 |
| Energy | 0.30 | 0.20 | 0.30 |

### Asset Sweating
Maximize equipment utilization and defer replacements. Accepts higher maintenance risk for greater runtime. Flags under-utilized equipment.

### Comfort First
Prioritize occupant comfort with tight temperature bands and fast fault response. Flags MTTR above 1 hour and comfort deviations.

### Cost Saving
Minimize operational spend. Favors load shifting, reduced runtime, and energy optimization. Flags excessive energy events and runtime hours.

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/simulation-analytics/runs` | GET | List all simulation runs |
| `/api/simulation-analytics/runs/{run_id}` | GET | Get run metadata |
| `/api/simulation-analytics/runs/{run_id}/events` | GET | Read events (filter, paginate) |
| `/api/simulation-analytics/runs/{run_id}/analysis` | GET | Get or generate analysis |
| `/api/simulation-analytics/runs/{run_id}/analysis/{profile}` | GET | Single profile analysis |
| `/api/simulation-analytics/runs/{run_id}/analyze` | POST | Re-analyze with custom weights |
| `/api/simulation-analytics/profiles` | GET | List optimization profiles |

### Query Parameters for Events

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `event_type` | string | null | Filter by event type |
| `offset` | int | 0 | Skip N events |
| `limit` | int | 100 | Max events to return (1-1000) |

## Log Format

### Events JSONL

One JSON line per event, appended in real-time:

```json
{"timestamp": "2026-02-06T14:30:00", "simulated_hour": 14, "event_type": "equipment_fault", "equipment_id": "S002-UPS-B1-001", "equipment_name": "UPS-1", "description": "Battery degradation detected", "details": {"fault_type": "battery_degradation"}, "success": true}
```

### Run Metadata JSON

```json
{
  "run_id": "sim_20260206_143000",
  "scenario": "fault_day",
  "building_code": "site-002",
  "started_at": "2026-02-06T14:30:00",
  "ended_at": "2026-02-06T14:35:00",
  "duration_minutes": 5.0,
  "event_count": 42,
  "events_file": "sim_20260206_143000_events.jsonl",
  "config": {"duration_minutes": 5, "scenario": "fault_day", "start_hour": 0}
}
```

## Computed Metrics

The analyzer computes these metrics from event data:

| Metric | Description |
|--------|-------------|
| `total_events` | Total events in the run |
| `total_faults` | Equipment fault count |
| `faults_repaired` | Repairs completed |
| `mean_time_to_repair_hours` | Average fault-to-repair duration |
| `alerts_generated` | Alert events |
| `work_orders_created` | Work order events |
| `ai_optimizations` | AI optimization events |
| `setpoint_changes` | Setpoint change events |
| `fault_types` | Breakdown by fault type |
| `events_by_hour` | Event distribution across hours |

## Usage Examples

### List Simulation Runs

```bash
curl http://localhost:9095/api/simulation-analytics/runs | jq
```

### View Analysis for a Run

```bash
curl http://localhost:9095/api/simulation-analytics/runs/sim_20260206_143000/analysis | jq
```

### Filter Events by Type

```bash
curl "http://localhost:9095/api/simulation-analytics/runs/sim_20260206_143000/events?event_type=equipment_fault" | jq
```

### Re-Analyze with Custom Weights

```bash
curl -X POST http://localhost:9095/api/simulation-analytics/runs/sim_20260206_143000/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "name": "balanced",
    "description": "Equal weight across all dimensions",
    "weights": {"runtime": 0.2, "comfort": 0.2, "cost": 0.2, "maintenance": 0.2, "energy": 0.2},
    "thresholds": {}
  }'
```

### Grep JSONL Logs Directly

```bash
# Find all faults in a run
grep '"event_type": "equipment_fault"' backend/app/data/simulation_logs/sim_*_events.jsonl

# Count events per type
cat backend/app/data/simulation_logs/sim_20260206_143000_events.jsonl | \
  jq -r '.event_type' | sort | uniq -c | sort -rn
```

## Design Decisions

- **JSONL format**: Grep-able, appendable, Grafana/Loki compatible
- **File-based storage**: No database dependency, easy to archive/share
- **Profiles as config**: Editable JSON file, not hardcoded
- **Analysis on demand**: Generated at simulation end + re-runnable via API
- **No auto-feedback**: Analysis reports are read-only reference material

## Files

| File | Purpose |
|------|---------|
| `models/simulation_analytics.py` | Pydantic models for profiles, metrics, reports |
| `services/simulation_logger.py` | JSONL event logger (callback on orchestrator) |
| `services/simulation_analyzer.py` | Metrics computation and profile scoring |
| `api/simulation_analytics.py` | REST API endpoints |
| `data/optimization_profiles.json` | Profile definitions with weights/thresholds |
| `data/simulation_logs/` | Log directory for JSONL, meta, and analysis files |

## Related Documentation

- [24-Hour Lifecycle Simulation](./lifecycle-simulation.md) - The simulation engine that feeds this pipeline
- [Service Feedback System](./service-feedback-system.md) - Feedback events captured in logs
- [Health Scoring System](./health-scoring-system.md) - Health metrics referenced in analysis
