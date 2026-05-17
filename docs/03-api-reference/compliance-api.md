---
title: "Compliance API"
type: "api-reference"
status: "active"
version: "1.0.0"
created: "2026-05-17"
updated: "2026-05-17"
tags: ["api", "compliance", "OHS", "fire-safety", "legionella", "electrical", "lift-safety"]
domain: "compliance"
audience: "developers"
complexity: "intermediate"
estimated_read_time: 10
---

# Compliance API Reference

Base path: `/api/compliance`

## Overview

The Compliance API provides endpoints for managing regulatory compliance across OHS, Fire Safety, Legionella Risk Management, Electrical Certificates, and Lift Safety.

## Common Types

### RiskLevel

```typescript
type RiskLevel = 'critical' | 'high' | 'medium' | 'marginal' | 'low'
```

**Note:** `marginal` was added in 2026-05-17 for Legionella 50-55°C transitional zone.

### AuditTrail

All compliance records include audit trail fields:

```typescript
interface AuditTrail {
  recorded_by?: string
  recorded_by_email?: string
  recorded_at: string  // ISO 8601
  updated_by?: string
  updated_at?: string  // ISO 8601
}
```

## Endpoints

### OHS Compliance

#### Generate OHS Checklist

```http
POST /api/compliance/ohs/checklist/generate
```

**Request Body:**
```json
{
  "site_code": "site-002",
  "zone_id": "Zone-100"
}
```

**Response:**
```json
{
  "id": "uuid",
  "site_code": "site-002",
  "zone_id": "Zone-100",
  "checklist_items": [...],
  "status": "pending",
  "recorded_by": "user@example.com",
  "recorded_at": "2026-05-17T10:00:00Z"
}
```

#### Complete OHS Checklist

```http
POST /api/compliance/ohs/checklist/{task_id}/complete
```

**Request Body:**
```json
{
  "findings": {
    "critical_issues": [],
    "recommendations": [],
    "completed_items": [...]
  }
}
```

### Fire Safety

#### List Fire Equipment

```http
GET /api/compliance/fire/equipment?site_code={site_code}&zone_id={zone_id}
```

**Query Parameters:**
- `site_code` (required): Site identifier
- `zone_id` (optional): Filter by zone

**Response:**
```json
{
  "equipment": [
    {
      "id": "uuid",
      "site_code": "site-002",
      "equipment_type": "extinguisher",
      "location_description": "L1 Corridor B",
      "last_inspection_date": "2026-04-15",
      "next_inspection_date": "2027-04-15",
      "status": "active",
      "recorded_by": "inspector@example.com",
      "recorded_at": "2026-04-15T10:00:00Z"
    }
  ]
}
```

#### Schedule Fire Inspection

```http
POST /api/compliance/fire/equipment/{equipment_id}/inspect
```

#### Record Pressure Test

```http
POST /api/compliance/fire/equipment/{equipment_id}/charge
```

**Request Body:**
```json
{
  "pressure": 150,
  "test_date": "2026-05-17"
}
```

### Legionella Risk Management

#### Assess Legionella Risk

```http
POST /api/compliance/legionella/assess
```

**Request Body:**
```json
{
  "tower_code": "CT-001",
  "water_temp": 35.5,
  "last_treatment": "2026-04-20"
}
```

**Risk Assessment Logic:**

| Water Temp | Days Since Treatment | Risk Level | Interval |
|------------|---------------------|------------|----------|
| 20-45°C | >30 | HIGH | 14 days |
| 20-45°C | ≤30 | MEDIUM | 30 days |
| 45-50°C | Any | MEDIUM | 30 days |
| 50-55°C | Any | MARGINAL | 60 days |
| <20°C or >55°C | Any | LOW | 90 days |

**Response:**
```json
{
  "id": "uuid",
  "tower_code": "CT-001",
  "water_temperature": 35.5,
  "risk_level": "medium",
  "days_since_treatment": 27,
  "next_treatment_date": "2026-06-16",
  "biocide_treatment_interval_days": 30,
  "recorded_by": "system",
  "recorded_at": "2026-05-17T10:00:00Z"
}
```

**Notes:**
- HIGH risk requires immediate attention (14-day treatment)
- MARGINAL risk (50-55°C) is a transitional zone requiring monthly monitoring
- LOW risk (<20°C or >55°C) is outside Legionella growth range

### Electrical Compliance

