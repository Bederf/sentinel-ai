---
title: "SENTINEL Security Documentation"
type: "reference"
status: "approved"
version: "1.2.0"
created: "2026-02-04"
updated: "2026-02-20"
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
| [Logical Access Control Policy](logical-access-control-policy.md) | Logical access control, IAM, RBAC, PAM, MFA, password standards | Complete |
| [Application Security Policy](application-security-policy.md) | SSDLC, SAST/DAST, WAF, code review, penetration testing | Complete |
| [Secure Coding Standards](secure-coding-standards.md) | Python/FastAPI and TypeScript/React secure development practices | Complete |
| [Password Security Standard](password-security-standard.md) | Password complexity, rotation, and storage requirements | Complete |

### Vulnerability & Incident Management (Phase 64-03)

| Document | Description | Status |
|---|---|---|
| [Vulnerability Management Process](vulnerability-management-process.md) | Scanning schedules, remediation SLAs, dependency monitoring | Complete |
| [Incident Response Policy](incident-response-policy.md) | Detection, containment, eradication, recovery, notification procedures | Complete |
| [Incident Response Process](incident-response-process.md) | Operational runbooks for incident handling | Complete |

### Business Continuity & Third Parties (Phase 64-04)

| Document | Description | Status |
|---|---|---|
| [Business Continuity Policy](business-continuity-policy.md) | BIA, RTO/RPO, DR procedures, annual testing | Complete |
| [Third-Party Security Register](third-party-security-register.md) | Supplier register, compliance framework, review cadence | Complete |

### Risk & Privacy (Phase 64-05)

| Document | Description | Status |
|---|---|---|
| [Information Security Risk Register](information-security-risk-register.md) | Risk register, annual assessment, acceptance criteria | Complete |
| [Data Privacy Policy](data-privacy-policy.md) | POPIA compliance, data handling rules, privacy notices | Complete |
| [Information Classification Policy](information-classification-policy.md) | Classification scheme, labelling, handling procedures | Complete |
| [Privacy Impact Assessment Template](privacy-impact-assessment-template.md) | PIA template for new systems/features | Complete |
| [PIA: Claude API](pia-claude-api.md) | Privacy impact assessment for Claude API integration | Complete |
| [PIA: Sentry Messaging](pia-sentry-messaging.md) | Privacy impact assessment for Telegram/WhatsApp messaging | Complete |
| [POPIA Cross-Border Register](popia-cross-border-register.md) | Register of cross-border data transfers | Complete |

### HR, Crypto, Assets & Audit (Phase 64-06)

| Document | Description | Status |
|---|---|---|
| [HR Security Policy](hr-security-policy.md) | Vetting, training, joiners/leavers, disciplinary process | Complete |
| [Cryptography & Key Management Policy](cryptography-key-management-policy.md) | Algorithms, key rotation, secrets management, Fernet encryption at rest | Complete |
| Asset Register | Infrastructure components, ownership, disposal procedures | Planned |
| Security Awareness Training Programme | Training content, completion tracking, annual cadence | Planned |
| [Security Audit Programme](security-audit-programme.md) | Audit cadence, findings tracking, remediation monitoring | Complete |

### MCP Security Hardening (Phase SSE-P2)

Technical controls securing the SIMBIOT MCP Server (Model Context Protocol) for remote access via SSE transport. Aligned with OWASP MCP Security Guidelines.

| Document | Description | Status |
|---|---|---|
| [MCP Security Hardening](mcp-security-hardening.md) | 8-layer security architecture: auth gating, demo bypass restriction, schema validation, rate limiting, ticket-based auth, audit logging, manifest tamper resistance, approval workflow | Complete |

Key controls:
- **Auth for all remote tools** — SSE transport requires auth for every tool, including read-only
- **Demo bypass locked to development** — `DEMO_MODE=true` in production is blocked
- **Tool Security Registry** — Canonical per-tool classification (risk tier, role, module, audit fields, secret-zero flags)
- **Secret-Zero Output Filter** — Credential patterns in tool output are redacted before reaching the model
- **Policy Decision Records** — SIEM-queryable audit events with tool, risk_tier, auth_method, user, result
- **Cross-Tenant Isolation** — Rate limits, approval tokens, and SSE tickets scoped per identity

Related: [MCP Tools Reference](../03-api-reference/mcp-tools-reference.md) (Safety & Security section)

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
| 4.1 | Information Security Governance | Framework, Strategy, Policy, AUP | 3.7 | 4.0 | LOW |
| 4.2 | Asset Management | Asset Register | 4.0 | 4.5 | LOW |
| 4.3 | Information Classification | Data Privacy & Classification Policy | 3.5 | 4.0 | LOW |
| 4.4 | Human Resource Security | HR Security Policy, Training Programme | 3.0 | 3.8 | MEDIUM |
| 4.5 | Physical Access Security | (Provider attestations) | 4.0 | 4.0 | NONE |
| 4.6 | Network Security | Information Security Policy s3.6 | 4.0 | 4.5 | LOW |
| 4.7 | Logical Access Control | Access Control Policy | 3.8 | 4.0 | LOW |
| 4.8 | System Security | Information Security Policy s3.8 | 3.5 | 4.0 | LOW |
| 4.9 | Application Security | Application Security Policy, Secure Coding Standards | 3.8 | 4.0 | LOW |
| 4.10 | Vulnerability Management | Vulnerability Management Policy | 4.3 | 4.5 | LOW |
| 4.11 | Communication Management | Information Security Policy s3.11 | 4.0 | 4.0 | NONE |
| 4.12 | Cryptography & Key Management | Cryptography & Key Management Policy | 4.0 | 4.5 | LOW |
| 4.13 | Incident Detection | Incident Response Policy, Logging Architecture | 3.8 | 4.0 | LOW |
| 4.14 | Incident Management | Incident Response Policy | 3.2 | 4.0 | MEDIUM |
| 4.15 | Business Continuity | BCP/DR Policy, BCP/DR Procedures | 3.0 | 4.0 | MEDIUM |
| 4.16 | Third Party Management | Third-Party Security Policy | 3.7 | 4.0 | LOW |
| 4.17 | Risk & Compliance | Risk Management Policy | 3.5 | 4.0 | LOW |
| 4.18 | Information Security Audit | Security Audit Procedure | 3.0 | 3.5 | MEDIUM |

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
