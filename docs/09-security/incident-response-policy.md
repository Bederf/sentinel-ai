# SENTINEL Incident Response Policy

**Document ID:** SENTINEL-IRP-001
**Version:** 1.0
**Effective Date:** 2026-02-04
**Review Cadence:** Annual, or after any P1 incident
**Classification:** Internal — FSR Supplier Confidential
**FSR Domains:** 4.13 (Information Security Incident Detection, 3.0 to 4.0 HIGH), 4.14 (Information Security Incident Management, 3.0 to 4.0 MEDIUM)

---

## 1. Purpose

This policy establishes SENTINEL's approach to detecting, responding to, containing, and recovering from information security incidents. It defines severity classifications, response time targets, notification obligations, and organisational responsibilities to ensure timely and effective incident handling across the SENTINEL BMS Intelligence Platform.

This policy directly addresses two FSR Privacy and Service Risk Assessment domains:
- **Domain 4.13 (Information Security Incident Detection):** Ensuring centralised monitoring, automated alerting, and structured detection capabilities.
- **Domain 4.14 (Information Security Incident Management):** Ensuring defined roles, response procedures, notification workflows, and post-incident improvement.

## 2. Scope

This policy applies to:

- All SENTINEL systems, infrastructure, and services (backend API, frontend application, InfluxDB time-series database, Supabase PostgreSQL, ML inference services).
- All infrastructure hosting SENTINEL (Contabo VPS, Docker containers, Cloudflare edge services).
- All data processed by SENTINEL, including building telemetry, occupant personal information, technician identifiers, and BMS operational data.
- All third-party integrations (Anthropic Claude API, MRI Evolution FSI Public API, Ollama local LLM, EskomSePush).
- All personnel with access to SENTINEL systems, including administrators, developers, and FM operators.

## 3. Definitions

| Term | Definition |
|------|-----------|
| **Security Event** | Any observable occurrence relevant to information security, including log entries, alerts, access attempts, and system state changes. Not all security events are incidents. |
| **Security Incident** | A security event that compromises or threatens the confidentiality, integrity, or availability of SENTINEL systems, data, or services. |
| **Data Breach** | A security incident involving unauthorised access to, disclosure of, or loss of personal information as defined by POPIA. Triggers mandatory notification obligations. |
| **Near Miss** | An event that could have resulted in a security incident but was prevented or contained by existing controls before causing impact. |
| **Incident Response Team (IRT)** | The designated group of individuals responsible for coordinating incident detection, analysis, containment, eradication, recovery, and post-incident review. |
| **Personal Information (PI)** | Information relating to an identifiable, living natural person or juristic person, as defined in POPIA Section 1. For SENTINEL, this includes occupant phone numbers, names, technician identifiers, and building-associated operational data. |
| **BMS Safety Incident** | A security incident that affects building management system device control, safety interlocks, or emergency controls. Triggers both security and safety lockdown procedures. |

## 4. Incident Classification and Severity Levels

All security incidents are classified into four severity levels based on impact, scope, and urgency:

### 4.1 Critical (P1)

**Definition:** Active compromise with confirmed or imminent impact on data confidentiality, system integrity, or service availability.

**Examples:**
- Active data breach involving personal information (occupant phone numbers, names, technician identifiers)
- Complete system compromise or unauthorised administrative access to production infrastructure
- BMS safety system breach — unauthorised device control commands bypassing safety interlocks
- Ransomware or destructive malware affecting SENTINEL containers or host
- Compromise of API keys providing access to FSR building data

**Characteristics:**
- Confirmed data exfiltration or exposure
- System integrity cannot be assured
- Immediate risk to building occupant safety or FSR data
- Requires all-hands IRT mobilisation

### 4.2 High (P2)

**Definition:** Successful unauthorised access or partial data exposure with confirmed security control bypass.

**Examples:**
- Successful unauthorised access to SENTINEL administrative functions
- Partial data exposure (e.g., API response leaking building telemetry to unauthenticated users)
- Service degradation affecting FSR data processing (Supabase, InfluxDB)
- Compromised service account credentials (Claude API key, Supabase service role key)
- Wazuh alert confirming file integrity modification on production containers

**Characteristics:**
- Confirmed bypass of at least one security control
- Data exposure scope under investigation
- Service impact to FSR-related functions
- Requires Incident Manager and Technical Lead engagement

### 4.3 Medium (P3)

**Definition:** Detected intrusion attempt blocked by controls, policy violation, or suspicious activity requiring investigation.

