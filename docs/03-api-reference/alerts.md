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

- GET /alerts
- GET /alerts/{alert_id}
- GET /sites/{site_id}/alerts
- GET /anomalies
- POST /alerts
- POST /alerts/{alert_id}/acknowledge
- POST /alerts/{alert_id}/dispatch
- GET /anomalies/{anomaly_id}

## Implementation

For full details, see: `backend/app/api/alerts.py`
