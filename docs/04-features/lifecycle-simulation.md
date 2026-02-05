---
title: "24-Hour Building Lifecycle Simulation"
type: "guide"
status: "approved"
version: "1.0.0"
created: "2026-02-05"
updated: "2026-02-05"
author: "Sentinel Development Team"
tags: ["simulation", "demo", "testing", "lifecycle"]
domain: "general"
audience: "developers"
complexity: "intermediate"
estimated_read_time: 10
---

# 24-Hour Building Lifecycle Simulation

Simulates a complete 24-hour building day to test and demonstrate the full AI optimization, fault detection, alert, repair, and feedback cycle.

## Overview

The lifecycle simulation compresses 24 simulated hours into 2-24 real minutes, allowing rapid testing of:

- AI optimization recommendations
- Equipment health degradation
- Fault detection and alert generation
- Work order creation and technician dispatch
- Service feedback submission
- Health score restoration
- Alert resolution

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                    Lifecycle Orchestrator                        │
│  (backend/app/services/lifecycle_orchestrator.py)                │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────┐   ┌─────────────┐   ┌─────────────┐           │
│  │ Time Engine │   │  Scenario   │   │   Event     │           │
│  │ (compress)  │   │   Config    │   │   Logger    │           │
│  └──────┬──────┘   └──────┬──────┘   └──────┬──────┘           │
│         │                 │                 │                   │
│         └─────────────────┼─────────────────┘                   │
│                           │                                     │
│                    ┌──────▼──────┐                              │
│                    │ Hour Loop   │                              │
│                    │  Processor  │                              │
│                    └──────┬──────┘                              │
│                           │                                     │
│         ┌─────────────────┼─────────────────┐                   │
│         │                 │                 │                   │
│   ┌─────▼─────┐    ┌─────▼─────┐    ┌─────▼─────┐             │
│   │ Building  │    │   Fault   │    │  Repair   │             │
│   │  Events   │    │ Injection │    │ Scheduler │             │
│   └───────────┘    └───────────┘    └───────────┘             │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
                              │
         ┌────────────────────┼────────────────────┐
         │                    │                    │
         ▼                    ▼                    ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│  AI Optimizer   │  │  Alert Service  │  │ Service Feedback│
│  (recommendations)│  │  (Clawd notify) │  │  (health update)│
└─────────────────┘  └─────────────────┘  └─────────────────┘
```

## API Endpoints

### Control Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/lifecycle/start` | POST | Start simulation with scenario |
| `/api/lifecycle/stop` | POST | Stop running simulation |
| `/api/lifecycle/pause` | POST | Pause simulation |
| `/api/lifecycle/resume` | POST | Resume paused simulation |
| `/api/lifecycle/status` | GET | Get current simulation status |

### Event Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/lifecycle/events` | GET | Get simulation events (filterable) |
| `/api/lifecycle/events/timeline` | GET | Events organized by hour |
| `/api/lifecycle/scenarios` | GET | List available scenarios |
| `/api/lifecycle/scenarios/{id}` | GET | Get scenario details |

### Manual Intervention

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/lifecycle/inject-fault` | POST | Manually inject a fault |
| `/api/lifecycle/trigger-repair/{code}` | POST | Force repair completion |

### Demo Shortcuts

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/lifecycle/demo/quick-cycle` | POST | 5-minute demo cycle |
| `/api/lifecycle/demo/ultra-fast` | POST | 2-minute demo cycle |

## Scenarios

### normal_day
- **Description:** Typical building operations
- **Fault Probability:** 10%
- **Auto-Repair:** No
- **Use Case:** Baseline demonstration

### fault_day (Default)
- **Description:** Guaranteed fault with auto-repair
- **Fault Hour:** 11:00 (simulated)
- **Repair Hour:** 14:00 (simulated)
- **Auto-Repair:** Yes
- **Use Case:** Full lifecycle demonstration

### chiller_failure
- **Description:** Chiller-specific fault scenario
- **Fault Equipment Type:** CHILLER
- **Fault Hour:** 10:00 (simulated)
- **Auto-Repair:** Yes
- **Use Case:** HVAC fault workflow demo

