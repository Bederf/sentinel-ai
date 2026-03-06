---
title: "Brick Ontology Layer"
type: "architecture"
status: "implemented"
version: "1.0.0"
created: "2026-03-05"
updated: "2026-03-05"
author: "SENTINEL Development Team"
tags: ["brick", "ontology", "asset-graph", "semantic-model", "digital-twin"]
related: ["device-abstraction-layer.md", "system-overview.md", "hybrid-knowledge-layer.md"]
domain: "bms"
audience: "developers"
complexity: "advanced"
estimated_read_time: 20
---

# Brick Ontology Layer

Semantic building model that formalizes equipment, points, locations, and relationships into a traversable graph.

## Overview

SENTINEL's device abstraction layer (SIMBIOT) normalizes BMS protocols into a consistent point/device view. The Brick ontology layer adds a **semantic graph** on top of SIMBIOT, enabling deterministic traversal from sensor points to equipment, locations, vendors, contracts, and documents.

**Why Brick?** Brick Schema is an open-source building ontology that provides:
- Standard vocabulary for equipment, locations, and points
- Defined relationships (`hasPoint`, `hasLocation`, `hasPart`, `feeds`)
- External reference patterns linking points to BACnet/Modbus identifiers
- SHACL validation for model correctness

## Architecture

```
BMS (Desigo / Niagara / Honeywell / etc.)
       |
       v
SIMBIOT Device Abstraction Layer
(protocol normalization)
       |
       v
Brick Ontology Layer          <-- NEW
(semantic graph + relationships)
       |
       v
Hybrid Knowledge Layer
(context assembly for AI agents)
```

**Key principle:** Brick sits above SIMBIOT, never beside it. New BMS types only need a SIMBIOT adapter. The Brick layer works identically regardless of source vendor.

## Entity Types

### Equipment (from `equipment` table)

Maps `equipment.type` to Brick classes:

| SENTINEL Type | Brick Class | Example Code |
|--------------|-------------|-------------|
| chiller | `brick:Chiller` | S002-CHILLER-B1-001 |
| ahu | `brick:AHU` | S002-AHU-B1-001 |
| vav | `brick:VAV` | S002-VAV-L1-A |
| fcu | `brick:Fan_Coil_Unit` | S002-FCU-L1-A |
| pump | `brick:Pump` | S002-PUMP-B1-001 |
| generator | `brick:Generator` | S002-GEN-B1-001 |
| ups | `brick:UPS` | S002-UPS-B1-001 |
| ct / cooling_tower | `brick:Cooling_Tower` | S002-CT-B1-001 |
| dali / dali_controller | `brick:Lighting_Equipment` | S002-DALI-B1-CTRL |
| meter | `brick:Electrical_Meter` | S002-MTR-B1-001 |

### Points (from equipment JSON `points` dict)

Each point in the equipment JSON maps to a Brick Point subclass:

```turtle
sentinel:pt/S002-CHILLER-B1-001/chilled_water_temperature
    a brick:Supply_Chilled_Water_Temperature_Sensor ;
    brick:isPointOf sentinel:eq/S002-CHILLER-B1-001 ;
    ref:hasExternalReference [
        a ref:BACnetReference ;
        bacnet:object-identifier "analogInput,1000" ;
        bacnet:object-name "CH-1.ChwSupplyTemp"
    ] .
```

**Data sources for points:**
- **Equipment JSON** (`data/buildings/{site}/equipment/*.json`): Authoritative source for BACnet refs, instances, writable flags
- **Discovery mapping** (`data/niagara/mappings/mapping_*.json`): Classification enrichment (`point_category`, `confidence`, `brick_class`)

### Locations (from `device_location` JSONB + discovery `metadata.zone`)

Flat JSONB converted to traversable hierarchy:

```turtle
sentinel:loc/site-002 a brick:Site .
sentinel:loc/site-002/B1 a brick:Floor ;
    brick:isPartOf sentinel:loc/site-002 .
sentinel:loc/site-002/B1/Zone-B1-001 a brick:HVAC_Zone ;
    brick:isPartOf sentinel:loc/site-002/B1 .
```

### Relationships (new entities needed)

| Relationship | From | To | Source |
|-------------|------|-----|--------|
| `brick:hasPoint` | Equipment | Point | equipment JSON `points` dict |
| `brick:hasLocation` | Equipment | Location | discovery `metadata.zone` |
| `brick:hasPart` | Location | Location | hierarchy parsing |
| `sentinel:maintainedBy` | Equipment | Vendor | `service_provider_name` |
| `sentinel:coveredBy` | Equipment | Contract | new contract table |
| `sentinel:relatesTo` | Document | Equipment | RAG metadata |

## IRI Minting Rules

Stable, deterministic IRIs that survive re-runs:

| Entity | IRI Pattern | Example |
|--------|------------|---------|
| Equipment | `sentinel:eq/{equipment.code}` | `sentinel:eq/S002-CHILLER-B1-001` |
| Point | `sentinel:pt/{equipment.code}/{point_key}` | `sentinel:pt/S002-CHILLER-B1-001/chilled_water_temperature` |
| Location | `sentinel:loc/{site_id}/{floor}/{zone}` | `sentinel:loc/site-002/B1/Zone-B1-001` |

## Auto-Generation Pipeline

### Service: `backend/app/services/brick_autogen_service.py`

**Status:** Implemented. 28 tests passing (`tests/services/test_brick_autogen.py`).

