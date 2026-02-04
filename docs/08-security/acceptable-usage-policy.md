---
title: "SENTINEL Acceptable Usage Policy"
type: "policy"
status: "approved"
version: "1.0.0"
created: "2026-02-04"
updated: "2026-02-04"
author: "SENTINEL Security Office"
tags: ["security", "policy", "acceptable-use", "infrastructure", "AUP"]
domain: "security"
audience: "all"
complexity: "beginner"
estimated_read_time: 15
classification: "Confidential"
review_date: "2027-02-04"
---

# SENTINEL Acceptable Usage Policy

## 1. Purpose

This Acceptable Usage Policy (AUP) defines the rules and expectations for the acceptable use of all SENTINEL BMS Intelligence Platform systems, infrastructure, and communication channels. It aims to protect SENTINEL assets, client data, and personnel while enabling effective use of technology resources.

## 2. Scope

This policy applies to all users of SENTINEL systems, including:

- **Developers** working on SENTINEL codebase (FastAPI backend, React frontend, ML models, MCP server)
- **System administrators** managing SENTINEL infrastructure (Contabo VPS, Docker, databases, Cloudflare)
- **Operators** monitoring and managing SENTINEL for facilities management clients
- **Client-side users** accessing the SENTINEL web interface, API endpoints, or conversational interfaces
- **Contractors and third parties** engaged to work on or with SENTINEL systems
- **Bot integrations** (Clawd Telegram bot, WhatsApp Business API handlers)

This policy covers all SENTINEL-related activities regardless of location, device, or time of day.

---

## 3. Acceptable Use of SENTINEL Infrastructure

### 3.1 Contabo VPS and Server Infrastructure

Users with administrative access to the SENTINEL Contabo VPS shall:

- Access the server only via SSH with multi-factor authentication (2FA) through Cloudflare Tunnel
- Use individual, named accounts; shared accounts are prohibited
- Limit activity to SENTINEL-related work only; the VPS shall not be used for personal computing, hosting unrelated services, or cryptocurrency mining
- Follow the principle of least privilege; request only the access level required for the task
- Log off or lock sessions when not actively in use
- Report any suspected unauthorised access immediately to the Information Security Officer

### 3.2 Docker Container Environment

Users managing the Docker Swarm environment shall:

- Use only approved Docker images from the SENTINEL registry or official trusted repositories
- Never run containers in privileged mode without explicit ISO approval
- Never disable Docker security features (seccomp, AppArmor, capability restrictions)
- Follow documented Dockerfile hardening guidelines when building or modifying container images
- Remove unused containers, images, and volumes regularly to minimise attack surface
- Never store secrets or credentials in Docker images, Dockerfiles, or docker-compose files

### 3.3 Database Systems

Users with access to PostgreSQL (Supabase), InfluxDB, or any SENTINEL data store shall:

- Access databases only through approved tools and connection methods
- Never use production database credentials in development or testing environments
- Never export or copy production data to personal devices or unapproved storage
- Apply data classification handling rules when querying or exporting data
- Never disable database audit logging or modify audit trail records
- Report any data quality issues, unexpected data, or suspected data breaches immediately

### 3.4 Source Code and Repositories

Users with access to SENTINEL source code repositories shall:

- Never commit secrets, API keys, credentials, or personal information to version control
- Use pre-commit hooks (`.pre-commit-config.yaml`) to prevent accidental secret commits
- Follow the established branching and code review workflow
- Never disable security-related pre-commit hooks without ISO approval
- Never introduce unlicensed or copyleft-licensed dependencies without legal review
- Protect repository access credentials and report any suspected compromise

---

## 4. Acceptable Use of Communication Systems

### 4.1 API Access

Users and systems accessing SENTINEL APIs shall:

- Authenticate using valid credentials (API keys, JWT tokens, or OAuth tokens)
- Respect rate limits and not attempt to circumvent API throttling
- Not use SENTINEL APIs for purposes outside the agreed scope of service
- Report any API security vulnerabilities through the responsible disclosure process
- Not attempt to access API endpoints beyond their authorised scope
- Ensure all API communications use HTTPS/TLS

### 4.2 WhatsApp and Telegram Integrations

The SENTINEL platform integrates with WhatsApp Business API and Telegram for building occupant communication. Users of these channels shall:

- Use messaging integrations only for legitimate facilities management purposes (comfort complaints, maintenance requests, status notifications)
- Not share sensitive building security information via messaging platforms
- Not use messaging channels to distribute personal information beyond what is required for the facilities request
- Acknowledge that message content may be logged by SENTINEL for work order creation and audit purposes
- Not use messaging channels for harassment, spam, or any inappropriate communication
- Recognise that messaging platforms (Meta, Telegram) have their own data processing terms

### 4.3 Claude AI API (Anthropic)

The SENTINEL platform uses Anthropic's Claude API for conversational AI, the SIMBIOT MCP server, and AI-assisted optimization. Users shall:

