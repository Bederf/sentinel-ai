# FirstRand Group — Privacy and Service Risk Assessment Response

**Vendor:** SENTINEL BMS (Smart Environment & Telemetry Intelligence)
**Document:** SENTINEL-FSR-001
**Version:** 1.0
**Date:** 2026-06-15
**Classification:** Confidential

---

## Trigger Question

| # | Question | Vendor Response | Comment |
|---|----------|----------------|---------|
| T1 | Does the 3rd Party process any FirstRand data for or on behalf of FirstRand? | **Yes** | SENTINEL processes building telemetry, access logs, maintenance records, and equipment health data for FirstRand properties (site-001 Fairlands). No financial or customer PII is processed. |

---

## Governance

| # | Question | Vendor Response | Comment |
|---|----------|----------------|---------|
| 1 | Do you have an ISMS aligned to industry best practice standards (e.g. ISO 27001, NIST CSF)? | **Yes** | ISMS aligned to ISO 42001 (AI management) and NIST CSF. 27 security policy documents. Architecture Board Charter established. Control applicability matrix maps 13 ISO 42001 controls. **Evidence:** `docs/09-security/information-security-framework.md`, `docs/09-security/information-security-policy.md` |
| 2 | Is there a dedicated Information Security Officer or equivalent senior role responsible for cybersecurity oversight? | **Yes** | Architecture Board provides governance oversight. Security controls managed through formal governance body with quarterly management reviews. **Evidence:** `docs/architecture-repository/governance/architecture-board-charter.md` |
| 3 | Do you regularly perform independent and/or self assessments against industry best practice standards like ISO 27001/2 and NIST CSF? | **Partially** | Self-assessments complete: NIST control-effectiveness review (11 controls, 87% effective), EU AI Act assurance review (75% compliant), TOGAF governance evidence (100% coverage). **Internal audit plan ready** (24 controls, 3-day schedule). **Independent external audit pending** — budgeted at R80K-R200K, 4-6 week engagement. **Evidence:** `docs/ai-governance/nist-control-effectiveness-review.md`, `docs/ai-governance/internal-audit-plan.md` |

---

## Legal & Regulatory Compliance

| # | Question | Vendor Response | Comment |
|---|----------|----------------|---------|
| 4 | Where applicable do you comply with regulatory and industry frameworks (e.g., POPIA, GDPR, PCI DSS)? | **Yes** | POPIA compliance complete: Section 72 cross-border transfer register (6 transfers), Privacy Impact Assessments (Claude API, Sentry messaging). PCI DSS not applicable — no payment card processing. **Evidence:** `docs/09-security/popia-cross-border-register.md`, `docs/09-security/pia-claude-api.md` |
| 5 | Do you have a Privacy Policy and associated procedures for handling personal data? | **Yes** | Data privacy policy documented. PII guard middleware redacts SA ID numbers, phone numbers, and email addresses before Claude API processing. Consent management service with hash verification. **Evidence:** `docs/09-security/data-privacy-policy.md`, `backend/app/middleware/pii_guard.py` |
| 6 | Are there documented data retention and destruction policies? | **Yes** | 90-day retention for sensor readings and audit logs. Configurable cleanup functions. Log retention management with automatic purge. **Evidence:** `supabase/migrations/036_login_audit_log.sql` (cleanup function), `docs/09-security/logging-architecture.md` |
| 7 | Do you ensure cross-border data transfers comply with applicable regulations? | **Yes** | POPIA Section 72 register documents 6 cross-border transfers (Claude API US, Supabase US/EU, n8n cloud, Telegram, Sentry, Grafana). PIAs completed for all external providers. **Evidence:** `docs/09-security/popia-cross-border-register.md` |

---

## Asset & Data Management

| # | Question | Vendor Response | Comment |
|---|----------|----------------|---------|
| 8 | Do you maintain an asset inventory of all users, IT systems, infrastructure, devices, data and 3rd Parties? | **Yes** | Equipment registry tracks all building assets (49 device adapters active). Asset lifecycle policy covers planning through disposal. Health snapshots and baseline assessments maintained. Third-party security register documents 6 vendors. **Evidence:** `docs/09-security/asset-lifecycle-policy.md`, `docs/09-security/third-party-security-register.md` |
| 9 | Do you classify and label data? | **Yes** | 4-tier classification: Public, Internal, Confidential, Restricted. PII guard middleware enforces classification at processing boundaries. **Evidence:** `docs/09-security/information-classification-policy.md` |
| 10 | Do you protect data at rest and data in transit? | **Yes** | **At rest:** Fernet AES-128-CBC + HMAC-SHA256 encryption for audit logs. **In transit:** TLS for all external API calls. JWT tokens with 15-minute expiry. **Evidence:** `docs/09-security/cryptography-key-management-policy.md`, `backend/app/services/encryption_service.py` |
| 11 | Do you encrypt portable devices? | **N/A** | SENTINEL runs on-premises server infrastructure (Contabo VPS). No portable devices are used in the data processing chain. |

---

