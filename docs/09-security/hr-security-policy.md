# Human Resource Security Policy

**Document ID:** SENTINEL-HRS-001
**Version:** 1.0
**Effective Date:** 2026-02-04
**Review Cadence:** Annual, or on organisational change
**Owner:** SENTINEL Platform Team
**Classification:** Internal

---

## 1. Purpose

This policy defines information security requirements throughout the employment and engagement lifecycle for all SENTINEL personnel. It establishes controls for pre-employment screening, ongoing security responsibilities, and termination procedures to protect SENTINEL systems, data, and FSR client information.

---

## 2. Scope

This policy applies to:

- All employees with access to SENTINEL systems or data
- Contractors and consultants engaged for SENTINEL-related work
- Third-party personnel with access to SENTINEL infrastructure or FSR data
- Temporary staff and interns with any level of system access

---

## 3. Role Definitions and Security Access Requirements

### 3.1 SENTINEL Roles

All roles include explicit information security responsibilities as defined by the RBAC model deployed in Phase 63-04:

| Role | System Access | Security Responsibilities |
|------|--------------|--------------------------|
| **System Administrator** | Full infrastructure access (PAM-controlled), all API endpoints, Cloudflare dashboard, GitHub admin, Supabase admin, Grafana/Loki admin | Security clearance required. Responsible for infrastructure security, patch management, access provisioning/deprovisioning, incident response, audit log review. PAM escalation logged and audited. |
| **Developer** | Source code repository access (GitHub), CI/CD pipeline access, local development environment, no direct production infrastructure access without PAM escalation | Secure coding practices, code review participation, dependency management, secret handling compliance. Production access only via PAM escalation with justification. |
| **Operator** | Application access (operator RBAC role), BMS monitoring dashboards, read-only API access, limited device control (non-safety-critical) | Monitor system health, report anomalies, follow operational procedures, escalate incidents. No administrative or infrastructure access. |
| **Technician** | Field operations access (technician RBAC role), work order management, mobile inspection forms, equipment baseline capture | Follow equipment handling procedures, report safety hazards, secure mobile device access, handle PI according to classification policy. |

### 3.2 Job Description Requirements

All job descriptions for SENTINEL-related roles must include:

- Explicit information security responsibilities relevant to the role
- Requirement to comply with all SENTINEL security policies
- Obligation to report security incidents and suspicious activity
- Acknowledgement that system access is monitored and audited
- Requirement for security awareness training completion

---

## 4. Pre-Employment / Pre-Engagement

### 4.1 Vetting and Screening

The following checks are required before granting access to SENTINEL systems:

| Check | Roles | Requirement |
|-------|-------|-------------|
| **Criminal background check** | All roles with access to FSR data or production systems | Clear criminal record verification. Completed before any system access provisioned. |
| **Reference verification** | All technical roles (System Administrator, Developer) | Minimum 2 professional references verified. Technical competence confirmed. |
| **Identity verification** | All roles | Government-issued identification verified before account creation. |
| **Qualification verification** | Roles requiring specific certifications | Relevant certifications confirmed (if specified in job description). |

**Records retention:** Vetting records retained for the duration of engagement plus 2 years after departure.

### 4.2 Contractual Requirements

Before any system access is granted, the following must be signed:

| Document | Purpose | Timing |
|----------|---------|--------|
| **Confidentiality / NDA** | Protect SENTINEL proprietary information, FSR client data, and occupant PI | Before any access granted |
| **Employment / Contractor Agreement** | Include information security responsibilities, data handling obligations, and acceptable use | Before engagement starts |
| **Acceptable Usage Policy (AUP) Acknowledgement** | Confirm understanding of permitted system usage, prohibited activities, monitoring | Before access provisioned |
| **Security Policy Acknowledgement** | Confirm receipt and understanding of all relevant security policies | Within first week |

---

## 5. During Employment / Engagement

### 5.1 Security Awareness Training

All personnel must complete security awareness training as deployed in Phase 63-06:

**Training Programme (5 modules):**

