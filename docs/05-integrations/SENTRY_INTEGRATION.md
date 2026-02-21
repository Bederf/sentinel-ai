# Sentry Telegram Bot - SENTINEL BMS Integration

This document describes the integration between Sentry (Telegram AI bot) and SENTINEL BMS Intelligence Platform.

## Overview

Sentry is a Telegram AI bot located at `$SENTRY_HOME` that integrates with SENTINEL for building management queries. Technicians can ask questions via Telegram and receive BMS-aware responses with actual HVAC readings, diagnostics, and device control capabilities.

**Demo Building:** Sandton - Full DALI lighting + HVAC + Energy Centre integration
- 300 desks (100 per floor, 20 per zone)
- 15 zones across 3 floors (L10, L11, L12)
- 145 equipment items in Supabase (HVAC, generators, energy centre, DALI lighting)

## Integration Modes

| Mode | Direction | Description |
|------|-----------|-------------|
| **Query Mode** | User → Sentry → SENTINEL | Technician asks questions, gets BMS data |
| **Alert Mode** | SENTINEL → Sentry → User | BMS sends alerts to FM team |
| **Work Order Mode** | Bidirectional | Alert → Dispatch → Data Collection |

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Telegram User                             │
│                  (Technician in field)                       │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      Sentry Bot                               │
│                  (Telegram interface)                        │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│               sentry_ai_bridge.py                             │
│         Pattern matching & intelligent routing               │
└─────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┴───────────────┐
              ▼                               ▼
┌──────────────────────────┐    ┌──────────────────────────┐
│   Desk Complaint?        │    │   General Query?         │
│   ▼ YES                  │    │   ▼                      │
│   bms_desk_diagnosis.py  │    │   tiered_ai_router.py    │
└──────────────────────────┘    └──────────────────────────┘
              │                               │
              ▼                               ▼