### multi_fault
- **Description:** Multiple equipment failures
- **Fault Probability:** 80%
- **Fault Equipment Types:** Various
- **Auto-Repair:** Yes (4-hour delay)
- **Use Case:** Stress testing, multiple alert handling

### maintenance_day
- **Description:** Scheduled maintenance day
- **Fault Probability:** 0%
- **Auto-Repair:** N/A
- **Use Case:** Maintenance workflow demonstration

## Time Compression

The `duration_minutes` parameter controls how real time maps to simulated time:

| Duration | Real Time per Hour | Total Duration | Use Case |
|----------|-------------------|----------------|----------|
| 24.0 | 1 minute | 24 minutes | Detailed demo |
| 12.0 | 30 seconds | 12 minutes | Standard demo |
| 5.0 | 12.5 seconds | 5 minutes | Quick demo |
| 2.0 | 5 seconds | 2 minutes | Ultra-fast testing |

## Hour-by-Hour Events

The simulation processes events based on simulated hour:

| Hour | Event Type | Description |
|------|------------|-------------|
| 6:00 | `building_wake` | Building systems start up |
| 7:00 | `occupancy_rise` | Occupancy begins increasing |
| 8:00-9:00 | `ai_optimization` | AI analyzes and recommends |
| 10:00-14:00 | `peak_load` | Peak occupancy and load |
| 11:00* | `fault_injection` | Fault occurs (fault_day scenario) |
| 14:00* | `repair_complete` | Auto-repair (fault_day scenario) |
| 17:00-18:00 | `occupancy_fall` | Occupancy decreases |
| 20:00-6:00 | `night_mode` | Building in standby |

*Scenario-dependent

## Usage Examples

### Start 5-Minute Demo

```bash
curl -X POST http://localhost:9095/api/lifecycle/demo/quick-cycle
```

### Start Custom Simulation

```bash
curl -X POST http://localhost:9095/api/lifecycle/start \
  -H "Content-Type: application/json" \
  -d '{
    "scenario": "fault_day",
    "duration_minutes": 10,
    "start_hour": 6
  }'
```

### Monitor Events

```bash
# Watch events in real-time
watch -n 5 'curl -s http://localhost:9095/api/lifecycle/events | jq ".events[-5:]"'
```

### Inject Fault Manually

```bash
curl -X POST "http://localhost:9095/api/lifecycle/inject-fault?fault_type=vibration"
```

### Check Status

```bash
curl http://localhost:9095/api/lifecycle/status | jq
```

**Response:**
```json
{
  "running": true,
  "paused": false,
  "scenario": "fault_day",
  "simulated_time": "2026-02-05T11:30:00",
  "simulated_hour": 11,
  "real_elapsed_seconds": 125.5,
  "events_count": 8,
  "active_faults": 1,
  "pending_repairs": 1,
  "recent_events": [...]
}
```

## Integration with Other Systems

### AI Optimizer
- Runs at 8:00 and 9:00 simulated time
- Generates optimization recommendations for the site
- Recommendations appear in dashboard

### Alert Service
- Fault injection creates alerts in Supabase
- Clawd notifications sent to FM team chat
- Alerts appear in dashboard bell icon

### Predictions
- Fault injection creates ML predictions
- Predictions appear in Risk Intelligence panel
- Probability and timeframe calculated from fault type

### Service Feedback
- After repair completion, service feedback is auto-submitted
- Health scores updated based on feedback
- Equipment status restored to normal

### Work Orders
- Faults create work orders automatically
- Technician assigned based on equipment type
- Work order status tracked through completion

## Files

| File | Purpose |
|------|---------|
| `services/lifecycle_orchestrator.py` | Core orchestrator with time engine, event processing |
| `api/lifecycle_simulation.py` | REST API endpoints |

## Related Documentation

- [Demo Simulation Control](./demo-simulation-control.md) - Simple trigger/reset endpoints
- [Asset Lifecycle State Machine](../05-integrations/asset-lifecycle-state-machine.md) - State definitions
- [Service Feedback System](./service-feedback-system.md) - Technician feedback
- [Health Scoring System](./health-scoring-system.md) - Health calculation
