---
title: "SENTINEL Current Stack Discovery Report"
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

# SENTINEL Current Stack Discovery Report

Last updated: 2026-03-16

## Purpose
This document captures the current on-prem SENTINEL stack as discovered from the repository, local configuration, startup scripts, systemd units, and visible runtime processes.

This is a discovery report only. It does not redesign the system.

## Discovery Method
Sources used for this report:
- repository structure and source files
- [docker-compose.yml](/opt/bms-intelligence/docker-compose.yml)
- [supabase/config.toml](/opt/bms-intelligence/supabase/config.toml)
- [backend/.env](/opt/bms-intelligence/backend/.env) and root [.env](/opt/bms-intelligence/.env)
- startup scripts and service units
- visible local processes from `ps`
- migration files under [supabase/migrations](/opt/bms-intelligence/supabase/migrations) and [backend/supabase/migrations](/opt/bms-intelligence/backend/supabase/migrations)

Discovery limits:
- live Docker inspection was blocked by sandboxed Docker socket access
- `systemctl` queries were blocked by DBus permissions
- direct `psql` inspection of the local database was blocked by sandbox socket restrictions

Where database schemas, extensions, or services could not be queried directly, they are marked as inferred from config, migrations, or process names.

## System Overview
SENTINEL is currently a mixed local appliance stack centered on:
- a FastAPI backend
- a React/Vite frontend
- a local Supabase stack used as the primary PostgreSQL platform
- local document and JSON-backed data stores
- local workflow and support services including n8n, Ollama, Redis, Loki, Promtail, Caddy, and InfluxDB

The current runtime is mostly local-first, but the repository still contains older cloud-facing assumptions and some cloud tunnel/runtime remnants. The current stack is therefore best described as:
- primary runtime: local/on-prem
- current dependencies: strongly local
- residual external-era artifacts: still present

## Repository Structure
High-level tree with the most important areas:

```text
/opt/bms-intelligence
├── backend/                 FastAPI APIs, domain services, repositories, ML logic
├── frontend/                React + TypeScript + Vite UI
├── docs/                    Product, architecture, operations, feature, and integration docs
├── supabase/                Local Supabase config and SQL migrations
├── infrastructure/          Deployment and infrastructure assets
├── infra/                   Systemd and operational support files
├── n8n/                     n8n workflow assets and related integration scaffolding
├── firmware/                Embedded/edge node firmware and occupancy node code
├── e2e/                     Playwright end-to-end tests
├── scripts/                 Operational scripts, including backup scripts
├── backups/                 Backup output structure
├── simbiot_concept/         SIMBIOT integration concept assets
├── docker-compose.yml       Local container stack definition
├── start-backend.sh         Backend startup helper
├── start-frontend.sh        Frontend startup helper
├── sentinel-backend.service Systemd unit for backend
└── sentinel-frontend.service Systemd unit for frontend
```

Important folders:

### `backend/`
Primary application logic.
- `backend/app/api/`: FastAPI route modules
- `backend/app/services/`: ingestion, rules, AI, simulation, storage, protocol, memory, diagnostics
- `backend/app/database/`: Supabase client and repository layer
- `backend/app/models/`: Pydantic/domain models
- `backend/app/data/`: local JSON and file-backed domain/state storage
- `backend/tests/`: Python tests

### `frontend/`
Primary local operator UI.
- `frontend/src/components/`: most UI modules
- `frontend/src/pages/`: route/page compositions
- `frontend/src/lib/api/`: frontend API clients
- `frontend/src/contexts/`: selected site, module, simulation, and app contexts

### `supabase/`
Local database platform assets.
- `supabase/config.toml`: local Supabase service definitions and port map
- `supabase/migrations/`: schema evolution, pgvector/RAG, solar, auth, storage-related SQL

### `docs/`
Architecture, feature, and operating docs.
- current repo contains both current local-first docs and older cloud-era docs

### `scripts/`
Operational helpers.
- backup scaffolding now exists under [scripts/backup](/opt/bms-intelligence/scripts/backup)

