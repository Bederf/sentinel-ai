---
title: "Privacy Impact Assessment: Sentry Messaging Platforms"
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

# Privacy Impact Assessment: Sentry Messaging Platforms

**PIA Reference:** PIA-2026-002
**Document Owner:** Information Security Officer
**Version:** 1.0
**Effective Date:** 2026-02-05
**Review Cadence:** Annually or when processing activities change
**FSR Reference:** Domain 4.3 -- Information Classification & Data Privacy
**Classification:** Confidential
**Status:** Approved

---

## Section 1: Project Description

### 1.1 Project Overview

| Field | Details |
|-------|---------|
| **PIA Reference** | PIA-2026-002 |
| **Project/System Name** | Sentry Telegram/WhatsApp Bot Integration |
| **Business Owner** | SENTINEL Platform Team |
| **Technical Owner** | SENTINEL Development Team |
| **Date Initiated** | 2025-09-01 |
| **PIA Prepared By** | SENTINEL Platform Team |
| **PIA Version** | 1.0 |

### 1.2 Purpose of Processing

Sentry is a Telegram/WhatsApp bot that enables technicians and building occupants to interact with SENTINEL:

- **Primary purpose:** Work order creation and management via messaging platforms
- **Secondary purposes:** Equipment fault reporting, desk comfort complaints, technician dispatch notifications
- **Business justification:** Messaging platforms provide convenient mobile access for field technicians who may not have access to desktop applications

### 1.3 Scope

- **Systems involved:** Sentry bot (`$SENTRY_HOME`), SENTINEL API, WhatsApp Business API (Meta), Telegram Bot API
- **Geographic scope:** South Africa (users) with cross-border processing to Meta (US/Ireland) and Telegram (UAE/Netherlands/Singapore) infrastructure
- **Data subjects:** Building technicians, facilities managers, building occupants
- **Timeframe:** Ongoing operational use

---

## Section 2: Data Inventory

### 2.1 Personal Information Categories

| Category | Description | Examples | Volume (Est.) | Sensitivity |
|----------|-------------|----------|---------------|-------------|
| Technician Names | Full names of assigned technicians | "John Smith", "Thabo Mokoena" | ~20 technicians | Medium |
| Technician Phone Numbers | Mobile numbers for WhatsApp/Telegram | "+27 82 XXX XXXX" | ~20 technicians | Medium |
| Technician Telegram IDs | Telegram user identifiers | "@john_tech", chat_id | ~20 technicians | Low-Medium |
| Equipment Fault Descriptions | Details of equipment issues | "Chiller making unusual noise" | ~100/month | Low |
| Work Order IDs | SENTINEL work order references | "WO-2026-0234" | ~100/month | Low |
| Building Locations | Site and zone references | "Sandton City, Level 2" | ~100/month | Low |
| Occupant Comfort Complaints | Comfort issues from occupants | "Too hot at desk 201" | ~50/month | Low |

### 2.2 Special Personal Information

| Category | Processed? | Justification |
|----------|------------|---------------|
| Religious or philosophical beliefs | No | Not applicable to work orders |
| Race or ethnic origin | No | Not applicable to work orders |
| Trade union membership | No | Not applicable to work orders |
| Political persuasion | No | Not applicable to work orders |
| Health or sex life | No | Not applicable to work orders |
| Biometric information | No | Not collected |
| Criminal behaviour | No | Not applicable to work orders |
| Children's information | No | All users are adult employees/technicians |

### 2.3 Data Sources

| Source | Description | Lawful Basis |
|--------|-------------|--------------|
| Telegram Messages | User messages to Sentry bot | Contract (employment/service agreement) + Consent |
| WhatsApp Messages | User messages via WhatsApp Business API | Contract (employment/service agreement) + Consent |
| SENTINEL API | Work order and equipment data | Legitimate interest (building management) |
| Technician Database | Stored technician contact details | Contract (employment terms) |

### 2.4 Data Retention

