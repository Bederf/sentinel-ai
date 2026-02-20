---
title: "SENTINEL Information Security Strategy"
type: "policy"
status: "approved"
version: "1.0.0"
created: "2026-02-04"
updated: "2026-02-04"
author: "SENTINEL Security Office"
tags: ["security", "strategy", "governance", "maturity", "FSR", "roadmap"]
domain: "security"
audience: "all"
complexity: "intermediate"
estimated_read_time: 20
classification: "Confidential"
review_date: "2027-02-04"
---

# SENTINEL Information Security Strategy

## 1. Strategic Objectives

### 1.1 Purpose

This document defines the information security strategy for the SENTINEL BMS Intelligence Platform. It aligns security investment and effort with the SENTINEL product roadmap, establishes measurable maturity targets per FSR security domain, and sets the remediation roadmap to achieve FSR supplier onboarding readiness.

### 1.2 Strategic Objectives

| # | Objective | Success Measure | Timeline |
|---|---|---|---|
| SO-1 | Achieve FSR supplier security threshold across all 18 domains | All domains score >= 3.5 on FSR 0-5 maturity scale | Q2 2026 |
| SO-2 | Establish ISO 27001-aligned ISMS governance | Framework, policies, and supporting documents approved | Q1 2026 |
| SO-3 | Deploy technical security controls | SIEM, IDS, WAF, SAST/DAST, PAM, vulnerability scanning operational | Q1-Q2 2026 |
| SO-4 | Complete independent security validation | External audit and penetration test completed with no critical findings | Q2 2026 |
| SO-5 | Achieve POPIA compliance for SENTINEL data processing | Privacy impact assessments complete, consent mechanisms operational, cross-border transfer controls documented | Q1 2026 |
| SO-6 | Maintain ongoing security maturity | Quarterly health reports demonstrate sustained compliance; annual improvement cycle | Ongoing |

---

## 2. Current Maturity Assessment

### 2.1 Assessment Summary

The following table summarises SENTINEL's current maturity scores against the FSR Privacy and Service Risk Assessment Questionnaire V8. Scores are based on the internal gap analysis conducted in January 2026 (see `.planning/phases/64-risk-governance-foundation/FSR-GAP-ANALYSIS.md` for full assessment).

| # | FSR Domain | Threshold | Baseline | Current | Target | Gap | Priority |
|---|---|---|---|---|---|---|---|
| 4.1 | Information Security Governance | 3.5 | 3.0 | **3.7** | 4.0 | LOW | Phase 64 ✅ |
| 4.2 | Asset Management | 3.5 | 4.0 | 4.0 | 4.5 | LOW | Phase 64 |
| 4.3 | Information Classification | 3.5 | 3.5 | 3.5 | 4.0 | LOW | Phase 64 |
| 4.4 | Human Resource Security | 3.5 | 3.0 | 3.0 | 3.8 | MEDIUM | Phase 64 |
| 4.5 | Physical Access Security | 3.5 | 4.0 | 4.0 | 4.0 | NONE | N/A |
| 4.6 | Network Security | 3.5 | 4.0 | 4.0 | 4.5 | LOW | Phase 64 |
| 4.7 | Logical Access Control | 3.5 | 3.0 | **3.8** | 4.0 | LOW | Phase 63 + 64 ✅ |
| 4.8 | System Security | 3.5 | 3.5 | 3.5 | 4.0 | LOW | Phase 63 + 64 |
| 4.9 | Application Security | 3.5 | 2.5 | **3.8** | 4.0 | LOW | Phase 63 + 64 ✅ |
| 4.10 | Vulnerability Management | 3.5 | 3.0 | **4.3** | 4.5 | LOW | Phase 63 + 64 ✅ |
| 4.11 | Communication Management | 3.5 | 4.0 | 4.0 | 4.0 | NONE | Phase 64 |
| 4.12 | Cryptography & Key Management | 3.5 | 4.0 | 4.0 | 4.5 | LOW | Phase 64 |
| 4.13 | Incident Detection | 3.5 | 3.0 | **3.8** | 4.0 | LOW | Phase 63 ✅ |
| 4.14 | Incident Management | 3.5 | 3.0 | 3.2 | 4.0 | MEDIUM | Phase 64 |
| 4.15 | Business Continuity | 3.5 | 3.0 | 3.0 | 4.0 | MEDIUM | Phase 63 + 64 |
| 4.16 | Third Party Management | 3.5 | 3.5 | **3.7** | 4.0 | LOW | Phase 64 ✅ |
| 4.17 | Risk & Compliance Management | 3.5 | 3.0 | **3.5** | 4.0 | LOW | Phase 64 ✅ |
| 4.18 | Information Security Audit | 3.5 | 2.0 | 3.0 | 3.5 | MEDIUM | External |

