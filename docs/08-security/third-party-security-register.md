# SENTINEL Third-Party Security Register

**Document Owner:** Information Security Officer
**Version:** 1.0
**Effective Date:** 2026-02-04
**Review Cadence:** Register reviewed quarterly; full assessments annually
**FSR Reference:** Domain 4.16 -- Third Party Security
**Classification:** Confidential
**Status:** Active

---

## 1. Purpose

This register inventories and tracks the security posture of all third parties with access to SENTINEL systems or FSR client data. It documents data flows, security assessments, contractual agreements, risk ratings, and cross-border data transfers to satisfy FSR Domain 4.16 (Third Party Security) requirements and POPIA Section 72 (cross-border transfer) obligations.

---

## 2. Scope

This register covers all external service providers that:

- Host SENTINEL infrastructure or data
- Process, transmit, or have access to client (FSR) data
- Provide services that SENTINEL depends on for operation
- Receive personal information (PI) processed by SENTINEL

**Exclusions:** Self-hosted open-source software (Ollama, InfluxDB, Grafana/Loki, Wazuh) are not third parties as they run entirely within SENTINEL's own infrastructure. They are noted for completeness but do not require third-party security assessments.

---

## 3. Third-Party Register

### 3.1 Infrastructure Providers

| Provider | Service | Data Access | Classification | Location | Security Assessment | Agreement Date | Next Review | Risk Rating | Notes |
|----------|---------|-------------|----------------|----------|---------------------|----------------|-------------|-------------|-------|
| **Contabo** | VPS hosting | Full infrastructure access to all data (disk, network, memory) | Confidential | South Africa (JNB) / Germany (NUE) | ISO 27001 certified; SOC 2 Type II | 2025-01-01 | 2026-01-01 | **Medium** | Single VPS risk mitigated by daily snapshots and config-as-code rebuild procedure |
| **Cloudflare** | CDN, WAF, DNS, Tunnel (zero-trust networking) | Processes all inbound/outbound web traffic; terminates TLS | Confidential | Global (edge nodes); configurable geo-restrictions | SOC 2 Type II; ISO 27001; PCI DSS Level 1 | 2025-01-01 | 2026-01-01 | **Low** | Enterprise-grade security; no data persistence at edge; tunnel encrypts end-to-end |

### 3.2 AI and Data Processing Providers

| Provider | Service | Data Access | Classification | Location | Security Assessment | Agreement Date | Next Review | Risk Rating | Notes |
|----------|---------|-------------|----------------|----------|---------------------|----------------|-------------|-------------|-------|
| **Anthropic** | Claude API (AI chat, analysis, optimization) | Processes chat queries which may contain building data, occupant names, desk locations, comfort complaints | Confidential | **United States** (cross-border transfer) | SOC 2 Type II; responsible AI policy; API data not used for training | 2025-06-01 | 2026-06-01 | **Medium** | Cross-border transfer requires POPIA s72 assessment. Ollama fallback available. Data processed ephemerally (not retained). |
| **Supabase** | PostgreSQL database hosting | Stores all application data including PI (names, phone numbers, consent records, work orders, audit logs) | Restricted | AWS regions (configurable; af-south-1 preferred) | SOC 2 Type II; ISO 27001; HIPAA compliant | 2025-01-01 | 2026-01-01 | **Medium** | JSON file fallback mitigates availability risk. Data encrypted at rest (AES-256). |

### 3.3 Messaging Providers

| Provider | Service | Data Access | Classification | Location | Security Assessment | Agreement Date | Next Review | Risk Rating | Notes |
|----------|---------|-------------|----------------|----------|---------------------|----------------|-------------|-------------|-------|
| **Meta / WhatsApp** | WhatsApp Business API (occupant messaging) | Processes occupant phone numbers, names, and facilities request messages | Confidential | **Global** (Meta infrastructure; cross-border transfer) | WhatsApp Business API terms; end-to-end encryption for messages | 2025-09-01 | 2026-09-01 | **Medium** | Cross-border transfer requires POPIA s72 consent. Phone numbers are PI. Minimal data transferred -- only message content. |
| **Telegram** | Bot API (technician and occupant messaging via Clawd bot) | Processes occupant and technician phone numbers, names, and messages | Confidential | **Global** (Telegram infrastructure; cross-border transfer) | Telegram Bot API terms; client-server encryption (not E2E for bots) | 2025-09-01 | 2026-09-01 | **Medium** | Cross-border transfer requires POPIA s72 consent. Bot messages not end-to-end encrypted. Minimal data transferred. |

### 3.4 Business Application Providers

