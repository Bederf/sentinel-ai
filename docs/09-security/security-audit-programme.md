# Security Audit Programme

**Document ID:** SENTINEL-SAP-001
**Version:** 1.0
**Effective Date:** 2026-02-04
**Review Cadence:** Annual, or after major audit findings
**Owner:** SENTINEL Platform Team
**Classification:** Internal

---

## 1. Purpose

This document establishes a structured programme for independent verification of SENTINEL's security controls. It defines audit types, scope, methodology, calendar, and reporting requirements to ensure continuous assurance that deployed controls are effective and compliant with FSR requirements.

---

## 2. Scope

The security audit programme covers all aspects of SENTINEL's security posture:

- **Infrastructure security** -- VPS (Contabo), Docker containers, networking, SSH, firewall
- **Application security** -- FastAPI backend, React frontend, ML pipeline, API endpoints
- **Data security** -- PI handling, encryption at rest/in transit, access controls, data classification
- **Operational security** -- Change management, incident response, BCP/DR procedures
- **Third-party security** -- Cloud vendor compliance (Supabase, Cloudflare, Anthropic), messaging platform security (WhatsApp, Telegram)

---

## 3. Audit Types

### 3.1 Internal Audit

| Attribute | Detail |
|-----------|--------|
| **Frequency** | Quarterly |
| **Scope** | Self-assessment against deployed controls and policies |
| **Performed by** | SENTINEL Platform Team |
| **Output** | Internal audit report with findings and action items |

**Internal audit activities include:**

- Review of access control effectiveness (RBAC roles, PAM configuration)
- Verification of logging and monitoring (Loki log retention, SIEM alert effectiveness)
- Check of vulnerability scanning compliance (monthly external, quarterly internal)
- Review of incident response procedures and any incidents since last audit
- Verification of BCP/DR readiness (test results, runbook currency)
- Assessment of security awareness training completion rates
- Review of change management compliance

### 3.2 Technical Audit

| Attribute | Detail |
|-----------|--------|
| **Frequency** | Monthly (external scan), Quarterly (internal scan) |
| **Scope** | Automated security scanning of infrastructure and applications |
| **Performed by** | Automated tools (Phase 63-05 scanning infrastructure) |
| **Output** | Scan reports with vulnerability findings |

**Technical audit activities include:**

- **Monthly external scanning** (`infrastructure/scanning/external-scan.sh`):
  - Port scanning and service enumeration
  - SSL/TLS certificate validity and configuration
  - Web application vulnerability scanning
  - DNS configuration review
- **Quarterly internal scanning** (`infrastructure/scanning/internal-scan.sh`):
  - Docker container vulnerability scanning (Trivy)
  - Dependency vulnerability audit (pip-audit, safety)
  - Configuration compliance checking
  - File integrity verification
- **Continuous scanning** (GitHub Actions, Phase 63-03):
  - Bandit (Python static analysis)
  - pip-audit (Python dependency vulnerabilities)
  - gitleaks (secret detection)
  - Trivy (container scanning)
  - safety (Python dependency safety)

### 3.3 Independent Audit

| Attribute | Detail |
|-----------|--------|
| **Frequency** | Annual |
| **Scope** | Third-party security assessment of SENTINEL platform |
| **Performed by** | Independent security assessor (external) |
| **Output** | Independent audit report with classified findings |

**Independent audit activities include:**

- Penetration testing covering OWASP Top 10 and BMS-specific attack vectors
- Architecture review and threat modelling
- Source code security review (critical components)
- Configuration review of infrastructure and applications
- Social engineering assessment (if applicable)
- Physical security review of hosting environment (if accessible)

### 3.4 Compliance Audit

| Attribute | Detail |
|-----------|--------|
| **Frequency** | Annual |
| **Scope** | Review against FSR questionnaire domains and POPIA requirements |
| **Performed by** | SENTINEL Platform Team with independent review |
| **Output** | Compliance audit report with gap analysis |

**Compliance audit activities include:**

- Point-by-point review against all 18 FSR questionnaire domains (4.1 through 4.18)
- POPIA compliance assessment (PI handling, cross-border transfers, consent)
- Policy review and currency check (all security policies)
- Evidence mapping -- verify each control claim has supporting evidence
- Gap identification with remediation recommendations

---

## 4. Annual Audit Calendar

