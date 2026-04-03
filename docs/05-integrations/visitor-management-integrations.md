---
title: "Visitor Management Integrations"
type: "spec"
status: "approved"
version: "1.2.0"
created: "2026-04-01"
updated: "2026-04-03"
tags: ["visitor-management", "integrations", "outlook", "google-calendar", "whatsapp", "active-directory", "c-cure"]
related: ["../04-features/176-visitor-management.md", "../03-api-reference/visitor-management-api.md", "./ccure-9000-integration.md"]
domain: "integrations"
audience: "operators"
complexity: "intermediate"
estimated_read_time: 15
---

# Visitor Management Integrations

Five external systems integrated with the SENTINEL Visitor Management Module.

---

## 1. Google Calendar (via Google Calendar API + Cloud Pub/Sub)

**Purpose:** Auto-create Visit records when a Google Calendar event with an external attendee is created or updated.

**Components:**
- `app/services/google_calendar_service.py` — Google Calendar API + Pub/Sub webhook handling
- `app/api/google_calendar_webhook_endpoint.py` — webhook receiver with channel validation
- `~/.sentry/gateway/credentials/gmail_token.json` — OAuth2 token store (auto-refreshed)
- `~/.sentry/gateway/credentials/google.json` — Desktop app OAuth2 client config

### Accept-First Flow

Google Calendar uses **Accept-First** — the QR code is **not sent** on initial invite. The visitor must accept the invite first.

```
METHOD=REQUEST (new invite)  → Visit status = PENDING  → no email sent
METHOD=REPLY + PARTSTAT=ACCEPTED → Visit status = CREATED → QR email sent
METHOD=REPLY + PARTSTAT=DECLINED → Visit status = CANCELLED → no email sent
```

### Configuration

```bash
GOOGLE_WEBHOOK_URL=https://bms.sentinel-ai.co.za/api/webhooks/google/calendar
GOOGLE_PUBSUB_TOPIC=sentinel-calendar-notifications
INTERNAL_EMAIL_DOMAINS=fnb.co.za,sentinel.bms,sentinel-ai.co.za
```

### Webhook URL

`https://bms.sentinel-ai.co.za/api/webhooks/google/calendar`

This must be registered as the push notification address in Google Cloud Pub/Sub. Run `GoogleCalendarService().ensure_channel(GOOGLE_WEBHOOK_URL)` once to register the watch channel (auto-refreshed every 7 days by the background scheduler).

### How It Works (Webhook — Primary)

1. `ensure_channel()` creates a Google Cloud Pub/Sub topic and registers a calendar watch on `primary` calendar
2. Watch channel stored in `data/google_channel_store.json` (channel_id → resource_id mapping)
3. Google delivers push notifications to `POST /api/webhooks/google/calendar` in real-time
4. Webhook validates `channelId` against stored channels
5. Event ID extracted from `resourceUri`, queued via FastAPI BackgroundTasks
6. `GoogleCalendarService.handle_webhook_notification()` fetches full event from Google Calendar API
7. External attendee detected via `INTERNAL_DOMAINS` list
8. `external_event_id = "gcal-" + eventId` stored on Visit — prevents duplicates on webhook retry
9. If visitor already accepted (PARTSTAT=accepted) at creation time → status=CREATED and QR email sent immediately
10. Channel renewed hourly by background scheduler (expires every 7 days)

### How It Works (Polling — Backup)

Background scheduler runs `poll_recent_events()` every 5 minutes as backup if webhooks miss events.

### OAuth2 Setup

1. Create a **Desktop app** OAuth client in Google Cloud Console
2. Run the auth URL generator (see `app/services/google_calendar_service.py`)
3. Authorize at `http://localhost` — code appears in address bar after redirect
4. Save token to `~/.sentry/gateway/credentials/gmail_token.json`

```bash
# Required scopes
https://www.googleapis.com/auth/calendar.readonly
https://www.googleapis.com/auth/calendar.events
```

### Google Cloud Pub/Sub Topic

Topic: `projects/aimthelaw-465707/topics/sentinel-calendar-notifications`

The topic is created automatically by `ensure_channel()` if it doesn't exist.

---

## 2. Microsoft Outlook / Exchange (via Microsoft Graph API)

**Purpose:** Auto-create Visit records when a calendar event with an external attendee is created.

**Primary (Phase 177):** Real-time webhook subscription — no polling delay.

**Components:**
- `app/services/graph_subscription_service.py` — subscription lifecycle (create, renew)
- `app/api/graph_webhook_endpoint.py` — webhook receiver with validation handshake
- `app/services/graph_event_processor.py` — event processing with idempotency

### Accept-First Flow

Microsoft Graph also uses **Accept-First** — same as Google Calendar above.

```
METHOD=REQUEST (new invite)  → Visit status = PENDING  → no email sent
METHOD=REPLY + PARTSTAT=ACCEPTED → Visit status = CREATED → QR email sent
METHOD=REPLY + PARTSTAT=DECLINED → Visit status = CANCELLED → no email sent
```

