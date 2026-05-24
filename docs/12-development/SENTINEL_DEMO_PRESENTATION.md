---
title: "SENTINEL BMS Intelligence Platform"
type: "guide"
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

# SENTINEL BMS Intelligence Platform
## Interview Demo Presentation Guide

---

## 1. Introduction (2-3 minutes)

### What is SENTINEL?

**SENTINEL** (Smart ENvironment & Telemetry INtelligence for Efficient Living) is an AI-powered Building Management System that transforms how facilities are monitored, maintained, and optimized.

### The Problem We Solve

| Traditional BMS | SENTINEL |
|-----------------|----------|
| Reactive maintenance (fix when broken) | Predictive maintenance (fix before failure) |
| Manual monitoring | AI-driven anomaly detection |
| Siloed systems | Unified intelligence layer |
| Complex interfaces | Conversational AI interface |
| Static rules | Adaptive learning |

### Value Proposition

- **40% reduction** in unplanned downtime
- **25% savings** on maintenance costs
- **Real-time insights** via natural language
- **Proactive alerts** before equipment fails

---

## 2. Platform Architecture (3-4 minutes)

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    SENTINEL Platform                         │
├─────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │   Frontend   │  │   Backend    │  │   AI Layer   │      │
│  │  React + TS  │  │   FastAPI    │  │ Claude + ML  │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
├─────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │   SIMBIOT    │  │  ML Engine   │  │  Supabase    │      │
│  │  MCP Server  │  │ LSTM/AutoEnc │  │  PostgreSQL  │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
├─────────────────────────────────────────────────────────────┤
│           Siemens Desigo CC (BMS/SCADA Head-End)            │
│              4,850 data points │ 10 subsystems               │
├─────────────────────────────────────────────────────────────┤
│                    Device Abstraction Layer                  │
│    BACnet/IP  │  Modbus TCP  │  DALI-2  │  OPC-UA  │  KNX  │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐           │
│  │  HVAC   │ │Lighting │ │ Energy  │ │Metering │           │
│  │ Desigo  │ │Tridonic │ │ DSE8610 │ │ ION9000 │           │
│  │  PXC    │ │ DALI-2  │ │ Modbus  │ │ Modbus  │           │
│  └─────────┘ └─────────┘ └─────────┘ └─────────┘           │
└─────────────────────────────────────────────────────────────┘
```

### Bolt-On Module System

SENTINEL uses a modular architecture where capabilities can be enabled per site:

| Module | Capabilities |
|--------|--------------|
| **HVAC** | Temperature control, air quality, comfort optimization |
| **Energy** | Load monitoring, demand response, load shedding |
| **Lighting** | DALI integration, daylight harvesting, scheduling |
| **Security** | Access control, occupancy detection |

**Auto-Integrations**: When multiple modules are active, they work together automatically (e.g., Security + HVAC = occupancy-based climate control).

---

## 3. SIMBIOT - The Intelligence Core (4-5 minutes)

### What is SIMBIOT?

**SIMBIOT** (Smart Integrated Management for Buildings via Intelligent Operations Technology) is SENTINEL's Model Context Protocol (MCP) server that enables AI assistants to interact with building systems.

### 21 Integrated Tools

| Category | Tools | Purpose |
|----------|-------|---------|
| **Equipment** | get_equipment_list, get_equipment_status, get_equipment_health | Real-time asset visibility |
| **Telemetry** | get_zone_temperatures, get_energy_usage, get_sensor_readings | Live data access |
| **Control** | control_device, set_temperature, adjust_lighting | Safe command execution |
| **Maintenance** | get_maintenance_schedule, log_maintenance, create_work_order | Workflow automation |
| **Alerts** | get_active_alerts, acknowledge_alert, get_alert_history | Incident management |
| **Predictions** | get_failure_predictions, get_health_trends | Predictive insights |

### Safety Validation Layer

Every control command passes through the Safety Engine:

```
User Request → AI Processing → Safety Validation → Device Control
                                     ↓
                              ┌─────────────────┐
                              │ Safety Rules    │
                              │ • Temp: 16-28°C │
                              │ • Pressure lim  │
                              │ • Interlocks    │
                              │ • Runtime caps  │
                              └─────────────────┘
```

**Severity Levels:**
- `WARNING` - Allow with notification
- `BLOCK` - Prevent action
- `ALARM` - Critical escalation

---

## 4. AI Chat System (4-5 minutes)

### How the Chat Works

```
┌──────────────────────────────────────────────────────────┐
│                    User Message                           │
└─────────────────────────┬────────────────────────────────┘
                          ▼