| Data Category | Retention Period | Justification | Destruction Method |
|---------------|------------------|---------------|--------------------|
| Message content (SENTINEL) | 30 days | Operational troubleshooting | Automated purge |
| Message content (WhatsApp) | Per Meta policy (varies) | Platform retention | Platform managed |
| Message content (Telegram) | Per Telegram policy | Platform retention | Platform managed |
| Work order records | 7 years | Legal/audit requirements | Secure deletion |
| Technician contact details | Employment duration + 2 years | HR records requirements | Secure deletion |

---

## Section 3: Necessity and Proportionality Assessment

### 3.1 Legal Basis for Processing (POPIA Section 11)

| Basis | Applicable? | Justification |
|-------|-------------|---------------|
| **Consent** (s11(1)(a)) | Yes (Secondary) | Consent for cross-border transfer; consent for PI processing via messaging |
| **Contract** (s11(1)(b)) | Yes (Primary) | Necessary for work order management per employment/service contracts |
| **Legal obligation** (s11(1)(c)) | No | Not required by law |
| **Legitimate interest** (s11(1)(d)) | Yes (Supporting) | Efficient facilities management |
| **Public interest** (s11(1)(e)) | No | Not a public law duty |
| **Protection of legitimate interests** (s11(1)(f)) | No | Not applicable |

**Primary basis:** Contract performance (work order management)
**Secondary basis:** Consent (cross-border transfer, PI processing)

### 3.2 Necessity Test

- [x] Is the processing necessary for the stated purpose? **Yes** - Messaging enables mobile technician access
- [x] Can the purpose be achieved with less data? **Partially** - Names and phone numbers required for assignment/notification
- [x] Can the purpose be achieved with anonymised/pseudonymised data? **No** - Technician identification required for work order assignment
- [x] Is the data retained only for as long as necessary? **Yes** - 30-day message retention; work orders per legal requirements

### 3.3 Proportionality Test

| Factor | Assessment |
|--------|------------|
| **Benefits to organisation** | Faster work order processing, mobile technician access, improved response times |
| **Benefits to data subjects** | Convenient mobile interface, real-time notifications, faster fault resolution |
| **Potential harm to data subjects** | Phone numbers and names transmitted to third-party platforms; platform-specific retention policies |
| **Overall proportionality** | **Proportionate** - Benefits outweigh moderate privacy impact; data minimised to essential fields |

---

## Section 4: Data Flow Diagram

### 4.1 Data Flow Overview

```
Technician/Occupant (South Africa)
           |
           v
    [WhatsApp/Telegram App]
           |
           | Message to Sentry bot
           v
    [WhatsApp Business API / Telegram Bot API]
           |                              |
           | (Meta infrastructure)        | (Telegram infrastructure)
           | USA / Ireland                | UAE / Netherlands / Singapore
           |                              |
           +------------------------------+
                       |
                       v
              [Sentry Bot Server]
                       |
                       | Parse request, query SENTINEL API
                       v
              [SENTINEL Backend API]
                       |
                       | Work order creation, technician lookup
                       v
              [SENTINEL Database]
                       |
                       | Response back through chain
                       v
    [WhatsApp/Telegram] --> Technician/Occupant
```

### 4.2 Data Flow Description

| Step | From | To | Data Elements | Transfer Method | Encryption |
|------|------|-----|--------------|-----------------|------------|
| 1 | User | WhatsApp/Telegram App | Message text | App encryption | Yes (E2E for WhatsApp; TLS for Telegram bots) |
| 2 | App | Platform API | Message + user metadata | HTTPS | Yes (TLS 1.3) |
| 3 | Platform | Sentry Bot | Webhook payload (message, user info) | HTTPS | Yes (TLS 1.3) |
| 4 | Sentry | SENTINEL API | Parsed request | HTTPS | Yes (TLS 1.3) |
| 5 | SENTINEL | Sentry | Work order data, technician info | HTTPS | Yes (TLS 1.3) |
| 6 | Sentry | Platform API | Response message | HTTPS | Yes (TLS 1.3) |
| 7 | Platform | User App | Response message | App encryption | Yes |

### 4.3 Cross-Border Transfers

