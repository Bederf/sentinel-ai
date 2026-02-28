# Email Intake Pipeline — Centre Court 5-Layer Trace

**Phase:** 134 | **Version:** 134.0 | **Date:** 2026-02-28

## Trace Scenario: HVAC Complaint from Centre Court Tenant

This trace follows a real-world FM email through all 5 layers of the SENTINEL email intake pipeline.

---

### Layer 1: Email Arrives (n8n IMAP Trigger)

**Input:** Email from tenant at Centre Court (site-002)

```
From: john.smith@centrecourt.co.za
To: workorder@sentinel-ai.co.za
CC: facilities.manager@fmcompany.co.za
Subject: URGENT: Air conditioning not working on Level 2 East Wing
Date: 2026-02-28T09:15:00+02:00
Message-ID: <abc123@centrecourt.co.za>

Hi,

The air conditioning on Level 2 East Wing has been off since this morning.
It's extremely hot and staff are struggling to work.

This was reported under FNBFW:45678 last week but the issue has returned.

Please send someone urgently.

Regards,
John Smith
Legal Department
ext. 2145
```

### Layer 2: n8n Extract & Parse (Raw Fields Only)

Phase 134 moved all classification to the backend AI agent. n8n now extracts raw IMAP fields only — no keyword matching, no urgency detection, no CC analysis.

**Output fields extracted:**

| Field | Value | Source |
|-------|-------|--------|
| `from_email` | john.smith@centrecourt.co.za | IMAP header |
| `from_name` | John Smith | IMAP header |
| `subject` | URGENT: Air conditioning not working on Level 2 East Wing | IMAP header |
| `body_plain` | (full email body, max 5000 chars) | IMAP text/textAsHtml |
| `message_id` | `<abc123@centrecourt.co.za>` | IMAP header |
| `in_reply_to` | (empty) | IMAP header |
| `references` | (empty) | IMAP header |
| `received_at` | 2026-02-28T09:15:00Z | IMAP date |
| `existing_reference` | FNBFW:45678 | Regex match in body |
| `site_id` | site-002 | Domain mapping (centrecourt.co.za) |
| `attachment_count` | 0 | IMAP attachments |

**Filters applied (before POST):**
- System email filter: skip noreply, mailer-daemon, etc.
- Noise filter: skip OOO, newsletters, auto-replies

### Layer 3: SENTINEL Backend — Auth + Dedup (Deterministic)

**Step 3a: Auth chain**
- `X-Sentry-API-Key` → validated against `sentry_bot_api_key` ✓
- `X-Sentry-Secret` → validated against `sentry_webhook_secret` ✓
- `email_intake_enabled` → True ✓

**Step 3b: Duplicate/follow-up check**
- `existing_reference = "FNBFW:45678"` → query `email_intakes` table
- Found existing intake from 2026-02-20 with same reference
- **Action:** `linked_existing` — link as follow-up, bump `follow_up_count`

### Layer 4: SENTINEL Backend — AI Agent Classification + Reply

**Step 4a: BMS enrichment** (feeds into agent prompt)
1. Building name: "Centre Court" (from `buildings.code = 'site-002'`)
2. Active alerts: `S002-AHU-B1-001` has "high supply air temp" alert
3. Recent work orders: WO-2026-0221 "AHU filter replacement" (scheduled)
4. Equipment health: 2 at-risk assets in building
5. Agent memory: "Level 2 East Wing HVAC issues tend to be AHU-B1-001 related"

**Step 4b: AI Agent call** (`EmailIntakeAgent.classify_and_reply()`)

The agent receives the raw email + BMS context and performs classification, location extraction, completeness scoring, and reply generation in a single LLM call.

**LLM fallback chain:** OpenAI gpt-4.1-nano → Claude → keyword matching

**Agent result:**

```json
{
  "discipline": "HVAC",
  "sub_category": "Too hot",
  "specialty": "hvac",
  "priority": "high",
  "location_desk": null,
  "location_floor": "L2",
  "location_area": "East Wing",
  "phone": "ext. 2145",
  "issue_summary": "AC not working on Level 2 East Wing, follow-up to FNBFW:45678",
  "completeness": 0.90,
  "action": "auto_submit",
  "reply_text": "Dear John, thank you for following up on the air conditioning issue in Level 2 East Wing. Reference: {ref}. Our HVAC team has been notified and this has been escalated due to the recurring nature of the problem. We can see an active alert on the air handling unit serving your area. Kind regards,\nSENTINEL Building Management",
  "agent_model": "gpt-4.1-nano",
  "agent_latency_ms": 320
}
```

**Step 4c: Urgency escalation** (deterministic, post-agent)
- Agent priority: "high"
- Active critical alert on AHU-B1-001 → escalate to "critical"
- **Final urgency:** "critical"

**Step 4d: Work order creation** (always — WO number included in reply)
- Create Concept WO → `WO-2026-0456`
- Replace `{ref}` placeholder in agent reply with `WO-2026-0456`

### Layer 5: Threaded Reply

The backend sends a threaded SMTP reply with `In-Reply-To` and `References` headers matching the original email. The WO code is included in the subject line.

```
From: SENTINEL Work Orders <workorder@sentinel-ai.co.za>
To: John Smith <john.smith@centrecourt.co.za>
Subject: Re: URGENT: Air conditioning not working on Level 2 East Wing [WO-2026-0456]
In-Reply-To: <abc123@centrecourt.co.za>
References: <abc123@centrecourt.co.za>

Dear John, thank you for following up on the air conditioning issue in
Level 2 East Wing. Reference: WO-2026-0456. Our HVAC team has been
notified and this has been escalated due to the recurring nature of
the problem. We can see an active alert on the air handling unit
serving your area.

Kind regards,
SENTINEL Building Management
```

The reply is also sent as branded HTML with category badge and SENTINEL styling.

---

## Routing Decision Matrix

| Completeness Score | Route | What Happens |
|-------------------|-------|--------------|
| ≥ 0.85 | `auto_submit` | WO created, auto-reply sent |
| 0.60 – 0.84 | `request_info` | WO created, reply asks for missing details |
| < 0.60 | `manual_review` | WO created, queued for FM team triage |

**Note:** A Concept WO is always created regardless of route, so every reply includes a WO reference number.

## Dedup Priority Order

1. `existing_reference` match (e.g. FNBFW:12345)
2. `message_id` exact match (RFC 822 dedup)
3. Recent-window heuristic (same sender + site + category within 24h)

## Architecture: Before vs After (Phase 134)

```
BEFORE (Phase 131):
n8n (IMAP + keyword classify + urgency + CC analysis) → backend (taxonomy re-classify + regex location + score + template reply)

AFTER (Phase 134):
n8n (IMAP raw extract only) → backend (dedup → BMS enrich → AI Agent [classify + reply] → WO creation → threaded reply)
```

## LLM Cost

- Model: GPT-4.1-nano (~$0.0001/email)
- Fallback: keyword matching (zero cost)
- Target latency: < 500ms per classification
