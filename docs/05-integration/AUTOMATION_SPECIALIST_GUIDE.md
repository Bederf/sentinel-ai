# Automation Specialist Integration Guide

This guide provides automation specialists with the essential information needed to integrate external systems with SENTINEL BMS, focusing on device control, real-time data access, and workflow automation.

**Target Audience:** Automation engineers, systems integrators, and IoT specialists integrating SENTINEL with third-party platforms.

---

## Quick Start

### What You Can Control
SENTINEL provides programmatic control over 175+ devices across multiple protocols:
- **HVAC Systems:** Chillers, air handlers, VAV boxes, thermostats, split units
- **Lighting:** DALI lighting control with zone-based automation
- **Power Systems:** Generators, UPS, distribution boards, transformers
- **Fire & Security:** Fire detection, access control, CCTV monitoring
- **Energy Metering:** Real-time power consumption by building/zone

### Access Methods
1. **REST API** (HTTP/JSON) — Recommended for most integrations
2. **MQTT** (Real-time pub/sub) — For continuous data streaming
3. **BACnet/Modbus** (Native protocols) — Direct device communication
4. **Webhook Events** (Inbound) — Alert/event notifications to your system
5. **WebSocket** (Real-time) — Live equipment data streams

---

## Core Integration Modules

### 1. Device Abstraction Layer
**Purpose:** Protocol-agnostic device control across multiple standards.

**Supported Protocols:**
- **BACnet** — HVAC controllers (Siemens PXC4.E16-2), sensors, VAV boxes
- **Modbus TCP** — Industrial equipment, meters, generators
- **DALI** — Lighting control (Tridonic systems, dimming, color)
- **OPC-UA** — Enterprise systems, cross-platform integration
- **Mock Protocol** — Testing and simulation

**Key Features:**
- Single API regardless of underlying protocol
- Safety interlocks prevent invalid equipment states
- Automatic device discovery via network scanning
- Protocol-specific configuration management

**Integration Point:**
```
POST /api/devices/{id}/control
Content-Type: application/json

{
  "action": "set_temperature",
  "value": 22.5,
  "duration": 3600
}
```

### 2. Safety & Interlock System
**Purpose:** Guardrails preventing equipment damage or unsafe states.

**Rule Types:**
- **Temperature Range:** Prevent HVAC setpoints outside 16–28°C
- **Pressure Limit:** Protect chiller from dangerous pressures
- **Interlock:** Prevent incompatible devices from running simultaneously
- **Runtime Limit:** Prevent equipment overrun (e.g., compressor runtime < 10 min intervals)
- **Brightness Limit:** Prevent lighting levels outside comfortable range (20–100% per zone)

**Safety Levels:**
- **WARNING:** Device control allowed with log entry
- **BLOCK:** Device control prevented; requires override authorization
- **ALARM:** Critical violation; immediate alert + emergency shutdown

**Access Control:**
- `AUTHENTICATED` users: Read-only access (view equipment state)
- `OPERATOR` role: Control with safety interlocks enabled
- `ADMIN` role: Override all safety interlocks (use carefully)

**Safety Rules Location:** `backend/app/data/safety_rules.json`

### 3. Equipment Control API

#### Get Equipment Status
```bash
GET /api/devices/{id}
Authorization: Bearer {token}

Response:
{
  "id": "uuid-of-device",
  "code": "S002-CHILLER-B1-001",
  "name": "Basement Chiller Unit 1",
  "type": "CHILLER",
  "protocol": "BACnet",
  "state": "running",
  "health_score": 85,
  "current_value": 22.5,
  "unit": "°C",
  "last_update": "2024-02-12T10:15:30Z",
  "alerts": []
}
```

#### Control Device
```bash
POST /api/devices/{id}/control
Authorization: Bearer {token}
Content-Type: application/json

{
  "action": "set_temperature",
  "value": 24.0,
  "duration": 3600,
  "reason": "Occupancy increase detected"
}

Response:
{
  "success": true,
  "device_id": "uuid",
  "action": "set_temperature",
  "previous_value": 22.5,
  "new_value": 24.0,
  "executed_at": "2024-02-12T10:16:00Z"
}
```