| Recipient | Country | Data Transferred | POPIA s72 Basis | Safeguards |
|-----------|---------|------------------|-----------------|------------|
| Meta (WhatsApp Business API) | USA / Ireland | Phone numbers, message content, user metadata | s72(1)(b) consent; s72(1)(d) necessary for service | End-to-end encryption; WhatsApp Business API terms |
| Telegram FZ-LLC | UAE / Netherlands / Singapore | Phone numbers, Telegram user IDs, message content | s72(1)(b) consent; s72(1)(d) necessary for service | Client-server encryption; Telegram Bot API terms |

---

## Section 5: Risk Assessment

### 5.1 Risk Identification

| Risk ID | Risk Description | Risk Category |
|---------|------------------|---------------|
| R1 | Technician PII (names, phone numbers) exposed to Meta/Telegram | Confidentiality |
| R2 | Cross-border transfer to multiple jurisdictions (US, Ireland, UAE, NL, SG) | Confidentiality |
| R3 | Telegram bot messages not end-to-end encrypted | Confidentiality |
| R4 | Platform data retention policies outside SENTINEL control | Confidentiality |
| R5 | Unauthorised access to Sentry bot (impersonation) | Integrity |
| R6 | Work order data exposed via messaging platform | Confidentiality |
| R7 | Platform security breach affecting technician data | Confidentiality |

### 5.2 Risk Assessment Table

| Risk ID | Likelihood | Impact | Score | Level | Risk Owner |
|---------|------------|--------|-------|-------|------------|
| R1 | 5 (Certain - design requirement) | 2 (Limited) | 10 | Medium | ISO |
| R2 | 5 (Certain - inherent in architecture) | 2 (Limited) | 10 | Medium | ISO |
| R3 | 5 (Certain - Telegram design) | 2 (Limited) | 10 | Medium | Technical Owner |
| R4 | 4 (Likely - platform policy varies) | 2 (Limited) | 8 | Medium | ISO |
| R5 | 2 (Unlikely - authentication controls) | 3 (Significant) | 6 | Medium | Technical Owner |
| R6 | 3 (Possible - design exposure) | 2 (Limited) | 6 | Medium | Technical Owner |
| R7 | 2 (Unlikely - platform security) | 3 (Significant) | 6 | Medium | ISO |

---

## Section 6: Mitigating Controls

### 6.1 Technical Controls

| Control ID | Control Description | Risk(s) Addressed | Implementation Status |
|------------|---------------------|-------------------|----------------------|
| TC1 | **Data minimisation** - Only essential PI transmitted (name, phone for assignment) | R1, R6 | Implemented |
| TC2 | **End-to-end encryption** - WhatsApp messages E2E encrypted | R3 (WhatsApp) | Inherent (platform) |
| TC3 | **TLS encryption** - All API communications encrypted | R1, R2, R3 | Implemented |
| TC4 | **User authentication** - Telegram user ID verification against registered technicians | R5 | Implemented |
| TC5 | **Message content sanitisation** - No building occupant names in work orders | R1, R6 | Implemented |
| TC6 | **30-day message retention** - SENTINEL-side logs purged after 30 days | R4 | Implemented |
| TC7 | **Secure webhook endpoints** - Sentry webhooks validate signature/tokens | R5 | Implemented |

### 6.2 Organisational Controls

| Control ID | Control Description | Risk(s) Addressed | Implementation Status |
|------------|---------------------|-------------------|----------------------|
| OC1 | **Consent capture** - Technicians consent to messaging channel use during onboarding | R1, R2 | Implemented |
| OC2 | **Privacy notice** - Clear disclosure of messaging platform use | R1, R2 | Implemented |
| OC3 | **Technician training** - Guidance on appropriate message content | R6 | Planned |
| OC4 | **Incident response** - Process for messaging-related incidents | R7 | Implemented |
| OC5 | **Annual PIA review** - Reassess platform risks annually | All | Planned (this document) |

### 6.3 Contractual Controls

| Control ID | Control Description | Third Party | Status |
|------------|---------------------|-------------|--------|
| CC1 | **WhatsApp Business API Terms** - Compliance with Meta policies | Meta | In place |
| CC2 | **Telegram Bot API Terms** - Compliance with Telegram policies | Telegram | In place |
| CC3 | **Employment agreements** - Consent to messaging-based work assignment | Technicians | In place |

