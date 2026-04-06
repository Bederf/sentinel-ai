---
title: "n8n Email Intake Pipeline — Setup Runbook"
type: "spec"
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

# n8n Email Intake Pipeline — Setup Runbook

**Phase:** 134 | **Version:** 134.0 | **Date:** 2026-02-28

## Overview

The SENTINEL email intake pipeline uses n8n to:
1. Receive emails via IMAP trigger (polls `workorder@sentinel-ai.co.za`)
2. Filter noise (OOO, newsletters, system emails)
3. Extract raw fields (sender, subject, body, references)
4. POST raw fields to SENTINEL backend for AI classification + reply
5. Optionally send auto-reply via n8n SMTP (if backend didn't send threaded reply)

**Phase 134 change:** All classification (keyword matching, urgency detection, CC analysis) moved from n8n to the backend AI agent. n8n now extracts raw IMAP fields only.

## Prerequisites

- n8n instance (self-hosted or cloud)
- SENTINEL backend running with `EMAIL_INTAKE_ENABLED=true`
- IMAP credentials for the intake mailbox
- SMTP credentials for auto-reply sending (fallback — backend sends threaded replies by default)

**Note:** OpenAI API key is no longer needed in n8n. Classification uses the backend's AI agent (configured in SENTINEL's `.env`).

## Setup Steps

### 1. Import Workflow

```bash
# Import the workflow JSON into n8n
# Via n8n UI: Settings → Import from File → select email-intake-imap.json
# Via CLI:
n8n import:workflow --input=n8n/workflows/email-intake-imap.json
```

### 2. Configure Credentials in n8n

**IMAP credential** (for receiving emails):
- Host: `imap.your-provider.com`
- Port: `993` (SSL)
- User: `workorder@sentinel-ai.co.za`
- Password: (app-specific password)

**SMTP credential** (for fallback auto-reply):
- Host: `smtp.your-provider.com`
- Port: `587` (TLS)
- User: `workorder@sentinel-ai.co.za`
- Password: (app-specific password)

### 3. Configure Auth Headers

In the "POST to SENTINEL" HTTP Request node, set:

```
X-Sentry-API-Key: {your sentry_bot_api_key}
X-Sentry-Secret: {your sentry_webhook_secret}
```

These must match the values in SENTINEL's backend `.env` file.

### 3.1 Required n8n Environment Variables (Security)

Do not hardcode secrets directly in workflow JSON. Use n8n environment variables in header expressions:

```
X-Sentry-API-Key: ={{ $env.SENTRY_BOT_API_KEY }}
X-Sentry-Secret: ={{ $env.SENTRY_WEBHOOK_SECRET }}
```

Recommended n8n env vars for this pipeline:

```bash
# n8n -> SENTINEL auth
SENTRY_BOT_API_KEY=...
SENTRY_WEBHOOK_SECRET=...

# Optional base URL used by webhook-style workflow variant
SENTINEL_BACKEND_URL=http://127.0.0.1:9095
```

Security note:
- Keep these values out of repo files and workflow exports.
- Rotate both secrets if they were previously committed in plaintext.

### 4. Enable in SENTINEL Backend

```bash
# In backend/.env
EMAIL_INTAKE_ENABLED=true
EMAIL_INTAKE_AGENT_ENABLED=true      # Use AI agent (default: true)
EMAIL_INTAKE_AUTO_WO_ENABLED=true    # Auto-create work orders (default: false)

# AI agent uses backend's OpenAI key
OPENAI_API_KEY=your_openai_api_key

# Restart backend
sudo systemctl restart sentinel-backend.service
```

### 5. Test

```bash
# Test SENTINEL endpoint directly (minimal payload — n8n no longer sends classification fields)
curl -X POST http://localhost:9095/api/sentry/email/intake \
  -H "Content-Type: application/json" \
  -H "X-Sentry-API-Key: $SENTRY_BOT_API_KEY" \
  -H "X-Sentry-Secret: $SENTRY_WEBHOOK_SECRET" \
  -d '{
    "from_email": "test@example.com",
    "from_name": "Test User",
    "subject": "Broken plug at desk 204",
    "body_plain": "Hi, I have a broken plug at my desk 204. Regards, Pieter, 0798607245",
    "message_id": "<test-001@example.com>",
    "site_id": "site-002"
  }'

# Expected response includes agent_model showing which classifier was used:
# {
#   "success": true,
#   "intake_id": "...",
#   "action_taken": "auto_submit",
#   "concept_ref": "WO-2026-XXXX",
#   "urgency": "normal",
#   "agent_model": "gpt-4.1-nano",
#   "reply_template": "Hi Pieter, I've logged your broken plug at desk 204..."
# }
```

## Workflow Architecture

```
[IMAP Trigger] → [Filter System Emails] → [Extract & Parse] → [Noise Gate]
                                                                    ↓
                                                           [POST to SENTINEL]
                                                                    ↓
                                                          [Process Response]
                                                                    ↓
                                                            [Should Reply?]
                                                              ↙        ↘
                                                   [Send Auto-Reply]  [Log Result]
                                                         ↓
                                                    [Log Result]
```

**Nodes:**

