---
title: "SENTINEL Information Security Framework"
type: "policy"
status: "approved"
version: "1.0.0"
created: "2026-02-04"
updated: "2026-02-04"
author: "SENTINEL Security Office"
tags: ["security", "governance", "framework", "ISO-27001", "POPIA", "FSR"]
domain: "security"
audience: "all"
complexity: "intermediate"
estimated_read_time: 20
classification: "Confidential"
review_date: "2027-02-04"
---

# SENTINEL Information Security Framework

## 1. Document Purpose and Scope

### 1.1 Purpose

This Information Security Framework establishes the governance structure, policy hierarchy, and management system for protecting all information assets associated with the SENTINEL BMS Intelligence Platform. It provides the overarching structure within which all information security policies, standards, procedures, and guidelines operate.

### 1.2 Scope

This framework applies to:

- **All SENTINEL systems:** FastAPI backend, React frontend, PostgreSQL/Supabase databases, InfluxDB time-series storage, TensorFlow ML models, Docker container infrastructure, and the SIMBIOT MCP server
- **All infrastructure:** Contabo VPS hosting, Cloudflare CDN and tunnel services, cloud API integrations (Anthropic Claude, Ollama), and messaging platform integrations (WhatsApp, Telegram)
- **All data processing:** Building telemetry from BMS/SCADA systems (Siemens Desigo CC, Tridonic DALI-2, Modbus TCP devices), occupant personal information, work order data, predictive maintenance outputs, and AI-generated recommendations
- **All personnel:** Developers, system administrators, operators, contractors, and any third party with access to SENTINEL systems or data
- **All client deployments:** Including the demo environment (Sandton City Office Tower, site-002) and any future production deployments for facilities management clients

### 1.3 Exclusions

This framework does not cover:

- Client-side BMS/SCADA infrastructure operated by building owners (covered by shared responsibility agreements)
- End-user devices used to access the SENTINEL web interface (covered by the Acceptable Usage Policy)

---

## 2. Governance Structure

### 2.1 Information Security Officer (ISO)

The Information Security Officer is the designated individual responsible for the development, implementation, and ongoing management of the SENTINEL information security programme.

| Attribute | Detail |
|---|---|
| **Role title** | Information Security Officer |
| **Named individual** | To be appointed by the SENTINEL commercial entity Board of Directors |
| **Reporting line** | Reports directly to the Managing Director / CEO of the SENTINEL commercial entity |
| **Authority** | Has authority to enforce security policies, approve exceptions, and escalate security incidents to executive management |
| **Accountability** | Accountable for the overall security posture of SENTINEL, compliance with applicable legislation (POPIA, FSR requirements), and timely reporting of security incidents |

### 2.2 Key Responsibilities of the ISO

1. **Policy management:** Maintain the information security policy suite, ensure annual reviews, and approve updates
2. **Risk management:** Conduct and oversee annual information security risk assessments, maintain the risk register, and track remediation
3. **Incident management:** Oversee the incident response process, ensure timely notification to affected parties and regulators
4. **Compliance:** Ensure SENTINEL meets all applicable regulatory requirements including POPIA, FSR supplier security requirements, and ISO 27001 alignment
5. **Training:** Ensure all personnel complete security awareness training annually
6. **Audit:** Coordinate internal and external security audits, track findings to resolution
7. **Reporting:** Produce quarterly Information Security Health Reports for executive management and client stakeholders

### 2.3 Supporting Roles

| Role | Responsibility |
|---|---|
| **System Administrator** | Maintain infrastructure security (Contabo VPS, Docker, databases), implement patches and updates, manage access controls |
| **Lead Developer** | Enforce secure coding standards, conduct peer code reviews with security focus, manage application security testing (SAST/DAST) |
| **DevOps Engineer** | Manage CI/CD security controls, container image scanning, dependency monitoring, and deployment security |
| **All Personnel** | Comply with information security policies, report incidents, complete training, protect credentials |