| Quarter | Activity | Type | Owner |
|---------|----------|------|-------|
| **Q1 (Jan-Mar)** | Internal controls self-assessment | Internal | Platform Team |
| **Q1 (Jan-Mar)** | Annual risk assessment (full register review) | Internal | Platform Team |
| **Q1 (Jan-Mar)** | Monthly external scans (Jan, Feb, Mar) | Technical | Automated |
| **Q1 (Mar)** | Quarterly internal scan | Technical | Automated |
| **Q2 (Apr-Jun)** | Independent penetration test | Independent | External Assessor |
| **Q2 (Apr-Jun)** | Independent security assessment | Independent | External Assessor |
| **Q2 (Apr-Jun)** | Monthly external scans (Apr, May, Jun) | Technical | Automated |
| **Q2 (Jun)** | Quarterly internal scan | Technical | Automated |
| **Q3 (Jul-Sep)** | Third-party compliance review | Compliance | Platform Team + Reviewer |
| **Q3 (Jul-Sep)** | Internal infrastructure audit | Internal | Platform Team |
| **Q3 (Jul-Sep)** | Monthly external scans (Jul, Aug, Sep) | Technical | Automated |
| **Q3 (Sep)** | Quarterly internal scan | Technical | Automated |
| **Q4 (Oct-Dec)** | Annual compliance evaluation | Compliance | Platform Team |
| **Q4 (Oct-Dec)** | FSR reporting preparation | Compliance | Platform Team |
| **Q4 (Oct-Dec)** | Monthly external scans (Oct, Nov, Dec) | Technical | Automated |
| **Q4 (Dec)** | Quarterly internal scan | Technical | Automated |

---

## 5. Audit Methodology

### 5.1 Compliance-Based Assessment

Verify that controls exist and are effective through policy-to-evidence mapping:

1. **Identify control requirement** from FSR domain or internal policy
2. **Locate evidence** of control implementation:
   - Configuration files (infrastructure/, .github/)
   - Monitoring dashboards (Grafana, Loki)
   - Scan reports (external/internal scan results)
   - Log entries (audit logs, access logs)
   - Training records (security awareness completion)
   - Test results (BCP/DR test outcomes)
3. **Evaluate effectiveness** -- is the control operating as intended?
4. **Document findings** -- conformance, partial conformance, or non-conformance
5. **Recommend improvements** where controls are insufficient

### 5.2 Threat-Based Assessment

Simulate attack scenarios to test control weaknesses:

- **Penetration testing**: External and internal attack simulation
  - Network penetration (port scanning, service exploitation)
  - Web application testing (OWASP Top 10)
  - API security testing (authentication bypass, injection)
  - BMS-specific vectors (device control bypass, safety system circumvention)
- **Tabletop exercises**: Scenario-based discussion of incident response
  - Data breach scenario
  - Ransomware scenario
  - Insider threat scenario
  - BMS equipment safety incident
  - Cloud provider failure

---

## 6. Audit Evidence Requirements

### 6.1 Evidence Base from Phase 63 Technical Controls

The following deployed controls provide the primary evidence base for audits:

| Control Area | Evidence Source | Phase |
|-------------|----------------|-------|
| Centralised logging | Grafana Loki logs (90-day retention) | 63-01 |
| SIEM alerting | 6 security alerting rules in Grafana | 63-01 |
| Intrusion detection | Wazuh FIM alerts, rootkit scan results | 63-02 |
| Web application firewall | Cloudflare WAF event logs (9 rules) | 63-02 |
| Brute-force protection | Fail2Ban ban logs and statistics | 63-02 |
| Static analysis | Bandit scan results (CI/CD) | 63-03 |
| Dependency scanning | pip-audit, safety reports (CI/CD) | 63-03 |
| Secret detection | gitleaks, detect-secrets results | 63-03 |
| Container scanning | Trivy scan reports (CI/CD) | 63-03 |
| Dependency updates | Dependabot status (4 ecosystems) | 63-03 |
| Access control | PAM configuration, RBAC role assignments | 63-04 |
| SSH hardening | sshd configuration, key-only auth | 63-04 |
| API authentication | Auth middleware logs, JWT validation | 63-04 |
| PII protection | PII guard filtering logs | 63-04 |
| Vulnerability scanning | Monthly external, quarterly internal reports | 63-05 |
| Remediation tracking | Remediation tracker with SLA enforcement | 63-05 |
| BCP/DR testing | Test results from 5 BCP/DR scenarios | 63-06 |
| Security training | Training completion records (5 modules) | 63-06 |
| Consent management | Consent capture records with SHA-256 hashing | 63-06 |

