---
title: Commercial Data Model
category: integrations
version: 11.0
status: planned
audience: [developers, architects]
last_updated: 2026-01-31
---

# Commercial Data Model

v11.0 FM Commercial Intelligence data model - contracts, SLAs, budgets, and profitability tracking.

## Entity Relationship Diagram

```
                                    ┌─────────────────┐
                                    │  organizations  │
                                    │─────────────────│
                                    │ id              │
                                    │ code            │
                                    │ name            │
                                    │ tier            │
                                    │ status          │
                                    └────────┬────────┘
                                             │
                                             │ 1:N
                                             ▼
┌─────────────────┐              ┌─────────────────────┐
│    buildings    │◄─────────────│      contracts      │
│─────────────────│   1:N        │─────────────────────│
│ id              │              │ id                  │
│ code            │              │ code                │
│ name            │              │ organization_id  ───┼───► organizations
│ address         │              │ building_id      ───┼───► buildings
│ ...             │              │ monthly_fee_zar     │
└────────┬────────┘              │ start_date          │
         │                       │ end_date            │
         │ 1:N                   │ status              │
         ▼                       └──────────┬──────────┘
┌─────────────────┐                         │
│    equipment    │                         │ 1:N
│─────────────────│                         ▼
│ id              │              ┌─────────────────────┐
│ code            │              │     sla_terms       │
│ building_id  ───┼───► bldg     │─────────────────────│
│ name            │              │ id                  │
│ type            │              │ contract_id      ───┼───► contracts
│ health_score    │              │ sla_type            │
│ ...             │              │ target_value        │
└────────┬────────┘              │ penalty_type        │
         │                       └──────────┬──────────┘
         │                                  │
         │                                  │ 1:N
         │                                  ▼
         │                       ┌─────────────────────┐
         │                       │   sla_performance   │
         │                       │─────────────────────│
         │                       │ id                  │
         │                       │ contract_id         │
         │                       │ sla_term_id      ───┼───► sla_terms
         │                       │ actual_value        │
         │                       │ met_target          │
         │                       │ penalty_amount_zar  │
         │                       └─────────────────────┘
         │
         │                       ┌─────────────────────┐
         ├──────────────────────►│   asset_contracts   │
         │           N:M         │─────────────────────│
         │                       │ id                  │
         │                       │ contract_id      ───┼───► contracts
         │                       │ equipment_id     ───┼───► equipment
         │                       │ allocated_fee_zar   │
         │                       │ coverage_type       │
         │                       │ criticality         │
         │                       └─────────────────────┘
         │
         │                       ┌─────────────────────┐
         └──────────────────────►│condition_assessments│
                     1:N         │─────────────────────│
                                 │ id                  │
                                 │ equipment_id     ───┼───► equipment
                                 │ building_id      ───┼───► buildings
                                 │ contract_id      ───┼───► contracts
                                 │ overall_score       │
                                 │ failure_risk        │
                                 │ recommended_budget  │
                                 └─────────────────────┘


┌─────────────────────┐              ┌─────────────────────┐
│      budgets        │              │contract_profitability│
│─────────────────────│              │─────────────────────│
│ id                  │              │ id                  │
│ contract_id      ───┼───► contr   │ contract_id      ───┼───► contracts
│ budget_year         │              │ period_year         │
│ labor_budget_zar    │              │ period_month        │
│ parts_budget_zar    │              │ total_revenue_zar   │
│ total_budget_zar    │              │ total_direct_cost   │
│ total_actual_zar ◄──┼─── work     │ gross_margin_zar    │
│ variance_zar        │    orders   │ sla_penalties_zar   │
└─────────────────────┘              │ net_margin_zar      │
                                     └─────────────────────┘


                 ┌─────────────────────┐
                 │     work_orders     │
                 │─────────────────────│
                 │ id                  │
                 │ contract_id      ───┼───► contracts (NEW FK)
                 │ equipment_id     ───┼───► equipment
                 │ building_id      ───┼───► buildings
                 │ labor_cost_zar      │──┐
                 │ parts_cost_zar      │  │ Aggregates to
                 │ total_cost_zar      │──┼─► budgets.actual_zar
                 │ ...                 │  │
                 └─────────────────────┘  │
                                          │
                                          └─► contract_profitability
```

