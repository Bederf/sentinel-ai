---
title: "Contract Management Module"
type: "feature"
status: "implemented"
version: "1.0.0"
created: "2026-02-06"
updated: "2026-02-06"
author: "SENTINEL Development Team"
tags: ["contracts", "sla", "budget", "profitability", "commercial", "mcp"]
domain: "general"
audience: "developers"
complexity: "intermediate"
estimated_read_time: 12
phase: "48"
---

# Contract Management Module

Commercial intelligence for FM contract portfolio management -- organizations, contracts, SLA compliance, budget tracking, condition assessments, and profitability analysis.

**Demo Site:** Sandton City Office Tower (site-002) --  Commercial Property full-maintenance contract

## Overview

Phase 48 delivers a complete contract management system across 4 plans:

| Plan | Layer | Features |
|------|-------|----------|
| 48-01 | Data Layer | Pydantic models, 5 Supabase repositories, contract service |
| 48-02 | MCP Tools | 3 SIMBIOT MCP tools, demo contract data (contract.json) |
| 48-03 | API Endpoints | 23 REST endpoints under /api/contracts/ |
| 48-04 | Frontend | Dashboard page with portfolio KPIs, SLA tracking, budget visualization |

## Architecture

### Data Model

Built on the `018_commercial_schema.sql` migration with these core entities:

- **Organization** -- FM client (e.g.,  Commercial Property) with tier (platinum/gold/silver/bronze)
- **Contract** -- Service agreement with type (comprehensive/reactive/hybrid/preventive), lifecycle status, monthly fee
- **SLA Term** -- Performance targets (uptime, response time, resolution time, PPM completion, first-fix rate) with penalty exposure
- **Asset Contract** -- Equipment-to-contract assignment with coverage type and pricing basis
- **Budget** -- Annual budgets with 5 cost categories (labor, parts, consumables, subcontractor, callout)
- **Condition Assessment** -- Building/equipment condition scores (mechanical, electrical, structural, controls, documentation)
- **SLA Performance** -- Actual SLA measurement records
- **Contract Profitability** -- Revenue vs costs with margin analysis

### Backend Stack

**Models:** `backend/app/models/contract.py` -- 15 enums, 8 entity models with Create/Update variants

**Repositories (Supabase):**
- `organization_repository.py` -- CRUD + tier/status filter
- `contract_repository.py` -- CRUD + building/org/status filters
- `sla_terms_repository.py` -- CRUD + bulk insert/delete by contract
- `budget_repository.py` -- CRUD + spending summary aggregation
- `condition_assessment_repository.py` -- CRUD + latest for equipment

**Service:** `backend/app/services/contract_service.py` -- Contract lifecycle management (draft -> active -> suspended -> expired), SLA term management, budget variance calculation

**API Router:** `backend/app/api/contracts.py` -- 23 endpoints (see [API Reference](../03-api-reference/contracts-api.md))

### MCP Tools (SIMBIOT)

3 tools added to `backend/app/mcp/simbiot_server.py`:

| Tool | Description |
|------|-------------|
| `get_contracts` | Retrieve contracts with building/org/status filters, optional SLA inclusion |
| `add_building_contract` | Create contract.json + update building.json with dual-write |
| `get_contract_profitability` | Margin analysis with portfolio summary and at-risk flagging |

### Frontend

**API Client:** `frontend/src/lib/contractApi.ts` -- Typed client for all 23 endpoints with auth headers and error handling

**Page:** `frontend/src/pages/ContractManagementPage.tsx` -- 4-section dashboard:

1. **Portfolio Overview** -- KPI cards (total contracts, active contracts, monthly revenue, average margin)
2. **Contract List** -- Sortable table with status filtering (all/active/draft/expired), click-to-select
3. **SLA Tracking** -- Per-term cards with traffic-light indicators (met/at risk/breached), progress bars, penalty exposure summary
4. **Budget Overview** -- Budget vs actual horizontal bars by category, variance percentages, profitability snapshot, condition assessment scores

**Navigation:** Accessible via "Contracts" in the sidebar base menu (always visible, no module gating)

## API Endpoints

23 endpoints under `/api/contracts/`:

### Organizations (4)
- `GET /api/contracts/organizations` -- List organizations (optional tier filter)
- `POST /api/contracts/organizations` -- Create organization
- `GET /api/contracts/organizations/{code}` -- Get organization by code
- `PATCH /api/contracts/organizations/{code}` -- Update organization

### Contracts (6)
- `GET /api/contracts/` -- List contracts (optional building_id, status filters)
- `POST /api/contracts/` -- Create contract
- `GET /api/contracts/summary` -- Portfolio summary (total, active, revenue, margin)
- `GET /api/contracts/{id}` -- Get contract by code
- `PATCH /api/contracts/{id}` -- Update contract
- `PATCH /api/contracts/{id}/status` -- Change contract status