| Module | Content | Duration |
|--------|---------|----------|
| 1. POPIA and Data Protection | POPIA obligations, PI handling, data classification, cross-border transfer rules | 45 min |
| 2. Phishing and Social Engineering | Email phishing identification, social engineering tactics, reporting procedures | 30 min |
| 3. Password and Access Security | Password hygiene, MFA usage, credential management, shared access prohibition | 30 min |
| 4. Incident Reporting | What constitutes a security incident, reporting procedures, escalation paths | 30 min |
| 5. BMS Safety and Operations | BMS safety protocols, SafetyEngine rules, device control responsibilities, equipment handling | 45 min |

**Training requirements:**

- **Initial training**: Mandatory completion within 30 days of onboarding
- **Annual refresher**: Required annually for all personnel
- **Role-specific training**: Additional training for elevated roles (e.g., PAM usage for System Administrators)
- **Tracking**: Completion tracked by module, reported in quarterly security reviews
- **Non-completion**: Access restricted after 30-day deadline if training not completed

### 5.2 Ongoing Responsibilities

All personnel with access to SENTINEL systems must:

- Comply with all information security policies at all times
- Report security incidents and suspicious activity immediately to the System Administrator
- Protect credentials and never share access (SSH keys, API tokens, passwords)
- Handle data according to classification policy (PI treated as confidential)
- Lock workstations when unattended
- Use only approved devices and software for SENTINEL work
- Not install unauthorised software on systems with SENTINEL access
- Not bypass security controls (VPN, firewall, access restrictions)
- Cooperate with security audits and investigations

### 5.3 Performance and Compliance Monitoring

- Security policy compliance is monitored through audit logs:
  - SSH access logs reviewed for anomalous patterns
  - API access logs reviewed for policy violations
  - PAM escalation events reviewed for justification
  - Wazuh FIM alerts reviewed for unauthorised changes
- Non-compliance addressed through the disciplinary process (Section 7)
- Compliance metrics reported in quarterly security reviews

---

## 6. Termination / Change of Role

### 6.1 Joiners Process

When a new team member is onboarded:

| Step | Action | Owner | Timing |
|------|--------|-------|--------|
| 1 | **Approve access request** -- role-based, least privilege principle | System Administrator | Before start date |
| 2 | **Provision accounts** -- create accounts aligned to RBAC role (viewer/operator/technician/engineer) | System Administrator | Day 1 |
| 3 | **Issue credentials** -- SSH keys (Ed25519), API tokens as needed, initial passwords | System Administrator | Day 1 |
| 4 | **Complete security awareness training** -- all 5 modules (Phase 63-06) | New team member | Within 30 days |
| 5 | **Acknowledge policies** -- sign AUP, security policy, NDA/confidentiality | New team member | Within first week |
| 6 | **Verify completion** -- confirm all steps completed, document in access register | System Administrator | Day 30 |

### 6.2 Leavers Process

When a team member departs (termination, contract end, resignation):

| Step | Action | Owner | Timing |
|------|--------|-------|--------|
| 1 | **Trigger**: Receive termination notice, contract end date, or resignation | HR / Management | On notice |
| 2 | **Disable all system accounts** -- application accounts, API access | System Administrator | Within 24 hours of departure |
| 3 | **Revoke SSH keys** -- remove from authorized_keys on all servers | System Administrator | Within 24 hours of departure |
| 4 | **Revoke API tokens** -- invalidate all issued API tokens and JWT sessions | System Administrator | Within 24 hours of departure |
| 5 | **Remove from PAM groups** -- revoke sudo and elevated access (reference `infrastructure/pam/sudo-sentinel.conf`) | System Administrator | Within 24 hours of departure |
| 6 | **Remove Cloudflare dashboard access** -- revoke team member access | System Administrator | Within 24 hours of departure |
| 7 | **Revoke GitHub repository access** -- remove from organisation/repository | System Administrator | Within 24 hours of departure |
| 8 | **Review audit logs** -- check access logs for final 30 days for anomalous activity or data exfiltration | System Administrator | Within 7 days of departure |
| 9 | **Return/destroy assets** -- collect or confirm destruction of SENTINEL documentation, credentials, or data on personal devices | Departing member | On departure date |
| 10 | **Verify complete** -- confirm all access revoked using access review checklist | System Administrator | Within 7 days of departure |

