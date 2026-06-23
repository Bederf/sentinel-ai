---
title: "SENTINEL Customer Security Pack"
type: "reference"
status: "approved"
version: "1.0.0"
created: "2026-06-23"
updated: "2026-06-23"
tags: ["sentinel", "security", "compliance", "customer", "enterprise"]
domain: "security"
audience: "bank-it, bank-security, compliance, procurement"
complexity: "intermediate"
estimated_read_time: 15
---

# SENTINEL Customer Security Pack

This document provides a consolidated security and compliance overview for enterprise customers evaluating SENTINEL BMS Intelligence Platform. It is designed for architecture review, security assessment, and procurement due diligence.

---

## 1. Architecture Overview

SENTINEL is a BMS intelligence layer that sits above existing building management systems. It does not replace BMS controllers — it reads telemetry, generates insights, and optionally issues approved control commands through existing protocols.

### High-Level Architecture

```
Building Systems (BACnet/Modbus/DALI-2)
    ↓
SIMBIOT Adapter
    ↓
SENTINEL Backend (FastAPI)
    ├──→ Database (PostgreSQL/Supabase)
    ├──→ AI Services (Ollama or Claude API)
    ├──→ ML Pipeline (Forecasting, Anomaly Detection)
    └──→ Notification Layer (Teams/Email)
    ↓
Users (Web UI, API, Chat)
```

### Deployment Options

| Option | Description | Best For |
|--------|-------------|----------|
| **Cloud VPS** | FastAPI + React on VPS, Supabase af-south-1 | Initial deployment, single-site |
| **On-Prem SA** | Same stack on customer-managed SA server | Data residency requirements |
| **Air-Gapped** | Jetson Orin Nano / VM, local Ollama, zero cloud | Banks, classified environments |

See `docs/09-security/bank-deployment-architecture.md` for full topology, routing profiles, and network requirements.

---

## 2. Security Overview

### 2.1 Access Control (RBAC)

| Layer | Mechanism | Coverage |
|-------|-----------|----------|
| Endpoint gating | `require_role()` FastAPI dependency | 109 endpoints across 6 role levels |
| Site isolation | `require_site_access()`, `require_equipment_access()` | 94 site-level + 35 equipment-level checks |
| Response shaping | `presentation_guidance` in MCP tool output | Role-dependent data visibility |

### 2.2 Authentication

- JWT-based session tokens (256-bit signing)
- API key authentication for service accounts
- 6 role levels: ADMIN → ENGINEER → DEVELOPER → OPERATOR → AUDITOR → BOT_AGENT
- MFA support via TOTP

### 2.3 Encryption

| Context | Algorithm | Key Management |
|---------|-----------|----------------|
| In transit | TLS 1.3 | Let's Encrypt or customer-managed CA |
| At rest (audit logs) | Fernet AES-128-CBC | SOPS + age encryption |
| At rest (database) | PostgreSQL TDE / Supabase at-rest | Platform-managed |
| Secrets | SOPS + age, environment-file based runtime | Rotated quarterly |

### 2.4 Audit Logging

- Centralised log aggregation via Loki + Promtail
- 90-day immutable retention
- 6 log sources (Docker, system auth, syslog, security, audit trail, decisions)
- 5 security alert rules
- Append-only audit trail with Fernet encryption

### 2.5 Penetration Testing

| Type | Status | Date |
|------|--------|------|
| Internal OWASP ZAP + Kali scan | Complete | 2026-06-23 |
| Third-party independent (CREST/CHECK) | Planned — next assurance phase | Q3 2026 |

### 2.6 Vulnerability Management

- CI/CD security scanning: Dependabot (4 ecosystems), pip-audit, safety, gitleaks
- Remediation SLAs: Critical 24h, High 7d, Medium 30d, Low 90d
- FSR maturity score: 4.5/5.0 (target: 4.0)
- Full policy: `docs/09-security/vulnerability-management-process.md`

### 2.7 Threat Model

STRIDE-based threat model covering:
- Edge deployment (Jetson/VM)
- SIMBIOT adapters
- API layer
- Database
- AI services
- Notification channels
- Reverse tunnels

See `docs/09-security/threat-model.md` and `threat-model-summary.md`.

---

## 3. Compliance Overview

### 3.1 POPIA (South Africa)

| Control Area | Status |
|---|---|
| Accountability and governance | PASS |
| Security safeguards | PASS |
| Breach response | PASS |
| Consent capture | PASS |
| Consent enforcement | PASS |
| Data subject rights | PASS |
| Retention/deletion | PASS |
| Cross-border transfer | PASS |

