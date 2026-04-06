---
title: "Technician Document Rules Matrix"
type: "spec"
status: "draft"
version: "1.0.0"
created: "2026-03-31"
updated: "2026-03-31"
tags: ["sentinel", "documentation"]
related: []
domain: "bms"
audience: "all"
complexity: "intermediate"
estimated_read_time: 10
---

# Technician Document Rules Matrix

---
title: "Technician Document Rules Matrix"
type: "spec"
status: "draft"
version: "1.1.0"
created: "2026-03-23"
updated: "2026-03-23"
author: "SENTINEL Team"
tags: ["technician-chat", "documents", "compliance", "metadata", "retention"]
domain: "compliance"
audience: "developers"
complexity: "intermediate"
estimated_read_time: 12
---

## Purpose

Define mandatory metadata, controlled values, validation rules, and expiry-alert behavior for documents uploaded by technicians. This applies to the **Technician Chat upload workflow** (not AI Chat upload).

## Scope

- In scope: equipment/service/compliance documentation uploaded by technicians.
- Out of scope: AI Chat knowledge uploads (handled by separate upload policy).

## Identity and Site Binding (Login-Derived, Mandatory)

- `uploaded_by_user_id` must always be derived from the authenticated session/JWT.
- Technician `site_id` must always be derived from technician site allocation in the backend.
- Technician UI must not allow editing `site_id` or `uploaded_by_user_id`.
- Backend must reject/ignore client attempts to override derived identity/site fields.
- If technician has no active site allocation, upload must fail with a clear actionable error.
- Site supervisors/admins can be granted multi-site selection via role policy (separate permission).

## Mandatory Metadata (Upload-Time)

| Field | Required | Notes |
|---|---|---|
| `site_id` | Yes | Derived from logged-in technician site allocation (not free input) |
| `equipment_id` (or system asset id) | Yes | Required for equipment-linked docs |
| `document_sub_class` | Yes | Controlled dropdown |
| `category_discipline` | Yes | Controlled dropdown |
| `document_type` | Yes | Controlled dropdown from matrix below |
| `document_creation_date` | Yes | Actual document date (not upload timestamp) |
| `trigger_date` | Conditional | Mandatory where retention/validity applies |
| `uploaded_by_user_id` | Yes | System-derived from authenticated user (JWT/session) |
| `author_name` | Conditional | Optional display name if different from uploader |

## Trigger Date Rules

| Document Class | Trigger Date Label | Mandatory |
|---|---|---|
| Warranty | Warranty start or expiry date (as configured per type) | Yes |
| Certificate | Certificate issue date (or expiry date if explicit certificate expiry doc) | Yes |
| Inspection | Inspection date | Yes |
| Service Report | Service completion date | Yes |
| Test Report | Test execution date | Yes |
| Incident / Repair | Incident or repair completion date | Yes |
| Bulk Logs / Consumption Summaries | Reporting period start (and end if applicable) | Yes |
| Ad-hoc Engineering Notes | N/A | No (unless governance flag set) |

## Expiry/Retention Automation

| Capability | Requirement |
|---|---|
| Expiry calculation | Compute `expiry_date` from `trigger_date + retention_policy` (or explicit rule) |
| Expired status | Auto-flag `expired` when `today > expiry_date` |
| Pre-expiry alerts | Alert nominated admin at offsets `90/30/7` days (policy-configurable) |
| Audit trail | Persist rule used, trigger date, calculation timestamp, and notifier events |

## Validation Controls (Enforced at Upload)

- Block save if mandatory fields are missing.
- Block free-text where controlled dropdown fields are required.
- Validate date formats (`YYYY-MM-DD`) and date logic (`expiry_date >= trigger_date`).
- Validate user-site scope from login-derived allocation (no cross-site upload for technician role).
- Duplicate detection:
  - hard duplicate: same file hash + same site + same document type,
  - soft duplicate: same site + same document type + same document_creation_date + same equipment_id.
- Require resolution action for soft duplicate (`replace`, `version`, `cancel`).

## Controlled Dropdown Vocabularies (Initial)

### Document Sub Class

- HVAC
- Electrical
- Fire
- Plumbing
- Lifts
- Building Fabric
- Power Factor Correction
- UPS
- Solar PV
- General Facilities

### Category / Discipline

- Preventive Maintenance
- Corrective Maintenance
- Compliance
- Safety
- Energy
- Water
- Testing & Commissioning
- Incident & Repair

### Document Type Families

- Service Report
- Inspection Report / Checklist
- Test Report
- Certificate
- Date / Certificate
- Incident Report
- Consumption Report
- Survey / Hygiene Report

## Seed Document Type Matrix (from operations examples)