### 2.2 Key Findings

> **Updated February 2026** — reflects remediation work completed through Phase 81.

- **3 of 18 domains** currently score below the FSR threshold of 3.5 (was 10 originally)
- **0 HIGH gap domains** remain (was 4 originally)
- **3 MEDIUM gap domains** remain: Human Resource Security (3.0), Business Continuity (3.0), Information Security Audit (3.0)
- **Deployment context:** SENTINEL runs locally on-premises with only Telegram and WhatsApp as external interfaces. This minimal attack surface means the automated scanning pipeline exceeds what the threat model requires.
- **1 domain exceeds target:** Vulnerability Management (4.3 vs 4.0 target) — 5-job CI pipeline + Dependabot across 4 ecosystems

---

## 3. Target Maturity by Domain

### 3.1 Maturity Scale Reference

| Score | Level | Description |
|---|---|---|
| 0 | Non-existent | No awareness of the need for the control |
| 1 | Initial | Ad-hoc, undocumented |
| 2 | Repeatable | Consistent but undocumented |
| 3 | Defined | Documented and standardised |
| 4 | Managed | Measured and monitored |
| 5 | Optimised | Continuously improving |

### 3.2 Target Scores

The target score for each domain is set above the FSR threshold of 3.5 to provide a safety margin and demonstrate continuous improvement capability.

| Domain | Current | Target | Improvement Required |
|---|---|---|---|
| 4.1 Information Security Governance | 3.0 | 4.0 | +1.0 via framework, strategy, policy, AUP |
| 4.2 Asset Management | 4.0 | 4.5 | +0.5 via formal asset register |
| 4.3 Information Classification | 3.5 | 4.0 | +0.5 via classification policy and data mapping |
| 4.4 Human Resource Security | 3.0 | 3.8 | +0.8 via HR security policy, training programme |
| 4.5 Physical Access Security | 4.0 | 4.0 | Maintain (cloud-hosted, provider attestations) |
| 4.6 Network Security | 4.0 | 4.5 | +0.5 via formal network security policy |
| 4.7 Logical Access Control | 3.0 | 4.0 | +1.0 via access control policy, PAM, MFA, RBAC |
| 4.8 System Security | 3.5 | 4.0 | +0.5 via system security policy, CIS benchmarks |
| 4.9 Application Security | 2.5 | 4.0 | +1.5 via AppSec policy, SAST/DAST, secure coding standards, WAF |
| 4.10 Vulnerability Management | 3.0 | 4.0 | +1.0 via VM policy, scanning, remediation SLAs |
| 4.11 Communication Management | 4.0 | 4.0 | Maintain (TLS, encrypted comms) |
| 4.12 Cryptography & Key Management | 4.0 | 4.5 | +0.5 via crypto policy, key rotation procedures |
| 4.13 Incident Detection | 3.0 | 4.0 | +1.0 via SIEM, centralised logging, IDS |
| 4.14 Incident Management | 3.0 | 4.0 | +1.0 via incident response policy, team, register |
| 4.15 Business Continuity | 3.0 | 4.0 | +1.0 via BCP/DR policy, testing, runbooks |
| 4.16 Third Party Management | 3.5 | 4.0 | +0.5 via third-party security policy, register |
| 4.17 Risk & Compliance | 3.0 | 4.0 | +1.0 via risk policy, risk register, assessments |
| 4.18 Information Security Audit | 2.0 | 3.5 | +1.5 via independent audit, audit cadence |

---

## 4. Strategic Priorities

### 4.1 Priority Ordering

Remediation is prioritised by gap severity. HIGH gaps are addressed first as they represent the greatest risk to FSR onboarding approval.

**Priority 1 - HIGH gaps (address first):**

1. **Logical Access Control (4.7):** Formal access control policy, PAM implementation, MFA enforcement, RBAC documentation, stale account reviews
2. **Application Security (4.9):** Secure coding standards, SAST/DAST pipeline, WAF deployment, application security assessment
3. **Incident Detection (4.13):** Centralised logging (Loki/Promtail), SIEM implementation, host-based IDS (OSSEC/Wazuh), alerting rules
4. **Security Audit (4.18):** Independent security assessment, audit cadence establishment, findings tracking

