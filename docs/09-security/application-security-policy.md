# Application Security Policy

SENTINEL BMS Intelligence Platform

**Document Classification:** Confidential
**FSR Domain:** 4.9 - Application Security
**Version:** 1.0
**Effective Date:** 2026-02-04
**Review Cadence:** Annual, or upon major architecture change
**Owner:** Information Security Officer
**Approved By:** SENTINEL Product Owner

---

## 1. Purpose

This policy defines the mandatory security requirements for all custom-developed software within the SENTINEL BMS Intelligence Platform. It establishes security gates at each phase of the Software Development Lifecycle (SDLC), sets standards for code review, third-party component management, web application firewall configuration, penetration testing, and BMS-specific security controls.

The policy ensures that application security is embedded by design, not added as an afterthought, and that SENTINEL meets the requirements of FSR Domain 4.9 (Application Security) for FirstRand Group supplier onboarding.

## 2. Scope

This policy applies to all custom-developed software components of the SENTINEL platform:

| Component | Technology | Description |
|-----------|-----------|-------------|
| **FastAPI Backend** | Python 3.11 | REST API, business logic, device abstraction, safety engine |
| **React Frontend** | TypeScript, Vite | Dashboard, control panel, monitoring interfaces |
| **ML Pipeline** | TensorFlow, scikit-learn, lifelines | LSTM forecasting, autoencoder anomaly detection, survival analysis |
| **MCP Server** | Python (SIMBIOT) | 23 tools for building management via dual transport |
| **BMS Connectors** | Python | BACnet/IP, Modbus TCP, DALI-2 protocol adapters |
| **Integration Bridge** | Python | MRI Evolution CAFM connector, log parsers, point matchers |
| **Telegram/WhatsApp Bots** | Python (Sentry) | Conversational interface for technician queries |

This policy does **not** apply to third-party commercial off-the-shelf (COTS) software or managed services (Cloudflare, Supabase, Anthropic Claude API), which are covered by the Third-Party Security Management Policy.

## 3. SDLC Security Gates

Security checkpoints are mandatory at each phase of the development lifecycle. No code may progress to the next phase without satisfying the gate requirements for the current phase.

### 3.1 Gate Summary

| Phase | Gate | Required Activities | Tools / Evidence | Gate Keeper |
|-------|------|---------------------|------------------|-------------|
| **Design** | Architecture Security Review | Threat model (STRIDE), security architecture review for integrations | STRIDE threat model document, architecture review notes | Security Officer |
| **Development** | Shift-Left Security | Secure coding standards compliance, pre-commit hooks pass, local security scan | Pre-commit hooks, `scripts/security-scan.sh` output | Developer |
| **Build** | Automated Security Scan | SAST, dependency scan, container scan, secrets detection - all pass | GitHub Actions `security-scan.yml` results | CI/CD Pipeline (automated) |
| **Test** | Security Testing | Security test cases pass, DAST for web-facing endpoints | Test results, DAST report | QA / Security |
| **Deploy** | Production Readiness | WAF rules verified, no debug mode, production config reviewed | Deployment checklist, WAF config screenshot | Security Officer |
| **Monitor** | Runtime Security | IDS active, audit logging operational, API anomaly detection | Wazuh alerts, Grafana/Loki dashboards | Operations |

### 3.2 Design Gate

Before implementation of any new feature or integration begins:

1. **Threat Modelling (STRIDE):** Identify Spoofing, Tampering, Repudiation, Information Disclosure, Denial of Service, and Elevation of Privilege threats for the feature. Document in a threat model table with mitigations.
2. **Security Architecture Review:** For features involving external integrations (BACnet, Modbus, DALI, CAFM APIs, Claude API), conduct a security architecture review covering:
   - Data flow diagrams showing trust boundaries
   - Authentication and authorisation mechanisms
   - Network segmentation requirements (OT/IT boundary for BMS protocols)
   - Data classification of processed information
