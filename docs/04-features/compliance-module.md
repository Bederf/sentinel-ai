---
title: "Compliance Module"
type: "feature"
status: "active"
version: "1.0.0"
created: "2026-05-17"
updated: "2026-05-17"
tags: ["compliance", "OHS", "fire-safety", "legionella", "electrical", "lift-safety", "audit-trail"]
domain: "compliance"
audience: "facilities-managers, compliance-officers, developers"
complexity: "intermediate"
estimated_read_time: 15
---

# Compliance Module

The SENTINEL Compliance Module provides comprehensive tracking and management of regulatory compliance across multiple domains: OHS Act, Fire Safety, Legionella Risk Management, Electrical Certificate of Compliance, and Lift Safety Inspections.

## Overview

The Compliance Module is designed for South African facilities management, with specific support for:
- **SANS 10400-T** (fire protection in buildings)
- **SANS 1475** (portable fire extinguishers)
- **OHS Act** occupational health and safety requirements
- **SABS** electrical Certificate of Compliance standards
- **SANS Legionella** guidance for cooling tower management

## Compliance Domains

### 1. OHS Act Compliance

Tracks safety compliance checklists across building zones.

**Features:**
- Zone-based checklist generation
- Hazard identification tracking
- Risk assessment documentation
- Control measures verification

**Standards:** South African OHS Act requirements

### 2. Fire Safety

Manages fire equipment inventory and inspection scheduling.

**Features:**
- Equipment inventory (extinguishers, hose reels, hydrants, alarms, detectors)
- 12-month inspection interval tracking
- Pressure test validation
- Location-based equipment mapping

**Standards:**
- **Primary:** SANS 10400-T (fire protection in buildings)
- **Primary:** SANS 1475 (portable fire extinguishers)
- **Supplementary:** NFPA 10 (international reference only)

### 3. Legionella Risk Management

Comprehensive cooling tower risk assessment and treatment scheduling.

**Risk Matrix (SABS Standard):**

| Risk Level | Temperature Range | Treatment Interval | Cleaning Frequency |
|------------|-------------------|-------------------|-------------------|
| **HIGH** | 20-45°C + >30 days untreated | 14 days | Weekly |
| **MEDIUM** | 20-45°C (≤30 days treated) OR 45-50°C | 30 days | Bi-weekly |
| **MARGINAL** | 50-55°C (transitional zone) | 60 days | Monthly |
| **LOW** | <20°C OR >55°C | 90 days | Monthly |

**Key Temperature Thresholds:**
- **Danger Zone:** 20-45°C (optimal Legionella growth)
- **Transitional Zone:** 50-55°C (not safe, monitor closely)
- **Kill Threshold:** >55°C (hot water disinfection)
- **Safe Cold:** <20°C (growth inhibited)

**Implementation Note:** The MEDIUM classification (30-day interval) assumes biocide treatment provides effective protection for recently-treated water in the danger zone. This assumption should be validated against actual biocide efficacy data.

### 4. Electrical Certificate of Compliance (CoC)

Tracks SABS electrical compliance certificates with dynamic validity monitoring.

**Important Legal Disclaimer:**
> Certificate validity is context-dependent per OHS Act / SANS 10142-1. Validity depends on installation type, occupancy changes, property sale, or Department of Labour inspector discretion. The 5-year tracking displayed is for **administrative monitoring purposes only** and does not constitute a legal validity determination.

**Features:**
- Certificate type tracking (new installation, alterations, SABS inspection)
- Administrative 5-year validity monitoring
- 30-day and 90-day renewal alerts
- Certifying body documentation

### 5. Lift Safety Inspections

Manages lift/elevator safety inspection scheduling per South African regulations.

**Inspection Types:**
- **6-Month Periodic:** Standard inspection cycle for passenger lifts
- **Annual Insurance:** Required for insurance validity
- **Post-Repair:** After major repair or component replacement

**Required Tests:**
- Brake load test
- Speed governor test
- Emergency stop test

### 6. Emergency Light Testing

IEC 62034 battery health monitoring and auto-test scheduling.

**Schedule:** Daily auto-tests at 03:00-03:30 SAST (01:00-01:30 UTC)

