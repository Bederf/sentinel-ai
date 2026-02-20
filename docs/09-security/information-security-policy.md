---
title: "SENTINEL Information Security Policy"
type: "policy"
status: "approved"
version: "1.0.0"
created: "2026-02-04"
updated: "2026-02-04"
author: "SENTINEL Security Office"
tags: ["security", "policy", "governance", "FSR", "POPIA"]
domain: "security"
audience: "all"
complexity: "intermediate"
estimated_read_time: 25
classification: "Confidential"
review_date: "2027-02-04"
---

# SENTINEL Information Security Policy

## 1. Purpose

This Information Security Policy establishes the overarching security requirements governing all SENTINEL BMS Intelligence Platform operations. It defines the mandatory security controls, roles, responsibilities, and compliance obligations for all personnel, systems, and data associated with SENTINEL.

This policy is the Level 2 document within the SENTINEL Information Security Framework hierarchy and provides the basis for all subordinate standards, procedures, and guidelines.

## 2. Scope

This policy applies to:

- All SENTINEL systems, applications, infrastructure, and data
- All personnel with access to SENTINEL systems, including employees, contractors, and third-party service providers
- All locations from which SENTINEL systems are accessed or administered
- All phases of the SENTINEL system lifecycle: development, testing, deployment, operation, maintenance, and decommissioning

## 3. Policy Statements by FSR Domain

### 3.1 Information Security Governance (FSR 4.1)

SENTINEL shall maintain a formal information security governance structure headed by a designated Information Security Officer (ISO) with authority and accountability for the security programme. The governance structure shall include documented policies, standards, procedures, and guidelines organised in a defined hierarchy. The ISO shall produce quarterly security health reports and conduct annual reviews of all governance documents. Executive management shall demonstrate visible commitment to information security through resource allocation, policy endorsement, and participation in security reviews.

### 3.2 Asset Management (FSR 4.2)

All SENTINEL information assets shall be identified, classified, and recorded in a formal Asset Register. Assets include but are not limited to: the Contabo VPS infrastructure, Docker container images, PostgreSQL and InfluxDB databases, TensorFlow ML models, API keys, TLS certificates, source code repositories, and configuration files. Each asset shall have a designated owner responsible for its security. Asset disposal shall follow documented secure disposal procedures, including cryptographic erasure of storage media and destruction certificates where applicable.

### 3.3 Information Classification (FSR 4.3)

All SENTINEL data shall be classified according to a defined classification scheme with categories: Public, Internal, Confidential, and Restricted. Data classification shall determine handling requirements including storage, transmission, access control, retention, and disposal. Building telemetry and BMS sensor data shall be classified as Internal. Work order data, occupant personal information, and API credentials shall be classified as Confidential. Encryption keys and security audit reports shall be classified as Restricted. Classification labels shall be consistently applied across documentation, API responses, and stored data.

### 3.4 Human Resource Security (FSR 4.4)

All personnel with access to SENTINEL systems or FirstRand data shall undergo appropriate vetting and clearance processes prior to access being granted. Job descriptions shall include explicit information security responsibilities. All personnel shall complete information security awareness training annually, with completion tracked and recorded. A documented joiners and leavers process shall ensure that system access is provisioned upon joining and revoked within 24 hours of departure. Contractors and third parties shall be contractually bound to comply with this policy. Violations of this policy shall be subject to disciplinary action as defined in the HR disciplinary process.

### 3.5 Physical Access Security (FSR 4.5)

Physical security for SENTINEL infrastructure is primarily managed through the cloud hosting provider (Contabo) and is documented via provider attestations and SLAs. SENTINEL development and administrative environments shall implement appropriate physical access controls including locked workstations, secure storage of removable media, and clean desk practices. For on-premise client deployments, a shared responsibility matrix shall document physical security obligations between SENTINEL and the client.

### 3.6 Network Security (FSR 4.6)

SENTINEL network architecture shall implement defence-in-depth principles. All external access to SENTINEL infrastructure shall be routed through Cloudflare Tunnel, eliminating direct exposure of the Contabo VPS. Firewall rules shall follow a default-deny policy, permitting only explicitly authorised traffic. Network segmentation shall separate BMS connectors (OT network) from application services (IT network) and management access. All network communication shall be encrypted using TLS 1.2 or higher. Firewall rules shall be reviewed at least bi-annually. Wireless network use shall be documented and secured where applicable.

