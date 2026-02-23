# SENTINEL Asset Lifecycle Policy

**Document ID:** SENTINEL-ALP-001
**Version:** 1.0
**Effective Date:** 2026-02-23
**Review Cadence:** Annual
**Owner:** Information Security Officer
**Classification:** Confidential
**FSR Domain:** 4.2 -- Asset Management
**Status:** Active

---

## 1. Purpose

This policy defines how SENTINEL information assets are identified, classified, maintained, transferred, and retired across their full lifecycle. It establishes ownership and control requirements to reduce operational, privacy, and security risk.

---

## 2. Scope

This policy applies to:

- Platform infrastructure assets (VPS, containers, storage, networking)
- Software and service assets (APIs, agents, integrations, CI/CD workflows)
- Data assets (telemetry, audit logs, consent records, privacy request records)
- Security and compliance artifacts (policies, evidence packs, runbooks)

Out of scope:

- Client-owned BMS hardware not operated by SENTINEL
- End-user devices managed by client IT

---

## 3. Lifecycle Stages

| Stage | Required Activities | Evidence |
|---|---|---|
| Plan | Define owner, classification, risk profile, and business purpose | Asset proposal / change request |
| Acquire / Build | Apply secure baseline, naming, and access controls | Provisioning logs, IaC commits |
| Register | Record asset metadata in register | Asset register entry |
| Operate | Patch, monitor, back up, and review access | Monitoring logs, patch records |
| Change | Assess impact and approve material changes | Change record + approval |
| Transfer | Re-assign ownership with handover controls | Handover checklist |
| Retire / Dispose | Revoke access, archive evidence, delete or destroy data | Disposal certificate / deletion evidence |

---

## 4. Asset Register Minimum Fields

Each managed asset must include:

- `asset_id`
- `asset_name`
- `asset_type` (infra, app, data, integration, document)
- `owner_role`
- `custodian`
- `classification` (public, internal, confidential, restricted)
- `environment` (dev, test, prod)
- `criticality` (low, medium, high, critical)
- `backup_requirement`
- `retention_requirement`
- `last_review_date`
- `next_review_date`
- `status` (active, suspended, retired)

---

## 5. Control Requirements

### 5.1 Ownership and Accountability

- Every asset must have one accountable owner and one operational custodian.
- Ownership changes must be recorded within 5 business days.

### 5.2 Classification and Handling

- Asset classification must align with `information-classification-policy.md`.
- PI-bearing assets require POPIA controls and explicit retention rules.

### 5.3 Access and Change Control

- Least-privilege access must be enforced for all production assets.
- Material changes to high/critical assets require approved change records.

### 5.4 Monitoring and Recovery

- High/critical assets must have monitoring and alert coverage.
- High/critical assets must map to tested backup and DR procedures.

### 5.5 Retirement and Disposal

- Access revocation is mandatory before asset retirement.
- Data disposal must be auditable and aligned with retention policy.

---

## 6. Roles and Responsibilities

| Role | Responsibilities |
|---|---|
| Information Security Officer | Policy ownership, annual review, exception approval |
| Platform/SRE Lead | Asset registration quality, operational controls, retirement evidence |
| Compliance Lead | POPIA retention/disposal verification for PI-bearing assets |
| Architecture Board | Oversight of lifecycle controls for critical systems |

---

## 7. Exceptions

Policy exceptions require:

1. Documented business rationale
2. Risk assessment
3. Defined compensating controls
4. Approved expiry date
5. Information Security Officer approval

---

## 8. Related Documents

- `docs/09-security/information-classification-policy.md`
- `docs/09-security/business-continuity-policy.md`
- `docs/09-security/data-privacy-policy.md`
- `docs/05-integrations/asset-lifecycle-state-machine.md`
- `docs/04-features/44-46-54-integration-workflow.md`

---

## 9. Version History

| Version | Date | Author | Changes |
|---|---|---|---|
| 1.0 | 2026-02-23 | SENTINEL Platform Team | Initial policy release |
