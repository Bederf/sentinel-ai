---
title: "Information Classification Policy"
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

# Information Classification Policy

**Document:** SENTINEL BMS Platform - Information Classification Policy
**Document ID:** SENT-POL-IC-001
**FSR Domain:** 4.3 - Information Classification (current 3.5, target 4.0)
**Version:** 1.0
**Effective Date:** 2026-02-04
**Owner:** Information Security Officer
**Review Cadence:** Annual (next review: 2027-02-04)
**Classification:** Internal

---

## 1. Purpose

This policy defines how all information assets created, processed, stored, or transmitted by the SENTINEL BMS Intelligence Platform must be classified and handled. It ensures that data is protected at a level appropriate to its sensitivity and business value, in compliance with the Protection of Personal Information Act (POPIA), the FirstRand Group (FSR) Privacy and Service Risk Assessment requirements, and industry best practices.

## 2. Scope

This policy applies to:

- All data processed, stored, or transmitted by SENTINEL platform components
- All SENTINEL personnel, contractors, and third parties with access to SENTINEL data
- All infrastructure hosting SENTINEL services (Contabo VPS, Docker containers, Supabase, InfluxDB)
- All external integrations (Claude API, WhatsApp/Telegram, MRI Evolution FSI API, Cloudflare)
- All documentation, source code, configuration files, and operational artefacts

## 3. Regulatory Framework

| Regulation | Relevance |
|---|---|
| POPIA (Act 4 of 2013) | Protection of personal information processed by SENTINEL |
| POPIA Section 72 | Cross-border transfer controls for Claude API data flows |
| FSR Privacy and Service Risk Assessment V8 | FirstRand supplier assessment (Domain 4.3) |
| ISO 27001:2022 Annex A.5.12-5.13 | Classification and labelling of information |

---

## 4. Classification Categories

SENTINEL uses four classification levels. All information must be assigned to one of these levels.

### 4.1 Public

**Definition:** Information explicitly approved for unrestricted distribution. Disclosure carries no risk to SENTINEL, its clients, or data subjects.

**Examples:**
- Published API documentation (OpenAPI specs at `/docs`)
- Open-source component attributions
- Marketing materials and product brochures
- Published blog posts and case studies
- SENTINEL feature descriptions for public websites

### 4.2 Internal

**Definition:** Information intended for use within SENTINEL operations and authorised client personnel. Disclosure would not cause significant harm but is not intended for public distribution.

**Examples:**
- BMS telemetry data (temperature, pressure, humidity readings)
- Aggregated analytics and KPI dashboards
- Equipment metadata (make, model, location, capacity)
- System architecture documentation
- Non-sensitive operational procedures
- ML model performance metrics (accuracy, c-index)
- Aggregated energy consumption data
- Zone mapping and floor plan configurations

### 4.3 Confidential

**Definition:** Information that, if disclosed, could cause material harm to SENTINEL, its clients, or business operations. Access restricted to individuals with a documented business need.

**Examples:**
- Work orders and maintenance records
- AI failure predictions and anomaly data
- Financial data (contract values, cost analyses, profitability metrics)
- SLA terms and penalty calculations
- Audit logs and security event records
- Detailed building operational patterns
- Client-specific configuration and integration settings
- Business continuity and disaster recovery plans
- Incident reports and investigation records
- Vulnerability assessment results
- Third-party security assessments

### 4.4 Restricted

**Definition:** Information of the highest sensitivity. Unauthorised disclosure could cause severe harm to individuals (POPIA subjects), critical business damage, or regulatory penalties. Access strictly limited and individually authorised.

**Examples:**
- Occupant personal information (phone numbers, names, locations captured via WhatsApp/Telegram)
- Technician personal identifiers (synced from MRI Evolution)
- API credentials, encryption keys, and service account tokens
- SSH private keys and 2FA seed values
- Database connection strings and service passwords
- ML model training data containing personal information
- POPIA consent records
- Security audit findings with exploitable detail
- Break-glass emergency credentials
- Supabase service role keys

---

## 5. Handling Requirements

### 5.1 Storage

| Classification | Encryption at Rest | Storage Location | Access Control |
|---|---|---|---|
| Public | Not required | Any approved storage | No restrictions |
| Internal | Recommended (AES-256) | SENTINEL infrastructure only | Role-based (Auditor and above) |
| Confidential | Required (AES-256) | Encrypted volumes, Supabase with RLS | Role-based (Operator and above for writes) |
| Restricted | Required (AES-256) | Encrypted secrets manager, environment variables | Named individuals only, Admin role |

