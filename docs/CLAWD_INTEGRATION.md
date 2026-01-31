# Clawd Telegram Bot - SENTINEL BMS Integration

This document describes the integration between Clawd (Telegram AI bot) and SENTINEL BMS Intelligence Platform.

## Overview

Clawd is a Telegram AI bot located at `/home/bederf/clawd` that integrates with SENTINEL for building management queries. Technicians can ask questions via Telegram and receive BMS-aware responses with actual HVAC readings, diagnostics, and device control capabilities.

**Demo Building:** Sandton - Full DALI lighting + HVAC + Energy Centre integration
- 300 desks (100 per floor, 20 per zone)
- 15 zones across 3 floors (L10, L11, L12)
- 145 equipment items in Supabase (HVAC, generators, energy centre, DALI lighting)

## Integration Modes

| Mode | Direction | Description |
|------|-----------|-------------|
| **Query Mode** | User → Clawd → SENTINEL | Technician asks questions, gets BMS data |
| **Alert Mode** | SENTINEL → Clawd → User | BMS sends alerts to FM team |
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
│                      Clawd Bot                               │
│                  (Telegram interface)                        │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│               clawd_ai_bridge.py                             │
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

## Clawd BMS Tools

Located in `/home/bederf/clawd/tools/`:

| Tool | Purpose | SENTINEL API Used |
|------|---------|-------------------|
| `bms_desk_diagnosis.py` | Desk comfort diagnosis | `/api/complaints/*` |
| `bms_control.py` | Device control | `/api/devices/*` |
| `bms_monitor.py` | Health monitoring alerts | `/api/alerts`, `/api/equipment` |
| `clawd_ai_bridge.py` | AI routing with BMS detection | Routes to appropriate tool |
| `tiered_ai_router.py` | Claude/Ollama fallback | N/A (AI routing) |

## Desk Comfort Diagnosis

### Pattern Detection

`clawd_ai_bridge.py` recognizes desk complaint patterns:

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

1. **Pattern Match**: `clawd_ai_bridge.is_desk_complaint()` detects desk query
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

Header `X-User-Id: clawdbot` identifies bot for audit logging.

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
python /home/bederf/clawd/tools/bms_desk_diagnosis.py 201 too_hot

# With building disambiguation
python /home/bederf/clawd/tools/bms_desk_diagnosis.py L12-21 too_cold Sandton

# List available desks
python /home/bederf/clawd/tools/bms_desk_diagnosis.py list Sandton
```

### Test Device Control

```bash
# List devices
python /home/bederf/clawd/tools/bms_control.py list

# Set temperature
python /home/bederf/clawd/tools/bms_control.py temp 001-gwc-fcu-001 22

# Check safety
python /home/bederf/clawd/tools/bms_control.py safety 001-gwc-chiller-001
```

### Test AI Bridge

```bash
python /home/bederf/clawd/tools/clawd_ai_bridge.py
```

## SENTINEL API Requirements

Clawd requires these SENTINEL endpoints:

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

### Clawd Side

In Clawd tools, the BMS API URL is configured:

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

All Clawd actions are logged in SENTINEL:

- User ID: `clawdbot`
- Source: Telegram user ID passed in metadata
- Actions logged: Device reads, control actions, complaints submitted

Query audit logs:
```
GET /api/audit/logs?user=clawdbot
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

## Alert Notifications (SENTINEL → Clawd)

When SENTINEL detects equipment faults, it sends alerts to FM team via Clawd Telegram.

### Alert Flow

```
Zone Temp Spike (25°C in Zone-L10-C)
    ↓
Zone Diagnostics Service
    ↓
Root Cause Analysis (FCU valve stuck at 15%)
    ↓
Alert Notifier → Clawd Bot → Telegram FM Group
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
🚨 CRITICAL ALERT - Sandton

Zone: Zone-L10-C
Equipment: FCU-L10-03
Type: fcu_valve_stuck

FCU valve stuck at 15% - insufficient chilled water flow

Equipment Status:
✅ AHU-L10-01: normal
⚠️ FCU-L10-03: warning
✅ VAV-L10-03: normal

Diagnosis: Valve actuator not responding
Fault Code: E04

Actions:
  1. Check valve actuator power supply (24VAC)
  2. Verify BMS control signal (0-10V)
  3. Replace actuator if unresponsive

Parts: Belimo LMV-D3 actuator
Est. Repair: 2h

Reply: /ack | /dispatch | /wo FCU-L10-03
```

### Alert Notifier Service

**Location**: `backend/app/services/clawd_integration/alert_notifier.py`

```python
from app.services.clawd_integration.alert_notifier import alert_notifier

# Send alert to FM team
alert_notifier.send_alert_sync({
    "id": alert_id,
    "building_name": "Sandton",
    "zone_name": "Zone-L10-C",
    "equipment_name": "FCU-L10-03",
    "equipment_code": "FCU-L10-03",
    "type": "fcu_valve_stuck",
    "severity": "critical",
    "message": "FCU valve stuck at 15%",
    "reading": 25.0,
    "setpoint": 21.0
})
```

**Environment Variables**:
```bash
CLAWD_BOT_TOKEN=<telegram-bot-token>
CLAWD_FM_CHAT_ID=<fm-group-chat-id>
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
3. **Email Technician** - Via Clawd Gmail skill
4. **Telegram Notification** - To assigned technician
5. **Update Alert Status** - Marked as "dispatched"

## ML Knowledge Capture

After technician repairs equipment, Clawd collects service data for ML training.

See `docs/04-features/41-ml-knowledge-capture-01.md` for complete details.

### Context-Aware Prompts

Because Clawd knows the original fault, it asks **targeted questions**:

```
Clawd: FCU-L10-03 repair complete - thanks!
       We detected: FCU valve stuck at 15% (E04)
       Did you confirm this was the issue?
       □ Yes, confirmed
       □ No, different issue

Tech: Yes, confirmed

Clawd: What was the root cause?
       □ Actuator motor failed
       □ Actuator jammed mechanically
       □ Control signal issue (0-10V)
       □ Power supply issue (24VAC)
```

### Comprehensive Response Handling

If technician provides all info at once:

```
Tech: Yes actuator motor failed, replaced Belimo LMV-D3, zone now 21.5C

Clawd: Got it! (fault confirmed, root cause: Actuator motor failed,
       part: Belimo LMV-D3, temp: 21.5°C)

       Just need a photo of the replacement part label
```

## Files Reference

### SENTINEL (this repo)
- `backend/app/api/complaints.py` - Complaint endpoints
- `backend/app/api/alerts.py` - Alert and dispatch endpoints
- `backend/app/services/complaint_handler.py` - Diagnosis logic
- `backend/app/services/zone_diagnostics.py` - Zone fault analysis
- `backend/app/services/clawd_integration/alert_notifier.py` - Alert notifications
- `backend/app/services/clawd_integration/work_order_notifier.py` - WO notifications
- `backend/app/services/ml_template_service.py` - ML data collection templates
- `backend/app/data/ml_data_templates.json` - Equipment-specific templates (19 types)
- `backend/app/data/buildings/sandton/zones.json` - Zone definitions

### Clawd (`/home/bederf/clawd`)
- `tools/bms_desk_diagnosis.py` - Desk diagnosis client
- `tools/bms_control.py` - Device control client
- `tools/clawd_ai_bridge.py` - Pattern detection & routing
- `tools/tiered_ai_router.py` - AI model routing
- Gmail skill - Email notifications to technicians