### 6.2 Additional Evidence Sources

- Access review records (joiners/leavers checklist completion)
- Change management logs (Git commit history, PR reviews)
- Incident response records (if any incidents occurred)
- Risk register review minutes
- Policy acknowledgement records

---

## 7. Findings Management

### 7.1 Finding Classification

| Classification | Description | Example |
|---------------|-------------|---------|
| **Critical** | Immediate threat to security; exploitable vulnerability with high impact | Unauthenticated API endpoint exposing PI |
| **High** | Significant weakness requiring urgent remediation | Missing encryption on sensitive data store |
| **Medium** | Moderate weakness with limited exploitability or impact | Weak password policy enforcement |
| **Low** | Minor issue with minimal security impact | Informational disclosure in error messages |
| **Observation** | Best practice recommendation, no current risk | Logging format inconsistency |

### 7.2 Remediation SLAs

| Classification | Remediation Deadline | Progress Review |
|---------------|---------------------|-----------------|
| Critical | 7 days | Daily until resolved |
| High | 14 days | Weekly |
| Medium | 30 days | Bi-weekly |
| Low | 90 days | Monthly |
| Observation | Next scheduled review | Quarterly |

### 7.3 Remediation Tracking

All findings are tracked through the remediation tracker deployed in Phase 63-05:

- **File**: `infrastructure/scanning/remediation-tracker.md`
- **Process**: Finding logged with ID, classification, description, owner, deadline
- **Monitoring**: SLA compliance tracked, overdue items escalated
- **Closure**: Evidence of remediation documented, re-tested, and verified

---

## 8. FSR Reporting

### 8.1 Quarterly Summary

Provide FSR with a quarterly summary of audit activities:

- Audit activities conducted during the quarter
- Number and classification of findings (new, closed, open)
- Remediation progress and SLA compliance
- Significant changes to security posture
- Upcoming audit activities

### 8.2 Annual Comprehensive Report

Provide FSR with an annual comprehensive security posture report:

- Summary of all audit activities conducted during the year
- Aggregated findings analysis (trends, patterns, improvements)
- Risk register review outcomes
- Compliance status against all FSR questionnaire domains
- Security training completion rates
- BCP/DR test results
- Key security improvements implemented
- Forward-looking security roadmap

### 8.3 Critical Finding Notification

Findings classified as Critical that affect FSR data or systems require:

- **Immediate notification** to FSR within 24 hours of discovery
- **Impact assessment** -- what FSR data is affected and exposure scope
- **Containment actions** taken to limit further exposure
- **Remediation plan** with estimated timeline
- **Evidence of remediation** upon completion
- **Post-incident review** shared with FSR

---

## 9. Pre-Submission Requirements

Before any FSR submission, the following audit activities must be completed:

### 9.1 Independent Application Security Assessment

- **Scope**: Full SENTINEL application stack (API, frontend, integrations)
- **Coverage**: OWASP Top 10, SANS CWE Top 25, BMS-specific attack vectors
- **Output**: Assessment report with classified findings
- **Requirement**: All Critical and High findings remediated before submission

### 9.2 Penetration Test

- **Scope**: External and internal attack surface
- **Coverage**:
  - OWASP Top 10 web application vulnerabilities
  - API security testing (authentication, authorisation, injection)
  - BMS-specific vectors (device control bypass, safety override)
  - Infrastructure security (VPS, Docker, networking)
  - Social engineering (if applicable)
- **Output**: Penetration test report with proof-of-concept for findings
- **Requirement**: All Critical and High findings remediated with evidence

### 9.3 Remediation Evidence

- All Critical findings: Remediated, re-tested, and verified
- All High findings: Remediated, re-tested, and verified
- Medium findings: Remediation plan documented with timeline
- Low findings: Acknowledged with risk acceptance or remediation plan

---

## 10. Roles and Responsibilities

| Role | Responsibility |
|------|---------------|
| **System Administrator** | Schedule and coordinate audits, manage remediation tracker, FSR reporting |
| **Platform Team** | Internal audit execution, evidence collection, remediation implementation |
| **External Assessor** | Independent audit execution, penetration testing |
| **Management** | Approve audit scope, review findings, authorise remediation resources |

---

## 11. Version History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-02-04 | SENTINEL Platform Team | Initial security audit programme |

---

*Document: SENTINEL-SAP-001*
*Classification: Internal*
*Next Review: 2027-02-04*
