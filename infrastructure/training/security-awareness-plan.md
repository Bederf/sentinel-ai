# SENTINEL Security Awareness Training Programme

**Document Owner:** SENTINEL Platform Team
**Version:** 1.0
**Created:** 2026-02-04
**Review Cycle:** Annual
**Status:** Active

---

## 1. Programme Objectives

Ensure all SENTINEL personnel understand their security responsibilities and can identify, prevent, and respond to information security threats. This programme supports FSR domain 4.4 (Human Resource Security) compliance.

**Goals:**

- All personnel with system access complete security awareness training annually
- New personnel complete onboarding training within first 5 working days
- Maintain auditable completion records for FSR submission
- Reduce security incidents caused by human error
- Build a security-conscious culture across development and operations

---

## 2. Target Audience

| Audience | Description | Required Modules |
|----------|-------------|------------------|
| **Developers** | Backend/frontend engineers, ML engineers | Modules 1, 2, 4, 5 |
| **Operators** | System administrators, DevOps, infrastructure | Modules 1, 3, 4, 5 |
| **Contractors** | Third-party FM technicians, integrators | Modules 1, 4 |
| **Administrators** | Platform admins, data managers | Modules 1, 3, 4 |
| **All Personnel** | Anyone with SENTINEL system access | Modules 1, 4 |

---

## 3. Training Frequency

| Event | Frequency | Notes |
|-------|-----------|-------|
| **Annual mandatory training** | Yearly | All modules relevant to role |
| **New personnel onboarding** | Within 5 days of access grant | All role-relevant modules |
| **Quarterly security briefing** | Quarterly | Threat landscape updates, incident reviews |
| **Ad-hoc security alerts** | As needed | Emerging threats, zero-day advisories |
| **Post-incident review** | After security incident | Lessons learned, procedure updates |

---

## 4. Training Modules

### Module 1: Information Security Fundamentals (All Personnel)

**Duration:** 45 minutes
**Format:** Self-paced documentation review + acknowledgment

**Topics:**

1. **SENTINEL Security Architecture Overview**
   - System components: Frontend, Backend API, Database (Supabase), AI Services
   - Network architecture: Contabo VPS, Docker Swarm, Cloudflare Tunnel
   - Data flow: BMS sensors -> SENTINEL -> Dashboard/Chat/Alerts
   - Defence-in-depth principles

2. **Data Classification and Handling**
   - Classification levels: Public, Internal, Confidential, Restricted
   - Building telemetry data: Internal
   - Occupant personal information (PI): Confidential
   - Authentication credentials: Restricted
   - Handling requirements per classification level

3. **Acceptable Use of SENTINEL Systems**
   - Authorised access and use boundaries
   - Prohibited activities (data exfiltration, unauthorised access, credential sharing)
   - Personal device usage guidelines
   - Acceptable AI usage (Claude API, Ollama)

4. **Password and Authentication Requirements**
   - Minimum password complexity: 12+ characters, mixed case, numbers, symbols
   - MFA requirement for all system access
   - SSH key management procedures
   - API key handling (never commit to version control)
   - Password manager usage

5. **Reporting Security Incidents**
   - What constitutes a security incident
   - Reporting channels and escalation path
   - Initial containment steps
   - "See something, say something" culture
   - Non-retaliation policy for good-faith reports

**Assessment:** Completion acknowledgment (digital sign-off)

---

### Module 2: Secure Development Practices (Developers)

**Duration:** 60 minutes
**Format:** Self-paced documentation review + code review checklist sign-off

**Topics:**

1. **OWASP Top 10 for Python/FastAPI**
   - A01: Broken Access Control — endpoint authorization checks
   - A02: Cryptographic Failures — proper use of hashing/encryption
   - A03: Injection — SQL injection, command injection prevention
   - A05: Security Misconfiguration — FastAPI security headers, CORS
   - A07: Authentication Failures — session management, credential storage
   - A09: Logging & Monitoring — structured audit logging patterns

2. **Secure Coding Standards**
   - Input validation on all API endpoints
   - Output encoding for rendered content
   - Parameterised database queries (SQLAlchemy/Supabase)
   - Secrets management (environment variables, never hardcode)
   - Error handling without information leakage
   - Pydantic model validation patterns

3. **Code Review Security Checklist**
   - Authentication and authorisation checks present
   - Input validation on all external inputs
   - No hardcoded credentials or API keys
   - Proper error handling without stack trace exposure
   - Audit logging for sensitive operations
   - Dependency versions pinned and reviewed

4. **Dependency Management and Vulnerability Monitoring**
   - `pip-audit` for Python dependency scanning
   - Trivy for container image scanning
   - Dependabot/Renovate for automated updates
   - CVE monitoring process
   - Approved dependency list maintenance

**Assessment:** Completion acknowledgment + first code review using security checklist

---

### Module 3: Operational Security (Operators)

**Duration:** 60 minutes
**Format:** Self-paced documentation review + procedure walkthrough

**Topics:**

1. **SSH Access and 2FA Usage**
   - SSH key-based authentication (password auth disabled)
   - Fail2ban configuration and monitoring
   - Port knocking or IP whitelisting
   - MFA enforcement for administrative access
   - Session timeout policies

2. **Docker Container Management Security**
   - Container image provenance verification
   - Non-root container execution
   - Resource limits and isolation
   - Docker secrets management
   - Container scanning with Trivy
   - Swarm service update procedures

