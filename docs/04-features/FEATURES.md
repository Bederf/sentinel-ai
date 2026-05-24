---
title: "SENTINEL BMS Intelligence Platform - Complete Feature Reference"
type: "feature"
status: "implemented"
version: "13.0"
created: "2026-02-03"
updated: "2026-02-03"
author: "SENTINEL Development Team"
tags: ["features", "platform", "bms", "ai", "predictive", "control"]
domain: "platform"
audience: "developers", "operators"
complexity: "overview"
estimated_read_time: 15
phase: "55"
---

# SENTINEL BMS Intelligence Platform - Complete Feature Reference

**Version:** 13.0 (Phase 55+)
**Updated:** 2026-02-03
**Status:** Production-ready with ongoing enhancements

## Platform Overview

SENTINEL is an AI-powered Building Management System (BMS) Intelligence Platform for facilities management. It combines predictive maintenance, conversational AI, device control, and South African load shedding optimization into a modular, bolt-on platform that integrates with existing BMS/SCADA systems.

**Key Differentiators:**
- AI-assisted onboarding from any BMS vendor (Desigo, Metasys, EBI, Niagara, Trend)
- Hybrid AI routing (free Ollama for simple queries, Claude for complex reasoning)
- Safety-first device control with interlock validation
- Desk-level comfort diagnosis combining HVAC + DALI lighting
- Mobile phone sensor integration (audio, vibration) for predictive maintenance
- Edge-to-head-office architecture: raw data stays on-prem, only optimization snapshots go to central
- South African load shedding optimization with Eskom schedule integration
- Complete asset lifecycle: onboard, baseline, inspect, repair, validate
- SIMBIOT MCP Server with 23 tools for building management

## 1. AI Chat System

### Documentation RAG Mode (Default)
- Searches indexed documentation using hybrid search (keyword + semantic matching)
- 384-dimensional MiniLM embeddings stored in Supabase pgvector
- Streams responses via Server-Sent Events (SSE)
- Cites documentation sources in responses
- Honest about unimplemented features - says "future development" for anything not built yet
- Logs all queries for feature request tracking

### System Control Mode
- Claude AI with 11 tool functions for building management
- Device control via natural language ("turn off AHU on level 2")
- All control actions validated through safety interlocks before execution
- Work order creation from conversational requests
- Equipment health queries, alert monitoring, energy data

### Chat Tools (11 tools)
1. **get_equipment_health** - Building-wide sensor readings and health summary
2. **get_site_equipment** - Equipment list for a site
3. **get_equipment_detail** - Specific equipment details with sensor data
4. **get_active_alerts** - Active alerts with severity levels
5. **create_work_order** - Create maintenance work order from conversation
6. **control_device** - Control device via device abstraction layer (safety validated)
7. **get_energy_data** - Energy consumption by category
8. **get_predictions** - ML failure predictions for equipment
9. **lookup_desk** - Desk to zone to HVAC to DALI sensor mapping
10. **diagnose_comfort_complaint** - Full comfort diagnosis with root cause analysis
11. **get_optimization_recommendations** - AI-generated HVAC and lighting recommendations

### Voice Chat (Phase 110 / Path C-Surgical)
- **Speech-to-Text input:** Browser-native Web Speech API (Chrome, Edge, Safari) for simple single-utterance mode; continuous capture via MediaRecorder + Silero-VAD for system docs mode
- Default language: en-ZA (South African English), single utterance per mic press
- Mic button auto-hidden on unsupported browsers (graceful degradation)
- **Text-to-Speech output:** ElevenLabs API (Rachel voice, `21m00Tcm4TlvDq8ikWAM`) for summarized audio playback — MP3 audio cached in Redis (SHA256 content hash, 1hr TTL)
- Claude summarizes AI response to 1-2 spoken sentences; full text still displayed
- Speaker button on each assistant message: Listen / Loading... / Playing...
- Requires `ELEVENLABS_API_KEY` + `ELEVENLABS_TTS_ENABLED=true` in `.env`
- **OpenAI Realtime-2 path (Path C-Surgical, 2026-05):** Replaces STT/VAD with OpenAI Realtime-2 WebSocket while keeping ElevenLabs TTS and Claude Sonnet. Enable via `VITE_REALTIME_VOICE_ENABLED=true` + `OPENAI_REALTIME_API_KEY` + `realtime_voice_enabled=true`
- See: [`docs/03-api-reference/chat-api.md`](docs/03-api-reference/chat-api.md)

