# n8n Email Intake Pipeline — Setup Runbook

**Phase:** 131 | **Version:** 131.1 | **Date:** 2026-02-27

## Overview

The SENTINEL email intake pipeline uses n8n to:
1. Receive emails via webhook (or IMAP trigger)
2. Parse headers and detect references
3. Classify with GPT-4.1-nano
4. POST to SENTINEL backend for BMS enrichment
5. Send auto-reply via SMTP

## Prerequisites

- n8n instance (self-hosted or cloud)
- OpenAI API key (for GPT-4.1-nano classification)
- SENTINEL backend running with `EMAIL_INTAKE_ENABLED=true`
- SMTP credentials for auto-reply sending

## Setup Steps

### 1. Import Workflow

```bash
# Import the workflow JSON into n8n
# Via n8n UI: Settings → Import from File → select email-intake-pipeline.json
# Via CLI:
n8n import:workflow --input=n8n/workflows/email-intake-pipeline.json
```

### 2. Configure Environment Variables

Set these in your n8n environment:

```bash
# SENTINEL backend URL
SENTINEL_BACKEND_URL=http://localhost:9095

# Auth credentials (must match SENTINEL .env)
SENTRY_BOT_API_KEY=your_sentry_bot_api_key
SENTRY_WEBHOOK_SECRET=your_sentry_webhook_secret

# OpenAI for classification
OPENAI_API_KEY=your_openai_api_key
```

### 3. Configure Email Trigger

Replace the webhook trigger with an IMAP Email Trigger for production:

1. Add "Email Trigger (IMAP)" node
2. Configure:
   - Host: `imap.your-provider.com`
   - Port: `993`
   - User: `helpdesk@fmcompany.co.za`
   - Password: (app-specific password)
   - Mailbox: `INBOX`
   - Poll interval: `1 minute`
3. Connect to "Extract & Parse" node

### 4. Configure Auto-Reply (Optional)

Add an "Send Email" node after the "Format Response" node:

1. Add "Send Email" node
2. Configure SMTP credentials
3. Set "To" = `{{ $json.from_email }}` (original sender)
4. Set "Subject" = `Re: {{ $json.subject }}`
5. Set "Body" = `{{ $json.reply_template }}`

### 5. Enable in SENTINEL

```bash
# In backend/.env
EMAIL_INTAKE_ENABLED=true

# Restart backend
sudo systemctl restart sentinel-backend.service
```

### 6. Test

```bash
# Test the webhook directly
curl -X POST http://localhost:5678/webhook/sentinel-email-intake \
  -H "Content-Type: application/json" \
  -d '{
    "from_email": "test@example.com",
    "from_name": "Test User",
    "subject": "Air conditioning broken on Level 2",
    "body_plain": "The AC has been off since this morning. Please send someone.",
    "message_id": "<test-001@example.com>"
  }'

# Test SENTINEL endpoint directly
curl -X POST http://localhost:9095/api/sentry/email/intake \
  -H "Content-Type: application/json" \
  -H "X-Sentry-API-Key: $SENTRY_BOT_API_KEY" \
  -H "X-Sentry-Secret: $SENTRY_WEBHOOK_SECRET" \
  -d '{
    "from_email": "test@example.com",
    "from_name": "Test User",
    "subject": "Air conditioning broken on Level 2",
    "body_plain": "The AC has been off since this morning.",
    "issue_category": "hvac",
    "issue_summary": "AC not working on Level 2",
    "urgency": "normal",
    "extraction_confidence": 0.80,
    "extraction_model": "gpt-4.1-nano",
    "site_id": "site-002"
  }'
```

## Parser Source-of-Truth

The Step 2 "Extract & Parse" code node has two copies:

- **Canonical source:** `n8n/workflows/email-intake-step2-enhanced.js`
- **Inline copy:** embedded in `email-intake-pipeline.json` node `node-2-extract`

When updating parser logic (urgency patterns, site mappings, noise filters), edit the `.js` file first and then sync the inline copy in the workflow JSON. The inline copy has a header comment referencing the canonical file.

## Workflow Architecture

```
Email Source → [Webhook/IMAP] → [Extract & Parse] → [AI Classify]
                                       ↓                  ↓
                                 [Merge Fields] ← ← ← ← ←
                                       ↓
                                [Combine Payload]
                                       ↓
                               [POST to SENTINEL]
                                       ↓
                                  [Success?]
                                  ↙       ↘
                         [Format Response] [Error Handler]
                              ↓
                         [Send Reply]
```

## BMS Enrichment Layers

When SENTINEL receives an intake, it enriches the record with 5 layers of BMS context (all fail gracefully if data is unavailable):

| # | Layer | Source | Purpose |
|---|-------|--------|---------|
| 1 | Building name | `buildings` table by site code | Human-readable site label for reply templates |
| 2 | Active alerts | `alerts` table (status=active, building UUID) | Urgency escalation + context for FM triage |
| 3 | Recent work orders | `work_orders` table (status=scheduled, building UUID) | Avoid duplicate WO creation |
| 4 | Equipment health | `equipment` table (at-risk count) | Flag buildings with degraded equipment |
| 5 | Agent memory | `agent_memory` table by site_id | Historical notes and quirks for AI context |

## Auth Flow

```
n8n → POST /api/sentry/email/intake
  Headers:
    X-Sentry-API-Key: {sentry_bot_api_key}   ← middleware gate
    X-Sentry-Secret: {sentry_webhook_secret}  ← endpoint check
```

Both headers are required. The API key is checked by the existing `/api/sentry/*` middleware. The webhook secret is verified within the endpoint handler.

## Troubleshooting

| Issue | Solution |
|-------|----------|
| 403 on POST | Check `X-Sentry-API-Key` matches `SENTRY_BOT_API_KEY` in SENTINEL .env |
| 401 on POST | Check `X-Sentry-Secret` matches `SENTRY_WEBHOOK_SECRET` in SENTINEL .env |
| 503 on POST | Set `EMAIL_INTAKE_ENABLED=true` in SENTINEL .env and restart |
| AI classification empty | Check OpenAI API key and model availability |
| Emails not arriving | Check IMAP credentials and poll interval |
| Duplicate intakes | Expected behavior — dedup window is 24h by default |
