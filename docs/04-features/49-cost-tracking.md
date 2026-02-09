---
title: "Cost Tracking & Budget Actuals"
type: "feature"
status: "implemented"
version: "1.0.0"
created: "2026-02-08"
updated: "2026-02-08"
author: "SENTINEL Development Team"
tags: ["costs", "budget", "work-orders", "commercial"]
domain: "bms"
audience: "developers"
complexity: "intermediate"
estimated_read_time: 6
phase: "49"
---

# Cost Tracking & Budget Actuals

Phase 49-08 captures actual costs from completed work orders and writes them into monthly contract budgets. This feeds profitability dashboards and variance analysis.

## Scope

- **Labor + parts actuals** sourced from `work_orders` in the selected period.
- **Auto-create monthly budget row** (contract-wide) if none exists.
- **Backfill missing contract_id** on work orders when asset assignment indicates the contract.

## Data Flow

1. `POST /api/contracts/{contract_id}/budgets/capture-actuals`
2. Gather contract assets → equipment IDs
3. Aggregate completed work orders for period
4. Update budget actuals (labor, parts; others default to 0)
5. Evaluate variance thresholds → emit budget alerts

## Variance Alerts

Alerts are stored in `budget_alerts` and triggered when spend percentage crosses thresholds:
- Warning: `warning_threshold_pct` (default 80%)
- Critical: `critical_threshold_pct` (default 100%)
Alerts are generated for contract-wide budgets and equipment-type budgets.
Contract UI supports alert filtering, pagination, and status actions (acknowledge/resolve).

## Reporting

- Budget report endpoint returns monthly breakdown, totals, and equipment-type rollups
- CSV/PDF exports available for finance workflows (API)
- Budget Reports UI available for contract-level exports and summaries
- JSON export available from Budget Reports UI (client-side)

## Assumptions

- If a work order has `total_cost_zar` but no `labor_cost_zar` or `parts_cost_zar`, total is assigned to labor.
- Subcontractor, callout, and consumables actuals are tracked when explicit fields are added to work orders or service records.

## Files

- Service: `backend/app/services/cost_capture_service.py`
- Repository: `backend/app/database/repositories/work_order_repository.py`
- API: `backend/app/api/contracts.py`
- DB Trigger: `supabase/migrations/051_work_order_budget_trigger.sql`
- Reporting: `backend/app/services/budget_reporting_service.py`
- Export: `backend/app/services/budget_export_service.py`
- Alerts: `backend/app/services/budget_variance_service.py`
- UI: `frontend/src/pages/BudgetReportPage.tsx`
- Contract UI: `frontend/src/pages/ContractManagementPage.tsx`

## Known Gaps

- Work order costs do not yet separate subcontractor/callout/consumables.
- Service records do not capture labor hours or parts used as structured costs.
- Automated triggers from work orders to budgets are implemented, but only for labor/parts.
- Variance alerts for equipment-type budgets are best-effort; depends on equipment-type budget entries.
