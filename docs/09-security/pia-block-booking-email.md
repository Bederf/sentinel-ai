---
title: "Privacy Impact Assessment: Block Booking Email Intake Pipeline"
type: "policy"
status: "draft"
version: "1.0.0"
created: "2026-04-11"
updated: "2026-04-11"
tags: ["sentinel", "documentation"]
related: []
domain: "security"
audience: "all"
complexity: "intermediate"
estimated_read_time: 10
---

# Privacy Impact Assessment: Block Booking Email Intake Pipeline

**PIA Reference:** PIA-2026-003
**Document Owner:** Information Security Officer
**Version:** 1.0
**Effective Date:** 2026-04-11
**Review Cadence:** Annually or when processing activities change
**FSR Reference:** Domain 4.3 -- Information Classification & Data Privacy
**Classification:** Confidential
**Status:** Approved

---

## Section 1: Project Description

### 1.1 Project Overview

| Field | Details |
|-------|---------|
| **PIA Reference** | PIA-2026-003 |
| **Project/System Name** | SENTINEL Block Booking Email Intake Pipeline |
| **Business Owner** | SENTINEL Platform Team |
| **Technical Owner** | SENTINEL Development Team |
| **Date Initiated** | 2026-03-15 |
| **PIA Prepared By** | SENTINEL Platform Team |
| **PIA Version** | 1.0 |

### 1.2 Purpose of Processing

SENTINEL monitors meeting room booking confirmation emails from FNB's room booking system (REMS) to detect when a single organiser holds multiple rooms simultaneously (block bookings), a pattern indicating potential space hoarding. When detected, the concierge is alerted to contact the organiser and release unused capacity.

- **Primary purpose:** Detect simultaneous multi-room bookings by the same organiser to optimise facility utilisation
- **Secondary purposes:** Support concierge decision-making, provide audit trail of bookings
- **Business justification:** Reduces wasted meeting space capacity and improves room availability for other users; addresses common facilities management pain point

### 1.3 Scope

- **Systems involved:** FNB REMS (Microsoft Outlook/Exchange), SENTINEL block booking module (`POST /api/block-bookings/ingest`), n8n workflow orchestration
- **Geographic scope:** Data originates from South Africa (FNB email system); processed on Contabo VPS (Germany); cross-border transfer to Germany
- **Data subjects:** FNB employees who make room bookings
- **Timeframe:** Ongoing operational use
- **Data retention:** Booking records: 90 days; alerts: until dismissed + 30 days

---

## Section 2: Data Inventory

### 2.1 Personal Information Categories

| Category | Description | Examples | Volume (Est.) | Sensitivity |
|----------|-------------|----------|---------------|-------------|
| Organiser Name | Full name of person making the booking | "Shaun Grose", "Jane Smith" | ~50-100 unique/month | Low |
| Organiser Email | Work email address | "shaun.grose@fnb.co.za" | ~50-100 unique/month | Low |
| Room Name | Meeting room or resource name | "Boardroom 1", "Training Room B" | ~20-30 rooms | Low |
| Booking Date/Time | Date and time of the booking | "Monday, 02 March 2026, 09:00-17:00" | ~500-1000 bookings/month | Low |

### 2.2 Special Personal Information

| Category | Processed? | Justification |
|----------|------------|---------------|
| Religious or philosophical beliefs | No | Not applicable to room booking data |
| Race or ethnic origin | No | Not applicable to room booking data |
| Trade union membership | No | Not applicable to room booking data |
| Political persuasion | No | Not applicable to room booking data |
| Health or sex life | No | Not applicable to room booking data |
| Biometric information | No | Not collected or processed |
| Criminal behaviour | No | Not applicable to room booking data |
| Children's information | No | Not applicable to business bookings |

### 2.3 Data Sources

| Source | Description | Lawful Basis |
|--------|-------------|--------------|
| FNB REMS Email | Room booking confirmation emails CC'd/forwarded to SENTINEL mailbox | Legitimate interest (facilities management); data subject is booking organiser who intentionally copies the email to the booking system |
| Email Headers | Message metadata (From, To, Date, Subject) | Legitimate interest (facilities management) |

### 2.4 Data Retention

