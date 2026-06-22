---
title: "Sentry Desk Complaint Agent -- Full Specification"
type: "spec"
status: "draft"
version: "1.0.0"
created: "2026-03-31"
updated: "2026-06-16"
tags: ["sentinel", "documentation"]
related: []
domain: "bms"
audience: "all"
complexity: "intermediate"
estimated_read_time: 10
---

# Sentry Desk Complaint Agent -- Full Specification

> **Version:** 1.3 | **Last Updated:** 2026-06-16 | **Location:** `/home/bederf/.sentry/`
>
> **Phase 147 Note:** Telegram free-text complaint routing is now handled by the backend conversation system (`POST /api/sentry/telegram/message`) with inline keyboard flows. The gateway delegates to the backend instead of routing through `sentry_ai_bridge.py` for free-text messages. Slash commands and the desk diagnosis tool remain unchanged. See `docs/05-integrations/SENTRY_INTEGRATION.md` for the updated architecture.

## 1. Goals & Success Metrics

**Primary Goal:** Instantly diagnose occupant comfort complaints by correlating desk location with live BMS zone data, and dispatch technicians when needed.

| Metric | Target | Current |
|--------|--------|---------|
| Diagnosis latency (complaint -> response) | < 3s | ~2s (local) |
| Root cause accuracy (confirmed by technician) | > 80% | Not yet measured |
| Dispatch rate (complaints requiring technician) | < 40% | N/A |
| WO data collection completion rate | > 90% | N/A |
| Telegram response rate (bot uptime) | > 99% | Active |

---

## 2. Agent Card

| Field | Value |
|-------|-------|
| **Name** | Sentry Staff Bot |
| **Location** | `/home/bederf/.sentry/` |
| **Platform** | Sentry channel adapters: Telegram current; WhatsApp/custom app planned |
| **Runtime** | Python 3, standalone process |
| **Framework** | Pattern-matching router (no LangGraph) |
| **Entry Point** | `bot.py` -> `sentry_ai_bridge.detect_and_route()` |
| **Key Files** | `tools/bms_desk_diagnosis.py`, `tools/sentry_ai_bridge.py`, `tools/work_order.py`, `tools/call_log.py`, `handlers/wo_conversation_handler.py`, `handlers/call_log_handler.py` |
| **AI Tiers** | 4-tier fallback: tinydolphin (fast) -> GPT-3.5/Gemini (cloud) -> Claude Haiku (complex) -> phi3:mini (quality) |
| **Auth** | `X-Sentry-API-Key`, `X-User-Id: sentry`, `X-Sentry-Secret` headers |

---

## 3. Staff Identity & Self-Registration

SENTINEL is the facilities/BMS platform. Sentry is the bot interface layer for the site manager, technicians, and staff. The current Staff bot deployment is scoped to site-002.

The canonical staff identity should be the HR/staff number, not a Telegram ID. Channel-specific IDs are bindings captured at first use:

- Telegram: current adapter stores the Telegram user ID for the Staff bot.
- WhatsApp: future adapter should bind the staff number to the WhatsApp number.
- Custom app: future adapter should bind the staff number to the app user ID/session identity.

Bulk onboarding should be roster driven. Import or sync a roster from HR with at least `staff_number`, `name`, `email`, `phone`, `desk`, `site_id`, and `active`. The desk number gives the technician enough location context for first response.

Recommended first-use flow:

1. Admin imports/syncs the staff roster for site-002.
2. Admin enables first-contact registration for the staff channel.
3. Staff receive a link or QR code, for Telegram currently `https://t.me/sentinelstaffbot?start=staff`.
4. Staff enter their staff number.
5. Staff confirm the last 4 digits of their phone number from the roster.
6. Sentry creates the channel binding, grants Staff bot access, and stores desk/location memory.
7. Future complaints can skip manual identity capture and use the saved desk/location context.

Security rule: unknown users must be gated before normal bot functions. Do not leave public first-contact registration enabled unless a roster/HR lookup is active. The current Telegram implementation uses `bot_users.telegram_id`; before adding WhatsApp or a custom app, introduce an explicit channel-binding model instead of overloading Telegram fields.

---

## 4. Directory Structure