3. **Privacy Impact Assessment:** For features processing personal information (occupant data, technician details, contact information), conduct a PIA per the Data Privacy Policy.

### 3.3 Development Gate

During active development, the following controls are enforced:

1. **Secure Coding Standards Compliance:** All code must conform to the [Secure Coding Standards](./secure-coding-standards.md). Developers are responsible for self-review against these standards before committing.
2. **Pre-commit Hooks (Mandatory):** The following pre-commit hooks must be installed and active on every developer workstation. Commits that bypass these hooks are prohibited.

   | Hook | Purpose | Reference |
   |------|---------|-----------|
   | `detect-secrets` | Entropy-based and regex secrets scanning | `.pre-commit-config.yaml` |
   | `check-hardcoded-secrets` | Blocks API key patterns (`sk-ant-*`, `eyJhbGci*`) | `.pre-commit-config.yaml` |
   | `check-env-files` | Prevents `.env` files from being committed | `.pre-commit-config.yaml` |
   | `validate-safety-rules` | Validates safety rules JSON structure and required fields | `.pre-commit-config.yaml` |
   | `check-debug-patterns` | Warns about debug statements (`pdb`, `breakpoint`, `console.log`) | `.pre-commit-config.yaml` |
   | `check-equipment-id-format` | Validates v2.0 naming convention compliance | `.pre-commit-config.yaml` |

3. **Local Security Scanning:** Developers should run the security scan script before pushing:
   ```bash
   ./scripts/security-scan.sh        # Full scan
   ./scripts/security-scan.sh --quick # Quick scan (skip container scanning)
   ```

### 3.4 Build Gate

Automated security scanning runs in the CI/CD pipeline on every push to `main`, every pull request to `main`, and on a weekly schedule (Monday 06:00 UTC).

The pipeline (`.github/workflows/security-scan.yml`) executes 5 parallel security jobs:

| Job | Tool | Scope | Failure Condition |
|-----|------|-------|-------------------|
| **Python SAST** | Bandit | `backend/app/` (excludes `backend/app/data/`) | Any HIGH or CRITICAL finding |
| **Frontend Audit** | npm audit | `frontend/package.json` dependency tree | Any CRITICAL vulnerability |
| **Dependency Check** | pip-audit + Safety | `backend/requirements.txt` | Warning at 5+ vulnerable dependencies |
| **Container Scan** | Trivy | Backend Docker image + filesystem | Any CRITICAL finding in container image |
| **Secrets Detection** | Gitleaks | Full repository history | Any secret detected |

All scan reports are retained for 90 days as GitHub Actions artifacts.

**Build gate failure:** If any job reports a CRITICAL or HIGH finding, the pull request must not be merged until the finding is resolved or a documented exception is approved.

### 3.5 Test Gate

Security testing is conducted as part of the overall test suite:

1. **Security Test Cases:** Dedicated security test cases within the test suite covering:
   - Input validation (injection prevention, boundary testing)
   - Authentication and authorisation enforcement
   - Safety interlock validation (device control safety rules)
   - Error handling (no information leakage)
2. **DAST for Web-Facing Endpoints:** Dynamic Application Security Testing is performed against the deployed application. Key areas tested:
   - OWASP Top 10 vulnerability checks
   - API endpoint enumeration and access control verification
   - Rate limiting effectiveness
   - SSE endpoint security

### 3.6 Deploy Gate

Before deploying to production:

1. **WAF Rules Verification:** Confirm all 9 Cloudflare WAF rules (Phase 63-02) are active and correctly configured:

   | Rule | Type | Description |
   |------|------|-------------|
   | 1 | OWASP Core | OWASP ModSecurity Core Rule Set |
   | 2 | SQL Injection | SQLi detection and blocking |
   | 3 | XSS Prevention | Cross-site scripting detection |
   | 4 | Command Injection | OS command injection blocking |
   | 5 | Path Traversal | Directory traversal prevention |
   | 6 | Rate Limit - Chat | 30 requests/minute per IP on `/api/chat` |
   | 7 | Rate Limit - Control | 20 requests/minute per IP on `/api/devices/*/control` |
   | 8 | Rate Limit - General | 120 requests/minute per IP on all other endpoints |
   | 9 | Bot Protection | Known bad bot user-agent blocking |

