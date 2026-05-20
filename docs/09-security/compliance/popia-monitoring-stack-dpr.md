---
title: "POPIA Data Processing Record - Monitoring Stack"
type: "compliance-document"
status: "active"
version: "1.1.0"
created: "2026-05-18"
updated: "2026-05-19"
author: "SENTINEL Compliance Team"
tags: ["popia", "compliance", "monitoring", "data-processing", "retention"]
domain: "compliance"
audience: "platform, compliance, security, legal"
complexity: "intermediate"
estimated_read_time: 15
---

# POPIA Data Processing Record (DPR) - Monitoring Stack

## 1. Document Purpose

This Data Processing Record (DPR) documents the processing of personal information by the SENTINEL BMS Monitoring Stack (Prometheus, Grafana, Alertmanager, Loki) in compliance with POPIA Section 14 and Section 17 requirements. This record is required for FNB Supplier Registration (FSR) compliance.

**Reference:** POPIA Act 4 of 2013, Sections 14 (Retention), 17 (Processing)

---

## 2. Data Controller Information

| Field | Value |
|-------|-------|
| **Data Controller** | Asikhwele Building Projects (Pty) Ltd |
| **Registration Number** | 2015/010878/07 |
| **Physical Address** | Johannesburg, South Africa |
| **Information Officer** | To be appointed per Section 55 |
| **DPO Contact** | dpo@sentinel-ai.co.za |

> **Verified:** CoR 14.3 CIPC certificate confirmed. Entity: Asikhwele Building Projects (Pty) Ltd, reg 2015/010878/07, director Petrus Wilhelm Van Rooyen.

---

## 3. Processing Activity Overview

### 3.1 Activity Description

The SENTINEL BMS Monitoring Stack processes building management system telemetry, system health metrics, and operational alerts to ensure building safety, energy efficiency, and equipment reliability.

### 3.2 Purpose of Processing

| Purpose | POPIA Legal Basis | Description |
|---------|-------------------|-------------|
| **Building Safety Monitoring** | Section 11(1)(a) - Consent | Monitor HVAC, fire, security systems to protect occupants |
| **Operational Efficiency** | Section 11(1)(f) - Legitimate Interest | Optimize energy usage and equipment performance |
| **Incident Response** | Section 11(1)(c) - Legal Obligation | Respond to equipment failures and safety events |
| **Audit & Compliance** | Section 11(1)(d) - Lawful Processing | FSR compliance, FNB supplier requirements |

---

## 4. Personal Information Processed

### 4.1 Categories of Personal Information

| Category | Data Elements | Source | Sensitive? |
|----------|--------------|--------|------------|
| **Building Occupant Data** | Zone presence (PIR), comfort complaints | BMS sensors, Telegram bot | No (aggregated) |
| **Technician Contact Data** | Name, phone number, WhatsApp ID | Technician registration | Yes (contact details) |
| **Staff Contact Data** | Name, email, phone number | Outlook/HR system | Yes (contact details) |
| **System User Data** | Login logs, IP addresses, user actions | Application access logs | No |
| **Visitor Data** | Name, phone, check-in/out times | Visitor management system | Yes (contact details) |

### 4.2 Special Personal Information (Section 26)

**Status:** No special personal information (race, health, biometric) is processed by the monitoring stack.

> **Note:** BMS sensor data (temperature, occupancy) is environmental telemetry, not personal health information.

---

## 5. Retention Periods

### 5.1 Retention Schedule (FSR 4.13 Compliant)

| Data Category | Retention Period | Legal Basis | Automated Purge |
|--------------|------------------|-------------|-----------------|
| **Raw Telemetry** | 90 days | POPIA s14(1) - Data minimization | Yes (Loki config) |
| **Aggregated Metrics** | 2 years | Legitimate interest - trend analysis | Yes |
| **Audit Logs** | 5 years | FSR 4.13 - Compliance evidence | Manual review |
| **Alert History** | 90 days | Operational necessity | Yes |
| **User Access Logs** | 90 days | Security monitoring | Yes |
| **PII (Technician/Staff)** | Duration of engagement + 90 days | Contractual obligation | Manual |

### 5.2 Technical Implementation

```yaml
# Loki Retention Configuration
limits_config:
  retention_period: 2160h  # 90 days

# Prometheus Retention
storage:
  tsdb:
    retention.time: 90d
```

---

## 6. Data Subject Rights

### 6.1 Rights Under POPIA

| Right | Implementation | Contact Point |
|-------|---------------|---------------|
| **Access (s23)** | Request via dpo@sentinel-ai.co.za | DPO |
| **Correction (s24)** | Self-service portal or DPO request | DPO |
| **Deletion (s25)** | DPO request with justification | DPO |
| **Objection (s11(3))** | DPO request | DPO |
| **Portability** | Export available via API | Technical Support |

### 6.2 Response SLA

- **Acknowledgment:** 72 hours
- **Resolution:** 21 business days (complex requests: 60 days)

---

## 7. Data Security Measures

