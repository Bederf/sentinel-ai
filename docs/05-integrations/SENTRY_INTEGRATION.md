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
| **Document Intake Mode** | User → Sentry → SENTINEL | Technician sends a photo, bot captures metadata, raw file is saved to Concept |

See [sentry-telegram-document-intake.md](/opt/bms-intelligence/docs/05-integrations/sentry-telegram-document-intake.md) for the guided raw-document upload flow.

## POPIA Runtime Controls

Sentry/Telegram ingress is now consent-gated before personal information is processed.

### Consent gate behavior

Applied at:

- `POST /api/sentry/work-order/response`
- `POST /api/sentry/ocr/process-service-sheet`
- Telegram complaint/approval flows in `work_order_notifier.py`

Runtime outcomes:

- No active `pi_processing` consent: request is blocked and consent prompt is returned.
- Consent withdrawn (`STOP` patterns): processing is halted immediately.
- Consent granted (`YES` patterns): consent is recorded and user is asked to resend the request.

### Cloud routing rule (cross-border)

For Telegram-driven AI chat and hybrid routing:

- If `cross_border_transfer` consent is absent, cloud LLM routing is blocked.
- Local Ollama fallback is used.
- Tool/control flows are disabled in forced-local mode.

## Architecture

### Current Architecture (Phase 147+)

Free-text messages and inline keyboard callbacks are now routed through the backend's intent-first conversation system. Slash commands remain unchanged.

```
┌─────────────────────────────────────────────────────────────┐
│                    Telegram User                             │
│           (Tenant / Technician / FM)                         │
└─────────────────────────────────────────────────────────────┘
                              │
                    ┌─────────┴─────────┐
                    ▼                   ▼
            Slash commands         Free-text / Callbacks
            (/info_, /WO_,         ("too hot", "broken tap",
             /inspect_, etc.)       button taps)
                    │                   │
                    ▼                   ▼
┌──────────────────────┐  ┌──────────────────────────────────┐
│   Sentry Gateway     │  │   SENTINEL Backend               │
│   (Claude via        │  │   POST /api/sentry/telegram/     │
│    openclaw engine)  │  │        message | callback        │
│                      │  │                                  │
│   Reads SOUL.md,     │  │   Intent Classifier (9 rules)    │
│   TOOLS.md, runs     │  │        ↓                         │
│   tool scripts       │  │   Conversation Manager (sessions)│
│                      │  │        ↓                         │
│   Delegates free-    │  │   Flow Handlers:                 │
│   text to backend    │  │   - Client Complaint (4 steps)   │
│   endpoints          │  │   - Tech Checklist (6 items)     │
│                      │  │   - WO Update (stateless)        │
│                      │  │   - Ad-Hoc Fault (2 steps)       │
│                      │  │   - Orientation Menu             │
└──────────────────────┘  │        ↓                         │
         │                │   TelegramMessageSender          │
         ▼                │   (sends reply + inline keyboard │
┌──────────────────────┐  │    directly to Telegram API)     │
│ Tool scripts:        │  └──────────────────────────────────┘
│ bms_query.py         │
│ bms_inspect.py       │
│ bms_wo.py            │
│ bms_reset.py         │
│ bms_note.py          │
└──────────────────────┘
```

### Legacy Architecture (pre-Phase 147)

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
              ┌──────────────┼───────────────┐
              ▼              ▼               ▼
┌──────────────────┐ ┌──────────────┐ ┌──────────────────┐
│ Desk Complaint?  │ │ Call Log?    │ │ General Query?   │
│ ▼ YES            │ │ ▼ YES        │ │ ▼                │
│ bms_desk_diag.py │ │ call_log_    │ │ tiered_ai_router │
│                  │ │ handler.py   │ │                  │
└──────────────────┘ └──────────────┘ └──────────────────┘
        │                   │                  │
        ▼                   ▼                  ▼