- Not submit personal information of building occupants or employees to the Claude API beyond what is strictly necessary for the facilities management query
- Not use the Claude API to generate offensive, discriminatory, or inappropriate content
- Acknowledge that data sent to the Claude API is processed on Anthropic servers in the United States, constituting cross-border data transfer
- Not attempt to use the Claude API for purposes outside SENTINEL's facilities management scope
- Not share SENTINEL's Anthropic API key with unauthorised parties
- Follow data minimisation principles when constructing prompts that include building or occupant data

### 4.4 Email

SENTINEL-related email communication shall:

- Use encrypted email channels for transmitting Confidential or Restricted information
- Not be used to send unencrypted passwords, API keys, or database credentials
- Include appropriate classification labels when transmitting classified information
- Be sent only to recipients with a legitimate need for the information
- Not be auto-forwarded to personal email accounts

---

## 5. Internet and Network Usage

### 5.1 General Internet Usage

Users accessing the Internet from SENTINEL infrastructure or while working on SENTINEL systems shall:

- Not use SENTINEL infrastructure to access, download, or distribute illegal content
- Not use SENTINEL network resources for excessive personal use
- Not install peer-to-peer file sharing software on SENTINEL infrastructure
- Not attempt to bypass network security controls (firewall rules, Cloudflare tunnel, content filters)
- Not conduct network scanning, penetration testing, or vulnerability assessment against SENTINEL systems without prior written authorisation from the ISO

### 5.2 Cloudflare Tunnel and Remote Access

The SENTINEL Cloudflare Tunnel is the approved remote access mechanism. Users shall:

- Access SENTINEL infrastructure only through the Cloudflare Tunnel; direct SSH to the Contabo VPS public IP is prohibited
- Not share Cloudflare access credentials or tunnel configurations with unauthorised parties
- Not attempt to create alternate tunnels or VPN connections to SENTINEL infrastructure without ISO approval
- Report any Cloudflare configuration issues to the System Administrator

---

## 6. Software Installation and Development Practices

### 6.1 Software Installation

Users shall:

- Install only software approved for use on SENTINEL systems
- Not install personal software, games, or entertainment applications on SENTINEL infrastructure
- Validate the integrity and security of any software before installation (checksum verification, trusted sources)
- Not disable or interfere with endpoint protection, antivirus, or security monitoring software on SENTINEL systems
- Report any software that behaves unexpectedly or appears malicious

### 6.2 Development Practices

Developers working on the SENTINEL codebase shall:

- Follow the documented Secure Coding Standards for Python/FastAPI and TypeScript/React
- Run SAST scans locally before pushing code (where tooling is available)
- Submit all code changes through peer review with a security review checklist
- Not introduce backdoors, debug endpoints, or hardcoded credentials into the codebase
- Ensure test data does not contain real personal information
- Keep local development environment dependencies up to date with security patches
- Use `.env` files for local configuration and never commit them to version control

---

## 7. Data Handling Obligations

### 7.1 General Data Handling

All SENTINEL users shall handle data according to its classification:

| Classification | Handling Requirements |
|---|---|
| **Public** | No restrictions on access or distribution |
| **Internal** | Access limited to SENTINEL personnel; not shared externally without approval |
| **Confidential** | Encrypted at rest and in transit; access on need-to-know basis; logged access |
| **Restricted** | Encryption mandatory; named access list; dual-control for modification; audit trail |

### 7.2 Personal Information

Personal information processed by SENTINEL (occupant phone numbers, names, locations, technician identifiers) shall be:

- Processed only for legitimate facilities management purposes
- Not retained beyond the defined retention period (90 days raw, 2 years aggregated)
- Not shared with third parties without appropriate consent or contractual basis
- Protected by technical and organisational measures as defined in the Information Security Policy
- Subject to data subject rights (access, correction, deletion) under POPIA

Refer to the Data Privacy and Classification Policy for detailed handling procedures.

---

## 8. Remote Access Requirements

### 8.1 Cloudflare Tunnel

All remote access to SENTINEL production infrastructure shall be through the Cloudflare Tunnel. This provides:

- Zero-trust network access (no exposed ports on the Contabo VPS)
- TLS-encrypted connection
- Cloudflare Access policies for authentication and authorisation
- Audit logging of all access attempts

### 8.2 SSH Access

SSH access to the Contabo VPS shall:

- Be authenticated using SSH keys (password authentication is disabled)
- Require multi-factor authentication (2FA)
- Be routed through the Cloudflare Tunnel
- Use the current stable version of the SSH protocol
- Be logged and monitored for suspicious activity

### 8.3 Database Remote Access

Remote access to SENTINEL databases (PostgreSQL/Supabase, InfluxDB) shall:

- Be through approved application interfaces or managed database dashboards only
- Not use direct database connections from personal workstations to production databases without VPN/tunnel
- Require authentication with individual credentials (no shared database accounts)

---

## 9. Personal Device Usage (BYOD)

### 9.1 Policy

