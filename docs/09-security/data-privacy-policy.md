# SENTINEL Data Privacy Policy

**Document Owner:** Information Security Officer / Deputy Information Officer
**Version:** 1.0
**Effective Date:** 2026-02-04
**Review Cadence:** Annual, or on new PI processing activity
**POPIA Reference:** Protection of Personal Information Act, 2013
**FSR Reference:** Privacy Controls Sections 1-8
**Classification:** Confidential
**Status:** Active

---

## 1. Purpose

This policy documents SENTINEL BMS Intelligence Platform's approach to processing personal information (PI) in compliance with the Protection of Personal Information Act (POPIA). It establishes the principles, controls, and processes governing how PI is collected, processed, stored, shared, and deleted across all SENTINEL operations.

This policy serves as SENTINEL's standalone privacy policy, addressing the FSR gap analysis finding that no standalone privacy policy existed. It complements the operational privacy controls documented in `docs/08-security/consent-and-privacy.md`.

---

## 2. Scope

This policy applies to all personal information processed by SENTINEL, including:

- **Occupant data:** Building occupants who interact with SENTINEL via WhatsApp, Telegram, or web portal
- **Technician data:** Maintenance technicians and contractors managed through MRI Evolution/FSI CAFM
- **Building manager/operator data:** System administrators and facility managers who use the SENTINEL dashboard
- **Sensor-derived data:** Occupancy patterns, location data, and building usage patterns that may indirectly identify individuals

This policy covers all processing activities regardless of whether data is stored in Supabase (PostgreSQL), JSON files, InfluxDB, or transmitted to third-party services.

---

## 3. Privacy Principles

SENTINEL adheres to the eight POPIA conditions for lawful processing:

| # | Condition | SENTINEL Implementation |
|---|-----------|------------------------|
| 1 | **Accountability** | Information Security Officer designated as privacy lead; this policy establishes accountability framework |
| 2 | **Processing limitation** | PI only processed with consent or legitimate interest; purpose limited to building management |
| 3 | **Purpose specification** | Specific purposes documented per data type (Section 5); no secondary processing without consent |
| 4 | **Further processing limitation** | PI not used beyond documented purposes; no sale or sharing of PI for marketing |
| 5 | **Information quality** | Data subjects can request correction (Section 8); data validated on collection |
| 6 | **Openness** | This policy and external privacy notice published; data subjects informed of processing |
| 7 | **Security safeguards** | Encryption, access control, monitoring (see security documentation suite) |
| 8 | **Data subject participation** | Rights exercisable by data subjects (Section 8); consent mechanism implemented |

---

## 4. Legal Basis for Processing

SENTINEL processes PI under the following legal bases:

### 4.1 Consent (POPIA Section 11(1)(a))

| Data Type | Consent Mechanism | Withdrawal Method |
|-----------|-------------------|-------------------|
| Occupant phone numbers and names | First-contact consent flow via WhatsApp/Telegram (see `consent_service.py`) | Send "STOP" keyword |
| Occupant comfort complaints and facilities requests | Implicit in PI processing consent | Send "STOP" keyword |
| Cross-border data transfer to Claude API | Explicit cross_border_transfer consent type | Send "STOP CROSS-BORDER" or contact privacy officer |
| Communication message content | Implicit in PI processing consent | Send "STOP" keyword |

### 4.2 Legitimate Interest (POPIA Section 11(1)(f))

| Data Type | Legitimate Interest | Balancing Assessment |
|-----------|--------------------|---------------------|
| BMS telemetry (sensor readings) | Building management, energy optimisation, safety monitoring | Non-personal aggregate data; minimal privacy impact; essential for building safety |
| Occupancy sensor data (presence/absence) | HVAC and lighting optimisation for comfort and energy savings | Aggregate zone-level data; not individual tracking; benefit to all occupants |
| Desk/zone assignment data | Route facilities requests to correct zone; enable comfort diagnosis | Required for service delivery; alternative is less effective manual routing |

### 4.3 Contractual Necessity (POPIA Section 11(1)(b))