**Examples:**
- Intrusion attempt blocked by Cloudflare WAF or Fail2Ban
- Policy violation (e.g., access to production systems outside approved change window)
- Suspicious API access patterns detected by SIEM alerting rules
- Failed privilege escalation attempt detected by Wazuh
- Unauthorised BMS write attempt blocked by safety engine

**Characteristics:**
- Controls prevented actual compromise
- Activity pattern warrants investigation
- No confirmed data exposure or system compromise
- Technical Lead investigates, Incident Manager notified

### 4.4 Low (P4)

**Definition:** Failed attack attempts, minor policy deviations, or false positives confirmed through investigation.

**Examples:**
- Failed SSH brute force attempts (blocked by Fail2Ban)
- Port scanning detected and blocked at Cloudflare edge
- Minor policy deviations (e.g., weak password detected during audit)
- False positive SIEM alerts confirmed through log review
- Automated vulnerability scanner hits with no exploitable findings

**Characteristics:**
- No impact on systems, data, or services
- Attack attempt unsuccessful
- May indicate reconnaissance — logged for trend analysis
- Technical Lead handles, logged in incident register

## 5. Detection Capabilities

SENTINEL deploys layered detection capabilities across infrastructure, application, and network layers. All detection systems were deployed during Phase 63 technical implementation.

### 5.1 Centralised Logging (Phase 63-01)

- **Grafana Loki** centralised log aggregation with Promtail log shipper
- **Sources collected:** Docker container logs (SENTINEL backend, frontend, InfluxDB), system authentication logs (auth.log), syslog, application security audit logs
- **Structured JSON event logging** for machine-parseable security event analysis
- **90-day log retention** with configurable retention policies
- **Configuration:** `infrastructure/loki/loki-config.yaml`

### 5.2 SIEM Alerting Rules (Phase 63-01)

Six automated alerting rules for common attack patterns:

| Rule | Detection Pattern | Threshold |
|------|------------------|-----------|
| Brute Force SSH | Repeated SSH authentication failures | 5 failures in 5 minutes |
| Failed API Auth | Repeated API authentication failures | 10 failures in 5 minutes |
| Privilege Escalation | sudo/su usage by non-authorised users | Any occurrence |
| BMS Write Anomaly | Unusual device control write patterns | Outside normal hours or frequency |
| After-Hours Access | System access outside business hours | Configurable time window |
| Data Exfiltration | Large data transfers from SENTINEL API | Volume threshold exceeded |

**Configuration:** `infrastructure/grafana/provisioning/alerting/security-alerts.yaml`

### 5.3 Host-Based IDS (Phase 63-02)

- **Wazuh agent** with file integrity monitoring (FIM), log analysis, rootkit detection, and active response
- **File Integrity Monitoring:** Detects unauthorised modifications to critical configuration files, application binaries, and Docker container filesystems
- **Rootkit Detection:** Scans for hidden processes, files, and kernel modules
- **Active Response:** Automated blocking of detected threats
- **Configuration:** `infrastructure/wazuh/ossec.conf`, `infrastructure/wazuh/local_rules.xml`

### 5.4 Network Protection (Phase 63-02)

- **Cloudflare WAF** with 9 custom rules for web application attack protection (SQL injection, XSS, path traversal, API abuse)
- **Cloudflare DDoS protection** and bot management at edge
- **Fail2Ban** brute force protection with escalating ban durations for SSH and API endpoints
- **Configuration:** `infrastructure/fail2ban/jail.local`

### 5.5 Application-Level Security Audit Logging (Phase 63-01)

- **Security audit middleware** (`backend/app/middleware/security_logging.py`) captures all authentication events, authorisation decisions, device control actions, and data access patterns
- **Structured JSON format** with correlation IDs for cross-request tracing
- **BMS-specific logging:** All device write commands, safety interlock validations, and override actions are logged with operator identity, timestamp, and action details

## 6. Incident Response Team (IRT)

### 6.1 Roles and Responsibilities

| Role | Primary Responsibility | Backup |
|------|----------------------|--------|
| **Incident Manager** | Overall incident coordination, severity classification, escalation decisions, FSR and regulatory notifications | Information Security Officer (same person in current team structure) |
| **Technical Lead** | Technical investigation, containment actions, evidence preservation, eradication, and recovery | System Administrator (same person in current team structure) |
| **Communications Lead** | FSR notification drafting, POPIA Information Regulator notifications, data subject notifications, internal communications | Incident Manager (escalation path) |

**Note:** In SENTINEL's current team structure, the Incident Manager and Technical Lead roles may be filled by the same person. However, the responsibilities for each role remain distinct and must be executed in the documented sequence. As the team scales, these roles should be separated.

### 6.2 Contact Information