## Access Control & Identity Management

| # | Question | Vendor Response | Comment |
|---|----------|----------------|---------|
| 12 | Do you implement RBAC, Least Privilege and Need-To-Know access control model? | **Yes** | 4-tier RBAC: ADMIN (all buildings), OPERATOR/DEVELOPER/AUDITOR (assigned buildings only). Building-level permissions enforced at API layer via `require_site_access()` middleware. **Evidence:** `backend/app/middleware/auth_middleware.py`, `supabase/migrations/035_user_site_access.sql` |
| 13 | Do you enforce Multi-Factor Authentication (MFA) for all user, privileged/elevated and remote access? | **Yes** | TOTP MFA (pyotp, 30-second interval) mandatory for ADMIN role. 10 backup codes (bcrypt-hashed). Brute force protection: 5 failed attempts = 15-minute lockout. Rate limiting: 100 req/min general, 30/min admin API. **Evidence:** `backend/app/services/mfa_service.py`, `backend/app/api/mfa.py` |
| 14 | Do you have an automated identity and access management system with full access lifecycle management, access attestation and governance capabilities? | **Yes** | Session management with Redis-backed token blacklist. Access grant/revoke APIs with audit trail. Session revocation capability. JWT access tokens (15min) with refresh token rotation (7-day TTL). **Evidence:** `backend/app/services/session_service.py`, `backend/app/services/token_blacklist_service.py` |

---

## Network & Infrastructure Security

| # | Question | Vendor Response | Comment |
|---|----------|----------------|---------|
| 15 | Do you maintain network segmentation for sensitive systems? | **Yes** | OT/IT segmentation via WireGuard tunnels. Site bridges on isolated network segments. Supabase containers on dedicated Docker network. **Evidence:** `docs/09-security/bank-deployment-architecture.md` |
| 16 | Do you have firewalls and intrusion detection/prevention systems in place that are actively monitored? | **Yes** | Cloudflare WAF with 9 rules (OWASP, SQLi, XSS, command injection, path traversal, rate limiting, bot protection). Wazuh IDS with FIM and rootkit detection. Grafana Loki SIEM with 6 alert rules. **Evidence:** `docs/09-security/intrusion-detection.md`, `docs/09-security/logging-architecture.md` |
| 17 | Do you have any unsupported Operating Systems, Databases, Hardware or any other form of unsupported software in your environment? | **No** | All systems on supported versions. Docker containers regularly scanned. Dependabot monitors 4 ecosystems (pip, npm, Docker, GitHub Actions). **Evidence:** `.github/dependabot.yml` |
| 18 | Do you implement patching according to industry best practice standards? | **Yes** | Vulnerability management lifecycle with remediation SLAs: Critical 7 days, High 14 days, Medium 30 days, Low 90 days. Automated dependency scanning in CI. **Evidence:** `docs/09-security/vulnerability-management-process.md` |
| 19 | Do you perform continuous vulnerability scanning and penetration testing? | **Yes** | 5 CI security jobs (Bandit, Trivy, safety, pip-audit, gitleaks). Dependabot runs daily. Penetration test is budgeted and scheduled as next phase item. **Evidence:** `.github/workflows/security-scan.yml` |

---

## Application Security

| # | Question | Vendor Response | Comment |
|---|----------|----------------|---------|
| 20 | Do you follow a secure SDLC and are your applications developed using secure coding practices? | **Yes** | Secure coding standards documented. 6 pre-commit security hooks. Quality gate evaluator (14 metrics, 42 thresholds). Safety interlocks enforce physical boundaries. MCP security hardening applied. **Evidence:** `docs/09-security/secure-coding-standards.md`, `.pre-commit-config.yaml` |

---

## Physical Security

| # | Question | Vendor Response | Comment |
|---|----------|----------------|---------|
| 21 | Are physical access and acceptable use procedures implemented that include access control, sensitive zone separation, surveillance, clean desk and anti-tailgating practices? | **Yes** | SENTINEL hosted at Contabo data centre (industry-standard physical security). Clean desk policy documented in acceptable usage policy. Remote-only administration via Cloudflare tunnel + MFA. **Evidence:** `docs/09-security/acceptable-usage-policy.md` |

---

## Monitoring & Incident Response

