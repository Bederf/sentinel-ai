---
title: "Contract Management API Reference"
type: "reference"
status: "approved"
version: "1.0.0"
created: "2026-02-06"
updated: "2026-02-06"
author: "Sentinel Development Team"
tags: ["api", "contracts", "sla", "budget", "organizations", "commercial"]
domain: "bms"
audience: "developers"
complexity: "intermediate"
estimated_read_time: 12
---

# Contract Management API Reference

Phase 48 Contract Management endpoints. Provides CRUD operations for FM commercial intelligence: organizations, contracts, SLA terms, equipment assignments, budgets, and condition assessments.

Base path: `/api/contracts`

## Organizations

### GET `/api/contracts/organizations`

List all FM client organizations with optional tier filter.

**Query Parameters:**
| Parameter | Type   | Required | Description                              |
|-----------|--------|----------|------------------------------------------|
| tier      | string | No       | Filter by tier: platinum, gold, silver, bronze |

**Response:**
```json
{
  "organizations": [
    {
      "id": "uuid",
      "code": "FNB",
      "name": "First National Bank Ltd",
      "trading_name": "FNB",
      "tier": "platinum",
      "status": "active",
      "primary_contact_name": "John Smith",
      "primary_contact_email": "john@fnb.co.za",
      "industry": "Banking",
      "created_at": "2026-01-15T00:00:00"
    }
  ],
  "count": 1
}
```

**Example:**
```bash
curl http://localhost:9095/api/contracts/organizations?tier=platinum
```

### POST `/api/contracts/organizations`

Create a new FM client organization.

**Request Body:**
```json
{
  "code": "FNB",
  "name": "First National Bank Ltd",
  "trading_name": "FNB",
  "registration_number": "1929/001225/06",
  "vat_number": "4000101186",
  "primary_contact_name": "John Smith",
  "primary_contact_email": "john@fnb.co.za",
  "primary_contact_phone": "+27 11 371 1234",
  "billing_email": "billing@fnb.co.za",
  "industry": "Banking",
  "tier": "platinum"
}
```

**Response:** `201 Created` with the created organization object.

**Example:**
```bash
curl -X POST http://localhost:9095/api/contracts/organizations \
  -H "Content-Type: application/json" \
  -d '{"code": "FNB", "name": "First National Bank Ltd", "tier": "platinum"}'
```

### GET `/api/contracts/organizations/{org_id}`

Get a single organization by UUID.

### PUT `/api/contracts/organizations/{org_id}`

Update an existing organization. Only provided fields are updated (partial update).

## Contracts

### GET `/api/contracts/`

List contracts with optional filters.

**Query Parameters:**
| Parameter       | Type   | Required | Description                         |
|-----------------|--------|----------|-------------------------------------|
| building_id     | string | No       | Filter by building UUID             |
| organization_id | string | No       | Filter by organization UUID         |
| status          | string | No       | Filter by status (draft, active, etc.) |
| limit           | int    | No       | Max results (default: 100, max: 500) |

**Response:**
```json
{
  "contracts": [
    {
      "id": "uuid",
      "code": "CON-FNB-2026-001",
      "organization_id": "uuid",
      "building_id": "uuid",
      "contract_type": "comprehensive",
      "start_date": "2026-01-01",
      "end_date": "2028-12-31",
      "monthly_fee_zar": 145000.00,
      "status": "active"
    }
  ],
  "count": 1
}
```

**Example:**
```bash
curl http://localhost:9095/api/contracts/?status=active
```

### POST `/api/contracts/`

Create a new contract linking an organization to a building. Always starts in `draft` status.

**Request Body:**
```json
{
  "code": "CON-FNB-2026-001",
  "organization_id": "org-uuid",
  "building_id": "building-uuid",
  "contract_type": "comprehensive",
  "start_date": "2026-01-01",
  "end_date": "2028-12-31",
  "monthly_fee_zar": 145000.00,
  "annual_escalation_pct": 6.0,
  "payment_terms_days": 30,
  "included_callouts_per_month": 8,
  "callout_rate_zar": 1200.00,
  "after_hours_rate_zar": 1800.00
}
```

**Response:** `201 Created` with the created contract object.

