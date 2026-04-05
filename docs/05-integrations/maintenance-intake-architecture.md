---
title: "Maintenance Intake Architecture"
type: "guide"
status: "draft"
version: "1.0.0"
created: "2026-04-05"
updated: "2026-04-05"
author: "Sentinel Development Team"
tags: ["maintenance", "work-orders", "intake", "sla", "adapters", "servicenow", "mri-evolution"]
related:
  - "../07-database/SERVICE_RECORDS_SCHEMA.md"
  - "servicenow-integration.md"
  - "../04-features/maintenance-history-feature.md"
domain: "integration"
audience: "developers"
complexity: "intermediate"
estimated_read_time: 10
---

# Maintenance Intake Architecture

## Problem

Every site has a maintenance management system — MRI Evolution, ServiceNow, a spreadsheet, a phone call log. The system of record varies by site. SENTINEL needs to ingest job card data from whatever source a site uses, normalise it into a canonical form, and provide SLA awareness, breach alerting, and technician accountability on top — regardless of where the data originated.

The maintenance intake layer is the adapter that sits between each site's system of record and SENTINEL's canonical `maintenance_events` table.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                     SENTINEL Maintenance Intake Layer               │
├──────────────┬──────────────┬──────────────┬──────────────────────┤
│ MRI Adapter  │ ServiceNow   │ CSV/SFTP     │ Future adapters      │
│ (Phase 178) │ Adapter      │ Adapter      │                      │
│              │              │              │                      │
│ mri_evolu-   │ maintenance_ │ maintenance_ │ maintenance_          │
│ tion_client  │ adapter_     │ adapter_     │ adapter_...           │
└──────┬───────┴──────┬───────┴──────┬───────┴──────────┬───────────┘
       │              │              │                  │
       ▼              ▼              ▼                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│              maintenance_events  (canonical sink — same table)       │