### 3.7 Logical Access Control (FSR 4.7)

Access to SENTINEL systems shall be controlled through a formal Identity and Access Management (IAM) process. All access shall be granted on the principle of least privilege and role-based access control (RBAC). Multi-factor authentication (MFA) shall be required for all administrative access to SENTINEL infrastructure, including SSH access to the Contabo VPS, Supabase database administration, Docker management, and Cloudflare dashboard access. Password standards shall meet current industry best practice: minimum 14 characters, complexity requirements, and prohibition of password reuse. Privileged access shall be managed through a Privileged Access Management (PAM) solution with session recording for administrative access. Stale accounts shall be reviewed monthly and dormant accounts deactivated after 90 days of inactivity. Access recertification shall be performed at least quarterly.

### 3.8 System Security (FSR 4.8)

SENTINEL infrastructure shall be hardened according to CIS Benchmarks for Ubuntu Server, Docker, and PostgreSQL. Security configuration standards shall be documented and enforced. The Contabo VPS shall run current, supported operating system versions with automatic security updates enabled. Docker container images shall be built from minimal base images, scanned for vulnerabilities, and run with non-root user contexts. Endpoint protection (antivirus/anti-malware) shall be deployed on the Contabo VPS. Patch management procedures shall ensure critical security patches are applied within 7 days of release. Device control measures shall restrict USB and removable media access where appropriate.

### 3.9 Application Security (FSR 4.9)

SENTINEL software development shall follow a Secure Software Development Lifecycle (SSDLC) integrating security at every phase: requirements, design, implementation, testing, deployment, and maintenance. Secure coding standards for Python/FastAPI and TypeScript/React development shall be documented and enforced. All code changes shall undergo peer review with a security review checklist. Static Application Security Testing (SAST) shall be integrated into the CI/CD pipeline and executed on every code commit. Dynamic Application Security Testing (DAST) shall be performed at least quarterly against deployed SENTINEL instances. A Web Application Firewall (WAF) shall protect all Internet-facing SENTINEL endpoints (Cloudflare WAF). Input validation, output encoding, authentication, session management, and access control shall follow OWASP Top 10 best practices. Vulnerability remediation SLAs shall be enforced: Critical within 7 days, High within 14 days. An independent application security assessment shall be conducted annually.

### 3.10 Vulnerability Management (FSR 4.10)

SENTINEL shall maintain a formal vulnerability management programme. External vulnerability scanning of Internet-facing endpoints shall be performed monthly. Internal infrastructure vulnerability scanning shall be performed quarterly. Python dependency vulnerabilities shall be monitored continuously using automated tools (Safety, Dependabot, or Snyk). Docker container images shall be scanned for known vulnerabilities before deployment. Remediation SLAs shall be: Critical within 7 days, High within 14 days, Medium within 30 days, Low within 90 days. Firewall rules shall be reviewed bi-annually. A vulnerability register shall track all discovered vulnerabilities from detection through remediation.

### 3.11 Communication Management (FSR 4.11)

All SENTINEL API communications shall be encrypted using TLS 1.2 or higher. Email communications containing sensitive SENTINEL information shall use encrypted channels. BMS data transmission between connectors and the SENTINEL backend shall be encrypted in transit. Portable storage media containing SENTINEL data shall be encrypted. Communication security requirements shall be included in the security awareness training programme. The WhatsApp and Telegram messaging integrations shall implement end-to-end encryption where supported by the platform, and message content shall be handled according to its classification.

### 3.12 Cryptography and Key Management (FSR 4.12)

SENTINEL shall use industry-standard cryptographic algorithms: AES-256 for data at rest, TLS 1.2+ with strong cipher suites for data in transit, and RSA-2048/ECDSA for digital signatures and key exchange. API keys, database credentials, and encryption keys shall be managed through a secrets management solution (environment variables with restricted access, or HashiCorp Vault for production deployments). Keys shall never be stored in source code, configuration files committed to version control, or application logs. Key rotation shall be performed annually at minimum, or immediately upon suspected compromise. Certificate expiry shall be monitored and renewals completed at least 30 days before expiration. Cryptographic control requirements shall be documented in a standalone Cryptography and Key Management Policy.