```
/home/bederf/.sentry/
├── bot.py                                 # Main Staff bot (Phase 41 WO handlers)
├── handlers/
│   ├── wo_conversation_handler.py        # Work Order conversation state machine
│   └── call_log_handler.py              # Call logging: fixed taxonomy, discovery, escalation
├── tools/
│   ├── bms_desk_diagnosis.py            # PRIMARY DESK COMPLAINT TOOL
│   ├── sentry_ai_bridge.py              # AI routing & message orchestration
│   ├── tiered_ai_router.py              # 4-tier AI fallback system
│   ├── fast_ai_service.py               # Quick response service
│   ├── sentinel_health_alert.py         # Equipment health monitoring
│   ├── work_order.py                    # Work order creation & email
│   ├── ai_performance_monitor.py        # Response latency tracking
│   ├── call_log.py                    # Call logging CLI (classify/log/categories)
│   └── load_docker_secrets.py           # Secret management
├── skills/
│   ├── sentinel_desk_complaint.md       # Desk comfort complaint skill
│   ├── sentinel_inspection.md           # Inspection debrief skill
│   └── sentry_call_logging.md           # Call logging skill (fixed taxonomy)
├── memory/
│   ├── work-orders.json                 # Persisted WO state
│   ├── rate_limit_state.json            # Rate limiting tracker
│   └── [daily logs]
├── config/
│   └── ai_router_config.json            # AI tier configuration
├── IDENTITY.md                          # Sentry Staff Bot identity
├── SOUL.md                              # Core behavioral principles
├── AGENTS.md                            # Memory & session management
└── CLAUDE.md                            # Development guidelines
```

---

## 5. Workflows

### 4A: Desk Complaint Workflow

```
1. User sends "Desk 120 is too hot" via the Staff channel
2. bot.py -> detect_and_route() matches desk complaint regex
3. Extract: desk_id=120, complaint_type="too_hot"
4. diagnose_comfort_issue(120, "too_hot", "site-002")
   4a. POST /api/complaints/submit?desk_id=120&complaint_type=too_hot
   4b. SENTINEL CrossSystemAnalyzer:
       - Map desk -> zone (120 -> zone-101, Level 1)
       - Read live HVAC: temp=24.5C, setpoint=22.0C, FCU status
       - Read DALI sensors: occupancy, light levels
       - Check context: near_window, near_diffuser, near_printer
   4c. Return: diagnosis, probable_causes, suggested_actions, dispatch_required
5. format_diagnosis_for_channel(result) -> formatted message
6. Send response to user with:
   - Desk location (floor, zone, department)
   - Current readings (temp, setpoint, deviation)
   - Root cause analysis
   - Recommended actions
   - Whether technician dispatched
7. IF dispatch_required:
   7a. Create work order -> Supabase
   7b. Assign technician by specialty
   7c. Sentry notification to the assigned technician
```

### 4B: Work Order Data Collection Workflow

```
1. Technician receives WO notification (SR-2026-ABC123)
2. Technician completes service, sends "done" via the Tech bot
3. WOConversationHandler.handle_initial_done()
   3a. POST "done" to /api/sentry/work-order/response
   3b. BMS returns first data prompt ("Take service sheet photo")
4. Bot displays prompt to technician
5. Technician uploads photo/audio/document
6. WOConversationHandler.handle_file_reply(file_info)
   6a. POST file to /api/sentry/work-order/response
   6b. BMS returns next_prompt or is_complete=true
7. REPEAT steps 5-6 until all items collected
8. Completion message sent, context cleared
```

### Message Routing (Functional DAG)

```
message
  ├── Pattern: /WO-<code>              -> handle_wo_command()
  ├── Pattern: /WO-minor-<code>        -> handle_wo_minor_command()
  ├── Pattern: /WO-major-<code>        -> handle_wo_major_command()
  ├── Pattern: /WO-inspect-<code>      -> handle_wo_inspect_command()
  ├── Pattern: /note-<code>            -> handle_note_command()
  ├── Pattern: /info-<code>            -> handle_info_command()
  ├── Pattern: SR-XXXX-XXXXXX + "done" -> handle_work_order_initial()
  ├── Pattern: Desk complaint regex    -> diagnose_comfort_issue()
  ├── Active call log conversation     -> continue_call_log()
  ├── Facilities complaint keywords    -> start_call_log()
  ├── Pattern: BMS status query        -> check_equipment_health()
  └── Default: Fast AI response        -> tiered_ai_router
```

