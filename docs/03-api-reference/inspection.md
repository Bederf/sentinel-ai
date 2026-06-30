---
title: "Inspection API"
type: "reference"
status: "draft"
version: "1.0.0"
created: "2026-03-31"
updated: "2026-06-11"
tags: ["sentinel", "documentation"]
related: []
domain: "bms"
audience: "all"
complexity: "intermediate"
estimated_read_time: 10
---

# Inspection API

## Overview

Inspection endpoints support two workflows:

1. **Standard inspections** — Scheduled/ad-hoc inspection tasks managed via the inspection module (`backend/app/api/inspection.py`)
2. **Sentry Telegram inspections** — Guided debrief flow triggered by technicians via Telegram slash commands (`backend/app/api/sentry_webhooks.py`)

## Sentry Telegram Inspection Endpoints

These endpoints are used by the Sentry Telegram bot during the inspection skill flow. The bot routes via `sentry_ai_bridge.py` — see [call-log-api.md](call-log-api.md) for the full routing architecture.

### GET /api/sentry/inspection-checklist/{equipment_type}

Returns a Telegram-formatted inspection checklist for an equipment type. Called by Sentry when a technician uses `/info-{code}` to see what to check on-site, or during the "done" debrief flow.

**Authentication:** None required (read-only, public in demo mode)

**Path Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `equipment_type` | string | Equipment type: `fcu`, `ahu`, `chiller`, `generator`, `pump`, `ups`, `vav` |

**Response (200 OK):**

```json
{
  "found": true,
  "equipment_type": "fcu",
  "template_name": "FCU Routine Inspection",
  "estimated_minutes": 20,
  "checklist_text": "📋 FCU Routine Inspection\n⏱ Estimated: 20 min\n\n▸ Mechanical\n  ☐ Filter Condition\n  ☐ Fan Operation\n...",
  "items": [
    {
      "item_id": "filter_condition",
      "question": "Filter Condition",
      "category": "Mechanical",
      "item_type": "checklist",
      "options": ["Clean", "Dirty", "Blocked"]
    },
    {
      "item_id": "supply_air_temp",
      "question": "Supply Air Temperature",
      "category": "Performance",
      "item_type": "measurement",
      "unit": "°C",
      "tolerance_min": 11,
      "tolerance_max": 18
    }
  ]
}
```

**Response (not found):**

```json
{
  "found": false,
  "equipment_type": "unknown_type",
  "checklist_text": "No inspection checklist available for unknown_type.",
  "items": []
}
```

**Checklist templates:** Stored in `backend/app/data/inspection_checklist_templates.json` (7 equipment types).

---

### POST /api/sentry/inspection-result

Submits inspection results after a technician completes the Sentry guided debrief. Writes to three Supabase tables: `inspection_tasks`, `inspection_results`, and `inspection_deficiencies`.

**Authentication:** Required — `X-Sentry-Secret` header.

```
X-Sentry-Secret: sentry-bms-phase-41
```

**Request Body:**

```json
{
  "equipment_code": "S002-FCU-201",
  "work_order_code": "WO-2026-0030",
  "technician_name": "John Smith",
  "telegram_user_id": "8359288792",
  "items": [
    {
      "item_id": "filter_condition",
      "question": "Filter Condition",
      "answer": "Blocked",
      "status": "critical"
    },
    {
      "item_id": "fan_operation",
      "question": "Fan Operation",
      "answer": "Noisy",
      "status": "warning"
    },
    {
      "item_id": "thermostat_response",
      "question": "Thermostat Response",
      "answer": "Normal",
      "status": "ok"
    }
  ],
  "ai_diagnosis": "Blocked filter causing restricted airflow. Noisy fan suggests bearing wear.",
  "recommendations": "Replace filter immediately. Schedule fan bearing check within 7 days."
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `equipment_code` | string | Yes | Equipment code (e.g., `S002-FCU-201`) |
| `work_order_code` | string | Yes | Work order code (e.g., `WO-2026-0030`) |
| `technician_name` | string | Yes | Technician who performed inspection |
| `telegram_user_id` | string | No | Telegram user ID for audit provenance |
| `items` | array | Yes | Checklist item results (see below) |
| `ai_diagnosis` | string | No | AI-curated diagnosis summary |
| `recommendations` | string | No | AI recommendations for FM |

**Item fields:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `item_id` | string | Yes | Checklist item ID (e.g., `filter_condition`) |
| `question` | string | Yes | Question text shown to technician |
| `answer` | string | Yes | Technician's answer |
| `status` | string | No | `ok` (default), `warning`, or `critical` |

**Response (200 OK):**

```json
{
  "success": true,
  "inspection_id": "a1b2c3d4-...",
  "task_id": "e5f6g7h8-...",
  "equipment_code": "S002-FCU-201",
  "work_order_code": "WO-2026-0030",
  "overall_status": "fail",
  "deficiencies_found": 2,
  "critical_findings": 1
}
```

**Overall status logic:**

| Condition | Status |
|-----------|--------|
| Any item with `status: "critical"` | `fail` |
| Any item with `status: "warning"` (no criticals) | `pass_with_issues` |
| All items `status: "ok"` | `pass` |

**Side effects:**

1. Creates `inspection_tasks` record (status: `completed`)
2. Creates `inspection_results` record with `item_results` JSONB
3. Creates `inspection_deficiencies` records for each warning/critical item

**Note:** Work order milestone advancement (`assigned` → `in_progress` → `resolved`) is handled separately by the technician closeout skill via `PATCH /api/sentry/wo-milestone`. The inspection-result endpoint does NOT update the work order status.

**Error responses:**

| Code | Condition |
|------|-----------|
| 403 | Missing or invalid `X-Sentry-Secret` |
| 404 | Equipment code not found in Supabase |
| 500 | Database error |

---

## Web Chat FM Workflow

The AI chat (SENTINEL web UI) integrates with the same FM workflow used by Telegram. When a user asks about equipment issues, Claude presents clickable slash commands rather than calling `create_work_order` directly:

```
User asks about equipment problem
    ↓