### 3.13 Information Security Incident Detection (FSR 4.13)

SENTINEL shall implement centralised log aggregation for all system components: FastAPI application logs, PostgreSQL database audit logs, Docker container logs, SSH access logs, Cloudflare access logs, and BMS connector activity logs. Logs shall be stored in a forensically sound manner, separate from application data, and tamper-evident. Automated alerting shall be configured for security-relevant events including: failed authentication attempts, privilege escalation, unusual API access patterns, configuration changes, and data access anomalies. A host-based intrusion detection system shall be deployed on the Contabo VPS. Network-based intrusion detection shall leverage Cloudflare security features. Security monitoring procedures shall be documented and maintained.

### 3.14 Information Security Incident Management (FSR 4.14)

SENTINEL shall maintain a formal Incident Response Policy and Process covering: detection, triage, containment, eradication, recovery, and post-incident review. An Incident Response Team (IRT) shall be established with named roles and 24-hour contact details. An Incident Register shall record all security incidents with severity classification, timeline, actions taken, and lessons learned. Incident disclosure to FirstRand and other affected parties shall follow agreed notification timelines (critical incidents within 4 hours, high within 24 hours). Post-incident reviews shall produce actionable recommendations and feed into the risk register. Incident response metrics shall be reported in the quarterly security health report.

### 3.15 Business Continuity Management (FSR 4.15)

SENTINEL shall maintain a Business Continuity Management policy covering all critical business processes: anomaly detection, work order creation, BMS data ingestion, AI recommendation generation, and occupant communication. Business Impact Analysis (BIA) shall identify critical processes and their Recovery Time Objectives (RTO) and Recovery Point Objectives (RPO). Disaster Recovery procedures shall be documented for: Contabo VPS failure, database corruption, Docker container failure, Cloudflare tunnel disruption, and third-party API outage. BCP/DR plans shall be tested annually and after significant infrastructure changes. Test results shall be documented with identified gaps fed into the remediation plan.

### 3.16 Third-Party Security Management (FSR 4.16)

All third-party service providers with access to SENTINEL systems or FirstRand data shall be recorded in a Third-Party Register. Third parties include but are not limited to: Contabo (hosting), Cloudflare (CDN/tunnel), Anthropic (Claude AI API), Meta (WhatsApp Business API), Telegram, MRI Evolution (FSI Public API), and BMS hardware vendors. Security requirements shall be defined in agreements with each third party. Third-party compliance shall be assessed periodically according to a defined review cadence. Third-party security incidents affecting SENTINEL or FirstRand data shall be reported immediately to the ISO. The ISO shall maintain a risk register for third-party non-compliance and notify FirstRand of any material deviations.

### 3.17 Information Security Risk and Compliance Management (FSR 4.17)

SENTINEL shall maintain a formal Information Security Risk Register documenting identified risks, their likelihood, impact, current controls, residual risk level, and risk treatment plan. A comprehensive annual Information Security Risk Assessment shall be conducted, with quarterly reviews of the risk register. Risk acceptance decisions shall be documented with justification and approved by the ISO (or executive management for risks exceeding the defined appetite). Compliance with applicable legislation (POPIA), contractual obligations (FSR requirements), and adopted standards (ISO 27001) shall be evaluated quarterly. Remediation plans shall track progress with defined milestones and owners. FirstRand shall be notified of any deviations to remediation plans that may impact their data.

### 3.18 Information Security Audit (FSR 4.18)

SENTINEL shall undergo regular security audits to verify the effectiveness of information security controls. Audits shall cover both compliance-based (control effectiveness) and threat-based (control weakness) approaches. An initial comprehensive security audit shall be completed prior to FSR submission. Ongoing audit cadence shall be established at minimum annually. Audit findings shall be tracked in a findings register with remediation owners, target dates, and progress monitoring. Audit results and remediation progress shall be shared with FirstRand as required. The ISO shall ensure audit recommendations are implemented within agreed timelines.

---

## 4. Roles and Responsibilities

