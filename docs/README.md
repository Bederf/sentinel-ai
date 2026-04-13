---
title: "SENTINEL Documentation"
type: "guide"
status: "approved"
version: "1.3.0"
created: "2026-01-30"
updated: "2026-03-21"
author: "Sentinel Development Team"
tags: ["documentation", "overview"]
domain: "general"
audience: "all"
complexity: "beginner"
estimated_read_time: 5
---

# SENTINEL Documentation

Comprehensive documentation for the SENTINEL BMS Intelligence Platform.

## Quick Navigation

### 🚀 Getting Started
- [Quick Start Guide](01-getting-started/quick-start.md) - 5-minute setup
- [Development Environment](01-getting-started/development-environment.md) - Full setup guide
- [Demo Guide](01-getting-started/demo-guide.md) - Demo walkthrough

### 🏗️ Architecture
- [System Overview](02-architecture/system-overview.md) - High-level architecture
- [Document Retrieval Canonical Index](02-architecture/document-retrieval-canonical-note.md) - Canonical subsystem names and boundaries for retrieval/intake/OCR pipelines
- [Concept→Canonical RAG Migration Checklist](02-architecture/concept-rag-convergence-migration-checklist.md) - ADR-005 execution checklist: deprecation flags, compatibility window, telemetry gates, cutover/rollback criteria
- **[Frontend Navigation Architecture](02-architecture/frontend-navigation.md)** - Two-level navigation: minimal global sidebar (4 items) + scrollable module-gated building detail tabs (23 views)
- [Architecture Repository (TOGAF)](02-architecture/architecture-repository/README.md) - TOGAF-aligned architecture principles, governance, landscapes, and roadmaps
- [Module System](02-architecture/module-system.md) - Bolt-on module architecture, activation, cross-module integrations
- [Module Connectivity & Cross-System Integration](02-architecture/module-connectivity.md) - How modules interconnect, integration patterns, multi-module behaviors, upsell value
- [Profile-Based Optimization Architecture](02-architecture/profile-based-optimization.md) - Three optimization profiles (SWEAT ASSETS, COMFORT, COST) with multi-objective scoring and feedback loop (Phase 72)
- [Module Connectivity - Quick Reference](02-architecture/module-connectivity-quick-ref.md) - Executive summary of modules, integrations, and profiles
- [Device Abstraction Layer](02-architecture/device-abstraction-layer.md) - Protocol-agnostic interface
- [Naming Conventions](02-architecture/naming-conventions.md) - Device ID and point naming
- [Background ML Model Retraining](02-architecture/background-ml-retraining.md) - Automated background training, APScheduler integration, production deployment (Phase 45-01)
- **[ML Data Architecture](02-architecture/ML-DATA-ARCHITECTURE.md)** - Building Operations ML, Equipment Condition ML, Unified AI Recommendation Engine, feature engineering, inspection priority scoring (Phase 132)
- **[Event Bus Architecture](02-architecture/event-bus-architecture.md)** - Async pub/sub event bus with importance scoring, middleware pipeline, event chaining, 7 default subscribers (Phase 139)
- **[Site Resolver & Multi-Site Architecture](02-architecture/site-resolver.md)** - Centralized building resolution, dynamic site discovery, no hardcoded site IDs, fresh instance support (Phase 143)