┌──────────────────┐ ┌──────────────┐ ┌──────────────────┐
│ SENTINEL API     │ │ /call-log    │ │ Ollama / Cloud   │
│ localhost:9095   │ │ /call-log/   │ │ (Hybrid AI)      │
│                  │ │   escalate   │ │                  │
│                  │ │ /call-log/   │ │                  │
│                  │ │ location-    │ │                  │
│                  │ │ memory       │ │                  │
└──────────────────┘ └──────────────┘ └──────────────────┘
```

## Sentry BMS Tools

Located in `$SENTRY_HOME/tools/`:

| Tool | Purpose | SENTINEL API Used |
|------|---------|-------------------|
| `bms_desk_diagnosis.py` | Desk comfort diagnosis | `/api/complaints/*` |
| `bms_control.py` | Device control | `/api/devices/*` |
| `bms_monitor.py` | Health monitoring alerts | `/api/alerts`, `/api/equipment` |
| `sentry_ai_bridge.py` | AI routing with BMS detection | Routes to appropriate tool |
| `tiered_ai_router.py` | Cloud/Ollama fallback | N/A (AI routing) |
| `call_log.py` | General staff defect reporting | `/api/sentry/call-log`, `/api/sentry/call-log/escalate`, `/api/sentry/call-log/location-memory` |

Located in `$SENTRY_HOME/handlers/`:

| Handler | Purpose |
|---------|---------|
| `wo_conversation_handler.py` | Work order data collection state machine |
| `call_log_handler.py` | Call logging taxonomy, classification, discovery conversation |

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

Header `X-User-Id: sentry` identifies bot for audit logging.

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
| 2 | Configured cloud provider (Anthropic or Z.ai) | Complex reasoning, control | PAID |

Safety-critical operations use cloud tool path only. If POPIA cross-border consent is missing, the request remains local/advisory and tool/control actions are not executed.

## Audit Trail

All Sentry actions are logged in SENTINEL:

- User ID: `sentry`
- Source: Telegram user ID passed in metadata
- Actions logged: Device reads, control actions, complaints submitted

Query audit logs:
```
GET /api/audit/logs?user=sentry
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
FM chooses action via slash commands:
  /info_    → Equipment details + checklist
  /reset_   → Remote on/off to clear fault
  /inspect_ → Dispatch technician for physical check
  /WO_      → Formal maintenance work order
  /note_    → Log observation only
```

### Alert Notification Format

```
⚠️ WARNING ALERT - Sandton City Office Tower

🏢 Zone: Level 10 Zone C
🔧 Equipment: FCU-L10-03
📋 Type: FCU
🆔 Code: S002-FCU-L10-03

FCU valve stuck at 15% - insufficient chilled water flow

⏰ Time: 14:32:15
━━━━━━━━━━━━━━━━━━
/info_S002_FCU_L10_03 - More info
/reset_S002_FCU_L10_03 - Remote reset
/inspect_S002_FCU_L10_03 - Send technician
/WO_S002_FCU_L10_03 - Raise work order
/note_S002_FCU_L10_03 - Add note
```

**Important: Telegram Command Format**

Telegram bot commands can only contain letters, numbers, and underscores. Commands end at hyphens or spaces. Therefore:

- Equipment code `FCU-L10-03` becomes command `/WO_FCU_L10_03`
- Sentry converts underscores back to dashes when looking up equipment
- The actual equipment code is displayed in the `Code:` field for reference

### Alert Notifier Service

**Location**: `backend/app/services/sentry_integration/alert_notifier.py`

The alert notifier sends Telegram messages via the `sentry` CLI tool.

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
3. Sends via `sentry message send` CLI

**Configuration**:
- FM Chat ID: Set in `alert_notifier.py` or via `SENTRY_FM_CHAT_ID` env var
- Sentry CLI must be installed and in PATH (vendored at `sentry-gateway/bin/sentry.mjs`)

## Slash Commands

Sentry uses AI-driven slash commands (not hardcoded handlers). The bot reads `SOUL.md` for routing rules and `TOOLS.md` for API instructions.

### FM Workflow

**Standard flow:** Alert → `/info_` → Action (`/reset_`, `/inspect_`, `/WO_`) → `/note_`

Each response ends with clickable next-step buttons (excluding the command just used).

**Web Chat Integration:** The same FM workflow is enforced in the SENTINEL web chat. Claude presents `/info_`, `/inspect_`, `/WO_`, `/note_` as clickable buttons (rendered via `COMMAND_RE` regex in `ChatMessage.tsx`). Claude's system prompt and tool description instruct it to follow the FM process rather than calling `create_work_order` directly. When the tool is called, it routes through `POST /api/sentry/create-work-order` (same as `/WO_` slash command) to persist to Supabase.

### Command Reference

| Command | Purpose | Response to FM |
|---------|---------|----------------|
| `/info_{code}` | Full equipment details: health, make, model, service history, inspection checklist | Detailed report + buttons: `/reset_`, `/inspect_`, `/WO_`, `/note_` |
| `/reset_{code}` | Remote on/off to clear fault (blocked for FIRE/GEN) | Reset result + buttons: `/info_`, `/inspect_`, `/WO_`, `/note_` |
| `/inspect_{code}` | Create inspection WO + dispatch technician via Telegram | One-line ack: `✅ #WO-XXXX sent to {name}` |
| `/WO_{code}` | Formal maintenance work order (asks FM for title/desc/priority) | WO confirmation + buttons: `/reset_`, `/info_`, `/inspect_`, `/note_` |
| `/note_{code}` | Add maintenance note to equipment record | Confirmation + buttons: `/info_`, `/reset_`, `/inspect_`, `/WO_` |

**Telegram command format:** Equipment dashes become underscores (`S002-FCU-301` → `/info_S002_FCU_301`). Bot converts back when calling API.

### `/inspect_` — Dispatch Flow

The `/inspect_` command is a **silent dispatch** — it creates a work order and notifies the technician without verbose output to the FM:

1. FM sends `/inspect_S002_FCU_301`
2. Bot calls `POST /api/sentry/create-work-order` with `telegram_user_id` for audit
3. Bot sends tech a Telegram message via `sentry message send --target {technician_telegram_id}`:
   ```
   #WO-2026-0030 — S002-FCU-301
   ━━━━━━━━━━━━━━━━━━
   /info_S002_FCU_301 - Equipment details
   /note_S002_FCU_301 - Add note
   ```
4. Bot replies to FM: `✅ #WO-2026-0030 sent to John Smith` (one line, no buttons)

**Important:** Technicians only get `/info_` and `/note_` buttons. They do NOT get `/reset_`, `/WO_`, or `/inspect_`.

### `/WO_` — Formal Work Order

When FM clicks `/WO_`, the bot asks for title, description, and priority before creating the work order:

1. FM sends `/WO_S002_FCU_301`
2. Bot asks for work order details (title, description, priority)
3. Bot calls `POST /api/sentry/create-work-order`
4. Bot sends email notification to assigned technician
5. Bot confirms to FM with WO code and assignment

### `/note_` — Log Note

For observations that don't require action. Bot asks the FM for the note text, then logs it against the equipment record.

## Telegram Conversation Flow (Phase 147)

Backend-driven intent classification and multi-step conversation flows with inline keyboard support. Replaces the previous approach where all free-text messages were forwarded to Claude for processing.

### Intent Classification

The `TelegramIntentClassifier` uses a 9-rule priority cascade (no LLM):

| Priority | Rule | Intent | Confidence |
|----------|------|--------|------------|
| 1 | Callback + active session | CHECKLIST_REPLY | 1.0 |
| 2 | Callback, no session | Parse from callback prefix | 0.95 |
| 3 | Active session + free text | CHECKLIST_REPLY | 0.9 |
| 4 | WO-XXXX-XXXX pattern | WO_UPDATE | 0.95 |
| 5 | Equipment ID pattern (S00X-, AHU, FCU...) | TECHNICIAN_REPORT | 0.85 |
| 6 | Technical vocabulary (inspection, vibration...) | TECHNICIAN_REPORT | 0.75 |
| 7 | Issue classifier match (reuses `classify_issue()`) | CLIENT_COMPLAINT | varies |
| 8 | Ad-hoc keywords (chair, door, tap...) | AD_HOC_FAULT | 0.7 |
| 9 | Fallback | UNKNOWN | 0.0 |

### Conversation Flows

**Client Complaint** (4 steps):
1. Category selection (inline keyboard: Temperature, Water, Lighting, Noise, Access, Other)
2. Location (free text, uses `extract_floor_from_message()`)
3. Duration (inline keyboard: Just started / A few hours / Since yesterday / Several days)
4. Optional photo, then WO creation

**Technician Report / AHU Checklist** (6 items with follow-up branching):
- Filter Condition, Filter Pressure Drop, Fan Vibration, Belt Condition, Coil Condition, Damper Operation
- Non-Good answers trigger context-specific follow-ups (e.g., "Blocked" -> "Can you replace now?")
- Auto-creates WOs for critical findings (Blocked/Excessive/Stuck -> CRITICAL priority)

**WO Update** (stateless): Extract WO code -> lookup -> status buttons (Completed / In progress / Blocked)

**Ad-Hoc Fault** (2 steps): Ask location -> create WO

**Unknown/Orientation**: 3-button menu (Report a problem / Start inspection / Check work order)

### API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/sentry/telegram/message` | POST | Classify and handle free-text messages |
| `/api/sentry/telegram/callback` | POST | Handle inline keyboard button taps |

Both require `X-Sentry-API-Key` and `X-Sentry-Secret` headers. Both pass through prompt guard and POPIA consent gate.

The backend sends replies directly to Telegram via `TelegramMessageSender` (calls `api.telegram.org`). The gateway does NOT send a reply -- it delegates entirely.

### Session Management

- In-memory `ConversationSession` keyed by `chat_id`
- 30-minute timeout, cleaned up by background scheduler (30s tick)
- Fields: intent, flow, current_step, answers, equipment_id, wo_codes

### Callback Data Format

`{flow}:{action}:{value}` -- max 64 bytes per Telegram API limit.

Examples: `complaint:category:hvac`, `wo:status:completed`, `menu:start:complaint`, `inspect:filter:good`

### Files

| File | Location | Purpose |
|------|----------|---------|
| `telegram_message_sender.py` | `backend/app/services/` | Telegram Bot API wrapper (send_text, answer_callback, edit_reply_markup) |
| `telegram_intent_classifier.py` | `backend/app/services/` | 9-rule intent classification |
| `telegram_conversation_manager.py` | `backend/app/services/` | Session CRUD + expiry |
| `telegram_flow_handlers.py` | `backend/app/services/` | All 5 conversation flows + router |
| `sentry_webhooks.py` | `backend/app/api/` | `/telegram/message` and `/telegram/callback` endpoints |

### Tests

81 tests across 5 files:
- `test_telegram_message_sender.py` (9 tests)
- `test_telegram_intent_classifier.py` (27 tests)
- `test_telegram_conversation_manager.py` (12 tests)
- `test_telegram_conversation_flow.py` (26 tests)
- `test_telegram_intent_routing.py` (7 tests)

---

## Call Logging Skill — General Staff Defect Reporting

> **Note (Phase 147):** Free-text complaint routing is now handled by the backend conversation system via `POST /api/sentry/telegram/message`. The call logging skill (`call_log.py`) and gateway handler (`call_log_handler.py`) are retained as reference/fallback only. The `sentry-call-logging` SKILL.md is marked DEPRECATED.

The call logging skill allows non-technical users (office workers, cleaners, security guards) to report building defects via natural language Telegram messages. The bot runs a guided discovery conversation, classifies the issue against a fixed taxonomy, and creates an inspection work order.

### Security Model — Fixed Taxonomy

Classification uses a **closed set of 10 disciplines / 46 sub-categories**. The Python handler (`call_log_handler.py`) does ALL classification via keyword matching — the LLM never decides the category.

If the complaint doesn't match any taxonomy entry, it is **NOT logged as a work order**. Instead, it is escalated to the facilities supervisor for manual review.

| Discipline | Sub-categories | Default Priority |
|---|---|---|
| **Plumbing** | Leaking tap, Leaking pipe, Blocked drain, Blocked toilet, No hot water, Flooding | medium–critical |
| **Electrical** | Power outlet not working, Tripped breaker, Sparking, Light flickering, Light not working, Emergency light fault | medium–critical |
| **HVAC** | Too hot, Too cold, Noisy unit, Stuffy air, Water dripping from AC unit, AC unit not working | medium–high |
| **Building Fabric** | Carpet lifting, Damaged floor tile, Broken window, Ceiling tile damaged, Wall damage, Paint peeling | low–high |
| **Access & Security** | Door won't close, Door won't lock, Badge reader not working, Boom gate fault | medium |
| **Fire & Life Safety** | Fire alarm sounding, Smoke detected, Gas smell, Sprinkler issue, Extinguisher missing, Emergency exit blocked | high–critical |
| **Furniture & Fittings** | Broken chair, Broken desk, Broken blind | low |
| **Pest Control** | Insects, Rodents, Birds | low–medium |
| **Cleaning** | Spill on floor, Bad odour, Biohazard | medium–high |
| **Grounds & Parking** | Pothole, Outdoor lighting, Landscaping | low–medium |

### Conversation Flow

```
User: "there is a dripping tap in the ladies bathroom"
    ↓
sentry_ai_bridge.py: is_facilities_complaint() → True
    ↓
call_log_handler.py: start_call_log()
    ↓
classify_issue() → Plumbing / Leaking tap / medium
    ↓
Location check: area="Ladies Bathroom" but no floor
    ↓
Bot: "Which floor is the ladies bathroom on?"
User: "level 2"
    ↓
continue_call_log() → state=CONFIRMING
    ↓
Bot: "I'll log that for you:
      Discipline: Plumbing
      Issue: Leaking tap
      Location: L2, Ladies Bathroom
      Priority: MEDIUM
      Shall I go ahead and log this?"
User: "yes"
    ↓
POST /api/sentry/call-log → WO created
    ↓
Bot: "Logged! Ref: WO-2026-0035
      Our John Smith has been notified."
```

### Location memory-assisted flow

The backend supports reporter location memory for faster repeat logging:

1. Reporter logs first issue with manual location confirmation (desk or floor/area)
2. `POST /api/sentry/call-log` stores reporter memory (`reporter_phone` and/or `reporter_telegram_id`)
3. On later issues, client/bot can query `GET /api/sentry/call-log/location-memory`
4. Bot asks: "I have your last location as Desk 208, L2. Use this location?"
5. On confirmation, create WO without asking location again

If user has moved, they provide a new desk/location and memory is overwritten on the next successful call log.

### State Machine

```
IDLE → COMPLAINT_DETECTED → AWAITING_LOCATION → CONFIRMING → LOGGED
IDLE → COMPLAINT_DETECTED → NO_MATCH → ESCALATED (supervisor notified)
```

### Urgency Escalation (automatic)

Keywords automatically bump priority without asking the user:
- `trip`, `tripping`, `someone could` → bumps to HIGH
- `flooding`, `burst`, `pouring`, `sparking`, `danger` → bumps to CRITICAL
- `fire`, `smoke`, `gas`, `trapped`, `emergency` → bumps to CRITICAL

### IT Exclusion

Messages about PCs, laptops, WiFi, printers, software, etc. are rejected with a redirect to the IT helpdesk. Facility keywords (`power`, `outlet`, `socket`, `light`) override the IT exclusion.

### Supervisor Escalation

When a complaint doesn't match any taxonomy entry but contains action words (`fix`, `repair`, `broken`, `send someone`, etc.):
1. The complaint is logged as an anomaly in `call_log_escalations.json`
2. The supervisor is notified via Telegram (if `CALL_LOG_SUPERVISOR_TELEGRAM_ID` configured)
3. The user receives: "I've flagged it for the facilities supervisor who will follow up."

### Location Discovery

| Input | Desk Mapping | Floor |
|-------|-------------|-------|
| Desk 001–099 | Zone mapping | L0 (Ground) |
| Desk 100–199 | Zone mapping | L1 |
| Desk 200–299 | Zone mapping | L2 |
| Named area + floor | Free text | From user |
| Named area only | Free text | Bot asks |

Current limitation: AD profile location and access-card telemetry are not used for auto-location in the current implementation. Location remains user-confirmed, with memory prefill only.

### API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/sentry/call-log` | POST | Create inspection WO from classified complaint |
| `/api/sentry/call-log/escalate` | POST | Escalate unmatched complaint to supervisor |
| `/api/sentry/call-log/location-memory` | GET | Lookup reporter last confirmed location for prefill |

See `docs/03-api-reference/call-log-api.md` for full request/response schemas.

### Files

| File | Location | Purpose |
|------|----------|---------|
| `call_log_handler.py` | `$SENTRY_HOME/handlers/` | Taxonomy, classification, conversation state machine |
| `call_log.py` | `$SENTRY_HOME/tools/` | CLI tool for classify/log/categories commands |
| `sentry_call_logging.md` | `$SENTRY_HOME/skills/` | Skill documentation for Sentry gateway |
| `sentry_webhooks.py` | `backend/app/api/` | Backend endpoints (call-log + escalation) |
| `reporter_location_repository.py` | `backend/app/database/repositories/` | Reporter location memory persistence |
| `reporter_location_memory.json` | `backend/app/data/` | Fallback store for reporter location memory |
| `call_log_escalations.json` | `backend/app/data/` | Persisted escalation records |

---

## Inspection Skill — Guided Debrief & Supabase Persistence

The inspection skill is a complete end-to-end workflow: FM dispatches, tech inspects, bot guides data collection, results persist to Supabase, FM receives AI diagnosis.

### Full Flow

```
FM: /inspect_S002_FCU_301
    ↓
Bot: Creates WO via POST /api/sentry/create-work-order
    ↓
Bot → Tech (Telegram): "#WO-2026-0030 — S002-FCU-301" + /info_ + /note_
Bot → FM: "✅ #WO-2026-0030 sent to John Smith"
    ↓
Tech: /info_S002_FCU_301 (sees equipment details + inspection checklist)
    ↓
Tech inspects on-site
    ↓
Tech: "done #WO-2026-0030"
    ↓
Bot: Fetches checklist via GET /api/sentry/inspection-checklist/{type}
    ↓
Bot: Prompts tech ONE ITEM AT A TIME:
  "Filter? (Clean / Dirty / Blocked)"
  "Fan? (Normal / Noisy / Not running)"
  "Thermostat? (Responding / Slow / No response)"
    ↓
Bot: Saves to Supabase via POST /api/sentry/inspection-result
    ↓
Bot → FM: AI-curated diagnosis with findings + recommendations + next-step commands
    ↓
FM: /WO_S002_FCU_301 (if needed, creates formal repair work order)
```

### Data Persistence

The `POST /api/sentry/inspection-result` endpoint writes to three Supabase tables:

| Table | What it stores |
|-------|---------------|
| `inspection_tasks` | Task record linked to equipment, status `completed` |
| `inspection_results` | `item_results` JSONB with all checklist answers, `overall_status`, deficiency counts |
| `inspection_deficiencies` | One row per warning/critical finding, linked to result + equipment |

**Overall status:** `pass` (all OK), `pass_with_issues` (warnings only), `fail` (any critical).

**Audit provenance:** `telegram_user_id` is formatted as `sentry:telegram:{user_id}` in the `inspected_by` and `completed_by` fields.

### Checklist Templates

Seven equipment types have inspection checklists in `backend/app/data/inspection_checklist_templates.json`:

| Type | Items | Duration |
|------|-------|----------|
| FCU | Filter, fan, thermostat, drain, coil | ~20 min |
| AHU | Filters, belts, dampers, coils, sensors | ~45 min |
| Chiller | Compressor, condenser, evaporator, refrigerant, oil | ~60 min |
| Generator | Oil, coolant, battery, belts, fuel, load test | ~45 min |
| Pump | Bearings, seals, alignment, vibration, flow | ~30 min |
| UPS | Battery, load, transfer, alarms, ventilation | ~30 min |
| VAV | Damper, actuator, sensor, airflow, controls | ~20 min |

### AI Diagnosis to FM

After the technician completes all checklist items, the bot:

1. Analyses all answers against equipment health data and alert history
2. Highlights abnormalities (e.g., blocked filter + noisy fan = restricted airflow)
3. Recommends next action: schedule service, raise WO, monitor, or no action
4. Sends diagnosis to FM via `sentry message send --target {fm_chat_id}`
5. Ends with relevant slash commands for the FM to act on

### API Reference

See `docs/03-api-reference/inspection.md` for full request/response schemas.

---

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
- `backend/app/api/sentry_webhooks.py` - Sentry webhook endpoints (WO + OCR + inspection + Telegram conversation flow)
- `backend/app/services/telegram_message_sender.py` - Telegram Bot API wrapper (inline keyboards)
- `backend/app/services/telegram_intent_classifier.py` - 9-rule intent classification
- `backend/app/services/telegram_conversation_manager.py` - Session management with 30-min expiry
- `backend/app/services/telegram_flow_handlers.py` - 5 conversation flows (complaint, checklist, WO, ad-hoc, orientation)
- `backend/app/api/inspection.py` - Standard inspection task endpoints
- `backend/app/services/complaint_handler.py` - Diagnosis logic
- `backend/app/services/checklist_service.py` - Inspection checklist template service
- `backend/app/database/repositories/inspection_repository.py` - Inspection data access
- `backend/app/data/inspection_checklist_templates.json` - Checklist templates (7 equipment types)
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
- `tools/call_log.py` - Call logging CLI (classify, log, categories)
- `handlers/call_log_handler.py` - Fixed taxonomy classification & conversation state machine
- Gmail skill - Email notifications to technicians

### Sentry Bot Configuration (`$SENTRY_HOME/`)
- `SOUL.md` - Bot identity, slash command routing rules, data integrity rules
- `TOOLS.md` - API endpoints, CLI commands, slash command procedures
- `SKILL.md` - Skill-specific instructions (inspection flow, debrief prompts)
- `skills/sentry_call_logging.md` - Call logging skill (discovery flow, taxonomy reference)
- `skills/sentinel_inspection.md` - Inspection skill documentation
- `skills/sentinel_desk_complaint.md` - Desk comfort complaint skill