### Configuration

```bash
OUTLOOK_CLIENT_ID=your-azure-app-client-id
OUTLOOK_CLIENT_SECRET=your-azure-app-secret
OUTLOOK_TENANT_ID=your-tenant-id
OUTLOOK_USER_EMAIL=reception@company.com
INTERNAL_EMAIL_DOMAINS=company.com,fnb.co.za
GRAPH_WEBHOOK_URL=https://your-domain.com/api/webhooks/graph/events
```

### How It Works (Webhook — Primary)

1. On startup: `GraphSubscriptionService` creates or restores a Graph subscription (`/me/events`)
2. Microsoft Graph delivers notifications to `POST /api/webhooks/graph/events` in real-time
3. Webhook validates `clientState` and `subscriptionId` against stored values
4. Event ID extracted from resource path, queued via FastAPI BackgroundTasks
5. `process_graph_event` fetches full event from Graph API
6. External attendees detected via `INTERNAL_EMAIL_DOMAINS` list
7. `external_event_id` (Graph event ID) stored on Visit — prevents duplicate creation on webhook retry
8. Created/updated/deleted events handled idempotently
9. Visit confirmation email enriched with host name, building name, meeting subject, map link
10. Subscription renewed hourly (within 24h of expiry) by background scheduler

### How It Works (Polling — Fallback)

1. Background scheduler polls every 5 minutes
2. MS Graph API: `GET /me/events?$filter=...`
3. Filter: events where `start >= now` and `attendees` contain external email
4. External attendee = not in `INTERNAL_EMAIL_DOMAINS` list
5. Extract: organizer (host), attendee (visitor), start, end, location
6. Location string → building_id via BuildingMap lookup
7. Create Visit with UUID token + 6-digit PIN + QR code
8. Send visitor confirmation email with QR + PIN

### Graceful Degradation

If `OUTLOOK_*` env vars are not set, the webhook subscription service logs a warning and skips startup creation. Polling also skips. The module operates in manual registration mode only.

If `GRAPH_WEBHOOK_URL` is not set, the subscription service cannot create webhooks — polling fallback remains active.

### Azure App Registration

Requires a Microsoft Entra ID (Azure AD) app with:
- `Calendars.Read` permission (delegated)
- `Mail.Read` permission (delegated)
- Redirect URI: `http://localhost`

For webhook delivery, the app also needs:
- `offline_access` scope (to receive long-lived tokens)
- The public `GRAPH_WEBHOOK_URL` must be reachable from the internet

---

## 3. Email Intake (IMAP — n8n Workflow)

**Purpose:** Parse ICS calendar invite emails polled from `info@` mailbox via n8n.

**Component:** `n8n/workflows/visitor-intake-imap.json` — n8n workflow (Phase 178)

### Accept-First Flow

Same Accept-First logic handled in n8n:

```
METHOD=REQUEST (new invite)  → POST /api/visits/internal → status=PENDING → no email
METHOD=REPLY + PARTSTAT=ACCEPTED → POST /api/visits/rsvp → status=CREATED → QR email sent
METHOD=REPLY + PARTSTAT=DECLINED → POST /api/visits/rsvp → status=CANCELLED
```

### Workflow Architecture

```
[Poll info@ Inbox] → [Parse ICS Invite] → [Filter: request]     → POST PENDING
                                            → [Filter: reply_accepted] → POST RSVP Accept → Build QR Email → Send Email
                                            → [Filter: reply_declined] → POST RSVP Decline
```

Each filter node (Code node) receives all parsed items and returns only the matching `_route` subset. The Switch node was replaced due to a bug in n8n 2.9.4 with `mode: expression` on empty input arrays.

### Internal Endpoints

| n8n Node | Endpoint | Purpose |
|----------|---------|---------|
| POST PENDING (REQUEST) | `POST /api/visits/internal` | Create PENDING visit |
| POST RSVP Accept | `POST /api/visits/rsvp` | Accept → CREATED + send QR email |
| POST RSVP Decline | `POST /api/visits/rsvp` | Decline → CANCELLED |

Auth: All three use `X-Sentry-API-Key: sentry-bot-RncXWQCYticUnuG06L4qnSUj-heKAeV0NnMdHOvIlKM3TNUv`

### Configuration

```bash
INTAKE_IMAP_USER=info@sentinel-ai.co.za   # n8n environment variable
SENTINEL_PUBLIC_URL=https://sentinel-ai.co.za
```

### Why No Switch Node?

n8n 2.9.4 has a bug where `Switch` node crashes with `Cannot read properties of undefined (reading 'push')` when `mode: expression` receives empty input (e.g., when all emails are filtered out by Parse ICS). The workaround uses three parallel Code filter nodes that each self-filter by `_route` value.

---

## 4. Twilio WhatsApp

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

## 5. C-CURE 9000 (Access Control Enforcement)

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

## 6. Active Directory (Mock / JSON Lookup)

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

## 7. SMTP / Email (Visitor Confirmation)

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
