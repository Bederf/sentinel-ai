---
title: "SLA Monitoring, Profitability, and Risk-Based Pricing"
type: "feature"
status: "implemented"
version: "1.0.0"
created: "2026-02-07"
updated: "2026-02-08"
author: "SENTINEL Development Team"
tags: ["sla", "profitability", "pricing", "commercial"]
domain: "general"
audience: "developers"
complexity: "intermediate"
estimated_read_time: 10
phase: "50-52"
---

# SLA Monitoring, Profitability, and Risk-Based Pricing

Phases 50–52 extend Contract Management with operational compliance tracking, portfolio profitability analytics, and actuarial pricing tools for quotes.

## Phase 50: SLA Monitoring & Alerts

**Goal:** Track SLA compliance across response time, resolution time, uptime, and preventive maintenance metrics. Detect breaches and compute clawbacks.

**Key Components**
- Models in `backend/app/models/contract.py`
  - `SLAMetricType`, `SLABreachSeverity`, `SLAComplianceStatus`
  - `SLAPerformanceWithCompliance`, `SLABreachEvent`
- Service: `backend/app/services/sla_compliance_service.py`
  - Period performance calculation
  - Breach detection & severity classification
  - Fixed/percentage/tiered clawback calculations
- Repository: `backend/app/database/repositories/sla_repository.py`
  - Supabase-first storage with JSON fallback
- API: `backend/app/api/contracts.py`
  - `/api/contracts/sla/performance/{contract_id}`
  - `/api/contracts/sla/breaches/{contract_id}`
  - `/api/contracts/sla/summary/{contract_id}`
  - `/api/contracts/sla/recalculate/{contract_id}`

## Phase 51: Profitability Dashboards & Analytics

**Goal:** Provide portfolio and per-contract profitability views, loss-leader analysis, and trend analytics.

**Key Components**
- Models in `backend/app/models/contract.py`
  - `PortfolioMetrics`, `ContractProfitabilityDetail`, `ProfitabilityTrend`, `LossLeaderAnalysis`
- Service: `backend/app/services/profitability_service.py`
  - Portfolio aggregation, per-contract breakdown, trends, loss leader detection
- API: `backend/app/api/contracts.py`
  - `/api/contracts/profitability/portfolio`
  - `/api/contracts/profitability/contract/{contract_id}`
  - `/api/contracts/profitability/loss-leaders`
  - `/api/contracts/profitability/trends/{contract_id}`
  - `/api/contracts/profitability/asset-roi/{contract_id}/{equipment_id}`
  - `/api/contracts/profitability/assets/{contract_id}`
  - `/api/contracts/profitability/report/{contract_id}`

**Frontend**
- `frontend/src/pages/ProfitabilityDashboardPage.tsx`
  - KPI cards, loss leader panel, contract table, margin trend chart
  - CSV/PDF export actions
- `frontend/src/lib/profitabilityApi.ts` API client

## Phase 52: Risk-Based Pricing

**Goal:** Generate pricing recommendations from equipment condition, age, ML risk, SLA tiers, and target margins.

**Key Components**
- Models: `backend/app/models/pricing.py`
  - `SLATier`, `ConditionFactor`, `RiskBuffer`, `QuoteRequest/Response`
- Service: `backend/app/services/pricing_engine.py`
  - Base cost + adjustments + margin, with market benchmarks
- API: `backend/app/api/pricing.py`
  - `/api/pricing/calculate-quote`
  - `/api/pricing/calculate-price-range`
  - `/api/pricing/what-if`
  - `/api/pricing/renewal`
  - `/api/pricing/benchmarks/{contract_id}`
  - `/api/pricing/equipment-types`
  - `/api/pricing/sla-tiers`
  - `/api/pricing/config`
  - `/api/pricing/health`

## Data Sources

- Contract monthly fees: `contracts.monthly_fee_zar`
- Cost actuals: `budgets.*_actual_zar`
- SLA terms: `sla_terms` + performance events
- Condition assessments: `condition_assessments`
- ML predictions: model outputs (failure probability, health score)

## Operational Notes

- SLA clawbacks are exposed for finance and fed into profitability calculations.
- Profitability analytics are best-effort when real cost data is incomplete; demo fallbacks exist.
- Pricing engine uses defaults if templates or ML predictions are unavailable.

## Known Gaps

- Overhead allocation is not yet modeled in budget actuals.
- Asset ROI uses even cost distribution when fee allocation is missing.
- Report export is basic PDF/CSV (Excel via CSV). Styled PDF exports pending.