### `backend/app/data/`
Large local filesystem data area used for:
- building JSON
- site data
- simulation state
- space occupancy data
- Niagara discovery mappings
- RAG knowledge artifacts
- legacy/fallback storage
- JSON backup artifacts

## Runtime Service Inventory
The table below combines services defined in files with services visible in the local process list.

| Service | Purpose | Technology | Expected Node | Dependencies |
|---|---|---|---|---|
| `backend` | Main application API, orchestration, ingestion, simulation, business logic | FastAPI + Uvicorn | NVIDIA | local Postgres/Supabase, Redis, local files, n8n, Ollama |
| `frontend` | Local operator UI | React + Vite preview | NVIDIA | backend API |
| `caddy` | Reverse proxy / local HTTPS entrypoint | Caddy | NVIDIA | backend, frontend |
| `supabase-db` | Primary relational database | PostgreSQL via local Supabase | NVIDIA | local storage |
| `postgrest` | REST API over Postgres | Supabase component | NVIDIA | Postgres |
| `supabase-auth` | Local auth service | Supabase Auth | NVIDIA | Postgres |
| `supabase-storage` | Object/file bucket layer | Supabase Storage | NVIDIA | Postgres, filesystem/object store |
| `supabase-studio` | Admin UI | Supabase Studio | NVIDIA | Postgres |
| `supabase-realtime` | Realtime subscriptions | Supabase Realtime | NVIDIA | Postgres |
| `inbucket` | Local mail capture/test mailbox | Supabase component | NVIDIA | none significant |
| `redis` | local cache / queue/helper runtime | Redis | NVIDIA | backend |
| `n8n` | workflow and email intake automation | n8n | NVIDIA | backend API, local mail/integration inputs |
| `ollama` | local model serving | Ollama | NVIDIA | local model files, backend |
| `influxdb` | time-series data store and metrics support | InfluxDB | NVIDIA | local volumes |
| `loki` | log aggregation | Loki | NVIDIA | promtail |
| `promtail` | log shipping | Promtail | NVIDIA | Loki |
| `wazuh-agent` | host monitoring/security agent | Wazuh Agent | NVIDIA | Wazuh manager if connected |
| `fail2ban` | local host protection | Fail2Ban | NVIDIA | log sources |
| `cloudflared` | external tunnel runtime artifact still present | Cloudflare Tunnel | NVIDIA | external tunnel endpoint |
| `sentry.service` | local Sentry/self-hosted monitoring support, inferred from unit file | Python/service stack | NVIDIA | local config, storage |
| disk monitor timer | routine disk health check | systemd timer/script | NVIDIA | local filesystem |
| postgres backup timer | scheduled logical backups, present in repo | systemd timer/script | NVIDIA | local Postgres tools |
| Raspberry Pi support services | not explicitly codified in repo; inferred support role only | unknown/lightweight helpers | Raspberry Pi | NVIDIA node health and local network |

Notes:
- Docker-defined services include [docker-compose.yml](/opt/bms-intelligence/docker-compose.yml) entries for `backend`, `frontend`, `caddy`, `influxdb`, `loki`, `promtail`, `wazuh-agent`, and `fail2ban`.
- Local Supabase services are configured in [supabase/config.toml](/opt/bms-intelligence/supabase/config.toml) and were also evidenced by live `postgres`/`postgrest` processes.
- `cloudflared` is still running locally. That is part of the current stack, but it is inconsistent with a strict local-only runtime target.