#### Batch Control Multiple Devices
```bash
POST /api/devices/batch-control
Authorization: Bearer {token}
Content-Type: application/json

{
  "actions": [
    {"device_id": "uuid1", "action": "on", "reason": "Load shedding recovery"},
    {"device_id": "uuid2", "action": "set_temperature", "value": 20}
  ]
}

Response:
{
  "executed": 2,
  "failed": 0,
  "results": [...]
}
```

### 4. Real-Time Data Streaming

#### MQTT Topics
Subscribe to real-time equipment updates:

```
# All equipment updates
devices/+/state

# Specific building equipment
devices/S002/+/state

# Temperature sensors only
devices/S002/CHILLER-B1-001/temperature

# Alert stream
alerts/critical
alerts/warning
alerts/all
```

#### WebSocket Connection
```javascript
const ws = new WebSocket('wss://api.sentinel.local/ws');

ws.addEventListener('open', () => {
  ws.send(JSON.stringify({
    type: 'subscribe',
    channels: ['equipment_state', 'alerts']
  }));
});

ws.addEventListener('message', (event) => {
  const data = JSON.parse(event.data);
  console.log('Equipment update:', data);
  // {
  //   equipment_id: "uuid",
  //   code: "S002-CHILLER-B1-001",
  //   state: "running",
  //   value: 22.5,
  //   timestamp: "2024-02-12T10:15:30Z"
  // }
});
```

### 5. Work Order & Maintenance Automation

#### Create Work Order
```bash
POST /api/work-orders/supabase
Authorization: Bearer {token}
Content-Type: application/json

{
  "equipment_code": "S002-CHILLER-B1-001",
  "issue_description": "Temperature sensor reading high variance",
  "severity": "warning",
  "requested_by": "external-system",
  "priority": "high"
}

Response:
{
  "id": "wo-uuid",
  "code": "WO-2024-0125",
  "equipment": {...},
  "assigned_technician": {
    "id": "tech-uuid",
    "name": "John Smith",
    "specialty": "hvac",
    "email": "john@facilities.local",
    "telegram_id": "123456789"
  },
  "status": "assigned",
  "created_at": "2024-02-12T10:16:00Z"
}
```

#### Query Work Order Status
```bash
GET /api/work-orders/supabase/{code}
Authorization: Bearer {token}

Response:
{
  "id": "wo-uuid",
  "code": "WO-2024-0125",
  "equipment": {...},
  "status": "in_progress",
  "assigned_to": "John Smith",
  "started_at": "2024-02-12T10:30:00Z",
  "notes": "Replacing temperature sensor, testing calibration"
}
```

#### Submit Service Feedback
```bash
POST /api/service-feedback/supabase
Authorization: Bearer {token}
Content-Type: application/json

{
  "work_order_id": "wo-uuid",
  "equipment_id": "equipment-uuid",
  "feedback_type": "hvac_service",
  "issue_resolution": "replaced_compressor",
  "health_impact": "positive",  # "positive", "neutral", "negative", "critical"
  "notes": "New compressor installed, tested at load, all OK"
}

Response:
{
  "id": "feedback-uuid",
  "work_order": "WO-2024-0125",
  "equipment": {...},
  "health_score": 87,
  "impact_applied": true
}
```

### 6. Alert & Event System

#### Subscribe to Equipment Alerts
```bash
GET /api/alerts?equipment_id={uuid}&limit=50&severity=critical
Authorization: Bearer {token}

Response:
{
  "alerts": [
    {
      "id": "alert-uuid",
      "equipment": {...},
      "severity": "critical",
      "message": "Chiller compressor high discharge pressure",
      "detected_at": "2024-02-12T10:15:00Z",
      "status": "active"
    }
  ]
}
```

#### Alert Webhook (Incoming)
Configure your system to receive alerts:

```bash
# SENTINEL will POST to your webhook when alerts are created
POST https://your-system.com/webhooks/bms-alerts
Content-Type: application/json

{
  "event": "alert_created",
  "alert_id": "alert-uuid",
  "equipment": {
    "id": "uuid",
    "code": "S002-CHILLER-B1-001",
    "name": "Basement Chiller"
  },
  "severity": "critical",
  "message": "Compressor discharge pressure exceeded safe limit",
  "timestamp": "2024-02-12T10:15:00Z",
  "health_score_before": 85,
  "health_score_after": 45
}
```

### 7. Predictive Maintenance Integration

#### Get Equipment Health & Predictions
```bash
GET /api/predictions/equipment/{equipment_id}
Authorization: Bearer {token}

Response:
{
  "equipment_id": "uuid",
  "equipment_code": "S002-CHILLER-B1-001",
  "health_score": 45,
  "trend": "declining",
  "predictions": [
    {
      "id": "pred-uuid",
      "type": "maintenance_required",
      "confidence": 0.87,
      "severity": "critical",
      "description": "Chiller approaching compressor failure - recommend preventive replacement",
      "recommended_action": "Schedule major maintenance within 7 days",
      "impact_if_ignored": "Potential complete failure leading to 24–48 hour outage"
    }
  ]
}
```

#### Get Recommendations by Site
```bash
GET /api/recommendations/{site_id}
Authorization: Bearer {token}

Response:
{
  "site": "S002",
  "generated_at": "2024-02-12T10:15:00Z",
  "recommendations": [
    {
      "id": "rec-uuid",
      "equipment": {...},
      "category": "maintenance",
      "priority": "high",
      "description": "Replace air filter - 2 months overdue",
      "estimated_cost": "$150",
      "risk_reduction": "Improves efficiency by 15%"
    }
  ]
}
```

---

## Equipment Hierarchy & Naming

### Two-Tier Naming System

**Tier 1: Zone Equipment (Offices)**
```
Pattern: {site}-{type}-{zone_id}
Examples:
  S002-VAV-101    → Level 1, Zone B (VAV serving offices)
  S002-FCU-200    → Level 2, Zone A (Fan coil unit)
  S002-DALI-104   → Level 1, Zone E (Lighting control)
```

**Tier 2: Plant Equipment (Infrastructure)**
```
Pattern: {site}-{type}-{location}-{sequence}
Examples:
  S002-CHILLER-B1-001  → Basement 1, Chiller Unit 1
  S002-AHU-R-001       → Roof, Air Handler Unit 1
  S002-GEN-G-001       → Ground Plant, Generator Unit 1
  S002-PUMP-B1-CHW1    → Basement 1, Chilled Water Pump
```

### Equipment Type to Technician Specialty
```
HVAC Specialists:
  CHILLER, AHU, FCU, VAV, SPLIT, CT (Cooling Tower), CRAC, PUMP, BOILER

Electrical Specialists:
  GEN (Generator), TX (Transformer), UPS, ATS, MSB, MTR (Meter),
  PFC, FDR, MV, DB (Distribution Board), KEF (Kitchen Exhaust), JACE

Lighting (DALI) Specialists:
  DALI, LUM (Luminaire)

Fire Safety:
  FIRE

Security:
  ACC (Access Control), CCTV
```

---

## Common Integration Scenarios

### Scenario 1: Load Shedding Response
When utility load shedding is announced, automatically adjust building load:

```python
# 1. Receive load shedding event from external system
load_shedding_stage = 6  # Stage 6 = 6 x 100MW cuts

# 2. Query current state
GET /api/sites/S002/energy-profile

# 3. Execute coordinated shutdown
POST /api/devices/batch-control
{
  "actions": [
    {"device_id": "gen-uuid", "action": "on", "reason": "Load shedding stage 6"},
    {"device_id": "ups-uuid", "action": "eco_mode", "reason": "Power conservation"},
    {"device_id": "hvac-uuid", "action": "setback", "value": 26, "reason": "Load reduction"}
  ]
}

# 4. Monitor real-time response
GET /api/sites/S002/current-load
# Returns: {"total": 450, "shed": 120, "efficiency": "87%"}

# 5. Restore when stage ends
POST /api/devices/batch-control
{
  "actions": [
    {"device_id": "gen-uuid", "action": "standby"},
    {"device_id": "ups-uuid", "action": "normal_mode"},
    {"device_id": "hvac-uuid", "action": "normal", "value": 22}
  ]
}
```

