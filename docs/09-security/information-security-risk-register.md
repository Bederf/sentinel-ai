---
title: "Information Security Risk Register"
type: "policy"
status: "draft"
version: "1.0.0"
created: "2026-03-31"
updated: "2026-03-31"
tags: ["sentinel", "documentation"]
related: []
domain: "security"
audience: "all"
complexity: "intermediate"
estimated_read_time: 10
---

# Information Security Risk Register

**Document ID:** SENTINEL-ISR-001
**Version:** 1.0
**Effective Date:** 2026-02-04
**Review Cadence:** Quarterly (minimum), or after any P1/P2 incident, or after significant architecture change
**Owner:** SENTINEL Platform Team
**Classification:** Internal

---

## 1. Purpose

This document maintains a living register of identified information security risks to the SENTINEL BMS Intelligence Platform. It provides a structured approach to risk identification, assessment, treatment, and ongoing monitoring to protect SENTINEL infrastructure, data, and operations.

The risk register underpins all other security policies and serves as the central reference for risk-based decision making across the platform.

---

## 2. Scope

This register covers all information security risks to:

- SENTINEL platform infrastructure (Contabo VPS, Docker containers, networking)
- Application components (FastAPI backend, React frontend, ML pipeline)
- Data assets (building telemetry, occupant PI, equipment data, FSR client data)
- Third-party services (Supabase, Cloudflare, Claude API, GitHub)
- Messaging integrations (WhatsApp Business API, Telegram Bot API)
- CAFM integration (MRI Evolution FSI Public API)
- Operational processes (change management, incident response, BCP/DR)

---

## 3. Risk Management Framework

### 3.1 Risk Identification Methods

Risks are identified through four complementary approaches:

| Method | Description | Frequency |
|--------|-------------|-----------|
| **Threat-based** | Identify external threats targeting SENTINEL (attackers, malware, supply chain) | Quarterly |
| **Vulnerability-based** | Identify weaknesses in deployed controls (scanning results, audit findings) | Monthly |
| **Compliance-based** | Identify gaps against FSR questionnaire domains, POPIA, and industry standards | Quarterly |
| **Operational** | Identify risks from day-to-day operations (staff changes, vendor updates, incidents) | Continuous |

### 3.2 Risk Assessment Methodology

Each risk is assessed using a **Likelihood x Impact** matrix:

**Likelihood Scale (1-5):**

| Score | Level | Description |
|-------|-------|-------------|
| 1 | Rare | May occur only in exceptional circumstances (less than once per 5 years) |
| 2 | Unlikely | Could occur but not expected (once per 2-5 years) |
| 3 | Possible | Might occur at some time (once per 1-2 years) |
| 4 | Likely | Will probably occur in most circumstances (once or more per year) |
| 5 | Almost Certain | Expected to occur frequently (multiple times per year) |

**Impact Scale (1-5):**

| Score | Level | Description |
|-------|-------|-------------|
| 1 | Negligible | Minor inconvenience, no data loss, no service disruption |
| 2 | Minor | Limited service degradation (<1 hour), minor data exposure, no PI involved |
| 3 | Moderate | Service disruption (1-4 hours), limited PI exposure, regulatory notification may be needed |
| 4 | Major | Extended service outage (4-24 hours), significant PI exposure, FSR notification required |
| 5 | Critical | Complete service failure (>24 hours), large-scale PI breach, regulatory penalties, physical safety risk |

**Risk Score = Likelihood x Impact (range: 1-25)**

### 3.3 Risk Appetite

| Score Range | Rating | Response |
|-------------|--------|----------|
| 1-5 | **Low** | Accept -- monitor during quarterly review |
| 6-12 | **Medium** | Monitor/Mitigate -- implement proportionate controls, track progress |
| 13-20 | **High** | Mitigate Urgently -- implement controls within 30 days, escalate to management |
| 21-25 | **Critical** | Unacceptable -- immediate action required, cease affected operations if necessary |