Two jobs:
1. **Build/update Brick graph** from equipment + discovery data
2. **Publish Resolution Index** for fast runtime lookups

### Data Flow

```
equipment JSON files (authoritative points + BACnet refs)
       +
discovery mappings (classification: point_category, brick_class, confidence)
       |
       v
brick_autogen_service.py
       |
       +-- Location hierarchy (from metadata.zone)
       +-- Equipment nodes (from equipment.type -> Brick class)
       +-- Point nodes (from equipment JSON points dict)
       +-- BACnet external refs (from bacnet_ref + object_type + instance)
       +-- Classification enrichment (from discovery brick_class)
       |
       v
Brick Graph (TTL) + Resolution Index
```

### Point Classification Confidence Thresholds

| Confidence | Action |
|-----------|--------|
| >= 0.75 (HIGH) | Use classifier's `brick_class` directly |
| >= 0.45 (LOW) | Use classifier's `brick_class`, tag as low-confidence |
| < 0.45 | Fall back to `point_category` + `unit` heuristics |

### Fallback Heuristics (when classifier unavailable)

| Name/Unit Pattern | Brick Class |
|------------------|-------------|
| temp, degC, C | `brick:Temperature_Sensor` |
| pressure, kPa, psi | `brick:Pressure_Sensor` |
| flow, l/s, m3/h | `brick:Flow_Sensor` |
| speed, Hz, rpm | `brick:Speed_Sensor` |
| cmd, command | `brick:Command` |
| status | `brick:Status` |
| default | `brick:Point` |

### Incremental Updates

- SHA256 hash per `equipment.code` of (equipment row + device points + discovery mapping)
- Only regenerate subgraph if hash changed since last run
- No full rebuilds

### Validation

- SHACL validation via `brickschema` Python library on every build
- Fail build if core Brick constraints break
- Partial publish OK per `site_id` boundary

## Resolution Index

Fast runtime lookup table published after each graph build:

| From | To | Use Case |
|------|-----|----------|
| `simbiot_point_key` | `brick_point_iri` | Telemetry event -> graph entry |
| `bacnet_object_type,instance` | `brick_point_iri` | BACnet alarm -> graph entry |
| `brick_point_iri` | `brick_equipment_iri` | Point -> which equipment |
| `brick_equipment_iri` | `asset_code` | Graph -> Supabase join |
| `asset_code` | `brick_location_iri` | Equipment -> where |

## BMS-Agnostic Design

The Brick layer never touches vendor-specific APIs. It reads from SIMBIOT's normalized tables only.

| BMS Vendor | SIMBIOT Adapter | Brick Impact |
|-----------|----------------|-------------|
| Siemens Desigo | CSV import + BACnet | None |
| Tridium Niagara | Niagara REST + BACnet | None |
| Honeywell | BACnet/Modbus | None |
| Johnson Controls | BACnet | None |

Adding a new BMS type requires only a SIMBIOT adapter. The Brick layer auto-generates from the normalized data.

## Graph Store

**Recommended:** Neo4j (simplest traversal queries, Cypher language)
**Alternative:** Postgres + Apache AGE extension (keeps everything in existing Postgres)
**For validation/export:** RDFLib + brickschema Python library

## Implementation Details

### Key Data Finding

Discovery mappings and equipment JSON use **different** point names and BACnet instances:
- Discovery: `original_name`=`CH-2_CHW_Supply_Temp`, instance=`0` (placeholder)
- Equipment JSON: key=`chilled_water_temperature`, `bacnet_ref`=`CH-1.ChwSupplyTemp`, instance=`1000` (real)

The service uses equipment JSON as authoritative and discovery for enrichment only. Join is by `equipment_id` (shared key), with point matching by `point_category` within the same equipment.

### Test Coverage

28 tests in `backend/tests/services/test_brick_autogen.py`:
- Helper functions (IRI sanitization, deterministic hashing)
- Discovery mapping loader (real site-002 data, 400+ mapping files filtered)
- Graph build (equipment/point/location creation, BACnet refs)
- Delta detection (skip unchanged equipment on re-build)
- Point classification (sensors, setpoints, commands, pressure, fallbacks)
- TTL serialization and resolution index JSON export
- Equipment type mapping coverage

### Usage

```python
from app.services.brick_autogen_service import build_brick_for_site
from pathlib import Path

idx, result = build_brick_for_site(
    Path("/opt/bms-intelligence/backend"),
    "site-002",
    validate=False,
    output_dir=Path("/tmp/brick"),
)
# Produces: site-002_brick.ttl + site-002_resolution_index.json
```

## Dependencies

- `rdflib` (required) - RDF graph manipulation and TTL serialization
- `brickschema` (optional) - SHACL validation, Brick ontology loading. Service degrades gracefully without it.
- Graph store (Neo4j or Postgres+AGE) for runtime queries (future)

## Related Documents

- [Device Abstraction Layer](device-abstraction-layer.md) - SIMBIOT protocol normalization
- [Hybrid Knowledge Layer](hybrid-knowledge-layer.md) - Context assembly using Brick + RAG + telemetry
- [Drive Intake Pipeline](../05-integrations/drive-intake-pipeline.md) - Document ingestion from Google Drive
- [RAG Integration Overview](../08-ai-ml/rag-integration-overview.md) - Vector database and semantic search
- [ML Data Architecture](ML-DATA-ARCHITECTURE.md) - ML model registry and feature engineering