## Current Architecture Diagram
```mermaid
flowchart LR
    subgraph Building["Building / Site Inputs"]
        BMS["BMS / BACnet / Niagara / telemetry"]
        EMAIL["Email inputs / intake"]
        DOCS["Documents / manuals / uploads"]
        SIM["Lifecycle and space simulation"]
        NOTES["Technician notes / maintenance events"]
    end

    subgraph NVIDIA["NVIDIA Main Node"]
        FE["Frontend UI :9096"]
        CADDY["Caddy"]
        API["FastAPI backend :9095"]
        N8N["n8n :5678"]
        OLLAMA["Ollama :11434"]
        REDIS["Redis"]
        PG["Local Supabase Postgres :55322"]
        POSTGREST["PostgREST :55321"]
        STUDIO["Supabase Studio :55323"]
        STORAGE["Supabase Storage"]
        INFLUX["InfluxDB :8086"]
        LOKI["Loki"]
        PROMTAIL["Promtail"]
        FILES["Local filesystem / backend/app/data"]
        BACKUP["Backup scripts / systemd timers"]
    end

    subgraph PI["Raspberry Pi Support Node"]
        PIHELP["Support role inferred only\nwatchdog / buffer / helper"]
    end

    BMS --> API
    EMAIL --> N8N
    N8N --> API
    DOCS --> API
    SIM --> API
    NOTES --> API

    FE --> CADDY
    CADDY --> API
    API --> PG
    API --> STORAGE
    API --> FILES
    API --> REDIS
    API --> OLLAMA
    API --> INFLUX
    POSTGREST --> PG
    STUDIO --> PG
    BACKUP --> PG
    PROMTAIL --> LOKI
    PIHELP -. local network / support .-> NVIDIA
```

## Database Architecture
### Current Primary Database
Current evidence strongly indicates that local Supabase Postgres is the primary database platform.

Evidence:
- [backend/.env](/opt/bms-intelligence/backend/.env) sets:
  - `SUPABASE_URL=http://127.0.0.1:55321`
  - `DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:55322/postgres`
  - `USE_JSON_STORAGE=false`
- [supabase/config.toml](/opt/bms-intelligence/supabase/config.toml) defines local API, DB, Studio, Storage, Auth, Realtime, and Inbucket services
- [backend/app/database/supabase_client.py](/opt/bms-intelligence/backend/app/database/supabase_client.py) creates the shared SDK client used throughout the app

### Exposed Local Supabase Ports
From [supabase/config.toml](/opt/bms-intelligence/supabase/config.toml):
- API / PostgREST: `55321`
- PostgreSQL: `55322`
- Studio: `55323`
- Inbucket: `55324`

### Schemas
Direct live schema inspection was blocked, but current config and migrations indicate:
- `public`
- `graphql_public`
- `extensions`

### Enabled Extensions
Direct live extension inspection was blocked. Based on config, migrations, and process names, the following are present or strongly implied:
- `pgvector` / `vector`
- `pg_net`
- `pg_cron`
- standard Supabase extension set

### Key Table Groups
The codebase shows extensive use of Postgres tables through the Supabase SDK. The following groups are directly evidenced by migrations, repositories, and API/service queries.

#### Core site and asset model
- `sites`
- `equipment`
- `sensors`
- `hvac_zones`
- `zone_display_mappings`
- `site_modules`
- `site_module_configs`
- `cross_module_links`

Purpose:
- site identity
- asset inventory
- zones
- module activation and per-site configuration

#### Alerts, work, and operational state
- `alerts`
- `predictions`
- `work_orders`
- `asset_health_snapshots`
- `asset_health_daily_rollups`
- `api_keys`

Purpose:
- active alerting
- predictive maintenance
- work orchestration
- operational health history

#### Energy, lighting, and building telemetry
- `energy_consumption_history`
- `power_meter_validations`
- `lighting_energy`
- `dali_sensors`
- `dali_luminaires`
- `telemetry`

Purpose:
- energy and power history
- lighting/DALI integration
- broader telemetry persistence

#### Solar and BESS
From [supabase/migrations/071_solar_schema.sql](/opt/bms-intelligence/supabase/migrations/071_solar_schema.sql):
- `solar_sites`
- `solar_plants`
- `solar_inverters`
- `solar_bess`
- `solar_meters`
- plus snapshot/aggregate tables referenced in code:
  - `solar_annual_simulations`
  - `solar_hourly_snapshots`
  - `solar_daily_aggregates`