### Hybrid AI Routing
- Tier 1 (Ollama - FREE): Simple lookups, data queries, status checks
- Tier 2 (Claude - PAID): Complex reasoning, device control, multi-step analysis
- Automatic routing based on query complexity
- 40% cost savings vs all-Claude approach
- Fallback to Claude on Ollama failures
- Safety-critical queries always route to Claude

## 2. Device Control & Safety

### Device Abstraction Layer
- Protocol-agnostic interface supporting BACnet/IP, Modbus TCP, DALI-2, OPC-UA, KNX
- Singleton device manager for lifecycle management
- Mock device support for development and demos
- Point read/write operations with type validation
- Device state tracking and history

### Safety Interlocks Engine
- All control actions validated before execution - no exceptions
- Rule types: TemperatureRange, PressureLimit, Interlock, RuntimeLimit, BrightnessLimit
- Severity levels:
  - **WARNING** - Allow action but log concern
  - **BLOCK** - Prevent action, return reason to user
  - **ALARM** - Critical safety violation, alert generated immediately
- Temperature range enforcement: 16-28°C
- Interlock dependencies (e.g., chiller requires cooling tower running)
- Configurable rules in safety_rules.json per equipment type

### Audit Trail
- Every control action logged with timestamp, user, device, action, result
- Safety validation results recorded for every attempt
- JSON audit log + Supabase storage (dual-write)
- Immutable audit entries for compliance
- Query by device, user, action type, time range
- Statistics: actions per day, success rates, blocked attempts

## 3. Equipment Health & Predictive Maintenance

### Health Scoring System
- Real-time equipment health scores (0-100%)
- Weighted multi-metric scoring per equipment type
- Configurable thresholds: normal, warning, critical ranges
- Health score weights customizable per building
- Health score history and trending
- Fleet-level health dashboards
- Automatic alert generation when scores drop

### ML Predictions (LSTM)
- Time-series failure prediction using LSTM neural networks
- 24h, 48h, 72h prediction horizons
- Confidence scoring for each prediction
- Equipment-specific models trained on historical data
- Explainable AI: natural language explanations of predictions via Ollama
- Contributing factor analysis (which sensor drove the prediction)

### Anomaly Detection (Autoencoder)
- Unsupervised anomaly detection using autoencoder neural networks
- Reconstruction error thresholds for anomaly classification
- Real-time monitoring of equipment behavior
- Automatic alert generation for detected anomalies
- No labeled training data required

### Equipment Survival Analysis
- Kaplan-Meier survival curves for equipment lifetime estimation
- Remaining useful life (RUL) predictions
- Maintenance scheduling optimization based on survival probability
- Fleet-level failure pattern analysis

### Equipment Classification
- ML-powered equipment type classification from BMS point names
- Automatic categorization: chillers, AHUs, FCUs, VAVs, pumps, cooling towers, boilers, meters, generators

## 4. Asset Lifecycle Management

### Asset Baseline Assessment
- Capture equipment performance baselines during commissioning or healthy operation
- Multi-metric baseline profiles per equipment type
- Automated baseline capture from sensor data
- Baseline comparison with current performance showing deviations
- Deviation detection and alerting when performance degrades
- Cost modeling: repair cost vs replacement cost vs failure cost analysis
- API endpoints for capture, compare, and report generation

### Routine Inspection & Maintenance
- Digital inspection checklists by equipment type (chiller, AHU, FCU, generator, etc.)
- Mobile-friendly field inspection forms
- Photo capture and OCR for nameplate reading
- Inspection scheduling with configurable frequency
- Deficiency tracking and prioritization (critical, high, medium, low)
- Inspection report generation with findings and recommendations
- API endpoints for checklist management, submission, and reporting

### Repair Effectiveness & ML Feedback Loop
- Pre-repair and post-repair performance comparison
- Repair effectiveness scoring (did the repair actually fix the problem?)
- ML model retraining after successful repairs
- Feedback loop: repair data improves future predictions
- Contractor performance tracking

### Workflow Orchestration
- Automated asset lifecycle workflow: onboard → baseline → inspect → repair → validate
- Trigger types:
  - ML_ANOMALY: ML model detects anomaly
  - BASELINE_DEVIATION: Performance deviates from baseline
  - CRITICAL_DEFICIENCY: Inspection finds critical issue
  - REPAIR_COMPLETED: Repair work finished, needs validation
  - REPAIR_VALIDATION: Validate repair was effective
