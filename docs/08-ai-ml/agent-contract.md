---
title: "SENTINEL Agent Contract"
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

# SENTINEL Agent Contract

> **Version:** 1.0 | **Last Updated:** 2026-02-22 | **Status:** Pre-live_control

---

## 1. Agent Specs

### Agent A: Sentry Desk Complaint Agent

| Field | Value |
|-------|-------|
| **Purpose** | Intake comfort complaints and return a data-backed diagnosis. Create and track work orders when dispatch is needed. |
| **Channels** | Telegram bot now, Discord later |
| **Entry point** | `bot.py` -> `sentry_ai_bridge.detect_and_route()` |
| **Runtime** | Python 3 standalone process |
| **Routing** | Regex classifier with fallback "unknown" |

**Core capabilities:**
- Desk to zone mapping
- Live reads for HVAC and lighting context
- Root cause hypotheses with confidence levels
- Dispatch decision gate: FCU fault OR deviation > 2C
- Guided WO evidence collection loop

**Data access:**
- Read BMS API
- Write Supabase for WO creation
- Write BMS API for evidence upload only

**State and storage:**
- In-memory `_user_context` until restart
- Local JSON logs and rate limit state persisted under `~/.sentry/memory/`

**Latency target:** < 3s user response, with tier fallback cut-off at 3s

**Safety boundary:** No device writes

---

### Agent B: PARASITE AI Recommendation Agent

| Field | Value |
|-------|-------|
| **Purpose** | Generate, score, gate, route, approve, and execute recommendations with auditability |
| **Platform** | FastAPI REST services, async |
| **Pipeline** | scorer -> grouper -> quality gate -> tier router -> approval and execution |
| **Modes** | `simulation`, `shadow_live`, `live_control` |

**Core controls:**
- Risk classification with independent safety boundary enforcement
- Tier routing by confidence thresholds plus risk override
- Quality gate with mode-specific enforcement
- COV verification on writes
- Auto rollback with rate limits
- Feedback loop via module multipliers

**Data access:**
- Read multiple internal services
- Write Supabase tables plus BMS device writes in Tier 2 and Tier 3

**Latency targets:**
- Tier routing < 500ms
- COV timeout 10s default

---

## 2. Tool Permission Matrix

### Desk Complaint Agent

| Tool / Service | Read | Write | Notes |
|---|---|---|---|
| BMS API complaints endpoints | Yes | Yes | "submit" creates a complaint record |
| BMS API desk and zone context | Yes | No | Short cache ok |
| BMS API equipment health | Yes | No | Short cache ok |
| BMS API work order endpoints | Yes | Yes | Evidence upload is a write |
| Supabase work order create | No | Yes | Creates WO and triggers technician notification |
| AI APIs tier router | Yes | No | No side effects |

### PARASITE AI Recommendation Agent

| Tool / Service | Read | Write | Notes |
|---|---|---|---|
| Supabase recommendations | Yes | Yes | Full lifecycle |
| Supabase parasite_decisions | Yes | Yes | Tier 3 audit trail |
| Supabase equipment metadata | Yes | No | Input to risk rules and routing |
| Supabase health_snapshots | Yes | Yes | Daily series |
| Supabase audit_log | Yes | Yes | Every action, every mode |
| MonitoringService snapshot | Yes | No | Gate metric source |
| CommissioningService scorecard | Yes | No | Gate metric source |
| MVVerificationService accuracy | Yes | No | Gate metric source |
| MLFeedbackService capture rate | Yes | Yes | Writes feedback records |
| DeviceManager read_value | Yes | No | Pre and post checks |
| DeviceManager set_value | No | Yes | Tier 2 and Tier 3 writes |
| SafetyEngine validate_control_change | Yes | No | Must fail closed |
| COVMonitor verify_write | Yes | No | Post write read-back |
| Auto rollback | No | Yes | Needs cooldown logic |

---

## 3. Workflow Map

### Desk Complaint Workflow