| Node | Purpose |
|------|---------|
| New Email Received | IMAP trigger, polls for UNSEEN emails |
| Filter System Emails | Skip emails from @sentinel-ai.co.za (own replies) |
| Extract & Parse | Extract raw IMAP fields, filter noise/system emails |
| Noise Gate | Skip dropped items (noise/system filter) |
| POST to SENTINEL | Send raw fields to backend AI agent (3 retries, 45s timeout) |
| Process Response | Map backend response, check if backend sent threaded reply |
| Should Reply? | Skip n8n SMTP if backend already sent threaded reply |
| Send Auto-Reply | Fallback SMTP reply (only if backend didn't send) |
| Log Result | Set final status fields for execution log |

## What n8n Extracts (Phase 134)

n8n sends only raw fields — no classification:

```json
{
  "from_email": "john@centrecourt.co.za",
  "from_name": "John Smith",
  "subject": "Air conditioning broken on Level 2",
  "body_plain": "The AC has been off since this morning...",
  "message_id": "<abc123@centrecourt.co.za>",
  "in_reply_to": null,
  "references": null,
  "received_at": "2026-02-28T09:15:00Z",
  "existing_reference": "FNBFW:45678",
  "site_id": "site-002",
  "attachment_count": 0
}
```

**Removed from n8n (now in backend AI agent):**
- `issue_category` — AI agent classifies against 47-category taxonomy
- `issue_summary` — AI agent generates contextual summary
- `urgency` / `urgency_boost` — AI agent + BMS enrichment determines urgency
- `extraction_confidence` / `extraction_model` — AI agent scores completeness
- `cc_count` / `has_manager_cc` — no longer needed (agent reads full email context)

## BMS Enrichment Layers

When SENTINEL receives an intake, it enriches the record with 5 layers of BMS context. This context is injected into the AI agent's prompt for better classification:

| # | Layer | Source | Purpose |
|---|-------|--------|---------|
| 1 | Building name | `buildings` table by site code | Context for agent reply |
| 2 | Active alerts | `alerts` table (status=active, building UUID) | Agent sees correlated alerts |
| 3 | Recent work orders | `work_orders` table (status=scheduled, building UUID) | Agent avoids duplicate WOs |
| 4 | Equipment health | `equipment` table (at-risk count) | Agent prioritizes degraded equipment |
| 5 | Agent memory | `agent_memory` table by site_id | Historical notes for AI context |

## Auth Flow

```
n8n → POST /api/sentry/email/intake
  Headers:
    X-Sentry-API-Key: {sentry_bot_api_key}   ← middleware gate
    X-Sentry-Secret: {sentry_webhook_secret}  ← endpoint check
```

Both headers are required. The API key is checked by the existing `/api/sentry/*` middleware. The webhook secret is verified within the endpoint handler.

## AI Agent Details

The backend AI agent (`EmailIntakeAgent`) performs classification + reply in one LLM call:

| Aspect | Detail |
|--------|--------|
| Primary model | GPT-4.1-nano (~$0.0001/email) |
| Fallback chain | OpenAI → Claude → keyword matching |
| Taxonomy | 47 categories from `CALL_LOG_TAXONOMY` |
| Output | Discipline, sub-category, location, phone, completeness score, action, natural reply |
| Completeness ≥ 0.85 | `auto_submit` — WO created, auto-reply sent |
| Completeness 0.60–0.84 | `request_info` — WO created, reply asks for missing details |
| Completeness < 0.60 | `manual_review` — WO created, queued for FM triage |
| Reply format | Plain text + branded HTML with SENTINEL styling |
| Feature flag | `EMAIL_INTAKE_AGENT_ENABLED` (default: true) |

## Threaded Reply Flow

Phase 134 supports two reply paths:

1. **Backend threaded reply** (default): Backend sends SMTP reply with `In-Reply-To` / `References` headers. Reply appears in sender's original email thread. WO code appended to subject: `Re: Original Subject [WO-2026-XXXX]`.
2. **n8n SMTP fallback**: If backend reply fails, n8n sends reply via its own SMTP node.

The "Should Reply?" node checks `_backend_reply_sent` to avoid sending duplicate replies.

## Troubleshooting

| Issue | Solution |
|-------|----------|
| 403 on POST | Check `X-Sentry-API-Key` matches `SENTRY_BOT_API_KEY` in SENTINEL .env |
| 401 on POST | Check `X-Sentry-Secret` matches `SENTRY_WEBHOOK_SECRET` in SENTINEL .env |
| 503 on POST | Set `EMAIL_INTAKE_ENABLED=true` in SENTINEL .env and restart |
| Agent returns keyword_fallback | Check `OPENAI_API_KEY` in backend .env; verify OpenAI API is reachable |
| Emails not arriving | Check IMAP credentials and n8n trigger status |
| Duplicate intakes | Expected behavior — dedup window is 24h by default |
| Reply not threaded | Ensure backend has SMTP credentials configured |
| Duplicate replies | Check "Should Reply?" node — n8n should skip if backend sent reply |
| Slow response (>30s) | Agent LLM timeout is 30s; check OpenAI latency or increase `EMAIL_INTAKE_AGENT_TIMEOUT_SECONDS` |