**Call log routing details:**

The `sentry_ai_bridge.py` checks call log routing after desk complaints but before the general fallback:

1. `has_active_call_log(user_id)` → Continue the discovery conversation (`call_log_continue`)
2. `is_facilities_complaint(message)` → Start a new call log (`call_log_start`)

The `is_facilities_complaint()` function returns `True` if the message matches the fixed taxonomy OR contains facility action words (`fix`, `repair`, `broken`, `send someone`, etc.). IT-related messages are excluded.

Location handling for call log:

1. First-time reporter: staff member registers with staff number, confirms roster phone digits, and uses the roster desk/location
2. Repeat reporter: backend can prefill last location using `GET /api/sentry/call-log/location-memory` (phone or current channel binding; Telegram ID today)
3. User confirmation is still mandatory before WO creation

Current limitation: AD profile location and access-card telemetry are not used yet for auto-location.

---

## 6. Tools & Functions

### Primary Tool: bms_desk_diagnosis.py

```python
diagnose_comfort_issue(
    desk_id: str,                    # e.g., "120", "201", "L12-21"
    complaint_type: str,             # "too_hot" | "too_cold" | "stuffy" | "drafty"
    building: str = None,            # Defaults to "site-002"
    additional_info: str = None      # Optional context from user
) -> Dict[str, Any]
```

**Returns (Success Case):**
```python
{
    'success': True,
    'diagnosis': {
        'complaint_id': str,                # UUID from complaint API
        'desk_id': str,
        'complaint_type': str,
        'desk_location': {
            'building': str,
            'floor': str,
            'zone': str,                    # Zone ID (100-199 = L1, etc.)
            'department': str
        },
        'zone_readings': {
            'zone_id': str,
            'zone_name': str,
            'current_temp': float,          # Actual temperature in C
            'setpoint': float,              # Target temperature
            'temp_deviation': str,          # Formatted deviation description
            'fcu_status': str,              # "normal" | "warning" | "fault"
            'fcu_id': str,                  # Equipment ID (S002-FCU-L1-A)
            'vav_id': str,                  # VAV equipment ID if present
        },
        'context_flags': {
            'near_window': bool,
            'near_diffuser': str,           # Diffuser ID if applicable
            'near_printer': bool
        },
        'probable_causes': [str],           # List of root causes
        'suggested_actions': [str],         # List of recommendations
        'dispatch_required': bool,          # True if technician needed
        'confidence': str,                  # "high" | "medium" | "low"
    },
    'source': str  # "sentinel_diagnosis" | "fallback_with_bms_readings"
}
```

### Orchestration Tool: sentry_ai_bridge.py

```python
# Pattern matching
is_desk_complaint(message: str) -> Optional[Dict]
is_bms_status_query(message: str) -> bool
is_work_order_message(message: str) -> Tuple[bool, Optional[str], Optional[str]]

# Routing
detect_and_route(message, user_id, message_type="text") -> Dict
route_to_handler(route_data) -> str

# AI responses
async get_ai_response(message, user_id, platform) -> Optional[Dict]
async get_ai_system_status() -> Dict
```

### Work Order Tools

```python
handle_work_order_initial(sr_code, user_id) -> str
handle_wo_file_upload(sr_code, user_id, file_info, message_type) -> str
handle_wo_status(sr_code, user_id) -> str
handle_wo_inspect_command(equipment_code, user_id) -> str
handle_wo_minor_command(equipment_code, user_id) -> str
handle_wo_major_command(equipment_code, user_id) -> str
```

---

## 6. Complaint Types & Diagnosis Logic

| Type | Keywords | Root Causes | Actions |
|------|----------|-------------|---------|
| `too_hot` | "hot", "warm", "baking" | FCU cooling fault, high setpoint, solar gain, printer heat | Raise damper, lower setpoint, deploy blinds, technician dispatch |
| `too_cold` | "cold", "freezing", "chilly" | FCU heating fault, low setpoint, direct diffuser airflow | Lower damper, raise setpoint, adjust diffuser, technician dispatch |
| `stuffy` | "stale", "no air", "bad air" | Low fresh air supply, CO2 high, AHU damper stuck | Check AHU outside air damper, verify CO2 sensor, increase ventilation |
| `drafty` | "windy", "breezy", "draft" | High velocity diffuser, window leaks, damper oscillation | Reduce airflow, close diffuser vanes, seal window, technician dispatch |

