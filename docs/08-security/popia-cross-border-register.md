# POPIA Section 72 Cross-Border Transfer Register

**Document Owner:** Information Security Officer
**Version:** 1.0
**Effective Date:** 2026-02-05
**Review Cadence:** Quarterly or when new transfers added
**FSR Reference:** Domain 4.3 -- Information Classification & Data Privacy
**Classification:** Confidential
**Status:** Active

---

## 1. Purpose

This register documents all transfers of personal information (PI) outside the Republic of South Africa as required by the Protection of Personal Information Act (POPIA) Section 72. It tracks compliance status, legal basis, safeguards, and ongoing monitoring requirements for each cross-border data flow.

---

## 2. Regulatory Background

### 2.1 POPIA Section 72 Requirements

Section 72 of POPIA prohibits transfer of PI to a third party in a foreign country unless one of the following conditions is satisfied:

| Condition | Section | Description |
|-----------|---------|-------------|
| **Adequate Protection** | s72(1)(a) | Recipient country provides adequate level of protection (laws, binding corporate rules) |
| **Data Subject Consent** | s72(1)(b) | Data subject has consented to the proposed transfer |
| **Contract Performance** | s72(1)(c) | Transfer is necessary for performance of contract between data subject and responsible party |
| **Pre-contractual Measures** | s72(1)(d) | Transfer is necessary for conclusion of contract in interest of data subject |
| **Benefit of Data Subject** | s72(1)(e) | Transfer is for benefit of data subject, and obtaining consent not reasonably practicable |

### 2.2 Compliance Approach

SENTINEL relies primarily on:
1. **s72(1)(a)** - Adequate safeguards via contracts, certifications (SOC 2, ISO 27001), and DPAs
2. **s72(1)(b)** - Data subject consent obtained via SENTINEL consent service
3. **s72(1)(c)(d)** - Transfer necessary for service delivery (contract/legitimate interest)

---

## 3. Cross-Border Transfer Register

### 3.1 Summary Table

| Recipient | Country | Data Categories | PI Elements | Legal Basis | Safeguards | PIA Reference | Compliance Status |
|-----------|---------|-----------------|-------------|-------------|------------|---------------|-------------------|
| **Anthropic (Claude API)** | USA | Chat queries | Zone names, equipment IDs, comfort complaints | s72(1)(a) + s72(1)(b) | SOC 2 Type II; no data retention for training; DPA | PIA-2026-001 | **Compliant** |
| **Meta (WhatsApp Business API)** | USA / Ireland | Work orders | Technician names, phone numbers, work order details | s72(1)(b) + s72(1)(d) | E2E encryption; WhatsApp Business Terms | PIA-2026-002 | **Compliant** |
| **Telegram (Bot API)** | UAE / Netherlands / Singapore | Work orders | Technician names, phone numbers, Telegram IDs, work order details | s72(1)(b) + s72(1)(d) | Client-server encryption; Telegram Terms | PIA-2026-002 | **Compliant** |
| **Contabo (VPS Hosting)** | Germany | All system data | Building data, equipment data, anonymised analytics | s72(1)(a) | ISO 27001; SOC 2 Type II; EU adequacy decision | N/A (infrastructure) | **Compliant** |
| **GitHub** | USA | Source code | No PI (code only) | s72(1)(a) | SOC 2 Type II; ISO 27001; FedRAMP | N/A (no PI) | **Compliant** |
| **Supabase** | AWS (configurable) | Database content | Names, phone numbers, consent records, audit logs | s72(1)(a) | SOC 2 Type II; ISO 27001; af-south-1 preferred | N/A (SA hosting preferred) | **Compliant** |

### 3.2 Detailed Transfer Records

#### 3.2.1 Anthropic (Claude API)

| Field | Details |
|-------|---------|
| **Recipient** | Anthropic, PBC |
| **Service** | Claude API (claude-sonnet-4-20250514 model) |
| **Destination Country** | United States |
| **PI Transferred** | Zone names, equipment IDs, desk references, comfort complaint descriptions |
| **Data Subjects** | Building occupants, technicians, facilities managers |
| **Volume** | ~500 chat queries/month |
| **Legal Basis** | s72(1)(a): Adequate safeguards via SOC 2 + DPA; s72(1)(b): Consent |
| **Safeguards** | SOC 2 Type II certification; API data not retained for training; ephemeral processing; prompt injection guard |
| **Consent Mechanism** | `cross_border_transfer` consent type captured via SENTINEL consent service |
| **Fallback** | Ollama local LLM available for users who decline consent |
| **PIA Reference** | `docs/08-security/pia-claude-api.md` (PIA-2026-001) |
| **Residual Risk** | LOW |
| **Next Review** | 2027-02-05 |