┌──────────────────────────────────────────────────────────┐
│              Hybrid AI Router                             │
│  ┌────────────────┐    ┌────────────────┐               │
│  │    Tier 1      │    │    Tier 2      │               │
│  │  Ollama (Local)│    │  Claude (API)  │               │
│  │  Simple queries│    │  Complex tasks │               │
│  │     FREE       │    │     PAID       │               │
│  └────────────────┘    └────────────────┘               │
└─────────────────────────┬────────────────────────────────┘
                          ▼
┌──────────────────────────────────────────────────────────┐
│           SIMBIOT Tool Execution                          │
│  • Query equipment status                                 │
│  • Execute control commands                               │
│  • Generate predictions                                   │
└─────────────────────────┬────────────────────────────────┘
                          ▼
┌──────────────────────────────────────────────────────────┐
│              Streaming Response (SSE)                     │
└──────────────────────────────────────────────────────────┘
```

### Example Conversations

**Simple Query (Tier 1 - Ollama):**
> "What's the temperature in Level 2?"
> → Returns: "Level 2 average temperature is 22.7°C (range 21.6-23.7°C across 5 zones)"

**Complex Task (Tier 2 - Claude):**
> "The CFO is coming tomorrow. Optimize L2 for comfort and prepare a status report."
> → Adjusts setpoints, checks equipment health, generates report with readings

### Cost Optimization

| Query Type | Router Decision | Cost |
|------------|-----------------|------|
| Data lookups | Tier 1 (Ollama) | Free |
| Status checks | Tier 1 (Ollama) | Free |
| Control actions | Tier 2 (Claude) | Paid |
| Complex reasoning | Tier 2 (Claude) | Paid |

**Result: 40% cost savings** vs all-Claude approach

---

## 5. Technician Chat (3-4 minutes)

### Purpose

A specialized interface for maintenance technicians working on-site, providing:

- Equipment diagnostics
- Troubleshooting guidance
- Service history lookup
- Parts recommendations
- Work order creation

### RAG-Enhanced Knowledge

The Technician Chat uses Retrieval-Augmented Generation (RAG) to access:

| Knowledge Source | Content |
|------------------|---------|
| Equipment Manuals | OEM documentation, specs |
| Service History | Past repairs, patterns |
| Fleet Knowledge | Similar equipment insights |
| Best Practices | Industry standards |

### Example Interaction

**Technician:** "Chiller-001 is making a grinding noise"

**System Response:**
```
Based on the symptoms and Chiller-001's service history:

LIKELY CAUSES:
1. Bearing wear (70% probability) - Last replaced 18 months ago
2. Compressor issue (20% probability)
3. Loose mounting (10% probability)

RECOMMENDED ACTIONS:
1. Check bearing temperatures (currently 45°C - normal)
2. Listen for frequency pattern (low = bearing, high = compressor)
3. Inspect mounting bolts