### 2.4 Review Cadence

| Activity | Frequency | Responsible |
|---|---|---|
| Information Security Framework review | Annually (minimum) | ISO |
| Information Security Policy review | Annually (minimum) | ISO |
| Quarterly Security Health Report | Quarterly | ISO |
| Risk register review | Quarterly | ISO |
| Access rights review | Monthly | System Administrator |
| Incident response drill | Annually | ISO + Incident Response Team |
| BCP/DR test | Annually | ISO + System Administrator |
| Security awareness training | Annually | All personnel |

---

## 3. Policy Hierarchy

SENTINEL's information security documentation follows a hierarchical structure. Each level provides increasing specificity:

```
Level 1: FRAMEWORK (this document)
    Establishes governance, structure, principles
    ↓
Level 2: POLICIES
    Define WHAT must be done
    (e.g., Information Security Policy, Access Control Policy)
    ↓
Level 3: STANDARDS
    Define specific requirements and thresholds
    (e.g., Password Standard: min 14 characters, MFA required)
    ↓
Level 4: PROCEDURES
    Define HOW to do it, step-by-step
    (e.g., Incident Response Procedure, BCP/DR Runbook)
    ↓
Level 5: GUIDELINES
    Provide advisory best practices
    (e.g., Secure Coding Guidelines, Remote Work Guidelines)
```

### 3.1 Document Governance Rules

- **Level 1-2 documents** require ISO approval and annual review
- **Level 3-4 documents** require ISO review and may be approved by relevant technical leads
- **Level 5 documents** are advisory and maintained by relevant team members
- All documents must carry version numbers, effective dates, review dates, and classification labels
- Policy exceptions must be documented, risk-assessed, time-limited, and approved by the ISO

---

## 4. Policy Suite

The following table lists all documents in the SENTINEL Information Security Policy Suite, grouped by the FSR domain they primarily address.

| Document | Level | FSR Domain | Status |
|---|---|---|---|
| Information Security Framework (this document) | Framework | 4.1 Governance | Complete |
| Information Security Strategy | Framework | 4.1 Governance | Complete |
| Information Security Policy | Policy | 4.1 Governance (all domains) | Complete |
| Acceptable Usage Policy | Policy | 4.1 Governance | Complete |
| Access Control Policy | Policy | 4.7 Logical Access Control | Planned |
| Application Security Policy | Policy | 4.9 Application Security | Planned |
| Secure Coding Standards | Standard | 4.9 Application Security | Planned |
| Vulnerability Management Policy | Policy | 4.10 Vulnerability Management | Planned |
| Incident Response Policy | Policy | 4.13-4.14 Incident Detection/Management | Planned |
| Business Continuity & DR Policy | Policy | 4.15 Business Continuity | Planned |
| Third-Party Security Policy | Policy | 4.16 Third Party Management | Planned |
| Risk Management Policy | Policy | 4.17 Risk & Compliance | Planned |
| Data Privacy & Classification Policy | Policy | 4.3 Information Classification | Planned |
| Human Resource Security Policy | Policy | 4.4 HR Security | Planned |
| Cryptography & Key Management Policy | Policy | 4.12 Cryptography | Planned |
| Information Security Risk Register | Register | 4.17 Risk & Compliance | Planned |
| Security Awareness Training Programme | Programme | 4.4 HR Security | Planned |
| Asset Register | Register | 4.2 Asset Management | Planned |
| Third-Party Register | Register | 4.16 Third Party Management | Planned |

---

## 5. Applicable Standards and Legislation

### 5.1 Primary Regulatory Framework