**Example:**
```bash
curl -X POST http://localhost:9095/api/contracts/ \
  -H "Content-Type: application/json" \
  -d '{"code": "CON-FNB-2026-001", "organization_id": "...", "building_id": "...", "start_date": "2026-01-01", "monthly_fee_zar": 145000}'
```

### GET `/api/contracts/{contract_id}`

Get a contract with summary info including organization, SLA count, and budget.

**Response:**
```json
{
  "contract": { "...contract fields..." },
  "sla_terms": [ "...SLA term objects..." ],
  "budget_summary": { "total_budget_zar": 500000, "total_actual_zar": 320000, "variance_zar": 180000 },
  "equipment_count": 12
}
```

### PUT `/api/contracts/{contract_id}`

Update contract fields (partial update). Cannot change status - use PATCH /status.

### PATCH `/api/contracts/{contract_id}/status`

Change contract lifecycle status.

**Request Body:**
```json
{
  "status": "active",
  "reason": "Approved by FM Director"
}
```

**Valid Transitions:**
| Current Status      | Target Status | Notes                    |
|---------------------|---------------|--------------------------|
| draft               | active        | Approves the contract    |
| pending_approval    | active        | Approves the contract    |
| active              | suspended     | Suspends with reason     |
| active              | expired       | Marks as expired         |
| active / suspended  | terminated    | Terminates with reason   |

**Example:**
```bash
curl -X PATCH http://localhost:9095/api/contracts/{id}/status \
  -H "Content-Type: application/json" \
  -d '{"status": "active", "reason": "Approved by FM Director"}'
```

### GET `/api/contracts/{contract_id}/summary`

Get comprehensive contract summary with organization, SLAs, budget, and equipment count.

## SLA Terms

### GET `/api/contracts/{contract_id}/sla-terms`

List all SLA terms for a contract.

**Response:**
```json
{
  "sla_terms": [
    {
      "id": "uuid",
      "contract_id": "uuid",
      "sla_type": "response_time",
      "target_value": 4.0,
      "target_unit": "hours",
      "priority": "critical",
      "measurement_period": "monthly",
      "penalty_type": "percentage",
      "penalty_value": 5.0,
      "is_active": true
    }
  ],
  "count": 1
}
```

### POST `/api/contracts/{contract_id}/sla-terms`

Add a single SLA term to a contract.

**Request Body:**
```json
{
  "contract_id": "uuid",
  "sla_type": "response_time",
  "target_value": 4.0,
  "target_unit": "hours",
  "priority": "critical",
  "measurement_period": "monthly",
  "penalty_type": "percentage",
  "penalty_value": 5.0,
  "penalty_cap_pct": 15.0
}
```

**SLA Types:** `uptime`, `response_time`, `resolution_time`, `ppm_completion`, `first_fix_rate`

**Example:**
```bash
curl -X POST http://localhost:9095/api/contracts/{id}/sla-terms \
  -H "Content-Type: application/json" \
  -d '{"contract_id": "...", "sla_type": "response_time", "target_value": 4, "target_unit": "hours", "priority": "critical"}'
```

### PUT `/api/contracts/sla-terms/{term_id}`

Update an existing SLA term. Only provided fields are updated.

### DELETE `/api/contracts/sla-terms/{term_id}`

Remove an SLA term. Returns `204 No Content` on success.

## Equipment Assignment

### GET `/api/contracts/{contract_id}/equipment`

List all equipment assigned to a contract with coverage details.

**Response:**
```json
{
  "equipment": [
    {
      "id": "uuid",
      "contract_id": "uuid",
      "equipment_id": "uuid",
      "allocated_fee_zar": 5000.00,
      "coverage_type": "full",
      "criticality": "critical",
      "equipment": {
        "code": "S002-CHILLER-B1-001",
        "name": "Primary Chiller",
        "type": "chiller"
      }
    }
  ],
  "count": 1
}
```

### POST `/api/contracts/{contract_id}/equipment`

Assign equipment to a contract with fee allocation and coverage configuration.

**Request Body:**
```json
{
  "contract_id": "uuid",
  "equipment_id": "equipment-uuid",
  "allocated_fee_zar": 5000.00,
  "fee_allocation_pct": 3.5,
  "coverage_type": "full",
  "annual_parts_cap_zar": 25000.00,
  "criticality": "critical"
}
```

**Coverage Types:** `full`, `parts_only`, `labor_only`, `excluded`

