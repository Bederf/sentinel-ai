# SENTINEL Consent and Privacy Controls

**Document Owner:** SENTINEL Platform Team
**Version:** 1.0
**Created:** 2026-02-04
**FSR Reference:** Privacy Controls Sections 1, 3, 4, and 7
**POPIA Reference:** Protection of Personal Information Act, 2013
**Status:** Active

---

## 1. Personal Information Processing Overview

SENTINEL BMS Intelligence Platform processes personal information (PI) as part of its building management operations. This document describes the PI processed, consent mechanisms, privacy notices, cross-border data flows, and data retention policies.

**SENTINEL's role:** SENTINEL acts as an operator (processor) on behalf of the facilities management company (responsible party) that manages the building. The FM company determines the purpose and means of processing; SENTINEL provides the technology platform.

---

## 2. Data Subjects

SENTINEL processes PI for the following categories of data subjects:

| Data Subject | Interaction Channel | PI Collected | Purpose |
|-------------|--------------------|--------------|---------|
| **Building occupants** | WhatsApp, Telegram, web portal | Phone numbers, names, desk locations, facilities requests, occupancy data | Handle comfort complaints, facilities requests, building access |
| **Technicians** | MRI Evolution CAFM, Sentry Telegram bot, mobile app | Names, phone numbers, skills, work assignments, location (during dispatch) | Work order dispatch, skill matching, field data collection |
| **System administrators** | SSH, web dashboard, API | Usernames, email addresses, IP addresses, access logs | System administration, audit trail |

---

## 3. PI Categories Processed

| Category | Data Elements | Classification | Retention |
|----------|--------------|----------------|-----------|
| **Contact information** | Phone numbers, email addresses | Confidential | 90 days raw, 2 years aggregate |
| **Identity information** | Names, desk/office numbers | Confidential | 90 days raw, 2 years aggregate |
| **Location data** | Building floor, zone, desk number | Internal | 90 days raw, 2 years aggregate |
| **Facilities requests** | Complaint text, request descriptions | Internal | 90 days raw, 2 years aggregate |
| **Occupancy data** | Presence/absence via sensors | Internal | 90 days raw, 2 years aggregate |
| **Communication content** | WhatsApp/Telegram messages | Confidential | 90 days |
| **Access logs** | Login times, IP addresses, actions | Internal | 90 days (audit log) |
| **Consent records** | Consent decisions, timestamps | Confidential | Duration of relationship + 5 years |

---

## 4. Consent Capture Mechanism

### 4.1 First-Contact Consent Flow

When a building occupant first interacts with SENTINEL via WhatsApp or Telegram, the system presents a consent message before processing any data.

**WhatsApp/Telegram first-contact message:**

> SENTINEL Building Management processes your phone number and messages to handle facilities requests. Your data is stored securely in South Africa with 90-day retention. You can withdraw consent anytime by messaging 'STOP'. Privacy notice: https://sentinel.bms/privacy

**Consent flow:**

```
1. Occupant sends first message to SENTINEL bot
2. SENTINEL detects new user (no existing consent record)
3. SENTINEL sends consent message with privacy notice link
4. Occupant responds:
   a) "YES" / "AGREE" / continues messaging → Consent recorded
   b) "NO" / "STOP" / no response → Consent declined, no processing
5. Consent record created (immutable, timestamped, hashed identifier)
6. Normal service begins (if consented)
```

### 4.2 Consent Types

Three types of consent are captured for each data subject:

| Consent Type | Description | Required for Service | Withdrawal Impact |
|-------------|-------------|---------------------|-------------------|
| **PI processing** | Basic consent to process personal information (phone number, name, location, facilities requests) for building management purposes | Yes | Service discontinued |
| **Data retention** | Agreement to 90-day raw data / 2-year aggregate data retention periods | Yes | Data deleted per POPIA |
| **Cross-border transfer** | Acknowledgment that AI processing may use international services (Anthropic Claude API, US-based) | No (service degrades to local AI) | AI chat uses Ollama only |

### 4.3 Consent Storage

- **Immutable records:** All consent decisions are stored as append-only records; withdrawals create new records rather than modifying existing ones
- **Hashed identifiers:** Phone numbers and user IDs are hashed with SHA-256 before storage, ensuring PI is not stored in plaintext in the consent database
- **Dual-write:** Consent records are written to both Supabase (primary) and JSON file (fallback), consistent with SENTINEL's dual-write architecture
- **Audit trail:** Each consent record includes record_id, timestamp, platform, consent_text, and metadata

