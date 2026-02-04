---
title: "SENTINEL Security Documentation"
type: "reference"
status: "approved"
version: "1.0.0"
created: "2026-02-04"
updated: "2026-02-04"
author: "SENTINEL Security Office"
tags: ["security", "governance", "index", "FSR"]
domain: "security"
audience: "all"
complexity: "beginner"
estimated_read_time: 5
---

# SENTINEL Security Documentation

This directory contains the SENTINEL Information Security Policy Suite -- the governance documents underpinning the SENTINEL BMS Intelligence Platform's security programme. These documents support FSR (FirstRand Group) supplier onboarding by addressing all 18 security domains in the FSR Privacy and Service Risk Assessment Questionnaire V8.

## Document Index

### Governance Foundation (Phase 64-01)

| Document | Description | Status |
|---|---|---|
| [Information Security Framework](information-security-framework.md) | Governance structure, ISO role, policy hierarchy, applicable standards, risk appetite | Complete |
| [Information Security Strategy](information-security-strategy.md) | Maturity assessment, target scores, remediation roadmap, quarterly health report template | Complete |
| [Information Security Policy](information-security-policy.md) | Overarching policy with statements covering all 18 FSR domains | Complete |
| [Acceptable Usage Policy](acceptable-usage-policy.md) | Rules for infrastructure, communication, data handling, remote access, BYOD | Complete |

### Access Control & Application Security (Phase 64-02)

| Document | Description | Status |
|---|---|---|
| Access Control Policy | Logical access control, IAM, RBAC, PAM, MFA, password standards | Planned |
| Application Security Policy | SSDLC, SAST/DAST, WAF, code review, penetration testing | Planned |
| Secure Coding Standards | Python/FastAPI and TypeScript/React secure development practices | Planned |

### Vulnerability & Incident Management (Phase 64-03)

| Document | Description | Status |
|---|---|---|
| Vulnerability Management Policy | Scanning schedules, remediation SLAs, dependency monitoring | Planned |
| Incident Response Policy | Detection, containment, eradication, recovery, notification procedures | Planned |

### Business Continuity & Third Parties (Phase 64-04)

| Document | Description | Status |
|---|---|---|
| Business Continuity & DR Policy | BIA, RTO/RPO, DR procedures, annual testing | Planned |
| Third-Party Security Policy | Supplier register, compliance framework, review cadence | Planned |

### Risk & Privacy (Phase 64-05)

| Document | Description | Status |
|---|---|---|
| Risk Management Policy | Risk register, annual assessment, acceptance criteria | Planned |
| Data Privacy & Classification Policy | Classification scheme, POPIA compliance, data handling rules | Planned |

### HR, Crypto, Assets & Audit (Phase 64-06)

| Document | Description | Status |
|---|---|---|
| HR Security Policy | Vetting, training, joiners/leavers, disciplinary process | Planned |
| Cryptography & Key Management Policy | Algorithms, key rotation, secrets management | Planned |
| Asset Register | Infrastructure components, ownership, disposal procedures | Planned |
| Security Awareness Training Programme | Training content, completion tracking, annual cadence | Planned |
| Security Audit Procedure | Audit cadence, findings tracking, remediation monitoring | Planned |

### Technical Implementation Evidence (Phase 63)

These documents record the technical security controls deployed as part of Phase 63 (RISK Technical Implementation). They serve as evidence for governance documents.

| Document | Description | Status |
|---|---|---|
| [Logging Architecture](logging-architecture.md) | Centralised logging with Loki/Promtail, audit log pipeline | Complete |
| [Intrusion Detection](intrusion-detection.md) | OSSEC HIDS, Cloudflare WAF, alerting configuration | Complete |
| [Access Control Implementation](access-control-implementation.md) | PAM, MFA, RBAC technical deployment | Complete |
| [Application Security Pipeline](application-security-pipeline.md) | SAST/DAST integration, Bandit, Safety, container scanning | Complete |
| [Vulnerability Management](vulnerability-management.md) | Scanning tools, schedules, remediation workflow | Complete |
| [BCP/DR Procedures](bcp-dr-procedures.md) | Backup, recovery, failover, test runbooks | Complete |
| [Consent and Privacy](consent-and-privacy.md) | Consent capture for messaging platforms, privacy notices | Complete |

## FSR Domain Coverage

The following table maps each FSR security domain to the SENTINEL governance document(s) that address it.

| # | FSR Domain | Primary Document | Current | Target | Gap |
|---|---|---|---|---|---|
| 4.1 | Information Security Governance | Framework, Strategy, Policy, AUP | 3.0 | 4.0 | MEDIUM |
| 4.2 | Asset Management | Asset Register | 4.0 | 4.5 | LOW |
| 4.3 | Information Classification | Data Privacy & Classification Policy | 3.5 | 4.0 | LOW |
| 4.4 | Human Resource Security | HR Security Policy, Training Programme | 3.0 | 3.8 | MEDIUM |
| 4.5 | Physical Access Security | (Provider attestations) | 4.0 | 4.0 | LOW |
| 4.6 | Network Security | Information Security Policy s3.6 | 4.0 | 4.5 | LOW |
| 4.7 | Logical Access Control | Access Control Policy | 3.0 | 4.0 | HIGH |
| 4.8 | System Security | Information Security Policy s3.8 | 3.5 | 4.0 | MEDIUM |
| 4.9 | Application Security | Application Security Policy, Secure Coding Standards | 2.5 | 4.0 | HIGH |
| 4.10 | Vulnerability Management | Vulnerability Management Policy | 3.0 | 4.0 | MEDIUM |
| 4.11 | Communication Management | Information Security Policy s3.11 | 4.0 | 4.0 | LOW |
| 4.12 | Cryptography & Key Management | Cryptography & Key Management Policy | 4.0 | 4.5 | LOW |
| 4.13 | Incident Detection | Incident Response Policy, Logging Architecture | 3.0 | 4.0 | HIGH |
| 4.14 | Incident Management | Incident Response Policy | 3.0 | 4.0 | MEDIUM |
| 4.15 | Business Continuity | BCP/DR Policy, BCP/DR Procedures | 3.0 | 4.0 | MEDIUM |
| 4.16 | Third Party Management | Third-Party Security Policy | 3.5 | 4.0 | MEDIUM |
| 4.17 | Risk & Compliance | Risk Management Policy | 3.0 | 4.0 | MEDIUM |
| 4.18 | Information Security Audit | Security Audit Procedure | 2.0 | 3.5 | HIGH |

## Gap Analysis Reference

The detailed FSR gap analysis with current scores, target scores, and required remediation actions is maintained at:

`.planning/phases/64-risk-governance-foundation/FSR-GAP-ANALYSIS.md`

This analysis drives the prioritisation and content of all governance documents in this directory.

## Document Standards

All documents in this directory follow the SENTINEL documentation standards:

- **Frontmatter:** YAML metadata including classification, review date, and ownership
- **Classification:** Documents are classified as Confidential unless otherwise stated
- **Review cycle:** Annual review at minimum; triggered reviews on significant change
- **Versioning:** Semantic versioning (Major.Minor.Patch) in version history table
- **Ownership:** Information Security Officer is the owner of all Level 1-2 documents