┌──────────────────────────┐    ┌──────────────────────────┐
│   SENTINEL API           │    │   Ollama / Claude        │
│   localhost:9095         │    │   (Hybrid AI routing)    │
└──────────────────────────┘    └──────────────────────────┘
```

## Sentry BMS Tools

Located in `$SENTRY_HOME/tools/`:

| Tool | Purpose | SENTINEL API Used |
|------|---------|-------------------|
| `bms_desk_diagnosis.py` | Desk comfort diagnosis | `/api/complaints/*` |
| `bms_control.py` | Device control | `/api/devices/*` |
| `bms_monitor.py` | Health monitoring alerts | `/api/alerts`, `/api/equipment` |
| `sentry_ai_bridge.py` | AI routing with BMS detection | Routes to appropriate tool |
| `tiered_ai_router.py` | Claude/Ollama fallback | N/A (AI routing) |

## Desk Comfort Diagnosis

### Pattern Detection

`sentry_ai_bridge.py` recognizes desk complaint patterns:

```python
desk_complaint_patterns = [
    r"desk\s+(\d+|[A-Z]\d+-\d+)\s+.*(hot|cold|stuffy|draft)",
    r"user at desk\s+(\d+|[A-Z]\d+-\d+)\s+says",
    r"complaint.*desk\s+(\d+|[A-Z]\d+-\d+)",
    r"(too hot|too cold|stuffy|drafty).*desk\s+(\d+|[A-Z]\d+-\d+)",
]
```

### Example Queries

| Query | Detected Pattern |
|-------|------------------|
| "User at desk 201 says it's too hot" | desk_id=201, complaint=too_hot |
| "Desk L12-21 is too cold at Sandton" | desk_id=L12-21, complaint=too_cold |
| "Complaint from desk 203 about stuffy air" | desk_id=203, complaint=stuffy |

### Diagnosis Flow

1. **Pattern Match**: `sentry_ai_bridge.is_desk_complaint()` detects desk query
2. **Route to BMS**: Calls `bms_desk_diagnosis.diagnose_and_format()`
3. **SENTINEL API**: `POST /api/complaints/submit?desk_id=X&complaint_type=Y`
4. **Rich Response**: Returns with HVAC readings, root cause, actions

### Response Format

```
Desk 201 - Too Hot

Building: Sandton
Floor: Level 12
Zone: Zone-L12-N

HVAC Readings:
  Temperature: 24.5°C
  Setpoint: 22.0°C
  Status: +2.5°C above setpoint
  FCU: FCU-L12-N-01 - RUNNING

Desk factors: Near window

Probable Causes:
  • Zone is 2.5°C above setpoint
  • Solar heat gain through nearby window (afternoon)

Actions:
  1. Check if blinds are deployed
  2. Check FCU-L12-N-01 cooling capacity
  3. Verify VAV-L12-N damper position

⚠️ On-site dispatch recommended

Confidence: medium
Source: sentinel_diagnosis
```

## Device Control

### `bms_control.py` Commands

```bash
# List controllable devices
bms_control.py list

# Get device info
bms_control.py info <device_name/id>

# Read point value
bms_control.py read <device> <point>

# Set temperature
bms_control.py temp <device> <temperature>

# Turn device on/off
bms_control.py on <device>
bms_control.py off <device>

# Set any point
bms_control.py set <device> <point> <value>

# Check safety status
bms_control.py safety <device>
```

### API Endpoints Used

| Command | Endpoint | Method |
|---------|----------|--------|
| list | `/api/devices` | GET |
| info | `/api/devices/{id}/points` | GET |
| read | `/api/devices/{id}/points/{point}` | GET |
| temp/on/off/set | `/api/devices/{id}/control` | POST |
| safety | `/api/devices/{id}/safety-status` | GET |

### Control Request Format

```python
{
    'point': 'cooling_setpoint',
    'value': 22.0,
    'priority': 8
}
```

Header `X-User-Id: sentrybot` identifies bot for audit logging.

## Demo Desks

Pre-configured desks for testing at Sandton:

| Desk ID | Context | Expected Diagnosis |
|---------|---------|-------------------|
| 201 | `near_window: true` | Solar heat gain (afternoon) |
| 202 | `near_window: true` | Solar heat gain (afternoon) |
| 203 | `near_diffuser: "D-L12-03"` | Draft/overcooling |
| 204 | `near_printer: true` | Local heat source |

## Testing

### Test Desk Diagnosis

```bash
# Direct API test
python $SENTRY_HOME/tools/bms_desk_diagnosis.py 201 too_hot

# With building disambiguation
python $SENTRY_HOME/tools/bms_desk_diagnosis.py L12-21 too_cold Sandton

# List available desks
python $SENTRY_HOME/tools/bms_desk_diagnosis.py list Sandton
```

### Test Device Control

```bash
# List devices
python $SENTRY_HOME/tools/bms_control.py list

# Set temperature
python $SENTRY_HOME/tools/bms_control.py temp S001-FCU-L0-A 22

# Check safety
python $SENTRY_HOME/tools/bms_control.py safety S001-CHILLER-B1-001
```

### Test AI Bridge

```bash
python $SENTRY_HOME/tools/sentry_ai_bridge.py
```

## SENTINEL API Requirements

Sentry requires these SENTINEL endpoints:

### Complaints API (Desk Diagnosis)
```
POST /api/complaints/submit?desk_id=X&complaint_type=Y
GET  /api/complaints/desk/{desk_id}
GET  /api/complaints/zone/{zone_id}
GET  /api/complaints/desks
```

### Devices API (Control)
```
GET  /api/devices
GET  /api/devices/{id}/points
GET  /api/devices/{id}/points/{point}
POST /api/devices/{id}/control
GET  /api/devices/{id}/safety-status
```

## Configuration

### Sentry Side

In Sentry tools, the BMS API URL is configured:

```python
BMS_API_URL = "http://localhost:9095"  # SENTINEL BMS Backend
```

### SENTINEL Side

Ensure backend is running on port 9095:

```bash
cd /opt/bms-intelligence/backend
source venv/bin/activate
uvicorn app.main:app --reload --port 9095
```

## Hybrid AI Routing

When a query isn't a desk complaint, `tiered_ai_router.py` routes:

| Tier | Model | Use Cases | Cost |
|------|-------|-----------|------|
| 1 | Ollama (llama3.2:1b) | Simple lookups, status | FREE |
| 2 | Claude | Complex reasoning, control | PAID |

Safety-critical operations always route to Claude.

## Audit Trail

All Sentry actions are logged in SENTINEL:

- User ID: `sentrybot`
- Source: Telegram user ID passed in metadata
- Actions logged: Device reads, control actions, complaints submitted

Query audit logs:
```
GET /api/audit/logs?user=sentrybot
```

## Troubleshooting

### Desk Not Found

```
Could not find desk 201
Please verify the desk ID or specify the building
```

**Solution**: Check desk exists in `backend/app/data/desks.json` or specify building name.

### Connection Refused

```
error: [Errno 111] Connection refused
```

**Solution**: Ensure SENTINEL backend is running on port 9095.

### Safety Block

```
Error: Control action blocked by safety rule
```

**Solution**: Check safety rules - temperature must be 16-28°C.

## Alert Notifications (SENTINEL → Sentry)

When SENTINEL detects equipment faults, it sends alerts to FM team via Sentry Telegram.

### Alert Flow

```
Zone Temp Spike (25°C in Zone-L10-C)
    ↓
Zone Diagnostics Service
    ↓
Root Cause Analysis (FCU valve stuck at 15%)
    ↓
Alert Notifier → Sentry Bot → Telegram FM Group
    ↓
FM replies: /dispatch
    ↓
Work Order Created with Diagnostic Context
    ↓
Technician Email (Gmail API)
    ↓
Technician repairs → replies "done"
    ↓
Context-Aware Data Collection
```

### Alert Notification Format

```
⚠️ WARNING ALERT - Sandton City Office Tower

Zone: Level 10 Zone C
Equipment: FCU-L10-03
Type: FCU
Code: FCU-L10-03

FCU valve stuck at 15% - insufficient chilled water flow

Time: 14:32:15

/WO_FCU_L10_03 - Create Work Order
/note_FCU_L10_03 - Log note only
```

**Important: Telegram Command Format**

Telegram bot commands can only contain letters, numbers, and underscores. Commands end at hyphens or spaces. Therefore:

- Equipment code `FCU-L10-03` becomes command `/WO_FCU_L10_03`
- Sentrybot converts underscores back to dashes when looking up equipment
- The actual equipment code is displayed in the `Code:` field for reference

### Alert Notifier Service

**Location**: `backend/app/services/sentry_integration/alert_notifier.py`

The alert notifier sends Telegram messages via the `sentrybot` CLI tool.

```python
from app.services.sentry_integration.alert_notifier import alert_notifier

# Send alert to FM team
alert_notifier.send_alert_sync({
    "id": alert_id,
    "building_name": "Sandton City Office Tower",
    "zone_name": "Level 10 Zone C",
    "equipment_name": "FCU-L10-03",
    "equipment_code": "FCU-L10-03",  # Displayed as-is, converted to underscores for commands
    "equipment_type": "fcu",
    "severity": "warning",
    "message": "Health score dropped from 92% to 65%. Maintenance recommended."
})
```

The notifier automatically:
1. Formats the equipment code with underscores for clickable Telegram commands
2. Includes the original code in the message body for reference
3. Sends via `sentrybot message send` CLI

**Configuration**:
- FM Chat ID: Set in `alert_notifier.py` or via `SENTRY_FM_CHAT_ID` env var
- Sentrybot must be installed and in PATH

## Work Order Commands

### `/WO_<equipment_code>` - Create Work Order

When FM clicks the `/WO_` command in a Telegram alert, Sentrybot:

1. Extracts equipment code (converts underscores back to dashes)
2. Looks up equipment from SENTINEL API
3. Creates a Concept Evolution-compatible work order
4. Returns confirmation with job card number

**Handler**: `sentry_ai_bridge.py:handle_wo_command()`

**Example**:
```
User clicks: /WO_FCU_L12_03

Sentrybot response:
Work order created:

JC-2026-0202143256 🟡

• Site: Sandton City (SC-JHB-001)
• Equipment: Fan Coil Unit Zone-L12-C
• Code: FCU-L12-03
• Priority: P3 - Medium (24hr SLA)
• Issue: Health degradation - maintenance required

Reply /email to send to maintenance team.
```

### `/note_<equipment_code>` - Log Note Only

For alerts that don't require a work order (acknowledged but no action needed).

**Handler**: `sentry_ai_bridge.py:handle_note_command()`

**Example**:
```
User clicks: /note_FCU_L12_03

Sentrybot response:
📝 Note logged for FCU-L12-03

Logged by: @username
Time: 2026-02-02 14:35

Alert acknowledged - no work order created.
Equipment will continue to be monitored.
```

## Zone Diagnostics

Root cause analysis for zone comfort issues.

**Location**: `backend/app/services/zone_diagnostics.py`

### Fault Types

| Fault Type | Description | Typical Cause |
|------------|-------------|---------------|
| `fcu_valve_stuck` | Valve not responding | Actuator failure |
| `fcu_fan_failure` | No airflow | Motor/capacitor |
| `vav_damper_stuck` | Damper not moving | Actuator/linkage |
| `ahu_supply_high` | Supply air too warm | Chiller/coil issue |
| `sensor_fault` | Erratic readings | Failed sensor |
| `high_occupancy` | Minor deviation | Heat load |

### Diagnostic Result

```python
@dataclass
class DiagnosticResult:
    zone_id: str
    current_temp: float
    setpoint: float
    deviation: float
    fault_type: FaultType
    faulty_equipment: str
    fault_code: Optional[str]
    fault_description: str
    equipment_status: Dict[str, Dict]
    recommended_actions: List[str]
    parts_required: List[str]
    estimated_repair_hours: float
    severity: str  # critical, warning, info
```

## Work Order Dispatch

When FM replies `/dispatch` to an alert, SENTINEL creates a work order with full diagnostic context.

### Dispatch API

**Endpoint**: `POST /api/alerts/{alert_id}/dispatch`

```python
{
    "technician_id": "@jsmith",
    "technician_name": "John Smith",
    "service_type": "breakdown",
    "diagnostic_context": {
        "fault_type": "fcu_valve_stuck",
        "fault_code": "E04",
        "fault_description": "FCU valve stuck at 15%",
        "original_reading": 25.0,
        "setpoint": 21.0,
        "deviation": 4.0,
        "faulty_equipment": "FCU-L10-03",
        "zone_id": "Zone-L10-C",
        "recommended_actions": [
            "Check valve actuator power supply (24VAC)",
            "Verify BMS control signal (0-10V)",
            "Replace actuator if unresponsive"
        ],
        "parts_required": ["Belimo LMV-D3 actuator"],
        "severity": "critical"
    }
}
```

### Dispatch Flow

1. **Create Work Order** - Linked to alert
2. **Create Service Record** - With diagnostic context
3. **Email Technician** - Via Sentry Gmail skill
4. **Telegram Notification** - To assigned technician
5. **Update Alert Status** - Marked as "dispatched"

## ML Knowledge Capture

After technician repairs equipment, Sentry collects service data for ML training.

See `docs/04-features/41-ml-knowledge-capture-01.md` for complete details.

### Context-Aware Prompts

Because Sentry knows the original fault, it asks **targeted questions**:

```
Sentry: FCU-L10-03 repair complete - thanks!
       We detected: FCU valve stuck at 15% (E04)
       Did you confirm this was the issue?
       □ Yes, confirmed
       □ No, different issue

Tech: Yes, confirmed

Sentry: What was the root cause?
       □ Actuator motor failed
       □ Actuator jammed mechanically
       □ Control signal issue (0-10V)
       □ Power supply issue (24VAC)
```

### Comprehensive Response Handling

If technician provides all info at once:

```
Tech: Yes actuator motor failed, replaced Belimo LMV-D3, zone now 21.5C

Sentry: Got it! (fault confirmed, root cause: Actuator motor failed,
       part: Belimo LMV-D3, temp: 21.5°C)

       Just need a photo of the replacement part label
```

## Service Sheet OCR (3-Stage Pipeline)

When technicians upload service sheet photos, SENTINEL processes them through a 3-stage OCR pipeline.

See `docs/04-features/41-ml-knowledge-capture-02.md` for complete details.

### OCR Architecture

```
Technician sends service sheet photo
    ↓
┌─────────────────────────────────────┐
│  Stage 1: Claude Vision OCR         │
│  - Extract text and structured data │
│  - Per-field confidence scores      │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│  Stage 2: Template Validation       │
│  - Validate against equipment type  │
│  - Type coercion and range checks   │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│  Stage 3: AI Enhancement            │
│  - Fill gaps, trigger corrections   │
│  - Track human-verified corrections │
└─────────────────────────────────────┘
    ↓
Store in service_readings table
```

### Sentry OCR Endpoints

```bash
# Upload service sheet photo
POST /api/sentry/ocr/process-service-sheet
{
    "service_record_id": "SR-2026-ABC123",
    "equipment_id": "gen-001",
    "service_type": "minor",
    "telegram_user_id": "@jsmith",
    "image_data": "base64...",
    "media_type": "image/jpeg"
}

# Submit correction
POST /api/sentry/ocr/correction
{
    "service_record_id": "SR-2026-ABC123",
    "correction": "24.5"
}

# Check OCR status
GET /api/sentry/ocr/status/{service_record_id}
```

### Correction Flow

If OCR has low confidence or validation errors, Sentry prompts for corrections:

```
Sentry: ⚠️ Battery voltage not detected on service sheet.
       Please type the value:

Tech: 24.5

Sentry: ✅ Got it! (battery_voltage: 24.5V)
       Next: Hour meter reading?

Tech: 1247

Sentry: ✅ Service sheet data complete!
       - Battery voltage: 24.5V
       - Hour meter: 1247h
       - Oil pressure: 45 psi (from OCR)
```

### Correction Tracking

All corrections tracked for ML data quality:
```json
{
    "reading_name": "battery_voltage",
    "reading_value": "24.5",
    "ocr_confidence": 0.0,
    "was_corrected": true,
    "corrected_from": null,
    "corrected_by": "@jsmith"
}
```

## Files Reference

### SENTINEL (this repo)
- `backend/app/api/complaints.py` - Complaint endpoints
- `backend/app/api/alerts.py` - Alert and dispatch endpoints
- `backend/app/api/ocr.py` - OCR processing endpoints
- `backend/app/api/sentry_webhooks.py` - Sentry webhook endpoints (WO + OCR)
- `backend/app/services/complaint_handler.py` - Diagnosis logic
- `backend/app/services/zone_diagnostics.py` - Zone fault analysis
- `backend/app/services/ocr_service.py` - 3-stage OCR pipeline
- `backend/app/services/sentry_integration/alert_notifier.py` - Alert notifications
- `backend/app/services/sentry_integration/work_order_notifier.py` - WO notifications
- `backend/app/services/sentry_integration/ocr_correction_handler.py` - OCR corrections
- `backend/app/services/ml_template_service.py` - ML data collection templates
- `backend/app/data/ml_data_templates.json` - Equipment-specific templates (23 types)
- `backend/app/data/buildings/sandton/zones.json` - Zone definitions

### Sentry (`$SENTRY_HOME`)
- `tools/bms_desk_diagnosis.py` - Desk diagnosis client
- `tools/bms_control.py` - Device control client
- `tools/sentry_ai_bridge.py` - Pattern detection & routing
- `tools/tiered_ai_router.py` - AI model routing
- Gmail skill - Email notifications to technicians
