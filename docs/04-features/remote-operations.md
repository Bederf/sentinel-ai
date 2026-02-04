---
title: "Remote Operations"
type: "guide"
status: "approved"
version: "1.0.0"
created: "2026-02-04"
updated: "2026-02-04"
author: "Sentinel Development Team"
tags: ["remote-operations", "dispatch", "monitoring", "commands"]
domain: "general"
audience: "developers"
complexity: "intermediate"
estimated_read_time: 15
---

# Remote Operations

Phase 59 delivers remote building operations capabilities: monitoring, command execution, and intelligent dispatch. The system enables field technicians and dispatchers to check building status remotely, execute commands with safety guardrails, and make smart dispatch decisions that reduce unnecessary truck rolls by 50%+.

## Architecture Overview

```
                    +-------------------+
                    |   Telegram/WhatsApp|
                    |   Bot (Clawd)     |
                    +--------+----------+
                             |
                    +--------v----------+
                    |   REST API Layer   |
                    |   /api/remote/*    |
                    |   /api/dispatch/*  |
                    +--------+----------+
                             |
              +--------------+--------------+
              |              |              |
     +--------v---+  +------v------+  +----v--------+
     |  Remote     |  |  Remote     |  |  Smart      |
     |  Monitoring |  |  Command    |  |  Dispatch   |
     |  Service    |  |  Service    |  |  Service    |
     +------+------+  +------+------+  +------+------+
            |                |                |
     +------v------+  +-----v-------+  +-----v-------+
     | Device      |  | Safety      |  | Work Order  |
     | Manager     |  | Engine      |  | Service     |
     +-------------+  +-------------+  +-------------+
```

## Authorization Levels

Remote operations use a 4-level authorization model where higher levels include all permissions of lower levels.

| Level | Name | Value | Capabilities |
|-------|------|-------|-------------|
| 1 | VIEW_ONLY | 1 | View building status, equipment readings, active alarms |
| 2 | OPERATOR | 2 | + Run diagnostics, assess dispatch need, unlock doors |
| 3 | TECHNICIAN | 3 | + Adjust setpoints, override schedules |
| 4 | ENGINEER | 4 | + Start/stop equipment, fault reset, fire panel reset |

### Command Authorization Matrix

| Command Type | Required Level | Auto-Expiry |
|-------------|---------------|-------------|
| `status_check` | VIEW_ONLY (1) | None |
| `door_unlock` | OPERATOR (2) | 15 minutes |
| `setpoint_adjust` | TECHNICIAN (3) | 4 hours |
| `schedule_override` | TECHNICIAN (3) | 8 hours |
| `equipment_start_stop` | ENGINEER (4) | None |
| `fault_reset` | ENGINEER (4) | None |
| `fire_panel_reset` | ENGINEER (4) | None |

### Demo Users

| User ID | Role | Auth Level |
|---------|------|-----------|
| `view_user` | viewer | VIEW_ONLY |
| `operator_user` | operator | OPERATOR |
| `tech_user` | technician | TECHNICIAN |
| `engineer_user` | engineer | ENGINEER |

Pass `X-User-Id` and/or `X-User-Role` headers. Falls back to demo technician.

## Remote Monitoring (Plan 59-01)

Building-wide status aggregation, equipment diagnostics, and dispatch assessment.

### API Endpoints

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/api/remote/building/{site_id}/status` | VIEW_ONLY+ | Building status summary |
| GET | `/api/remote/equipment/{id}/diagnostic` | OPERATOR+ | Equipment diagnostic (quick_status or full_diagnostic) |
| GET | `/api/remote/equipment/{id}/dispatch-assessment` | OPERATOR+ | Should we dispatch? |
| GET | `/api/remote/user/{user_id}/sessions` | Own user or ENGINEER | Session history |
| GET | `/api/remote/commands/allowed` | Any | Commands allowed for current role |

### Building Status Response

```json
{
  "site_id": "site-002",
  "timestamp": "2026-02-04T10:30:00",
  "device_count": 48,
  "devices_online": 45,
  "devices_offline": 3,
  "devices_in_alarm": 1,
  "devices_in_warning": 2,
  "active_alarms": [...],
  "overall_health_score": 87.5,
  "key_metrics": {
    "average_temperature_c": 22.3,
    "total_devices": 48,
    "alarm_rate_pct": 2.1
  }
}
```

## Remote Command Execution (Plan 59-02)

Safe remote command execution with auto-expiring overrides, rollback, and rate limiting.

### Safety Architecture

Safety validation is **delegated to the existing SafetyEngine** which reads configurable rules from `safety_rules.json` (managed via the settings page). The remote command service handles authorization, rate limiting, override lifecycle, and rollback -- not safety rule enforcement.

```
Remote Command Request
    |
    v