| Provider | Service | Data Access | Classification | Location | Security Assessment | Agreement Date | Next Review | Risk Rating | Notes |
|----------|---------|-------------|----------------|----------|---------------------|----------------|-------------|-------------|-------|
| **MRI Evolution / FSI** | CAFM Public API (work order management, asset data exchange) | Exchanges work orders, asset IDs, technician assignments, site data | Confidential | **South Africa** | FSI security assessment (vendor questionnaire) | 2025-01-01 | 2026-01-01 | **Low** | South African hosted; no cross-border transfer. SIMBIOT Concept Connector dormant until FSI API credentials configured. |
| **GitHub** | Source code hosting, CI/CD (GitHub Actions), security scanning (Dependabot, CodeQL) | Stores source code, CI/CD configuration, security scan results, dependency vulnerability reports | Confidential | **United States** (cross-border transfer) | SOC 2 Type II; ISO 27001; FedRAMP authorized | 2025-01-01 | 2026-01-01 | **Low** | No PI in source code. Security scan results may contain vulnerability information. Private repositories with branch protection. |

### 3.5 Self-Hosted Components (Not Third Parties)

These components run entirely within SENTINEL-controlled infrastructure. No data leaves the VPS. Listed for completeness.

| Component | Purpose | Data Access | Hosting | Third-Party Risk |
|-----------|---------|-------------|---------|-----------------|
| **Ollama** | Local LLM (AI fallback) | Processes same queries as Claude API | Self-hosted on Contabo VPS | None (no external network calls) |
| **InfluxDB** | Time-series database (telemetry) | Stores sensor readings, trend data | Self-hosted Docker container | None |
| **Grafana / Loki / Promtail** | Centralised logging and dashboards | Stores application logs | Self-hosted Docker containers | None |
| **Wazuh** | Intrusion detection system (IDS/SIEM) | Reads system and application logs | Self-hosted Docker container | None |

---

## 4. Third-Party Management Framework

### 4.1 Onboarding New Third Parties

Before granting any third party access to SENTINEL systems or FSR data:

1. **Security assessment:** Complete vendor security questionnaire covering:
   - Data protection certifications (ISO 27001, SOC 2, etc.)
   - Encryption at rest and in transit
   - Access control mechanisms
   - Incident response capabilities
   - Sub-processor disclosure
   - Data retention and deletion policies
2. **Data classification review:** Determine what data the third party will access; classify per SENTINEL data classification scheme
3. **POPIA assessment:** If PI is processed, assess compliance with POPIA requirements including cross-border transfer obligations (Section 72)
4. **Contractual requirements:** Execute DPA (Data Processing Agreement) or equivalent covering:
   - Purpose limitation
   - Security obligations
   - Breach notification requirements (within 72 hours)
   - Data return and destruction on termination
   - Audit rights
5. **Risk rating:** Assign initial risk rating (Low / Medium / High / Critical)
6. **Register entry:** Add to this register with all required fields
7. **Approval:** Information Security Officer approves onboarding

### 4.2 Ongoing Monitoring

| Activity | Frequency | Responsibility |
|----------|-----------|----------------|
| Register review | Quarterly | Information Security Officer |
| Full security assessment | Annually | Information Security Officer |
| Certification verification | On renewal | Information Security Officer |
| Breach monitoring | Continuous | Security monitoring (automated alerts) |
| Dependency updates | Monthly | Development team (Dependabot/Trivy) |
| SLA performance review | Quarterly | Operations team |

### 4.3 Offboarding Third Parties

When a third-party relationship ends:

1. **Access revocation:** Immediately revoke all API keys, credentials, and access permissions
2. **Data return:** Request return of all SENTINEL/FSR data in machine-readable format
3. **Data deletion confirmation:** Obtain written confirmation of data deletion from provider
4. **Destruction certificate:** Request formal destruction certificate for any PI processed
5. **Register update:** Update this register with termination date and final status
6. **Audit log:** Record offboarding in SENTINEL audit trail

### 4.4 Non-Compliance Handling

If a third party fails to meet security requirements:

| Severity | Trigger | Action | Timeline |
|----------|---------|--------|----------|
| **Low** | Minor policy deviation; no data exposure | Notify provider; request remediation plan | 30 days to remediate |
| **Medium** | Certification lapse; delayed security updates | Escalate to ISO; formal remediation request | 14 days to remediate |
| **High** | Data breach; significant security failure | Suspend data sharing; notify FSR; assess impact | Immediate suspension; 7-day assessment |
| **Critical** | Confirmed PI breach; refusal to remediate | Terminate relationship; invoke BCP fallback | Immediate termination |