### 3.4 Treatment Options

| Option | Description | When to Use |
|--------|-------------|-------------|
| **Accept** | Acknowledge risk, no additional controls | Low-scored risks where cost of mitigation exceeds potential impact |
| **Mitigate** | Implement controls to reduce likelihood or impact | Medium to high-scored risks where effective controls exist |
| **Transfer** | Transfer risk to third party (insurance, outsourcing) | Risks where specialist management is more effective |
| **Avoid** | Eliminate the risk by ceasing the activity | Unacceptable risks where no adequate mitigation exists |

---

## 4. Risk Register

### RISK-001: Single VPS Failure

| Field | Value |
|-------|-------|
| **Risk ID** | RISK-001 |
| **Category** | Infrastructure |
| **Description** | Single Contabo VPS hosts all SENTINEL services; hardware or hosting failure causes complete platform unavailability |
| **Threat** | Hardware failure, data centre incident, hosting provider outage |
| **Vulnerability** | Single point of failure -- no redundant infrastructure |
| **Likelihood** | 2 (Unlikely) |
| **Impact** | 5 (Critical) |
| **Risk Score** | **10 (Medium)** |
| **Treatment** | Mitigate |
| **Controls** | Regular backups (Supabase automated, InfluxDB daily snapshots), configuration as code (Docker Compose, infrastructure scripts), documented rebuild procedure (DR runbook at `infrastructure/bcpdr/dr-runbook.md`), BCP/DR test plan (`infrastructure/bcpdr/bcp-test-plan.md`) |
| **Owner** | System Administrator |
| **Status** | Active -- controls deployed (Phase 63-06) |
| **Review Date** | 2026-05-04 |

---

### RISK-002: Cross-Border Data Exposure (Claude API)

| Field | Value |
|-------|-------|
| **Risk ID** | RISK-002 |
| **Category** | Data Privacy / Compliance |
| **Description** | Personal Information (PI) sent to Claude API servers in the United States, creating POPIA cross-border transfer risk |
| **Threat** | Regulatory non-compliance, unauthorised access to PI in foreign jurisdiction |
| **Vulnerability** | Claude API requires data transfer to US-hosted infrastructure |
| **Likelihood** | 3 (Possible) |
| **Impact** | 4 (Major) |
| **Risk Score** | **12 (Medium)** |
| **Treatment** | Mitigate |
| **Controls** | POPIA Section 72 Data Processing Agreement with Anthropic, data minimisation (only building/equipment data sent, not occupant PI), PII guard middleware (Phase 63-04) strips PI before API calls, anonymisation of occupant identifiers, consent capture service (Phase 63-06) for messaging platforms |
| **Owner** | System Administrator |
| **Status** | Active -- controls deployed (Phase 63-04, 63-06) |
| **Review Date** | 2026-05-04 |

---

### RISK-003: Unauthorised BMS Device Control

| Field | Value |
|-------|-------|
| **Risk ID** | RISK-003 |
| **Category** | Operational / Safety |
| **Description** | Unauthorised or incorrect control commands sent to BMS equipment, potentially causing safety hazards or equipment damage |
| **Threat** | Malicious actor, compromised credentials, software bug issuing unvalidated commands |
| **Vulnerability** | Write access to BMS device points via API |
| **Likelihood** | 2 (Unlikely) |
| **Impact** | 5 (Critical) |
| **Risk Score** | **10 (Medium)** |
| **Treatment** | Mitigate |
| **Controls** | SafetyEngine validation on all control commands (temperature range 16-28C, pressure limits, runtime limits), RBAC with 4 roles restricting write access (Phase 63-04), comprehensive audit logging of all control actions, BMS write restrictions requiring operator+ role, safety interlock patterns preventing dangerous combinations |
| **Owner** | System Administrator |
| **Status** | Active -- controls deployed (Phase 6, Phase 63-04) |
| **Review Date** | 2026-05-04 |

---