3. **Log Review and Incident Detection**
   - Loki/Grafana dashboard monitoring
   - Wazuh alert review process
   - Key log patterns indicating compromise
   - Failed authentication monitoring
   - Anomalous network activity detection
   - Escalation triggers and thresholds

4. **Change Management Procedures**
   - Change request and approval workflow
   - Pre-deployment testing requirements
   - Rollback procedures (Docker Swarm service rollback)
   - Post-deployment verification checks
   - Emergency change procedures
   - Configuration drift detection

**Assessment:** Completion acknowledgment + supervised procedure walkthrough

---

### Module 4: Privacy and Data Protection (All Personnel)

**Duration:** 45 minutes
**Format:** Self-paced documentation review + acknowledgment

**Topics:**

1. **POPIA Requirements Relevant to SENTINEL**
   - 8 POPIA conditions for lawful processing
   - Responsible party vs operator obligations
   - Information regulator oversight
   - SENTINEL as processor of building occupant PI

2. **Personal Information Handling Procedures**
   - PI categories in SENTINEL: phone numbers, names, locations, facilities requests
   - Data subjects: building occupants, technicians, administrators
   - Collection minimisation: only collect what is necessary
   - Purpose limitation: FM operations and building management only
   - Storage limitation: 90 days raw, 2 years aggregate

3. **Consent Management Process**
   - First-contact consent flow for WhatsApp/Telegram
   - Three consent types: PI processing, data retention, cross-border transfer
   - Consent withdrawal: "STOP" keyword, immediate effect
   - Consent record immutability and audit trail
   - Consent verification before data processing

4. **Data Breach Notification Requirements**
   - POPIA Section 22: notify Information Regulator and data subjects
   - 72-hour notification window
   - Breach assessment criteria (risk of harm)
   - Notification content requirements
   - Internal incident response triggers

**Assessment:** Completion acknowledgment (digital sign-off)

---

### Module 5: BMS/OT Security (Developers and Operators)

**Duration:** 60 minutes
**Format:** Self-paced documentation review + scenario discussion

**Topics:**

1. **BACnet/Modbus Security Considerations**
   - BACnet/IP: No built-in authentication — network segmentation critical
   - Modbus TCP: Cleartext protocol — VPN or tunnel required for remote access
   - DALI-2: Local bus protocol — gateway security is the perimeter
   - OPC-UA: Certificate-based security — proper PKI management

2. **OT/IT Network Segmentation**
   - BMS controller network isolation
   - Firewall rules between IT and OT zones
   - Jump server access patterns for OT networks
   - VLAN segmentation for building systems
   - DMZ for SENTINEL API (between IT and OT)

3. **BMS Protocol Attack Vectors**
   - BACnet device enumeration and point manipulation
   - Modbus register read/write attacks
   - DALI broadcast command injection
   - Man-in-the-middle on unencrypted protocols
   - Denial of service against building controllers

4. **Safe Device Control Practices**
   - Safety interlock system (SENTINEL SafetyEngine)
   - Temperature range limits (16-28 degrees C)
   - Pressure limits and runtime limits
   - Interlock dependencies (e.g., cooling tower must run before chiller)
   - Audit logging for all control commands
   - Confirmation workflow for manual overrides
   - Emergency shutdown procedures

**Assessment:** Completion acknowledgment + scenario discussion participation

---

## 5. Delivery Methods

| Method | Frequency | Description |
|--------|-----------|-------------|
| **Self-paced review** | Continuous | Module documentation in infrastructure/training/ |
| **Quarterly briefing** | Every 3 months | 30-minute team session covering recent threats and incidents |
| **Ad-hoc alerts** | As needed | Email/Slack notification for urgent security advisories |
| **Onboarding package** | New joiners | Structured first-week training with mentor sign-off |
| **Incident debriefs** | Post-incident | Lessons learned sessions after security events |

---

## 6. Assessment and Completion

### Completion Requirements

- **Read** all assigned module documentation
- **Acknowledge** understanding via digital sign-off (training register)
- **Complete** any module-specific activities (code review, procedure walkthrough)
- **Achieve** minimum pass on any assessed content

### Non-Compliance Consequences

1. **First overdue (30 days):** Email reminder to personnel and line manager
2. **Second overdue (60 days):** Escalation to management, access review triggered
3. **Third overdue (90 days):** System access suspended pending training completion
4. **Documented** in HR record for performance review consideration

---

## 7. Programme Review

| Activity | Frequency | Owner |
|----------|-----------|-------|
| Module content review | Annual | Security lead |
| Training effectiveness assessment | Annual | Management |
| Compliance reporting | Quarterly | Security lead |
| Threat landscape update | Quarterly | Security lead |
| Programme improvement review | Annual | Management |

---

## 8. References

- POPIA (Protection of Personal Information Act, 2013)
- ISO 27001:2022 Annex A.6.3 (Information Security Awareness, Education and Training)
- FSR Domain 4.4 (Human Resource Security)
- OWASP Top 10 (2021)
- NIST Cybersecurity Framework (PR.AT)
- SENTINEL Security Architecture: `docs/08-security/logging-architecture.md`
- SENTINEL Access Controls: `docs/08-security/access-control-implementation.md`

---

*Document maintained by SENTINEL Platform Team. Annual review required.*