The IRT contact list is maintained as a controlled document separate from this policy. It includes:
- Primary and secondary contact details for each IRT role
- FSR Security Operations contact details (for incident notifications)
- POPIA Information Regulator contact details
- Third-party vendor emergency contacts (Contabo, Cloudflare, Anthropic)

The contact list is reviewed quarterly and updated immediately when personnel changes occur.

## 7. Response Time Targets

Response time targets are measured from the point of initial detection or report:

| Severity | Acknowledge | Contain | Initial Assessment | Full Resolution |
|----------|-------------|---------|-------------------|-----------------|
| **Critical (P1)** | 15 minutes | 1 hour | 4 hours | Best effort (72 hours target) |
| **High (P2)** | 30 minutes | 4 hours | 8 hours | 5 business days |
| **Medium (P3)** | 2 hours | 24 hours | 48 hours | 10 business days |
| **Low (P4)** | 8 hours | N/A | 5 business days | 20 business days |

**Definitions:**
- **Acknowledge:** IRT member confirms receipt and begins initial triage
- **Contain:** Active threat is isolated, bleeding stopped, no further damage occurring
- **Initial Assessment:** Scope, impact, root cause hypothesis, and containment effectiveness documented
- **Full Resolution:** Root cause addressed, systems restored, incident closed

## 8. FSR Notification Requirements

### 8.1 Mandatory Notifications

SENTINEL is contractually obligated to notify FSR of security incidents affecting their data:

| Severity | Notification Timeframe | Content Required |
|----------|----------------------|-----------------|
| **Critical (P1)** | Within 24 hours of confirmation | Incident reference number, severity, initial assessment, containment actions taken, estimated scope of impact, next steps |
| **High (P2)** | Within 24 hours of confirmation | Incident reference number, severity, initial assessment, containment actions taken, next steps |
| **Medium (P3)** | Monthly summary report | Aggregated in quarterly incident report |
| **Low (P4)** | Quarterly summary report | Aggregated in quarterly incident report |

### 8.2 Follow-Up Reporting

- **Detailed incident report** within 72 hours of initial notification (P1/P2)
- **Root cause analysis** within 10 business days (P1/P2)
- **Lessons learned and remediation plan** within 15 business days (P1/P2)
- **Remediation completion confirmation** when all corrective actions are implemented

### 8.3 Notification Format

All FSR notifications use the standardised templates defined in the Incident Response Process document (`docs/08-security/incident-response-process.md`), ensuring consistent, actionable communication.

## 9. POPIA Breach Notification

### 9.1 Obligations Under POPIA

When a security incident constitutes a data breach involving personal information as defined by POPIA:

1. **Information Regulator notification:** Within 72 hours of becoming aware of a personal data breach, SENTINEL must notify the Information Regulator using the prescribed form.
2. **Data subject notification:** As soon as reasonably possible after becoming aware of a breach, SENTINEL must notify affected data subjects in writing (or by publication if individual notification is not feasible).
3. **FSR notification:** In addition to the standard FSR notification above, POPIA breach notifications must include the nature of the personal information compromised.

### 9.2 Breach Notification Register

A breach notification register is maintained as a controlled document, recording:
- Date breach discovered
- Date Information Regulator notified
- Date data subjects notified
- Nature of personal information affected
- Number of data subjects affected
- Remedial measures implemented
- Reference to incident register entry

### 9.3 Personal Information Categories in SENTINEL

The following PI categories may be affected in a breach:
- Occupant phone numbers (WhatsApp/Telegram)
- Occupant names and desk/location identifiers
- Technician identifiers and contact details (from MRI Evolution)
- Building occupancy patterns (indirect PI — may reveal work schedules)

## 10. Incident Register

### 10.1 Register Requirements

An incident register is maintained as a living document and serves as the authoritative record of all security incidents:

| Field | Description |
|-------|-------------|
| Incident Reference | Format: INC-YYYY-NNN (e.g., INC-2026-001) |
| Date/Time Detected | ISO 8601 format with timezone |
| Date/Time Reported | ISO 8601 format with timezone |
| Detection Source | Which detection system or person identified the event |
| Severity (P1-P4) | Classification at time of detection |
| Description | Factual summary of the incident |
| Affected Systems | SENTINEL components impacted |
| Affected Data | Data categories involved (if any) |
| Containment Actions | Actions taken to stop the incident |
| Root Cause | Identified root cause (may be updated) |
| Remediation Actions | Corrective actions implemented |
| Status | Open, Contained, Resolved, Closed |
| Lessons Learned | Post-incident review findings |
| FSR Notified | Yes/No, with date if applicable |
| POPIA Notified | Yes/No, with date if applicable |

### 10.2 Retention and Review