- State machine tracking for each equipment's lifecycle
- Workflow status tracking and reporting

## 5. Energy & Optimization

### AI Optimizer (Multi-System)
- Coordinated HVAC + DALI lighting optimization
- Occupancy-based control: reduce cooling/lighting when zones are empty
- Weather-aware setpoint optimization
- Energy price-aware scheduling (time-of-use tariffs)
- Rule-based fallback when Claude API unavailable
- Cross-system recommendations (e.g., dim lights + reduce cooling when empty)

### Load Shedding Optimization (South Africa)
- Eskom load shedding schedule integration
- Thermal runway planning: pre-cool building before scheduled outage
- Generator priority management during load shedding
- Zone priority classification: P1 (critical like server rooms) to P5 (lowest like parking)
- Automatic load reduction during grid constraints
- UPS and generator coordination
- Comfort extension: +108% during outages
- Cost savings: R2,100 per 4-hour outage

### Energy Monitoring
- Real-time energy consumption by category (HVAC, lighting, power)
- Power meter integration (Modbus TCP)
- Energy cost calculation with time-of-use tariffs
- Historical energy trending and comparison
- Carbon footprint estimation

### Energy Centre Integration
- Generator management: status, fuel levels, runtime, auto-start scheduling
- Automatic Transfer Switch (ATS) monitoring
- UPS monitoring: battery health, load percentage, runtime estimation
- Transformer monitoring: temperature, load, oil analysis
- Power quality metrics: voltage, frequency, power factor

## 6. HVAC Management

### Zone Control
- HVAC zone management with equipment mappings (zone → FCU → VAV → AHU)
- Temperature setpoint control per zone (safety validated: 16-28°C)
- Zone occupancy tracking via DALI PIR sensors
- Supply air, return air, and chilled water monitoring
- VAV damper position control
- FCU fan speed control

### Chiller Plant
- Chiller staging and sequencing
- Chilled water supply/return temperature monitoring
- Compressor status and fault monitoring
- Energy efficiency tracking (kW/ton)
- Lead/lag chiller management

### Air Handling
- AHU supply air temperature control
- Filter pressure differential monitoring for replacement scheduling
- Fan status and speed control
- Fresh air damper management
- Economizer control for free cooling

## 7. DALI Lighting Integration

### Tridonic Scenecom DALI-2
- Individual luminaire control and dimming (0-100%)
- Group and zone lighting control
- Scene management (preset lighting configurations)
- DALI PIR occupancy sensor integration
- Daylight harvesting with lux sensor feedback
- Emergency lighting test and monitoring

### DALI-HVAC Cross-System Integration
- Shared occupancy data between lighting and HVAC systems
- Coordinated comfort optimization: right light + right temperature
- Zone-level energy optimization: reduce both when unoccupied
- Desk-level environmental mapping

## 8. Comfort Diagnosis

### Desk-Level Comfort Analysis
- Trace comfort complaints from specific desk to root cause
- Desk-to-zone-to-equipment mapping: desk → HVAC zone → FCU → AHU
- Environmental factor analysis:
  - **Near window**: Solar heat gain analysis by orientation (N=most sun in Southern Hemisphere)
  - **Near diffuser**: Draft issues from supply air
  - **Near heat sources**: Printers, copiers, servers
- DALI lighting comfort analysis: glare, insufficient light
- Temperature vs setpoint deviation analysis
- Historical comfort pattern analysis

### Cross-System Diagnosis
- Combined HVAC + lighting + occupancy analysis
- Root cause identification across subsystems
- Recommendation generation for comfort improvement

## 9. Building Onboarding

### AI-Assisted Onboarding (8-Step Workflow)
Complete workflow using SIMBIOT MCP tools:
1. **create_building** - Create building config and folder structure
2. **import_point_list** - AI parses BMS point export, generates devices/zones
3. **add_building_devices** - Save parsed devices to system
4. **add_building_zones** - Save HVAC zones with equipment mappings
5. **add_building_desks** - Map desks to zones for comfort diagnosis (optional)
6. **activate_building** - Make building live in the system
7. **get_asset_metrics_template** - Get ML metric templates for equipment types
8. **configure_asset_metrics** - Customize thresholds for predictive maintenance

