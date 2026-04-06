---
title: "Work Orders API"
type: "reference"
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

# Work Orders API

## Overview

Work Orders are created through three paths, all persisting to Supabase via the work order repository:

| Path | Trigger | Endpoint |
|------|---------|----------|
| **Slash command** (`/WO_`, `/inspect_`) | User types command in chat or Telegram | `POST /api/sentry/create-work-order` |
| **Claude AI tool** (`create_work_order`) | Claude decides a WO is needed during chat | `POST /api/sentry/create-work-order` (same) |
| **Standard API** | Direct API call from integrations | `POST /api/work-orders` |

## FM Workflow (Recommended)

The AI chat guides users through the proper FM process using clickable slash commands:

```
Alert / User Question
    ↓
1. `/info_{CODE}`    — Equipment diagnostics (health, alerts, service history)
    ↓
2. `/inspect_{CODE}` — Schedule inspection + auto-assign technician
    ↓
3. `/WO_{CODE}`      — Create formal work order with checklist
    ↓
4. `/note_{CODE}`    — Log observations against equipment record
```

Each command renders as a **clickable button** in the web chat. Claude is instructed to present these commands rather than calling `create_work_order` directly, ensuring the FM workflow is followed.

## Sentry Work Order Endpoint

`POST /api/sentry/create-work-order` — Primary creation path used by both slash commands and Claude tool.

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

## Standard Endpoints

- `GET /work-orders` — List work orders (filterable by site, status, assignee)
- `GET /work-orders/{work_order_id}` — Get work order details
- `POST /work-orders` — Create work order (standard API path)
- `GET /assets` — List assets
- `GET /assets/{asset_id}` — Asset details
- `GET /assets/{asset_id}/history` — Asset maintenance history
- `GET /failure-stories` — Equipment failure case studies
- `GET /stats/work-orders` — Work order statistics
- `POST /work-orders/technician` — Assign technician
- `GET /work-orders/technician` — List technician assignments
- `GET /work-orders/technician/{work_order_id}` — Technician WO details

... and 9 more endpoints

## Implementation

- Slash command router: `backend/app/services/slash_command_router.py`
- Sentry WO endpoint: `backend/app/api/sentry_webhooks.py` (line 910)
- Claude tool: `backend/app/services/chat_tools.py` (`create_work_order_chat`)
- Standard API: `backend/app/api/work_orders.py`
- Repository: `backend/app/database/repositories/work_order_repository.py`
