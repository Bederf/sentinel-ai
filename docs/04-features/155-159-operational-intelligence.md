---
title: Operational Intelligence — Correlation Engine & Issue Graph
status: Active
version: 1.0
created: 2026-03-14
updated: 2026-03-15
phases: 155, 156, 159
---

# Operational Intelligence — Correlation Engine & Issue Graph

## Overview

The Operational Intelligence module detects cross-domain issues by correlating signals from email, booking, occupancy, HVAC, and maintenance systems. It clusters related signals into issue records, classifies them by domain, tracks escalation lifecycle, and surfaces role-scoped dashboard cards. The UI renders interactive relationship graphs using Cytoscape.js.

**Core principle:** Dashboard first, graph second. The product value is "the right person sees the right developing issue early enough to act." The graph helps explain — the dashboard delivers.

## Architecture

```
Signal Sources                    Correlation Engine              UI Layer
─────────────                     ──────────────────              ────────
Email intake  ─┐
Booking data  ─┤  Signal Emitter   Candidate        Issue        Dashboard
Occupancy     ─┼─ Bridges ────────► Generation ────► Clustering ─► Cards
HVAC faults   ─┤  (Phase 159)      Weighted         State        Issue
Maintenance   ─┘                   Scoring          Machine      Detail
                                   Time Decay       Routing      Graph
                                   Contradiction    Cards        (Cytoscape)
                                   Detection
```

### Phases

| Phase | Name | Status | Date |
|-------|------|--------|------|
| 155 | Schema & Data Model | Complete | 2026-03-14 |
| 156 | Correlation Engine | Complete (5 plans, 211 tests) | 2026-03-14 |
| 159 | Signal Emitter Bridges | Planned | — |

## Schema (Phase 155)

**14 enums, 9 tables** in Supabase with pgvector for semantic similarity.

### Core Tables

| Table | Purpose |
|-------|---------|
| `signal` | Individual detection from any source module |
| `issue_cluster` | Group of related signals forming an operational issue |
| `issue_classification` | Domain classification with confidence score |
| `entity` | People, rooms, buildings, assets involved |
| `relationship` | Typed edges between entities (for graph traversal) |
| `issue_evidence` | Links signals to clusters with scoring |
| `role_assignment` | Maps roles to locations with domain scoping |
| `dashboard_card` | Role-scoped advisory cards for the operational dashboard |
| `email_thread` | Email thread tracking for signal correlation |

### Key Schema Features

- `signal.emits_multiple` + `signal.parent_signal_id` — one email produces multiple typed signals
- `issue_cluster` lifecycle: emerging → active → escalated → resolved → suppressed (with reopen)
- Cluster merge rules: same location, overlapping time, entity overlap > 0.60
- `role_assignment.location_scope` with wildcard matching (`Fairlands/FA1/L1/*`)
- `dashboard_card` with advisory labels — suggestions only, human decision required

## Correlation Engine (Phase 156)

5 plans, 4 waves, 211 tests. Shipped 2026-03-14.

### Pipeline

1. **Signal fixtures + candidate generation** — time-window pairing, entity overlap scoring
2. **Weighted scoring + contradiction detection** — semantic similarity, location, domain, resolution conflicts
3. **Cluster management + state machine** — merge rules, confidence aggregation, lifecycle transitions
4. **Classification + routing + card generation** — domain scoring, role matching, advisory card creation
5. **Graph traversal + runner + acceptance tests** — BFS/DFS traversal, Fairlands end-to-end

### Acceptance Case: Fairlands Meeting Rooms

The Fairlands email thread (Shaun Grose, Keryn Norman, Greg Temlett, Thandi Dineka) is the acceptance test:
- 9 email signals + booking saturation + occupancy mismatch
- Engine clusters them into `escalated` state
- Classifies `space_optimisation >= 0.90`
- Routes a card to Thandi (concierge) without her being on the email thread

## Frontend — Issue Intelligence Page

### Access

Sidebar → **Intelligence** (Network icon). Available to all users, no module gate.

### Components

