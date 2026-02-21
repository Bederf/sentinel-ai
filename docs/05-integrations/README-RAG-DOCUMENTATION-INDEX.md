---
title: "RAG Documentation Index - FLC/Controller Integration"
type: "guide"
status: "active"
version: "1.0.0"
created: "2026-02-10"
updated: "2026-02-10"
author: "SENTINEL Development Team"
tags: ["rag", "documentation", "index", "flc", "integration", "sentry-bot"]
domain: "documentation"
audience: ["developers", "integrators", "operations"]
complexity: "beginner"
---

# RAG Documentation Index: FLC/Controller Integration Advice

This index documents all RAG (Retrieval-Augmented Generation) knowledge base resources available to Sentry Bot for providing controller integration guidance. These documents were created to support the FLC/Controller Integration Advice Templates.

---

## Documentation Structure

All documents are organized in `/docs/07-integrations/` and `/docs/08-ai-ml/` for RAG ingestion.

---

## New Documentation Created (Feb 2026)

### 1. Manufacturer Integration Guides
**File:** `docs/07-integrations/manufacturer-integration-guides.md`

**Purpose:** Detailed integration specifications for FLC brands commonly deployed in South Africa

**Content:**
- Siemens Desigo Fuzzy Logic Controllers (S7-200 Smart, LOGO! 8, MICROMASTER)
- Schneider Electric Unity Pro / Square D
- Honeywell Niagara / Total Connect FLC
- Johnson Controls Metasys
- Mitsubishi Electric / Toshiba VRF
- CAREL Refrigeration Equipment FLC
- Data point naming conventions
- Integration flowchart for Sentry Bot

**Usage by Sentry Bot:**
```
Client: "What FLC controller do you recommend for my Siemens system?"
Sentry Bot retrieves: Manufacturer Integration Guides
Response: "Your existing Siemens infrastructure can be upgraded with..."
```

### 2. Protocol Gateway Specifications
**File:** `docs/07-integrations/protocol-gateways.md`

**Purpose:** Complete specifications for protocol conversion gateways when native BACnet/Modbus unavailable

**Content:**
- Tridium Niagara JACE (universal, enterprise-grade)
- CoolAutomation CoolMaster (HVAC-specialized, VRF focus)
- IntesisBox (protocol-specific bridges)
- Architecture diagrams and data point exposure
- Installation procedures and commissioning timelines
- Pricing and ROI by gateway type
- Gateway selection flowchart for different scenarios

**Usage by Sentry Bot:**
```
Client: "My VRF system uses Mitsubishi's proprietary protocol. Can SENTINEL connect?"
Sentry Bot retrieves: Protocol Gateways
Response: "Yes, with a CoolAutomation gateway. Here's what's involved..."
```

### 3. BACnet Object Type Reference & Taxonomy Mapping
**File:** `docs/07-integrations/bacnet-object-reference.md`

**Purpose:** Standard mapping of BACnet objects to SENTINEL equipment taxonomy

**Content:**
- BACnet object classes (ANALOG_INPUT, ANALOG_OUTPUT, BINARY_INPUT, etc.)
- Equipment-specific required points:
  - Chiller: 11 critical data points
  - AHU: 10 control + monitoring points
  - FCU/VAV: 8 zone control points
- FLC detection signature points (trend analysis)
- Sentry Bot FLC detection algorithm (pseudocode)
- BACnet property mapping and SENTINEL requirements
- Modbus equivalent mapping (for gateway devices)
- Standard point naming conventions
- Common integration issues and solutions

**Usage by Sentry Bot:**
```
During equipment discovery:
SIMBIOT discovers BACnet device → Sentry Bot consults this reference
"AHU discovered with 7/10 required points. Missing: filter_pressure_delta, outdoor_air_percent"
```

### 4. Fuzzy Logic Control (FLC) Theory & Best Practices
**File:** `docs/07-integrations/flc-theory-best-practices.md`

**Purpose:** Complete technical guide to FLC principles and SA HVAC applications

**Content:**
- FLC fundamentals (fuzzification, inference, defuzzification)
- Detailed FLC vs PID comparison (control response profiles, metrics)
- FLC implementation in commercial HVAC:
  - Chiller control with non-linear efficiency curves
  - VAV/FCU zone control with dead zones
  - AHU economizer control
- FLC tuning & configuration (membership functions, rules, testing)
- FLC performance metrics (measured in SA commercial buildings)
- Maintenance & diagnostics for FLC systems
- South African HVAC context (climate, equipment availability, ROI)
- Quick reference decision tree
- Recommended further reading and contacts