**Alert Thresholds:**
- Battery health < 75%: Alert triggered
- 90-day battery health trend tracking
- 3-hour minimum runtime requirement

## Audit Trail

All compliance records include audit trail fields:

```typescript
interface AuditTrail {
  recorded_by?: string        // User who created the record
  recorded_by_email?: string  // Email of recording user
  recorded_at: string         // ISO 8601 timestamp
  updated_by?: string         // User who last updated
  updated_at?: string         // Last update timestamp
}
```

**Usage:**
- Every compliance entry tracks who recorded it and when
- Provides legally defensible records for DoL inspections
- Supports internal audit and governance requirements

## Database Schema

### Legionella Risk Assessment Table

```sql
CREATE TABLE legionella_risk_assessment (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    site_id UUID NOT NULL REFERENCES buildings(id),
    tower_code TEXT NOT NULL,
    equipment_id UUID REFERENCES equipment(id),
    risk_level TEXT NOT NULL
        CHECK (risk_level IN ('low', 'medium', 'marginal', 'high'))
        DEFAULT 'medium',
    water_temperature FLOAT,
    water_test_date TIMESTAMPTZ,
    biocide_treatment_date TIMESTAMPTZ,
    biocide_treatment_interval_days INTEGER DEFAULT 30,
    -- ... additional fields
);
```

**Note:** The `risk_level` column uses a CHECK constraint (not PostgreSQL ENUM) to allow for future risk level additions.

## API Endpoints

See [Compliance API Reference](../03-api-reference/compliance-api.md) for detailed endpoint documentation.

## Frontend Components

### Compliance Dashboard

Multi-tab interface providing:
- Overview with compliance score KPIs
- Domain-specific panels for each compliance area
- Real-time status indicators
- Audit trail visibility

### Key UI Patterns

**Time Display:** All times shown in SAST (South African Standard Time) with UTC in parentheses for backend operations.

**Risk Indicators:** Color-coded risk levels (red/amber/blue/green) with clear temperature ranges.

**Empty States:** Guided onboarding prompts for new sites (e.g., "Start with Electrical Compliance").

## Deployment Notes

### Migration 092: Add MARGINAL Risk Level

For existing deployments, run:

```sql
-- Update risk_level constraint to include 'marginal'
ALTER TABLE legionella_risk_assessment
DROP CONSTRAINT IF EXISTS legionella_risk_assessment_risk_level_check;

ALTER TABLE legionella_risk_assessment
ADD CONSTRAINT legionella_risk_assessment_risk_level_check
CHECK (risk_level IN ('low', 'medium', 'marginal', 'high'));
```

### S002 Configuration

Site-002 (Sandton City Office Tower) has cooling tower `S002-CT-R-001` configured for Legionella monitoring.

## Future Enhancements

### Telemetry Integration

**Planned:** Auto-wire Legionella assessment to cooling tower temperature telemetry rather than manual form input.

**Benefits:**
- Real-time risk assessment updates
- Automated treatment interval adjustments
- Reduced manual data entry

## Related Documentation

- [Compliance API Reference](../03-api-reference/compliance-api.md)
- [Safety Interlocks Engine](../06-safety-compliance/safety-interlocks-engine.md)
- [Audit Logging](../06-safety-compliance/audit-logging.md)
- [Module Matrix](../13-modules/module-matrix.md)

## Changelog

### 2026-05-17

**Added:**
- MARGINAL risk level (50-55°C transitional zone)
- Audit trail fields (recorded_by, recorded_at, updated_by, updated_at)
- SAST time conversion for emergency lights (03:00-03:30 SAST)
- Legal disclaimer for Electrical CoC validity
- SANS 10400-T/1475 primary standards for fire safety
- Zone deduplication logic for OHS checklists
- Guided onboarding prompts for empty states

**Fixed:**
- Legionella risk matrix gap (50-55°C range now properly classified)
- Date.now() impurity issues in React components
- NFPA 10 incorrectly listed as primary standard (now supplementary)

**Technical:**
- Added `MARGINAL = "marginal"` to RiskLevel enum
- Updated CHECK constraint in database schema
- Created migration 092 for existing deployments
