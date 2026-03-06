# Operational Event Intelligence Layer

**Phase 145** | **Status**: Implemented

## Overview

The Event Intelligence layer sits between raw telemetry and AI reasoning. It converts
200,000+ sensor updates into ~30 meaningful operational events that the reasoning layer
can act on efficiently.

```
Telemetry Ingestion
       ↓
Event Intelligence Service    ← this layer
       ↓
SentinelEvent → EventBus
       ↓
Hybrid Context Assembly
       ↓
AI Reasoning
```

## How It Works

The `EventIntelligenceService` evaluates all equipment on a site against a set of
detection rules. When a condition is detected, it creates an `OperationalEvent` and
emits it as a `SentinelEvent` on the existing event bus.

### Detection Rules

| Rule | Trigger | Severity |
|------|---------|----------|
| Temperature deviation | Actual vs setpoint > 2°C | WARNING (>2°C), HIGH (>5°C), CRITICAL (>8°C) |
| Energy spike | Power > 1.5× rolling average | WARNING (1.5×), HIGH (2×), CRITICAL (3×) |
| Sensor failure | NaN/None/stale (>15 min) | HIGH |
| Comfort violation | Zone temp outside 20-24°C | WARNING (1°C), HIGH (2°C) |
| Setpoint drift | Setpoint changed without command | WARNING |
| Threshold breach | Value outside configured min/max | WARNING to CRITICAL |
| Pattern anomaly | ML anomaly score > 0.5 | WARNING (0.5), HIGH (0.7), CRITICAL (0.85) |

### Event Object

```python
OperationalEvent(
    event_id="EVT-20260305-a1b2c3d4",
    event_type=OperationalEventType.TEMPERATURE_DEVIATION,
    equipment_id="S002-CHILLER-B1-001",
    site_id="site-002",
    severity=EventSeverity.HIGH,
    signals=[{"point": "chw_supply_temp", "value": 12.0, "setpoint": 7.0}],
    description="CHW supply temp 5.0°C above setpoint",
    trend="rising",
    duration_minutes=18.5,
)
```

### Duration & Trend Tracking

- **Duration**: First detection time is stored. On subsequent evaluations, duration is updated.
- **Trend**: Last 5 values per point are buffered. Monotonically increasing = "rising",
  decreasing = "falling", otherwise "stable".

### Event Bus Integration

Events are converted to `SentinelEvent` via `to_sentinel_event()` and emitted on the
existing event bus with `event_type="operational.{type}"` format.

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/events/active` | All active operational events |
| GET | `/api/events/active/{site_id}` | Active events for a site |
| GET | `/api/events/summary/{site_id}` | Event counts by type/severity |
| GET | `/api/events/history` | Event history with filters |
| GET | `/api/events/{event_id}` | Specific event details |

## Key Files

- `backend/app/models/operational_event.py` — Event models and enums
- `backend/app/services/event_intelligence_service.py` — Detection engine
- `backend/app/api/event_intelligence.py` — API router
- `backend/tests/services/test_event_intelligence.py` — 37 tests
- `backend/tests/services/test_phase145_wiring.py` — 16 wiring tests

## Wiring (Active)

- **Background Scheduler**: `add_event_intelligence_job()` runs `process_site()` for all
  registered sites every 2 minutes. Read-only: detects conditions, emits events.
- **HybridContext**: `_gather_active_events()` pulls active events per equipment into
  the AI prompt (Step 5 in `query()` flow).

## Integration Points

- **EventBus** (Phase 139): Events emitted via existing bus with middleware pipeline
- **HybridContext** (Phase 144): Events feed into context assembly via `_gather_active_events()`
- **Control Policy Engine** (Phase 145): Events trigger control mode workflows
- **Decision Memory** (Phase 145): Events linked to decisions via correlation_id