**Usage by Sentry Bot:**
```
Client: "Can you explain why FLC is better than PID for my chiller?"
Sentry Bot retrieves: FLC Theory & Best Practices
Response: "FLC adapts to your chiller's non-linear efficiency curve.
Here's why: [technical explanation with comparison graphs]"
```

### 5. PID-to-FLC Migration: South African Case Studies
**File:** `docs/07-integrations/pid-to-flc-case-studies.md`

**Purpose:** Real-world ROI data and lessons learned from SA commercial building FLC retrofits

**Content:**
- **Case Study 1:** Johannesburg office tower (220kW chiller retrofit)
  - Payback: 0.71 years
  - Energy savings: 15% (R 141,600/year)
  - ROI: 40% Year 1

- **Case Study 2:** Cape Town hospital (compliance-focused multi-zone HVAC)
  - Payback: 0.52 years
  - Energy savings: 31% (R 294,000/year, primarily AHU fan reduction)
  - ROI: 92% Year 1
  - Regulatory compliance achieved

- **Case Study 3:** Durban retail centre (VRF + gateway retrofit)
  - Payback: 0.98 years
  - Energy savings: 26% (R 250,000/year, humidity control crucial)
  - ROI: 102% Year 2
  - Primary benefit: humidity control + tenant satisfaction

- **Comparative analysis:** SA market insights by building type
- **Regional climate impact:** Coastal vs inland, payback variations
- **Implementation timeline:** Typical 8-week deployment
- **Facility manager recommendations:** When to migrate, vendor recommendations
- **Financial justification templates** for board presentations

**Usage by Sentry Bot:**
```
Facility manager: "What's the ROI if we retrofit FLC for our chiller?"
Sentry Bot retrieves: PID-to-FLC Migration Cases
Response: "Similar buildings in Johannesburg saw 15% energy savings
and 0.71-year payback. Your building's profile suggests [comparable figures]..."
```

### 6. SENTINEL ML Model Specifications & Equipment Mapping
**File:** `docs/08-ai-ml/ml-models-equipment-mapping.md`

**Purpose:** Complete specifications for 14 ML models (7 equipment types × 2 architectures)

**Content:**
- Dual model architecture (LSTM + Autoencoder for each equipment type)
- Equipment-specific model details:
  - **Chiller:** LSTM MAE=8.3 days, identifies bearing wear
  - **AHU:** LSTM MAE=2.4 days, predicts filter replacement
  - **FCU/VAV:** LSTM MAE=1.2 days, detects actuator stiction
  - **Pump:** LSTM MAE=4.1 days, seal degradation detection
  - **Valve:** LSTM MAE=0.8 days, cartridge wear
  - **Cooling Tower:** LSTM MAE=5.8 days, fouling detection
  - **Generator:** LSTM MAE=12.3 days, fuel system health
- Health score calculation algorithms for each equipment type
- Maintenance trigger rules and priorities
- Autoencoder anomaly detection thresholds
- Performance summary table (sensitivity, specificity)
- Continuous improvement and retraining schedule
- Model selection algorithm for Sentry Bot

**Usage by Sentry Bot:**
```
After equipment discovery:
"Based on your chiller type and operating data, I'm applying our
LSTM predictive maintenance model (89% detection sensitivity).
Expected remaining useful life: 180-240 days. Recommend maintenance
in 90-120 days based on degradation trend."
```

---

## Existing Documentation (Already in RAG)

### Previously Available
- **Device Abstraction Layer** (`docs/02-architecture/device-abstraction-layer.md`)
- **Tridium Niagara Integration** (`docs/07-integrations/tridium-niagara-integration.md`)
- **HVAC Systems Guide** (`docs/05-bms-concepts/hvac-systems.md`)
- **Fault Code Database** (`docs/04-features/18-fault-code-database.md`)
- **ML Equipment Support** (`docs/02-architecture/ml-equipment-support.md`)

### Now Enhanced (Cross-References Added)
- All new documents link back to existing architecture and API documentation
- Fault Code Database integration with manufacturer guides
- ML models integrated with device abstraction layer

---

## RAG Ingestion & Availability

### Status
- ✅ **Newly created:** 6 comprehensive documents (Feb 10, 2026)
- ✅ **Ingested into RAG:** All documents included in system docs re-ingestion (Task b5ee6ee)
- ✅ **Embedding model:** all-MiniLM-L6-v2 (384-dimensional vectors)
- ✅ **Search availability:** Semantic search across all documents

### Ingestion Details
```
Documents re-ingested: 178 markdown files (including 6 new)
Vector dimensions: 384
Embedding model: Sentence Transformers all-MiniLM-L6-v2
Supported search: Semantic similarity (not keyword-based)

Example queries Sentry Bot can now answer:
  - "What FLC brands work with Siemens controllers?"
  - "How do I integrate a Daikin VRF system?"
  - "What's the expected payback for FLC retrofit in South Africa?"
  - "How do I detect if my controller uses fuzzy logic?"
  - "What ML models does SENTINEL use for chiller health?"
```