**Confidence Levels:**
- **High**: FCU in fault state, or clear temp deviation >2C with active readings
- **Medium**: Probable causes identified + BMS readings available
- **Low**: Probable causes but no sensor confirmation, or unknown cause

**Complaint Pattern Regexes:**
```python
desk_complaint_patterns = [
    r"desk\s+(\d+)\s+(?:is\s+)?(?:saying\s+)?(?:it'?s?\s+)?too\s+(hot|cold)",
    r"too\s+(hot|cold)\s+(?:at\s+)?desk\s+(\d+)",
    r"desk\s+(\d+)\s+(?:is\s+)?(hot|cold|stuffy|drafty)",
    r"complaint\s+(?:from\s+)?desk\s+(\d+).*(hot|cold|stuffy|drafty)",
    r"user\s+at\s+desk\s+(\d+)\s+(?:says?\s+)?(?:it'?s?\s+)?too\s+(hot|cold)",
]
```

---

## 7. AI Tier System

| Tier | Name | Model | Speed | Use Case |
|------|------|-------|-------|----------|
| 1 | Claude (Fallback) | claude-haiku | 2s | Complex reasoning (NOT user-facing) |
| 2 | Cloud APIs | GPT-3.5, Gemini Flash | 1.5s | Balanced queries |
| 3 | Fast Local | tinydolphin | <1s | Quick user-facing responses |
| 4 | Quality Local | phi3:mini | 5-10s | Backend-only quality queries |

**User-facing priority:** Tier 3 -> Tier 2 -> Tier 1 (fast first, abort if latency > 3s)

---

## 8. Context & Memory

| Type | Storage | Persistence | Contents |
|------|---------|-------------|----------|
| Session context | `_user_context` dict (in-memory) | Until bot restart | active_sr_code, last_sr_code, collected_items, last_message_time |
| Work order history | `~/.sentry/memory/work-orders.json` | Persistent | Submitted WOs (sr_code, equipment, date) |
| Rate limit state | `~/.sentry/memory/rate_limit_state.json` | Persistent | API call counts per user |
| Daily logs | `~/.sentry/memory/YYYY-MM-DD.md` | Persistent | Raw session logs |
| AI perf metrics | In-memory (AIRequestMetric) | Until restart | Latency, tier usage, cache hits |

**Context Flow:**
```
Staff channel message -> bot.py identifies user_id -> load _user_context[user_id]
-> check active_sr_code (WO in progress?) -> process -> update context -> respond
```

---

## 9. Data Sources

| Source | Type | Endpoint/Path | Data |
|--------|------|---------------|------|
| SENTINEL BMS API | REST | `localhost:9095/api/complaints/submit` | Diagnosis result |
| SENTINEL BMS API | REST | `localhost:9095/api/complaints/desk/{id}` | Desk context |
| SENTINEL BMS API | REST | `localhost:9095/api/complaints/zone/{id}` | HVAC zone readings |
| SENTINEL BMS API | REST | `localhost:9095/api/equipment` | Equipment health |
| SENTINEL BMS API | REST | `localhost:9095/api/sites/{id}/summary` | Site summary |
| SENTINEL BMS API | REST | `localhost:9095/api/sentry/work-order/*` | WO management |
| Local JSON | File | `~/.sentry/memory/work-orders.json` | WO history |
| AI config | File | `~/.sentry/config/ai_router_config.json` | Tier config |

**Authentication:**
- Header: `X-Sentry-API-Key` (for `/api/sites/*`)
- Header: `X-User-Id: sentry` (for general queries)
- Secret header: `X-Sentry-Secret: sentry-bms-phase-41` (for WO endpoints)

---

## 10. Events & State

### States

```
IDLE -> COMPLAINT_DETECTED -> DIAGNOSING -> DIAGNOSIS_COMPLETE
                                              |
                                    [dispatch_required?]
                                     YES -> WO_CREATED -> TECHNICIAN_NOTIFIED
                                     NO  -> CLOSED

WO Data Collection:
IDLE -> WO_ACTIVE -> COLLECTING_DATA -> ITEM_UPLOADED -> [more items?]
                                                          YES -> COLLECTING_DATA
                                                          NO  -> WO_COMPLETE
```

