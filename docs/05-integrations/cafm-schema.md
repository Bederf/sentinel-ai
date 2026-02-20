---
title: "CAFM Integration Schema (Concept Evolution)"
type: "reference"
status: "approved"
version: "1.0.0"
created: "2026-01-30"
updated: "2026-01-30"
author: "Sentinel Development Team"
tags: ["cafm", "integration", "schema", "concept-evolution"]
related: ["../02-architecture/system-overview.md"]
domain: "compliance"
audience: "developers"
complexity: "intermediate"
estimated_read_time: 15
---

# Concept Evolution CAFM - Integration Schema

This document defines the expected data formats for Concept Evolution CAFM integration with SENTINEL.

## Overview

Concept Evolution exports data in CSV/Excel format. SENTINEL ingests this data to:
1. Track work order history per asset
2. Assess asset health/condition based on failure patterns
3. Identify repeat calls and escalating issues
4. Calculate maintenance costs and trends

---

## 1. Job Cards / Work Orders

**File:** `concept_jobcards.csv`
**Frequency:** Daily export or real-time via Workflow Pro

### Schema

| Column | Type | Description | Example |
|--------|------|-------------|---------|
| `JobCardNo` | string | Unique job card number | `JC-2026-00412` |
| `TaskRef` | string | Concept task reference | `TSK-889234` |
| `Priority` | string | P1-P4 priority code | `P2` |
| `Status` | string | Current status | `Completed` |
| `LoggedDate` | datetime | When call was logged | `2026-01-15 08:23:00` |
| `TargetDate` | datetime | SLA target completion | `2026-01-15 12:23:00` |
| `CompletedDate` | datetime | Actual completion | `2026-01-15 11:45:00` |
| `SLAMet` | boolean | Met SLA target? | `Y` |
| `BuildingCode` | string | Building/site reference | `GW-JHB-001` |
| `BuildingName` | string | Building name | `Gateway Theatre of Shopping` |
| `LocationCode` | string | Specific location | `L03-PLANTROOM-01` |
| `LocationDesc` | string | Location description | `Level 3 Plant Room` |
| `AssetCode` | string | Asset tag/code | `GW-HVAC-CH-001` |
| `AssetDesc` | string | Asset description | `Carrier 30XA Chiller 500kW` |
| `AssetCategory` | string | Asset category | `HVAC` |
| `AssetCriticality` | string | Criticality rating | `Critical` |
| `FaultCode` | string | Fault/call type code | `HVAC-MECH-003` |
| `FaultDesc` | string | Fault description | `Mechanical Fault - Compressor` |
| `ProblemDesc` | text | Caller's problem description | `Chiller making grinding noise, not cooling` |
| `CauseCode` | string | Root cause code | `WEAR-BEARING` |
| `CauseDesc` | string | Root cause description | `Bearing wear/failure` |
| `ActionTaken` | text | Resolution/action taken | `Replaced compressor bearings. Oil analysis shows metal contamination.` |
| `TechnicianCode` | string | Assigned technician | `TECH-042` |
| `TechnicianName` | string | Technician name | `Johan van der Berg` |
| `LabourHours` | decimal | Labour hours | `6.5` |
| `LabourCost` | decimal | Labour cost (ZAR) | `2275.00` |
| `PartsCost` | decimal | Parts cost (ZAR) | `8450.00` |
| `ContractorCost` | decimal | Contractor cost (ZAR) | `0.00` |
| `TotalCost` | decimal | Total job cost (ZAR) | `10725.00` |
| `RepeatCall` | boolean | Is this a repeat call? | `Y` |
| `RelatedJobCard` | string | Related previous job | `JC-2025-03892` |
| `PPMRef` | string | Related PPM schedule | `PPM-HVAC-Q4` |
| `ComplianceType` | string | Compliance category | `MECHANICAL` |
| `TechNotes` | text | Technician observations | `URGENT: Same issue as Nov. Recommend full compressor inspection.` |
| `CustomerFeedback` | integer | Satisfaction score 1-5 | `4` |
| `KPI1_Response` | datetime | Response time milestone | `2026-01-15 08:45:00` |
| `KPI2_Onsite` | datetime | Onsite arrival milestone | `2026-01-15 09:30:00` |
| `KPI3_Diagnosed` | datetime | Diagnosis complete | `2026-01-15 10:15:00` |
| `KPI4_PartsOrdered` | datetime | Parts ordered (if needed) | `null` |
| `KPI5_Completed` | datetime | Job completed | `2026-01-15 11:45:00` |

### Priority Codes

| Code | Description | SLA Target |
|------|-------------|------------|
| P1 | Emergency - Life Safety | 1 hour |
| P2 | Urgent - Business Critical | 4 hours |
| P3 | Standard - Operational | 24 hours |
| P4 | Low - Planned/Cosmetic | 72 hours |

### Status Values

- `Logged` - Call received, awaiting assignment
- `Assigned` - Technician assigned
- `In Progress` - Work underway
- `On Hold` - Waiting for parts/approval
- `Completed` - Work finished
- `Cancelled` - Job cancelled
- `Reopened` - Issue recurred