### 6.3 Role Change Process

When a team member changes roles within the organisation:

1. **Re-assess access** -- evaluate access requirements for new role against RBAC model
2. **Remove unnecessary permissions** -- revoke access no longer required for new role
3. **Grant new permissions** -- add access required for new role (least privilege)
4. **Update PAM groups** -- adjust sudo and escalation permissions as needed
5. **Acknowledge changes** -- team member confirms understanding of new access scope
6. **Document** -- update access register with role change and new permissions
7. **Additional training** -- assign role-specific training if new role requires elevated access

---

## 7. Disciplinary Process for Security Violations

### 7.1 Violation Categories

| Category | Description | Examples |
|----------|-------------|---------|
| **Minor** | First offence, low impact, no data loss | Failing to lock workstation, late training completion, weak password usage |
| **Moderate** | Repeated minor violations or medium impact | Sharing credentials, bypassing security controls, installing unauthorised software |
| **Serious** | Significant security impact, wilful non-compliance | Data breach (accidental or negligent), circumventing safety controls, unauthorised data access |
| **Criminal** | Illegal activity, intentional harm | Data theft, sabotage, selling credentials, intentional system damage |

### 7.2 Response Actions

| Category | Response | Escalation |
|----------|----------|------------|
| **Minor** | Verbal warning, mandatory additional training, documented in personnel file | System Administrator |
| **Moderate** | Written warning, access review (potentially restricted), mandatory training, documented | Management |
| **Serious** | Immediate access suspension pending investigation, formal disciplinary process, potential termination | Management + Legal |
| **Criminal** | Immediate access suspension, report to authorities (SAPS), formal investigation, termination | Management + Legal + Law enforcement |

### 7.3 Investigation Process

For Moderate and Serious violations:

1. **Suspend access** -- immediately upon discovery for Serious violations
2. **Preserve evidence** -- secure audit logs, system snapshots, relevant files
3. **Investigate** -- review audit logs, interview relevant parties, document findings
4. **Determine outcome** -- classify violation, identify root cause, recommend action
5. **Implement action** -- execute disciplinary response
6. **Document** -- record investigation and outcome in personnel file
7. **Review controls** -- assess whether controls need strengthening to prevent recurrence

---

## 8. Contractor and Third-Party Personnel

### 8.1 Equivalent Requirements

Contractors and third-party personnel with access to SENTINEL systems are subject to:

- Same vetting requirements as employees (criminal background check for FSR data access)
- Same training requirements (security awareness within 30 days of access)
- Same ongoing responsibilities (policy compliance, incident reporting)
- Contractual liability for security breaches

### 8.2 Additional Controls

| Control | Requirement |
|---------|-------------|
| **Access limitation** | Access limited to specific systems needed for contracted work only |
| **Time-bound access** | Access automatically expires at contract end date |
| **Supervision** | Contractor work reviewed by SENTINEL team member |
| **Data handling** | No PI or FSR data retained after contract completion |
| **Sub-contracting** | No sub-contracting of SENTINEL work without written approval |
| **Audit rights** | SENTINEL retains right to audit contractor security practices |

---

## 9. Records Management

| Record | Retention Period | Storage |
|--------|-----------------|---------|
| Vetting results | Duration of engagement + 2 years | Secure file (encrypted) |
| NDA / Confidentiality agreements | Duration of engagement + 5 years | Secure file |
| Training completion records | Duration of engagement + 2 years | Access register |
| Access provisioning/deprovisioning records | 3 years after action | Access register |
| Disciplinary records | Duration of engagement + 3 years | Personnel file (encrypted) |
| Policy acknowledgements | Duration of engagement + 2 years | Access register |

---

## 10. Version History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-02-04 | SENTINEL Platform Team | Initial HR security policy |

---

*Document: SENTINEL-HRS-001*
*Classification: Internal*
*Next Review: 2027-02-04*