| Standard/Legislation | Relevance to SENTINEL |
|---|---|
| **POPIA (Protection of Personal Information Act, 2013)** | Primary South African data protection legislation. SENTINEL processes personal information of building occupants (phone numbers, names, locations via WhatsApp/Telegram) and technician identifiers. Compliance is mandatory. |
| **FSR Privacy and Service Risk Assessment V8** | FirstRand Group supplier security assessment. SENTINEL must achieve a minimum score of 3.5 across all 18 security domains to qualify for onboarding. |
| **ISO/IEC 27001:2022** | International standard for information security management systems (ISMS). SENTINEL aligns to ISO 27001 controls without formal certification at this stage. |
| **ISO/IEC 27002:2022** | Implementation guidance for ISO 27001 controls. Used as the reference for SENTINEL security control selection and implementation. |

### 5.2 Supporting Standards

| Standard | Application |
|---|---|
| **OWASP Top 10** | Web application security controls for the SENTINEL FastAPI backend and React frontend |
| **CIS Benchmarks** | Security configuration standards for Ubuntu Server, Docker, and PostgreSQL |
| **NIST Cybersecurity Framework** | Risk management methodology reference for identify, protect, detect, respond, recover functions |
| **PCI DSS** | Not directly applicable (SENTINEL does not process payment card data), but referenced for cryptographic controls best practice |

---

## 6. Risk Appetite Statement

### 6.1 Overall Risk Appetite

SENTINEL operates with a **low to moderate** risk appetite for information security. As a platform that processes building telemetry, generates maintenance recommendations, and handles occupant personal information for facilities management clients including financial institutions, SENTINEL prioritises security and data protection.

### 6.2 Risk Appetite by Category

| Risk Category | Appetite | Rationale |
|---|---|---|
| **Data breach involving personal information** | Very Low | Regulatory exposure under POPIA, reputational damage, client trust |
| **Unauthorised access to BMS/SCADA systems** | Very Low | Safety implications for building occupants, potential physical harm |
| **Service availability disruption** | Low | Facilities management operations depend on SENTINEL for anomaly detection and work order creation |
| **AI model integrity compromise** | Low | Incorrect predictions could lead to equipment damage or unnecessary maintenance expenditure |
| **Third-party API security** | Low to Moderate | Claude API and messaging platforms process data externally; mitigated by data minimisation and contractual controls |
| **Development and testing environments** | Moderate | Demo/development environments have reduced risk profile compared to production |

### 6.3 Risk Acceptance

Risks that fall within the defined appetite may be accepted by the ISO with documented justification. Risks that exceed the appetite must be escalated to executive management for decision. All accepted risks must be recorded in the Information Security Risk Register with review dates.

---

## 7. Review and Approval Process

### 7.1 Document Lifecycle

1. **Draft:** Author creates document using appropriate template
2. **Review:** ISO reviews for completeness, consistency with framework, and regulatory alignment
3. **Approval:** ISO approves (Level 3-5) or ISO + Executive Management approve (Level 1-2)
4. **Publication:** Document is published to the security documentation repository (`docs/08-security/`)
5. **Annual Review:** All active documents reviewed annually at minimum, or upon significant change
6. **Retirement:** Superseded documents are marked deprecated and archived

### 7.2 Change Triggers

A document must be reviewed outside the regular annual cycle when:

- A security incident reveals a policy gap
- Regulatory requirements change (POPIA amendments, new FSR questionnaire version)
- SENTINEL architecture changes significantly (new infrastructure, new integrations)
- An audit finding identifies a documentation deficiency
- A client contractual requirement introduces new obligations

### 7.3 Approval Authority

| Document Level | Approval Authority |
|---|---|
| Framework (Level 1) | ISO + Managing Director |
| Policy (Level 2) | ISO + Managing Director |
| Standard (Level 3) | ISO |
| Procedure (Level 4) | ISO or delegated technical lead |
| Guideline (Level 5) | Relevant team lead |

---

## 8. Version Control

| Version | Date | Author | Changes |
|---|---|---|---|
| 1.0 | 2026-02-04 | SENTINEL Security Office | Initial release. Establishes governance structure, policy hierarchy, applicable standards, and risk appetite for FSR domain 4.1 compliance. |

---

*Classification: Confidential*
*Next Review: 2027-02-04*
*Owner: Information Security Officer*