### RISK-004: Cloud API Dependency Failure

| Field | Value |
|-------|-------|
| **Risk ID** | RISK-004 |
| **Category** | Operational |
| **Description** | Failure of cloud API dependencies (Claude, Supabase) causing service degradation or loss of functionality |
| **Threat** | Cloud provider outage, API rate limiting, network connectivity loss |
| **Vulnerability** | Dependency on multiple external cloud services for core functionality |
| **Likelihood** | 3 (Possible) |
| **Impact** | 3 (Moderate) |
| **Risk Score** | **9 (Medium)** |
| **Treatment** | Mitigate |
| **Controls** | Ollama local LLM fallback for AI queries (Tier 1 routing, Phase 22), JSON file fallback for database operations when Supabase unavailable, circuit breaker patterns in API clients, demo mode for offline operation, dual-write architecture (Supabase + JSON backup) |
| **Owner** | System Administrator |
| **Status** | Active -- controls deployed (Phase 22, existing architecture) |
| **Review Date** | 2026-05-04 |

---

### RISK-005: Supply Chain Vulnerability

| Field | Value |
|-------|-------|
| **Risk ID** | RISK-005 |
| **Category** | Application Security |
| **Description** | Compromised or vulnerable Python/JavaScript dependency introduces code execution, data exfiltration, or backdoor |
| **Threat** | Malicious package update, known vulnerability in dependency, typosquatting attack |
| **Vulnerability** | Large dependency tree across Python backend and React frontend |
| **Likelihood** | 2 (Unlikely) |
| **Impact** | 4 (Major) |
| **Risk Score** | **8 (Medium)** |
| **Treatment** | Mitigate |
| **Controls** | Dependabot automated updates across 4 ecosystems (Phase 63-03), pip-audit and safety scanning in CI/CD pipeline, Trivy container scanning, gitleaks secret detection, pinned dependency versions, pre-commit hooks blocking hardcoded secrets (detect-secrets), GitHub Actions security scanning (5 jobs: bandit, pip-audit, gitleaks, trivy, safety) |
| **Owner** | System Administrator |
| **Status** | Active -- controls deployed (Phase 63-03) |
| **Review Date** | 2026-05-04 |

---

### RISK-006: Insider Threat

| Field | Value |
|-------|-------|
| **Risk ID** | RISK-006 |
| **Category** | Human Resources |
| **Description** | Authorised user with privileged access performs unauthorised actions -- data exfiltration, sabotage, or policy violation |
| **Threat** | Disgruntled employee, compromised insider account, negligent privileged user |
| **Vulnerability** | Small team with broad access, limited separation of duties |
| **Likelihood** | 1 (Rare) |
| **Impact** | 5 (Critical) |
| **Risk Score** | **5 (Low)** |
| **Treatment** | Accept/Monitor |
| **Controls** | PAM with role-based sudo controls (Phase 63-04), comprehensive audit logging of all actions, access reviews on role change or departure, SSH key-only authentication (no shared passwords), small team with high trust but monitored access, Wazuh FIM detecting unauthorised file changes |
| **Owner** | System Administrator |
| **Status** | Active -- monitoring in place |
| **Review Date** | 2026-05-04 |

---

### RISK-007: WhatsApp/Telegram Data Leakage

| Field | Value |
|-------|-------|
| **Risk ID** | RISK-007 |
| **Category** | Data Privacy |
| **Description** | Occupant personal information exposed via messaging platform integrations (WhatsApp Business, Telegram Bot) |
| **Threat** | Data leakage through messaging platforms, unauthorised access to conversation history, platform data retention |
| **Vulnerability** | Messaging platforms store conversation content on their servers |
| **Likelihood** | 2 (Unlikely) |
| **Impact** | 4 (Major) |
| **Risk Score** | **8 (Medium)** |
| **Treatment** | Mitigate |
| **Controls** | Consent capture service with SHA-256 record hashing (Phase 63-06), PII guard middleware filtering PI from responses (Phase 63-04), data minimisation -- only building/equipment data in responses, no occupant PI stored in conversation logs, consent records with opt-in/opt-out tracking |
| **Owner** | System Administrator |
| **Status** | Active -- controls deployed (Phase 63-04, 63-06) |
| **Review Date** | 2026-05-04 |