### Scenario 2: Occupancy-Based HVAC Adjustment
Integrate building occupancy detection with HVAC control:

```bash
# Receive occupancy update from your occupancy system
POST /api/integrations/occupancy-webhook
{
  "zone": "Zone-101",
  "occupancy_level": 85,
  "trend": "increasing"
}

# SENTINEL responds by:
# 1. Query zone equipment: GET /api/equipment?zone=Zone-101
# 2. Adjust VAV setpoint: POST /api/devices/vav-uuid/control
#    {"action": "set_temperature", "value": 21.5}
# 3. Verify health: GET /api/predictions/equipment/{equipment_id}
# 4. If needed, create work order for maintenance
```

### Scenario 3: Equipment Failure Detection → Automatic Notification
When critical equipment fails, immediately notify external systems:

```bash
# SENTINEL detects chiller failure
POST https://your-system.com/webhooks/equipment-failure
{
  "event": "critical_alert",
  "equipment": "S002-CHILLER-B1-001",
  "failure_type": "compressor_lockout",
  "severity": "critical",
  "action_taken": "switched to backup cooling tower",
  "work_order_created": "WO-2024-0425",
  "assigned_technician": "John Smith",
  "estimated_repair_time": "4-6 hours"
}

# Your system can then:
# 1. Notify facilities manager via email/SMS
# 2. Trigger backup systems
# 3. Update your CMMS with work order reference
# 4. Schedule customer notification
```

### Scenario 4: Predictive Maintenance Scheduling
Integrate SENTINEL predictions with your maintenance scheduling system:

```bash
# Daily sync (10:00 AM)
GET /api/predictions/site/S002

# For each prediction with confidence > 0.8:
# 1. Check your scheduling system for technician availability
# 2. Post to: POST /api/work-orders/supabase
#    with scheduled date from your system
# 3. Track work order status via webhook
# 4. When complete, POST /api/service-feedback/supabase
#    to update SENTINEL health scores
```

---

## Authentication & Authorization

### API Authentication
```bash
# 1. Obtain token (one-time setup)
POST /api/auth/token
{
  "email": "integration@wardew.com",
  "password": "secure-password"
}

Response: {"access_token": "eyJhbGc..."}

# 2. Use token in requests
GET /api/devices
Authorization: Bearer eyJhbGc...
```

### Role-Based Access
```
Role Hierarchy: ADMIN > OPERATOR > AUTHENTICATED > PUBLIC

Public (no auth):
  - /health
  - /docs
  - /openapi.json

Authenticated (read-only):
  - GET /api/equipment
  - GET /api/devices
  - GET /api/alerts
  - GET /api/predictions

Operator (control operations):
  - POST /api/devices/{id}/control
  - POST /api/work-orders
  - POST /api/device-overrides

Admin (configuration):
  - POST /api/integrations/configure
  - POST /api/safety-rules/update
  - DELETE /api/audit-logs/purge
```

---

## Troubleshooting Common Issues

### Issue: Device Control Fails with 403 Forbidden
**Cause:** Your integration account doesn't have OPERATOR role.
**Solution:**
```bash
# Verify current user role
GET /api/auth/me
# Response: {"role": "AUTHENTICATED"}

# Request admin to promote account to OPERATOR role
# Then retry control operation
```

### Issue: Work Order Not Assigned to Technician
**Cause:** Equipment type not recognized, specialty mapping failed.
**Solution:**
```bash
# Check equipment type
GET /api/equipment/{equipment_id}
# Verify "type" field matches mapping (HVAC, electrical, fire, etc.)

# If type is missing or wrong, update it
PUT /api/equipment/{equipment_id}
{"type": "HVAC"}
```