---

## Section 7: Residual Risk Evaluation

### 7.1 Residual Risk Assessment

| Risk ID | Original Score | Controls Applied | Residual Score | Residual Level | Acceptable? |
|---------|----------------|------------------|----------------|----------------|-------------|
| R1 | 10 (Medium) | TC1, TC5, OC1, OC2 | 6 | Medium | Yes |
| R2 | 10 (Medium) | OC1, OC2 | 6 | Medium | Yes |
| R3 | 10 (Medium) | TC2 (WhatsApp), TC3 | 6 | Medium | Yes |
| R4 | 8 (Medium) | TC6, OC5 | 4 | Low | Yes |
| R5 | 6 (Medium) | TC4, TC7 | 2 | Low | Yes |
| R6 | 6 (Medium) | TC1, TC5, OC3 | 3 | Low | Yes |
| R7 | 6 (Medium) | OC4 | 4 | Low | Yes |

### 7.2 Overall Residual Risk Rating

| Level | Criteria | This Assessment |
|-------|----------|-----------------|
| **LOW** | All residual risks are Low or Medium with effective controls | [ ] |
| **MEDIUM** | Some High residual risks with mitigation plans in progress | [x] |
| **HIGH** | Critical or multiple High residual risks without adequate mitigation | [ ] |

**Overall Residual Risk: MEDIUM**

The inherent nature of messaging platforms requires transmitting technician PII (names, phone numbers) to third-party infrastructure. While data minimisation and consent controls reduce the impact, the cross-border transfer and platform retention policies remain medium-level residual risks that are accepted as necessary for operational efficiency.

---

## Section 8: POPIA Compliance Checklist

### 8.1 Conditions for Lawful Processing

| Condition | Requirement | Status | Evidence/Notes |
|-----------|-------------|--------|----------------|
| **1. Accountability** | Organisation takes responsibility for compliance | Met | This PIA; consent capture; training |
| **2. Processing Limitation** | Processing is lawful, adequate, relevant, not excessive | Met | Data minimised to work order essentials |
| **3. Purpose Specification** | Personal information collected for specific, explicit, legitimate purpose | Met | Purpose: Work order management and technician dispatch |
| **4. Further Processing Limitation** | Further processing compatible with original purpose | Met | Platforms prohibited from marketing use |
| **5. Information Quality** | Information is complete, accurate, not misleading, updated | Met | Technician records maintained by HR |
| **6. Openness** | Privacy notice provided to data subjects | Met | Privacy notice during onboarding |
| **7. Security Safeguards** | Appropriate technical and organisational measures | Met | Encryption, authentication, webhook validation |
| **8. Data Subject Participation** | Data subjects can access, correct, delete their information | Met | Technicians can request data via HR |

### 8.2 Cross-Border Transfer Compliance (Section 72)

| Requirement | Status | Evidence |
|-------------|--------|----------|
| Transfer only to countries with adequate protection | Compliant | Consent obtained; necessary for service |
| Binding corporate rules in place | N/A | Using consent basis |
| Data subject consent obtained | Compliant | Technician onboarding consent; `PI_processing` consent type |
| Transfer necessary for contract performance | Compliant | Work order management is core service |
| Transfer for benefit of data subject | Compliant | Enables mobile work access for technicians |

### 8.3 Platform-Specific Compliance

**WhatsApp Business API:**
- End-to-end encryption for message content
- Meta processes data per WhatsApp Business Terms
- No marketing use of business messaging data
- GDPR-compliant data handling in Ireland

**Telegram Bot API:**
- Client-server encryption (not E2E for bots)
- Telegram processes data per Bot API Terms
- Server-side storage subject to Telegram policies
- Multi-jurisdiction infrastructure

---

## Section 9: Recommendations

### 9.1 Required Actions (Before Processing)

| Action | Priority | Responsible | Target Date | Status |
|--------|----------|-------------|-------------|--------|
| Update technician onboarding consent forms | High | HR | 2025-09-01 | Complete |
| Implement webhook signature validation | High | Dev Team | 2025-09-01 | Complete |
| Review platform privacy policies | High | ISO | 2026-02-05 | Complete |