**Priority 2 - MEDIUM gaps (address second):**

5. **Information Security Governance (4.1):** Framework, strategy, policy, AUP documents
6. **Human Resource Security (4.4):** HR security policy, training programme, joiners/leavers process
7. **Vulnerability Management (4.10):** VM policy, scanning schedule, remediation SLAs
8. **Incident Management (4.14):** Incident response policy, IRT team, incident register
9. **Business Continuity (4.15):** BCP/DR policy, recovery procedures, annual testing
10. **Third Party Management (4.16):** Third-party security policy, supplier register, compliance framework
11. **Risk & Compliance (4.17):** Risk management policy, risk register, annual assessment
12. **System Security (4.8):** System security policy, CIS benchmarks, patch management

**Priority 3 - LOW gaps (finalise):**

13. **Asset Management (4.2):** Formal asset register, disposal procedures
14. **Information Classification (4.3):** Classification policy, data type mapping
15. **Network Security (4.6):** Network security policy, firewall review procedures
16. **Communication Management (4.11):** Communication security documentation
17. **Cryptography (4.12):** Crypto policy, key rotation procedures

---

## 5. Remediation Roadmap

### 5.1 Phase Mapping

| Phase | Timeline | Focus | Deliverables |
|---|---|---|---|
| **Phase 63: Technical Implementation** | Weeks 1-4 (Complete) | Deploy technical security controls | Centralised logging, SIEM, IDS, WAF, SAST/DAST, vulnerability scanning, PAM, MFA, container scanning, dependency monitoring, consent capture, security training, BCP/DR test |
| **Phase 64: Governance Foundation** | Weeks 5-8 (Current) | Create all governance documents | 19 policy and governance documents across 18 FSR domains |
| **Phase 65: External Validation** | Weeks 9-12 (Planned) | Independent verification | External security audit, penetration test, third-party attestations |
| **Phase 66: FSR Submission** | Weeks 13-16 (Planned) | Submission preparation | Questionnaire completion, evidence compilation, review rehearsal |

### 5.2 Phase 64 Governance Document Plan

Phase 64 is divided into 6 execution plans:

| Plan | Documents | FSR Domains |
|---|---|---|
| 64-01 | Information Security Framework, Strategy, Policy, AUP | 4.1 Governance |
| 64-02 | Access Control Policy, Application Security Policy, Secure Coding Standards | 4.7, 4.9 |
| 64-03 | Vulnerability Management Policy, Incident Response Policy | 4.10, 4.13-4.14 |
| 64-04 | BCP/DR Policy, Third-Party Security Policy | 4.15, 4.16 |
| 64-05 | Risk Management Policy, Data Privacy & Classification Policy | 4.17, 4.3 |
| 64-06 | HR Security Policy, Cryptography Policy, Asset Register, Security Audit Procedure | 4.4, 4.12, 4.2, 4.18 |

### 5.3 Dependencies

```
Phase 63 (Technical Controls)
    ↓ provides evidence for ↓
Phase 64 (Governance Documents)
    ↓ establishes framework for ↓
Phase 65 (External Validation)
    ↓ produces attestations for ↓
Phase 66 (FSR Submission)
```

---

## 6. Resource Allocation

### 6.1 Approach

SENTINEL's security remediation leverages existing team capabilities augmented by targeted external resources:

| Resource | Allocation | Focus |
|---|---|---|
| **ISO (internal)** | 20% of time during remediation phases | Policy drafting, risk assessments, compliance coordination |
| **System Administrator (internal)** | 30% of time during Phase 63 | Technical control deployment, infrastructure hardening |
| **Lead Developer (internal)** | 20% of time during Phase 63-64 | SAST/DAST integration, secure coding standards, peer review process |
| **External Auditor** | Engagement during Phase 65 | Independent security assessment, penetration testing |
| **Legal Counsel** | As needed | POPIA compliance review, cross-border transfer advice, contract review |

### 6.2 Budget Considerations

