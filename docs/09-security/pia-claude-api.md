# Privacy Impact Assessment: Claude API Integration

**PIA Reference:** PIA-2026-001
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
| **PIA Reference** | PIA-2026-001 |
| **Project/System Name** | SENTINEL Claude API Integration |
| **Business Owner** | SENTINEL Platform Team |
| **Technical Owner** | SENTINEL Development Team |
| **Date Initiated** | 2025-06-01 |
| **PIA Prepared By** | SENTINEL Platform Team |
| **PIA Version** | 1.0 |

### 1.2 Purpose of Processing

SENTINEL integrates with Anthropic's Claude API to provide AI-powered building management assistance:

- **Primary purpose:** Enable natural language interactions with the BMS for equipment status queries, fault diagnosis, comfort complaint handling, and optimization recommendations
- **Secondary purposes:** Generate explanations for ML predictions, support technician decision-making
- **Business justification:** AI chat provides differentiated user experience and enables non-technical users to interact with complex building systems

### 1.3 Scope

- **Systems involved:** SENTINEL backend API (`/api/chat`, `/api/hybrid-chat`), Claude API (claude-sonnet-4-20250514 model)
- **Geographic scope:** Processing occurs in United States (Anthropic servers); data originates from South African building operations
- **Data subjects:** Building occupants, technicians, facilities managers
- **Timeframe:** Ongoing operational use

---

## Section 2: Data Inventory

### 2.1 Personal Information Categories

| Category | Description | Examples | Volume (Est.) | Sensitivity |
|----------|-------------|----------|---------------|-------------|
| Building Data | Building/site identifiers | "Sandton City Office Tower", "Site-002" | ~15 sites | Low |
| Zone Data | Zone and desk identifiers | "Level 2", "Zone A", "Desk 201" | ~100 zones | Low |
| Equipment Data | Equipment IDs and status | "S002-CHILLER-B1-001", "supply temp 14.2C" | ~500 equipment | Low |
| Comfort Complaints | Occupant comfort issues | "Too hot", "Stuffy", "Cold draft" | ~50/month | Low-Medium |
| Occupant Context | Contextual information | "Near window", "Close to diffuser" | Limited | Low |
| Technician Queries | Technical questions | "Why is chiller efficiency dropping?" | ~200/month | Low |

### 2.2 Special Personal Information

| Category | Processed? | Justification |
|----------|------------|---------------|
| Religious or philosophical beliefs | No | Not applicable to BMS operations |
| Race or ethnic origin | No | Not applicable to BMS operations |
| Trade union membership | No | Not applicable to BMS operations |
| Political persuasion | No | Not applicable to BMS operations |
| Health or sex life | No | Not applicable to BMS operations |
| Biometric information | No | Not collected or processed |
| Criminal behaviour | No | Not applicable to BMS operations |
| Children's information | No | Building occupants are adults in commercial settings |

### 2.3 Data Sources

| Source | Description | Lawful Basis |
|--------|-------------|--------------|
| User Chat Input | Natural language queries entered by users | Legitimate interest (building management) |
| BMS Context | Equipment status and readings injected into prompts | Legitimate interest (building management) |
| Desk/Zone Data | Location context for comfort complaints | Legitimate interest (building management) |

### 2.4 Data Retention

| Data Category | Retention Period | Justification | Destruction Method |
|---------------|------------------|---------------|--------------------|
| Chat Queries (in SENTINEL) | 30 days | Operational troubleshooting | Automated purge |
| Chat Queries (at Anthropic) | Not retained | Anthropic API does not retain data for training | Ephemeral processing |
| AI Responses | 30 days | Operational troubleshooting | Automated purge |

---

## Section 3: Necessity and Proportionality Assessment

### 3.1 Legal Basis for Processing (POPIA Section 11)

