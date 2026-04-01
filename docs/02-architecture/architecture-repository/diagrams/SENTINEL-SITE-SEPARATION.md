# SENTINEL-Site Separation Diagram

## Visual Representation

```mermaid
graph TD
    subgraph Building1[Building Site 1]
        B1_Equipment[Equipment]
        B1_Schedules[Schedules]
        B1_BMS[BMS System]
    end

    subgraph Building2[Building Site 2]
        B2_Equipment[Equipment]
        B2_Schedules[Schedules]
        B2_BMS[BMS System]
    end

    subgraph SIMBIOT[SIMBIOT Integration Layer]
        SIM_Connect[Connectivity]
        SIM_Discovery[Discovery]
        SIM_Ingestion[Ingestion]
        SIM_Commands[Command Transport]
    end

    subgraph SENTINEL[SENTINEL AI Platform]
        SEN_Storage[Data Storage]
        SEN_ML[ML Models]
        SEN_Analytics[Analytics]
        SEN_Recommendations[Recommendations]
        SEN_Control[Optional Control]
    end

    subgraph Simulation[Lifecycle Simulation]
        SIM_BMS[Simulated BMS]
        SIM_Equipment[Simulated Equipment]
    end

    %% Building connections
    B1_BMS -->|Real telemetry| SIM_Connect
    B2_BMS -->|Real telemetry| SIM_Connect
    SIM_BMS -->|Simulated telemetry| SIM_Connect

    %% SIMBIOT to SENTINEL
    SIM_Ingestion -->|Normalized data| SEN_Storage
    SEN_Control -->|Control commands| SIM_Commands
    SIM_Commands -->|BMS writes| B1_BMS
    SIM_Commands -->|BMS writes| B2_BMS

    %% Ownership boundaries
    style Building1 fill:#f9f,stroke:#333
    style Building2 fill:#f9f,stroke:#333
    style SIMBIOT fill:#9f9,stroke:#333
    style SENTINEL fill:#99f,stroke:#333
    style Simulation fill:#ff9,stroke:#333

    %% Legends
    classDef building fill:#f9f,stroke:#333;
    classDef integration fill:#9f9,stroke:#333;
    classDef sentinel fill:#99f,stroke:#333;
    classDef simulation fill:#ff9,stroke:#333;

    class Building1,Building2 building
    class SIMBIOT integration
    class SENTINEL sentinel
    class Simulation simulation
```

## Key Boundary Rules

### 1. One SENTINEL Instance Per Building

```mermaid
graph LR
    Building1 --> SENTINEL1[SENTINEL Instance 1]
    Building2 --> SENTINEL2[SENTINEL Instance 2]
    Building3 --> SENTINEL3[SENTINEL Instance 3]
```

### 2. SIMBIOT is the Only Connection

```mermaid
graph TD
    Building --> BMS
    BMS --> SIMBIOT
    SIMBIOT --> SENTINEL

    Building -.->|FORBIDDEN| SENTINEL
    style FORBIDDEN stroke:#f00,stroke-width:4px,stroke-dasharray: 5 5
```

### 3. Lifecycle Simulation is a BMS Source

```mermaid
graph TD
    subgraph Simulation[Lifecycle Simulation]
        SIM_BMS[Simulated BMS Interface]
        SIM_Equipment[Simulated Equipment]
    end

    SIM_BMS --> SIMBIOT
    RealBMS[Real Building BMS] --> SIMBIOT

    SIMBIOT --> SENTINEL
```

### 4. Multi-Site Console is Read-Only

```mermaid
graph TD
    SENTINEL1[Site 1 SENTINEL] --> Console
    SENTINEL2[Site 2 SENTINEL] --> Console
    SENTINEL3[Site 3 SENTINEL] --> Console

    Console -.->|READ-ONLY| SENTINEL1
    Console -.->|READ-ONLY| SENTINEL2
    Console -.->|READ-ONLY| SENTINEL3

    style READ-ONLY stroke:#f00,stroke-width:2px
```

## Operational Flow Examples

### Commissioning Flow

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

### Production Monitoring Flow

```mermaid
sequenceDiagram
    participant BuildingBMS
    participant SIMBIOT
    participant SENTINEL
    participant Operator

    loop Every ingest cycle
        BuildingBMS->>SIMBIOT: Telemetry data
        SIMBIOT->>SENTINEL: Normalized data
        SENTINEL->>SENTINEL: Store & analyze
        SENTINEL->>Operator: Show recommendations
    end
    Note over SENTINEL: site_processing = on
    Note over SENTINEL: ingestion_mode = live_control
    Note over SENTINEL: control_tier = monitor
```

### Supervised Control Flow

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

## Data Flow Boundaries

### What Crosses SIMBIOT Boundary

✅ **Allowed:**
- Telemetry readings (temperature, pressure, status, etc.)
- Equipment metadata (names, types, locations)
- Control commands (setpoints, mode changes)
- Command verification responses

❌ **Forbidden:**
- Direct database access
- Raw building network access
- Bypassing quality gates
- Unapproved control actions

### What Stays in SENTINEL

🔒 **SENTINEL-only:**
- Historical data storage
- ML model training
- Recommendation generation
- Audit logs
- User preferences
- Module configurations

### What Stays in Building

🏢 **Building-only:**
- Physical equipment state
- Local schedules
- Emergency overrides
- Building network infrastructure
- Local operator interfaces

## Related Documents

- [SENTINEL-Site Separation Principle](../principles/SENTINEL-SITE-SEPARATION.md)
- [Architecture Principles](../principles/architecture-principles.md)
- [Building Operating Lifecycle](../principles/building-operating-lifecycle.md)
