# Demo Simulation Control

> **Phase:** 53 - SENTINEL Asset Management Workflow
> **Status:** Complete
> **Last Updated:** 2026-02-02

## Overview

Demo endpoints for triggering equipment health warnings and resetting to healthy state. Used for demonstrations and testing the alert → Telegram → Risk Intelligence workflow.

## Architecture

```
POST /simulation/demo/trigger-warnings
    │
    ├── Select N random healthy equipment (Supabase)
    ├── Update health_score → 65, status → 'warning'
    ├── Create alert in Supabase (AlertRepository)
    ├── Send Telegram notification (AlertNotifier)
    └── Generate prediction (PredictionGenerator)

POST /simulation/demo/reset-to-healthy
    │
    ├── Reset all equipment → health_score=92, status='normal'
    ├── Resolve all active alerts (AlertRepository)
    └── Resolve all active predictions (PredictionRepository)
```

## Files

| File | Purpose |
|------|---------|
| `services/equipment_alert_service.py` | Central orchestrator for alert creation with Telegram |
| `api/simulation.py` | Demo trigger/reset endpoints |
| `api/alerts.py` | Modified to query Supabase in addition to JSON + simulation |

## API Endpoints

### Trigger Warnings

```bash
POST /api/simulation/demo/trigger-warnings?site_code=site-002&count=3
```

**Parameters:**
- `site_code` (string, default: "site-002") - Building code
- `count` (int, 1-10, default: 3) - Number of equipment to degrade

**Response:**
```json
{
  "success": true,
  "message": "Triggered warnings for 3 equipment",
  "equipment": [
    {
      "id": "uuid",
      "name": "Air Handling Unit L1",
      "old_health": 92,
      "new_health": 65,
      "alert_id": "uuid",
      "telegram_sent": true
    }
  ]
}
```

### Reset to Healthy

```bash
POST /api/simulation/demo/reset-to-healthy?site_code=site-002
```

**Parameters:**
- `site_code` (string, default: "site-002") - Building code

**Response:**
```json
{
  "success": true,
  "message": "Reset 45 equipment to healthy, resolved 3 alerts and 3 predictions",
  "equipment_reset": 45,
  "alerts_resolved": 3,
  "predictions_resolved": 3
}
```

## Workflow Integration

When equipment transitions to warning:

1. **Supabase Update** - Equipment health_score and status updated
2. **Alert Created** - Stored in `alerts` table with severity, message, equipment_id
3. **Telegram Notification** - Sent via Sentry bot to FM team chat
4. **Prediction Generated** - Stored in `predictions` table for Risk Intelligence card
5. **Dashboard Updates** - Risk Intelligence card shows highest risk equipment

## Usage

```bash
# Trigger 3 warnings on Sandton (site-002)
curl -X POST "http://localhost:9095/api/simulation/demo/trigger-warnings?site_code=site-002&count=3"

# Check alerts appear
curl "http://localhost:9095/api/alerts?site_id=site-002"

# Check Risk Intelligence card in dashboard
# Frontend should show "Highest Risk - Immediate Attention Required"

# Reset everything back to healthy
curl -X POST "http://localhost:9095/api/simulation/demo/reset-to-healthy?site_code=site-002"
```

## Environment Variables

For Telegram notifications to work:

```bash
SENTRY_BOT_TOKEN=<telegram-bot-token>
SENTRY_FM_CHAT_ID=<telegram-chat-id>
```

If not configured, notifications are logged to console instead.

## Related Documentation

- [Sentry Integration](../SENTRY_INTEGRATION.md)
- [Alert System](./alerts-system.md)
- [Health Scoring System](./health-scoring-system.md)