---

## 5. Cross-Border Data Flow Register

All transfers of personal information outside South Africa, as required by POPIA Section 72.

### 5.1 Cross-Border Transfer Summary

| Provider | Destination | Data Transferred | Legal Basis (POPIA s72) | Safeguards | Risk Mitigation |
|----------|------------|-----------------|------------------------|------------|-----------------|
| **Anthropic (Claude API)** | United States | Chat messages containing building data, occupant names, desk locations, comfort complaints | Section 72(1)(a): adequate safeguards via DPA; Section 72(1)(b): consent obtained | DPA with Anthropic; API data not retained for training; ephemeral processing | Ollama local fallback eliminates cross-border transfer; data subjects who decline consent still receive service via Ollama; anonymise/pseudonymise where possible before transfer |
| **Meta (WhatsApp)** | Global (Meta infrastructure) | Phone numbers, message content (facilities requests) | Section 72(1)(b): consent; Section 72(1)(d): necessary for service delivery | WhatsApp Business API terms; end-to-end encryption for messages | Consent captured via consent service before processing; minimal data transferred; no bulk PI export |
| **Telegram** | Global (Telegram infrastructure) | Phone numbers, message content (technician queries) | Section 72(1)(b): consent; Section 72(1)(d): necessary for service delivery | Telegram Bot API terms; client-server encryption | Consent captured via consent service before processing; minimal data transferred; no bulk PI export |
| **GitHub** | United States | Source code, security scan results | Section 72(1)(a): adequate safeguards (SOC 2, ISO 27001) | No PI in source code; private repositories; 2FA enforced | Security scans may contain vulnerability info but no PI; branch protection rules |

### 5.2 POPIA Section 72 Adequacy Assessment

For each cross-border transfer, the following conditions are assessed:

| Condition (s72) | Claude API | WhatsApp | Telegram | GitHub |
|----------------|-----------|----------|----------|--------|
| **(a)** Adequate protection in recipient country | Yes (US: SOC 2 + DPA) | N/A (consent-based) | N/A (consent-based) | Yes (US: SOC 2 + ISO 27001) |
| **(b)** Data subject consents | Yes (cross_border_transfer consent type) | Yes (PI processing consent) | Yes (PI processing consent) | N/A (no PI) |
| **(c)** Necessary for contract performance | Yes (AI chat service) | Yes (messaging service) | Yes (messaging service) | No |
| **(d)** For benefit of data subject | Yes (building management) | Yes (facilities requests) | Yes (technician support) | No |
| **(e)** Binding corporate rules | N/A | N/A | N/A | N/A |

---

## 6. FSR Notification Requirements

### 6.1 Prompt Notification Obligations

SENTINEL must promptly notify the FSR client of:

- Any confirmed data breach affecting FSR data
- Any third-party security incident that may affect FSR data
- Any change in third-party sub-processors that process FSR data
- Any failure to meet contractual security requirements
- Any cross-border transfer not previously disclosed

### 6.2 Notification Timeline

| Event | Notification Timeline | Recipient |
|-------|----------------------|-----------|
| Confirmed data breach | Within 72 hours | FSR client + Information Regulator (POPIA s22) |
| Third-party security incident | Within 48 hours | FSR client |
| Sub-processor change | 30 days prior notice | FSR client |
| Security requirement failure | Within 7 days | FSR client |
| New cross-border transfer | Before activation | FSR client |

---

## 7. Document Control

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-02-04 | SENTINEL Platform Team | Initial register creation |

**Review schedule:**
- Register reviewed quarterly (provider status, risk ratings, compliance)
- Full security assessments conducted annually
- Cross-border data flow register updated on any new international transfer
- Triggered review on: provider breach, certification lapse, new provider onboarding, contract termination

---

## 8. References

| Document | Location |
|----------|----------|
| Data Privacy Policy | `docs/08-security/data-privacy-policy.md` |
| Consent and Privacy Controls | `docs/08-security/consent-and-privacy.md` |
| Business Continuity Policy | `docs/08-security/business-continuity-policy.md` |
| Access Control Implementation | `docs/08-security/access-control-implementation.md` |
| Vulnerability Management | `docs/08-security/vulnerability-management.md` |
| SIMBIOT Concept Connector | `docs/07-integrations/simbiot-concept-connector.md` |
| POPIA | Protection of Personal Information Act, 2013 |
| ISO 27001:2022 | Information Security Management Systems |

---

*This register is maintained by the Information Security Officer. Quarterly reviews and annual full assessments are mandatory for FSR compliance.*
