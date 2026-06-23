---
title: "Independent Penetration Test — Scope and Plan"
type: "plan"
status: "draft"
version: "1.0.0"
created: "2026-06-23"
updated: "2026-06-23"
tags: ["sentinel", "penetration-test", "security", "assessment", "scope"]
domain: "security"
audience: "security, bank-it"
complexity: "intermediate"
estimated_read_time: 8
---

# Independent Penetration Test — Scope and Plan

## Status

Internal automated external-surface scan (OWASP ZAP + Kali) completed 2026-06-23. All API/auth/BOLA/injection tests clean. Findings were infra config only (expired origin SSL, API version leak, missing headers) — all fixed.

Independent third-party penetration test is **scoped, budgeted, and planned as the next assurance phase**.

---

## Scope

### In-Scope

| Target | Description |
|--------|-------------|
| SENTINEL REST API | All 20+ routers, authentication, authorization, RBAC enforcement |
| SENTINEL MCP Server | 23 SIMBIOT tools, tool-level authorization, input validation |
| Frontend (React) | XSS, CSRF, session management, DOM manipulation |
| Database (PostgreSQL) | SQL injection vectors, RLS bypass, privilege escalation |
| Authentication | JWT signing, token expiry, API key rotation, MFA enforcement |
| Site isolation (BOLA) | require_site_access() and require_equipment_access() bypass attempts |
| Notification channels | Teams webhook injection, email header injection |
| Reverse tunnel | SSH configuration, port forwarding abuse, unauthorized access |
| Ollama inference | Prompt injection, model sandbox escaping |
| Host hardening | OS patch level, unnecessary services, file permissions |

### Out-of-Scope

| Target | Rationale |
|--------|-----------|
| Physical security | Not applicable (software-only assessment) |
| Social engineering | Not in scope for technical penetration test |
| Third-party cloud services | Covered by vendor SOC 2 / ISO 27001 attestations |
| BMS/OT devices at customer site | Customer-owned infrastructure |

---

## Methodology

| Phase | Activity | Tools |
|-------|----------|-------|
| 1. Reconnaissance | Passive information gathering, endpoint enumeration | nuclei, gobuster |
| 2. Vulnerability scanning | Automated vulnerability detection | OWASP ZAP, nuclei, nikto |
| 3. Manual testing | Business logic flaws, auth bypass, privilege escalation | Burp Suite, custom scripts |
| 4. Exploitation | Controlled proof-of-concept for confirmed findings | Burp Suite, Metasploit |
| 5. Reporting | Executive summary, findings, risk ratings, remediation | — |

---

## Deliverables

1. **Executive Summary** — 1-2 page overview for non-technical stakeholders
2. **Technical Report** — Full findings with CVSS 3.1 scoring, evidence, and remediation steps
3. **Remediation Tracking** — Findings mapped to CAPA register for closure verification

## Remediation SLA

| Severity | Remediation Target |
|----------|-------------------|
| Critical (CVSS 9.0-10.0) | 24 hours |
| High (CVSS 7.0-8.9) | 7 days |
| Medium (CVSS 4.0-6.9) | 30 days |
| Low (CVSS 0.1-3.9) | 90 days |

## Budget

Allocated in next assurance phase. Estimated cost: ZAR 80,000–150,000 for CREST/CHECK-equivalent assessment.

## Next Steps

1. Select approved assessor (CREST/CHECK member preferred)
2. Agree assessment window and scope
3. Provide pre-assessment evidence pack:
   - Architecture overview
   - API documentation
   - Threat model
   - Previous scan results
   - SBOM
4. Schedule remediation window post-assessment