| Basis | Applicable? | Justification |
|-------|-------------|---------------|
| **Consent** (s11(1)(a)) | Yes (Secondary) | Cross-border transfer consent obtained via consent service |
| **Contract** (s11(1)(b)) | No | Not based on contract with data subjects |
| **Legal obligation** (s11(1)(c)) | No | Not required by law |
| **Legitimate interest** (s11(1)(d)) | Yes (Primary) | Pursuing legitimate interest in efficient building management; balanced against minimal data subject impact |
| **Public interest** (s11(1)(e)) | No | Not a public law duty |
| **Protection of legitimate interests** (s11(1)(f)) | No | Not applicable |

**Primary basis:** Legitimate interest (building management efficiency)
**Secondary basis:** Consent for cross-border transfer

### 3.2 Necessity Test

- [x] Is the processing necessary for the stated purpose? **Yes** - AI assistance requires sending queries to Claude API
- [x] Can the purpose be achieved with less data? **Yes, partially** - Queries are designed to minimise personal identifiers
- [x] Can the purpose be achieved with anonymised/pseudonymised data? **Yes** - Zone-level data used instead of individual identifiers
- [x] Is the data retained only for as long as necessary? **Yes** - Anthropic does not retain data; SENTINEL retains 30 days for troubleshooting

### 3.3 Proportionality Test

| Factor | Assessment |
|--------|------------|
| **Benefits to organisation** | Enhanced BMS usability, reduced training requirements, faster fault diagnosis |
| **Benefits to data subjects** | Better building comfort, faster complaint resolution, improved maintenance |
| **Potential harm to data subjects** | Minimal - no direct identifiers sent; zone-level data only; data processed ephemerally |
| **Overall proportionality** | **Proportionate** - Benefits outweigh minimal privacy impact |

---

## Section 4: Data Flow Diagram

### 4.1 Data Flow Overview

```
Building Occupant/Technician
           |
           v
    [SENTINEL Frontend]
           |
           | Chat query (may contain zone/desk/equipment references)
           v
    [SENTINEL Backend API]
           |
           | Prompt injection guard validates query
           | System prompt + BMS context added
           v
    [Anthropic Claude API] ----> [United States]
           |
           | AI response (ephemeral processing, not retained)
           v
    [SENTINEL Backend API]
           |
           | Response streamed back, logged for 30 days
           v
    [SENTINEL Frontend]
           |
           v
    Building Occupant/Technician
```

### 4.2 Data Flow Description

| Step | From | To | Data Elements | Transfer Method | Encryption |
|------|------|-----|--------------|-----------------|------------|
| 1 | User | SENTINEL Frontend | Chat query | HTTPS | Yes (TLS 1.3) |
| 2 | Frontend | SENTINEL Backend | Chat query | HTTPS | Yes (TLS 1.3) |
| 3 | Backend | Claude API | Prompt (query + context) | HTTPS | Yes (TLS 1.3) |
| 4 | Claude API | Backend | AI response | HTTPS | Yes (TLS 1.3) |
| 5 | Backend | Frontend | Streamed response | HTTPS (SSE) | Yes (TLS 1.3) |

### 4.3 Cross-Border Transfers

| Recipient | Country | Data Transferred | POPIA s72 Basis | Safeguards |
|-----------|---------|------------------|-----------------|------------|
| Anthropic (Claude API) | United States | Chat prompts containing zone/equipment data | s72(1)(a) adequate safeguards; s72(1)(b) consent | API data not retained for training; DPA with Anthropic; ephemeral processing |

---

## Section 5: Risk Assessment

### 5.1 Risk Identification

| Risk ID | Risk Description | Risk Category |
|---------|------------------|---------------|
| R1 | Personal identifiers included in chat queries (e.g., occupant names) | Confidentiality |
| R2 | Cross-border transfer exposes data to US jurisdiction | Confidentiality |
| R3 | Prompt injection attack extracts system information | Confidentiality |
| R4 | Anthropic retains or uses data for training | Confidentiality |
| R5 | Chat logs at SENTINEL compromised | Confidentiality |

### 5.2 Risk Assessment Table