### Supported BMS Vendors
| Vendor | Key | Point Format |
|--------|-----|-------------|
| Siemens Desigo CC | desigo | AHU-L12-01.SupplyAirTemp |
| Johnson Controls Metasys | metasys | NAE-1/AHU-1.SAT |
| Honeywell EBI | ebi | AHU_01_SAT |
| Schneider EcoStruxure | ecostruxure | Building/Floor12/AHU01/SAT |
| Tridium Niagara | niagara | station/Drivers/BACnet/AHU_01/SAT |
| Trend Controls | trend | AHU1.SAT |

Auto-detection when vendor not specified.

### Niagara BMS Connection Wizard
- 4-step guided wizard on Integration Monitoring page
- Connect to Tridium Niagara 4 supervisor (IP/port/credentials)
- AI-assisted BACnet point discovery and Haystack/Brick classification
- Equipment mapping review with confidence badges (high/medium/low)
- One-click approval to create equipment models and activate monitoring
- Demo mode with pre-seeded Sandton City data for testing
- Fastest onboarding path for Niagara-based buildings (no file exports needed)

### SIMBIOT MCP Server
- 23 tools for building management
- Dual transport: stdio (Claude Desktop) + SSE (cloud)
- Tool categories: Core BMS, Onboarding, AI/ML configuration
- Compatible with Claude Desktop and any MCP-capable client

### Asset Metrics Configuration
- Equipment-type-specific metric templates (chiller, AHU, FCU, generator, etc.)
- Configurable thresholds: normal, warning, critical ranges
- Health score weights per metric
- Data source types:
  - **bms_sensor** - Automatic from BMS BACnet/Modbus points
  - **mobile_phone** - Technician captures via app (audio, vibration, photos)
  - **manual** - Manual measurements with test equipment or lab analysis

## 10. Data Management

### Dual-Write Storage
- All data written to both Supabase (primary) and JSON (backup)
- Automatic fallback to JSON when Supabase unavailable
- Building data: backend/app/data/buildings/{building_id}/
- Response indicates storage method: "supabase+json" or "json"

### Data Quality Monitoring
- Real-time data completeness monitoring
- Sensor reading validation and range checking
- Missing data detection and alerting
- Data freshness monitoring (stale sensor detection)
- Quality scoring per sensor and per system

### Time-Series Storage (InfluxDB)
- High-performance time-series data storage
- Configurable retention policies
- Fast aggregation queries for dashboards
- Historical trend analysis

### RAG Knowledge Base (pgvector)
- Documentation indexed with 384-dimensional embeddings
- Hybrid search: keyword matching + semantic similarity
- Equipment knowledge base: fault codes, symptoms, solutions
- Automatic re-indexing when documentation changes

## 11. Notification & Alerting

### Equipment Alerts
- Multi-severity alert system: critical, warning, info
- Equipment health-based alert generation
- ML anomaly-triggered alerts
- Baseline deviation alerts
- Configurable alert thresholds per equipment type

### Telegram Bot (SENTRY)
- BMS queries via Telegram messaging
- Equipment status checks from mobile phone
- Alert notifications pushed to Telegram
- Natural language queries about building status
- Integration with SENTINEL AI chat backend

### Alert Management
- Alert acknowledgment workflow
- Alert escalation rules
- Alert history and trending
- Root cause linking
- Resolution tracking

## 12. Work Orders & Maintenance

### Work Order System
- Create work orders from AI chat conversation or API
- Equipment-linked work orders
- Priority classification: critical, high, medium, low
- Status tracking: open, in-progress, completed
- Category classification: HVAC, electrical, plumbing, etc.
- Work order history and reporting

### Service Records
- Maintenance history per equipment
- Service contractor tracking
- Parts and materials logging
- Labor hours recording
- Cost tracking and reporting

## 13. Bolt-On Module System

### Module Architecture
- Modular feature activation per site
- Available modules: HVAC, Energy, Security, Lighting, ML
- Auto-integrations when multiple modules active
- Per-site module configuration in site_modules.json

### Auto-Integrations
- Security + HVAC → Occupancy-based HVAC control
- Lighting + HVAC → Coordinated comfort optimization
- Energy + HVAC → Cost-optimized setpoints
- ML + HVAC → Predictive maintenance scheduling

## 14. Multi-Site Management

### Site Management
- Multiple building support with site-level dashboards
- Cross-site equipment comparison
- Fleet-level health monitoring
- Centralized alert management
- Per-site module configuration

