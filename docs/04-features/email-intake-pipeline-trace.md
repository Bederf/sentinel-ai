---
title: "Email Intake Pipeline — Phase 184 Advisor Strategy"
type: "spec"
status: "active"
version: "184.0"
created: "2026-02-28"
updated: "2026-04-12"
tags: ["sentinel", "email-intake", "haiku", "opus", "bms-enrichment"]
related: ["../05-integrations/n8n-email-pipeline.md"]
domain: "bms"
audience: "all"
complexity: "intermediate"
estimated_read_time: 12
---

# Email Intake Pipeline — Haiku+Opus Advisor Strategy (Phase 184)

**Phase:** 184 | **Version:** 184.0 | **Date:** 2026-04-12 | **Strategy:** Advisor Pattern (Haiku executor + Opus advisor)

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

n8n extracts raw IMAP fields only — no classification, no urgency detection. All intelligence moved to Python backend (Phase 184 classifier service).

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

### Layer 4: SENTINEL Backend — BMS Enrichment + Haiku+Opus Classification

**Step 4a: BMS enrichment** (live data context)
1. Site lookup: "site-002" → Centre Court (UUID: site-uuid-123)
2. Active alerts: 1 critical on `S002-AHU-B1-001` ("high supply air temp")
3. Equipment health: `S002-AHU-B1-001` health_score=45% (at-risk)
4. Recent work orders: `WO-2026-0221` "AHU filter replacement" (scheduled 2026-02-28)
5. Floor equipment: 3 items on Level 2 East Wing, 2 with alerts

**Step 4b: Haiku executor classification** (routine cases, ~95%)

Haiku directly classifies straightforward emails (~$0.001 per email):

```json
{
  "issue_description": "Air conditioning not working on Level 2 East Wing",
  "issue_category": "HVAC",
  "urgency": "high",
  "specific_location": "Level 2 East Wing",
  "equipment_mentioned": "air conditioning",
  "is_followup": true,
  "existing_reference": "FNBFW:45678",
  "missing_info": [],
  "summary": "AC down on L2E, follow-up to FNBFW:45678",
  "advisor_consulted": false,
  "classification_confidence": 0.95
}
```

**Step 4c: Opus advisor consulted?** (edge cases, ~5%)

Decision tree: if `confidence < 0.6` OR `missing_info.length > 2` OR `urgency == "critical"` → consult Opus.

In this case: confidence=0.95, no missing info, urgency=high → **Haiku solo, no Opus call**.

(Opus would be consulted on emails like: "Building feeling odd" (ambiguous) or "Strange noise + water smell + electrical burning" (multi-issue + safety) where max_uses=2 caps cost at ~$0.02).

**Step 4d: Urgency escalation** (deterministic, post-classification)
- Haiku result: "high"
- BMS data: active_alerts present → escalate "high" → "critical"
- **Final urgency:** "critical"

**Step 4e: Work order creation** (always)
- Create Concept WO → `WO-2026-0456`
- Concept payload includes: issue_category, urgency, location, equipment, active_alerts context

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

## Architecture: Phase 184 Advisor Strategy

```
n8n (IMAP raw extract)
  ↓ (POST to /api/sentry-email/intake)
backend:
  1. Auth validation (X-Sentry-API-Key)
  2. Dedup check (message_id, existing_reference)
  3. BMS enrichment (alerts, equipment, recent WOs)
  4. Haiku executor (routine: 95%, ~$0.001)
     ├─ Confidence >= 0.85 → auto_submit WO
     ├─ Confidence 0.60-0.84 → request_info
     └─ Confidence < 0.60 OR complex → fallback rules OR Opus advisor
  5. Opus advisor (complex cases: 5%, max_uses=2, ~$0.01)
  6. Urgency escalation (BMS alerts trigger high→critical)
  7. Concept WO creation (MRI Evolution API)
  8. Supabase email_intakes table audit
  ↓
n8n outbound (auto-reply email)
```

## LLM Cost Breakdown

| Case | Model | Cost per email | Frequency |
|------|-------|---|---|
| Routine (Haiku solo) | claude-haiku-4-5 | ~$0.001 | 95% |
| Complex (Haiku + Opus) | claude-haiku-4-5 + claude-opus-4-6 | ~$0.01 | 3% |
| Fallback (no API) | keyword rules | $0.00 | 2% |
| **Average** | | **~$0.0015** | — |

**vs baseline:** GPT-4.1-nano (~$0.0001) costs less, but Haiku+Opus provides higher accuracy + safety filtering for ambiguous/multi-issue emails.

**Target latency:** < 2 seconds per classification (p95)