### 9.2 Recommendations (To Improve Privacy)

| Recommendation | Rationale | Implementation Cost |
|----------------|-----------|---------------------|
| Offer alternative notification channels | Provide SMS option for technicians who decline messaging platform consent | Medium |
| Implement message expiry notifications | Remind users that messages are retained by platforms | Low |
| Regular platform policy review | Monitor changes to Meta/Telegram data handling | Low |
| Consider self-hosted messaging | Mattermost or similar for highest privacy requirements | High |

### 9.3 Conditions for Approval

Processing may proceed only if:

- [x] All required actions are completed
- [x] Residual risk is acceptable to the risk owner
- [x] All POPIA conditions are met
- [x] Sign-off obtained from Information Security Officer

---

## Section 10: Sign-off and Review Schedule

### 10.1 PIA Sign-off

| Role | Name | Date |
|------|------|------|
| **Business Owner** | SENTINEL Platform Team | 2026-02-05 |
| **Technical Owner** | SENTINEL Development Team | 2026-02-05 |
| **Information Security Officer** | SENTINEL ISO | 2026-02-05 |

### 10.2 Approval Decision

| Decision | Date | Approved By |
|----------|------|-------------|
| [x] **Approved** - Processing may proceed | 2026-02-05 | Information Security Officer |
| [ ] **Approved with conditions** - Processing may proceed after completing required actions | | |
| [ ] **Not approved** - Processing must not proceed until issues resolved | | |

### 10.3 Review Schedule

| Review Type | Frequency | Next Review Date |
|-------------|-----------|------------------|
| Annual PIA review | 12 months | 2027-02-05 |
| Triggered review (on change) | As needed | N/A |
| Platform policy review | 6 months | 2026-08-05 |

**Triggers for immediate review:**
- Change in Meta or Telegram privacy policies
- New data categories transmitted via messaging
- Security incident involving messaging platforms
- Changes to POPIA requirements
- Addition of new messaging platform

---

## Appendices

### Appendix A: WhatsApp Business API Privacy Reference

**Meta Data Use:**
- Business messages stored for delivery purposes
- Metadata may be used for service improvement
- No advertising targeting based on business message content
- Data processing in compliance with GDPR (Ireland operations)

**Reference:** [WhatsApp Business Terms](https://www.whatsapp.com/legal/business-terms)

### Appendix B: Telegram Bot API Privacy Reference

**Telegram Data Use:**
- Bot messages stored on Telegram servers
- Not end-to-end encrypted (cloud-based storage)
- User metadata accessible to bot developers
- Multi-jurisdiction infrastructure (UAE, Netherlands, Singapore)

**Reference:** [Telegram Bot API Terms](https://core.telegram.org/bots/tos)

### Appendix C: Sentry Bot Architecture

The Sentry bot (`$SENTRY_HOME`) integrates with SENTINEL via:
- `sentry_ai_bridge.py` - Message routing and AI integration
- `bms_desk_diagnosis.py` - Desk comfort diagnosis
- SENTINEL API webhooks for work order management

**Key privacy features:**
- No bulk data export to messaging platforms
- Minimal message content (work order IDs, equipment codes)
- Technician data looked up from SENTINEL, not stored in Sentry

### Appendix D: Version History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-02-05 | SENTINEL Platform Team | Initial PIA |

---

## References

| Document | Location |
|----------|----------|
| SENTINEL Third-Party Security Register | `docs/08-security/third-party-security-register.md` |
| SENTINEL Consent and Privacy Controls | `docs/08-security/consent-and-privacy.md` |
| Sentry Integration Documentation | `docs/SENTRY_INTEGRATION.md` |
| Sentry Bot Code | `$SENTRY_HOME/` |
| WhatsApp Business Terms | https://www.whatsapp.com/legal/business-terms |
| Telegram Bot API Terms | https://core.telegram.org/bots/tos |
| POPIA Section 72 | Cross-border transfer requirements |

---

*This PIA is maintained by the Information Security Officer. Annual review is mandatory, with platform policy reviews every 6 months.*