**Implementation:** `backend/app/services/consent_service.py`
**API endpoints:** `backend/app/api/consent.py`
**Data storage:** `backend/app/data/consent_records.json`

### 4.4 Consent Withdrawal

Data subjects can withdraw consent at any time:

- **WhatsApp/Telegram:** Send "STOP" keyword
- **Web portal:** Navigate to privacy settings
- **Email:** Contact privacy@[company-domain]

**Withdrawal process:**
1. Withdrawal request received
2. New withdrawal record created (immutable audit trail)
3. Active consent marked with withdrawal timestamp
4. Data processing ceases immediately
5. Data deletion scheduled per retention policy
6. Confirmation sent to data subject

---

## 5. External Privacy Notice

SENTINEL's external privacy notice (accessible at the privacy notice URL) must include the following information per POPIA requirements:

### 5.1 What Data Is Collected and Why

| Data | Purpose | Legal Basis |
|------|---------|-------------|
| Phone number | Identify building occupant for service delivery | Consent (POPIA s11) |
| Name | Personalise interactions and work orders | Consent |
| Desk/office location | Route facilities requests to correct zone | Legitimate interest |
| Facilities request text | Fulfill maintenance and comfort requests | Consent + contract |
| Occupancy data (sensors) | Optimise HVAC and lighting for comfort and energy | Legitimate interest |
| Communication messages | Provide conversational building management | Consent |

### 5.2 How Data Is Stored and Protected

- **Encryption at rest:** Database encryption via Supabase (AES-256)
- **Encryption in transit:** TLS 1.2+ for all API communications
- **Access control:** Role-based access with MFA requirement
- **Network security:** Cloudflare Tunnel (zero-trust), Fail2ban, UFW firewall
- **Monitoring:** Wazuh SIEM, Grafana/Loki centralised logging
- **Location:** Primary data stored in South Africa (Supabase region: af-south-1 when available, otherwise eu-west with SA processing node)

### 5.3 Data Retention Periods

| Data Type | Raw Retention | Aggregated Retention | Deletion Method |
|-----------|--------------|---------------------|-----------------|
| Telemetry (sensor readings) | 90 days | 2 years | Automated purge |
| Communication messages | 90 days | Not aggregated | Automated purge |
| Facilities requests | 90 days | 2 years (anonymised) | Anonymisation + purge |
| Consent records | Duration of relationship + 5 years | N/A | Manual after expiry |
| Audit logs | 90 days | 1 year (summary) | Automated purge |
| Occupancy data | 90 days | 2 years (aggregated) | Automated purge |

### 5.4 Data Subject Rights Under POPIA

Building occupants have the following rights:

| Right | POPIA Section | How to Exercise |
|-------|--------------|-----------------|
| **Access** | s23 | Request a copy of all PI held about you |
| **Correction** | s24 | Request correction of inaccurate PI |
| **Deletion** | s24 | Request deletion of PI (subject to retention requirements) |
| **Objection** | s11(3) | Object to processing based on legitimate interest |
| **Withdrawal of consent** | s11(2)(a) | Withdraw consent at any time via "STOP" or contact |
| **Complaint** | s74 | Lodge complaint with Information Regulator |
| **Data portability** | s23 | Request PI in machine-readable format |

**How to exercise rights:**
- WhatsApp/Telegram: Message "RIGHTS" or "PRIVACY"
- Email: privacy@[company-domain]
- Response time: Within 30 days per POPIA

### 5.5 Cross-Border Transfer Disclosure

SENTINEL uses the following international services for AI-assisted processing:

| Service | Provider | Location | Data Transferred | Legal Basis |
|---------|----------|----------|-----------------|-------------|
| **Claude API** | Anthropic | United States | Chat messages (processed, not stored) | POPIA s72: adequate protection + consent |
| **WhatsApp** | Meta | International (various) | Messages (Meta terms of service) | Existing relationship + consent |
| **Telegram** | Telegram FZ-LLC | International (various) | Messages (Telegram terms of service) | Existing relationship + consent |

**POPIA Section 72 conditions for cross-border transfer:**
1. Recipient country provides adequate level of protection (US: adequacy assessment required)
2. Data subject consents to the transfer (captured in cross_border_transfer consent type)
3. Transfer is necessary for performance of contract
4. Transfer is for benefit of data subject