| Item | Estimated Cost | Justification |
|---|---|---|
| External security audit | R50,000 - R100,000 | Required for FSR domain 4.18 and independent validation |
| Penetration testing | R30,000 - R60,000 | Required for FSR domain 4.9 Application Security |
| Security tools (SIEM, IDS, scanning) | R0 - R5,000/month | Open-source tools preferred (Loki, OSSEC, Trivy); cloud options if needed |
| Legal review | R10,000 - R20,000 | POPIA compliance, cross-border data flow advice |

---

## 7. Success Metrics

### 7.1 Primary Metric

**All 18 FSR domains at or above the 3.5 threshold** on the FSR 0-5 maturity scale. This is the mandatory requirement for FSR supplier onboarding.

### 7.2 Supporting Metrics

| Metric | Target | Measurement |
|---|---|---|
| FSR domain scores | All >= 3.5, average >= 4.0 | FSR self-assessment quarterly |
| Policy coverage | 100% of 18 FSR domains covered by a policy document | Document index in `docs/08-security/README.md` |
| Security incidents (critical) | 0 unresolved critical incidents | Incident register |
| Vulnerability remediation | Critical: 7 days, High: 14 days | Vulnerability tracker |
| Training completion | 100% of personnel annually | Training register |
| Access review completion | 100% of accounts reviewed monthly | Access review log |
| BCP/DR test completion | 1 test per year minimum | Test report |
| Audit findings (critical/high) | 0 critical, <3 high open | Audit findings tracker |
| Mean time to detect (MTTD) | < 24 hours for security events | SIEM/logging metrics |
| Mean time to respond (MTTR) | < 4 hours for critical incidents | Incident register |

---

## 8. Quarterly Information Security Health Report

### 8.1 Template Outline

The ISO produces a Quarterly Information Security Health Report covering the following sections:

```
SENTINEL Quarterly Information Security Health Report
Quarter: Q[N] [Year]
Prepared by: Information Security Officer
Date: [DD Month YYYY]

1. Executive Summary
   - Overall security posture (Green/Amber/Red)
   - Key events this quarter
   - Significant changes to risk profile

2. FSR Domain Maturity Scores
   - Current scores per domain (table)
   - Domains below threshold (if any)
   - Score trends vs previous quarter

3. Security Incidents
   - Number of incidents by severity
   - Incident summary (anonymised)
   - Resolution status
   - Lessons learned

4. Vulnerability Management
   - Vulnerabilities discovered vs remediated
   - Remediation SLA compliance (% within target)
   - Outstanding critical/high vulnerabilities

5. Access Control
   - New accounts provisioned/deprovisioned
   - Stale account review results
   - Privileged access changes

6. Compliance Status
   - POPIA compliance actions
   - FSR requirement changes
   - Third-party compliance status

7. Training
   - Training completion rates
   - New training content deployed

8. Key Risk Changes
   - New risks identified
   - Risks closed/accepted
   - Risk register summary

9. Recommendations
   - Proposed security improvements
   - Budget requirements
   - Resource needs

10. Next Quarter Priorities
    - Focus areas
    - Planned activities
    - Dependencies
```

### 8.2 Distribution

- **Internal:** Managing Director, ISO, System Administrator, Lead Developer
- **Client stakeholders:** Provided to FSR or other clients upon request as evidence of ongoing security management
- **Retention:** Reports retained for 3 years minimum

---

## 9. Review Cadence

| Activity | Frequency |
|---|---|
| Information Security Strategy review | Annual (this document) |
| Quarterly Health Report | Quarterly (Q1, Q2, Q3, Q4) |
| FSR domain self-assessment | Quarterly |
| Risk assessment | Annual (comprehensive), quarterly (review) |
| Policy suite review | Annual |

---

## 10. Version Control

| Version | Date | Author | Changes |
|---|---|---|---|
| 1.0 | 2026-02-04 | SENTINEL Security Office | Initial release. Establishes strategic objectives, maturity assessment, target scores, remediation roadmap, resource allocation, and quarterly reporting template for FSR compliance. |
| 1.1 | 2026-02-19 | SENTINEL Team | Updated maturity scores to reflect Phase 63-81 remediation. Added Baseline/Current columns. Governance 3.0→3.7, App Security 2.5→3.8, Vulnerability Mgmt 3.0→4.3, Incident Detection 3.0→3.8, Logical Access 3.0→3.8. Added deployment context (local with Telegram/WhatsApp only external). |

---

*Classification: Confidential*
*Next Review: 2027-02-04*
*Owner: Information Security Officer*