| Data Type | Contract | Purpose |
|-----------|----------|---------|
| Technician names and assignments | FM service contract with FSR client | Work order dispatch, skill matching, service delivery |
| Technician phone numbers | FM service contract | Communication for dispatch and status updates |
| Technician service records | FM service contract | Performance tracking, quality assurance |

### 4.4 Legal Obligation (POPIA Section 11(1)(c))

| Data Type | Legal Obligation | Retention |
|-----------|-----------------|-----------|
| Audit logs (user actions, system events) | Regulatory compliance; FSR contractual requirements | 5 years |
| Consent records | POPIA evidence of lawful processing | Indefinite (legal evidence) |
| Security incident logs | POPIA Section 22 breach notification obligation | 5 years |

---

## 5. Data Subject Categories

### 5.1 Building Occupants

| Attribute | Detail |
|-----------|--------|
| **Who** | Office workers, visitors, tenants interacting with SENTINEL services |
| **Interaction channels** | WhatsApp, Telegram, web portal |
| **PI collected** | Phone numbers, names, desk/zone locations, facilities requests, comfort complaints |
| **Purpose** | Handle comfort complaints, process facilities requests, optimise building environment |
| **Consent** | Required before any processing; captured via first-contact consent flow |
| **Retention** | 12 months after last interaction, or duration of consent (whichever is shorter for raw PI) |

### 5.2 Technicians and Contractors

| Attribute | Detail |
|-----------|--------|
| **Who** | Maintenance technicians, service contractors, specialist engineers |
| **Interaction channels** | MRI Evolution CAFM, Sentry Telegram bot, mobile inspection app |
| **PI collected** | Names, phone numbers, skill categories, work assignments, service records, location (during dispatch) |
| **Purpose** | Work order dispatch, skill matching, field data collection, service quality tracking |
| **Legal basis** | Contractual necessity (FM service agreement) |
| **Retention** | Duration of contract + 5 years (contractual and regulatory requirement) |

### 5.3 Building Managers and Operators

| Attribute | Detail |
|-----------|--------|
| **Who** | Facility managers, system administrators, helpdesk operators |
| **Interaction channels** | SENTINEL dashboard, API, SSH access |
| **PI collected** | Usernames, email addresses, IP addresses, access logs, system actions |
| **Purpose** | System administration, access control, audit trail, security monitoring |
| **Legal basis** | Contractual necessity and legitimate interest |
| **Retention** | Duration of employment/engagement + 5 years (audit requirements) |

---

## 6. Personal Information Categories Processed

| Category | Data Elements | Classification | Legal Basis | Retention |
|----------|--------------|----------------|-------------|-----------|
| **Contact details** | Phone numbers (WhatsApp/Telegram), email addresses, names | Confidential | Consent | 12 months after last interaction |
| **Location data** | Desk/zone assignments, building floor, building access patterns | Internal | Legitimate interest | 90 days raw; 2 years aggregated |
| **Employment identifiers** | Technician IDs from MRI Evolution, skill categories | Confidential | Contractual necessity | Duration of contract + 5 years |
| **Communication content** | Chat messages, facility requests, comfort complaints | Confidential | Consent | 90 days |
| **Occupancy data** | Presence/absence from PIR sensors, zone-level occupancy counts | Internal | Legitimate interest | 90 days raw; 2 years aggregated |
| **System usage** | Login timestamps, actions performed, API calls | Internal | Legal obligation | 5 years (audit requirement) |
| **Consent records** | Consent decisions, timestamps, platform, hashed identifiers | Confidential | Legal obligation | Indefinite |

---

## 7. Consent Management

### 7.1 Consent Capture Service

SENTINEL implements a consent capture service (`backend/app/services/consent_service.py`) deployed in Phase 63-06 that:

- Detects first-time users on WhatsApp/Telegram
- Presents privacy notice and consent request before any processing
- Captures three consent types: PI processing, data retention, cross-border transfer
- Stores consent records as immutable, append-only entries
- Hashes identifiers with SHA-256 for PI protection in consent records
- Dual-writes to Supabase and JSON file for resilience

### 7.2 Consent Types