---

## 2. Asset Register

**File:** `concept_assets.csv`
**Frequency:** Weekly sync or on-change

### Schema

| Column | Type | Description | Example |
|--------|------|-------------|---------|
| `AssetCode` | string | Unique asset code | `GW-HVAC-CH-001` |
| `AssetDesc` | string | Asset description | `Carrier 30XA Chiller` |
| `AssetCategory` | string | Category | `HVAC` |
| `AssetType` | string | Equipment type | `Chiller` |
| `Manufacturer` | string | OEM | `Carrier` |
| `Model` | string | Model number | `30XA-502` |
| `SerialNo` | string | Serial number | `2819F04523` |
| `BuildingCode` | string | Building reference | `GW-JHB-001` |
| `BuildingName` | string | Building name | `Gateway Theatre of Shopping` |
| `LocationCode` | string | Location | `L03-PLANTROOM-01` |
| `LocationDesc` | string | Location description | `Level 3 Plant Room` |
| `InstallDate` | date | Installation date | `2005-03-15` |
| `WarrantyExpiry` | date | Warranty end | `2008-03-15` |
| `ExpectedLifeYears` | integer | Expected lifespan | `20` |
| `Criticality` | string | Criticality rating | `Critical` |
| `Condition` | string | Current condition | `Fair` |
| `ConditionScore` | integer | Condition 1-100 | `62` |
| `LastServiceDate` | date | Last PPM date | `2025-10-22` |
| `NextServiceDate` | date | Next PPM due | `2026-01-22` |
| `PPMFrequency` | string | PPM interval | `Quarterly` |
| `ReplacementCost` | decimal | Replacement value (ZAR) | `1850000.00` |
| `AnnualMaintCost` | decimal | Annual maint budget | `45000.00` |
| `RiskRating` | string | Risk assessment | `High` |
| `ComplianceReq` | string | Compliance requirements | `SANS 10400, OHS Act` |
| `Notes` | text | General notes | `Primary cooling. No redundancy.` |

### Condition Ratings

| Rating | Score Range | Description |
|--------|-------------|-------------|
| Excellent | 85-100 | Like new, no issues |
| Good | 70-84 | Minor wear, fully functional |
| Fair | 50-69 | Moderate wear, needs attention |
| Poor | 25-49 | Significant issues, repair needed |
| Critical | 0-24 | Failing/failed, replace urgently |

### Criticality Ratings

| Rating | Description |
|--------|-------------|
| Critical | Failure causes immediate business impact |
| High | Failure causes significant disruption |
| Medium | Failure causes moderate inconvenience |
| Low | Failure has minimal impact |

---

## 3. PPM Schedules

**File:** `concept_ppm.csv`
**Frequency:** Monthly sync

### Schema

| Column | Type | Description | Example |
|--------|------|-------------|---------|
| `PPMRef` | string | PPM schedule reference | `PPM-HVAC-Q4-2026` |
| `PPMDesc` | string | Schedule description | `Chiller Quarterly Service` |
| `AssetCode` | string | Asset reference | `GW-HVAC-CH-001` |
| `Frequency` | string | Service interval | `Quarterly` |
| `DueDate` | date | Next due date | `2026-01-22` |
| `LastCompleted` | date | Last completion | `2025-10-22` |
| `Status` | string | Schedule status | `Due` |
| `InstructionSet` | string | Work instructions ref | `IS-CHILLER-QTR` |
| `EstimatedHours` | decimal | Estimated labour | `4.0` |
| `EstimatedCost` | decimal | Estimated cost (ZAR) | `8500.00` |
| `ComplianceType` | string | Compliance link | `MECHANICAL` |
| `Mandatory` | boolean | Compliance mandatory? | `Y` |

---

## Integration Notes

### SENTINEL Field Mapping

| Concept Field | SENTINEL Field | Transform |
|---------------|----------------|-----------|
| `JobCardNo` | `work_order_id` | Direct |
| `AssetCode` | `asset_id` | Direct |
| `BuildingCode` | `site_id` | Direct |
| `FaultCode` | `fault_code` | Map to taxonomy |
| `Priority` | `priority` | P1→critical, P2→high, P3→medium, P4→low |
| `TechNotes` | `technician_notes` | Direct |
| `RepeatCall` | `repeat_call` | Y→true, N→false |
| `ConditionScore` | `health_score` | Direct (invert: 100-score for health) |

### Health Assessment Logic

SENTINEL calculates asset health from Concept data:

```
Health Score Factors:
- Base condition score from asset register (40%)
- Repeat call frequency last 12 months (25%)
- PPM compliance rate (15%)
- Age vs expected life (10%)
- Technician warning flags in notes (10%)
```

### Repeat Call Detection

A job is marked as repeat if:
1. Same asset + same fault code within 90 days
2. `RelatedJobCard` field populated
3. Technician notes contain "same issue", "again", "recurring"