#### Documents and vector/RAG
From code and pgvector migration references:
- `documents`
- `document_chunks`
- `document_equipment_links`

Purpose:
- indexed docs
- chunk embeddings
- links between manuals and equipment

#### Settings and configuration
- `system_settings`
- `public_settings`
- `municipal_tariff_schedules`
- `municipal_accounts`

#### Memory and AI support
- `agent_memory`
- `ml_models`
- `model_thresholds`

### Database Access Pattern
Current access pattern is strongly coupled to the Supabase Python client:
- [backend/app/database/supabase_client.py](/opt/bms-intelligence/backend/app/database/supabase_client.py)
- extensive `.table(...)`, `.rpc(...)`, and storage bucket access across APIs and services

This is a Postgres-backed system today, but much of the access layer is written against Supabase-specific SDK conventions rather than a plain SQL or repository abstraction boundary.

## Storage Architecture
### Local Filesystem Storage
The repository uses a large local data root under [backend/app/data](/opt/bms-intelligence/backend/app/data).

Important local storage areas:
- [backend/app/data/buildings](/opt/bms-intelligence/backend/app/data/buildings): building/site JSON
- [backend/app/data/sites](/opt/bms-intelligence/backend/app/data/sites): site-level data
- [backend/app/data/simulation](/opt/bms-intelligence/backend/app/data/simulation): lifecycle and synthetic runtime state
- [backend/app/data/space](/opt/bms-intelligence/backend/app/data/space): occupancy, room, and space analytics files
- [backend/app/data/niagara](/opt/bms-intelligence/backend/app/data/niagara): discoveries and mappings
- [backend/app/data/rag_knowledge](/opt/bms-intelligence/backend/app/data/rag_knowledge): documentation/RAG assets
- [backend/app/data/decision_memory](/opt/bms-intelligence/backend/app/data/decision_memory): JSON-based decision learning records
- [backend/app/data/supabase_backup](/opt/bms-intelligence/backend/app/data/supabase_backup): legacy JSON backup exports
- [backend/app/data/bms_simulator](/opt/bms-intelligence/backend/app/data/bms_simulator): simulator alarms, trends, exports

### Supabase Storage
[backend/app/services/storage_service.py](/opt/bms-intelligence/backend/app/services/storage_service.py) uses a Supabase Storage bucket:
- bucket: `building-documents`
- object path format: `{site_id}/{filename}`

This is used for uploaded documents and downloadable signed URLs.

### File Types Currently Stored
- building JSON and configuration
- simulation state and time-series JSONL
- discovery mappings and protocol metadata
- uploaded documents and manuals
- backup/export files
- RAG source assets
- occupancy and meeting-room workflow artifacts

## Data Ingestion Pipelines
### Summary Table
| Source Type | Ingestion Service | Processing Pipeline | Destination |
|---|---|---|---|
| BMS / Niagara oBIX | [backend/app/api/niagara.py](/opt/bms-intelligence/backend/app/api/niagara.py) | discovery, mapping, normalization | Supabase tables + local discovery files |
| BACnet/IP | [backend/app/api/niagara_bacnet.py](/opt/bms-intelligence/backend/app/api/niagara_bacnet.py) | device/point discovery, classification, mapping | Supabase + local mapping/discovery state |
| Zone/desk/site onboarding | [backend/app/services/zone_ingestion_service.py](/opt/bms-intelligence/backend/app/services/zone_ingestion_service.py) | validation and upsert | Supabase |
| Solar/BESS | [backend/app/services/solar_ingestion_service.py](/opt/bms-intelligence/backend/app/services/solar_ingestion_service.py) | load, normalize, seed/fallback | Supabase with JSON fallback |
| Email intake | [backend/app/api/sentry_email.py](/opt/bms-intelligence/backend/app/api/sentry_email.py), n8n workflows | parse, correlate, route | Supabase + local workflow state |
| Document uploads | [backend/app/api/upload.py](/opt/bms-intelligence/backend/app/api/upload.py), [backend/app/api/documents.py](/opt/bms-intelligence/backend/app/api/documents.py) | upload, parse, link, chunk | Supabase Storage + document/vector tables |
| Municipal billing and PDFs | OCR/PDF extraction services | extract, normalize | database + local artifacts |
| Simulation | [backend/app/api/lifecycle_simulation.py](/opt/bms-intelligence/backend/app/api/lifecycle_simulation.py), [backend/app/api/simulation.py](/opt/bms-intelligence/backend/app/api/simulation.py) | generate synthetic BMS/building state | local simulation files, then app ingestion paths |
| Technician notes / maintenance records | repository/service paths across alerts, maintenance, memory, and case data | stored and later surfaced to AI/memory | Supabase + local JSON |

