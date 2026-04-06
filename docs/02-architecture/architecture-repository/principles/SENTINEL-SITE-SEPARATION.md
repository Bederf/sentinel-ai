---
title: "SENTINEL and Site Separation Principle"
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

# SENTINEL and Site Separation Principle

## Core Design Principle

**SENTINEL and Sites are fundamentally separate entities, connected only through the BMS via SIMBIOT.**

### The Boundary Rule

```text
building -> BMS source -> SIMBIOT -> SENTINEL
```

This boundary must be maintained at all times. SENTINEL is an overlay, not an owner of building operations.

## Entity Definitions

### Site/Building
- Physical building with equipment, schedules, and operational state
- Owns its own BMS (Building Management System)
- Independent runtime entity
- May use real BMS or lifecycle simulation as its BMS source

### SIMBIOT
- Integration boundary layer
- Handles protocol connectivity, discovery, ingestion, and command transport
- Only connection point between buildings and SENTINEL
- Treats lifecycle simulation as just another BMS source

### SENTINEL
- AI/ML overlay system
- Provides analytics, storage, recommendations, and optional control
- Never owns building operation - only overlays it
- One SENTINEL instance per building in production
- May have read-only multi-site consoles, but operational control remains per-building

## Ownership Matrix

| Component | Owner | Responsibility |
|-----------|-------|----------------|
| Building equipment | Building | Physical systems, schedules, runtime state |
| BMS telemetry | BMS source | Telemetry and control surfaces exposed |
| Protocol connectivity | SIMBIOT | Discovery, ingestion, command transport |
| Data storage | SENTINEL | Historical data, analytics, ML models |
| Recommendations | SENTINEL | AI-generated insights and actions |
| Control decisions | SENTINEL (optional) | Approved control actions through SIMBIOT |

## Key Architectural Rules

1. **One SENTINEL instance per building** in production deployments
2. **SIMBIOT is the only connection** - no direct building-to-SENTINEL links
3. **Lifecycle simulation is a BMS source**, not part of SENTINEL
4. **site_processing = off means disconnected** - no reads, no ingest, no writes
5. **Module activation is SENTINEL-only** - unsupported building systems are ignored
6. **Multi-site consoles are read-only** - operational control remains per-building

## Operational States

### Disconnected
- Building exists but SENTINEL not attached
- `site_processing = off`
- No runtime operations

### Commissioning
- Connect through SIMBIOT
- Discover and map equipment
- Prepare for runtime operations
- No operational ML writes

### Shadow Live
- Live data ingest with no real writes
- Quality gates and baseline collection
- Recommendations generated internally only

### Live Control + Monitor
- Production-grade quality gates
- Recommendations shown to operators
- No direct BMS writes from SENTINEL

### Live Control + Human-in-Loop
- SENTINEL can suggest control actions
- Human approval required for each action
- Full audit and rollback capability

### Live Control + Auto-Execute
- Bounded autonomous control
- Only policy-allowed actions auto-execute
- Safety checks and COV verification mandatory
- Operator notifications continue

## Module Rollout

Modules expand what SENTINEL monitors and controls, but don't change the lifecycle stage:

- **No module active**: That subsystem is ignored even if BMS exposes it
- **Module activated**: Discovery, baselining, recommendations, then optional control
- **Incremental rollout**: Add subsystems (solar, water, security) independently

## ML Maturity Stages

1. **Early**: Conservative baseline models, focus on data quality
2. **Mid**: Site-specific models from building history
3. **Mature**: Closed-loop learning from approved/autonomous actions

**Rule**: Promotion depends on operational evidence, not just model availability

## Safe Operations

- **Demotion always allowed**: Bad data, safety issues, or client request can demote
- **Kill switches**: Site-level and equipment-level emergency stops
- **Rollback paths**: Mandatory for all control actions
- **Audit trails**: Complete history of all SENTINEL actions

## Visual architecture and flows

### System boundary diagram