**Mitigation measures:**
- Claude API processes messages ephemerally (not retained by Anthropic for training when using API)
- No raw PI is sent to Claude API — messages are contextualised with building data only
- Ollama (local AI) available as fallback for all AI processing without cross-border transfer
- Data subjects who decline cross-border consent still receive service via Ollama

### 5.6 Contact Details

| Role | Contact |
|------|---------|
| **Responsible Party (FM Company)** | [FM Company name and contact details] |
| **Information Officer** | [Designated information officer] |
| **Privacy queries** | privacy@[company-domain] |
| **Information Regulator** | inforeg.org.za |

---

## 6. Data Retention and Deletion

### 6.1 Retention Schedule

```
Day 0-90:    Raw data retained (full PI, full detail)
Day 91:      Raw data deleted, aggregated/anonymised data retained
Day 91-730:  Aggregated data retained (no PI, statistical only)
Day 731:     Aggregated data deleted
```

**Consent records exception:** Retained for duration of relationship + 5 years for compliance audit purposes.

### 6.2 Deletion Process at Contract Termination

When the FM company terminates their SENTINEL contract:

1. **Notification:** FM company provides 30-day termination notice
2. **Data export:** FM company can export all data in machine-readable format
3. **Grace period:** 30 days after termination for data retrieval
4. **Deletion:** All PI permanently deleted from:
   - Supabase database (cascading delete)
   - JSON fallback files (secure overwrite)
   - InfluxDB telemetry (drop measurement)
   - Loki logs (expire after retention)
   - Backup snapshots (expire after retention period)
5. **Destruction certificate:** Written confirmation of data destruction issued
6. **Consent records:** Retained separately for compliance (5 years post-termination)
7. **Audit logs:** Retained separately for compliance (1 year summary)

### 6.3 Automated Deletion

SENTINEL implements automated data lifecycle management:

- **90-day purge:** Background job removes raw telemetry and PI older than 90 days
- **Aggregation:** Before purge, data is aggregated and anonymised for trend analysis
- **Audit trail:** Deletion events logged for compliance evidence
- **Verification:** Monthly check that purge jobs completed successfully

---

## 7. FSR Privacy Controls Mapping

### Section 1: Privacy Governance

| Requirement | Evidence |
|-------------|----------|
| Privacy policy exists | This document + external privacy notice |
| Information officer designated | Contact details in Section 5.6 |
| Privacy impact assessment | Performed for WhatsApp/Telegram integration |

### Section 3: Personal Information Processing

| Requirement | Evidence |
|-------------|----------|
| Lawful processing basis identified | Consent (POPIA s11) for each data type |
| Purpose limitation | FM operations and building management only |
| Collection minimisation | Only data necessary for service delivery |
| Processing register | Sections 2 and 3 of this document |

### Section 4: Data Subject Rights

| Requirement | Evidence |
|-------------|----------|
| Rights communicated to data subjects | External privacy notice (Section 5.4) |
| Access request process | Documented in Section 5.4 |
| Correction process | Documented in Section 5.4 |
| Deletion process | Documented in Section 6 |

### Section 7: Cross-Border Transfers

| Requirement | Evidence |
|-------------|----------|
| Cross-border transfers identified | Section 5.5 |
| Adequate protection assessed | POPIA s72 conditions documented |
| Data subject consent obtained | cross_border_transfer consent type |
| Mitigation measures in place | Ollama fallback, ephemeral processing |

---

## 8. Related Documents

| Document | Location |
|----------|----------|
| Consent Service (implementation) | `backend/app/services/consent_service.py` |
| Consent API (endpoints) | `backend/app/api/consent.py` |
| Security Awareness Training | `infrastructure/training/security-awareness-plan.md` |
| BCP/DR Procedures | `docs/08-security/bcp-dr-procedures.md` |
| Logging Architecture | `docs/08-security/logging-architecture.md` |
| Access Control Implementation | `docs/08-security/access-control-implementation.md` |
| Vulnerability Management | `docs/08-security/vulnerability-management.md` |
| Sentry Telegram Integration | `docs/SENTRY_INTEGRATION.md` |

---

## 9. Document Control

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-02-04 | SENTINEL Platform Team | Initial creation |

---

*Document maintained by SENTINEL Platform Team. Annual review required for FSR compliance.*