#### 3.2.2 Meta (WhatsApp Business API)

| Field | Details |
|-------|---------|
| **Recipient** | Meta Platforms, Inc. / WhatsApp LLC |
| **Service** | WhatsApp Business API (Clawd bot integration) |
| **Destination Country** | United States / Ireland |
| **PI Transferred** | Technician names, phone numbers, work order details |
| **Data Subjects** | Building technicians |
| **Volume** | ~20 active technicians; ~100 work order messages/month |
| **Legal Basis** | s72(1)(b): Consent; s72(1)(d): Necessary for service delivery |
| **Safeguards** | End-to-end encryption; WhatsApp Business Terms; GDPR compliance (Ireland) |
| **Consent Mechanism** | Technician onboarding consent; `PI_processing` consent type |
| **PIA Reference** | `docs/08-security/pia-clawd-messaging.md` (PIA-2026-002) |
| **Residual Risk** | MEDIUM |
| **Next Review** | 2027-02-05 |

#### 3.2.3 Telegram (Bot API)

| Field | Details |
|-------|---------|
| **Recipient** | Telegram FZ-LLC |
| **Service** | Telegram Bot API (Clawd bot integration) |
| **Destination Country** | UAE (Dubai) / Netherlands / Singapore |
| **PI Transferred** | Technician names, phone numbers, Telegram user IDs, work order details |
| **Data Subjects** | Building technicians |
| **Volume** | ~20 active technicians; ~100 work order messages/month |
| **Legal Basis** | s72(1)(b): Consent; s72(1)(d): Necessary for service delivery |
| **Safeguards** | Client-server encryption (note: not E2E for bots); Telegram Terms |
| **Consent Mechanism** | Technician onboarding consent; `PI_processing` consent type |
| **PIA Reference** | `docs/08-security/pia-clawd-messaging.md` (PIA-2026-002) |
| **Residual Risk** | MEDIUM |
| **Next Review** | 2027-02-05 |

#### 3.2.4 Contabo (VPS Hosting)

| Field | Details |
|-------|---------|
| **Recipient** | Contabo GmbH |
| **Service** | Virtual Private Server hosting |
| **Destination Country** | South Africa (JNB) / Germany (NUE fallback) |
| **PI Transferred** | All SENTINEL data (stored on VPS) |
| **Data Subjects** | All SENTINEL users |
| **Legal Basis** | s72(1)(a): EU adequacy decision for Germany; South African node preferred |
| **Safeguards** | ISO 27001; SOC 2 Type II; encrypted disks; daily snapshots |
| **PIA Reference** | N/A (infrastructure provider, covered by Third-Party Security Register) |
| **Residual Risk** | LOW |
| **Next Review** | 2026-01-01 |

#### 3.2.5 GitHub

| Field | Details |
|-------|---------|
| **Recipient** | GitHub, Inc. (Microsoft) |
| **Service** | Source code hosting, CI/CD, security scanning |
| **Destination Country** | United States |
| **PI Transferred** | None (source code only, no PI in codebase) |
| **Data Subjects** | N/A |
| **Legal Basis** | s72(1)(a): Adequate safeguards |
| **Safeguards** | SOC 2 Type II; ISO 27001; FedRAMP; private repositories; 2FA enforced |
| **PIA Reference** | N/A (no PI processed) |
| **Residual Risk** | LOW |
| **Next Review** | 2026-01-01 |

#### 3.2.6 Supabase

| Field | Details |
|-------|---------|
| **Recipient** | Supabase, Inc. |
| **Service** | PostgreSQL database hosting |
| **Destination Country** | AWS (af-south-1 Cape Town preferred; other regions configurable) |
| **PI Transferred** | User data, consent records, work orders, technician details, audit logs |
| **Data Subjects** | All SENTINEL users |
| **Legal Basis** | s72(1)(a): SOC 2 + DPA; af-south-1 keeps data in South Africa |
| **Safeguards** | SOC 2 Type II; ISO 27001; HIPAA; AES-256 encryption at rest |
| **PIA Reference** | N/A (South African hosting preferred; JSON fallback available) |
| **Residual Risk** | LOW |
| **Next Review** | 2026-01-01 |

---

## 4. Adequacy Assessment Summary