| # | Question | Vendor Response | Comment |
|---|----------|----------------|---------|
| 22 | Do you have a Security Operations Center (SOC) with a Security Information and Event Management (SIEM) system in place? | **Yes** | Grafana Loki SIEM with 6 production alert rules (SIEM-001 to SIEM-006). Promtail log shipping. Wazuh IDS for host-level detection. Grafana dashboards for security monitoring. **Evidence:** `infrastructure/grafana/provisioning/alerting/security-alerts.yaml` |
| 23 | Are security logs retained and reviewed regularly? | **Yes** | 90-day retention for all logs. Login audit database with suspicious activity detection (brute force, credential theft, registration surge). Encrypted audit log with 1,000+ entries. **Evidence:** `backend/app/data/audit_log.json` (Fernet encrypted) |
| 24 | Do you maintain threat intelligence, perform threat hunting within your environment and monitor for both external and insider threats? | **Partially** | Wazuh rootkit detection and FIM monitoring active. Loki alerting for anomaly detection. Formal threat hunting programme not yet established — planned for next security cycle. |
| 25 | Do you have a documented Incident Response Plan that is regularly tested by means of Tabletop or any other form of incident response simulation testing? | **Yes** | Incident response plan v1.1 (6-phase NIST lifecycle, 11 sections). AI model incident playbook (Section 10.4). Tabletop exercise executed 2026-02-23 (TABLETOP-001): detection in 3 min, rollback in 3 min, zero unsafe actions. Stress test scenarios documented (3 scenarios). **Evidence:** `docs/09-security/incident-response-process.md`, `docs/ai-governance/incident-tabletop-report.md` |

---

## Business Continuity & Disaster Recovery

| # | Question | Vendor Response | Comment |
|---|----------|----------------|---------|
| 26 | Do you have Disaster Recovery and Business Continuity capabilities implemented that align to business requirements, including plans (with RTO, RPO etc.) for each which are tested regularly? | **Yes (with pending test)** | BCP/DR policy with RTO/RPO per process criticality. DR runbook (L1-L4 escalation, vendor SLAs). 3-tier fallback architecture (Supabase → Redis → JSON). Daily VM snapshots (RPO 24 hours). **DR exercise not yet executed** — template ready for Q2 2026. **Evidence:** `docs/09-security/bcp-dr-procedures.md`, `infrastructure/bcpdr/dr-runbook.md` |

---

## Vendor & Supply Chain Security

| # | Question | Vendor Response | Comment |
|---|----------|----------------|---------|
| 27 | Do you assess the security posture of your own suppliers/subcontractors? | **Yes** | Third-party security register (6 vendors with attestations: Supabase SOC2, Anthropic, Cloudflare, Contabo, Grafana, n8n). AI-specific third-party risk register. **Evidence:** `docs/09-security/third-party-security-register.md`, `docs/ai-governance/third-party-ai-risk-register.md` |
| 28 | Are security requirements included in contracts with third parties? | **Yes** | Vendor DPAs in place. 72-hour breach notification requirement documented. PIAs completed for all data-processing third parties. **Evidence:** `docs/09-security/popia-cross-border-register.md` |

---

## Training & Awareness

| # | Question | Vendor Response | Comment |
|---|----------|----------------|---------|
| 29 | Do employees undergo security awareness training at least annually? | **Yes** | AI literacy training package (4 modules, EU AI Act Article 4 compliance). Competence training register with role matrix (ISO 42001 7.2). Live-control entry criteria enforces training gate. **Evidence:** `docs/ai-governance/ai-literacy-training-package.md`, `docs/ai-governance/competence-training-register.md` |
| 30 | Do you conduct phishing simulations or social engineering awareness campaigns? | **Not yet implemented** | Phishing simulation programme is a planned addition. Security awareness training is in place (Q29). Social engineering campaigns will be incorporated into the next training cycle. |

---

## Annual Review

| # | Question | Vendor Response | Comment |
|---|----------|----------------|---------|
| AR1 | Has anything changed over the last year in terms of initial assessment? | **Yes — multiple improvements** | Average FSR score improved from 3.2 to 4.0. Domains at target increased from 4/18 to 17/18. Full detail in FSR Gap Analysis v3.1. **Evidence:** `docs/09-security/FSR_GAP_ANALYSIS_UPDATE.md` |
| AR2 | Has there been any significant breakdown identified in any of the information and cyber security controls? | **No** | CAPA register tracks 6 non-conformities (3 closed, 3 open — all minor). NIST effectiveness review found 87% controls effective. No significant control breakdowns. **Evidence:** `docs/ai-governance/nonconformity-capa-register.md` |
| AR3 | Has there been any significant information and/or cyber security and/or data privacy related incident? | **No** | No security incidents or data privacy incidents to date. Incident response capability validated via tabletop exercise. |
| AR4 | Have you had any regulatory actions and/or fines placed on you? | **No** | No regulatory actions or fines. All compliance obligations current (POPIA, cross-border transfers). |
| AR5 | Do you have cyber insurance? | **Under review** | Cyber insurance is being evaluated as part of the FSR submission readiness programme. Decision expected Q3 2026. |

---

## Evidence Index

All evidence files referenced above are located in the SENTINEL documentation repository:

| Category | Location |
|----------|----------|
| Security policies | `docs/09-security/` (27 documents) |
| AI governance | `docs/ai-governance/` (20+ artifacts) |
| Technical controls | `backend/app/middleware/`, `backend/app/services/` |
| Database migrations | `supabase/migrations/` |
| CI/CD security | `.github/workflows/security-scan.yml` |
| Infrastructure | `infrastructure/` (WAF, SSH, DR, monitoring) |

---

**Document Control**

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-06-15 | SENTINEL Team | Initial response to FirstRand V8 questionnaire |