**SENTINEL-specific storage requirements:**

- **API credentials:** Stored in `.env` files with 600 permissions, never committed to source control. Pre-commit hooks (Phase 63-03) block hardcoded credentials.
- **Database credentials:** Stored in environment variables within Docker Compose, never in application code.
- **Occupant PI:** Stored in Supabase with Row Level Security (RLS) policies enforcing tenant isolation.
- **SSH keys:** Ed25519 format, stored in `~/.ssh/` with 600 permissions, passphrase protected.
- **Audit logs:** Stored in separate logging infrastructure (Loki), tamper-evident with timestamp verification.

### 5.2 Transmission

| Classification | Encryption in Transit | Approved Channels |
|---|---|---|
| Public | Recommended (HTTPS) | Any channel |
| Internal | Required (TLS 1.2+) | SENTINEL APIs, secured email |
| Confidential | Required (TLS 1.2+) | SENTINEL APIs, encrypted email, Cloudflare Tunnel |
| Restricted | Required (TLS 1.2+ with certificate pinning) | SENTINEL APIs via Cloudflare Tunnel, encrypted email with recipient verification |

**SENTINEL-specific transmission requirements:**

- **All API traffic:** TLS 1.2+ enforced via Cloudflare Tunnel (no exposed ports)
- **SSH sessions:** ChaCha20-Poly1305 or AES-256-GCM ciphers only (configured in `infrastructure/ssh/sshd_hardening.conf`)
- **FSI API calls:** Certificate pinning to MRI Evolution gateway
- **Claude API calls:** TLS 1.3 to Anthropic endpoints (see Section 8 for cross-border controls)
- **BMS protocols:** BACnet/IP secured within building network segments; Modbus TCP within OT network perimeter

### 5.3 Access

| Classification | Access Requirement | RBAC Role Minimum | Approval |
|---|---|---|---|
| Public | None | None (PUBLIC endpoints) | None |
| Internal | Authentication required | Auditor (Level 1) | Automatic with role assignment |
| Confidential | Authentication + authorisation | Operator (Level 2) for writes, Auditor for reads | Manager approval for role assignment |
| Restricted | Authentication + authorisation + individual grant | Admin (Level 4) | CTO/CISO approval, documented justification |

**Reference:** RBAC model implemented in `backend/app/models/auth.py` with four roles: Auditor, Operator, Developer, Admin. Auth middleware enforces endpoint classification per `backend/app/middleware/auth_middleware.py`.

### 5.4 Retention

| Classification | Retention Period | Review Trigger |
|---|---|---|
| Public | Indefinite | Annual relevance review |
| Internal | 2 years from last use | Annual review |
| Confidential | As per contractual obligations (typically 2-5 years) | Contract expiry + 1 year |
| Restricted | Minimum required by regulation; delete when no longer needed | Quarterly review |

**SENTINEL-specific retention:**

| Data Type | Retention | Justification |
|---|---|---|
| Raw BMS telemetry | 90 days | Operational analysis window |
| Aggregated analytics | 2 years | Trend analysis and ML training |
| Work orders | Duration of client contract + 1 year | Contractual obligation |
| Audit logs | 3 years | FSR compliance and forensic capability |
| Occupant PI | Until consent withdrawn or 1 year after last interaction | POPIA Section 14 |
| API credentials | Until rotated (max 90 days for API keys, annual for service accounts) | Security best practice |
| ML training data | Duration of model lifecycle | Model reproducibility |
| Consent records | 5 years after last consent action | POPIA evidence requirement |

### 5.5 Disposal

| Classification | Disposal Method | Verification |
|---|---|---|
| Public | Standard deletion | None required |
| Internal | Secure deletion (overwrite) | Deletion confirmation log |
| Confidential | Cryptographic erasure or secure overwrite (3-pass) | Disposal certificate generated |
| Restricted | Cryptographic key destruction + secure overwrite | Disposal certificate with witness sign-off |

**SENTINEL-specific disposal:**

- **Database records:** `DELETE` with WAL truncation; for Restricted data, key rotation renders encrypted data unrecoverable.
- **VM snapshots:** Secure deletion via Contabo API with confirmation receipt.
- **Container images:** `docker rmi` with registry cleanup; no Restricted data in images.
- **Log files:** Automated rotation with secure deletion of rotated logs.
- **Physical media:** Not applicable (cloud-hosted); if any physical media is used, NIST SP 800-88 guidelines apply.

### 5.6 Labelling

