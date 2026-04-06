---
title: "Workflow API"
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

# Workflow API

## Overview

SENTINEL Workflow API Endpoints

## Current Behavior (Implemented)

- `POST /api/workflow/onboard-asset` now persists onboarding metadata to `equipment.operating_data.onboarding`.
- Workflow state transitions are persisted to `workflow_events` with `trigger_type: "workflow_state"` and transition details.
- `GET /api/workflow/status/{equipment_id}` resolves the latest persisted workflow state from `workflow_events` before using in-memory fallback.
- Dashboard workflow state logic treats assets with no onboarding evidence as `onboarding` (not `healthy`).
- Onboarding metadata persistence is durable; baseline capture is attempted and degrades gracefully when the deployed `equipment_baselines` schema is behind.

## Endpoints

- POST /onboard-asset
- GET /status/{equipment_id}
- POST /trigger-inspection
- POST /validate-repair
- POST /triggers/ml-anomaly
- POST /triggers/baseline-deviation
- POST /triggers/critical-deficiency
- POST /triggers/repair-completed
- POST /triggers/validate-effectiveness
- GET /triggers/history

... and 8 more endpoints


## Implementation

For full details, see: `backend/app/api/workflow.py`
