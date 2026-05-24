---
title: "Work Orders API"
type: "reference"
status: "active"
version: "2.0.0"
created: "2026-03-31"
updated: "2026-05-10"
tags: ["sentinel", "documentation"]
related: []
domain: "bms"
audience: "all"
complexity: "intermediate"
estimated_read_time: 12
---

# Work Orders API

## Data model note

**Work orders and service records are distinct entities with different lifecycles.**

| Entity | Purpose | Lifecycle |
|--------|---------|-----------|
| `work_orders` | Operational task with SLA milestones | Retained; `milestone_status` tracks lifecycle |
| `service_records` | Permanent equipment maintenance history | Retained forever; `work_order_id` nullable so history survives WO deletion |

When a work order is created for equipment, a service record is automatically created and linked via `work_order_id`. If the work order is later deleted, the service record's `work_order_id` is nullified — the equipment history is preserved.

---

## 4-Milestone SLA Model

Each work order progresses through four milestones, each with a configurable SLA deadline in hours. Deadlines are computed from milestone entry time and are materialised in `sla_deadline_at` — not derived at query time.

```
assigned ──► in_progress ──► resolved ──► verified
   │              │              │            │
   │  SLA hours   │  SLA hours   │  SLA hours  │  None (terminal)
   ▼              ▼              ▼            ▼
 deadline_at   deadline_at    deadline_at     null
```

**Milestones:**

| Milestone | Trigger | SLA clock |
|-----------|---------|-----------|
| `assigned` | WO created | Starts at WO creation; first deadline |
| `in_progress` | Technician acknowledges work | Restarts from `in_progress_at` |
| `resolved` | Technician completes on-site work, calls `done #WO-XXXX` | Restarts from `resolved_at` |
| `verified` | FM reviews and closes WO | Terminal — no deadline |

**SLA hours are per-site configurable** via `recommendation_sla_per_site` table. Site-level overrides take precedence over the default JSONB hours stored on the work order itself.

**Note:** `recommendations` (AI-generated BMS proposals) are a separate system with no SLA columns in the database. Only `work_orders` carries SLA milestone tracking.

---

## Slash Command Workflow

```
Alert / User Question
    ↓
1. `/info-{CODE}`    — Equipment diagnostics (health, alerts, service history)
    ↓
2. `/inspect-{CODE}` — Schedule inspection + auto-assign technician
    ↓
3. `/WO-{CODE}`      — Create formal work order with checklist
    ↓
4. `/note-{CODE}`    — Log observations against equipment record
```

Each command renders as a **clickable button** in the web chat. Claude is instructed to present these commands rather than calling `create_work_order` directly, ensuring the FM workflow is followed.

---

## Endpoints

### Create Work Order

`POST /api/sentry/create-work-order`

Primary creation path used by slash commands and Claude tool.

**Authentication:** `X-Sentry-Secret` header required.

**Request:**
```json
{
  "equipment_code": "S002-FCU-301",
  "title": "Work order for S002-FCU-301",
  "description": "Filter replacement needed - high differential pressure",
  "priority": "medium",
  "created_by": "web-chat"
}
```

**Response (200):**
```json
{
  "success": true,
  "code": "WO-20260302-A1B2C3D4",
  "equipment_code": "S002-FCU-301",
  "assigned_to": "Mike Johnson",
  "technician_email": "mike@example.com",
  "priority": "medium",
  "status": "scheduled"
}
```

**Side effects:**
- Persists to Supabase `work_orders` table
- Auto-assigns technician by equipment specialty
- Returns technician contact info for Telegram notification

---

### Advance Work Order Milestone

`PATCH /api/sentry/wo-milestone`

Advances a work order to the next milestone and recalculates the SLA deadline. Called by the technician bot after closeout inspection.

**Authentication:** `X-Sentry-Secret` header required.

**Request:**
```json
{
  "wo_code": "WO-2026-0030",
  "milestone": "resolved",
  "notes": "Blocked filter replaced. Fan noise resolved after filter change.",
  "outcome": "fixed",
  "operator_password": ""
}
```

**Fields:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `wo_code` | string | Yes | Work order code (e.g. `WO-2026-0001`) |
| `milestone` | string | Yes | One of: `assigned`, `in_progress`, `resolved`, `verified` |
| `notes` | string | No | Technician's findings (appended to existing notes) |
| `outcome` | string | No | `fixed` / `parts_needed` / `escalate` — drives notification routing |
| `operator_password` | string | No | Not used; pass empty string |

**Response (200):**
```json
{
  "success": true,
  "wo_id": "8fdfe233-7bdb-4244-acd9-289b82a5aa1d",
  "wo_code": "WO-2026-0030",
  "milestone_status": "resolved",
  "assigned_at": "2026-05-08T09:00:00+02:00",
  "in_progress_at": "2026-05-08T10:30:00+02:00",
  "resolved_at": "2026-05-08T14:00:00+02:00",
  "verified_at": "",
  "sla_deadline_at": "2026-05-09T14:00:00+02:00",
  "status": "in_progress"
}
```