[Authorization Check] --> 403 if insufficient
    |
    v
[Rate Limit Check] --> 429 if exceeded (10/user/hour)
    |
    v
[Record Pre-Command State] (for rollback)
    |
    v
[Device Manager Write] --> SafetyEngine validates automatically
    |
    v
[Audit Log] + [Schedule Override Expiry]
    |
    v
Response (with rollback info)
```

### API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/remote/commands/execute` | Execute a remote command |
| POST | `/api/remote/commands/{id}/rollback` | Rollback to pre-command state |
| GET | `/api/remote/overrides` | List active auto-expiring overrides |
| GET | `/api/remote/commands/history` | Command history with filters |
| POST | `/api/remote/commands/batch` | Atomic batch execution |

### Override Auto-Expiry

Overrides automatically revert after configured durations (from `remote_ops_config.json`):

- **Setpoint overrides**: 4 hours
- **Schedule overrides**: 8 hours
- **Door unlocks**: 15 minutes

### Rate Limiting

- Warning at 8 commands per user per hour
- Block at 10 commands per user per hour
- Configurable via `remote_ops_config.json`

## Smart Dispatch (Plan 59-03)

Intelligent dispatch decisions with "while you're there" task bundling.

### Dispatch Workflow

```
1. EVALUATE
   Equipment alarm/anomaly triggers evaluation
   |
   v
2. REMOTE RESOLUTION CHECK
   Can this be fixed remotely? (setpoint adjust, fault reset, schedule override)
   |
   +-- YES --> Return remote actions, no dispatch needed
   |
   +-- NO --> Continue to dispatch
   |
   v
3. BUNDLE TASKS ("while you're there")
   Find additional tasks at same site:
   - Open work orders
   - Devices in warning/alarm
   - Overdue inspections
   Group by floor for efficient routing
   |
   v
4. ASSIGN TECHNICIAN
   Priority: onsite at same building > available with matching skill > any available
   |
   v
5. GENERATE SITE BRIEFING
   Building info, current status, floor-by-floor routing,
   equipment details, tools needed, estimated time
   |
   v
6. DISPATCH
   Technician receives briefing, travels to site
   |
   v
7. CHECK-IN
   Technician arrives, gets refreshed briefing with latest status
   |
   v
8. COMPLETE TASKS
   Work through bundled tasks floor by floor
   |
   v
9. COMPLETE DISPATCH
   Record metrics: time onsite, tasks completed, efficiency
```

### API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/dispatch/evaluate` | Evaluate if dispatch needed for equipment |
| POST | `/api/dispatch/create` | Create dispatch with bundled tasks |
| GET | `/api/dispatch/briefing/{dispatch_id}` | Get/refresh site briefing |
| POST | `/api/dispatch/{dispatch_id}/check-in` | Technician check-in at site |
| POST | `/api/dispatch/{dispatch_id}/complete` | Complete dispatch with metrics |
| GET | `/api/dispatch/active` | List active dispatches |
| GET | `/api/dispatch/technicians` | List technicians with availability |

### Task Bundling

When dispatch IS needed, the system automatically bundles additional tasks at the same site:

1. **Open work orders** - Pending/open WOs for the same site
2. **Devices in warning/alarm** - Equipment needing attention
3. **Overdue inspections** - Scheduled inspections past due
4. **Deduplication** - No duplicate tasks for same equipment
5. **Floor routing** - Tasks sorted by floor for efficient path

### Technician Assignment

Best-fit algorithm:

1. Already onsite at same building with matching specialization
2. Available technician with matching specialization
3. Available technician with general skills
4. Any available technician