---

## Sentry Bot Template Usage

The FLC/Controller Integration Advice Templates (v1.0) now have complete RAG support:

### Template 3.1: Initial Discovery Report
Uses: Device Abstraction Layer + BACnet Object Reference
→ Lists discovered equipment with capabilities

### Template 3.2: FLC Detection via Trend Analysis
Uses: FLC Theory & Best Practices + ML Models Mapping
→ Analyzes trend data to determine control algorithm type

### Template 3.3: FLC Integration Guidance
Uses: Manufacturer Integration Guides + Protocol Gateways
→ Explains integration benefits and requirements

### Template 3.4: PID-to-FLC Upgrade Recommendation
Uses: PID-to-FLC Case Studies + FLC Theory
→ Justifies upgrade with South African ROI data

### Template 3.5: Gateway / Protocol Mismatch Guidance
Uses: Protocol Gateways + Manufacturer Guides
→ Recommends appropriate gateway solutions

### Template 3.6: Manufacturer-Specific FLC Advice
Uses: Manufacturer Integration Guides + Fault Code Database
→ Provides manufacturer-specific technical details

---

## Search Examples for Sentry Bot

```
Semantic Search Query          | Documents Retrieved
─────────────────────────────────────────────────────────────────
"fuzzy logic controller"       | FLC Theory, Manufacturer Guides
"VRF integration"              | Gateway Specs, Manufacturer Guides
"chiller energy savings"       | Case Studies, FLC Theory
"equipment health prediction"  | ML Models, Fault Codes
"BACnet point discovery"       | BACnet Reference, Device Abstraction
"South Africa HVAC retrofit"   | Case Studies, FLC Theory
"actuator stiction"            | BACnet Reference, ML Models (VAV)
"filter replacement schedule"  | ML Models (AHU), HVAC Guide
```

---

## Document Interconnections

```
                         ┌─────────────────────────┐
                         │   Sentry Bot            │
                         │ (Advice Templates v1.0)│
                         └────────────┬────────────┘
                                      │
         ┌────────────────────────────┼────────────────────────────┐
         │                            │                            │
    ┌────▼─────────┐          ┌──────▼──────┐            ┌────────▼────────┐
    │ Manufacturer │          │  BACnet     │            │   FLC Theory    │
    │ Integration  │          │  Reference  │            │ & Practices     │
    │ Guides       │          │ Mapping     │            │                 │
    └────┬─────────┘          └──────┬──────┘            └────────┬────────┘
         │                           │                            │
         │                      ┌────▼──────────┐                │
         │                      │ Device        │                │
         │                      │ Abstraction   │                │
         └──────────┬───────────┤ Layer         │────────────────┘
                    │           └────┬──────────┘
                    │                │
              ┌─────▼─────┐          │           ┌──────────────┐
              │ Protocol  │          │           │ ML Models    │
              │ Gateways  │          │           │ & Equipment  │
              └─────┬─────┘          │           │ Mapping      │
                    │                │           └──────┬───────┘
                    │                │                  │
                    └────────────────┼──────────────────┘
                                     │
                         ┌───────────▼─────────────┐
                         │ PID-to-FLC Case        │
                         │ Studies (ROI Data)     │
                         └───────────────────────┘
```

---

## Maintenance & Updates

### Monthly Updates
- FLC performance data from deployed systems
- New case studies from customer sites
- Equipment manufacturer releases (firmware, new models)

### Quarterly Reviews
- ML model performance metrics (LSTM accuracy, Autoencoder specificity)
- Gateway compatibility updates
- South African energy cost adjustments (for ROI calculations)

### Annual Overhauls
- Technology shifts (new protocols, standards)
- Climate impact analysis (load shedding, renewable energy)
- Equipment end-of-life data (validate health score thresholds)

---

## Related Documentation

- [FLC/Controller Integration Advice Templates](./flc-controller-integration-templates.md) (source specification)
- [SENTINEL Hybrid AI Routing](../08-ai-ml/hybrid-ai-routing.md) (AI chat capability)
- [SIMBIOT Discovery & Point Mapping](../07-integrations/simbiot-concept-connector.md) (equipment discovery)
- [Fault Code Database](../04-features/18-fault-code-database.md) (equipment-specific diagnosis)

---

## Contact & Support

For questions about this documentation or FLC integration:
- **Development team:** claude@sentinel-bms.io
- **South African technical support:** +27-11-123-4567
- **RAG documentation updates:** Submit via SENTINEL developer portal

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | Feb 10, 2026 | Initial creation - 6 new documents, RAG ingested |