### Current Pattern
The ingestion pattern is mixed:
- some sources write directly to Supabase tables
- some sources use local JSON first or as fallback
- some domains seed Supabase from local JSON when tables are empty

This means current ingestion is functional but not fully consolidated into a single storage strategy.

## AI and Reasoning Components
### Current AI Modules Found
- local/document RAG:
  - [backend/app/services/vector_db.py](/opt/bms-intelligence/backend/app/services/vector_db.py)
  - [backend/app/services/doc_rag_service.py](/opt/bms-intelligence/backend/app/services/doc_rag_service.py)
- model registry / thresholds:
  - `backend/app/ml/models/model_registry_db.py`
- optimizer/orchestration:
  - `backend/app/services/ai_optimizer.py`
- memory:
  - [backend/app/database/repositories/agent_memory_repository.py](/opt/bms-intelligence/backend/app/database/repositories/agent_memory_repository.py)
  - [backend/app/services/decision_memory_service.py](/opt/bms-intelligence/backend/app/services/decision_memory_service.py)
- local model service runtime:
  - [infra/systemd/ollama.service](/opt/bms-intelligence/infra/systemd/ollama.service)

### Vector and Embedding Path
[backend/app/services/vector_db.py](/opt/bms-intelligence/backend/app/services/vector_db.py) shows:
- documents inserted into `documents`
- chunks inserted into `document_chunks`
- embeddings generated via the internal embedding service
- pgvector-backed retrieval through Supabase/Postgres

### RAG Query Path
[backend/app/services/doc_rag_service.py](/opt/bms-intelligence/backend/app/services/doc_rag_service.py) shows:
- query enters documentation search
- hybrid search is performed in the vector service
- results are assembled into AI context for downstream response generation

### Current AI Runtime State
The repository supports both:
- local model serving through Ollama
- external-provider configuration through environment variables

So the current codebase is capable of local AI operation, but not all AI-related configuration and docs have been fully narrowed to local-only assumptions yet.

## Memory Pipeline Status
Target stages examined:
- extraction
- consolidation
- structured storage
- retrieval

### 1. Extraction
Existing implementation:
- email intake parsing
- document upload and OCR extraction
- municipal PDF extraction
- simulation/event generation
- notes, alerts, and maintenance records entering repositories/services

Status:
- partially implemented across several services
- extraction exists, but is spread across domains rather than centralized

### 2. Consolidation
Existing implementation:
- some RAG chunking/indexing
- some decision pattern extraction in [decision_memory_service.py](/opt/bms-intelligence/backend/app/services/decision_memory_service.py)
- some site/equipment memory shaping in [agent_memory_repository.py](/opt/bms-intelligence/backend/app/database/repositories/agent_memory_repository.py)

Status:
- partial
- fragmented between vector/RAG, agent memory, decision memory, and domain workflows

### 3. Structured Storage
Existing implementation:
- Supabase/Postgres tables for agent memory, docs, telemetry, predictions, assets
- JSON files for decision memory and several local operational domains

Status:
- present
- split across Postgres and JSON

### 4. Retrieval Layer
Existing implementation:
- doc RAG hybrid search
- agent memory repository queries by site/equipment
- application repositories used by APIs and services

