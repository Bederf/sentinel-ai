# Email Intake Pipeline — Centre Court 5-Layer Trace

**Phase:** 131 | **Version:** 131.1 | **Date:** 2026-02-27

## Trace Scenario: HVAC Complaint from Centre Court Tenant

This trace follows a real-world FM email through all 5 layers of the SENTINEL email intake pipeline.

---

### Layer 1: Email Arrives (n8n Webhook)

**Input:** Email from tenant at Centre Court (site-002)

```
From: john.smith@centrecourt.co.za
To: helpdesk@fmcompany.co.za
CC: facilities.manager@fmcompany.co.za
Subject: URGENT: Air conditioning not working on Level 2 East Wing
Date: 2026-02-27T09:15:00+02:00
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

### Layer 2: n8n Extract & Parse (Code Node)

**Output fields detected:**

| Field | Value | Source |
|-------|-------|--------|
| `from_email` | john.smith@centrecourt.co.za | Header |
| `from_name` | John Smith | Header |
| `existing_reference` | FNBFW:45678 | Regex match in body |
| `site_id` | site-002 | Reference prefix mapping |
| `urgency_boost` | true | "URGENT" in subject |
| `cc_count` | 1 | CC header |
| `has_manager_cc` | true | "facilities.manager" matches pattern |
| `message_id` | abc123@centrecourt.co.za | Header |

### Layer 3: AI Classification (GPT-4.1-nano)

**AI response:**

```json
{
  "site_id": "site-002",
  "zone_hint": "Level 2 East Wing",
  "floor_hint": "Level 2",
  "issue_category": "hvac",
  "issue_summary": "Air conditioning not working on Level 2 East Wing, reported previously under FNBFW:45678",
  "urgency": "high",
  "from_department": "Legal",
  "from_phone": "ext. 2145"
}
```

### Layer 4: SENTINEL Backend Processing

**Step 4a: Auth chain**
- `X-Sentry-API-Key` → validated against `sentry_bot_api_key` ✓
- `X-Sentry-Secret` → validated against `sentry_webhook_secret` ✓
- `email_intake_enabled` → True ✓

**Step 4b: Duplicate/follow-up check**
- `existing_reference = "FNBFW:45678"` → query `email_intakes` table
- Found existing intake from 2026-02-20 with same reference
- **Action:** `linked_existing` — link as follow-up, bump `follow_up_count`

**Step 4c: BMS enrichment** (5 layers, even for follow-ups context is useful)
1. Building name: "Centre Court" (from `buildings.code = 'site-002'`)
2. Active alerts: `S002-AHU-B1-001` has "high supply air temp" alert
3. Recent work orders: WO-2026-0221 "AHU filter replacement" (scheduled)
4. Equipment health: 2 at-risk assets in building
5. Agent memory: "Level 2 East Wing HVAC issues tend to be AHU-B1-001 related"

**Step 4d: Urgency escalation**
- Input urgency: "high" (from AI)
- `urgency_boost=true` → already "high", no change
- `has_manager_cc=true` → already "high", no change
- Active critical alert on AHU-B1-001 → escalate to "critical"
- **Final urgency:** "critical"

### Layer 5: Response to n8n

```json
{
  "success": true,
  "intake_id": "e7f8a9b0-1234-5678-9abc-def012345678",
  "action_taken": "linked_existing",
  "concept_ref": "FNBFW:45678",
  "bms_context": {
    "building_name": "Centre Court",
    "active_alerts": [
      {
        "equipment_id": "uuid-of-S002-AHU-B1-001",
        "severity": "critical",
        "message": "High supply air temperature"
      }
    ],
    "recent_work_orders": [
      {
        "code": "WO-2026-0221",
        "title": "AHU filter replacement",
        "priority": "medium",
        "status": "scheduled"
      }
    ],
    "equipment_health": {
      "at_risk_count": 2
    },
    "agent_notes": [
      {
        "key": "l2_east_hvac_pattern",
        "value": "Level 2 East Wing HVAC issues tend to be AHU-B1-001 related"
      }
    ]
  },
  "message": "Linked to existing reference FNBFW:45678",
  "reply_template": "Thank you for your follow-up regarding Air conditioning not working on Level 2 East Wing...",
  "urgency": "critical"
}
```

### Auto-Reply (n8n sends back to tenant)

```
Subject: Re: URGENT: Air conditioning not working on Level 2 East Wing

Dear John,

Thank you for your follow-up regarding Air conditioning not working on
Level 2 East Wing, reported previously under FNBFW:45678.

This has been linked to existing reference FNBFW:45678. Our team is
already working on it and will provide an update shortly.

Our building management system has detected an active alert on the
air handling unit serving your area, which confirms the issue.

Regards,
SENTINEL FM Helpdesk
```

---

## Routing Decision Matrix

| Completeness Score | Route | What Happens |
|-------------------|-------|--------------|
| ≥ 0.85 | `auto_submit` | Auto-create Concept WO (if enabled) |
| 0.60 – 0.84 | `request_info` | Ask sender for more details |
| < 0.60 | `manual_review` | Queue for FM team manual triage |

## Dedup Priority Order

1. `existing_reference` match (e.g. FNBFW:12345)
2. `message_id` exact match (RFC 822 dedup)
3. Recent-window heuristic (same sender + site + category within 24h)
