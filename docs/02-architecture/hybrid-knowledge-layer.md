---
title: "Hybrid Knowledge Layer"
type: "architecture"
status: "implemented"
version: "1.1.0"
created: "2026-03-05"
updated: "2026-03-05"
author: "SENTINEL Development Team"
tags: ["hybrid-rag", "knowledge-graph", "telemetry", "context-assembly", "digital-twin"]
related: ["brick-ontology-layer.md", "system-overview.md", "../08-ai-ml/rag-integration-overview.md"]
domain: "ai-ml"
audience: "developers"
complexity: "advanced"
estimated_read_time: 15
---

# Hybrid Knowledge Layer

Context assembly engine that combines document RAG, asset knowledge graph, and live telemetry for AI reasoning.

## Overview

SENTINEL currently reasons from telemetry (via `_gather_ml_context()` in `ai_optimizer.py`) and documents (via `doc_rag_service.py`) independently. The Hybrid Knowledge Layer merges these with a structured asset graph so agents can answer operational questions that span all three data types in a single query.

## Problem

Single-source reasoning hits a wall:

| Question | Requires |
|----------|---------|
| "What's the current chiller status?" | Telemetry only |
| "What does the SLA say about response time?" | Documents only |
| "The generator alarmed -- who is the vendor and what did the last inspection find?" | Telemetry + Graph + Documents |

The third type of question is what facility managers actually ask. It requires cross-referencing live state, asset relationships, and historical documents.

## Architecture

```
                    SENTINEL Agents
                (diagnostics / dispatch / AI)
                          |
                 Hybrid Knowledge Layer
                          |
        +---------+-------+--------+---------+
        |         |                |         |
        v         v                v         v
  Document RAG   Asset Graph    Telemetry   MRI Exports
  (doc_rag_svc)  (Brick)       (SIMBIOT)   (Drive intake)
        |         |                |
        +---------+-------+--------+
                          v
               Context Assembly Engine
              (hybrid_query_service.py)
```

## Three Data Layers

### Layer 1: Document RAG (existing)

**Service:** `doc_rag_service.py`
**Store:** pgvector (Supabase)

Current sources:
- SENTINEL system documentation (demo/Q&A)

Planned sources (via Drive intake pipeline):
- MRI Evolution inspection reports
- PPM schedules
- Maintenance contracts and SLAs
- OEM manuals
- Compliance certificates

**Key metadata per chunk:**
- `facility_id` - site filter
- `asset_id` - equipment filter
- `document_type` - category filter (inspection_report, contract, asset_register, etc.)
- `vendor` - vendor filter

### Layer 2: Asset Knowledge Graph (implemented)

**Service:** `brick_service.py` (runtime queries) + `brick_autogen_service.py` (graph generation)
**Store:** RDFLib in-memory graph from TTL file (Neo4j or Postgres+AGE for future scale)

Models equipment relationships that vector search cannot answer:

```
S002-CHILLER-B1-001
    |-- has_point --> chilled_water_temperature (BACnet AI:1000)
    |-- has_point --> chilled_water_setpoint (BACnet AV:1001)
    |-- has_location --> site-002/B1/Zone-B1-001
    |-- maintained_by --> XYZ_Power (vendor)
    |-- covered_by --> Contract-9932 (SLA: 4hr response)
```

**Auto-generated from:** Equipment table + discovery mappings + PointClassifier output.
See [Brick Ontology Layer](brick-ontology-layer.md) for details.

### Layer 3: Telemetry (existing)

**Services:** SIMBIOT adapters, `influxdb_service.py`, simulation engine
**Store:** InfluxDB / Redis streams / simulation state

Live operational data:
- Sensor readings (temperature, pressure, flow, power)
- Equipment status (running, fault, standby)
- Alarms and alarm history
- ML model outputs (anomaly scores, fault classifications, LSTM forecasts)

Already integrated into AI via `_gather_ml_context()` in `ai_optimizer.py`.

## Context Assembly Engine

### Service: `hybrid_query_service.py` (implemented)

**Status:** Implemented. 20 tests passing (`tests/services/test_hybrid_query_service.py`).

```python
from app.services.hybrid_query_service import get_hybrid_query_service

svc = get_hybrid_query_service("site-002")
ctx = await svc.query(
    equipment_id="S002-CHILLER-B1-001",  # or bacnet_ref="CH-1.ChwSupplyTemp"
    question="What is the maintenance history?",
    include_documents=True,
    include_telemetry=True,
    include_ml=True,
    include_points=True,
)

# Use in AI prompt
prompt_text = ctx.format_for_prompt()  # Readable text block
payload = ctx.to_dict()                # JSON-serializable dict
```

**Query pipeline (5 steps):**