Status:
- present
- not unified behind one memory service boundary

### Memory Categories Already Visible
#### Semantic memory
Facts and asset knowledge:
- documents
- document chunks
- equipment links
- building/equipment notes

#### Episodic memory
Event and operational history:
- alerts
- predictions
- work orders
- decision records
- maintenance/case artifacts

#### Procedural memory
Workflow/repair logic:
- embedded in docs, playbooks, and some decision patterns
- not yet clearly separated into a dedicated procedural memory layer

### Memory Technical Debt
- memory is spread across Supabase tables, JSON files, and RAG content
- decision memory is still JSON-first
- agent memory has JSON fallback, which keeps resilience but increases fragmentation
- no single authoritative memory service boundary yet

## Networking Model
### Known Local Ports
From config and visible processes:
- backend API: `9095`
- frontend preview: `9096`
- Supabase API / PostgREST: `55321`
- PostgreSQL: `55322`
- Supabase Studio: `55323`
- Inbucket: `55324`
- n8n: `5678`
- Ollama: `11434`
- InfluxDB: `8086`
- Caddy: `80`, `443`

### Internal Communication
- frontend calls backend over local HTTP
- backend calls local Supabase/Postgres
- backend uses Supabase Storage locally
- backend calls Ollama locally
- n8n sends email/workflow traffic into backend APIs
- backend persists supplementary state to filesystem
- logging stack collects local logs through Promtail into Loki

### Current Communication Paths
- operator browser -> frontend -> backend
- backend -> Supabase/Postgres
- backend -> Supabase Storage
- backend -> local files
- backend -> Ollama
- n8n -> backend
- backend -> Redis / Influx / logging services as configured

### Networking Risk
`cloudflared` is still visible as a runtime process and tunnel scripts remain in the repo. That is part of the current stack, but it contradicts a strict local-only deployment objective.

## Hardware Allocation
### NVIDIA Device
The repository strongly suggests the NVIDIA device is the main compute node.

Current/expected responsibilities on the NVIDIA node:
- FastAPI backend
- React frontend hosting
- local Supabase/Postgres stack
- n8n
- Ollama
- Redis
- log/monitoring services
- backup services
- protocol/API integrations
- simulation and AI orchestration

Evidence:
- startup scripts
- systemd units
- architecture docs such as [docs/02-architecture/EDGE-COMPUTE-DISCOVERY-REPORT.md](/opt/bms-intelligence/docs/02-architecture/EDGE-COMPUTE-DISCOVERY-REPORT.md)

### Raspberry Pi
The Raspberry Pi role is not clearly implemented in deployment scripts in this repository.

Current status:
- expected only as a support node based on system intent
- concrete Pi-specific deployment manifests were not found in the main runtime path
- firmware and occupancy-node code exist under [firmware/](/opt/bms-intelligence/firmware), but that is not the same as a Pi service deployment definition

Current conclusion:
- NVIDIA allocation is clear
- Raspberry Pi allocation is still mostly inferred, not operationally codified in this repo

## Backup and Recovery
### Current Backup Methods Found
#### Legacy JSON export path
- [backend/scripts/backup_supabase_to_json.py](/opt/bms-intelligence/backend/scripts/backup_supabase_to_json.py)
- output area: [backend/app/data/supabase_backup](/opt/bms-intelligence/backend/app/data/supabase_backup)

This is a JSON export of Supabase-backed data and has historically been used as the backup path.

#### PostgreSQL logical backup path
Present in the repo now:
- [scripts/backup/postgres_logical_backup.sh](/opt/bms-intelligence/scripts/backup/postgres_logical_backup.sh)
- [scripts/backup/run_postgres_backup_daily.sh](/opt/bms-intelligence/scripts/backup/run_postgres_backup_daily.sh)
- [infra/systemd/sentinel-postgres-backup.service](/opt/bms-intelligence/infra/systemd/sentinel-postgres-backup.service)
- [infra/systemd/sentinel-postgres-backup.timer](/opt/bms-intelligence/infra/systemd/sentinel-postgres-backup.timer)
- [docs/operations/postgres-logical-backup.md](/opt/bms-intelligence/docs/operations/postgres-logical-backup.md)