---

### RISK-008: Undetected Intrusion

| Field | Value |
|-------|-------|
| **Risk ID** | RISK-008 |
| **Category** | Infrastructure Security |
| **Description** | Attacker gains access to VPS and persists undetected, compromising data confidentiality and system integrity |
| **Threat** | Advanced persistent threat, opportunistic attacker, automated botnet exploitation |
| **Vulnerability** | Internet-facing services, potential unpatched vulnerabilities, configuration drift |
| **Likelihood** | 2 (Unlikely) |
| **Impact** | 5 (Critical) |
| **Risk Score** | **10 (Medium)** |
| **Treatment** | Mitigate |
| **Controls** | Wazuh IDS with file integrity monitoring and rootkit detection (Phase 63-02), Grafana Loki centralised log aggregation with 6 SIEM alerting rules and 90-day retention (Phase 63-01), Fail2Ban brute-force protection (Phase 63-02), Cloudflare WAF with 9 rules (Phase 63-02), SSH hardening (key-only, no root login, Phase 63-04), monthly external and quarterly internal vulnerability scanning (Phase 63-05) |
| **Owner** | System Administrator |
| **Status** | Active -- controls deployed (Phase 63-01, 63-02, 63-04, 63-05) |
| **Review Date** | 2026-05-04 |

---

### RISK-009: Compliance Non-Conformance

| Field | Value |
|-------|-------|
| **Risk ID** | RISK-009 |
| **Category** | Compliance |
| **Description** | Failure to meet FSR questionnaire requirements resulting in submission rejection or client confidence loss |
| **Threat** | Governance gaps, incomplete documentation, unaddressed audit findings |
| **Vulnerability** | Evolving FSR requirements, limited dedicated compliance resources |
| **Likelihood** | 2 (Unlikely) |
| **Impact** | 4 (Major) |
| **Risk Score** | **8 (Medium)** |
| **Treatment** | Mitigate |
| **Controls** | Phase 64 governance documents addressing all 18 FSR domains, quarterly compliance self-assessment against FSR questionnaire, annual formal risk assessment with full register review, security audit programme with FSR reporting cadence, remediation tracker with SLA enforcement (Phase 63-05 at `infrastructure/scanning/remediation-tracker.md`) |
| **Owner** | System Administrator |
| **Status** | Active -- Phase 64 governance documents in progress |
| **Review Date** | 2026-05-04 |

---

### RISK-010: Data Loss

| Field | Value |
|-------|-------|
| **Risk ID** | RISK-010 |
| **Category** | Data Protection |
| **Description** | Loss of critical data due to backup failure, corruption, accidental deletion, or ransomware |
| **Threat** | Storage failure, ransomware encryption, accidental deletion, backup corruption |
| **Vulnerability** | Dependence on automated backup processes, limited backup verification |
| **Likelihood** | 2 (Unlikely) |
| **Impact** | 4 (Major) |
| **Risk Score** | **8 (Medium)** |
| **Treatment** | Mitigate |
| **Controls** | Supabase automated database backups (provider-managed), InfluxDB daily snapshots for time-series data, JSON file fallback providing secondary data copy, BCP/DR test plan with 5 scenarios including data recovery (Phase 63-06), configuration as code enabling infrastructure rebuild, Git version control for all application code and configuration |
| **Owner** | System Administrator |
| **Status** | Active -- controls deployed (Phase 63-06) |
| **Review Date** | 2026-05-04 |

---

## 5. Risk Summary Matrix