| Document Type | Sub Class | Category / Discipline | Family | Trigger Date Label | Trigger Required | Retention Rule Key |
|---|---|---|---|---|---|---|
| Roof Guarantee Certificate | Building Fabric | Compliance | Certificate | Certificate issue date | Yes | `cert_default` |
| Warranties | General Facilities | Compliance | Date / Certificate | Warranty expiry date | Yes | `warranty_default` |
| Air-Handler Unit (AHU) Major Service | HVAC | Preventive Maintenance | Service Report | Service completion date | Yes | `service_report_default` |
| Air-Handler Unit (AHU) Minor Service | HVAC | Preventive Maintenance | Service Report | Service completion date | Yes | `service_report_default` |
| Air-Handler Unit (AHU) Weekly Inspection | HVAC | Compliance | Inspection Report / Checklist | Inspection date | Yes | `inspection_weekly` |
| Cooling Tower (CT) Major Service | HVAC | Preventive Maintenance | Service Report | Service completion date | Yes | `service_report_default` |
| Cooling Tower (CT) Weekly Inspection | HVAC | Compliance | Inspection Report / Checklist | Inspection date | Yes | `inspection_weekly` |
| Chiller Major Service | HVAC | Preventive Maintenance | Service Report | Service completion date | Yes | `service_report_default` |
| Chiller Weekly Inspection | HVAC | Compliance | Inspection Report / Checklist | Inspection date | Yes | `inspection_weekly` |
| Kitchen Canopy Manual Service | HVAC | Preventive Maintenance | Service Report | Service completion date | Yes | `service_report_default` |
| Building Management System (BMS) Service | Electrical | Preventive Maintenance | Service Report | Service completion date | Yes | `service_report_default` |
| Distribution Boards (DB) Maintenance | Electrical | Preventive Maintenance | Service Report | Service completion date | Yes | `service_report_default` |
| Transformer Service | Electrical | Preventive Maintenance | Service Report | Service completion date | Yes | `service_report_default` |
| Fire Pump System Inspection | Fire | Compliance | Inspection Report / Checklist | Inspection date | Yes | `inspection_monthly` |
| Generator Major Service | Electrical | Preventive Maintenance | Service Report | Service completion date | Yes | `service_report_default` |
| Generator Weekly Test | Electrical | Testing & Commissioning | Inspection Report / Checklist | Test date | Yes | `test_default` |
| Integrated Check Valve (ICV) Chamber Weekly Inspection | Plumbing | Compliance | Inspection Report / Checklist | Inspection date | Yes | `inspection_weekly` |
| Lift Service | Lifts | Preventive Maintenance | Service Report | Service completion date | Yes | `service_report_default` |
| Lift test Report | Lifts | Testing & Commissioning | Test Report | Test date | Yes | `test_default` |
| Escalator Monthly Service | Lifts | Preventive Maintenance | Service Report | Service completion date | Yes | `service_report_default` |
| MV and LV Weekly Inspection | Electrical | Compliance | Inspection Report / Checklist | Inspection date | Yes | `inspection_weekly` |
| Battery Tripping Unit (BTU) Weekly Inspection | Electrical | Compliance | Inspection Report / Checklist | Inspection date | Yes | `inspection_weekly` |
| Public Address (PA) & Intercom System Service Report | Electrical | Preventive Maintenance | Service Report | Service completion date | Yes | `service_report_default` |
| Solar PV & Test Service | Solar PV | Testing & Commissioning | Service Report | Service completion date | Yes | `service_report_default` |
| Solar PV Weekly Inspection | Solar PV | Compliance | Inspection Report / Checklist | Inspection date | Yes | `inspection_weekly` |
| UPS Weekly Inspection | UPS | Compliance | Inspection Report / Checklist | Inspection date | Yes | `inspection_weekly` |
| Waste Management Service | General Facilities | Preventive Maintenance | Service Report | Service completion date | Yes | `service_report_default` |
| Refrigeration Certificate of Compliance (CC) | HVAC | Compliance | Date / Certificate | Certificate issue date | Yes | `cert_regulatory` |
| Occupational Certificate | General Facilities | Compliance | Date / Certificate | Certificate issue date | Yes | `cert_regulatory` |
| Structural Integrity Report | Building Fabric | Compliance | Inspection Report | Inspection date | Yes | `inspection_annual` |
| Building Floor Plan | Building Fabric | Compliance | Date / Plan and Approvals | Document issue date | Yes | `plan_default` |
| Calibration of Test & Monitoring Equipment | Electrical | Compliance | Calibration Certificate | Calibration date | Yes | `calibration_default` |
| Certificate of Compliance (COC) | Electrical | Compliance | Date / Certificate | Certificate issue date | Yes | `cert_regulatory` |
| Diesel Tank Integrity Test | Plumbing | Testing & Commissioning | Date / Certificate | Test date | Yes | `test_default` |
| Earth Leakage Test | Electrical | Testing & Commissioning | Date / Certificate | Test date | Yes | `test_default` |
| Plumbing Certificate of Compliance | Plumbing | Compliance | Date / Certificate | Certificate issue date | Yes | `cert_regulatory` |
| Electrical Equipment Certificates | Electrical | Compliance | Date / Certificate | Certificate issue date | Yes | `cert_regulatory` |
| Fire Extinguishers & Hydrants & Hose Reel Service Report | Fire | Preventive Maintenance | Service Report | Service completion date | Yes | `service_report_default` |
| Smoke Detectors Service | Fire | Preventive Maintenance | Service Report | Service completion date | Yes | `service_report_default` |
| Gas Suppression System Integrity Test | Fire | Testing & Commissioning | Date / Certificate | Test date | Yes | `test_default` |
| ASIB Certificate | Fire | Compliance | Date / Certificate | Certificate issue date | Yes | `cert_regulatory` |
| Fire Pump System Service | Fire | Preventive Maintenance | Service Report | Service completion date | Yes | `service_report_default` |
| Lightning Protection Inspection | Electrical | Compliance | Date / Certificate | Inspection date | Yes | `inspection_annual` |
| Anchor Bolt Load Test Certificate | Building Fabric | Testing & Commissioning | Date / Certificate | Test date | Yes | `test_default` |
| Portable Electrical Equipment Certificates | Electrical | Compliance | Date / Certificate | Certificate issue date | Yes | `cert_regulatory` |
| Portable Electrical Tool Inspection | Electrical | Compliance | Inspection Report / Checklist | Inspection date | Yes | `inspection_periodic` |
| Potable Water Test Results | Plumbing | Testing & Commissioning | Test Report | Test date | Yes | `test_default` |
| Pressure Vessel Test Certificate | Plumbing | Compliance | Date / Certificate | Test date | Yes | `test_default` |
| Spillage Incidents Report | General Facilities | Incident & Repair | Incident Report | Incident date | Yes | `incident_default` |
| Underground Water Sampling | Plumbing | Testing & Commissioning | Test Report | Sampling date | Yes | `test_default` |
| Water Consumption Reports | Plumbing | Water | Inspection Report | Report period start | Yes | `consumption_report` |
| Energy Insight / Oil Guard / NUS Consumption Reports | Electrical | Energy | Consumption Report | Report period start | Yes | `consumption_report` |
| Building Inspection Report | Building Fabric | Compliance | Building maintenance, inspection date | Inspection date | Yes | `inspection_default` |
| Occupational Hygiene Surveys | General Facilities | Safety | Date of survey | Survey date | Yes | `survey_default` |
| Waste disposal certificates | General Facilities | Compliance | Waste details, date | Certificate issue date | Yes | `cert_regulatory` |
| Audit Reports | General Facilities | Compliance | Audit dates & company name | Audit date | Yes | `audit_default` |
| BSI Audit certificate | General Facilities | Compliance | certificate number | Certificate issue date | Yes | `cert_regulatory` |