| Risk ID | Likelihood | Impact | Score | Level | Risk Owner |
|---------|------------|--------|-------|-------|------------|
| R1 | 2 (Unlikely - system design prevents) | 3 (Significant) | 6 | Medium | Technical Owner |
| R2 | 4 (Likely - inherent in architecture) | 2 (Limited) | 8 | Medium | Information Security Officer |
| R3 | 2 (Unlikely - guard implemented) | 3 (Significant) | 6 | Medium | Technical Owner |
| R4 | 1 (Rare - Anthropic policy prohibits) | 3 (Significant) | 3 | Low | Information Security Officer |
| R5 | 2 (Unlikely - security controls in place) | 3 (Significant) | 6 | Medium | Technical Owner |

---

## Section 6: Mitigating Controls

### 6.1 Technical Controls

| Control ID | Control Description | Risk(s) Addressed | Implementation Status |
|------------|---------------------|-------------------|----------------------|
| TC1 | **Prompt injection guard** blocks sensitive data extraction attempts | R1, R3 | Implemented (`prompt_injection_guard.py`) |
| TC2 | **System prompt** instructs Claude not to request PII from users | R1 | Implemented |
| TC3 | **Zone-level data only** - no occupant names sent in queries | R1 | Implemented (design pattern) |
| TC4 | **TLS 1.3 encryption** for all data in transit | R2, R5 | Implemented |
| TC5 | **Ollama fallback** available for users who decline cross-border consent | R2 | Implemented (hybrid AI architecture) |
| TC6 | **30-day log retention** with automated purge | R5 | Implemented |
| TC7 | **Access controls** on SENTINEL systems (MFA for admins) | R5 | Implemented |

### 6.2 Organisational Controls

| Control ID | Control Description | Risk(s) Addressed | Implementation Status |
|------------|---------------------|-------------------|----------------------|
| OC1 | **Consent capture** for cross-border transfer before processing | R2 | Implemented (`consent_service.py`) |
| OC2 | **User training** on appropriate queries (no PII in chat) | R1 | Planned |
| OC3 | **Annual PIA review** to assess changing risks | All | Planned (this document) |
| OC4 | **Incident response process** for data breach handling | All | Implemented |

### 6.3 Contractual Controls

| Control ID | Control Description | Third Party | Status |
|------------|---------------------|-------------|--------|
| CC1 | **Anthropic API Terms** prohibit data retention for training | Anthropic | In place |
| CC2 | **Data Processing Agreement** with Anthropic | Anthropic | In place (API terms) |
| CC3 | **SOC 2 Type II certification** from Anthropic | Anthropic | Verified |

---

## Section 7: Residual Risk Evaluation

### 7.1 Residual Risk Assessment

| Risk ID | Original Score | Controls Applied | Residual Score | Residual Level | Acceptable? |
|---------|----------------|------------------|----------------|----------------|-------------|
| R1 | 6 (Medium) | TC1, TC2, TC3, OC2 | 2 | Low | Yes |
| R2 | 8 (Medium) | TC4, TC5, OC1 | 4 | Low | Yes |
| R3 | 6 (Medium) | TC1 | 2 | Low | Yes |
| R4 | 3 (Low) | CC1, CC2, CC3 | 1 | Low | Yes |
| R5 | 6 (Medium) | TC4, TC6, TC7 | 3 | Low | Yes |

### 7.2 Overall Residual Risk Rating

| Level | Criteria | This Assessment |
|-------|----------|-----------------|
| **LOW** | All residual risks are Low or Medium with effective controls | [x] |
| **MEDIUM** | Some High residual risks with mitigation plans in progress | [ ] |
| **HIGH** | Critical or multiple High residual risks without adequate mitigation | [ ] |

**Overall Residual Risk: LOW**