See `docs/09-security/compliance/popia-compliance-register.md`.

### 3.2 EU AI Act

- 12 AI features classified (minimal, limited, high-risk candidate)
- Article-level compliance mapping
- 75% compliant, remediation plan for remaining items

See `docs/09-security/compliance/eu-ai-act-compliance-register.md`.

### 3.3 AI Governance (ISO 42001 / NIST AI RMF)

- Model cards for all 6 active ML models
- Fairness and bias baseline (4 equity dimensions)
- Third-party AI risk register
- CAPA register for nonconformity tracking

See `docs/09-security/ai-governance/`.

### 3.4 South African Regulatory

| Regulation | Status |
|---|---|
| Cybercrimes Act 19/2020 | Compliant — 72h reporting procedure documented |
| National Energy Act 34/2008 | Energy balance export available |
| SANS 10400 | Ventilation rate alerting implemented |
| COIDA | Accident reporting procedure documented |
| Green Star / EDGE | BAS evidence package available |

### 3.5 SOC 2 / ISO 27001

- SOC 2: Not yet certified — on roadmap
- ISO 27001: Not yet certified — on roadmap
- Controls align with both frameworks via FSR domain mapping

---

## 4. Data Protection

### 4.1 Data Classification

| Classification | Examples | Storage | Retention |
|---|---|---|---|
| Public | Building energy ratings | Dashboard | Indefinite |
| Internal | HVAC telemetry, equipment state | Database | Configurable (default 1 year) |
| Confidential | Work orders, technician names | Database | 90 days (POPIA-compliant) |
| Restricted | Badge data, CCTV events | Local only | Never leaves bank network |

### 4.2 Data Residency

- Supabase af-south-1 (Cape Town) — building data stays in SA
- On-prem deployment: all data on customer-managed infrastructure
- Cross-border register with s72 basis documented
- Badge data, CCTV, access logs, AI prompts: never leave bank network

---

## 5. Business Continuity & Disaster Recovery

| Capability | Detail |
|---|---|
| RTO target | 4 hours (VM class outage) |
| RPO target | 24 hours (logical dumps) |
| PITR | Available via WAL archive |
| Replication | Async WAL streaming to remote standby |
| DR test | Tabletop executed 2026-06-23 (Q2) |
| CAPA process | Findings tracked in register with owners and target dates |

See `docs/10-operations/disaster-recovery.md` and `docs/10-operations/high-availability-architecture.md`.

---

## 6. Software Supply Chain

| Capability | Status |
|---|---|
| Dependency scanning | ✅ Dependabot (4 ecosystems), pip-audit, safety |
| Secret scanning | ✅ Gitleaks in CI |
| Container scanning | ✅ Trivy configured |
| SBOM | ✅ CycloneDX JSON — `docs/09-security/sbom-backend-cyclonedx.json` |
| SLSA attestation | ❌ On roadmap |
| Signed releases | ❌ On roadmap |

---

## 7. Document Index

| Category | Document | Path |
|---|---|---|
| Architecture | System overview | `docs/02-architecture/system-overview.md` |
| Architecture | Bank deployment | `docs/09-security/bank-deployment-architecture.md` |
| Architecture | HA architecture | `docs/10-operations/high-availability-architecture.md` |
| Security | Access control | `docs/09-security/access-control-implementation.md` |
| Security | Secrets management | `docs/09-security/secrets-management.md` |
| Security | Logging | `docs/09-security/logging-architecture.md` |
| Security | Threat model | `docs/09-security/threat-model.md` |
| Security | Vulnerability management | `docs/09-security/vulnerability-management-process.md` |
| Security | Multi-tenant isolation | `docs/09-security/multi-tenant-isolation.md` |
| Security | Penetration test scope | `docs/09-security/pen-test-scope-plan.md` |
| Security | SBOM | `docs/09-security/sbom-backend-cyclonedx.json` |
| Compliance | POPIA register | `docs/09-security/compliance/popia-compliance-register.md` |
| Compliance | EU AI Act register | `docs/09-security/compliance/eu-ai-act-compliance-register.md` |
| Compliance | SA regulatory register | `docs/09-security/compliance/south-africa-regulatory-compliance-register.md` |
| Compliance | AI governance | `docs/09-security/ai-governance/00-scope-and-system-boundaries.md` |
| Operations | Deployment runbook | `docs/10-operations/deployment-runbook.md` |
| Operations | DR runbook | `docs/10-operations/disaster-recovery.md` |
| Operations | DR exercise report | `docs/09-security/dr-exercise-report-2026Q2.md` |