### Issue: Real-Time Data Not Updating
**Cause:** Redis cache or connection issue.
**Solution:**
```bash
# Check cache status
GET /api/cache/stats
# If Redis offline, system falls back to poll-based updates

# Force cache refresh
POST /api/cache/flush
```

### Issue: Alert Webhook Not Triggering
**Cause:** Webhook URL not configured or unreachable.
**Solution:**
```bash
# Verify webhook configuration
GET /api/integrations/webhooks

# Test webhook manually
POST /api/integrations/webhooks/test
{"webhook_id": "webhook-uuid"}

# Configure webhook URL
PUT /api/integrations/webhooks/{webhook_id}
{"url": "https://your-system.com/webhooks/alerts"}
```

---

## Performance & Rate Limiting

### API Rate Limits
- **Authenticated Users:** 1,000 requests/hour
- **Service Accounts:** 10,000 requests/hour
- **Batch Operations:** 100 devices max per request

### Recommended Polling Intervals
```
Equipment State:        30 seconds
Alerts:                 15 seconds
Predictions:            5 minutes
Work Orders:            1 minute
Health Scores:          10 minutes
Recommendations:        10 minutes
```

### Batch Optimization
Instead of:
```bash
# ❌ 100 individual requests
GET /api/devices/uuid-1
GET /api/devices/uuid-2
...
```

Use:
```bash
# ✅ 1 batch request
POST /api/devices/batch
{"device_ids": ["uuid-1", "uuid-2", ...]}
```

---

## Next Steps

1. **Request API Credentials**
   - Email: integration@sentinel.local
   - Provide: Integration name, contact email, use case description

2. **Set Up Authentication**
   - Obtain API token via `/api/auth/token`
   - Store securely in your system (use vault/secrets manager)

3. **Configure Webhooks** (if needed)
   - Register inbound webhook URL
   - Test with `/api/integrations/webhooks/test`

4. **Test Integration**
   - Start with read-only queries (`GET /api/equipment`, `GET /api/alerts`)
   - Progress to control operations (`POST /api/devices/{id}/control`)
   - Implement full workflow (alert → work order → feedback)

5. **Monitor & Optimize**
   - Track API response times
   - Use batch operations for high-frequency data
   - Set appropriate polling intervals

---

## Support & Documentation

- **API Documentation:** http://localhost:9095/docs (Swagger UI)
- **Architecture Guides:** See `docs/02-architecture/`
- **Protocol Guides:**
  - `bacnet-object-reference.md` (BACnet device objects)
  - `dali-hvac-integration.md` (DALI lighting control)
  - `tridium-niagara-integration.md` (Niagara framework)
- **Integration Examples:** See `backend/app/api/registrars/integrations.py`
- **Support Email:** integration-support@sentinel.local

---

## Appendix: Equipment Control Reference

### HVAC Control Actions
```json
{"action": "set_temperature", "value": 22.5}
{"action": "set_humidity", "value": 45}
{"action": "fan_speed", "value": "medium"}
{"action": "mode", "value": "cooling"}  // heating, cooling, auto
{"action": "on"}
{"action": "off"}
{"action": "standby"}
```

### Lighting Control Actions
```json
{"action": "on"}
{"action": "off"}
{"action": "dim", "value": 75}  // 0-100%
{"action": "color", "value": "white"}  // white, warm, cool
{"action": "scene", "value": "meeting"}  // scene name
```

### Generator Control Actions
```json
{"action": "on"}
{"action": "off"}
{"action": "standby"}
{"action": "test"}
{"action": "set_load", "value": 50}  // 0-100%
```

### UPS Control Actions
```json
{"action": "on"}
{"action": "off"}
{"action": "eco_mode", "value": true}
{"action": "normal_mode"}
{"action": "set_battery_threshold", "value": 30}  // %
```
