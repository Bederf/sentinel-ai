# Optimization API

## Overview

Optimization API endpoints for HVAC load shedding, AI optimization, profile management, and M&V verification.

## Endpoints

### Core Optimization
- POST /optimization/analyze — Analyze building and generate recommendations
- POST /optimization/approve — Apply approved recommendations
- GET /optimization/status/{site_id} — Get optimization status + monthly savings
- POST /optimization/toggle/{site_id} — Enable/disable optimization

### Load Shedding
- GET /optimization/scenarios
- GET /optimization/eskom-status
- GET /optimization/eskom-status/{site_id}
- GET /optimization/eskomsepush/areas
- GET /optimization/eskomsepush/allowance
- GET /optimization/thermal-runway
- POST /optimization/analyze-load-shedding

### Profile Management
- GET /optimization/profiles — List available profiles
- GET /optimization/settings/{site_id} — Get site profile config
- PUT /optimization/settings/{site_id} — Update profile + control tier
- POST /optimization/settings/{site_id}/zone-override — Add zone override
- DELETE /optimization/settings/{site_id}/zone-override/{zone_id} — Remove zone override

### Measurement & Verification (M&V)
- GET /optimization/mv/summary/{site_id} — Get M&V verification stats (accuracy, outcomes, rollbacks)
- POST /optimization/mv/verify — Trigger pending verifications (call periodically)

## Tier Routing (Phase 82)

Recommendations are routed through a confidence-based tier system that determines
what action is taken for each recommendation.

### Routing Tiers

| Tier | Confidence | Behavior |
|------|-----------|----------|
| **Blocked** | < 0.30 | Rejected entirely. Cannot be approved. |
| **Tier 1 (Advisory)** | 0.30 - 0.60 | Display only. Cannot be approved in enforce mode. |
| **Tier 2 (Approval)** | 0.60 - 0.85 | Requires human approval before execution. |
| **Tier 3 (Auto-Execute)** | >= 0.85 | Auto-applied in auto_execute mode (safety permitting). |

FCU systems have a confidence cap of 0.45, forcing them to advisory-only routing.

### Control Tier Execution Matrix

| Routing Tier | monitor | human_in_loop | auto_execute |
|---|---|---|---|
| Blocked | blocked | blocked | blocked |
| Tier 1 | log_only | advisory | advisory |
| Tier 2 | log_only | pending_approval | pending_approval |
| Tier 3 | log_only | pending_approval | auto_execute |

### New Response Fields

The following fields are added to `/optimization/analyze` and `/optimization/status/{site_id}` responses:

| Field | Type | Description |
|-------|------|-------------|
| `control_tier` | string | Active control tier: monitor, human_in_loop, auto_execute |
| `routing_summary` | object | Counts of blocked, advisory, pending_approval, auto_executed |
| `routing_details` | array | Per-recommendation tier, action, effective_confidence |
| `execution_summary` | object | attempted/succeeded/failed counts for auto-applied items |

### Approval Hardening

When `optimization_routing_enforced=True`:
- **Blocked** recommendations cannot be approved (rejected with reason)
- **Advisory** recommendations cannot be approved (rejected with reason)
- **Already auto-executed** items return idempotent success
- Only **tier2_approval** and **tier3 pending_approval** items can be approved

### Shadow Mode vs Enforce Mode

- **Shadow mode** (default, `optimization_routing_enforced=False`): Routing decisions are computed and logged but do not change existing behavior. Auto-apply uses legacy `site_mode` logic.
- **Enforce mode** (`optimization_routing_enforced=True`): Routing decisions control auto-apply and approval paths. Only tier3+safety-passed items are auto-applied.

## Implementation

- Core optimization: `backend/app/api/ai_recommendations.py`
- Load shedding: `backend/app/api/optimization.py`
- Tier router: `backend/app/services/optimization_tier_router.py`
- M&V service: `backend/app/services/mv_verification_service.py`
- AI optimizer: `backend/app/services/ai_optimizer.py`

## Key Changes (2026-02-19)

- Monthly savings now use schedule-aware projection (actual weekdays + TOU-weighted rates)
- Recommendations include `data_quality` field showing live vs defaulted sensor data
- M&V endpoints added for post-action verification of predicted vs actual savings
- Tier routing added: confidence-based routing with shadow/enforce modes (Phase 82)
- Status endpoint includes `routing_summary` and `control_tier` from last recommendation
- Approval path hardened to reject blocked/advisory in enforce mode
