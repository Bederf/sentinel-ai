# Plant Room Notification Pipeline

**Phase:** 146 | **Version:** 1.0 | **Status:** Active

## Overview

The Plant Room Notification Pipeline converts Desigo BMS fault emails into classified, stored alarms with instant WhatsApp group notification. The pipeline is designed for plant-room and building-services teams who need real-time visibility into critical equipment faults.

```
Desigo BMS --> noreply@fnb.co.za email --> n8n IMAP trigger
  --> SENTINEL /api/plant/alerts/ingest
    --> Parse subject (equipment, alarm type, status)
    --> Classify severity (very_critical / critical / non_critical / cleared)
    --> Detect equipment category (hvac, power, fire_safety, etc.)
    --> Save alarm (Supabase -> JSON fallback)
    --> Send WhatsApp notification (n8n webhook)
```

## API Reference

### POST /api/plant/alerts/ingest

Parse and ingest a Desigo fault email.

**Request body:**
```json
{
  "from_address": "noreply@fnb.co.za",
  "subject": "AHU B2-AHU-01 Fail Status (Fault)",
  "body": "Building: Fairland 2\nEquipment: AHU B2-AHU-01\nAlarm: Fail Status High",
  "received_at": "2026-03-07T10:30:00Z",
  "site_id": "FLN02"
}
```

**Responses:**

| Code | Meaning |
|------|---------|
| 200  | Alarm ingested successfully |
| 400  | Empty subject |
| 403  | Sender not authorised (does not match DESIGO_SENDER_EMAIL) |
| 409  | Duplicate alarm within dedup window (1 hour) |

**200 Response:**
```json
{
  "alarm_id": "uuid-here",
  "severity": "critical",
  "equipment": "AHU B2-AHU-01",
  "notified": true,
  "cleared": false
}
```

### GET /api/plant/alerts

Return recent alarms for a site.

**Query parameters:**

| Param   | Type   | Default         | Description |
|---------|--------|-----------------|-------------|
| site_id | string | PLANT_SITE_ID   | Site identifier |
| limit   | int    | 50              | Max alarms to return |

### GET /api/plant/alerts/{alarm_id}

Return a single alarm by ID. Returns 404 if not found.

### POST /api/plant/alerts/{alarm_id}/acknowledge

Mark an alarm as acknowledged/notified.

**Response:**
```json
{
  "alarm_id": "uuid-here",
  "acknowledged": true
}
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| PLANT_ALERTS_ENABLED | false | Master switch -- must be true to register the router |
| DESIGO_SENDER_EMAIL | noreply@fnb.co.za | Authorised sender address for email validation |
| WHATSAPP_WEBHOOK_URL | (empty) | n8n webhook URL for WhatsApp delivery |
| WHATSAPP_GROUP_ID | (empty) | Target WhatsApp group ID |
| PLANT_SITE_ID | FLN02 | Default site identifier for alarms |
| PLANT_BUILDING_NAME | Fairland 2 | Default building name for alarms |

## Severity Classification

| Severity | Condition | WhatsApp Format |
|----------|-----------|-----------------|
| very_critical | fire_safety + body contains "High" | Red circle x2 -- "URGENT -- Immediate response required" |
| critical | Body contains "High" OR empty body (safe default) | Red circle -- "Action required" |
| non_critical | Everything else | Yellow circle -- "For attention" |
| cleared | Status = "Normal" AND alarm type contains "Fail"/"Fault" | Green check -- "Fault resolved" |

## Equipment Category Mapping

| Pattern (case-insensitive) | Category |
|---------------------------|----------|
| fire damper, fd  | fire_safety |
| generator, gen, ats, ups | power |
| ahu, fcu, fpu, fan, reheat, ohs, chiller | hvac |
| pump | mechanical |
| temperature, humidity | monitoring |
| (no match) | unknown |

## n8n IMAP Workflow Configuration

### Trigger Node: IMAP Email

| Setting | Value |
|---------|-------|
| Type | IMAP Email Trigger |
| Host | (your IMAP server) |
| Port | 993 |
| User | (service account) |
| Password | (service account password) |
| Mailbox | INBOX |
| SSL | true |
| Poll interval | Every 1 minute |

### Filter Node: Desigo Sender

```json
{
  "conditions": {
    "string": [
      {
        "value1": "={{ $json.from }}",
        "operation": "equals",
        "value2": "noreply@fnb.co.za"
      }
    ]
  }
}
```

### HTTP Request Node: POST to SENTINEL

| Setting | Value |
|---------|-------|
| Method | POST |
| URL | http://localhost:9095/api/plant/alerts/ingest |
| Body Type | JSON |
| Body | See below |

```json
{
  "from_address": "={{ $json.from }}",
  "subject": "={{ $json.subject }}",
  "body": "={{ $json.text }}",
  "received_at": "={{ $json.date }}"
}
```

### Error Handling

- 403 (wrong sender): n8n filter should prevent this; if it occurs, check DESIGO_SENDER_EMAIL setting
- 409 (duplicate): Safe to ignore -- alarm already processed
- 500 (save failed): Check Supabase connectivity and JSON fallback directory permissions

## WhatsApp Message Examples

### Very Critical (fire_safety + High)

```
🔴🔴 *URGENT -- Immediate response required*

*Site:* FLN02
*Building:* Fairland 2
*Equipment:* Fire Damper B2-FD-01
*Alarm:* Fail Status
*Status:* Fault
*Category:* fire_safety
*Received:* 2026-03-07 10:30
```

### Critical (High severity)

```
🔴 *Action required*

*Site:* FLN02
*Building:* Fairland 2
*Equipment:* AHU B2-AHU-01
*Alarm:* Fail Status
*Status:* Fault
*Category:* hvac
*Received:* 2026-03-07 10:30
```

### Non-Critical

```
🟡 *For attention*

*Site:* FLN02
*Equipment:* Temperature Sensor T-101
*Alarm:* High Temp
*Status:* Active
*Category:* monitoring
*Received:* 2026-03-07 10:30
```

### Cleared

```
✅ *Fault resolved*

*Site:* FLN02
*Equipment:* AHU B2-AHU-01
*Alarm:* Fail Status
*Status:* Normal
*Category:* hvac
*Received:* 2026-03-07 10:35
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Router not registered | Set PLANT_ALERTS_ENABLED=true in .env and restart backend |
| 403 on ingest | Check DESIGO_SENDER_EMAIL matches the actual Desigo sender address |
| WhatsApp not sending | Verify WHATSAPP_WEBHOOK_URL is set and reachable from the backend host |
| Duplicates not detected | Dedup window is 1 hour; alarms older than that are treated as new |
| Alarms not persisting | Check Supabase connectivity or JSON fallback directory permissions at backend/app/data/plant/ |
| n8n not triggering | Verify IMAP credentials, mailbox name, and poll interval in n8n |