SENTINEL permits the use of personal devices (laptops, mobile phones) for SENTINEL-related work under the following conditions:

- The device shall have an up-to-date operating system with security updates applied
- The device shall have endpoint protection (antivirus/anti-malware) installed and active
- Full-disk encryption shall be enabled on any device used to access SENTINEL systems
- Screen lock shall be configured with a maximum timeout of 5 minutes
- The user shall not store Confidential or Restricted SENTINEL data locally on personal devices without encryption
- The user shall report lost or stolen devices that may have SENTINEL credentials or data immediately to the ISO
- SENTINEL reserves the right to request remote wipe of SENTINEL data from personal devices upon personnel departure

### 9.2 Mobile Devices

Mobile devices used to access SENTINEL (including the Clawd Telegram bot or SENTINEL web interface) shall:

- Have PIN, biometric, or password lock enabled
- Have current OS and app updates installed
- Not be rooted or jailbroken
- Not have SENTINEL credentials stored in plain text

---

## 10. Monitoring and Audit Statement

### 10.1 Monitoring Notice

All SENTINEL systems are monitored for security purposes. By using SENTINEL systems, users acknowledge and consent to the following monitoring activities:

- **Access logging:** All authentication attempts (successful and failed) are logged
- **Activity logging:** API requests, database queries, and administrative actions are logged
- **Network monitoring:** Network traffic to and from SENTINEL infrastructure is monitored
- **Security scanning:** SENTINEL infrastructure is subject to ongoing vulnerability scanning and intrusion detection
- **Audit logging:** All control actions, configuration changes, and data modifications are recorded in an audit trail

### 10.2 Log Retention

Security and audit logs are retained for a minimum of 12 months for operational purposes and up to 3 years for compliance and forensic purposes.

### 10.3 Privacy

Monitoring is conducted for security and compliance purposes only. Personal privacy is respected within the bounds of security requirements. Users should have no expectation of privacy when using SENTINEL systems for work-related activities.

---

## 11. Prohibited Activities

The following activities are explicitly prohibited on SENTINEL systems:

1. **Unauthorised access:** Attempting to access systems, data, or accounts beyond authorised scope
2. **Credential sharing:** Sharing passwords, API keys, SSH keys, or other authentication credentials
3. **Data exfiltration:** Copying, transmitting, or removing Confidential or Restricted data without authorisation
4. **Security control bypass:** Disabling, circumventing, or interfering with security controls, monitoring, or audit logging
5. **Malware:** Introducing or distributing viruses, worms, ransomware, or other malicious software
6. **Social engineering:** Attempting to manipulate others into disclosing credentials or confidential information
7. **Cryptocurrency mining:** Using SENTINEL infrastructure for cryptocurrency mining or other resource-intensive non-business activities
8. **Harassment:** Using SENTINEL communication channels for harassment, discrimination, or inappropriate behaviour
9. **Illegal activity:** Using SENTINEL systems for any activity that violates South African law or any applicable jurisdiction
10. **Tampering:** Modifying audit logs, falsifying records, or destroying evidence
11. **Scanning/testing without authorisation:** Conducting security scans, penetration tests, or denial-of-service tests against SENTINEL systems without written ISO approval
12. **Shadow IT:** Deploying unapproved services, applications, or infrastructure that process SENTINEL data

---

## 12. Compliance Acknowledgement

### 12.1 Requirement

All users of SENTINEL systems shall acknowledge their understanding of and agreement to comply with this Acceptable Usage Policy. Acknowledgement shall be:

- Obtained before access to SENTINEL systems is granted
- Renewed annually as part of the security awareness training process
- Recorded and retained by the ISO

### 12.2 Acknowledgement Statement

> I acknowledge that I have read, understood, and agree to comply with the SENTINEL Acceptable Usage Policy. I understand that violation of this policy may result in disciplinary action, termination of access, or legal proceedings. I understand that my use of SENTINEL systems is subject to monitoring and audit as described in this policy.

---

## 13. Related Documents

| Document | Reference |
|---|---|
| Information Security Framework | `docs/08-security/information-security-framework.md` |
| Information Security Policy | `docs/08-security/information-security-policy.md` |
| Data Privacy & Classification Policy | `docs/08-security/data-privacy-classification-policy.md` (planned) |
| Secure Coding Standards | `docs/08-security/secure-coding-standards.md` (planned) |
| Incident Response Policy | `docs/08-security/incident-response-policy.md` (planned) |

---

## 14. Version History

| Version | Date | Author | Changes |
|---|---|---|---|
| 1.0 | 2026-02-04 | SENTINEL Security Office | Initial release. Defines acceptable use rules for SENTINEL infrastructure (Contabo, Docker, databases), communication systems (WhatsApp, Telegram, Claude API), remote access (Cloudflare Tunnel, SSH), personal devices (BYOD), and data handling obligations. |

---

*Classification: Confidential*
*Next Review: 2027-02-04*
*Owner: Information Security Officer*