### 📚 API Reference
- **[Energy Consumption API](03-api-reference/energy-consumption.md)** - Water, power validation, cost validation, AI recommendation endpoints (Phase A, v14.0)
- [MCP Tools Reference](03-api-reference/mcp-tools-reference.md) - Model Context Protocol tools
- [Module Integration API](03-api-reference/module-integration-api.md) - Query, activate, and monitor cross-module integrations
- [Service Feedback API](03-api-reference/service-feedback-api.md) - Technician feedback collection with health scoring (Phase 41-01)
- [Condition Monitoring API](03-api-reference/condition-api.md) - Trends, degradation, RUL, fleet risk (Phase 41-03)
- [Time-Series API](03-api-reference/timeseries-api.md) - Sensor data write/query with InfluxDB (Phase 42-01)
- [Data Quality API](03-api-reference/data-quality-api.md) - Sensor health, gaps, ML training readiness (Phase 42-03)
- [ML Predictions API](03-api-reference/ml-predictions-api.md) - LSTM forecasting, anomaly detection, maintenance recommendations (Phase 43)
- [RAG API](03-api-reference/rag-api.md) - Vector search, knowledge base, document management (Phase 44-01)
- [Technician Document Upload API](03-api-reference/technician-document-upload-api.md) - Login-derived site-bound technician uploads with controlled metadata and date validation
- [Concept Evolution Connector API](03-api-reference/concept-evolution-connector-api.md) - Site-network document upload handoff endpoint for per-site Concept/internal network storage integration
- [Local Chat API](03-api-reference/local-chat-api.md) - Natural language query endpoints (Phase 44-03)
- [ML Retraining API](03-api-reference/ml-retraining-api.md) - Model retraining, performance monitoring, A/B testing (Phase 45-01)
- [Fleet Learning API](03-api-reference/fleet-learning-api.md) - Cross-site patterns, global models, fine-tuning (Phase 45-02)
- [MLOps API](03-api-reference/mlops-api.md) - Drift detection, ML alerts, retraining triggers, success metrics (Phase 45-03)
- [Solar & BESS API](03-api-reference/solar-api.md) - Solar PV, BESS dispatch, grid compliance, financial reporting, maintenance (Phase 34)
- **[Peak Demand Management API](03-api-reference/peak-demand-api.md)** - Real-time NMD monitoring, multi-module peak shaving coordination, demand forecasting with municipal bill integration (Phase 081)
- **[Sustainability & ESG API](03-api-reference/sustainability-api.md)** - Carbon emissions (v1+v2), per-system breakdown, solar offset, ESG scoring, CSV/HTML report export (Phase 111)
- [Water Meter API](03-api-reference/water-api.md) - Water consumption monitoring, leak detection, trending, alert management (Phase 35)
- [Contract Management API](03-api-reference/contracts-api.md) - Organizations, contracts, SLA terms, equipment assignments, budgets, condition assessments (Phase 48)
- [Risk-Based Pricing API](03-api-reference/pricing-api.md) - Quote calculations, SLA tier pricing, risk buffers (Phase 52)
- [Recommendations API](03-api-reference/recommendations-api.md) - Profile-based recommendations, approval workflow, outcome tracking, rejection learning, ML context injection (Phases 72, 132)
- **[Asset Health API](03-api-reference/asset-health-api.md)** - Combined equipment health scores + baseline status + deviation tracking per site/equipment (Phase 109A)
- [System Health API](03-api-reference/system-health-api.md) - Unified health snapshots, diagnostics, and system error logs
- **[Security API](03-api-reference/security-api.md)** - Access control events, visitor management, zone occupancy, cameras, occupancy trends, cross-module recommendations (Phases 27, 58, 69)
- **[Visitor Management API](03-api-reference/visitor-management-api.md)** - Reception endpoints (scan, register, issue-card), WhatsApp YES/NO webhook, RSVP accept/decline, VisitStatus lifecycle, BuildingMap (Phase 176–178)
- **[Privacy & Consent API](03-api-reference/privacy-api.md)** - POPIA consent, cross-border gating, data subject requests (DSR), and retention automation endpoints
- [Block Bookings API](03-api-reference/block-bookings-api.md) - Azure AD OAuth + Graph API ingestion, security-hardened (Phase 184 v1.1)
- **[ServiceNow API](03-api-reference/servicenow-api.md)** - Read-only ITSM endpoints for incidents, work orders, table queries, schema, history, and aggregates (Phase 138)
- **[Event Bus Monitoring API](03-api-reference/event-bus-api.md)** - Metrics, history, event chain lookup, subscription listing for the async event bus (Phase 139)
- **[Dashboard Generator API](03-api-reference/dashboard-generator-api.md)** - Auto-generate dashboard cards, monitoring rules, health weights, and module suggestions from discovered equipment (Phase 141)
- **[Plant Alerts API](04-features/plant-room-notification-pipeline.md#api-reference)** - Desigo fault email ingest, alarm retrieval, throttle status, acknowledgement (Phase 146)
- **[Gateway Log API](03-api-reference/gateway-log-api.md)** - Sentry gateway tool-level observability, activity log query (ADR-001)
- **[AI Usage & Cost Tracking API](03-api-reference/ai-usage-api.md)** - Token usage summaries, daily breakdowns, exchange rate config, per-provider/model cost tracking (v48.0)
- **[Alert Routing API](03-api-reference/buildings.md)** - Configurable alert routing rules, equipment muting, channel status (Phase 159)
- **[Semantic Classification API](03-api-reference/semantic-classification-api.md)** - Classify BACnet/DALI points against 47-tag Haystack dictionary, batch equipment classification, tag dictionary inspection (Phase 162)

### ✨ Features

#### Core Platform Features
- **[Device Control & Safety Interlocks](04-features/06-device-control-safety.md)** - Protocol-agnostic device abstraction with safety validation (Phase 6)
- **[Autonomous Decision Engine](04-features/09-autonomous-decisions.md)** - Bounded autonomy with multi-level escalation (Phase 9)
- **[Load Shedding Optimization](04-features/10-load-shedding-optimization.md)** - Thermal runway, pre-cooling, generator coordination (Phase 10)
- **[BMS/CAFM Integration & Onboarding](04-features/14-17-bms-cafm-integration.md)** - Data ingestion, onboarding wizard, go-live validation (Phases 14-17)
- **[Building Systems Integration](04-features/21-24-building-systems-integration.md)** - DALI, Hybrid AI, Desk HVAC, SIMBIOT MCP (Phases 21-24)

#### AI & Operations
- **[AI Operations & Monitoring](04-features/ai-operations-monitoring.md)** - Day-to-day AI monitoring & recommendations (control-aware)
- **[Health Scoring System](04-features/health-scoring-system.md)** - Equipment health calculation with configurable thresholds
- **[72: Profile-Based Optimization](04-features/72-profile-based-optimization.md)** - Three business-aligned optimization profiles (SWEAT ASSETS, COMFORT, COST) with multi-objective scoring, control tiers, and feedback loop (Phase 72)
- **[82: Optimization Tier Router](04-features/phase-implementations.md#phase-82-optimization-tier-router)** - Confidence-based recommendation routing (blocked/advisory/approval/auto-execute) with shadow/enforce modes (Phase 82, v14.0)
- **[44-02: Explainable AI for ML Predictions](04-features/44-02-explainable-ai.md)** - Natural language explanations for AI predictions (Phase 44-02)
- **[44-03: Conversational Interface](04-features/44-03-conversational-interface.md)** - Natural language queries over ML predictions via local Ollama LLM (Phase 44-03)
- **[45-01: Online Learning & Automated Retraining](04-features/45-01-online-learning.md)** - Model freshness monitoring, auto-retraining, A/B testing (Phase 45-01)
- **[45-02: Fleet Learning & Cross-Site Insights](04-features/45-02-fleet-learning.md)** - Anonymized fleet patterns, global models, local fine-tuning (Phase 45-02)
- **[45-03: MLOps Monitoring & Success Metrics](04-features/45-03-mlops-monitoring.md)** - Drift detection, ML alerting, retraining triggers, metrics dashboard (Phase 45-03)
- **[113: RLM Runner Service](04-features/113-rlm-runner-service.md)** - Standalone long-context evidence analysis with recursive multi-pass LLM, POPIA redaction, audit trace, and feature-gated Sentinel integration (Phase 113)
- **[155-159: Operational Intelligence](04-features/155-159-operational-intelligence.md)** - Cross-signal correlation engine, issue clustering, relationship graph (Cytoscape.js), role-scoped routing, signal emitter bridges (Phases 155-156 shipped, 159 planned)

#### Asset Management Workflow
- **[Asset Baseline Assessment](04-features/44-asset-baseline-assessment.md)** - Asset condition scoring and maintenance cost modeling (Phase 44)
- **[Equipment Baseline Capture & Comparison](04-features/54-equipment-baseline-assessment.md)** - Multi-source baseline capture (manual, BMS, mobile), intelligent tolerances, deviation detection with automatic alerts (Phase 54)
- **[Routine Inspection & Maintenance](04-features/45-routine-inspection-maintenance.md)** - Field inspection workflow with baseline tracking (Phase 45)
- **[OEM-Specific Checklist Generation](04-features/66-oem-checklist-generation.md)** - AI-generated manufacturer-specific inspection checklists with Supabase storage (Phase 66)
- **[Repair Effectiveness & ML Feedback Loop](04-features/46-repair-effectiveness-ml-feedback.md)** - Post-repair validation, ML feedback, follow-up scheduling, cost-benefit analysis (Phase 57)
- **[Phases 44-46-54 Integration: Complete Asset Management Workflow](04-features/44-46-54-integration-workflow.md)** - Unified workflow integrating baseline capture, multi-source comparison, inspection, and repair validation (Phases 44, 45, 46, 54)
- **[Service Feedback System](04-features/service-feedback-system.md)** - Equipment-type specific feedback from technicians with health score updates
- **[109A: Asset Health Baseline Recording](04-features/109A-asset-health-baseline.md)** - Unified health score + baseline status + deviation view per equipment, auto-capture on onboarding (Phase 109A)
- **[109C: Site-002 Deterministic Mode Policy (Dry-Run)](04-features/109C-site-002-mode-policy-dry-run.md)** - Deterministic onboarding stage thresholds with dwell windows, fail-closed logic, and anti-flap stability (Phase 109C)
- **[109D: Operational Flows Pack](04-features/109D-operational-flows-index.md)** - Fail-closed, promotion evidence, provenance breach, supervised rollback, maintenance closure, and ML retraining readiness flows

#### Remote Operations
- **[Remote Operations](04-features/remote-operations.md)** - Remote monitoring, command execution, and smart dispatch with task bundling (Phase 59)

#### Onboarding & Integration
- **[Niagara BMS Connection Wizard](04-features/niagara-connection-wizard.md)** - 4-step wizard: connect to Niagara supervisor, discover BACnet points, AI-classify, approve
- **[141: Auto-Dashboard Generator](04-features/141-auto-dashboard-generator.md)** - Equipment classification (25 categories), tailored dashboard cards (15 templates), monitoring rules (21 defaults), health weights, module suggestions with savings hints, event-driven auto-trigger (Phase 141)

#### Simulation & Demo
- **[24-Hour Lifecycle Simulation](04-features/lifecycle-simulation.md)** - Full building day simulation for testing AI optimization, faults, alerts, repairs
- **[Simulation Analytics Pipeline](04-features/simulation-analytics-pipeline.md)** - JSONL event logging and optimization profile analysis (asset sweating, comfort first, cost saving)
- **[Demo Simulation Control](04-features/demo-simulation-control.md)** - Simple trigger/reset endpoints for demos

#### Solar & Energy Storage
- **[Solar & BESS Optimisation Module](04-features/34-solar-bess-module.md)** - Data ingestion, performance monitoring, NRS 097 compliance, arbitrage, demand management, forecasting, health analytics, maintenance, financial reporting (Phase 34)
- **[Water Meter Integration & Leak Detection](04-features/35-water-meter-integration.md)** - Modbus pulse counter integration, 3-algorithm leak detection, consumption trending, alert management, water dashboard (Phase 35)

#### Sustainability & ESG
- **[Sustainability & ESG Module](04-features/29-sentinel-sustainability.md)** - Carbon emissions (Scope 1/2/3), energy efficiency benchmarks, Green Star SA self-assessment, per-system breakdown, solar offset, ESG scoring, report export (Phase 29 + Phase 111)

#### Contract Management
- **[Contract Management Module](04-features/48-contract-management.md)** - Portfolio KPIs, SLA compliance tracking, budget variance analysis, profitability dashboard (Phase 48)
- **[SLA Monitoring & Profitability](04-features/50-52-commercial-analytics.md)** - SLA compliance tracking, profitability dashboards, and risk-based pricing (Phases 50-52)
- **[Municipal Billing Integration](04-features/49-municipal-billing.md)** - SA municipal invoice processing, cost tracking, tariff validation, variance detection, MCP tools for AI-powered workflows; NMD extraction for peak demand management (Phase 49, enhanced in Phase 081)
- **[Technician Document Upload Rules Matrix](04-features/technician-document-rules-matrix.md)** - Controlled technician upload taxonomy, mandatory metadata, trigger-date/retention rules, login-derived site binding, and validation controls

#### Plant Room Alerts
- **[Plant Room Notification Pipeline](04-features/plant-room-notification-pipeline.md)** - Desigo BMS fault email ingestion, severity classification, Twilio WhatsApp delivery with alarm flood protection and rate limiting (Phase 146)

#### Settings & Operations
- **[API & Service Cost Tracking](04-features/ai-cost-tracking.md)** - Unified cost tracking across AI providers, messaging (WhatsApp, BulkSMS, Telegram), and services (ElevenLabs, EskomSePush) with daily email reports and cost threshold alerts (v48.0 + Phase 158 + 2026-03-21 coverage fixes)
- **[160: AI Governance Metrics](04-features/160-ai-governance-metrics.md)** - 5 Prometheus metric families (quality gates, model drift, tool errors, approval latency, AI cost/route), POPIA evidence packs, 6 Grafana panels, 5 REST endpoints (Phase 160)

#### Additional Features
- [Technician Chat](04-features/technician-chat.md) - Guided fault diagnosis (Phase 19)
- [AI-Assisted Onboarding](04-features/ai-assisted-onboarding.md) - Import BMS data via MCP tools
- [41-01/02 - ML Knowledge Capture](04-features/41-ml-knowledge-capture-01.md) - OCR and data collection
- [41-03 - Vibration & Audio Analysis](04-features/41-03-vibration-audio-analysis.md) - phyphox sensor data, bearing defect detection, condition scoring
- [42 - Data Collection & Storage](04-features/42-data-collection-storage.md) - InfluxDB integration
- [43 - ML Model Development](04-features/43-ml-model-development.md) - LSTM and Autoencoder models
- [18 - Fault Code Database](04-features/18-fault-code-database.md) - Equipment fault diagnosis
- **[176: Visitor Management](04-features/176-visitor-management.md)** - Deterministic visitor identity (Outlook→QR→scan→register→WhatsApp→C-CURE), 8-state lifecycle, Twilio HMAC-verified webhook, policy engine, audit log (Phase 176)

### 🏢 BMS Concepts
- [BMS Fundamentals](05-bms-concepts/bms-fundamentals.md) - BMS domain knowledge
- [HVAC Systems Guide](05-bms-concepts/hvac-systems.md) - Chiller, AHU, FCU, VAV with schematics (Technician/Operator reference)

### 🛡️ Safety & Compliance
- [Safety Interlocks Engine](06-safety-compliance/safety-interlocks-engine.md) - Safety validation
- [Audit Logging](06-safety-compliance/audit-logging.md) - Device control, login, and decision pipeline audit trail
- [AEGIS Phase 1 Entry Gate](06-safety-compliance/aegis-phase1-entry-gate.md) - Mandatory readiness and sign-off checklist before enabling BESS writes
- **[Data Privacy & Security Architecture](09-security/SECURITY-PRIVACY.md)** - Data sovereignty, local AI, air-gapped deployment, POPIA compliance

### 🔒 Security & Governance
- **[Security Documentation Suite](09-security/README.md)** - Complete security policy suite for FSR supplier onboarding
- **[AI Governance Pack](09-security/ai-governance/README.md)** - ISO 42001, NIST AI RMF, and EU AI Act operational mapping with evidence structure
- **[EU AI Act Compliance Register](09-security/compliance/eu-ai-act-compliance-register.md)** - AI feature inventory, risk class, obligations, owners, and evidence tracker
- **[EU AI Act Policy](09-security/compliance/eu-ai-act-policy.md)** - Mandatory AI governance controls for EU AI Act alignment
- **[EU AI Act Internal Audit 2026 Q2](09-security/compliance/eu-ai-act-internal-audit-2026Q2.md)** - Internal assurance checklist and findings tracker
- **[POPIA Compliance Register](09-security/compliance/popia-compliance-register.md)** - POPIA pass/fail controls, evidence, and remediation tracking
- **[POPIA Data Subject Rights Workflow](09-security/compliance/popia-data-subject-rights-workflow.md)** - Request lifecycle, SLA tracking, and workflow states
- **[POPIA Retention Enforcement](09-security/compliance/popia-retention-enforcement.md)** - Automated retention enforcement and run evidence
- **[Asset Lifecycle Policy](09-security/asset-lifecycle-policy.md)** - Formal lifecycle controls for infrastructure, application, and data assets
- **[Vulnerability Disclosure Policy](09-security/vulnerability-disclosure-policy.md)** - Coordinated disclosure process and reporter safe-harbor
- **[BCP/DR Exercise Report 2026 Q1](09-security/dr-exercise-report-2026Q1.md)** - Tabletop + restore test evidence capture template
- **[FSR Gap Analysis - Updated](FSR_GAP_ANALYSIS_UPDATE.md)** - Current assessment against FSR V8 questionnaire
- **Encryption at Rest** - Fernet AES-128-CBC for audit logs (Phase 81, v14.0)
- **[Logging Architecture](09-security/logging-architecture.md)** - Promtail → Loki pipeline, security events, decision pipeline observability, Grafana dashboards
- [Information Security Framework](09-security/information-security-framework.md) - Governance structure, ISO role, policy hierarchy
- [Information Security Strategy](09-security/information-security-strategy.md) - Maturity targets, remediation roadmap
- [Information Security Policy](09-security/information-security-policy.md) - Overarching policy covering all 18 FSR domains
- [Acceptable Usage Policy](09-security/acceptable-usage-policy.md) - Infrastructure, communication, and data handling rules
- [Audit Logging](06-safety-compliance/audit-logging.md) - Device control and login audit trail

### 🔗 Integrations
- [DALI-HVAC Integration](07-integrations/dali-hvac-integration.md) - Cross-system comfort diagnosis
- [CAFM Schema](07-integrations/cafm-schema.md) - CAFM data model
- [Energy Centre](07-integrations/energy-centre.md) - Generators, ATS, power metering, UPS
- **[Tridonic DALI Discovery](07-integrations/tridonic-dali-discovery.md)** - Auto-discover DALI gateways and generate v2.0 equipment codes for bulk import (Phase 21-02)
- **[Tridium Niagara Integration](07-integrations/tridium-niagara-integration.md)** - BACnet/IP, oBIX, AI point discovery for Niagara JACE/Supervisor
- **[SIMBIOT Concept Connector](07-integrations/simbiot-concept-connector.md)** - MRI Evolution CAFM integration via FSI API (auto work orders, status polling, asset sync)
- **[SIMBIOT Universal Adapter Pattern](05-integrations/simbiot-universal-adapter-pattern.md)** - One SBC, any building: SIMBIOT translates any BMS format (Desigo, Trane, JCI, BACnet, Modbus, simulation) to SENTINEL's fixed Supabase schema without code changes
- **[Semantic Control Foundation — Classifier & Validation](05-integrations/162-semantic-classifier.md)** - Deterministic Haystack-inspired point classifier with weighted evidence scoring, safety-class gating, and static validation engine for blind site onboarding (Phase 162)
- **[Asset Workflow Architecture](05-integrations/asset-workflow-architecture.md)** - SIMBIOT + Baseline + Inspection + ML integration (Phase 53-01)
- **[Asset Lifecycle State Machine](05-integrations/asset-lifecycle-state-machine.md)** - 13 states from onboarding to monitoring (Phase 53-01)
- **[Workflow Triggers & Automation](05-integrations/workflow-triggers.md)** - 5 automated triggers for ML → Inspection → Repair → Validation (Phase 53-02)
- [AEGIS Site-002 Discovery](05-integrations/aegis-site-002-discovery.md) - Site-level BESS control boundaries, interfaces, and pre-live confirmation points
- **[ServiceNow Integration](05-integrations/servicenow-integration.md)** - Read-only ITSM client with auto-discovery, 10 API endpoints, 4 chat tools, config-ready (Phase 138)
- **[Maintenance Intake Architecture](05-integrations/maintenance-intake-architecture.md)** - Generic maintenance/work-order adapter layer — one `maintenance_events` table, one adapter per site (MRI Evolution, ServiceNow, CSV, etc.), source-agnostic SLA breach detection and P1-P4 priority normalisation
- **[Visitor Management Integrations](05-integrations/visitor-management-integrations.md)** - Google Calendar (Pub/Sub webhook), Microsoft Graph (webhook), Email intake (n8n IMAP), WhatsApp (Twilio), Active Directory (JSON), C-CURE, SMTP — Accept-First visitor flow (Phase 178)

### 📦 Modules
- [Module Registry](13-modules/module-registry.md) - Bolt-on module system architecture

### 🗄️ Database
- [Service Records Schema](07-database/SERVICE_RECORDS_SCHEMA.md) - Service records table structure
- **[Daily Sustainability Metrics](07-database/daily-sustainability-metrics.md)** - Energy/water/diesel/solar daily snapshots with computed emissions (Phase 111)
- **[Security Module Schema](07-database/69-security-module-schema.md)** - access_rules table, occupancy capacity, camera stream URLs (Phase 69)

### 🤖 AI & ML
- **[AI Recommendation System](08-ai-ml/ai-recommendation-system.md)** - Zone-aware HVAC optimization with Claude AI
- [Claude Integration](08-ai-ml/claude-integration.md) - Claude API usage
- [Hybrid AI Router](08-ai-ml/hybrid-ai-routing.md) - Ollama/cloud routing with POPIA consent gating
- **[RAG Integration Overview](08-ai-ml/rag-integration-overview.md)** - Vector database and semantic search (Phase 44-01)
- **[Explainable AI](08-ai-ml/explainable-ai.md)** - XAI for ML predictions and maintenance recommendations (Phase 44-02)

### 🔧 Development
- [Tool Use Best Practices](12-development/tool-use-best-practices.md) - Development workflow
- [GSD Pipeline Architecture](12-development/gsd-pipeline-architecture.md) - Phase orchestration, Ralph Loop, orthogonal validation

### 🔧 Operations
- **[Deployment Runbook](10-operations/deployment-runbook.md)** - Step-by-step new site deployment: install → Supabase → config → services → SIMBIOT wizard → technician setup → verification
- **[Monitoring Stack](10-operations/monitoring-stack.md)** - Loki + Promtail + Grafana deployment, config management, scrape jobs, dashboard provisioning
- **[Supabase Performance Runbook](10-operations/supabase-performance-runbook.md)** - Indexes, query optimization, Redis caching, archival, backup trigger
- [AEGIS Phase 0 Daily Ops Runbook](10-operations/aegis-phase0-daily-ops.md) - Daily governance, queue, tripwire, and evidence workflow for 0A/0B

### 🩺 Troubleshooting
- [ML Model Health](05-troubleshooting/ml-model-health.md) - ML model issues
- **[Logging & Observability](05-troubleshooting/logging-observability.md)** - Promtail/Loki/Grafana pipeline diagnostics, common issues

### 🧪 Testing
- [Testing Strategy](11-testing/testing-strategy.md) - Test architecture
- [E2E Testing](11-testing/e2e-testing.md) - End-to-end tests
- [Test Data](11-testing/test-data.md) - Test data management
- **[Runner Eval Harness](11-testing/runner-eval-harness.md)** - 5 golden-case fixtures for RLM runner quality validation, POPIA redaction compliance, and regression testing (Phase 113)

### 🌍 South Africa Context
- [Load Shedding Optimization](14-south-africa-context/load-shedding-optimization.md) - Eskom load shedding

## Documentation Structure

```
docs/
├── architecture-repository/ # TOGAF-aligned architecture repository (principles, governance, landscapes, roadmaps)
├── ai-governance/          # AI governance pack (scope, risk mapping, controls, evidence)
├── 01-getting-started/      # Onboarding, setup, quick start
├── 02-architecture/         # System design, patterns, data flow
├── 03-api-reference/        # REST API, MCP tools, SSE streams
├── 04-features/             # Feature specifications
├── compliance/              # Regulatory compliance (EU AI Act registers, policies, audits)
├── 05-bms-concepts/         # BMS/HVAC domain knowledge
├── 06-safety-compliance/    # Safety interlocks, audit trails
├── 07-integrations/         # BACnet, Modbus, CAFM, BMS, DALI
├── 08-ai-ml/                # Claude, Ollama, predictions
├── 09-security/             # Security policies, privacy, audit, governance
├── 10-operations/           # Deployment, monitoring
├── 11-testing/              # Unit tests, integration tests
├── 12-development/          # Workflow, tooling, best practices
├── 13-modules/              # Bolt-on module system (Energy, HVAC, Security, Lighting, Sustainability)
├── 14-south-africa-context/ # Load shedding, Eskom
├── 15-troubleshooting/      # Common issues, diagnostics
├── 16-glossary/             # BMS terms, acronyms
├── 17-appendices/           # Migration scripts, references
└── _templates/              # Documentation templates and standards
```

## Documentation Standards

All documentation follows the [AimTheLaw-style standards](_templates/standards.md):

- **Frontmatter:** Required metadata on all documents
- **Markdown:** GitHub Flavored Markdown (GFM)
- **Diagrams:** Mermaid.js for architecture and flow diagrams
- **Code Examples:** Tested, syntactically correct, with comments
- **Audience:** Clearly defined (developers, operators, safety engineers, etc.)
- **Complexity:** Reading level indicated (beginner, intermediate, advanced)

## Frontmatter Schema

Every document must include frontmatter:

```yaml
---
title: "Document Title"
type: "architecture|guide|reference|spec|tutorial|audit|policy"
status: "draft|review|approved|deprecated"
version: "1.0.0"
created: "2026-01-30"
updated: "2026-01-30"
tags: ["tag1", "tag2"]
domain: "bms|hvac|lighting|security|water|solar|compliance|general"
audience: "developers|operators|product-managers|safety-engineers|all"
complexity: "beginner|intermediate|advanced"
estimated_read_time: 15
---
```

## Validation

Run validation before committing documentation:

```bash
# Validate frontmatter
python scripts/validate-frontmatter.py

# Check links (requires markdown-link-check)
npm install -g markdown-link-check
find docs -name "*.md" -exec markdown-link-check {} \;
```

## Contributing

When adding new documentation:

1. **Choose appropriate directory** based on content type
2. **Use templates** from `_templates/` directory
3. **Include frontmatter** with all required fields
4. **Test code examples** to ensure they work
5. **Add diagrams** using Mermaid.js where appropriate
6. **Validate** using validation scripts
7. **Link** from relevant sections in this README

## Reading Guide

### For New Developers
1. Start with [Quick Start Guide](01-getting-started/quick-start.md)
2. Read [Development Environment](01-getting-started/development-environment.md)
3. Review [System Overview](02-architecture/system-overview.md)
4. Study [Tool Use Best Practices](12-development/tool-use-best-practices.md)

### For BMS Operators
1. Start with [Quick Start Guide](01-getting-started/quick-start.md)
2. Review [Demo Guide](01-getting-started/demo-guide.md)
3. Understand [Safety Interlocks Engine](06-safety-compliance/safety-interlocks-engine.md)
4. Study [Load Shedding Optimization](14-south-africa-context/load-shedding-optimization.md)

### For Product Managers
1. Start with [System Overview](02-architecture/system-overview.md)
2. Review [Features](04-features/) for capability overview
3. Study [BMS Fundamentals](05-bms-concepts/bms-fundamentals.md) for domain knowledge

### For Safety Engineers
1. Start with [Safety Interlocks Engine](06-safety-compliance/safety-interlocks-engine.md)
2. Review [System Architecture](02-architecture/system-overview.md) for data flow
3. Study [Audit Trail](06-safety-compliance/audit-trail.md) for compliance

## Status

- **Total Directories:** 17
- **Total Documents:** 30+
- **With Frontmatter:** 23+
- **Target:** 25-30 core documents (met)

## Next Actions

- [ ] Add frontmatter to migrated files
- [ ] Create Tier 1 critical documents (safety, database, API)
- [ ] Create Tier 2 domain-specific docs (BMS concepts, load shedding)
- [ ] Create Tier 3 feature specs
- [ ] Create Tier 4 troubleshooting and operations guides
- [x] Module Registry documentation (13-modules/module-registry.md)
- [x] Energy Centre integration (07-integrations/energy-centre.md)

## Related Resources

- [CLAUDE.md](../CLAUDE.md) - Claude Code project instructions
- [README_MCP_INTEGRATION.md](../backend/README_MCP_INTEGRATION.md) - MCP server guide
- [NAMING_CONVENTIONS.md](../NAMING_CONVENTIONS.md) - Device naming (moved to docs)
