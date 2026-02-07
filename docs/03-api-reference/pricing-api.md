---
title: "Risk-Based Pricing API"
type: "reference"
status: "approved"
version: "1.0.0"
created: "2026-02-07"
updated: "2026-02-07"
author: "Sentinel Development Team"
tags: ["api", "pricing", "risk", "contracts"]
domain: "bms"
audience: "developers"
complexity: "intermediate"
estimated_read_time: 8
---

# Risk-Based Pricing API

Phase 52 pricing endpoints for quote generation and what-if analysis.

Base path: `/api/pricing`

## POST `/api/pricing/calculate-quote`

Calculate a recommended monthly fee using multi-factor pricing.

**Request Body:**
```json
{
  "building_id": "site-002",
  "equipment_codes": ["S002-CHILLER-B1-001", "S002-AHU-L2-003"],
  "sla_tier": "standard",
  "contract_months": 12,
  "include_benchmarks": true
}
```

**Response:**
```json
{
  "request_id": "uuid",
  "recommended_fee_zar": 4218.75,
  "fee_range_zar": {"min": 3796.88, "target": 4218.75, "max": 4640.63},
  "cost_breakdown": {
    "base_cost": 1500,
    "condition_adjustment": 1125,
    "age_adjustment": 450,
    "risk_buffer": 75,
    "sla_adjustment": 225,
    "margin": 843.75
  },
  "risk_factors": ["Aging equipment: S002-CHILLER-B1-001 (16 years)"],
  "assumptions": ["Contract duration: 12 months", "SLA tier: standard"],
  "market_comparison": {"similar_contracts": 2, "average_monthly_fee": 16000},
  "valid_until": "2026-03-09"
}
```

## POST `/api/pricing/calculate-price-range`

Return min/max range based on a variance percentage.

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| variance_pct | float | No | Variance percent (0-50, default 10) |

## GET `/api/pricing/equipment-types`

List equipment types with available budget templates.

## GET `/api/pricing/sla-tiers`

List SLA tiers with pricing multipliers and margin targets.

## GET `/api/pricing/config`

Return pricing configuration (multipliers and margin targets).

## GET `/api/pricing/health`

Health check for pricing service.