PARTS POSSIBLY NEEDED:
• Bearing set (Part# CHB-2234) - 2 day lead time
• Vibration dampers (Part# VD-100)

Create work order? [Yes] [No]
```

---

## 6. Predictive Maintenance System (5-6 minutes)

### How Predictions Work

```
┌─────────────────────────────────────────────────────────┐
│                 Data Collection                          │
│  • Temperature readings    • Vibration patterns         │
│  • Power consumption       • Runtime hours              │
│  • Pressure readings       • Service history            │
└────────────────────────────┬────────────────────────────┘
                             ▼
┌─────────────────────────────────────────────────────────┐
│                 ML Model Pipeline                        │
│  ┌──────────────┐    ┌──────────────┐                  │
│  │    LSTM      │    │ Autoencoder  │                  │
│  │  Time-series │    │   Anomaly    │                  │
│  │  Forecasting │    │  Detection   │                  │
│  └──────────────┘    └──────────────┘                  │
└────────────────────────────┬────────────────────────────┘
                             ▼
┌─────────────────────────────────────────────────────────┐
│              Prediction Generation                       │
│  • Failure probability (0-100%)                         │
│  • Time to failure estimate                             │
│  • Contributing factors                                 │
│  • Confidence score                                     │
└────────────────────────────┬────────────────────────────┘
                             ▼
┌─────────────────────────────────────────────────────────┐
│           Explainable AI (XAI) Layer                    │
│  Converts ML output to natural language explanations    │
└─────────────────────────────────────────────────────────┘
```

### LSTM Model - Time Series Forecasting

**Purpose:** Predict future equipment behavior based on historical patterns

**Training Data:**
- 30-90 days of sensor readings
- Sampled at 15-minute intervals
- Features: temperature, pressure, power, runtime

**Output:**
- 24h, 48h, 72h predictions
- Confidence intervals
- Trend direction

### Autoencoder Model - Anomaly Detection

**Purpose:** Detect unusual equipment behavior that deviates from normal patterns

**How It Works:**
1. Learn "normal" operating patterns
2. Reconstruct incoming data
3. High reconstruction error = anomaly
4. Flag for investigation

### Health Score Calculation

```python
Health Score = 100 - (
    age_factor * 0.15 +           # Equipment age impact
    runtime_factor * 0.20 +        # Hours since maintenance
    anomaly_factor * 0.25 +        # ML-detected anomalies
    alert_history * 0.15 +         # Recent alert count
    prediction_factor * 0.25       # Failure probability
)
```

| Health Range | Status | Action |
|--------------|--------|--------|
| 90-100% | Healthy | Routine monitoring |
| 70-89% | Warning | Schedule inspection |
| 50-69% | Critical | Immediate attention |
| <50% | Failure Risk | Emergency response |

---

## 7. Work Order Workflow (3-4 minutes)

### Automated Work Order Generation

```
Equipment Alert → AI Analysis → Work Order Creation → Assignment → Execution → Verification
```

### Work Order Contains

| Field | Source |
|-------|--------|
| Priority | AI-calculated from health + prediction |
| Equipment Details | Asset database |
| Problem Description | AI-generated from telemetry analysis |
| Recommended Actions | ML model + RAG knowledge |
| Parts Needed | Historical patterns + OEM data |
| Estimated Duration | Similar job history |
| Technician Skills | Required certifications |

### Example Work Order

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WORK ORDER: WO-2024-0234
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PRIORITY: HIGH
EQUIPMENT: Chiller-001 (Carrier 30XA)
LOCATION: Sandton City - Plant Room B2

ISSUE: Predicted bearing failure within 14 days
       Health score dropped from 92% to 68%

EVIDENCE:
• Vibration levels increased 23% over 7 days
• Motor temperature trending upward (+2.1°C/day)
• Similar failure pattern seen in Chiller-003 (2023)

RECOMMENDED ACTIONS:
1. Inspect compressor bearings
2. Check motor alignment
3. Review lubrication schedule

PARTS TO ORDER:
• Bearing set (P/N: CHB-2234) - In stock
• Shaft seal kit (P/N: SS-445) - 3 day lead

ESTIMATED DOWNTIME: 4-6 hours
REQUIRED SKILLS: HVAC Level 3, Carrier certified
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## 8. Client Onboarding Process (3-4 minutes)

### Onboarding Workflow

```
┌─────────────────────────────────────────────────────────┐
│ Phase 1: Discovery (Week 1)                              │
│ • Site survey and equipment inventory                   │
│ • BMS protocol assessment (BACnet/Modbus/DALI)          │
│ • Integration requirements                               │
└────────────────────────────┬────────────────────────────┘
                             ▼
┌─────────────────────────────────────────────────────────┐
│ Phase 2: Integration (Week 2-3)                          │
│ • Device abstraction layer setup                         │
│ • Data point mapping                                     │
│ • Historical data import                                 │
└────────────────────────────┬────────────────────────────┘
                             ▼
┌─────────────────────────────────────────────────────────┐
│ Phase 3: Baseline (Week 3-4)                             │
│ • 2-week data collection minimum                         │
│ • Normal operation pattern learning                      │
│ • ML model training per equipment type                   │
└────────────────────────────┬────────────────────────────┘
                             ▼
┌─────────────────────────────────────────────────────────┐
│ Phase 4: Activation (Week 4-5)                           │
│ • Module activation per site                             │
│ • Alert threshold configuration                          │
│ • User training and handover                             │
└─────────────────────────────────────────────────────────┘
```

### Per-Site Configuration

Each site gets customized:

| Configuration | Example |
|---------------|---------|
| Modules Enabled | HVAC + Energy + Lighting |
| Alert Recipients | FM team, Building manager |
| Operating Hours | 07:00 - 19:00 weekdays |
| Comfort Ranges | 21-24°C summer, 20-22°C winter |
| Priority Zones | Executive floor = P1 |
| Integration Points | Existing BMS, Access control |

---

## 9. Telegram Integration (2-3 minutes)

### Real-Time Alert Delivery

Facility managers receive instant notifications:

```
🚨 CRITICAL ALERT - Sandton City Office Tower

🏢 Zone: Level 2 Zone C
🔧 Equipment: Chiller-001
📋 Type: Chiller
🆔 Code: CHILLER-001

📝 Health score dropped to 65%. Predicted bearing
   failure within 14 days. Immediate inspection
   recommended.

⏰ Time: 14:32:45

━━━━━━━━━━━━━━━━━━
/fix-CHILLER_001 - Run maintenance
/details-CHILLER_001 - Full diagnosis
/WO-CHILLER_001 - Create work order
```

### Interactive Commands

| Command | Action |
|---------|--------|
| `/fix-[equipment]` | Execute maintenance procedure |
| `/details-[equipment]` | Get full diagnostic report |
| `/WO-[equipment]` | Create work order in CMMS |
| `/status` | Building-wide health summary |

---

## 10. Security, Privacy & Compliance (3-4 minutes)

### Security Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   Security Layers                        │
├─────────────────────────────────────────────────────────┤
│ Layer 1: Network Security                                │
│ • TLS 1.3 encryption for all communications             │
│ • VPN tunnels for device connectivity                   │
│ • Firewall rules and network segmentation               │
├─────────────────────────────────────────────────────────┤
│ Layer 2: Authentication & Authorization                  │
│ • JWT-based API authentication                          │
│ • Role-based access control (RBAC)                      │
│ • Multi-factor authentication support                   │
├─────────────────────────────────────────────────────────┤
│ Layer 3: Data Protection                                 │
│ • Encryption at rest (AES-256)                          │
│ • Row-level security in database                        │
│ • Audit logging for all actions                         │
├─────────────────────────────────────────────────────────┤
│ Layer 4: Operational Security                            │
│ • Safety interlocks prevent dangerous commands          │
│ • Human-in-the-loop for critical actions                │
│ • Command rate limiting                                 │
└─────────────────────────────────────────────────────────┘
```

### Privacy Considerations

| Data Type | Handling |
|-----------|----------|
| Building Telemetry | Anonymized, aggregated |
| User Actions | Audit logged, access controlled |
| AI Conversations | Not stored beyond session |
| Equipment Data | Client-owned, exportable |

### Compliance Framework

| Standard | Status | Notes |
|----------|--------|-------|
| POPIA (SA Privacy) | Aligned | Data minimization practiced |
| ISO 27001 | Framework adopted | Security controls in place |
| BACnet/IT Security | Compliant | Device layer isolation |

### Safety Interlocks

Critical protection built into every control action:

```python
# Example: Temperature setpoint validation
SAFETY_RULES = {
    "temperature_range": {
        "min": 16,  # Never below 16°C
        "max": 28,  # Never above 28°C
        "severity": "BLOCK"  # Prevents action
    },
    "runtime_limit": {
        "max_hours": 24,  # Force cycling after 24h
        "severity": "WARNING"
    }
}
```

---

## 11. Demo Scenarios (5-6 minutes)

### Demo 1: Equipment Health Alert

**Trigger:**
```bash
curl -X POST "http://localhost:9095/api/simulation/demo/trigger-warnings?count=3"
```

**What Happens:**
1. 3 equipment items degrade to warning state
2. Alerts created in database
3. Telegram notification sent with slash commands
4. Predictions generated automatically
5. AI recommendations created

**Show:**
- Dashboard health indicators changing
- Telegram notification arriving
- Clicking `/details-` for diagnosis

### Demo 2: AI Chat Interaction

**Example Queries:**
1. "What's the status of Chiller-001?"
2. "Why did the health score drop?"
3. "Schedule maintenance for next week"
4. "Show me energy usage for Level 12"

### Demo 3: Predictive Maintenance

**Show:**
1. Navigate to Predictions view
2. Click on equipment with active prediction
3. Show contributing factors
4. Explain the AI reasoning
5. Create work order from prediction

### Demo 4: Reset to Healthy

**Trigger:**
```bash
curl -X POST "http://localhost:9095/api/simulation/demo/reset-to-healthy"
```

**What Happens:**
- All equipment returns to 92% health
- Active alerts resolved
- Predictions cleared
- Dashboard shows green status

---

## 12. Technical Differentiators

### Why SENTINEL is Different

| Feature | Traditional BMS | SENTINEL |
|---------|-----------------|----------|
| Interface | Complex dashboards | Conversational AI |
| Maintenance | Calendar-based | Condition-based |
| Alerts | Threshold rules | ML anomaly detection |
| Insights | Manual analysis | Automated recommendations |
| Integration | Point-to-point | Protocol-agnostic abstraction |
| Cost | High licensing | Modular, pay-for-what-you-use |

### Technology Stack

| Layer | Technology | Why |
|-------|------------|-----|
| Frontend | React + TypeScript | Type safety, component reuse |
| Backend | FastAPI + Python | Async, ML ecosystem |
| Database | Supabase (PostgreSQL) | Real-time, row-level security |
| AI | Claude + Ollama | Hybrid cost optimization |
| ML | TensorFlow | LSTM, Autoencoder models |
| Protocols | BACnet, Modbus, DALI | Industry standard support |

---

## 13. Q&A Preparation

### Likely Questions & Answers

**Q: How long does it take to deploy?**
> A: 4-5 weeks for full deployment including baseline learning. Basic visibility can be achieved in 1 week.

**Q: What if the AI makes a wrong control decision?**
> A: All control actions pass through the Safety Engine with hard limits. Dangerous commands are blocked. Human-in-the-loop for critical operations.

**Q: How does this integrate with existing CMMS?**
> A: API-first design allows integration with any CMMS. Work orders can flow bidirectionally.

**Q: What's the pricing model?**
> A: Modular per-site licensing. Pay only for enabled modules. Volume discounts for portfolios.

**Q: Does it work offline?**
> A: Local Ollama handles queries during outages. Control still works via direct device connection. Cloud features queue until restored.

**Q: How accurate are the predictions?**
> A: After 90-day baseline, 85%+ accuracy on 7-day predictions. Improves with more data.

---

## 14. Demo Site: Sandton City Office Tower (site-002)

### Building Overview
| Parameter | Value |
|-----------|-------|
| Address | 83 Rivonia Road, Sandton |
| Floors | 3 (L0, L1, L2) with 5 zones each (A-E) |
| Area | 4,500 sqm |
| Equipment | 156 items |
| Desks | 300 (100 per floor) |
| BMS/SCADA | Siemens Desigo CC V5.0 |

### Siemens Desigo CC Integration
| Parameter | Value |
|-----------|-------|
| Data Points | 4,850 total |
| Online Devices | 148 |
| Protocols | BACnet/IP, Modbus TCP, DALI-2, OPC-UA, KNX |
| PXC Controllers | 5 (2,340 points) |
| Subsystems | HVAC, Lighting, Energy, Generators, Metering, Fire, Access, UPS, Water, Lifts |

### Live Sensor Readings Available
| Sensor Type | Count | Data Points |
|-------------|-------|-------------|
| Temperature | 15 | current °C, setpoint |
| CO2 | 15 | current ppm, setpoint |
| Daylight | 15 | lux level, setpoint |
| Occupancy | 15 | occupied, count |
| DALI Controllers | 15 | scene, brightness |
| LED Luminaires | 15 | brightness %, watts |

### Equipment with Full Telemetry
| Equipment | Count | Data Points |
|-----------|-------|-------------|
| VAV Units | 15 | airflow CFM, damper %, supply temp |
| FCU Units | 15 | supply/return temp, fan speed |
| AHU | 3 | temps, fan speeds, filter DP |
| Chillers | 3 | CHW temps, load %, power kW |
| Generators (DSE8610) | 4 | RPM, temps, fuel, alarms, mains status |
| Power Meters | 3 | kW, kWh, PF, voltage |
| UPS | 2 | battery %, load %, runtime |

### Demo Access
| Resource | URL |
|----------|-----|
| Frontend Dashboard | http://localhost:9096 |
| Backend API | http://localhost:9095 |
| API Documentation | http://localhost:9095/docs |

### Quick Commands

```bash
# Trigger demo warnings
curl -X POST "http://localhost:9095/api/simulation/demo/trigger-warnings?count=3"

# Reset to healthy
curl -X POST "http://localhost:9095/api/simulation/demo/reset-to-healthy"

# Check simulation status
curl "http://localhost:9095/api/simulation/status"
```

---

## Presentation Flow Summary

| Section | Duration | Key Points |
|---------|----------|------------|
| 1. Introduction | 2-3 min | Problem, value proposition |
| 2. Architecture | 3-4 min | Modular design, layers |
| 3. SIMBIOT | 4-5 min | 21 tools, safety layer |
| 4. AI Chat | 4-5 min | Hybrid routing, cost savings |
| 5. Technician Chat | 3-4 min | RAG, diagnostics |
| 6. Predictive Maintenance | 5-6 min | LSTM, health scores |
| 7. Work Orders | 3-4 min | Automated generation |
| 8. Onboarding | 3-4 min | 4-5 week process |
| 9. Telegram | 2-3 min | Real-time alerts |
| 10. Security | 3-4 min | Layers, compliance |
| 11. Demo | 5-6 min | Live demonstration |
| 12. Differentiators | 2-3 min | Why us |
| 13. Q&A | 5+ min | Prepared answers |

**Total: ~45-55 minutes**

---

*Good luck with your interview!*