| Role | Responsibilities |
|---|---|
| **Information Security Officer** | Overall accountability for this policy; maintains policy suite; conducts risk assessments; manages incident response; coordinates audits; produces quarterly reports; approves policy exceptions |
| **System Administrator** | Implements technical security controls on infrastructure; manages access provisioning/deprovisioning; applies patches and updates; monitors system health; maintains backup and recovery systems |
| **Lead Developer / DevOps** | Enforces secure coding standards; conducts security code reviews; manages SAST/DAST tooling; maintains CI/CD security; manages Docker image security |
| **All Personnel** | Comply with this policy and all subordinate policies; complete security awareness training; protect credentials and classified information; report security incidents immediately; follow clean desk practices |

---

## 5. Compliance Requirements

### 5.1 Regulatory Compliance

| Requirement | Obligation |
|---|---|
| **POPIA** | SENTINEL must comply with the Protection of Personal Information Act, 2013 for all personal information processed. This includes lawful processing, purpose limitation, data minimisation, storage limitation, and data subject rights. Cross-border transfers (Claude API, messaging platforms) must comply with Section 72. |
| **FSR Supplier Requirements** | SENTINEL must achieve and maintain a minimum score of 3.5 across all 18 FSR security domains. Compliance is assessed through the FSR Privacy and Service Risk Assessment Questionnaire. |
| **ISO 27001 Alignment** | SENTINEL aligns to ISO/IEC 27001:2022 controls as its ISMS framework. Formal certification may be pursued in future but is not currently required. |

### 5.2 Contractual Compliance

All client contracts incorporating SENTINEL services shall include information security obligations consistent with this policy. Security requirements shall be reviewed as part of contract negotiation and acceptance processes.

---

## 6. Policy Violation

### 6.1 Consequences

Violations of this policy may result in disciplinary action, up to and including termination of employment or contract. The severity of disciplinary action shall be proportionate to the violation and may consider:

- Whether the violation was intentional or negligent
- The impact or potential impact of the violation
- Whether the individual had received adequate training
- Any mitigating circumstances

### 6.2 Reporting

All suspected policy violations shall be reported to the Information Security Officer. The ISO shall investigate, determine severity, and recommend appropriate action in consultation with management and HR as applicable. Violations involving criminal activity shall be referred to law enforcement authorities.

---

## 7. Related Documents

| Document | Reference |
|---|---|
| Information Security Framework | `docs/08-security/information-security-framework.md` |
| Information Security Strategy | `docs/08-security/information-security-strategy.md` |
| Acceptable Usage Policy | `docs/08-security/acceptable-usage-policy.md` |
| Access Control Policy | `docs/08-security/access-control-policy.md` (planned) |
| Application Security Policy | `docs/08-security/application-security-policy.md` (planned) |
| Secure Coding Standards | `docs/08-security/secure-coding-standards.md` (planned) |
| Vulnerability Management Policy | `docs/08-security/vulnerability-management-policy.md` (planned) |
| Incident Response Policy | `docs/08-security/incident-response-policy.md` (planned) |
| Business Continuity & DR Policy | `docs/08-security/bcp-dr-policy.md` (planned) |
| Third-Party Security Policy | `docs/08-security/third-party-security-policy.md` (planned) |
| Risk Management Policy | `docs/08-security/risk-management-policy.md` (planned) |
| Data Privacy & Classification Policy | `docs/08-security/data-privacy-classification-policy.md` (planned) |
| HR Security Policy | `docs/08-security/hr-security-policy.md` (planned) |
| Cryptography & Key Management Policy | `docs/08-security/cryptography-key-management-policy.md` (planned) |
| Information Security Risk Register | `docs/08-security/risk-register.md` (planned) |

---

## 8. Effective Date and Review

| Attribute | Value |
|---|---|
| **Effective date** | 2026-02-04 |
| **Review date** | 2027-02-04 |
| **Review frequency** | Annual (minimum) |
| **Owner** | Information Security Officer |
| **Approved by** | Managing Director |

---

## 9. Version History

| Version | Date | Author | Changes |
|---|---|---|---|
| 1.0 | 2026-02-04 | SENTINEL Security Office | Initial release. Overarching information security policy covering all 18 FSR domains with SENTINEL-specific policy statements, roles, compliance requirements, and violation consequences. |

---

*Classification: Confidential*
*Next Review: 2027-02-04*
*Owner: Information Security Officer*