### 4.1 Countries and Adequacy Status

| Country | Adequacy Status | Basis |
|---------|-----------------|-------|
| **Germany** | Adequate | EU member state; GDPR applies |
| **Ireland** | Adequate | EU member state; GDPR applies |
| **Netherlands** | Adequate | EU member state; GDPR applies |
| **United States** | Conditional | Requires additional safeguards (SOC 2, DPA, consent) |
| **UAE** | Conditional | Requires additional safeguards (consent, encryption) |
| **Singapore** | Conditional | PDPA provides reasonable protection; additional consent |

### 4.2 Safeguards by Transfer Type

| Safeguard | Anthropic | WhatsApp | Telegram | Contabo | GitHub | Supabase |
|-----------|-----------|----------|----------|---------|--------|----------|
| SOC 2 Type II | Yes | Via Meta | - | Yes | Yes | Yes |
| ISO 27001 | - | Via Meta | - | Yes | Yes | Yes |
| DPA in place | Yes (API terms) | Yes (Terms) | Yes (Terms) | Yes | Yes | Yes |
| E2E Encryption | N/A | Yes | No (bots) | N/A | N/A | At rest |
| TLS in Transit | Yes | Yes | Yes | Yes | Yes | Yes |
| Consent obtained | Yes | Yes | Yes | N/A | N/A | N/A |

---

## 5. Consent Management

### 5.1 Consent Types and Coverage

| Transfer | Consent Type | Capture Mechanism | Revocation Process |
|----------|--------------|-------------------|-------------------|
| Claude API | `cross_border_transfer` | SENTINEL consent service | Automatic fallback to Ollama |
| WhatsApp | `PI_processing` | Technician onboarding | Disable WhatsApp channel |
| Telegram | `PI_processing` | Technician onboarding | Disable Telegram channel |

### 5.2 Consent Withdrawal Impact

| Transfer | Impact of Withdrawal |
|----------|---------------------|
| Claude API | User receives Ollama-only AI responses (reduced capability) |
| WhatsApp | Technician receives SMS or email notifications instead |
| Telegram | Technician receives SMS or email notifications instead |

---

## 6. Incident Response for Cross-Border Transfers

### 6.1 Breach Notification Requirements

| Event | Notification Timeline | Recipients |
|-------|----------------------|------------|
| Confirmed PI breach at recipient | Within 72 hours | Information Regulator (POPIA s22), affected data subjects, FSR client |
| Suspected breach | Within 24 hours | ISO for assessment |
| Recipient notification of breach | Within 48 hours | FSR client |

### 6.2 Transfer Suspension Triggers

Suspend cross-border transfer immediately if:
- Confirmed data breach at recipient
- Recipient loses SOC 2 or equivalent certification
- Significant change in recipient's privacy policy
- Recipient refuses audit or information request
- Regulatory guidance advises against transfer

---

## 7. Monitoring and Review

### 7.1 Review Schedule

| Activity | Frequency | Responsible |
|----------|-----------|-------------|
| Register review | Quarterly | Information Security Officer |
| Recipient certification verification | Annually | Information Security Officer |
| PIA updates | Annually (or on change) | Information Security Officer |
| Consent mechanism audit | Bi-annually | Compliance team |
| Transfer volume monitoring | Monthly | Operations team |

### 7.2 Key Performance Indicators

| Metric | Target | Current |
|--------|--------|---------|
| Transfers with valid legal basis | 100% | 100% |
| Transfers with documented PIA | 100% (where required) | 100% |
| Consent capture rate (where required) | > 95% | TBD |
| Recipient certifications current | 100% | 100% |

---

## 8. Document Control

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-02-05 | SENTINEL Platform Team | Initial register creation |

---

## 9. References

| Document | Location |
|----------|----------|
| POPIA (Protection of Personal Information Act, 2013) | Government Gazette |
| PIA Template | `docs/08-security/privacy-impact-assessment-template.md` |
| PIA: Claude API | `docs/08-security/pia-claude-api.md` |
| PIA: Clawd Messaging | `docs/08-security/pia-clawd-messaging.md` |
| Third-Party Security Register | `docs/08-security/third-party-security-register.md` |
| Consent and Privacy Controls | `docs/08-security/consent-and-privacy.md` |
| Data Privacy Policy | `docs/08-security/data-privacy-policy.md` |

---

*This register is maintained by the Information Security Officer. Quarterly reviews are mandatory for FSR compliance. Any new cross-border transfer must be assessed and added before activation.*