Claude presents clickable commands:
  `/info-{CODE}`    — Equipment diagnostics (health, alerts, history)
  `/inspect-{CODE}` — Schedule inspection + auto-assign technician
  `/WO-{CODE}`      — Create formal work order with checklist
  `/note-{CODE}`    — Log observations against equipment record
    ↓
User clicks command → sent as chat message → slash_command_router.py handles it
    ↓
Work order persists to Supabase via POST /api/sentry/create-work-order
```

**Clickable command rendering:** Commands matching `/info-`, `/WO-`, `/inspect-`, `/reset-`, `/note-` in inline code blocks are rendered as clickable buttons in the web chat (`ChatMessage.tsx`, `COMMAND_RE` regex). Clicking a button sends the command text as a new chat message.

**Implementation:**
- Slash command router: `backend/app/services/slash_command_router.py`
- Claude tool enforcement: `backend/app/services/chat_tools.py` (tool description instructs FM workflow)
- System prompt: `backend/app/services/claude_service.py` (Claude instructed to present commands, not call tool directly)
- Button rendering: `frontend/src/components/ChatMessage.tsx` (`COMMAND_RE` pattern)

---

## Standard Inspection Endpoints

For the full inspection module (scheduled tasks, results, deficiencies, measurements), see `backend/app/api/inspection.py`.

Key endpoints:

```
GET  /api/inspections/tasks                    — List inspection tasks
POST /api/inspections/tasks                    — Create inspection task
GET  /api/inspections/tasks/{task_id}          — Get task details
GET  /api/inspections/tasks/{task_id}/results  — Get task results
POST /api/inspections/results                  — Submit inspection result
GET  /api/inspections/deficiencies             — List deficiencies
```

## Inspection Priority Scoring (Phase 132)

The `InspectionPriorityService` computes a priority score (0-100) per asset to rank which equipment should be inspected next. Higher score = more urgent.

### Priority Formula

```
Priority = (days_overdue × 0.25) + (anomaly_score × 0.25) +
           (fault_history × 0.20) + (rul_inverse × 0.15) +
           (criticality × 0.15)
```

### Component Calculations

| Component | Weight | Input | Scoring |
|-----------|--------|-------|---------|
| **Days Overdue** | 0.25 | Days since inspection vs interval | 0 = on schedule, 100 = 2× overdue. No record = 75 |
| **Anomaly Score** | 0.25 | ML autoencoder anomaly score (0-1) | Direct mapping × 100 |
| **Fault History** | 0.20 | Faults in last 30 days | 0=0, 1=25, 2=50, 3=75, 4+=100 |
| **RUL Inverse** | 0.15 | Remaining Useful Life (days) | ≤0=100, <30=90, <90=60, <180=30, else=10. Unknown=20 |
| **Criticality** | 0.15 | Equipment type criticality (0-1) | Direct mapping × 100 |

### Default Inspection Intervals

| Equipment Type | Interval (days) | Default Criticality |
|----------------|----------------|---------------------|
| Generator | 30 | 0.95 |
| Chiller | 90 | 0.90 |
| AHU | 90 | 0.70 |
| UPS | 90 | 0.85 |
| BESS | 90 | 0.80 |
| Cooling Tower | 90 | 0.60 |
| FCU | 180 | 0.30 |
| VAV | 180 | 0.30 |
| Pump | 180 | 0.50 |
| DALI | 365 | 0.20 |

### Priority Levels

| Score Range | Level | Action |
|-------------|-------|--------|
| 80-100 | Critical | Immediate inspection required |
| 60-79 | High | Schedule within 7 days |
| 40-59 | Medium | Schedule within 30 days |
| 20-39 | Low | Include in next routine cycle |
| 0-19 | Routine | No action needed |

### Fleet Priorities

`compute_fleet_priorities(site_id)` returns a ranked list of all equipment at a site, sorted by priority score descending. It automatically gathers anomaly scores from the ML anomaly detection service.

### Implementation

- Service: `backend/app/services/inspection_priority_service.py`
- Singleton: `get_inspection_priority_service()`
- Key methods:
  - `compute_priority(equipment_id, equipment_type, ...)` — Single asset
  - `compute_fleet_priorities(site_id)` — All assets at site, ranked

---

## Database Tables

| Table | Purpose |
|-------|---------|
| `inspection_tasks` | Scheduled or ad-hoc inspection tasks linked to equipment |
| `inspection_results` | Results with `item_results` JSONB, `overall_status`, deficiency counts |
| `inspection_deficiencies` | Individual warning/critical findings linked to result and equipment |
| `inspection_measurements` | Numeric measurement readings (temperature, pressure, etc.) |

## Implementation

- Sentry endpoints: `backend/app/api/sentry_webhooks.py`
- Standard endpoints: `backend/app/api/inspection.py`
- Repository: `backend/app/database/repositories/inspection_repository.py`
- Checklist templates: `backend/app/data/inspection_checklist_templates.json`
- Checklist service: `backend/app/services/checklist_service.py`