```mermaid
graph TD
    subgraph Building1[Building Site 1]
        B1_BMS[BMS System]
    end

    subgraph Building2[Building Site 2]
        B2_BMS[BMS System]
    end

    subgraph SIMBIOT[SIMBIOT Integration Layer]
        SIM_Connect[Connectivity]
        SIM_Ingestion[Ingestion]
        SIM_Commands[Command Transport]
    end

    subgraph SENTINEL[SENTINEL AI Platform]
        SEN_Storage[Data Storage]
        SEN_Analytics[Analytics]
        SEN_Control[Optional Control]
    end

    subgraph Simulation[Lifecycle Simulation]
        SIM_BMS[Simulated BMS]
    end

    B1_BMS -->|Real telemetry| SIM_Connect
    B2_BMS -->|Real telemetry| SIM_Connect
    SIM_BMS -->|Simulated telemetry| SIM_Connect

    SIM_Ingestion -->|Normalized data| SEN_Storage
    SEN_Control -->|Control commands| SIM_Commands
    SIM_Commands -->|BMS writes| B1_BMS
    SIM_Commands -->|BMS writes| B2_BMS
```

### Boundary rule diagrams

```mermaid
graph LR
    Building1 --> SENTINEL1[SENTINEL Instance 1]
    Building2 --> SENTINEL2[SENTINEL Instance 2]
    Building3 --> SENTINEL3[SENTINEL Instance 3]
```

```mermaid
graph TD
    Building --> BMS
    BMS --> SIMBIOT
    SIMBIOT --> SENTINEL
    Building -.->|FORBIDDEN| SENTINEL
```

```mermaid
graph TD
    subgraph Simulation[Lifecycle Simulation]
        SIM_BMS[Simulated BMS Interface]
    end
    SIM_BMS --> SIMBIOT
    RealBMS[Real Building BMS] --> SIMBIOT
    SIMBIOT --> SENTINEL
```

```mermaid
graph TD
    SENTINEL1[Site 1 SENTINEL] --> Console
    SENTINEL2[Site 2 SENTINEL] --> Console
    SENTINEL3[Site 3 SENTINEL] --> Console
    Console -.->|READ-ONLY| SENTINEL1
    Console -.->|READ-ONLY| SENTINEL2
    Console -.->|READ-ONLY| SENTINEL3
```

### Operational sequences

```mermaid
sequenceDiagram
    participant Operator
    participant SIMBIOT
    participant BuildingBMS
    participant SENTINEL

    Operator->>SIMBIOT: Start commissioning session
    SIMBIOT->>BuildingBMS: Discover equipment
    BuildingBMS-->>SIMBIOT: Equipment list
    SIMBIOT->>Operator: Show mappings
    Operator->>SIMBIOT: Approve mappings
    SIMBIOT->>SENTINEL: Store approved mappings
    Note over SENTINEL: site_processing = off (no runtime)
```

```mermaid
sequenceDiagram
    participant BuildingBMS
    participant SIMBIOT
    participant SENTINEL
    participant Operator

    loop Every ingest cycle
        BuildingBMS->>SIMBIOT: Telemetry data
        SIMBIOT->>SENTINEL: Normalized data
        SENTINEL->>SENTINEL: Store and analyze
        SENTINEL->>Operator: Show recommendations
    end
    Note over SENTINEL: ingestion_mode = live_control
    Note over SENTINEL: control_tier = monitor
```

```mermaid
sequenceDiagram
    participant BuildingBMS
    participant SIMBIOT
    participant SENTINEL
    participant Operator

    BuildingBMS->>SIMBIOT: Telemetry data
    SIMBIOT->>SENTINEL: Normalized data
    SENTINEL->>SENTINEL: Detect anomaly
    SENTINEL->>Operator: Recommend control action
    Operator->>SENTINEL: Approve action
    SENTINEL->>SIMBIOT: Send control command
    SIMBIOT->>BuildingBMS: Execute command
    BuildingBMS-->>SIMBIOT: Confirmation
    SIMBIOT-->>SENTINEL: Verification data
    Note over SENTINEL: control_tier = human_in_loop
```

## Implementation Checklist

For new building onboarding:

1. [ ] Connect building through SIMBIOT
2. [ ] Complete discovery and equipment mapping
3. [ ] Start passive baseline collection (shadow_live)
4. [ ] Prove data quality and mapping accuracy
5. [ ] Move to recommendation-only production (live_control + monitor)
6. [ ] Add supervised controls when client ready (human_in_loop)
7. [ ] Add autonomous controls only with evidence (auto_execute)
8. [ ] Add subsystems (solar, water, etc.) as independent modules

## Related Documents

- [Architecture Principles](architecture-principles.md)
- [Building Operating Lifecycle](building-operating-lifecycle.md)
- [SIMBIOT Concept Connector](../../05-integrations/simbiot-concept-connector.md)
- [BMS Adapter Contract](../../05-integrations/bms-adapter-contract.md)