| Component | Purpose |
|-----------|---------|
| `IssueIntelligence.tsx` | Page wrapper — status strip, data loading, hosts graph |
| `ClusterGraph.tsx` | Cytoscape.js graph renderer — nodes, edges, detail panel, legend, controls |

### Cluster Status Strip

Displayed at the top of the page:

```
ESCALATED | 10 Signals | 3 Domains | Confidence 0.87 | 60d
```

### Graph View

Interactive Cytoscape.js graph with:
- **Cluster node** (hexagon, centre, pinned by default)
- **Signal nodes** (circles, coloured by domain)
- **Entity nodes** (people=circles, rooms=rounded rectangles)
- **Typed edges** with label visibility rules:
  - Always show: `affects`, `escalated_to`, `owned_by`
  - Hover only: `involves`, `related_to`, `evidenced_by`
- **Hover**: highlights neighbourhood, dims everything else
- **Click**: opens detail panel with metadata, classifications, evidence basis
- **Controls**: fit, zoom in, zoom out
- **Legend**: colour-coded by domain

### Data Source

Currently loads the frozen Fairlands fixture (`src/fixtures/fairlands-cluster-graph.json`). When signal bridges (Phase 159) are active and the live API exists, it will fetch from `GET /api/clusters/{id}/graph`.

## API Contract

### `GET /api/clusters/{id}/graph`

Returns typed nodes and edges per the frozen contract.

#### Node Shape

```json
{
  "id": "signal:a1b2c3d4",
  "node_type": "signal",
  "signal_type": "booking_saturation",
  "domain": "space_optimisation",
  "label": "Booking Saturation",
  "severity": "high",
  "confidence": 0.88,
  "is_collapsed_summary_node": false,
  "metadata": { ... }
}
```

**Rules:**
- `signal_type` is top-level, not buried in metadata
- `severity` and `confidence` are top-level on every node and edge
- `is_collapsed_summary_node` marks summary nodes explicitly
- Node IDs use stable prefixes: `cluster:{uuid}`, `signal:{uuid}`, `entity:{uuid}`

#### Edge Shape

```json
{
  "id": "edge:x1y2z3",
  "source": "cluster:abc123",
  "target": "signal:def456",
  "edge_type": "evidenced_by",
  "weight": 0.85,
  "confidence": 0.90
}
```

**Edge types:** `evidenced_by`, `affects`, `involves`, `escalated_to`, `related_to`, `owned_by`

### Metric Badge Rules

- **Measured values** (objective): always show — `92% booked`, `util 0.31`, `4 no-shows`, `60d`
- **Inferred values** (AI-derived): show only when confidence >= 0.70

## Signal Emitter Bridges (Phase 159 — Planned)

5 bridge services that convert existing SENTINEL detections into correlation signals:

| Bridge | Source | Signal Types |
|--------|--------|-------------|
| Email | `email_intakes` | complaint, escalation, action_request, observation |
| Booking | ghost/block booking services | booking_saturation, no_show_pattern, block_booking |
| Occupancy | MQTT listener, analytics | occupancy_mismatch, underutilisation, sensor_fault |
| Shared utility | — | Common signal creation, entity extraction, dedup |
| Replay tool | Historical data | Replay through bridges for tuning |

## Source Files

| File | Purpose |
|------|---------|
| `frontend/src/components/intelligence/IssueIntelligence.tsx` | Page component |
| `frontend/src/components/intelligence/ClusterGraph.tsx` | Cytoscape.js graph |
| `frontend/src/fixtures/fairlands-cluster-graph.json` | Frozen acceptance fixture |
| `backend/app/data/fixtures/fairlands-cluster-graph.json` | Backend contract fixture |
| `frontend/src/fixtures/fairlands-cluster-graph.html` | Standalone reference render |
| `backend/app/services/correlation/` | Correlation engine services |
| `backend/app/api/clusters.py` | Cluster API stubs |

## Next Steps

1. Build signal emitter bridges (Phase 159) — the real bottleneck
2. Implement live `GET /api/clusters/{id}/graph` against frozen contract
3. Add issue list page / dashboard cards linking into Intelligence page
4. Add evidence timeline panel
5. Replace fixture with live Fairlands cluster