The combination of technical controls (prompt injection guard, zone-level data only, Ollama fallback), organisational controls (consent capture), and contractual controls (Anthropic's no-training policy) effectively mitigates the privacy risks of this cross-border data transfer.

---

## Section 8: POPIA Compliance Checklist

### 8.1 Conditions for Lawful Processing

| Condition | Requirement | Status | Evidence/Notes |
|-----------|-------------|--------|----------------|
| **1. Accountability** | Organisation takes responsibility for compliance | Met | This PIA; consent service; audit logging |
| **2. Processing Limitation** | Processing is lawful, adequate, relevant, not excessive | Met | Zone-level data only; no PII required |
| **3. Purpose Specification** | Personal information collected for specific, explicit, legitimate purpose | Met | Purpose: AI-assisted building management |
| **4. Further Processing Limitation** | Further processing compatible with original purpose | Met | Anthropic does not use data for other purposes |
| **5. Information Quality** | Information is complete, accurate, not misleading, updated | Met | Real-time BMS data; queries are user-generated |
| **6. Openness** | Privacy notice provided to data subjects | Met | Privacy notice in SENTINEL UI; consent capture |
| **7. Security Safeguards** | Appropriate technical and organisational measures | Met | TLS 1.3; prompt injection guard; access controls |
| **8. Data Subject Participation** | Data subjects can access, correct, delete their information | Met | 30-day retention; deletion on request |

### 8.2 Cross-Border Transfer Compliance (Section 72)

| Requirement | Status | Evidence |
|-------------|--------|----------|
| Transfer only to countries with adequate protection | Compliant | US: SOC 2 + Anthropic DPA provides adequate safeguards per s72(1)(a) |
| Binding corporate rules in place | N/A | Using consent and adequate safeguards instead |
| Data subject consent obtained | Compliant | `cross_border_transfer` consent type captured via consent service |
| Transfer necessary for contract performance | Compliant | AI chat is core service delivery |
| Transfer for benefit of data subject | Compliant | Improved building comfort and maintenance response |

---

## Section 9: Recommendations

### 9.1 Required Actions (Before Processing)

| Action | Priority | Responsible | Target Date | Status |
|--------|----------|-------------|-------------|--------|
| Verify Anthropic SOC 2 certification current | High | ISO | 2026-06-01 | Verified |
| Confirm consent service operational | High | Dev Team | 2025-06-01 | Complete |
| Test Ollama fallback for non-consenting users | High | Dev Team | 2025-06-01 | Complete |

### 9.2 Recommendations (To Improve Privacy)

| Recommendation | Rationale | Implementation Cost |
|----------------|-----------|---------------------|
| Implement query anonymisation layer | Further reduce any PI in queries before Claude API call | Medium |
| Add query audit sampling | Periodic review of query content for PII leakage | Low |
| Expand Ollama capabilities | Reduce reliance on cross-border Claude API | Medium |

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
| Compliance audit | Annually | 2027-02-05 |

**Triggers for immediate review:**
- Change in Claude API terms or data handling practices
- New data categories collected via chat
- Security incident involving Claude API
- Changes to POPIA requirements
- Significant increase in query volume

---

## Appendices

### Appendix A: Anthropic Data Handling Reference

**Anthropic API Data Use Policy (Summary):**
- API requests are not used to train Claude models
- Data processed ephemerally to generate responses
- Logs retained for up to 30 days for abuse prevention (configurable)
- SOC 2 Type II certified
- No third-party data sharing

**Reference:** [Anthropic Privacy Policy](https://www.anthropic.com/privacy)

### Appendix B: Prompt Injection Guard Patterns

The prompt injection guard (`backend/app/services/prompt_injection_guard.py`) blocks:
- System prompt extraction attempts (CRITICAL severity)
- Safety control bypass attempts (CRITICAL severity)
- Privilege escalation attempts (HIGH severity)
- Context manipulation attempts (MEDIUM severity)

### Appendix C: Version History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-02-05 | SENTINEL Platform Team | Initial PIA |

---

## References

| Document | Location |
|----------|----------|
| SENTINEL Third-Party Security Register | `docs/08-security/third-party-security-register.md` |
| SENTINEL Consent and Privacy Controls | `docs/08-security/consent-and-privacy.md` |
| Prompt Injection Guard | `backend/app/services/prompt_injection_guard.py` |
| Hybrid AI Service | `backend/app/services/hybrid_ai_service.py` |
| Anthropic Privacy Policy | https://www.anthropic.com/privacy |
| POPIA Section 72 | Cross-border transfer requirements |

---

*This PIA is maintained by the Information Security Officer. Annual review is mandatory, with triggered reviews on material changes to processing activities.*