## AI Chat Upload Guardrail (Interim)

AI Chat upload should remain limited to knowledge-assist content until policy is finalized:

- Allowed: `building_manual`, `oem_manual`, `spec_sheet`, `procedure`
- Blocked: certificates, compliance inspections, service reports, and warranty/legal records

## Open Implementation Notes

- Maintain controlled vocab in a server-managed registry table (not hardcoded in UI).
- Store both `document_creation_date` and `uploaded_at` explicitly.
- Add retention rules table keyed by `retention_rule_key`.
- Add alert recipients per site/discipline.
- Enforce technician uploads as site-scoped by login identity in API middleware/service layer.

## Change Log

| Version | Date | Change |
|---|---|---|
| 1.4.0 | 2026-03-23 | Added per-site storage routing policy (local/cloud/site-network), with optional dual-write and local fallback for site-network failures. |
| 1.3.0 | 2026-03-23 | Implemented Phase 2 scaffold in technician upload endpoint: hard/soft duplicate checks, retention-rule mapping, expiry date calculation, and returned alert offsets. |
| 1.2.0 | 2026-03-23 | Implemented backend Phase 1 endpoint `POST /api/documents/technician/upload` with controlled metadata validation, required creation/trigger dates, and login-derived site/uploader binding. |
| 1.1.0 | 2026-03-23 | Added login-derived identity/site binding requirements; clarified technician no-override policy and site-scoped validation. |
| 1.0.0 | 2026-03-23 | Initial matrix with mandatory metadata, controlled vocabularies, trigger-date rules, and seed type mapping. |