- **Review cadence:** Monthly review by Incident Manager to identify trends and patterns
- **Retention period:** 5 years from incident closure date
- **Access control:** Restricted to IRT members and authorised management
- **Integrity:** Register is version-controlled and changes are tracked

## 11. Metrics and Reporting

### 11.1 Key Performance Indicators

| Metric | Definition | Target |
|--------|-----------|--------|
| **Mean Time to Detect (MTTD)** | Average time from incident occurrence to detection | < 1 hour (automated), < 4 hours (reported) |
| **Mean Time to Respond (MTTR)** | Average time from detection to acknowledgement | Per severity targets (Section 7) |
| **Mean Time to Resolve** | Average time from detection to full resolution | Per severity targets (Section 7) |
| **False Positive Rate** | Percentage of alerts that are false positives | < 20% |
| **Incident Recurrence Rate** | Percentage of incidents with same root cause recurring | 0% target |
| **Notification Compliance** | Percentage of P1/P2 incidents notified within SLA | 100% |

### 11.2 Reporting Schedule

| Report | Audience | Frequency | Content |
|--------|----------|-----------|---------|
| Incident Summary | Information Security Officer | Monthly | All incidents, trends, metrics |
| Quarterly Incident Report | FSR | Quarterly | Aggregated incidents, trends, improvement actions |
| Annual Security Review | Management, FSR | Annual | Year-in-review, metrics trending, policy effectiveness |

## 12. BMS Safety Incident Integration

### 12.1 Dual-Track Response

When a security incident affects BMS device control systems, SENTINEL triggers a dual-track response:

1. **Security Track:** Standard incident response process (this policy) — investigation, containment, eradication, recovery.
2. **Safety Track:** BMS safety lockdown procedures — all device control commands halted, safety interlocks enforced, emergency controls activated.

### 12.2 BMS-Specific Incident Triggers

| Trigger | Security Action | Safety Action |
|---------|----------------|--------------|
| Unauthorised device control command | P1/P2 incident — investigate access | Safety engine blocks command, audit log records attempt |
| Safety interlock bypass attempt | P2 incident — investigate source | All device control suspended pending review |
| Anomalous BMS write pattern (SIEM rule) | P3 incident — investigate pattern | Enhanced monitoring on affected device group |
| Compromised operator credentials | P1 incident — credential rotation | All sessions terminated, device control suspended |

### 12.3 Emergency Controls Reference

BMS safety incidents reference the Emergency Controls service (Phase 63-04) for coordinated safety lockdown procedures. The safety engine (`backend/app/services/safety_interlocks.py`) enforces rule-based validation on all device control actions with severity levels: WARNING (allow with log), BLOCK (prevent execution), ALARM (critical — trigger incident).

## 13. Lessons Learned

### 13.1 Post-Incident Review

A mandatory post-incident review is conducted for all P1 and P2 incidents:

- **Timeline:** Within 5 business days of incident closure
- **Participants:** All IRT members involved in the incident
- **Format:** Structured review covering timeline, actions taken, what worked, what failed, and improvement recommendations
- **Output:** Documented lessons learned appended to incident register entry

### 13.2 Continuous Improvement

Lessons learned feed into:
- Updated detection rules (Grafana Loki SIEM rules, Wazuh custom rules)
- Updated WAF/Fail2Ban configurations
- Updated safety interlock rules
- Updated incident response procedures
- Updated security training content
- Updated risk register entries

## 14. Policy Governance

### 14.1 Review Schedule

| Trigger | Action |
|---------|--------|
| Annual review | Full policy review and update |
| After any P1 incident | Review and update within 15 business days |
| Significant infrastructure change | Review affected sections |
| Regulatory change (POPIA, FSCA) | Review affected sections |
| FSR requirement change | Review affected sections |

### 14.2 Version History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-02-04 | SENTINEL Security | Initial policy creation |

### 14.3 Approval

This policy is approved by the SENTINEL Information Security Officer and is effective from the date listed above. All personnel with access to SENTINEL systems are required to acknowledge and comply with this policy.

---

**Related Documents:**
- [Incident Response Process](./incident-response-process.md) — Step-by-step operational procedures
- [Logging Architecture](./logging-architecture.md) — Centralised logging and SIEM alerting
- [Intrusion Detection](./intrusion-detection.md) — IDS/WAF/Fail2Ban architecture
- [BCP/DR Procedures](./bcp-dr-procedures.md) — Business continuity and disaster recovery
- [Access Control Implementation](./access-control-implementation.md) — Logical access controls

*SENTINEL BMS Intelligence Platform — Incident Response Policy v1.0*
*Effective: 2026-02-04*