| Risk ID | Category | Risk Score | Rating | Treatment |
|---------|----------|------------|--------|-----------|
| RISK-001 | Infrastructure | 10 | Medium | Mitigate |
| RISK-002 | Data Privacy | 12 | Medium | Mitigate |
| RISK-003 | Safety | 10 | Medium | Mitigate |
| RISK-004 | Operational | 9 | Medium | Mitigate |
| RISK-005 | Application Security | 8 | Medium | Mitigate |
| RISK-006 | Human Resources | 5 | Low | Accept/Monitor |
| RISK-007 | Data Privacy | 8 | Medium | Mitigate |
| RISK-008 | Infrastructure Security | 10 | Medium | Mitigate |
| RISK-009 | Compliance | 8 | Medium | Mitigate |
| RISK-010 | Data Protection | 8 | Medium | Mitigate |

**Risk distribution:** 0 Critical, 0 High, 9 Medium, 1 Low

---

## 6. Compliance Evaluation Framework

### 6.1 Quarterly Self-Assessment

Every quarter, conduct a self-assessment against the FSR questionnaire domains:

1. Review each FSR domain (4.1 through 4.18) against deployed controls
2. Score current maturity level (1-5 scale)
3. Compare against target maturity levels
4. Identify gaps and create remediation plans
5. Document assessment results and actions

### 6.2 Annual Formal Risk Assessment

Annually, conduct a comprehensive risk assessment:

1. Full review of all entries in this risk register
2. Re-score likelihood and impact based on current threat landscape
3. Evaluate effectiveness of existing controls
4. Identify new risks from architectural changes, new integrations, or incidents
5. Update treatment plans for any risks with increased scores
6. Document assessment findings in annual security posture report

### 6.3 Continuous Monitoring

Technical controls provide ongoing risk monitoring:

- **Grafana Loki** (Phase 63-01): Real-time log aggregation with 6 SIEM alerting rules
- **Wazuh IDS** (Phase 63-02): File integrity monitoring, rootkit detection
- **Cloudflare WAF** (Phase 63-02): Web application firewall with 9 rules
- **Fail2Ban** (Phase 63-02): Brute-force detection and blocking
- **GitHub Actions** (Phase 63-03): CI/CD security scanning (5 jobs)
- **Vulnerability scanning** (Phase 63-05): Monthly external, quarterly internal

---

## 7. Deviation Management

### 7.1 Non-Conformance Documentation

When a non-conformance is identified (audit finding, incident, or policy violation):

1. **Document** the non-conformance with:
   - Description of the deviation
   - Root cause analysis
   - Affected systems or data
   - Discovery method (audit, incident, monitoring)
2. **Classify** severity: Critical, High, Medium, Low
3. **Assign** an owner and remediation deadline
4. **Track** progress in the remediation tracker (`infrastructure/scanning/remediation-tracker.md`)
5. **Verify** remediation effectiveness

### 7.2 Remediation SLAs

| Severity | Remediation Deadline | Escalation |
|----------|---------------------|------------|
| Critical | 7 days | Immediate management notification |
| High | 14 days | Weekly progress review |
| Medium | 30 days | Monthly progress review |
| Low | 90 days | Quarterly progress review |

### 7.3 FSR Notification

Deviations affecting FSR data or FSR questionnaire compliance require:

- Prompt notification to FSR within 72 hours of discovery (for significant deviations)
- Remediation plan shared with FSR
- Evidence of remediation provided upon completion

---

## 8. Review and Maintenance

### 8.1 Review Triggers

This risk register must be reviewed:

- **Quarterly** as part of routine governance cycle
- **After any P1/P2 security incident**
- **After significant architecture changes** (new integration, infrastructure migration)
- **After audit findings** requiring risk re-assessment
- **After changes to regulatory requirements** (POPIA amendments, new FSR requirements)

### 8.2 Version History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-02-04 | SENTINEL Platform Team | Initial risk register with 10 identified risks |

---

*Document: SENTINEL-ISR-001*
*Classification: Internal*
*Next Review: 2026-05-04*