### Edge-to-Head-Office Architecture (Planned)
- Raw data stays on-prem at each building
- Only optimization opportunity snapshots sent to central
- Self-contained snapshot format with full context
- Building profile accumulation over time for trend analysis
- Portfolio-level optimization dashboard
- Push triggers: cost savings above threshold, comfort deviation, efficiency gain, safety concern

## 15. Security & Compliance

### Data Sovereignty
- On-prem data processing: all raw building data stays at the edge
- No mandatory cloud data transfer
- Edge computing architecture for latency-sensitive operations

### Audit & Compliance
- Complete audit trail of all control actions
- Safety validation logging for every attempt
- Immutable audit records
- Export capability for compliance reporting

### Safety Validation
- Pre-execution safety checks on all control actions
- Configurable safety rules per equipment type
- Emergency override capability with enhanced logging
- Interlock dependency management

## 16. Demo & Simulation

### BMS Simulation
- Mock BMS data generation for development and demos
- Realistic sensor value simulation with drift
- Equipment state simulation (normal, warning, critical)
- Configurable simulation scenarios

### Health Simulation
- Equipment health score degradation simulation
- Alert trigger simulation for demo workflows
- One-command demo: trigger 3 equipment warnings
- One-command reset: return all equipment to healthy

### Demo Mode
- Pre-seeded AI chat responses for offline demos
- Cached response system for reliable presentations
- DEMO_MODE environment variable toggle

## API Endpoints Summary

| Category | Key Endpoints |
|----------|--------------|
| **Core Data** | /api/sites, /api/equipment, /api/sensors, /api/alerts, /api/stats |
| **AI Chat** | /api/chat (SSE), /api/hybrid-chat, /api/chat/status |
| **Devices** | /api/devices, /api/devices/{id}/control, /api/devices/{id}/points |
| **HVAC** | /api/hvac/zones, /api/hvac/chillers, /api/hvac/units/{id}/control |
| **Optimization** | /api/optimization/analyze, /api/optimization/eskom-status, /api/optimization/thermal-runway |
| **ML** | /api/ml/predictions/lstm/{id}, /api/survival/equipment/{id}, /api/rag/search |
| **Baseline** | /api/baseline/capture, /api/baseline/compare, /api/baseline/report |
| **Inspection** | /api/inspection/checklists, /api/inspection/submit, /api/inspection/reports |
| **Workflow** | /api/workflow/orchestrate, /api/workflow/triggers |
| **Integration** | /api/integration/sources, /api/integration/health, /api/integration/ingest |
| **MCP** | /api/mcp/simbiot/tools, /api/mcp/simbiot/call |
| **Energy** | /api/energy/consumption, /api/energy-centre/generators |
| **DALI** | /api/dali/zones, /api/dali/luminaires/{id}/control |
| **Simulation** | /api/simulation/start, /api/simulation/demo/trigger-warnings |
| **Health** | /api/health/scores, /api/health/config |
| **Work Orders** | /api/work-orders |

Full interactive API documentation: http://localhost:9095/docs

## Technology Stack

### Backend
- **Framework:** FastAPI + Python 3.11
- **Database:** Supabase (PostgreSQL) with pgvector for RAG
- **Time-Series:** InfluxDB for sensor data
- **AI:** Claude API (Anthropic) for complex reasoning + Ollama (local) for simple queries
- **ML:** TensorFlow (LSTM time-series, Autoencoder anomaly detection)
- **Embeddings:** all-MiniLM-L6-v2 (384 dimensions, local, free)

### Frontend
- **Framework:** Vite + React + TypeScript
- **Styling:** Tailwind CSS v4 + Sentinel design system (CSS variables, no Tremor)
- **State:** React Context (ModuleContext for bolt-on modules)

### Protocols
- BACnet/IP (HVAC systems)
- Modbus TCP (VSDs, pumps, meters)
- DALI-2 (Tridonic Scenecom lighting)
- OPC-UA (industrial systems)
- KNX (building automation)

### Deployment
- Docker Compose for development
- Docker Swarm for production
- Caddy reverse proxy with Cloudflare TLS

## Demo Building

**Sandton City Office Tower (site-002)**
- Address: 83 Rivonia Road, Sandton, Johannesburg
- Floors: 3 (L0, L1, L2) with 5 zones each (A-E)
- Area: 4,500 sqm
- Equipment: 156 items
- Desks: 300
- BMS: Siemens Desigo CC V5.0 with 4,850 data points across 10 subsystems
