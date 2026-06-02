---
title: "Alerts API"
type: "reference"
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

# Alerts API

## Overview

Alerts API endpoints - SENTINEL Integration.

## Endpoints

### GET /alerts

List active alerts with optional site/severity/equipment filters.

**Query Parameters:**
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `site_id` | string | — | Filter by site UUID |
| `equipment_id` | string | — | Filter by equipment UUID |
| `severity` | string | — | Filter by severity (warning, critical, etc.) |
| `status` | string | active | Filter by status |
| `category` | string | — | Filter by alert class |
| `limit` | int | 50 | Maximum alerts to return |

**Response:**
```json
{
  "total": 423,
  "alerts": [...],
  "by_severity": { "warning": 423 },
  "pending_recommendations": 0
}
```

`total` is the count of ALL matching alerts before the `limit` slice. The `alerts` array contains only `limit` items, but `total` reflects the full unfiltered count for accurate badge/KPI display. `by_severity` also reflects the full count, not the limited subset.

### GET /alerts/{alert_id}

Get a single alert by ID.

### GET /sites/{site_id}/alerts

Site-scoped alert query. Same filters as GET /alerts.

### GET /anomalies

List anomaly events.

### POST /alerts

Create a new alert.

### POST /alerts/{alert_id}/acknowledge

Acknowledge (dismiss) an alert.

### POST /alerts/{alert_id}/dispatch

Dispatch an alert to a notification channel.

### GET /anomalies/{anomaly_id}

Get single anomaly detail.

## Implementation

For full details, see: `backend/app/api/alerts.py`