Specialization mapping:
- HVAC equipment (chiller, AHU, FCU, VAV) -> `hvac`
- Electrical equipment (generator, UPS, transformer) -> `electrical`
- Fire equipment -> `fire_safety`
- Access control, general -> `general`

### Site Briefing

Structured briefing suitable for WhatsApp/PDF delivery:

```json
{
  "briefing_id": "uuid",
  "building": {
    "name": "Sandton City Office Tower",
    "address": "83 Rivonia Road, Sandton",
    "floors": ["B1", "G", "L0", "L1", "L2"],
    "access_instructions": "Enter via main lobby..."
  },
  "building_status": {
    "devices_total": 48,
    "devices_online": 45,
    "devices_in_alarm": 1,
    "active_alarms": [...]
  },
  "tasks": [...],
  "floor_routing": [
    {"floor": "B1", "tasks": [...], "estimated_minutes": 45},
    {"floor": "L1", "tasks": [...], "estimated_minutes": 30}
  ],
  "tools_needed": ["multimeter", "thermal camera", "PPE kit"],
  "estimated_onsite_time": "1h 30m",
  "safety_notes": [
    "Sign in at reception",
    "Check active alarms before entering plant rooms",
    "Wear PPE in plant room areas"
  ]
}
```

## Demo Scenarios

### Scenario 1: Remote Resolution (No Dispatch)

```bash
# Evaluate equipment with no issues
curl -X POST http://localhost:9095/api/dispatch/evaluate \
  -H "Content-Type: application/json" \
  -d '{"equipment_id": "S002-AHU-L1-01"}'
```

Expected: `dispatch_required: false` with remote diagnostic summary.

### Scenario 2: Full Dispatch Workflow

```bash
# 1. Evaluate equipment needing dispatch
curl -X POST http://localhost:9095/api/dispatch/evaluate \
  -H "Content-Type: application/json" \
  -d '{"equipment_id": "S002-CHILLER-B1-001"}'

# 2. Create dispatch (auto-assign technician)
curl -X POST http://localhost:9095/api/dispatch/create \
  -H "Content-Type: application/json" \
  -d '{"site_id": "site-002", "equipment_id": "S002-CHILLER-B1-001"}'

# 3. Check in (use dispatch_id from step 2)
curl -X POST http://localhost:9095/api/dispatch/DSP-XXXXXXXX/check-in \
  -H "X-User-Id: tech-002"

# 4. Complete dispatch
curl -X POST http://localhost:9095/api/dispatch/DSP-XXXXXXXX/complete \
  -H "Content-Type: application/json" \
  -d '{"overall_notes": "Chiller compressor replaced, all tasks completed"}'
```

### Scenario 3: View Technicians and Active Dispatches

```bash
# List technicians
curl http://localhost:9095/api/dispatch/technicians

# List active dispatches
curl http://localhost:9095/api/dispatch/active
```

## Configuration

### remote_ops_config.json

Located at `backend/app/data/remote_ops_config.json`:

- `command_authorization` - Command type to minimum authorization level
- `safety_guardrails` - Safety-related configuration
- `auto_expiring_overrides` - Override duration settings
- `rate_limit` - Rate limiting thresholds
- `demo_users` - Demo user definitions
- `authorization_levels` - Level descriptions

### technicians.json

Located at `backend/app/data/technicians.json`:

5 demo technicians with varying specializations, statuses, and site assignments.

### safety_rules.json

Located at `backend/app/data/safety_rules.json`:

Configurable safety rules enforced by SafetyEngine. Managed via the settings page -- **not hardcoded** in remote command or dispatch services.

## Key Files

| Category | File |
|----------|------|
| Models | `backend/app/models/remote_ops.py` |
| Auth Service | `backend/app/services/auth_service.py` |
| Monitoring | `backend/app/services/remote_monitoring_service.py` |
| Commands | `backend/app/services/remote_command_service.py` |
| Dispatch | `backend/app/services/smart_dispatch_service.py` |
| Config | `backend/app/data/remote_ops_config.json` |
| Technicians | `backend/app/data/technicians.json` |
| API (monitoring) | `backend/app/api/remote_ops.py` |
| API (commands) | `backend/app/api/remote_commands.py` |
| API (dispatch) | `backend/app/api/dispatch.py` |