### 7.1 Technical Controls

| Control | Implementation | Evidence |
|---------|---------------|----------|
| **Encryption at Rest** | AES-256 (Loki chunks, Prometheus TSDB) | Infrastructure config |
| **Encryption in Transit** | TLS 1.3 (all API endpoints) | Cloudflare cert |
| **Access Control** | Role-based (RBAC) + JWT tokens | Auth0/Supabase RLS |
| **Network Segmentation** | WireGuard VPN for remote sites | VPN config |
| **Log Integrity** | Immutable Loki chunks with hash verification | Loki architecture |

### 7.2 Organizational Controls

- **Access Logging:** All admin actions logged to Loki
- **Principle of Least Privilege:** Grafana viewers cannot access raw data
- **Regular Review:** Quarterly access audit
- **Incident Response:** Documented in `incident-response-policy.md`

---

## 8. Cross-Border Transfers

### 8.1 Transfer Assessment

| Transfer | Destination | Safeguards | POPIA Basis | Status |
|----------|-------------|------------|-------------|--------|
| **Cloudflare Tunnel** | USA (CF edge) | TLS 1.3 + DPA | s72(1)(a) - Adequate safeguards | ✅ Compliant |
| **Telegram Alerts** | International (UAE/BVI) | Platform terms only | s72(1)(a) | ⚠️ **Residual Risk** - No DPA available |
| **Anthropic API** | USA | SOC 2 Type II, DPA, no training retention | s72(1)(a) | ✅ Compliant |

### 8.2 Telegram Cross-Border Risk

**Risk:** Telegram FZ-LLC is incorporated in the UAE with data centers globally. They do not offer a standard Data Processing Agreement (DPA) for bot API usage.

**Mitigation:**
- Alert content is sanitized (no PII in alert messages)
- Only system health data transmitted (equipment IDs, metric values)
- Token-based authentication
- **Residual Risk:** Medium - accepted for operational necessity

**Recommendation:** Evaluate alternative notification channels (SMS via Twilio, email) for high-sensitivity alerts requiring DPA coverage.

### 8.2 Data Residency

- **Primary:** Contabo VPS, Germany (EU)
- **Backup:** Supabase (EU region)
- **Rationale:** EU GDPR adequacy + POPIA s72(1)(a)

---

## 9. Data Sharing

### 9.1 Third-Party Processors

| Processor | Purpose | Data Shared | DPA Status |
|-----------|---------|-------------|------------|
| **Cloudflare** | Reverse proxy, WAF | Access logs only | Signed |
| **Telegram** | Alert notifications | Alert text (no PII) | Platform terms |
| **Anthropic** | AI recommendations | Anonymized equipment data | Signed |
| **Supabase** | Database hosting | All structured data | Signed |

### 9.2 No Sale of Personal Information

SENTINEL does not sell, trade, or rent personal information to third parties.

---

## 10. Risk Assessment

### 10.1 Identified Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| **Unauthorized access to logs** | Low | High | RBAC, VPN, encryption |
| **Data breach via Telegram** | Low | Medium | Alert sanitization (no PII in alerts) |
| **Retention exceedance** | Low | Medium | Automated purge jobs |
| **Cross-border compliance** | Low | Medium | DPA, adequacy assessments |

### 10.2 Residual Risk

**Assessment:** Low - Technical and organizational controls adequately mitigate risks.

---

## 11. Compliance Evidence

### 11.1 FSR Domain Mapping

| FSR Domain | Requirement | Evidence Location |
|------------|-------------|-------------------|
| 4.13 - Logging | 90-day retention | This document + Loki config |
| 4.13.5 - Log Integrity | Tamper-evident storage | Loki architecture doc |
| 9.1 - Data Protection | POPIA compliance | This DPR |

### 11.2 Audit Trail

- **Last Review:** 2026-05-18
- **Next Review:** 2026-11-18 (6 months)
- **Change Log:** See git history for this document

---

## 12. Document Control

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.1.0 | 2026-05-19 | Compliance Team | Confirmed legal entity: Asikhwele Building Projects (Pty) Ltd, reg 2015/010878/07 |
| 1.0.0 | 2026-05-18 | Compliance Team | Initial DPR for Monitoring Stack |

### 12.1 Approval

- **Information Officer:** ___________________ Date: ___________
- **Technical Lead:** ___________________ Date: ___________

---

## 13. Related Documents

- [POPIA Compliance Register](popia-compliance-register.md)
- [POPIA Retention Enforcement](popia-retention-enforcement.md)
- [Information Security Policy](../information-security-policy.md)
- [Incident Response Policy](../incident-response-policy.md)
- [Data Privacy Policy](../data-privacy-policy.md)

---

## 14. Contact Information

**Data Protection Queries:**
- Email: dpo@sentinel-ai.co.za
- Address: [To be completed]

**Technical Queries:**
- Email: support@sentinel-ai.co.za

---

*This document is a controlled record under POPIA Section 17. Unauthorized modification is prohibited.*