2. **Production Configuration Review:**
   - `DEBUG=false` in production environment
   - `DEMO_MODE` appropriate for deployment context
   - No development API keys in production
   - CORS origins restricted to production frontend URL
   - All secrets loaded from environment variables, not hardcoded

3. **Deployment Checklist:** A deployment checklist must be completed and signed off by the Security Officer before each production release.

### 3.7 Monitor Gate

After deployment, continuous security monitoring ensures ongoing protection:

1. **Wazuh IDS:** Host-based intrusion detection system monitoring for:
   - File integrity changes on critical system files
   - Suspicious process execution patterns
   - Log anomaly detection
   - Rootkit detection scans
2. **Application Audit Logging:** All security-relevant events are logged in structured JSON format:
   - Authentication attempts (success and failure)
   - Device control commands (with before/after state)
   - Safety interlock triggers
   - API access patterns
3. **API Usage Anomaly Detection:** Monitoring for unusual API usage patterns:
   - Spike in authentication failures
   - Unusual geographic access patterns
   - Excessive rate limit triggers
   - Access to undocumented endpoints

## 4. Code Review Requirements

### 4.1 General Code Review

All code changes must be reviewed before merging to `main`:

- **Minimum reviewers:** 1 (for non-security changes)
- **Review scope:** Correctness, maintainability, security implications
- **Approval required:** At least one approving review before merge
- **CI/CD must pass:** All automated checks (including security scans) must pass

### 4.2 Security-Sensitive Code Review

Changes to security-sensitive areas require explicit security review notation. Security-sensitive areas include:

| Area | Examples | Additional Requirement |
|------|----------|----------------------|
| Authentication/Authorisation | `require_auth`, `require_role`, JWT handling | Security review notation in PR |
| Device Control Operations | `DeviceInterface.write_point()`, `control_device` tool | Safety review + security review |
| Safety Engine | `SafetyEngine`, safety rules, interlock logic | Safety officer approval |
| Cryptography | Encryption, hashing, key management, TLS configuration | Security officer review |
| API Input Validation | Pydantic models, route parameters, file upload handling | Security review notation |
| Database Queries | Raw SQL, ORM query construction | SQL injection review |
| External API Integration | Claude API, FSI API, messaging platform APIs | Data flow review |

### 4.3 BMS Control Operations Review

All changes to BMS write operations (commands that control building equipment) require additional safety review:

- Changes to `device_abstraction.py`, `mock_devices.py`, or protocol adapters
- Changes to `safety_interlocks.py` or `safety_rules.json`
- Changes to chat tools that invoke device control (`control_device`, `write_device_point`)
- Changes to the MCP server's write tools

Safety review verifies:
- Safety interlocks cannot be bypassed
- Write operations are constrained to Priority 8 (manual override level) for BACnet
- Audit logging captures all write operations with before/after state
- Rate limiting prevents rapid successive commands

## 5. Third-Party Component Management

### 5.1 Automated Dependency Updates

Dependabot is configured (`.github/dependabot.yml`) for automated updates across 4 ecosystems:

| Ecosystem | Directory | Frequency | Review SLA |
|-----------|-----------|-----------|------------|
| Python (pip) | `/backend` | Weekly | Critical: 7 days, High: 14 days |
| Node.js (npm) | `/frontend` | Weekly | Critical: 7 days, High: 14 days |
| GitHub Actions | `/` | Monthly | 14 days |
| Docker | `/backend`, `/frontend` | Monthly | 14 days |