**Side effects:**
- Recalculates `sla_deadline_at` from milestone entry time + per-site SLA hours
- Appends `notes` to existing notes with `---` separator
- On `resolved`: notifies staff (from `created_by` provenance string) via Telegram
- On `escalate`: notifies FM manager via Telegram
- On `verified`: clears SLA deadline (`sla_deadline_at = null`)

**Error responses:**
- `400` — Invalid milestone value
- `404` — Work order not found
- `401` — Missing or invalid `X-Sentry-Secret`

---

### Other Endpoints

- `GET /work-orders` — List work orders (filterable by site, status, assignee)
- `GET /work-orders/{work_order_id}` — Get work order details
- `GET /api/sentry/work-order/status/{service_record_code}` — Get by code
- `GET /api/sentry/work-order/pending` — List pending work orders
- `POST /api/sentry/work-order/complete/{service_record_code}` — Mark complete
- `POST /api/sentry/inspection-result` — Submit technician inspection checklist results
- `GET /api/sentry/inspection-checklist/{equipment_type}` — Get inspection checklist

---

## Technician Closeout Flow

**Trigger:** Technician sends `done #WO-XXXX` (or `done WO-XXXX`) on Telegram.

**Steps:**

1. **Parse** — Extract WO code, look up equipment type
2. **Checklist** — Prompt one inspection item at a time (mobile-friendly), map answers to `ok`/`warning`/`critical`
3. **AI Diagnosis** — Cross-reference checklist answers, generate findings summary
4. **POST** — Submit inspection result to `POST /api/sentry/inspection-result`
5. **Advance Milestone** — `PATCH /api/sentry/wo-milestone` with `milestone: "resolved"`, `outcome: "fixed"|"parts_needed"|"escalate"`, `notes: "{ai_diagnosis}"`
6. **Notify FM** — Send findings summary to FM manager via `sentrybot message send`

If milestone advance fails, FM notification includes: `⚠️ WO milestone sync pending — FM to verify closeout in SENTINEL.`

---

## Work Orders Table Columns

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID | Primary key |
| `code` | TEXT | Unique work order code (e.g. `WO-2026-0001`) |
| `milestone_status` | TEXT | Current milestone: `assigned`, `in_progress`, `resolved`, `verified` |
| `status` | TEXT | Legacy status: `scheduled`, `in_progress`, `completed`, `cancelled` |
| `assigned_at` | TIMESTAMPTZ | When WO was assigned (SAST, UTC+02:00) |
| `in_progress_at` | TIMESTAMPTZ | When technician started work |
| `resolved_at` | TIMESTAMPTZ | When on-site work completed |
| `verified_at` | TIMESTAMPTZ | When FM verified closeout |
| `sla_hours` | JSONB | Per-milestone hours: `{"assigned": 24, "in_progress": 48, "resolved": 72, "verified": 168}` |
| `sla_deadline_at` | TIMESTAMPTZ | Materialised deadline for current milestone (null when verified) |
| `assigned_to` | TEXT | Technician name |
| `equipment_id` | UUID | Link to equipment |
| `site_id` | UUID | Link to site |

Indexes: `idx_work_orders_milestone_status`, `idx_work_orders_sla_deadline`, `idx_work_orders_assigned_at`

---

## Implementation

- **Sentry WO endpoint:** `backend/app/api/sentry_webhooks.py`
- **Milestone advance:** `WorkOrderRepository.advance_work_order_milestone()` in `backend/app/database/repositories/work_order_repository.py`
- **Technician closeout skill:** `/home/bederf/.sentry/technician-workspace/skills/technician-closeout/SKILL.md`
- **Slash command router:** `backend/app/services/slash_command_router.py`
- **Standard API:** `backend/app/api/work_orders.py`
- **Repository:** `backend/app/database/repositories/work_order_repository.py`

---

## Spare Parts Integration (Phase 209)

Technician work orders are enriched from the spare parts catalog at two points.

### Work Order Creation (`POST /api/work-orders/technician`)

When a work order is created without `parts_needed`, the system queries the `spare_parts` table for the equipment type and auto-populates `parts_required` with matching part names and OEM part numbers.

Example: Creating a work order for `S002-AHU-B01` without specifying parts auto-fills:
```json
"parts_required": [
  "V-belt set (#BELT-AHU-B)",
  "Air filter MERV-13 (set) (#FLT-AHU-M13)",
  "Fan bearing assembly (#BRG-AHU-6205)",
  "Motor capacitor (#CAP-AHU-50UF)",
  "Condensate drain trap (#DRAIN-AHU)"
]
```

### Work Order Completion (`POST /api/work-orders/technician/{id}/complete`)

When a work order is completed with `parts_used`, the system matches each part against the `spare_parts` catalog and decrements `spare_parts_inventory.quantity_on_hand`. This keeps inventory in sync with actual consumption.

**Related files:**
- `backend/app/services/maintenance_recommender.py` — `DEFAULT_MAINTENANCE_ACTIONS` + `COMMON_SPARE_PARTS`
- `backend/app/database/repositories/spare_parts_repository.py` — CRUD + inventory
- `backend/app/api/spare_parts.py` — Parts catalog API
- `docs/03-api-reference/spare-parts-api.md` — Full API reference
- `docs/04-features/spare-parts-catalog.md` — Feature documentation
- **Migration:** `supabase/migrations/209_milestone_sla_work_orders.sql`