| Type | Description | Required for Service | Withdrawal Impact |
|------|-------------|---------------------|-------------------|
| **PI processing** | Consent to process phone number, name, location, and requests for building management | Yes | Service discontinued; data deleted per retention schedule |
| **Data retention** | Agreement to 90-day raw / 2-year aggregate retention periods | Yes | Data deleted per POPIA; consent record retained |
| **Cross-border transfer** | Acknowledgment that AI processing may use international services (Claude API) | No | AI chat degrades to Ollama (local); full service continues |

### 7.3 Consent Record Integrity

- **Immutable records:** Consent decisions are append-only; withdrawals create new records
- **Hashed identifiers:** Phone numbers and user IDs hashed with SHA-256 before storage
- **Dual-write:** Supabase + JSON file (consistent with SENTINEL's dual-write architecture)
- **Audit trail:** Each record includes record_id, timestamp, platform, consent_text, metadata
- **Tamper evidence:** Sequential record IDs; gaps indicate potential tampering

### 7.4 Consent Withdrawal

Data subjects can withdraw consent at any time:

- **WhatsApp/Telegram:** Send "STOP" keyword
- **Web portal:** Navigate to privacy settings
- **Email:** Contact privacy@[company-domain]
- **Response time:** Withdrawal processed immediately; confirmation sent within 24 hours
- **Effect:** Data processing ceases; data deletion scheduled per retention policy

---

## 8. Data Subject Rights (POPIA Sections 23-25)

### 8.1 Rights Summary

| Right | POPIA Section | Description | Process | Response Time |
|-------|--------------|-------------|---------|---------------|
| **Right of access** | Section 23 | Request a copy of all PI held about the data subject | Submit request via email, messaging, or web portal | 30 days |
| **Right to rectification** | Section 24(1)(a) | Request correction of inaccurate or incomplete PI | Submit correction request with evidence | 30 days |
| **Right to deletion/destruction** | Section 24(1)(b) | Request deletion of PI (subject to retention obligations) | Submit deletion request; verified against retention schedule | 30 days |
| **Right to object to processing** | Section 11(3)(a) | Object to processing based on legitimate interest | Submit objection with grounds; assessed against balancing test | 30 days |
| **Right to data portability** | Section 23 (implied) | Request PI in machine-readable format (JSON/CSV) | Submit portability request | 30 days |
| **Right to withdraw consent** | Section 11(2)(a) | Withdraw previously given consent | Send "STOP" keyword or contact privacy officer | Immediate |
| **Right to lodge complaint** | Section 74 | Complain to the Information Regulator | Contact Information Regulator at inforeg.org.za | N/A (external) |

### 8.2 How to Exercise Rights

| Channel | Method | Contact |
|---------|--------|---------|
| **WhatsApp/Telegram** | Send "RIGHTS" or "PRIVACY" keyword | SENTINEL bot |
| **Email** | Send request to designated privacy address | privacy@[company-domain] |
| **Web portal** | Navigate to Account > Privacy Settings | Self-service |
| **Post** | Written request to registered address | [Company registered address] |

### 8.3 Request Handling Process

1. **Receipt:** Request received and acknowledged within 5 business days
2. **Verification:** Identity of requestor verified (phone number, email, employee ID)
3. **Assessment:** Request assessed against retention obligations and legal requirements
4. **Execution:** Request fulfilled (access, correction, deletion, portability export)
5. **Notification:** Data subject notified of outcome within 30 days
6. **Record:** Request and outcome logged in privacy request register

### 8.4 Refusal Grounds

Requests may be refused where:

- Retention is required by law or regulation (audit logs, consent records)
- Deletion would prejudice ongoing legal proceedings
- PI is required for contract performance and contract is still active
- Request is manifestly unfounded or excessive (POPIA Section 23(2))

Refusals are documented with reasons and communicated to the data subject within 30 days.

---

## 9. Data Retention Schedule

### 9.1 Retention Periods

| Data Category | Raw Retention | Aggregated Retention | Legal Basis for Retention | Deletion Method |
|--------------|--------------|---------------------|--------------------------|-----------------|
| **Raw BMS telemetry** (sensor readings) | 90 days | 2 years (anonymised) | Legitimate interest (building management) | Automated purge job |
| **Aggregated analytics** | N/A | 2 years | Legitimate interest (trend analysis) | Automated expiry |
| **Work orders** | Duration of contract + 5 years | N/A | Contractual and regulatory | Manual review at termination |
| **Occupant PI** (phone, name, messages) | 12 months after last interaction | Not retained | Consent | Automated purge after inactivity period |
| **Communication content** (chat messages) | 90 days | Not retained | Consent | Automated purge |
| **Audit logs** | 5 years | N/A | Legal obligation (regulatory compliance) | Automated expiry |
| **Consent records** | Indefinite | N/A | Legal evidence (POPIA compliance) | Never auto-deleted; manual review only |
| **Security incident logs** | 5 years | N/A | Legal obligation (breach notification) | Automated expiry |
| **ML training data** | Duration of model lifecycle | N/A | Legitimate interest (model improvement) | Manual deletion on model retirement |

### 9.2 Retention Lifecycle

```
Collection → Processing → Active Use → Archival → Deletion
    ↓            ↓            ↓            ↓          ↓
  Day 0      Day 0-90     Day 0-90     Day 91+     Per schedule
  Consent    Full detail   Full access  Read-only   Permanent
  captured   PI retained   PI available Aggregated  removal
```

### 9.3 Automated Deletion

SENTINEL implements automated data lifecycle management:

- **90-day purge:** Background job removes raw telemetry and PI older than 90 days
- **Pre-purge aggregation:** Data anonymised and aggregated before raw deletion
- **Audit trail:** Deletion events logged for compliance evidence
- **Monthly verification:** Check that purge jobs completed successfully
- **Exception handling:** Consent records and audit logs explicitly excluded from automated purge

---

## 10. Cross-Border Transfers

### 10.1 International Data Transfers

SENTINEL transfers PI outside South Africa in the following circumstances:

| Transfer | Provider | Destination | Data | Legal Basis | Safeguards |
|----------|----------|------------|------|-------------|------------|
| AI chat processing | Anthropic (Claude API) | United States | Chat messages (may contain names, desk locations, complaints) | POPIA s72: DPA + consent | Data processed ephemerally (not retained); Ollama local fallback available; consent-based |
| Occupant messaging | Meta (WhatsApp) | Global | Phone numbers, message content | POPIA s72: consent + service delivery necessity | End-to-end encryption; minimal data; consent-based |
| Technician messaging | Telegram | Global | Phone numbers, message content | POPIA s72: consent + service delivery necessity | Client-server encryption; minimal data; consent-based |
| Source code hosting | GitHub | United States | No PI (code only) | POPIA s72: adequate safeguards | Private repositories; no PI in code; SOC 2 certified |

### 10.2 Mitigation Measures

- **Anonymise/pseudonymise:** Where possible, remove or hash PI before cross-border transfer
- **Minimal data transfer:** Only send data necessary for the specific processing purpose
- **Ollama fallback:** Data subjects who decline cross-border consent receive full service via local AI (no external transfer)
- **Ephemeral processing:** Claude API processes messages without retention; not used for model training
- **Consent-based:** Cross-border transfer consent captured separately; withdrawal does not affect core service

### 10.3 Transfer Impact Assessment

Before establishing any new cross-border data transfer:

1. Identify what PI will be transferred
2. Assess recipient country's data protection adequacy
3. Evaluate provider's security certifications and DPA terms
4. Document legal basis under POPIA Section 72
5. Implement technical safeguards (encryption, pseudonymisation)
6. Obtain data subject consent where required
7. Update cross-border data flow register (`docs/08-security/third-party-security-register.md`)
8. Information Security Officer approval required

---

## 11. Data Return and Deletion at Contract Termination

### 11.1 Data Return Process

When an FSR client terminates their SENTINEL contract:

| Step | Action | Timeline | Responsibility |
|------|--------|----------|---------------|
| 1 | **Termination notice** received | Day 0 | FSR client |
| 2 | **Data export** -- all client data exported in machine-readable format (JSON/CSV) | Within 14 days | SENTINEL operations |
| 3 | **Data package delivery** -- encrypted data package delivered to client via secure channel | Within 14 days | SENTINEL operations |
| 4 | **Client confirmation** -- client confirms receipt and completeness of data | Within 21 days | FSR client |
| 5 | **Data deletion** -- all PI permanently deleted from all systems | Within 30 days | SENTINEL operations |
| 6 | **Destruction certificate** -- written confirmation of data destruction issued | Within 30 days | Information Security Officer |

### 11.2 Deletion Scope

| System | Data Deleted | Method | Verification |
|--------|-------------|--------|-------------|
| **Supabase (PostgreSQL)** | All client records (cascading delete) | SQL DELETE with CASCADE | Row count verification |
| **JSON data files** | Client-specific data files | Secure overwrite (3-pass) | File existence check |
| **InfluxDB** | Client measurement data | DROP MEASUREMENT | Query verification |
| **Loki logs** | Expire after retention period | Automatic expiry | Retention policy check |
| **Backup snapshots** | Expire after retention period (7 days) | Automatic rotation | Snapshot inventory |

### 11.3 Retained After Termination

The following data is retained after contract termination for legal compliance:

| Data | Retention After Termination | Legal Basis |
|------|----------------------------|-------------|
| **Consent records** | 5 years | POPIA compliance evidence |
| **Audit log summaries** | 5 years | Regulatory requirement |
| **Anonymised aggregated data** | Indefinite (permitted) | No PI; statistical value only |
| **Destruction certificate** | Indefinite | Compliance evidence |

---

## 12. Privacy Incident Management

### 12.1 Privacy Breach Definition

A privacy breach is any event where PI is:
- Accessed by unauthorised persons
- Lost, destroyed, or damaged without authorisation
- Disclosed to unintended recipients
- Processed in a manner inconsistent with this policy or consent

### 12.2 Breach Notification (POPIA Section 22)

| Notification | Recipient | Timeline | Content |
|-------------|-----------|----------|---------|
| **Information Regulator** | South African Information Regulator | As soon as reasonably possible after discovery | Nature of breach, PI affected, measures taken |
| **Data subjects** | Affected individuals | As soon as reasonably possible after discovery | Nature of breach, possible consequences, measures taken, recommendations |
| **FSR client** | Responsible party (FM company) | Within 72 hours of discovery | Full incident details per contractual requirements |

### 12.3 Breach Response Process

1. **Detection:** Breach identified via monitoring, report, or third-party notification
2. **Containment:** Immediate steps to contain the breach (revoke access, isolate systems)
3. **Assessment:** Determine scope, PI affected, number of data subjects
4. **Notification:** Notify Information Regulator, data subjects, and FSR client per timelines above
5. **Remediation:** Fix root cause; implement controls to prevent recurrence
6. **Post-incident review:** Document lessons learned; update policies and procedures
7. **Record:** Maintain breach register for compliance audit

Reference: Incident response procedures in `docs/08-security/vulnerability-management.md`

---

## 13. Privacy Impact Assessments (PIAs)

### 13.1 When PIAs Are Required

A privacy impact assessment must be conducted before:

- Introducing a new integration that processes PI (new messaging platform, new CAFM provider)
- Changing the purpose of existing PI processing
- Implementing new technology that processes PI (new AI model, new sensor type)
- Introducing new cross-border data transfers
- Significantly changing the volume or categories of PI processed
- Onboarding a new sub-processor that handles PI

### 13.2 PIA Process

1. **Scope definition:** Identify the PI processing activity and its boundaries
2. **Data mapping:** Document what PI flows where, including third parties and cross-border transfers
3. **Risk assessment:** Identify privacy risks (unauthorized access, data breach, purpose creep)
4. **Control assessment:** Evaluate existing and proposed controls against identified risks
5. **Residual risk:** Document residual risks after controls
6. **Recommendations:** Propose additional controls or process changes
7. **Approval:** Information Security Officer reviews and approves
8. **Implementation:** Implement approved controls before go-live
9. **Record:** PIA documented and retained for audit purposes

### 13.3 Completed PIAs

| Processing Activity | PIA Date | Status | Key Finding |
|---------------------|----------|--------|-------------|
| WhatsApp/Telegram messaging integration | 2026-02-04 | Complete | Cross-border transfer consent required; Ollama fallback mitigates risk |
| Claude API AI processing | 2026-02-04 | Complete | Ephemeral processing; no retention; consent-based; fallback available |
| MRI Evolution/FSI work orders | 2026-02-04 | Pending | South African hosted; no cross-border concern; contractual basis |

---

## 14. External Privacy Notice

### 14.1 Purpose

An external privacy notice must be displayed to data subjects via WhatsApp, Telegram, and web portal, providing the information required by POPIA Sections 18 and 23.

### 14.2 Required Content

The external privacy notice must include:

1. **Identity of responsible party** (FM company) and operator (SENTINEL)
2. **Contact details** of the information officer
3. **Purpose of processing** (building management, comfort requests, maintenance)
4. **Categories of PI** collected (phone number, name, location, messages)
5. **Legal basis** for processing (consent, legitimate interest, contractual)
6. **Recipients** of PI (third-party providers listed in third-party register)
7. **Cross-border transfers** (Claude API, WhatsApp, Telegram)
8. **Retention periods** (90 days raw, 2 years aggregated)
9. **Data subject rights** (access, correction, deletion, objection, portability)
10. **How to exercise rights** (contact details, "RIGHTS" keyword)
11. **Right to lodge complaint** with Information Regulator
12. **Consent withdrawal** process ("STOP" keyword)

### 14.3 Privacy Notice Delivery

| Channel | Delivery Method | Timing |
|---------|----------------|--------|
| WhatsApp | First-contact consent message with privacy URL | Before first data processing |
| Telegram | First-contact consent message with privacy URL | Before first data processing |
| Web portal | Privacy notice page accessible from footer | Always available |
| Dashboard | Privacy settings page in user profile | Always available |

### 14.4 Reference Implementation

See `docs/08-security/consent-and-privacy.md` Section 5 for the detailed external privacy notice content including data tables, retention schedules, and POPIA rights summary.

---

## 15. Privacy Training

### 15.1 Training Requirements

| Audience | Training Content | Frequency |
|----------|-----------------|-----------|
| **All staff** | POPIA basics, PI identification, consent requirements, breach reporting | Annual + onboarding |
| **Development team** | Privacy-by-design, data minimisation, pseudonymisation techniques, secure coding for PI | Annual |
| **Operations team** | Data subject rights handling, retention enforcement, breach detection and reporting | Annual |
| **Management** | Privacy governance, regulatory obligations, PIA review, breach notification | Annual |

### 15.2 Training Records

- Training completion recorded with date, attendee, and course content
- Training effectiveness assessed annually
- Non-completion escalated to Information Security Officer

Reference: `infrastructure/training/security-awareness-plan.md` for comprehensive training programme including privacy modules.

---

## 16. Document Control

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-02-04 | SENTINEL Platform Team | Initial policy creation |

**Review schedule:** Annual review required, or triggered by:
- New PI processing activity
- New integration or sub-processor
- Privacy breach or incident
- POPIA regulatory update
- FSR contractual requirement change
- Information Regulator guidance

---

## 17. References

| Document | Location |
|----------|----------|
| Consent and Privacy Controls | `docs/08-security/consent-and-privacy.md` |
| Consent Service (implementation) | `backend/app/services/consent_service.py` |
| Third-Party Security Register | `docs/08-security/third-party-security-register.md` |
| Business Continuity Policy | `docs/08-security/business-continuity-policy.md` |
| Vulnerability Management | `docs/08-security/vulnerability-management.md` |
| Access Control Implementation | `docs/08-security/access-control-implementation.md` |
| Security Awareness Training | `infrastructure/training/security-awareness-plan.md` |
| POPIA | Protection of Personal Information Act, 2013 |
| Information Regulator | inforeg.org.za |

---

*This policy is owned by the Information Security Officer and subject to annual review. All SENTINEL personnel must comply with this policy. Non-compliance must be reported and may result in disciplinary action.*
