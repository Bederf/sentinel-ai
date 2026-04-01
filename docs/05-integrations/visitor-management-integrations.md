---
title: "Visitor Management Integrations"
type: "spec"
status: "approved"
version: "1.0.0"
created: "2026-04-01"
updated: "2026-04-01"
tags: ["visitor-management", "integrations", "outlook", "whatsapp", "active-directory", "c-cure"]
related: ["../04-features/176-visitor-management.md", "../03-api-reference/visitor-management-api.md", "./ccure-9000-integration.md"]
domain: "integrations"
audience: "operators"
complexity: "intermediate"
estimated_read_time: 12
---

# Visitor Management Integrations

Four external systems integrated with the SENTINEL Visitor Management Module.

---

## 1. Microsoft Outlook / Exchange (via Microsoft Graph API)

**Purpose:** Auto-create Visit records when a calendar event with an external attendee is created.

**Component:** `app/services/outlook_calendar_service.py`

### Configuration

```bash
OUTLOOK_CLIENT_ID=your-azure-app-client-id
OUTLOOK_CLIENT_SECRET=your-azure-app-secret
OUTLOOK_TENANT_ID=your-tenant-id
OUTLOOK_USER_EMAIL=reception@company.com
INTERNAL_EMAIL_DOMAINS=company.com,fnb.co.za
```

### How It Works

1. Background scheduler polls every 5 minutes
2. MS Graph API: `GET /me/events?$filter=...`
3. Filter: events where `start >= now` and `attendees` contain external email
4. External attendee = not in `INTERNAL_EMAIL_DOMAINS` list
5. Extract: organizer (host), attendee (visitor), start, end, location
6. Location string → building_id via BuildingMap lookup
7. Create Visit with UUID token + 6-digit PIN + QR code
8. Send visitor confirmation email with QR + PIN

### Graceful Degradation

If `OUTLOOK_*` env vars are not set, the service logs a warning and skips polling. No crash. The module operates in manual registration mode only.

### Azure App Registration

Requires a Microsoft Entra ID (Azure AD) app with:
- `Calendars.Read` permission (delegated)
- `Mail.Read` permission (delegated)
- Redirect URI: `http://localhost`

---

## 2. Twilio WhatsApp

**Purpose:** Notify hosts when visitors arrive and receive YES/NO approval replies.

**Component:** `app/integrations/whatsapp_service.py` (shared with Sentry notifications)

### Configuration

```bash
TWILIO_ACCOUNT_SID=AC...
TWILIO_AUTH_TOKEN=...
TWILIO_WHATSAPP_FROM=whatsapp:+14155238886
PUBLIC_BASE_URL=https://your-public-url.com   # Required for webhook signature verification
```

### Visitor Arrival Notification (outbound)

Sent when a visitor completes registration at reception.

```
🔔 Visitor Alert

John Doe has arrived at Fairlands Head Office.

Meeting: 09:00 - 10:00

Reply YES to approve or NO to deny.
```

### Host YES/NO Reply (webhook inbound)

**Endpoint:** `POST /api/whatsapp/whatsapp/visit/reply`

**Security:** Every inbound request is verified with Twilio HMAC-SHA1 signature. Requests with invalid signatures return 403.

**Signature verification:** `HMAC-SHA1(TWILIO_AUTH_TOKEN, request_url + sorted_form_params)` compared against `X-Twilio-Signature` header.

### Mobile Number Normalisation

Handles all SA mobile formats:
- `+27821234567` → `+27821234567`
- `0821234567` → `+27821234567` (leading 0 replaced with +27)
- `whatsapp:+27821234567` → `+27821234567` (prefix stripped)

---

## 3. C-CURE 9000 (Access Control Enforcement)

**Purpose:** Issue and revoke visitor access badges.

**Component:** `app/services/ccure/ccure_adapter.py` (extended in Phase 176)

### Configuration

No additional configuration — uses existing `CCURE_*` env vars from Phase 58.

### Access Group Mapping

| Building | Access Group |
|----------|-------------|
| site-001 (Fairlands) | `VISITOR_FAIRLANDS` |
| site-002 (Sandton) | `VISITOR_SANDTON` |
| site-003 (Centurion) | `VISITOR_CENTURION` |
| site-004 (Umhlanga) | `VISITOR_UMHLANGA` |
| Default | `VISITOR_DEFAULT` |

### Methods Added in Phase 176

```python
ccure_adapter.issue_visitor_access(visit: Visit) -> dict
# Returns: {success: bool, card_id: str, message: str}
# Modes: seeded (demo) or live (victor Web Service API)

ccure_adapter.revoke_visitor_access(visit_id: UUID) -> dict
# Returns: {success: bool, message: str}
```

### Seeded Mode (Default)

When `CCURE_HOST` is not set, adapter returns a demo response:
```json
{"success": true, "card_id": "VIS-550E8400", "message": "Demo access issued"}
```

---

## 4. Active Directory (Mock / JSON Lookup)

**Purpose:** Resolve host email → host name, mobile, department.

**Component:** `app/services/active_directory_service.py`

### Configuration

Data source: `backend/app/data/host_directory.json`

### Data Format

```json
{
  "hosts": [
    {
      "email": "tdineka@fnb.co.za",
      "name": "Thandi Dineka",
      "department": "Facilities Management",
      "mobile": "+27821234567",
      "site": "site-001"
    }
  ]
}
```

### Methods

| Method | Returns |
|--------|---------|
| `get_host_details(email)` | `{name, mobile, department}` or `None` |
| `get_host_by_mobile(mobile)` | Reverse lookup by normalized mobile |
| `is_internal_email(email)` | True if domain in `INTERNAL_EMAIL_DOMAINS` |

### Production Replacement

For production, replace the JSON lookup with a real LDAP query or Microsoft Graph `/users` endpoint. The interface (`ActiveDirectoryService`) remains the same — only the data source changes.

---

## 5. SMTP / Email (Visitor Confirmation)

**Purpose:** Send visitor confirmation with QR code and PIN when Visit is created.

**Component:** `app/services/visitor_email_service.py`

### Configuration

```bash
SMTP_HOST=smtp.company.com
SMTP_PORT=587
SMTP_USER=visitor@company.com
SMTP_PASSWORD=...
SMTP_FROM=SENTINEL Reception <visitor@company.com>
DEV_EMAIL_LOG=true   # Log emails instead of sending (dev mode)
```

### Email Content

**Subject:** `Your visit to Fairlands Head Office on Wednesday 01 April 2026`

**Body (HTML):**
- Host name
- Building name
- Date and time window
- Embedded QR code (inline image)
- 6-digit PIN (prominently displayed)
- Instructions: "Present this at reception on arrival"

### Dev Mode

When `DEV_EMAIL_LOG=true`, email content is logged at INFO level instead of being sent. No sending failure occurs.