| Classification | Labelling Requirement |
|---|---|
| Public | No label required |
| Internal | `Classification: Internal` in document header or metadata |
| Confidential | `Classification: Confidential` in document header, footer, and metadata |
| Restricted | `Classification: RESTRICTED` in document header, footer, metadata, and filename suffix `_RESTRICTED` |

**Digital labelling:**

- **Documents:** Classification in header/footer (this document is labelled `Classification: Internal`)
- **API responses:** PII guard middleware (`backend/app/middleware/pii_guard.py`) redacts Restricted data before LLM processing
- **Database tables:** Table-level comments indicating maximum classification level stored
- **Source code files:** No classification label needed (code itself is Internal; secrets are never in code)
- **Email:** Classification in subject line prefix for Confidential and Restricted

---

## 6. SENTINEL Data Type Classification Map

| Data Type | Classification | POPIA Category | Justification |
|---|---|---|---|
| **BMS sensor readings** (temperature, pressure, humidity) | Internal | N/A | Operational data with no personal information |
| **Occupancy patterns** (zone-level counts) | Internal | N/A | Aggregated, no individual identification |
| **Equipment metadata** (make, model, capacity, location) | Internal | N/A | Asset register data |
| **Aggregated energy data** (kWh by building/zone) | Internal | N/A | Operational analytics |
| **ML model metrics** (accuracy, predictions per equipment type) | Internal | N/A | Algorithm performance data |
| **Zone/floor plans** | Internal | N/A | Building configuration |
| **Work orders** | Confidential | Juristic person information | Contains client operational details |
| **Maintenance records** | Confidential | Juristic person information | Operational intelligence about client assets |
| **AI failure predictions** | Confidential | N/A | Could reveal operational vulnerabilities |
| **Anomaly detection results** | Confidential | N/A | Security-sensitive operational intelligence |
| **Financial data** (contract values, SLAs, profitability) | Confidential | Juristic person information | Commercial sensitivity |
| **Audit logs** | Confidential | May contain PI references | Security and compliance records |
| **Building operational patterns** | Confidential | N/A | Could reveal security-relevant patterns |
| **Client configuration** | Confidential | N/A | Integration settings, BMS connection details |
| **Incident reports** | Confidential | May contain PI references | Security investigation records |
| **Vulnerability scan results** | Confidential | N/A | Exploitable security information |
| **Occupant phone numbers** (WhatsApp/Telegram) | Restricted | Personal information (POPIA S1) | Direct personal identifier |
| **Occupant names and locations** | Restricted | Personal information (POPIA S1) | Direct personal identifier linked to physical location |
| **Technician identifiers** (from MRI Evolution) | Restricted | Personal information (POPIA S1) | Employee/contractor personal data |
| **API credentials** (Anthropic, FSI, Supabase keys) | Restricted | N/A | Critical security asset |
| **SSH private keys** | Restricted | N/A | Critical security asset |
| **Encryption keys** | Restricted | N/A | Cryptographic material |
| **Service account tokens** (`sent_sk_*` API keys) | Restricted | N/A | Critical security asset |
| **Database connection strings** | Restricted | N/A | Infrastructure access credentials |
| **2FA seed values** | Restricted | N/A | Authentication secret |
| **ML training data with PI** | Restricted | Personal information (POPIA S1) | Training data derived from personal information |
| **POPIA consent records** | Restricted | Personal information (POPIA S1) | Legal compliance evidence |
| **Break-glass credentials** | Restricted | N/A | Emergency access credentials |

---

## 7. Cross-Border Data Transfer

### 7.1 Overview

SENTINEL processes data primarily within South Africa. However, certain integrations involve cross-border data transfer, which must comply with POPIA Section 72.

### 7.2 Claude API (Anthropic) - US Processing

| Aspect | Detail |
|---|---|
| **Data transferred** | Chat queries, equipment context, BMS telemetry summaries |
| **Classification of transferred data** | Internal (telemetry), Confidential (work order context) |
| **Destination** | United States (Anthropic infrastructure) |
| **Legal basis (POPIA S72)** | Section 72(1)(a): Adequate level of protection via contractual safeguards |
| **Safeguards** | Anthropic Terms of Service prohibit training on API data; TLS 1.3 in transit; data not retained beyond request processing |
| **PI mitigation** | PII guard middleware (`backend/app/middleware/pii_guard.py`) redacts SA ID numbers, phone numbers, and email addresses before Claude API submission |
| **Review** | Annual review of Anthropic data processing practices |