### Events Emitted

| Event | Trigger | Consumer |
|-------|---------|----------|
| `complaint_submitted` | User sends desk complaint | SENTINEL complaint service |
| `work_order_created` | dispatch_required=true | Supabase, technician notification |
| `wo_item_collected` | Technician uploads file | BMS WO tracking |
| `wo_completed` | All items collected | BMS close WO |
| `health_alert` | Equipment health < 70 | Telegram channel |

---

## 11. Error Handling & Escalation

### Error Handling Hierarchy

1. **API call errors:** Return `{'error': f'HTTP {e.code}: {e.reason}'}`
2. **Fallback paths:** If complaint endpoint fails, use direct desk/zone API calls
3. **User-friendly messages:** Unknown cause -> "requires on-site investigation", dispatch_required=True
4. **Catastrophic failures:** Return "Could not diagnose desk. Please verify the desk ID or try 'list desks'"

### Escalation Logic

```python
# Priority based on health score
if health_score < 50:
    priority = "critical"   # SLA: 1 hour
elif health_score < 70:
    priority = "high"       # SLA: 4 hours
else:
    priority = "medium"     # SLA: 24 hours
```

### Timeout Handling

- All API calls: 30s default timeout
- Fast-response path: abort if latency > 3s, return interim message

---

## 12. Metrics & Observability

| Metric | Type | Source |
|--------|------|--------|
| `ai_request_count` | Counter | `ai_performance_monitor.py` |
| `ai_request_latency_ms` | Histogram | Per-tier latency tracking |
| `ai_cache_hit_rate` | Gauge | Cached AI response ratio |
| `ai_tier_distribution` | Counter | Requests per tier (1-4) |
| `diagnosis_success_rate` | Gauge | Successful vs failed diagnoses |
| `dispatch_rate` | Gauge | Complaints requiring technician |
| `wo_collection_completion` | Gauge | WOs with all items collected |

**AI Performance Metric Structure:**
```python
class AIRequestMetric:
    timestamp: float
    query: str
    tier: str
    model: str
    latency_ms: int
    fallback_reason: str
    cached: bool
    user_facing: bool
```

---

## 13. Integration with BMS

### Complaint Submission -> SENTINEL Diagnosis

```
Sentry Bot (user-facing)
    |
bms_desk_diagnosis.diagnose_comfort_issue()
    |
POST /api/complaints/submit
    |
SENTINEL CrossSystemAnalyzer
    ├── Desk -> Zone mapping
    ├── Live HVAC readings
    ├── DALI sensor data (occupancy, light levels)
    ├── Window/diffuser/printer context
    └── Returns: diagnosis, root_cause, suggestions, dispatch_required
    |
Format & return to user
```

### Work Order Submission -> Supabase -> Technician Notification

```
Sentry Bot (operator)
    |
/WO-inspect-<code> command
    |
POST /api/work-orders/supabase
    |
BMS API saves to Supabase
    ├── work_orders table
    ├── Assign to technician (by specialty)
    ├── Generate SR code (SR-2026-XXXXXX)
    └── Queue Telegram notification
    |
Technician receives WO -> completes -> "done" -> data collection
```

---

## 14. Open Questions / Risks

| # | Question/Risk | Impact | Status |
|---|---------------|--------|--------|
| 1 | No persistence across bot restarts — `_user_context` lost, active WO collections abandoned | Medium | Consider persisting to Redis or JSON |
| 2 | Single-building assumption — defaults to "site-002" | Low | Add multi-site support when needed |
| 3 | No NLP beyond regex — "my area is uncomfortable" not matched | Medium | Partially addressed: Call log handler uses 46-entry keyword taxonomy with multi-word scoring. Unmatched complaints escalate to supervisor. |
| 4 | Root cause accuracy not measured — no feedback loop from technician | High | Add technician confirmation flow |
| 5 | Rate limiting per-user only — no global rate limit | Low | Monitor and add if needed |
| 6 | AI tier fallback latency — if fast local fails, cloud adds 1-3s | Medium | Implement streaming/interim responses |