### 5.2 New Dependency Adoption

Before adding a new dependency to the project:

1. **Vulnerability Check:** Run `pip-audit` or `npm audit` to confirm no known vulnerabilities
2. **License Compliance:** Verify the licence is compatible (accepted: MIT, Apache 2.0, BSD, ISC, MPL-2.0; requires review: GPL, LGPL, AGPL)
3. **Maintenance Status:** Confirm the package is actively maintained (last release within 12 months, responsive issue tracker)
4. **Supply Chain Risk:** Prefer well-known packages with large user bases over obscure alternatives
5. **Minimal Scope:** Prefer packages that do one thing well over large frameworks with unnecessary capabilities

### 5.3 Dependency Review Process

- **Weekly:** Review open Dependabot PRs; merge non-breaking security updates promptly
- **Monthly:** Review dependency audit reports for emerging vulnerabilities
- **Quarterly:** Full dependency inventory review - remove unused dependencies

## 6. WAF Configuration Management

### 6.1 Cloudflare WAF Rules

SENTINEL's web application firewall consists of 9 rules deployed via Cloudflare (Phase 63-02):

- **OWASP Core Rule Set** - Comprehensive protection against OWASP Top 10
- **SQL Injection** - Pattern-based SQLi detection
- **XSS Prevention** - Cross-site scripting payload detection
- **Command Injection** - OS command injection blocking
- **Path Traversal** - Directory traversal prevention
- **Rate Limiting (3 rules)** - Endpoint-specific rate limits:
  - Chat endpoint: 30 requests/minute
  - Device control endpoint: 20 requests/minute
  - General endpoints: 120 requests/minute
- **Bot Protection** - Known malicious bot blocking

### 6.2 WAF Rule Review

- **Review cadence:** Quarterly (aligned with quarterly internal vulnerability scan)
- **Review scope:** Rule relevance, false positive analysis, rate limit appropriateness
- **Review owner:** Security Officer
- **Documentation:** WAF review findings recorded in the security audit log

### 6.3 WAF Change Management

Changes to WAF rules require:
1. Documented justification for the change
2. Testing in a non-blocking mode before enforcement
3. Security Officer approval
4. Post-change monitoring for false positives (minimum 72 hours)

## 7. Penetration Testing Requirements

### 7.1 Schedule

| Test Type | Frequency | Timing |
|-----------|-----------|--------|
| Independent Application Security Assessment | Annual | Scheduled during Q1 |
| Pre-FSR Submission Assessment | Before submission | Before each FSR questionnaire submission |
| Ad-hoc Testing | As needed | After significant architecture changes |

### 7.2 Scope

Penetration testing must cover:

- **External attack surface:** All Internet-facing API endpoints (via Cloudflare)
- **Application logic:** Business logic vulnerabilities, authorisation bypasses
- **BMS-specific attacks:** Attempts to bypass safety interlocks, send unauthorised device commands
- **API abuse:** Rate limiting bypass, injection via API parameters
- **Authentication/Authorisation:** Token manipulation, privilege escalation
- **Data exposure:** Sensitive data leakage, error-based information disclosure

### 7.3 Remediation SLAs

Findings from penetration tests follow the same remediation SLAs as vulnerability scans:

| Severity | Maximum Remediation Time |
|----------|------------------------|
| **Critical** | 7 calendar days |
| **High** | 14 calendar days |
| **Medium** | 30 calendar days |
| **Low** | 90 calendar days |

### 7.4 Reporting

Penetration test reports are classified as **Confidential** and stored securely. A remediation plan is created within 5 business days of report receipt. Progress against the remediation plan is tracked and reported monthly.

## 8. BMS-Specific Security Considerations

### 8.1 OT/IT Network Segmentation

SENTINEL operates at the boundary between Operational Technology (OT) networks (BMS/SCADA systems) and Information Technology (IT) networks (API services, databases, web interfaces). Strict segmentation is enforced:

- **OT Network (BMS):** BACnet/IP (UDP 47808), Modbus TCP (port 502), DALI-2 via Tridonic gateway
- **IT Network (API):** FastAPI on port 9095 (behind Cloudflare Tunnel), React frontend on port 9096
- **Segmentation Control:** Docker network isolation between BMS connector containers and API service containers
- **No direct OT-to-Internet path:** BMS protocols are never exposed to the public Internet
- **Data flows one direction:** BMS data flows into SENTINEL (read), write commands flow from SENTINEL to BMS (write) through the safety engine

### 8.2 BACnet/Modbus Write Safety Validation

All write operations to BMS devices are validated through the `SafetyEngine` before execution:

1. **Safety Rule Check:** Every write command is checked against the safety rules engine (`safety_interlocks.py`, `safety_rules.json`)
2. **Severity Enforcement:**
   - `WARNING` - Allow with logged warning
   - `BLOCK` - Prevent execution, return error to user
   - `ALARM` - Prevent execution, trigger alarm notification
3. **BACnet Priority Level:** All BACnet write commands are constrained to Priority 8 (manual override level), preventing SENTINEL from overriding life safety systems (Priority 1-7)
4. **Temperature Safety Range:** All temperature setpoint changes are validated against the 16-28 degrees C safety range

### 8.3 Device Control Audit Trail

Every device control action is recorded in the audit log with:

- **Timestamp** of the command
- **User/system** that initiated the command
- **Device ID** (v2.0 format) and point name
- **Before state** of the controlled parameter
- **After state** (commanded value)
- **Safety validation result** (passed/blocked and which rules triggered)
- **Execution result** (success/failure and error details)

Audit logs are stored separately from application data and are tamper-evident.

## 9. Version History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-02-04 | SENTINEL Security | Initial policy creation |

## 10. Related Documents

- [Secure Coding Standards](./secure-coding-standards.md) - Coding standards for SENTINEL development
- [Vulnerability Management Process](./vulnerability-management-process.md) - Vulnerability lifecycle management
- [Application Security Pipeline](./application-security-pipeline.md) - CI/CD security scanning implementation (Phase 63-03)
- [Vulnerability Management](./vulnerability-management.md) - Scanning tools and schedule implementation (Phase 63-05)
- [Access Control Implementation](./access-control-implementation.md) - Authentication and authorisation (Phase 63-04)
- [Intrusion Detection](./intrusion-detection.md) - IDS deployment (Phase 63-02)
- [Logging Architecture](./logging-architecture.md) - Centralised logging (Phase 63-01)

## 11. FSR Domain 4.9 Compliance Matrix

| FSR Requirement | Implementation | Evidence |
|----------------|---------------|----------|
| Application security policy | This document | `docs/08-security/application-security-policy.md` |
| SDLC security gates | 6 gates defined (Section 3) | Gate definitions with tools at each stage |
| Secure coding standards | Separate document | `docs/08-security/secure-coding-standards.md` |
| Code review with security checkpoints | Section 4 | PR review requirements and security-sensitive areas |
| Automated security testing (SAST/DAST) | Build gate (Section 3.4) | GitHub Actions `security-scan.yml`, 5 security jobs |
| Web application firewall | Section 6 | 9 Cloudflare WAF rules with quarterly review |
| Penetration testing | Section 7 | Annual independent assessment, pre-FSR submission |
| Vulnerability remediation SLAs | Section 7.3 | Critical 7d, High 14d, Medium 30d, Low 90d |
| Third-party component management | Section 5 | Dependabot across 4 ecosystems with review SLAs |
| BMS/OT security controls | Section 8 | OT/IT segmentation, SafetyEngine, audit trail |

---

*Document: Application Security Policy*
*Phase: 64-03 (RISK Governance Foundation)*
*Classification: Confidential*
*Review: Annual or on major architecture change*