#### Track Electrical Certificate

```http
POST /api/compliance/electrical/certificate
```

**Request Body:**
```json
{
  "site_code": "site-002",
  "certificate_type": "CoC_new_installation",
  "issue_date": "2024-01-15",
  "certifying_body": "SABS Accredited Certifier",
  "scope": "Main Distribution Board"
}
```

**Auto-calculated Fields:**
- `expiry_date`: 5 years from issue date (administrative tracking only)

**Legal Disclaimer:**
Certificate validity is context-dependent per OHS Act / SANS 10142-1 and depends on installation type, occupancy changes, or DoL inspector discretion. The 5-year tracking is for administrative purposes only and does not constitute a legal validity determination.

#### Get Electrical Compliance Status

```http
GET /api/compliance/electrical/status?site_code={site_code}
```

**Response:**
```json
{
  "certificates": [
    {
      "id": "uuid",
      "site_code": "site-002",
      "certificate_type": "CoC_new_installation",
      "issue_date": "2024-01-15",
      "expiry_date": "2029-01-15",
      "certifying_body": "SABS",
      "status": "active",
      "recorded_by": "user@example.com",
      "recorded_at": "2024-01-15T10:00:00Z"
    }
  ]
}
```

### Lift Safety

#### Schedule Lift Inspection

```http
POST /api/compliance/lift/schedule
```

**Request Body:**
```json
{
  "lift_code": "LIFT-001",
  "inspection_type": "periodic_6monthly"
}
```

**Inspection Types:**
- `periodic_6monthly`: Standard 6-month cycle
- `annual_insurance`: Insurance compliance check
- `after_repair`: Post-repair inspection

#### Record Lift Test Results

```http
POST /api/compliance/lift/{lift_code}/test-results
```

**Request Body:**
```json
{
  "brake_load_test": true,
  "speed_governor_test": true,
  "emergency_stop_test": true
}
```

### Emergency Light Testing

#### Schedule Emergency Light Tests

```http
POST /api/compliance/emergency-light/schedule
```

**Request Body:**
```json
{
  "light_codes": ["EM-001", "EM-002"],
  "auto_test": true
}
```

**Schedule:** Daily auto-tests at 03:00-03:30 SAST (01:00-01:30 UTC)

#### Record Emergency Light Test

```http
POST /api/compliance/emergency-light/{light_code}/test
```

**Request Body:**
```json
{
  "battery_health_percent": 85,
  "test_result": "pass"
}
```

### Overall Compliance Status

#### Get Compliance Status

```http
GET /api/compliance/status?site_code={site_code}
```

**Response:**
```json
{
  "site_id": "site-002",
  "compliance_score_percent": 92,
  "critical_issues_count": 0,
  "high_risk_items_count": 2,
  "items_expiring_30days": 1,
  "overdue_inspections": 0,
  "summary": {
    "ohs_status": "compliant",
    "fire_status": "compliant",
    "electrical_status": "expiring_soon",
    "legionella_status": "compliant",
    "lift_status": "compliant"
  }
}
```

## Error Responses

### 400 Bad Request

```json
{
  "error": "Invalid risk_level value",
  "message": "Risk level must be one of: low, medium, marginal, high",
  "field": "risk_level"
}
```

### 404 Not Found

```json
{
  "error": "Risk assessment not found",
  "message": "Risk assessment {id} not found"
}
```

### 409 Conflict

```json
{
  "error": "Constraint violation",
  "message": "Invalid risk_level for database CHECK constraint"
}
```

## Database Migrations

### Migration 092: Add MARGINAL Risk Level

For existing deployments:

```sql
-- Update risk_level constraint to include 'marginal'
ALTER TABLE legionella_risk_assessment
DROP CONSTRAINT IF EXISTS legionella_risk_assessment_risk_level_check;

ALTER TABLE legionella_risk_assessment
ADD CONSTRAINT legionella_risk_assessment_risk_level_check
CHECK (risk_level IN ('low', 'medium', 'marginal', 'high'));
```

**Important:** Run this migration BEFORE deploying backend code with MARGINAL RiskLevel enum, or inserts will fail.

## Rate Limits

- Standard API rate limits apply
- Bulk operations limited to 100 items per request

## Related Documentation

- [Compliance Module](../04-features/compliance-module.md)
- [Safety Interlocks Engine](../06-safety-compliance/safety-interlocks-engine.md)