```
IDLE
  -> COMPLAINT_DETECTED
  -> DIAGNOSING
  -> DIAGNOSIS_COMPLETE
       |
       +-- dispatch_required? --+
       |   YES                  |   NO
       v                        v
  WO_CREATED               CLOSED
       |
  TECHNICIAN_NOTIFIED
       |
  CLOSED
```

### WO Evidence Collection

```
IDLE
  -> WO_ACTIVE
  -> COLLECTING_DATA
  -> ITEM_UPLOADED
       |
       +-- is_complete? --+
       |   NO             |   YES
       v                  v
  COLLECTING_DATA     WO_COMPLETE
  (loop)
```

### Recommendation Lifecycle

```
PENDING
  -> Routing outcome:
       TIER 1: advisory (log only)
       TIER 2: requires approval
       TIER 3: auto execute
  -> Execution outcomes:
       EXECUTED or AUTO_EXECUTED
       COV verified or COV failed
       If failed -> ROLLED_BACK
  -> Post:
       outcome measured
       feedback recorded
       health updated
```

### Quality Gate Enforcement

Single decision point for "writes allowed" in live_control.

| Mode | Gate Status | Enforcement |
|---|---|---|
| simulation | FAIL | CAP_CONFIDENCE (0.59) |
| shadow_live | FAIL | SUPPRESS_TIER3 |
| live_control | WARN | SUPPRESS_TIER3 |
| live_control | FAIL | BLOCK_WRITES |

---

## 4. Prompt Caching Plan

### A. Desk Complaint Agent

**Stable prefix (cache for bot uptime):**
- Bot persona and response format
- Tool list and schemas
- Site rules and dispatch policy
- Safety policy: no control writes

**Semi-stable context (cache per building_id):**
- Building and desk mapping
- Department names and zone names
- Known "desk context" attributes list

**Dynamic context (never cache):**
- User message
- Desk id and extracted complaint type
- Live readings snapshot
- Recent WO status for that user

**Rules:**
- Keep system prompt identical for whole bot uptime
- Do not inject tool schemas dynamically
- Put live readings and diagnosis result in the last user message only

### B. PARASITE

**Stable prefix (cache for process uptime):**
- System rules for risk, modes, gating, and audit logging
- Tool schemas for read_value, set_value, validate_control_change, verify_write, rollback
- Output schema for recommendations

**Semi-stable context caches:**
- Equipment capability block per equipment_id (points list, limits, min/max, units, write permissions)
- Site schedule block per site_id per hour
- Baseline block per equipment_id per 5 minutes
- Thresholds per equipment_type per 5 minutes

**Dynamic context (never cache):**
- Single recommendation candidate
- Quality gate snapshot for this run
- Current device reads for this recommendation
- Recent rollback and cooldown state for this equipment

**Hard rule:** Never cache quality gate snapshots. Never reuse a previous snapshot in live_control.

---

## 5. Gaps to Close Before live_control

### Gap 1: Work Order Continuity

**Problem:** `_user_context` dies on restart and breaks evidence collection.

**Fix:** Persist `active_sr_code` and `collected_items` in Redis or Supabase keyed by `user_id` and `sr_code`.

### Gap 2: Graduation Criteria (shadow_live -> live_control)

**Problem:** Risk called out but no criteria defined.

**Proposed criteria:**
- 14 consecutive days in shadow_live
- COV pass rate > 98%
- Auto rollback rate < 5%
- Zero HIGH or CRITICAL actions auto executed
- Manual review sample of X Tier 3 actions per day

### Gap 3: Rollback Oscillation Control

**Problem:** write -> rollback -> write loops possible.

**Fix:** Add equipment cooldown:
- After rollback, block new writes to that equipment for N minutes
- Increase cooldown on repeated failures

### Gap 4: Desk-to-Zone Mapping Source of Truth

**Problem:** Where does `120 -> zone-101` live? If derived, needs validation.

**Fix:** Validation job and a version_id in responses.

---

## Appendices

See also:
- [Quality Gate Metrics & Safety Boundary Rules](agent-contract-appendix.md)
- [AI Recommendation Agent Full Spec](ai-recommendation-agent-spec.md)
- [Sentry Desk Complaint Agent Full Spec](../05-integrations/sentry-desk-complaint-agent-spec.md)