## Data Flow

### 1. Onboarding Flow (SIMBIOT)

```
create_building()
    │
    ├── Basic contract fields (client_code, monthly_fee, start_date)
    │
    └── Creates: buildings record + contracts record (draft)

add_building_contract()
    │
    ├── Detailed SLA terms (uptime %, response times, penalties)
    │
    ├── Condition assessment (initial scoring, risk, budget)
    │
    └── Creates: sla_terms + condition_assessments + budgets
```

### 2. Operational Flow

```
Work Order Completed
    │
    ├── labor_cost_zar, parts_cost_zar logged
    │
    ├── Updates: budgets.actual_zar (via trigger)
    │
    └── Updates: contract_profitability (monthly roll-up)

SLA Event (Downtime/Response)
    │
    ├── Measured against sla_terms.target_value
    │
    ├── Updates: sla_performance record
    │
    └── If missed: penalty_amount_zar calculated
```

### 3. Profitability Calculation

```
Monthly Revenue
    │
    ├── contracts.monthly_fee_zar
    ├── callout_revenue (from work_orders beyond included)
    └── parts_markup (parts sold - cost)

Monthly Costs
    │
    ├── SUM(work_orders.labor_cost_zar)
    ├── SUM(work_orders.parts_cost_zar)
    └── subcontractor_cost

Gross Margin = Revenue - Direct Costs
Net Margin = Gross Margin - SLA Penalties
```

## Key Tables

| Table | Purpose | Key Fields |
|-------|---------|------------|
| `organizations` | FM clients (, Nedbank) | code, name, tier |
| `contracts` | Building contracts | monthly_fee_zar, start/end_date |
| `sla_terms` | SLA definitions | uptime %, response hours, penalties |
| `asset_contracts` | Asset-level fee allocation | allocated_fee_zar, coverage_type |
| `condition_assessments` | Initial/annual assessments | overall_score, failure_risk |
| `budgets` | Budget vs actual tracking | budget_zar, actual_zar, variance |
| `sla_performance` | SLA compliance tracking | actual_value, met_target, penalty |
| `contract_profitability` | Monthly P&L per contract | revenue, costs, margins |

## Linking to Existing Tables

### buildings (001_initial_schema.sql)
- `contracts.building_id` references buildings
- `condition_assessments.building_id` references buildings

### equipment (001_initial_schema.sql)
- `asset_contracts.equipment_id` references equipment
- `condition_assessments.equipment_id` references equipment

### work_orders (004_additional_tables.sql)
- Added `work_orders.contract_id` FK to contracts
- Work order costs aggregate to budgets and profitability

## Views

| View | Purpose |
|------|---------|
| `v_active_contracts` | Active contracts with org/building details |
| `v_budget_summary` | Budget vs actual by contract and year |
| `v_contract_profitability_dashboard` | Profitability metrics for dashboard |

## Migration

File: `supabase/migrations/018_commercial_schema.sql`

Adds:
- 8 new tables (organizations, contracts, sla_terms, asset_contracts, condition_assessments, budgets, sla_performance, contract_profitability)
- 3 views
- FK from work_orders to contracts
- All appropriate indexes and triggers

## Mock Data Pattern

For demo mode, JSON files in `backend/app/data/commercial/`:
- `organizations.json` - Sample FM clients
- `contracts.json` - Sample contracts with SLA terms
- `budgets.json` - Sample budget allocations

Production uses Supabase tables.

---
*v11.0 FM Commercial Intelligence - Phase 48*