### Current Operational State
Current best-known state:
- JSON export backup exists
- PostgreSQL logical backup scripts now exist in the repo
- scheduled timer unit files exist in the repo
- host-level enablement of the timer was not verified in this discovery pass

### Restore Capability
Direct restore validation was not executed in this discovery pass.
Current restore maturity appears lower than backup maturity and should be treated as an area needing formal verification.

## Supabase Dependency Assessment
### Core Dependencies
Current code is tightly coupled to local Supabase for:
- primary Postgres access via the Supabase Python SDK
- storage bucket access
- PostgREST-based table operations
- local auth/storage/realtime platform services

Key evidence:
- [backend/app/database/supabase_client.py](/opt/bms-intelligence/backend/app/database/supabase_client.py)
- [backend/app/services/storage_service.py](/opt/bms-intelligence/backend/app/services/storage_service.py)
- [backend/app/services/vector_db.py](/opt/bms-intelligence/backend/app/services/vector_db.py)
- large repository surface under [backend/app/database/repositories](/opt/bms-intelligence/backend/app/database/repositories)

### Optional Convenience
Supabase is also serving as:
- Studio/admin UI
- Storage convenience layer
- local auth convenience layer
- local Realtime capability

These are useful locally, but not all of them need to own core business logic.

### Replaceable Later
Likely replaceable later with modest to significant effort:
- direct table CRUD wrappers if abstracted
- storage access wrappers
- parts of document/vector data access if rewritten against plain Postgres and object storage abstractions

Less replaceable quickly:
- broad SDK usage spread across API/service code
- any logic that currently assumes Supabase Storage and SDK semantics directly

### Current Assessment
Supabase is not just local infrastructure today. It is also a major application-facing dependency across the repository.

## Major Risks and Unknowns
### Risks
- strong Supabase SDK coupling across backend services and repositories
- split storage model between Postgres and JSON
- current backup story is in transition from JSON export to Postgres logical backup
- residual cloud-era runtime/config artifacts remain in the stack
- Raspberry Pi role is underspecified in operational deployment assets
- multiple persistence patterns increase recovery and consistency risk

### Unknowns
- exact live enabled Postgres extensions
- exact installed/active Docker container set on host
- exact live systemd enabled state for all repo-provided units
- exact Raspberry Pi runtime responsibilities today
- exact restore verification maturity for database recovery

## Clarification Questions
1. Is the local Supabase stack started via Supabase CLI on the NVIDIA host, or through a separate service wrapper outside this repo?
2. Which services are actually intended to remain in Docker in production versus systemd-native host services?
3. Is `cloudflared` still intentionally part of the deployed runtime, or is it a legacy artifact?
4. What exactly runs on the Raspberry Pi today: watchdog only, protocol bridging, buffering, or something else?
5. Are `realtime`, `auth`, and `storage` all actively used in production, or are some only enabled because Supabase ships them by default?
6. Has the new Postgres logical backup timer been installed and enabled on the target appliance, or is it still repo scaffolding only?
7. Which domains are intentionally JSON-backed long term, and which are only temporary fallbacks?

## Current State Summary
The current SENTINEL stack is already substantially local and appliance-oriented:
- local FastAPI backend
- local React frontend
- local Supabase/Postgres as the main database platform
- local workflow, AI, and logging services
- substantial local filesystem data usage

At the same time, the current system is not yet a cleanly separated local appliance stack:
- Supabase SDK coupling is deep
- JSON fallback/storage remains common
- backup and restore operational maturity is uneven
- Pi support-node responsibilities are not explicit
- some external-era assumptions remain in code, config, and runtime artifacts

This report should be used as the baseline for any later architecture decisions.