**Example:**
```bash
curl -X POST http://localhost:9095/api/contracts/{id}/equipment \
  -H "Content-Type: application/json" \
  -d '{"contract_id": "...", "equipment_id": "...", "coverage_type": "full", "criticality": "critical"}'
```

### DELETE `/api/contracts/{contract_id}/equipment/{equipment_id}`

Remove equipment from a contract. Returns `204 No Content` on success.

## Budgets

### GET `/api/contracts/{contract_id}/budgets`

List budget entries for a contract, optionally filtered by year.

**Query Parameters:**
| Parameter | Type | Required | Description       |
|-----------|------|----------|-------------------|
| year      | int  | No       | Filter by budget year |

**Response:**
```json
{
  "budgets": [
    {
      "id": "uuid",
      "code": "BUD-FNB-SANDTON-2026",
      "contract_id": "uuid",
      "budget_year": 2026,
      "labor_budget_zar": 200000.00,
      "parts_budget_zar": 150000.00,
      "total_budget_zar": 500000.00,
      "total_actual_zar": 320000.00,
      "variance_zar": 180000.00,
      "status": "approved"
    }
  ],
  "count": 1
}
```

### POST `/api/contracts/{contract_id}/budgets`

Create a budget entry for a contract period. Sets planned amounts by cost category.

**Request Body:**
```json
{
  "code": "BUD-FNB-SANDTON-2026",
  "contract_id": "uuid",
  "budget_year": 2026,
  "labor_budget_zar": 200000.00,
  "parts_budget_zar": 150000.00,
  "consumables_budget_zar": 50000.00,
  "subcontractor_budget_zar": 75000.00,
  "callout_budget_zar": 25000.00,
  "warning_threshold_pct": 80.0,
  "critical_threshold_pct": 100.0
}
```

### GET `/api/contracts/{contract_id}/budget-variance`

Get budget vs actual variance report for a contract year.

**Query Parameters:**
| Parameter | Type | Required | Description                    |
|-----------|------|----------|--------------------------------|
| year      | int  | Yes      | Budget year for variance calc  |

**Response:**
```json
{
  "contract_id": "uuid",
  "year": 2026,
  "total_budget_zar": 500000.00,
  "total_actual_zar": 320000.00,
  "variance_zar": 180000.00,
  "categories": {
    "labor": { "budget": 200000, "actual": 150000, "variance": 50000 },
    "parts": { "budget": 150000, "actual": 100000, "variance": 50000 }
  }
}
```

**Example:**
```bash
curl "http://localhost:9095/api/contracts/{id}/budget-variance?year=2026"
```

## Condition Assessments

### GET `/api/contracts/assessments`

List all condition assessments, optionally filtered by building.

**Query Parameters:**
| Parameter   | Type   | Required | Description            |
|-------------|--------|----------|------------------------|
| building_id | string | No       | Filter by building UUID |

### POST `/api/contracts/assessments`

Create a condition assessment for equipment or a building.

**Request Body:**
```json
{
  "code": "CA-001-2026-001",
  "equipment_id": "equipment-uuid",
  "assessment_type": "annual",
  "assessment_date": "2026-02-01",
  "assessor_name": "Mike Johnson",
  "assessor_company": "BMS Inspect (Pty) Ltd",
  "overall_score": 4,
  "mechanical_score": 4,
  "electrical_score": 3,
  "controls_score": 5,
  "findings": "Equipment in good condition. Minor wear on fan belt.",
  "estimated_failure_risk": "low",
  "estimated_annual_cost_zar": 15000.00,
  "recommended_budget_zar": 25000.00
}
```

**Assessment Types:** `initial`, `annual`, `handover`, `ad_hoc`

**Scores:** 1 (poor) to 5 (excellent)

### GET `/api/contracts/assessments/equipment/{equipment_id}`

Get the latest condition assessment for a piece of equipment.

## Error Responses

All endpoints return standard HTTP error codes:

| Code | Description                                            |
|------|--------------------------------------------------------|
| 400  | Invalid request data or failed business logic          |
| 404  | Resource not found                                     |
| 409  | Conflict (e.g., duplicate organization code)           |
| 500  | Internal server error                                  |

Error response format:
```json
{
  "detail": "Human-readable error message"
}
```