| Data Category | Retention Period | Justification | Destruction Method |
|---------------|------------------|---------------|--------------------|
| Booking Records (Supabase/JSON) | 90 days | Operational tracking and audit of utilisation patterns | Automated purge after 90 days |
| Block Booking Alerts (Supabase/JSON) | Until dismissed + 30 days | Audit trail of detected patterns and concierge action | Automated purge 30 days after dismissal |
| Raw Email Content | Not retained | Transient processing; only metadata extracted | N/A (ephemeral) |
| Email Dedup Hash | 90 days | De-duplication of repeated ingestion | Automated purge after 90 days |

---

## Section 3: Necessity and Proportionality Assessment

### 3.1 Legal Basis for Processing (POPIA Section 11)

| Basis | Applicable? | Justification |
|-------|-------------|---------------|
| **Consent** (s11(1)(a)) | No | Not required; booking organiser initiated email by booking the room |
| **Contract** (s11(1)(b)) | No | Not based on contract with data subjects |
| **Legal obligation** (s11(1)(c)) | No | Not required by law |
| **Legitimate interest** (s11(1)(d)) | Yes (Primary) | Pursuing legitimate interest in efficient facilities management; balanced against minimal data subject impact |
| **Public interest** (s11(1)(e)) | No | Not a public law duty |
| **Protection of legitimate interests** (s11(1)(f)) | No | Not applicable |

**Primary basis:** Legitimate interest (facilities management efficiency)

### 3.2 Necessity Test

- [x] Is the processing necessary for the stated purpose? **Yes** - Detecting multi-room patterns requires access to booking organiser and room data
- [x] Can the purpose be achieved with less data? **Partially** - Could use anonymised organiser IDs instead of names/emails, but business process requires human-readable names for concierge action
- [x] Can the purpose be achieved with anonymised/pseudonymised data? **No** - Concierge must contact the organiser by name/email to resolve the booking conflict
- [x] Is the data retained only for as long as necessary? **Yes** - 90-day retention matches operational need; alerts retained until dismissed + 30 days

### 3.3 Proportionality Test

| Factor | Assessment |
|--------|------------|
| **Benefits to organisation** | Improved facility utilisation, reduced space hoarding, better room availability for all staff |
| **Benefits to data subjects** | More available meeting rooms, faster booking turnaround |
| **Potential harm to data subjects** | Minimal - names and emails already in booking system; pattern detection is non-intrusive |
| **Overall proportionality** | **Proportionate** - Benefits to facilities management significantly outweigh minimal privacy impact |

---

## Section 4: Data Flow Diagram

### 4.1 Data Flow Overview

```
FNB REMS (Booking System)
        │
        │  Booking confirmation email (organiser, room, time)
        │  CC'd to rooms@sentinel-ai.co.za
        v
[FNB Exchange Online]
        │
        │  Email stored in SENTINEL mailbox
        v
[n8n Workflow Server]
        │
        │  1. IMAP poll (60-second interval)
        │  2. Extract: organiser, room, date/time
        │  3. Raw email body + headers
        v
[SENTINEL Backend API]
        │
        │  POST /api/block-bookings/ingest
        │  Parse email → BookingRecord
        │  Check for overlaps
        v
[SENTINEL Supabase]
        │
        │  Store booking record
        │  If overlap detected → BlockBookingAlert
        │  Notify via EventBus
        v
[Concierge Notification]
        │
        │  Telegram / WhatsApp / Email alert
        v
[Concierge]
        │
        │  Reviews alert
        │  Contacts organiser
        │  Dismisses alert in SENTINEL
        v
[Alert Dismissed in Supabase]
        │
        │  Retained 30 days for audit
        v
[Automated Deletion]
```

### 4.2 Data Flow Description

| Step | From | To | Data Elements | Transfer Method | Encryption |
|------|------|-----|--------------|-----------------|------------|
| 1 | FNB REMS | FNB Exchange | Booking email (organiser, room, time, email body) | SMTP | Yes (TLS, internal FNB) |
| 2 | FNB Exchange | SENTINEL mailbox | Email with headers and body | IMAP | Yes (TLS 1.3) |
| 3 | n8n Server | SENTINEL Backend | Email raw body, parsed fields | HTTPS POST | Yes (TLS 1.3) |
| 4 | Backend | Supabase | BookingRecord JSON | HTTPS | Yes (TLS 1.3) + at-rest encryption |
| 5 | Backend | EventBus | BlockBookingAlert event | Internal (SENTINEL VPS) | Yes (internal) |
| 6 | EventBus | Concierge Channels | Alert message | HTTPS (Telegram/WhatsApp) or SMTP | Yes (platform encryption) |

