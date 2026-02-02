# SENTINEL BMS Intelligence Platform

## Overview

SENTINEL is an AI-powered Building Management System (BMS) Intelligence Platform designed for facilities management in South Africa. It combines predictive maintenance, conversational AI, and automated device control to help facility managers proactively maintain buildings and reduce operational costs.

## Core Capabilities

### 1. Predictive Maintenance

SENTINEL uses machine learning to predict equipment failures before they occur:

- **LSTM Neural Networks**: Predict equipment health degradation 24, 48, and 72 hours into the future based on historical sensor patterns
- **Autoencoder Anomaly Detection**: Identifies unusual sensor readings that deviate from learned normal behavior
- **Health Scoring**: Every piece of equipment has a health score (0-100%) calculated from:
  - Current sensor telemetry (temperature, pressure, vibration, power)
  - Service history and time since last maintenance
  - Equipment age relative to expected lifespan
  - Recent alert patterns and frequency

**Health Thresholds:**
- 90-100%: Healthy (green)
- 70-89%: At-risk (yellow) - schedule preventive maintenance
- 50-69%: Warning (orange) - maintenance required soon
- Below 50%: Critical (red) - immediate attention needed

### 2. Hybrid AI Architecture

SENTINEL uses a cost-optimized AI routing system:

- **Tier 1 (Ollama - Local/Free)**: Simple queries, data lookups, status checks
- **Tier 2 (Claude - Cloud/Paid)**: Complex reasoning, control actions, diagnostics
- **Cost Savings**: ~40% reduction compared to using Claude for everything

The system automatically routes queries to the appropriate tier based on complexity patterns.

### 3. Device Control & Safety

Protocol-agnostic device control with built-in safety:

**Supported Protocols:**
- BACnet (HVAC systems)
- Modbus (generators, energy meters)
- DALI-2 (lighting via Tridonic Scenecom)
- REST APIs (modern IoT devices)

**Safety Interlocks:**
All control actions pass through the Safety Engine before execution:
- Temperature limits: 16-28°C for HVAC setpoints
- Pressure limits for chillers and pumps
- Runtime limits to prevent equipment damage
- Brightness limits for lighting (0-100%)
- Equipment interlocks (e.g., can't start chiller if pump is off)

Blocked actions are logged with the specific safety rule that prevented them.

### 4. Alert Workflow

When equipment health degrades:

1. **Detection**: Health drops below threshold (e.g., 90%)
2. **Alert Created**: Stored in database with severity, equipment details
3. **Telegram Notification**: Sent via Clawd bot to facility managers
4. **Work Order**: FM can click `/WO_<code>` to create a Concept Evolution-compatible job card
5. **Resolution**: Technician completes work, uploads service data for ML training

### 5. RAG Knowledge Base

Natural language search across equipment documentation:

- Uses pgvector with 384-dimensional MiniLM embeddings
- Indexes equipment manuals, fault code databases, maintenance procedures
- Retrieves relevant context when users ask about specific equipment or fault codes

### 6. Modular Architecture

SENTINEL uses a bolt-on module system:

**Available Modules:**
- **HVAC**: Chillers, AHUs, FCUs, VAVs - temperature control and optimization
- **Energy**: Generators, UPS, transformers, meters - power monitoring and load shedding
- **Lighting**: DALI-2 integration for scene control and occupancy-based lighting
- **Security**: Access control integration (future)

Modules can be enabled/disabled per building. When multiple modules are active, cross-module automations become available (e.g., occupancy sensors trigger both lighting and HVAC adjustments).

## Data Sources

### Primary: Supabase (PostgreSQL)
- Equipment registry with health scores
- Alerts and predictions
- Service records and maintenance history
- Building configuration

### Time-Series: InfluxDB
- Sensor telemetry (temperature, pressure, humidity, power)
- High-frequency data for ML model training
- Historical trend analysis

### Fallback: JSON Files
- Offline operation capability
- Demo mode data
- Configuration backup

## Integration Points

### Clawd Telegram Bot
- Receives BMS alerts with equipment details
- `/WO_<code>` creates work orders
- `/note_<code>` logs acknowledgments
- Natural language queries about building status

### Concept Evolution CAFM
- Work orders exported in Concept-compatible format
- Job card numbers follow Concept conventions
- Priority codes (P1-P4) match Concept SLA system

### MCP (Model Context Protocol)
- 21 tools exposed for AI assistants
- Dual transport: stdio for Claude Desktop, SSE for cloud
- Enables external AI systems to query and control SENTINEL

## South African Context

SENTINEL is designed for South African facilities:

- **Load Shedding**: Zone-based priority system (P1-P5) for generator management
- **Standards**: SANS, OHS Act, SABS compliance references
- **Currency**: All costs in ZAR
- **Terminology**: Uses local FM terminology

## Key Metrics

- **Equipment Coverage**: Typically 100-200 assets per building
- **Prediction Accuracy**: 85%+ for 24-hour failure predictions
- **Alert Response**: Telegram notifications within 10 seconds
- **Cost Savings**: 30-50% reduction in reactive maintenance costs
