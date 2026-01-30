---
title: "SENTINEL Glossary"
type: "reference"
status: "approved"
version: "1.0.0"
created: "2026-01-30"
updated: "2026-01-30"
author: "Sentinel Development Team"
tags: ["glossary", "terminology", "definitions", "bms", "hvac"]
related: ["../02-architecture/system-overview.md", "../05-bms-concepts/"]
domain: "general"
audience: "all"
complexity: "beginner"
estimated_read_time: 10
---

# SENTINEL Glossary

This glossary defines key terms used throughout SENTINEL documentation and the building management industry.

## A

### AHU (Air Handling Unit)
A large HVAC component that conditions and circulates air through ductwork. Contains fans, filters, heating/cooling coils, and dampers.

### Alarm
A notification indicating an abnormal condition requiring attention. SENTINEL categorizes alarms by priority: Critical, High, Medium, Low.

### Audit Log
Immutable record of all control actions, safety validations, and system events. Used for compliance and incident investigation.

### Autonomous Mode
SENTINEL operating mode where AI can execute approved optimization actions without explicit operator approval for each action.

## B

### BACnet (Building Automation and Control Network)
Standard communication protocol for building automation. SENTINEL supports BACnet IP for device communication.

### BMS (Building Management System)
System that monitors and controls a building's mechanical and electrical equipment. SENTINEL is an AI-enhanced BMS platform.

### Boundary
Safety limit values that define acceptable operating ranges. Approaching a boundary triggers warnings; crossing it triggers blocks.

## C

### CAFM (Computer-Aided Facility Management)
Software for managing facilities operations including maintenance, space planning, and asset tracking. SENTINEL integrates with CAFM systems.

### CHW (Chilled Water)
Cold water circulated through HVAC systems to provide cooling. Typical supply temperature: 5-12°C.

### Chiller
Equipment that produces chilled water by removing heat through a refrigeration cycle. Critical HVAC component.

### Claude
Anthropic's AI assistant used by SENTINEL for complex reasoning, optimization recommendations, and natural language interaction.

### Comfort Limit
Maximum acceptable temperature for occupant comfort. Typical value: 26°C for commercial spaces.

### Control Point
A readable/writable parameter on a device. Examples: temperature setpoint, fan speed, valve position.

## D

### Damper
Adjustable plate or valve that controls airflow in ductwork. Can be motorized for automatic control.

### Device Abstraction Layer
SENTINEL architecture component that provides protocol-agnostic device control. Supports BACnet, Modbus, and mock devices.

### Device Manager
Singleton service that handles device discovery, communication, and lifecycle management.

## E

### Eskom
South African electricity public utility. Implements load shedding during supply shortages.

### Escalation
Process of elevating an issue to higher attention levels based on severity or duration. SENTINEL has 5 escalation levels.

## F

### FCU (Fan Coil Unit)
Compact HVAC unit containing a fan and heating/cooling coil. Used for zone-level temperature control.

### Fault Code
Standardized error identifier from equipment manufacturers. SENTINEL includes a fault code database for diagnosis.

## H

### HVAC (Heating, Ventilation, and Air Conditioning)
Building systems that provide thermal comfort and air quality. Primary focus of SENTINEL control capabilities.

### Hybrid AI
SENTINEL's two-tier AI architecture using local Ollama (free) for simple queries and cloud Claude (paid) for complex reasoning.

## I

### Interlock
Safety mechanism that prevents certain operations based on system state. Example: Fire alarm → HVAC shutdown.

### Integration
Process of connecting external data sources (BMS logs, CAFM systems) to SENTINEL for unified monitoring.

## L

### Load Shedding
Controlled power outages to prevent grid collapse. Common in South Africa; SENTINEL optimizes HVAC for load shedding events.

### Loop
Control algorithm that adjusts outputs to maintain a setpoint. Common types: PID (Proportional-Integral-Derivative).

## M

### MCP (Model Context Protocol)
Protocol for AI agents to interact with external tools and data. SENTINEL's SIMBIOT MCP server provides 12 building management tools.

### Modbus
Serial communication protocol for industrial devices. SENTINEL supports Modbus TCP and Modbus RTU.

## O

### Ollama
Local LLM runtime used by SENTINEL for cost-efficient AI queries. Handles simple lookups and data retrieval.

### Optimization
Process of adjusting building systems to improve efficiency, comfort, or cost. SENTINEL provides AI-driven optimization recommendations.

## P

### Point
Individual data element on a device. Can be read-only (sensor value) or read-write (setpoint).

### Pre-cooling
Strategy of lowering building temperature before a scheduled outage to extend thermal comfort during the outage.

### Prediction
AI-generated forecast of equipment failure or performance degradation. SENTINEL provides predictive maintenance alerts.

## R

### Rule
Safety constraint that validates control actions. Types: temperature_range, pressure_limit, interlock, runtime_limit, brightness_limit, custom.

### Runtime Limit
Safety rule preventing equipment cycling. Example: Chiller must run 5 minutes minimum before restart.

## S

### Safety Engine
SENTINEL component that validates all control actions against configurable safety rules.

### Setpoint
Target value for a control loop. Example: Cooling setpoint of 22°C means the system targets 22°C.

### Severity
Classification of rule violations. Levels: WARNING (allow with notice), BLOCK (prevent), ALARM (critical alert).

### SIMBIOT
SENTINEL's MCP server providing 12 building management tools for AI integration.

### Site
Building or facility managed by SENTINEL. Each site has unique characteristics and device configurations.

### SSE (Server-Sent Events)
Protocol for streaming data from server to client. Used by SENTINEL for AI chat responses and MCP communication.

### Supabase
PostgreSQL-based backend platform. SENTINEL uses Supabase for production data storage with JSON fallback for demos.

## T

### Telemetry
Real-time data from building sensors and equipment. Includes temperature, pressure, flow rates, energy consumption.

### Thermal Mass
Building's ability to absorb and store heat. Higher thermal mass means slower temperature changes.

### Thermal Runway
Time until building temperature exceeds comfort limit during a cooling outage. Key metric for load shedding planning.

### Trend
Historical record of a point's values over time. Used for analysis, reporting, and AI training.

## V

### VAV (Variable Air Volume)
HVAC system that adjusts airflow to maintain temperature. VAV boxes modulate dampers based on zone demand.

### Validation
Process of checking a proposed action against safety rules before execution.

### Vision Analysis
SENTINEL feature using Claude Vision API to analyze equipment photos for diagnosis and identification.

## W

### Work Order
Maintenance task created for equipment repair or service. SENTINEL can create work orders via MCP tools.

## Z

### Zone
Controlled area within a building with its own temperature control. Typically served by a VAV box or FCU.

### Zone Controller
Device that manages temperature and airflow for a specific zone. Communicates setpoints to HVAC equipment.

---

## Acronyms quick reference

| Acronym | Full Form |
|---------|-----------|
| AHU | Air Handling Unit |
| BACnet | Building Automation and Control Network |
| BMS | Building Management System |
| CAFM | Computer-Aided Facility Management |
| CHW | Chilled Water |
| FCU | Fan Coil Unit |
| HVAC | Heating, Ventilation, and Air Conditioning |
| MCP | Model Context Protocol |
| PID | Proportional-Integral-Derivative |
| SSE | Server-Sent Events |
| VAV | Variable Air Volume |

---

## See also

- [System Overview](../02-architecture/system-overview.md) - Architecture context
- [Device Abstraction Layer](../02-architecture/device-abstraction-layer.md) - Device concepts
- [Safety Interlocks Engine](../06-safety-compliance/safety-interlocks-engine.md) - Safety terminology