### SLA Terms (4)
- `GET /api/contracts/{id}/sla-terms` -- List SLA terms for contract
- `POST /api/contracts/{id}/sla-terms` -- Add SLA term
- `PATCH /api/contracts/{id}/sla-terms/{term_id}` -- Update SLA term
- `DELETE /api/contracts/{id}/sla-terms/{term_id}` -- Delete SLA term

### Equipment Assignments (3)
- `GET /api/contracts/{id}/equipment` -- List assigned equipment
- `POST /api/contracts/{id}/equipment` -- Assign equipment to contract
- `DELETE /api/contracts/{id}/equipment/{equipment_id}` -- Unassign equipment

### Budgets (3)
- `GET /api/contracts/{id}/budgets` -- List budgets (optional year filter)
- `POST /api/contracts/{id}/budgets` -- Create budget
- `GET /api/contracts/{id}/budgets/{year}/variance` -- Budget variance report

### Condition Assessments (3)
- `GET /api/contracts/assessments` -- List assessments (optional building_id filter)
- `POST /api/contracts/assessments` -- Create assessment
- `GET /api/contracts/assessments/equipment/{equipment_id}` -- Get latest for equipment

## Demo Data

Demo contract data seeded in `backend/app/data/buildings/site-002/contract.json`:

- **Client:**  Commercial Property (enterprise tier)
- **Contract:** CON--S002-2024, full maintenance, R285,000/month
- **SLA Terms:** 3 terms (uptime 99.0%, response time 4h, resolution time 24h)
- **Budget:** R245,000/month across labor, parts, subcontractors, overhead
- **Condition:** Overall 3.8/5.0 (mechanical 3.5, electrical 4.0, structural 4.2)
- **Profitability:** 23.5% gross margin, 13.9% net margin

The frontend falls back to this demo data when the API is unavailable.

## Dashboard Sections

### 1. Portfolio Overview

Four KPI cards showing aggregate metrics:

| Card | Metric | Demo Value |
|------|--------|------------|
| Total Contracts | Count of all contracts | 1 |
| Active Contracts | Count with status=active | 1 |
| Monthly Revenue | Sum of monthly_fee_zar | R285,000 |
| Average Margin | Mean gross_margin_percent | 23.5% |

Color-coded status summary bar shows counts by status (active=green, expiring=amber, expired=red).

### 2. Contract List

Sortable table with columns: Client, Building, Type, Status, Monthly Fee, SLA Score, Margin %.

- **Status filter** buttons: All, Active, Draft, Expired
- **Sortable columns** with direction indicators (client, type, status, fee, margin)
- **Click to select** a contract -- reveals SLA Tracking and Budget panels
- **SLA Score** shown as progress bar with fraction (e.g., 2/3 terms met)
- **Margin** color-coded: green (>=15%), amber (>=10%), red (<10%)

### 3. SLA Tracking

Appears when a contract is selected. Shows per-SLA-term cards:

- **Metric type** (System Uptime, Response Time, Resolution Time)
- **Status badge** (Met=green, At Risk=amber, Breached=red)
- **Target vs Current** values with progress bar
- **Penalty exposure** per breach and monthly cap
- **Penalty Exposure Summary** card with max monthly exposure and YTD penalties incurred

### 4. Budget Overview

Appears alongside SLA tracking. Includes:

- **Budget summary KPIs**: Monthly budget, monthly fee, risk buffer percentage
- **Budget vs Actual bars**: Horizontal bar chart per category (Labor, Parts, Subcontractors, Overhead) with variance percentages -- green for under budget, red for over
- **Profitability snapshot**: YTD revenue, YTD costs, gross margin, net margin
- **Condition Assessment**: Overall/mechanical/electrical/structural scores with risk factor tags
- **Client Contact**: Name, email, phone, contract dates, auto-renew and payment terms badges

## Key Files

### Backend
- `backend/app/models/contract.py` -- Domain models and enums
- `backend/app/database/repositories/organization_repository.py`
- `backend/app/database/repositories/contract_repository.py`
- `backend/app/database/repositories/sla_terms_repository.py`
- `backend/app/database/repositories/budget_repository.py`
- `backend/app/database/repositories/condition_assessment_repository.py`
- `backend/app/services/contract_service.py` -- Business logic
- `backend/app/api/contracts.py` -- REST API router (23 endpoints)
- `backend/app/mcp/simbiot_server.py` -- 3 MCP tools
- `backend/app/data/buildings/site-002/contract.json` -- Demo data

### Frontend
- `frontend/src/lib/contractApi.ts` -- Typed API client
- `frontend/src/pages/ContractManagementPage.tsx` -- Dashboard page
- `frontend/src/lib/navigation.ts` -- Navigation entry (base menu)
- `frontend/src/App.tsx` -- View routing

## Related Documentation

- [Contract Management API Reference](../03-api-reference/contracts-api.md) -- Full endpoint documentation
- [Module Registry](../13-modules/module-registry.md) -- Bolt-on module system
- [Service Feedback System](service-feedback-system.md) -- Technician feedback that feeds into contract SLA tracking