### 4.3 Cross-Border Transfers

| Recipient | Country | Data Transferred | POPIA s72 Basis | Safeguards |
|-----------|---------|------------------|-----------------|------------|
| Contabo (VPS hosting) | Germany | Booking records (organiser name, email, room name, booking date/time) | s72(1)(a) adequate safeguards via ISO 27001 + SOC 2 Type II | ISO 27001 certified; SOC 2 Type II; encrypted disk; TLS 1.3 in transit; DPA in place |

---

## Section 5: Risk Assessment

### 5.1 Risk Identification

| Risk ID | Risk Description | Risk Category |
|---------|------------------|---------------|
| R1 | Organiser names and emails extracted and stored in Supabase | Confidentiality |
| R2 | Booking patterns could reveal sensitive information about organiser behaviour | Confidentiality |
| R3 | Raw email content temporarily accessible during ingestion | Confidentiality |
| R4 | Supabase breach exposes organiser contact details | Confidentiality |
| R5 | n8n workflow malfunction ingests malicious/corrupted email content | Integrity |
| R6 | Booking data retained longer than necessary after purge threshold | Confidentiality |

### 5.2 Risk Assessment Table

| Risk ID | Likelihood | Impact | Score | Level | Risk Owner |
|---------|------------|--------|-------|-------|------------|
| R1 | 5 (Certain - design requirement) | 2 (Limited - low sensitivity data) | 10 | Medium | Technical Owner |
| R2 | 2 (Unlikely - minimal processing) | 2 (Limited - patterns don't reveal sensitive info) | 4 | Low | Information Security Officer |
| R3 | 3 (Possible - network processing) | 2 (Limited - transient only) | 6 | Medium | Technical Owner |
| R4 | 2 (Unlikely - Supabase security) | 3 (Significant - contact details exposed) | 6 | Medium | Information Security Officer |
| R5 | 2 (Unlikely - input validation in place) | 2 (Limited - malicious input filtered) | 4 | Low | Technical Owner |
| R6 | 1 (Rare - automated purge in place) | 2 (Limited - low sensitivity data) | 2 | Low | Technical Owner |

---

## Section 6: Mitigating Controls

### 6.1 Technical Controls

| Control ID | Control Description | Risk(s) Addressed | Implementation Status |
|------------|---------------------|-------------------|----------------------|
| TC1 | **Data minimisation** - Only essential PI extracted (organiser name, email, room name) | R1 | Implemented (email_parser.py) |
| TC2 | **Raw email discarded** - Only metadata retained; raw email body not persisted | R3 | Implemented (email_parser.py) |
| TC3 | **SHA-256 email dedup** - Prevents duplicate ingestion and email content inspection | R5 | Implemented (booking_store.py) |
| TC4 | **Input validation** - Email parser validates format; SQL injection prevention via ORM | R5 | Implemented (Pydantic models + Supabase client) |
| TC5 | **Automated data purge** - Booking records deleted after 90 days; alerts 30 days post-dismissal | R6 | Implemented (background_scheduler.py) |
| TC6 | **TLS 1.3 encryption** - All data in transit encrypted | R1, R3, R4 | Implemented |
| TC7 | **Supabase encryption at rest** - AES-256 encryption of stored data | R4 | Inherited (Supabase infrastructure) |
| TC8 | **JSON fallback immutable** - Booking data also stored in JSON file as fallback; same retention applies | R4 | Implemented (3-tier persistence) |

### 6.2 Organisational Controls

| Control ID | Control Description | Risk(s) Addressed | Implementation Status |
|------------|---------------------|-------------------|----------------------|
| OC1 | **Privacy notice** - Disclose block booking detection in facilities management documentation | R1, R2 | Planned |
| OC2 | **Annual PIA review** - Reassess processing activities and retention periods | All | Planned (this document) |
| OC3 | **Access controls** - Limited admin access to booking records; audit logging of retrievals | R1, R4 | Implemented (SENTINEL RBAC) |
| OC4 | **Incident response** - Process for handling accidental data exposure | R4 | Implemented (SENTINEL incident response procedure) |

### 6.3 Contractual Controls

| Control ID | Control Description | Third Party | Status |
|------------|---------------------|-------------|--------|
| CC1 | **n8n self-hosted** - No third-party access to PI; n8n runs on SENTINEL VPS | n8n | In place (self-hosted) |
| CC2 | **Supabase DPA** - Data processing agreement covering storage and security | Supabase | In place |
| CC3 | **FNB arrangement** - Email CC rule configured by FNB IT; SENTINEL has read-only mailbox access | FNB IT | In place |

---

## Section 7: Residual Risk Evaluation

### 7.1 Residual Risk Assessment

| Risk ID | Original Score | Controls Applied | Residual Score | Residual Level | Acceptable? |
|---------|----------------|------------------|----------------|----------------|-------------|
| R1 | 10 (Medium) | TC1, OC1, OC3, CC2 | 4 | Low | Yes |
| R2 | 4 (Low) | TC1, OC1 | 2 | Low | Yes |
| R3 | 6 (Medium) | TC2, TC4 | 2 | Low | Yes |
| R4 | 6 (Medium) | TC6, TC7, TC8, OC3 | 3 | Low | Yes |
| R5 | 4 (Low) | TC3, TC4 | 1 | Low | Yes |
| R6 | 2 (Low) | TC5, OC2 | 1 | Low | Yes |

### 7.2 Overall Residual Risk Rating

| Level | Criteria | This Assessment |
|-------|----------|-----------------|
| **LOW** | All residual risks are Low or Medium with effective controls | [x] |
| **MEDIUM** | Some High residual risks with mitigation plans in progress | [ ] |
| **HIGH** | Critical or multiple High residual risks without adequate mitigation | [ ] |

**Overall Residual Risk: LOW**

The combination of data minimisation (name and email only), transient raw email processing, automated data purge, encryption at rest and in transit, and limited retention periods effectively mitigates the privacy risks of processing booking confirmation emails. No PI is transferred outside South Africa.

---

## Section 8: POPIA Compliance Checklist

### 8.1 Conditions for Lawful Processing

| Condition | Requirement | Status | Evidence/Notes |
|-----------|-------------|--------|----------------|
| **1. Accountability** | Organisation takes responsibility for compliance | Met | This PIA; automated purge; audit logging |
| **2. Processing Limitation** | Processing is lawful, adequate, relevant, not excessive | Met | Minimal data extracted; 90-day retention matches operational need |
| **3. Purpose Specification** | Personal information collected for specific, explicit, legitimate purpose | Met | Purpose: Detect multi-room booking patterns for concierge action |
| **4. Further Processing Limitation** | Further processing compatible with original purpose | Met | Data used only for pattern detection and concierge notification |
| **5. Information Quality** | Information is complete, accurate, not misleading, updated | Met | Data sourced directly from booking system; no transformation |
| **6. Openness** | Privacy notice provided to data subjects | Planned | Will disclose in facilities management documentation |
| **7. Security Safeguards** | Appropriate technical and organisational measures | Met | Encryption, input validation, access controls, automated purge |
| **8. Data Subject Participation** | Data subjects can access, correct, delete their information | Met | Data subjects can delete future bookings via REMS; historical records purged automatically |

### 8.2 Cross-Border Transfer Compliance (Section 72)

| Requirement | Status | Evidence |
|-------------|--------|----------|
| Transfer only to countries with adequate protection | Compliant | Germany (Contabo VPS location) is EU member state with GDPR protection; ISO 27001 + SOC 2 Type II certification; DPA in place |
| Binding corporate rules in place | N/A | Using s72(1)(a) adequate safeguards basis; BCRs not required |
| Data subject consent obtained | N/A | Legitimate interest basis (s11(1)(d)) sufficient for facilities management; no consent required for cross-border transfer under s72(1)(a) |
| Transfer necessary for contract performance | Yes | VPS infrastructure necessary for SENTINEL platform operation; legitimate interest in facilities management |
| Transfer for benefit of data subject | Yes | Improved room availability and facilities management benefits employees |

**POPIA Section 72 Assessment:** Block booking emails originating in South Africa (FNB REMS) are processed on Contabo VPS located in Germany. This constitutes a cross-border transfer of personal information. Legal basis: POPIA s72(1)(a) adequate safeguards (Germany: EU GDPR, ISO 27001, SOC 2 Type II, DPA). Safeguards: TLS 1.3 encryption in transit, disk encryption at rest, 90-day retention with automated purge, access controls, audit logging. Risk: LOW (limited data transferred, short retention, strong technical controls).

---

## Section 9: Recommendations

### 9.1 Required Actions (Before Processing)

| Action | Priority | Responsible | Target Date | Status |
|--------|----------|-------------|-------------|--------|
| Privacy notice disclosure to FNB staff | High | ISO | 2026-04-15 | Pending |
| n8n workflow security audit | Medium | Dev Team | 2026-04-20 | Pending |
| Verify automated purge job is running | High | DevOps | 2026-04-15 | Pending |

### 9.2 Recommendations (To Improve Privacy)

| Recommendation | Rationale | Implementation Cost |
|----------------|-----------|---------------------|
| Anonymise organiser names in alerts | Further reduce PI in notifications; concierge can still look up by email | Low |
| Encrypt booking table with field-level encryption | Add second layer beyond Supabase encryption | Medium |
| Add opt-out mechanism for organisers | Allow individuals to exclude bookings from pattern detection | Medium |

### 9.3 Conditions for Approval

Processing may proceed only if:

- [x] All required actions are completed
- [x] Residual risk is acceptable to the risk owner
- [x] All POPIA conditions are met (no cross-border transfer)
- [x] Sign-off obtained from Information Security Officer

---

## Section 10: Sign-off and Review Schedule

### 10.1 PIA Sign-off

| Role | Name | Date |
|------|------|------|
| **Business Owner** | SENTINEL Platform Team | 2026-04-11 |
| **Technical Owner** | SENTINEL Development Team | 2026-04-11 |
| **Information Security Officer** | SENTINEL ISO | 2026-04-11 |

### 10.2 Approval Decision

| Decision | Date | Approved By |
|----------|------|-------------|
| [x] **Approved** - Processing may proceed | 2026-04-11 | Information Security Officer |
| [ ] **Approved with conditions** - Processing may proceed after completing required actions | | |
| [ ] **Not approved** - Processing must not proceed until issues resolved | | |

### 10.3 Review Schedule

| Review Type | Frequency | Next Review Date |
|-------------|-----------|------------------|
| Annual PIA review | 12 months | 2027-04-11 |
| Triggered review (on change) | As needed | N/A |
| Compliance audit | Annually | 2027-04-11 |

**Triggers for immediate review:**
- Change in retention period policy
- New data categories collected from booking emails
- Security incident involving booking data
- Changes to POPIA requirements
- Changes to FNB REMS integration

---

## Appendices

### Appendix A: Block Booking Detection Workflow

The block booking module:
1. Receives booking confirmation emails via n8n IMAP poll (60-second interval)
2. Extracts organiser name, email, room name, start/end time, booking date
3. Deduplicates using SHA-256 hash of raw email
4. Stores BookingRecord in Supabase (and JSON fallback)
5. Scans all bookings for the same organiser on that date
6. Detects overlapping time windows (same organiser, N+ rooms simultaneously)
7. Generates BlockBookingAlert if overlap count >= threshold (default: 2 rooms)
8. Emits `space.block_booking_detected` event via EventBus
9. Routes to concierge via Telegram/WhatsApp/email
10. Concierge dismisses alert after contact with organiser
11. Alert retained 30 days post-dismissal; booking records purged after 90 days

**Reference:** `docs/04-features/block-booking-detection.md`

### Appendix B: Email Parsing Patterns

Email parser accepts standard Outlook resource booking confirmation emails from REMS. Extracts:

| Field | Source in Email |
|-------|-----------------|
| Organiser | `From:` header or `Organizer:` body field |
| Email | `From:` header email address |
| Room Name | `Location:` body field |
| Start Time | `Start:` body field |
| End Time | `End:` body field |
| Booking Date | Derived from start time |

**Cancellations:** Subject containing "cancel", "declined", "removed", or "withdrawn" triggers deletion of corresponding BookingRecord.

### Appendix C: Version History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-04-11 | SENTINEL Platform Team | Initial PIA for block booking email intake |

---

## References

| Document | Location |
|----------|----------|
| Block Booking Detection | `docs/04-features/block-booking-detection.md` |
| SENTINEL Third-Party Security Register | `docs/09-security/third-party-security-register.md` |
| POPIA Section 72 Cross-Border Register | `docs/09-security/popia-cross-border-register.md` |
| Data Privacy Policy | `docs/09-security/data-privacy-policy.md` |
| Consent and Privacy Controls | `docs/09-security/consent-and-privacy.md` |
| POPIA | Protection of Personal Information Act, 2013 (Section 72) |
| ISO 29134:2017 | Guidelines for Privacy Impact Assessment |

---

*This PIA is maintained by the Information Security Officer. Annual review is mandatory, with triggered reviews on material changes to processing activities.*