1. **Resolve equipment** — from `equipment_id` directly, or via `bacnet_ref` → Brick graph resolution
2. **Brick graph context** — equipment type, manufacturer, model, location path, points, protocol
3. **Document RAG** — search `doc_rag_service` with equipment type + question filters
4. **Telemetry** — pull operating data, health score, status from equipment repository
5. **ML context** — per-equipment anomaly scores, fault classifications, health trends

**Data sources tracked in `ctx.sources_used`:** `brick_resolution`, `brick_graph`, `document_rag`, `telemetry`, `ml_models`

### Example Merged Context Payload

```json
{
  "asset": {
    "id": "S002-GEN-B1-001",
    "type": "generator",
    "manufacturer": "Caterpillar",
    "vendor": "XYZ Power",
    "sla_response_hours": 4,
    "location": "site-002/B1/Plantroom",
    "contract_id": "Contract-9932"
  },
  "telemetry": {
    "oil_pressure_psi": 38,
    "coolant_temp_c": 92,
    "status": "alarm",
    "alarm_code": "LOW_OIL_PRESSURE",
    "last_updated": "2026-03-05T09:12:00Z"
  },
  "documents": [
    {
      "doc_id": "MRI-REP-2023-991",
      "type": "inspection_report",
      "date": "2023-11-14",
      "excerpt": "Generator oil pressure below specification. Oil pump showing wear...",
      "relevance_score": 0.92
    },
    {
      "doc_id": "CONTRACT-9932-SLA",
      "type": "contract",
      "excerpt": "Clause 4.2: Emergency response within 4 hours for critical faults...",
      "relevance_score": 0.87
    }
  ]
}
```

### Query Flow

```
Agent question: "Generator alarm triggered. What's the issue and who is responsible?"
     |
     v
1. Detect asset_id from alarm event (simbiot_point_id -> Brick graph -> equipment)
     |
     v
2. Pull telemetry: oil_pressure=38 psi (low), coolant_temp rising
     |
     v
3. Traverse graph: GEN-B1-001 -> vendor=XYZ Power -> SLA=4hr
     |
     v
4. Search RAG: inspection reports for GEN-B1-001 -> previous oil pump wear
     |
     v
5. Assemble context -> send to Claude
     |
     v
Agent output: "Probable oil pump failure based on low oil pressure (38 psi)
              and previous inspection finding oil pump wear (Nov 2023).
              Dispatch vendor XYZ Power. Required response: 4 hours per SLA."
```

## Implementation Status

### Completed

| Component | Service | Tests | Status |
|-----------|---------|-------|--------|
| Brick graph auto-gen | `brick_autogen_service.py` | 28 | Implemented |
| Brick runtime queries | `brick_service.py` | 24 | Implemented |
| Hybrid context assembly | `hybrid_query_service.py` | 20 | Implemented |
| Telemetry -> AI | `_gather_ml_context()` in `ai_optimizer.py` | - | Working |
| Document RAG | `doc_rag_service.py` | - | System docs only |

### Remaining

| Component | Service | Priority |
|-----------|---------|----------|
| Drive document intake | `drive_intake_agent.py` | Medium |
| Wire hybrid into AI optimizer | Replace `_gather_ml_context()` with hybrid | Medium |
| Vendor/contract enrichment | Brick graph extensions | Low |

### Generated Artifacts (site-002)

| Artifact | Path | Size |
|----------|------|------|
| Brick TTL graph | `data/buildings/site-002/brick/site-002_brick.ttl` | ~2.2 MB |
| Resolution index | `data/buildings/site-002/brick/site-002_resolution_index.json` | ~54 KB |

**Graph stats:** 85 equipment, 267 points, 85 locations, 241 BACnet refs indexed, 86 BACnet objects indexed

## Operational Benefits

| Capability | Single-Source | Hybrid |
|-----------|-------------|--------|
| "What's the temperature?" | Telemetry | Telemetry |
| "What does the SLA say?" | RAG search | RAG search |
| "Generator alarmed -- who and what?" | Manual lookup | Automatic: telemetry + graph + docs |
| Root cause analysis | ML anomaly only | ML + historical inspections + OEM specs |
| Technician dispatch | Alert-based | Graph-informed (vendor, SLA, location) |
| Compliance monitoring | Manual audit | Automated: cert expiry + inspection history |

## Related Documents

- [Brick Ontology Layer](brick-ontology-layer.md) - Semantic building model
- [Drive Intake Pipeline](../05-integrations/drive-intake-pipeline.md) - Document ingestion from Google Drive
- [RAG Integration Overview](../08-ai-ml/rag-integration-overview.md) - Vector database and semantic search
- [ML Data Architecture](ML-DATA-ARCHITECTURE.md) - ML model registry and context bridge
- [Device Abstraction Layer](device-abstraction-layer.md) - SIMBIOT protocol normalization