**Prohibited transfers to Claude API:**
- Restricted data (occupant PI, credentials, keys) -- NEVER sent to Claude
- Unredacted personal information
- Raw POPIA consent records

### 7.3 WhatsApp (Meta) - International Processing

| Aspect | Detail |
|---|---|
| **Data transferred** | Message content, phone numbers, timestamps |
| **Classification** | Restricted (phone numbers), Confidential (message content) |
| **Destination** | Meta infrastructure (US/EU/Singapore) |
| **Legal basis (POPIA S72)** | Section 72(1)(b): Consent of data subject (captured at bot registration) |
| **Safeguards** | End-to-end encryption; WhatsApp Business API terms; consent captured before processing |
| **Review** | Annual review of Meta data processing practices |

### 7.4 Telegram - International Processing

| Aspect | Detail |
|---|---|
| **Data transferred** | Message content, user identifiers, timestamps |
| **Classification** | Restricted (user identifiers), Confidential (message content) |
| **Destination** | Telegram infrastructure (distributed globally) |
| **Legal basis (POPIA S72)** | Section 72(1)(b): Consent of data subject (captured at bot registration) |
| **Safeguards** | Telegram Bot API terms; consent captured before processing |
| **Review** | Annual review of Telegram data processing practices |

### 7.5 Cloudflare - Edge Processing

| Aspect | Detail |
|---|---|
| **Data transferred** | HTTP requests/responses (encrypted tunnel) |
| **Classification** | Internal to Confidential (depends on request payload) |
| **Destination** | Nearest Cloudflare edge node (SA preferred, global fallback) |
| **Legal basis (POPIA S72)** | Section 72(1)(a): Adequate protection via Cloudflare DPA and EU adequacy |
| **Safeguards** | Cloudflare Tunnel (no data inspection); DPA in place; data routing configurable to SA region |
| **Review** | Annual review of Cloudflare data processing addendum |

---

## 8. Reclassification and Declassification

### 8.1 Reclassification (Upgrading)

Information must be reclassified to a higher level when:

1. New personal information is associated with previously non-PI data
2. Data is combined with other datasets creating a higher sensitivity aggregate
3. Regulatory requirements change (e.g., new POPIA guidance)
4. Client contractual requirements specify higher classification

**Process:**
1. Data owner identifies reclassification need
2. Information Security Officer reviews and approves
3. Handling controls updated to match new classification
4. Access permissions reviewed and adjusted
5. Reclassification recorded in data inventory

### 8.2 Declassification (Downgrading)

Information may be declassified when:

1. Personal information has been fully anonymised (irreversible)
2. Confidential data has been publicly disclosed by the data owner
3. Retention period has expired and data is scheduled for deletion
4. Contractual confidentiality obligations have expired

**Process:**
1. Data owner requests declassification with justification
2. Information Security Officer confirms PI has been removed or anonymised
3. Legal review for Restricted-to-Confidential downgrades
4. New classification applied, handling controls adjusted
5. Declassification recorded in data inventory

---

## 9. Owner Responsibilities

### 9.1 Data Owners

| Classification Level | Data Owner | Responsibilities |
|---|---|---|
| Public | Product Manager | Approve content for public release; annual relevance review |
| Internal | Operations Manager | Ensure appropriate access controls; review Internal data inventory annually |
| Confidential | Information Security Officer | Approve access requests; monitor handling compliance; incident response for breaches |
| Restricted | CTO / CISO | Approve and document all access grants; quarterly access review; incident response lead |

### 9.2 All Personnel

All SENTINEL personnel and contractors must:

- Classify data they create according to this policy
- Handle data according to the controls specified for its classification
- Report suspected classification errors or data handling violations
- Not downgrade data classification without approval
- Complete annual information classification training

---

## 10. Enforcement

Violations of this policy may result in:

1. **Minor violation** (mislabelling, accidental mishandling with no data exposure): Corrective training
2. **Moderate violation** (sharing Confidential data without authorisation): Formal warning, access review
3. **Severe violation** (exposing Restricted data, deliberate circumvention): Access revocation, disciplinary action, potential legal action
4. **Regulatory breach** (POPIA violation): Mandatory notification to Information Regulator within 72 hours, client notification

---

## 11. Version Control

| Version | Date | Author | Changes |
|---|---|---|---|
| 1.0 | 2026-02-04 | Information Security Officer | Initial policy creation |

---

*SENTINEL BMS Intelligence Platform - Information Classification Policy*
*FSR Domain 4.3 - Information Classification*
*Classification: Internal*