│   One row per job card, source_system field identifies the origin   │
└────────────────────────────┬────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│              SENTINEL Maintenance Awareness Layer                    │
│                                                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐ │
│  │ SLA Breach    │  │ Priority     │  │ Sentry Telegram          │ │
│  │ Detection     │  │ Normalisation│  │ Technician Workflow      │ │
│  │ (respond/     │  │ (Rev 4 P1-P4 │  │ (attendance, photos,     │ │
│  │  attend/      │  │  translation │  │  completion sign-off)     │ │
│  │  resolve)     │  │  from any    │  │                          │ │
│  └──────────────┘  └──────────────┘  └──────────────────────────┘ │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │ Event Bus: work_order.created / work_order.updated            │  │
│  │ (downstream consumers: alerts, recommendations, audit)        │  │
│  └──────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

**Rule: one adapter per site, one canonical table for all.**

## Canonical Schema: `maintenance_events`

All adapters write to the same table. The `source_system` field identifies which origin system each record came from.

```sql
CREATE TABLE maintenance_events (
    id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    external_ref            TEXT UNIQUE NOT NULL,          -- e.g. "FNBFW:30453"
    source_system           TEXT NOT NULL DEFAULT 'mri_evolution',
    site_id                 UUID REFERENCES sites(id),
    org_id                  UUID,
    building                TEXT,
    location                TEXT,
    discipline              TEXT,
    problem                 TEXT,
    priority_raw            TEXT,                          -- as received from source
    priority_normalised      TEXT CHECK (priority_normalised IN ('P1','P2','P3','P4')),
    sla_respond_hours       INTEGER,
    sla_attend_hours        INTEGER,
    sla_temp_fix_hours      INTEGER,
    sla_resolve_work_days   INTEGER,
    is_ppm                  BOOLEAN DEFAULT FALSE,
    status                  TEXT,
    created_at_source       TIMESTAMPTZ,                   -- T=0 SLA clock
    assigned_at             TIMESTAMPTZ,                   -- T1: technician assigned
    attended_at             TIMESTAMPTZ,                   -- T2: technician on site
    temp_fixed_at           TIMESTAMPTZ,                   -- T3: temporary fix applied
    resolved_at             TIMESTAMPTZ,                   -- T4: fully resolved
    level_of_completion     TEXT,
    sla_pct                 NUMERIC(5,2),
    days_open               INTEGER,
    ingested_at             TIMESTAMPTZ DEFAULT NOW(),
    last_synced_at          TIMESTAMPTZ DEFAULT NOW(),
    metadata                JSONB DEFAULT '{}'::jsonb       -- raw original record
);
```

The table is identical regardless of source system. Each adapter populates the same fields from its own API or data format.

## Adapter Pattern

Each adapter follows the same interface:

```python
class MaintenanceAdapter(ABC):
    """Base class for all maintenance intake adapters."""

    source_system: str  # Identifies this adapter's origin system
    site_id: str       # Which site this adapter syncs

    @abstractmethod
    async def fetch_records(self, since: datetime | None) -> list[dict]:
        """Fetch raw records from the source system since last sync."""

    @abstractmethod
    def normalise(self, raw: dict) -> MaintenanceEvent:
        """Translate source-specific record format to canonical schema."""

    async def run_sync(self) -> SyncResult:
        """Fetch → normalise → upsert → check SLA → publish event."""
```

The base `MaintenanceAdapter` provides:
- `_upsert()` — deduplication by `external_ref`
- `_check_sla_breach()` — threshold-based breach detection
- `_publish_event()` — Event Bus publish (`work_order.created` / `work_order.updated`)
- `_update_sync_state()` — last-sync tracking per adapter

Each subclass only implements `fetch_records()` and `normalise()`.

### Why not a generic webhook per site?

A webhook per site would require each source system to support webhooks — most don't. Polling is universal: any REST API, any SFTP dump, any CSV export can be polled on a schedule. The adapter pattern makes the polling interval, credential management, and field mapping per-source without SENTINEL needing to know the details.

## Priority Normalisation (Universal)

All sources use their own priority labels. SENTINEL normalises to Rev 4 P1–P4:

| Tier | Labels (MRI) | Labels (ServiceNow) | Labels (generic) | Respond | Attend | Temp Fix | Resolve |
|------|-------------|---------------------|-----------------|---------|--------|----------|---------|
| P1 | Very Critical, URGENT, High | 1-Critical, Critical | Emergency | 1h | 4h | 8h | — |
| P2 | Critical | 2-High | High | 2h | 6h | 12h | 3d |
| P3 | Non Critical, Low, Medium | 3-Moderate | Medium | 3h | 8h | 16h | 6d |
| P4 | Routine, Planned | 4-Low, Planned | Low, Routine | 4h | 24h | 48h | 15d |

Each adapter's `normalise()` method applies the priority map for its source system. The `maintenance_events` table always stores the raw label and the normalised tier.

## SLA Breach Detection (Universal)

Three milestone checks run on every ingested or updated record:

| Milestone | Trigger field | SLA clock starts |
|-----------|--------------|-----------------|
| Respond | `assigned_at` set | `created_at_source` |
| Attend | `attended_at` set | `created_at_source` |
| Temp Fix | `temp_fixed_at` set | `created_at_source` |

If the milestone timestamp exceeds the threshold hours from `created_at_source`, a breach event is written to `sla_breach_events`:

```sql
CREATE TABLE sla_breach_events (
    id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    maintenance_event_id    UUID REFERENCES maintenance_events(id),
    breach_type             TEXT CHECK (breach_type IN ('respond','attend','temp_fix','resolve')),
    breached_at             TIMESTAMPTZ DEFAULT NOW(),
    sla_threshold_hours     INTEGER,
    actual_hours            NUMERIC,
    notified                BOOLEAN DEFAULT FALSE
);
```

Breach events flow into the alert pipeline — Sentry Telegram fires alerts at 50%, 80%, and 100% of SLA window consumed.

## What SENTINEL Adds (Regardless of Source)

These capabilities are source-agnostic — they apply to every site's `maintenance_events` records:

1. **Real-time SLA awareness** — 15-min polling interval keeps the canonical table current vs. weekly exports
2. **Breach-before-breach alerting** — Sentry fires at 50%/80% SLA consumed, before the breach is recorded
3. **Cross-site portfolio view** — one query across all `maintenance_events` records regardless of `source_system`
4. **Priority normalisation** — consistent P1–P4 tier across all buildings from all sources
5. **Technician accountability** — Sentry Telegram workflow walks technicians through attendance → photos → completion sign-off, filling the `level_of_completion` gap that most systems leave blank
6. **Cross-building pattern detection** — the `maintenance_events` history across all sites feeds ML models for recurring fault detection

## Implemented Adapters

### MRI Evolution Adapter (Phase 178)

Files: `backend/app/services/mri_evolution_client.py`, `backend/app/services/maintenance_adapter_mri.py`

Polls MRI Evolution REST API every 15 minutes. `FIELD_MAP` translates MRI field names to canonical names — update this when vendor confirms API field names.

Configuration:
```
MRI_EVOLUTION_BASE_URL=https://{tenant}.mrisoftware.com/Evolution/api/v1
MRI_EVOLUTION_API_KEY={from vendor}
MRI_POLL_INTERVAL_MINUTES=15
```

API: `POST /api/maintenance/sync`, `GET /api/maintenance/status`

### Adding a ServiceNow Adapter

1. Create `backend/app/services/maintenance_adapter_servicenow.py`
2. Subclass `MaintenanceAdapter`, implement `fetch_records()` and `normalise()`
3. Apply ServiceNow priority map in `normalise()`
4. Register in `maintenance_adapters.py` registry keyed by `site_id`
5. Add `SERVICENOW_BASE_URL`, `SERVICENOW_API_KEY` to settings
6. Call from APScheduler or event-driven — same pattern as MRI adapter

## Sync State Per Adapter

```sql
CREATE TABLE maintenance_connector_sync (
    id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    adapter_source          TEXT NOT NULL,               -- e.g. 'mri_evolution', 'servicenow'
    site_id                 UUID REFERENCES sites(id),
    last_successful_sync    TIMESTAMPTZ,
    last_sync_attempted     TIMESTAMPTZ,
    records_ingested        INTEGER DEFAULT 0,
    records_updated          INTEGER DEFAULT 0,
    errors                  INTEGER DEFAULT 0
);
```

`external_ref` is the deduplication key across all adapters. No two adapters may produce the same `external_ref` — each source system's IDs must be namespaced (e.g. `mri:30453`, `sn:INC001234`).

## API Endpoints (Source-Agnostic)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/maintenance/sync` | Trigger sync for a site adapter (auth required) |
| `POST` | `/api/maintenance/webhook` | Receive push events from any source system |
| `GET`  | `/api/maintenance/status` | Return last sync state per site |
| `GET`  | `/api/maintenance/events` | Query `maintenance_events` with filters |

Webhook is source-agnostic — each adapter registers its own webhook URL with its source system. The endpoint parses the incoming payload and routes to the correct adapter.
