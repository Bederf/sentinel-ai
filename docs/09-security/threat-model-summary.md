---
title: "Threat Model Summary"
type: "security-summary"
status: "current"
version: "1.0"
created: "2026-03-14"
updated: "2026-03-14"
owner: "SENTINEL Platform Team"
classification: "Internal"
---

# Threat Model Summary

## 1. Purpose

This document provides the one-page threat model summary for the SENTINEL BMS Intelligence Platform. It is the concise security view used for design review, production readiness, and audit conversations.

It answers five questions:

1. What assets are being protected?
2. What trust boundaries exist?
3. What attacks are considered realistic?
4. What controls mitigate those attacks?
5. What behavior is explicitly not allowed?

This summary complements, but does not replace, the detailed controls in:

- `docs/09-security/information-security-risk-register.md`
- `docs/09-security/application-security-policy.md`
- `docs/09-security/application-security-pipeline.md`
- `docs/09-security/logging-architecture.md`
- `docs/09-security/access-control-implementation.md`

## 2. Scope

In scope:

- FastAPI backend, React frontend, AI and ML services, MCP tools, BMS connectors, Supabase integration, messaging integrations, audit logging, and production operations

Out of scope:

- Third-party provider internals such as Cloudflare, Supabase managed internals, Anthropic/OpenAI infrastructure, and customer-side building network devices outside the SENTINEL control boundary

## 3. Protected Assets

The primary assets are:

- Building control capability for HVAC, lighting, power, and safety-adjacent workflows
- Building telemetry, equipment state, alerts, work orders, and operational history
- Personal information for users, technicians, and building occupants
- Secrets, tokens, signing keys, and integration credentials
- Audit evidence, safety evidence, and security logs
- AI outputs, recommendations, and operator decisions made from those outputs
- Platform availability and integrity

## 4. Trust Boundaries

The main trust boundaries are:

- Public/client traffic to frontend and API
- Authenticated user context to privileged operator or admin actions
- AI model outputs to tool execution and control actions
- Application services to Supabase, Redis, external APIs, and messaging platforms
- IT platform components to OT/BMS device control surfaces
- Local repo configuration to deployed runtime configuration

The highest-risk boundary is the transition from analysis or recommendation into real control action.

## 5. Threat Actors

Relevant threat actors are:

- External attackers targeting internet-facing endpoints
- Authenticated users exceeding their intended privileges
- Compromised accounts or leaked API keys
- Malicious or malformed prompts, emails, documents, or tool inputs
- Insider misuse or operator error
- Supply-chain compromise through dependencies or images
- Infrastructure or provider failure causing unsafe degradation

## 6. Threat Summary

| Threat | Example attack path | Primary mitigations |
|---|---|---|
| Spoofing | Stolen JWT, API key misuse, impersonated technician | JWT auth, RBAC, token expiry, refresh flow, API key controls, access reviews |
| Tampering | Unauthorised config change, unsafe device write, audit log manipulation | Change control, safety interlocks, approval workflow, audit logging, file integrity monitoring |
| Repudiation | User denies issuing command or approving action | Structured audit logs, before/after state capture, identity attribution, decision event logging |
| Information disclosure | PI leakage in logs, model prompts, exports, or messaging | PII sanitization, data minimisation, POPIA controls, access control, secret handling standards |
| Denial of service | API flooding, provider outage, queue overload | Rate limiting, WAF, circuit breakers, monitoring, fallback modes, scheduler controls |
| Elevation of privilege | Standard user reaches admin or control paths | RBAC, role checks, MCP tool security registry, narrow service interfaces, protected write tools |
| Prompt injection / tool abuse | User or email tries to coerce model into unsafe actions | Prompt/input guards, tool allow-listing, human approval gates, refusal rules, no raw ORM access from agents |
| Unsafe autonomous control | Model or service issues damaging building command | SafetyEngine validation, bounded write constraints, operator approval, rollback patterns, live-mode gates |
| Supply chain compromise | Vulnerable dependency, poisoned image, leaked secret in repo | Pre-commit hooks, CI security scans, dependency review, Trivy, Gitleaks, pinned versions |
| Monitoring failure / blind operation | Alerts or metrics fail silently | Prometheus/Grafana/Loki stack, audit logs, target health checks, operational review |

## 7. Security Posture Statement

SENTINEL is designed around the following security position:

- Analysis and recommendation are less trusted than authenticated business logic.
- Tool execution is more restricted than model generation.
- Device control is more restricted than tool execution.
- Production writes must stay inside explicit safety boundaries.
- Every security-relevant action must be attributable to an identity, service, or system process.
- When the system is uncertain, degraded, or outside policy, it must fail closed or return a clear error rather than guess.

## 8. Explicitly Not Allowed

The following behavior is explicitly prohibited:

- AI agents directly querying raw ORM or unrestricted SQL
- AI outputs bypassing RBAC, approvals, or safety interlocks
- Control commands outside configured safety limits
- Silent use of cloud AI where policy requires local-only or consent-gated handling
- Logging secrets, passwords, tokens, or unredacted sensitive PI
- Treating email, uploaded content, or prompt text as trusted instructions
- Disabling or bypassing audit logging for control or security-relevant actions
- Using `DEMO_MODE` as a production authorization bypass

## 9. Residual Risks

The main residual risks currently accepted or tracked are:

- Single-host deployment remains a resilience constraint
- Shared operational dependencies still exist during migration phases
- Cloud and network dependencies can still degrade AI or data services
- Human misconfiguration remains possible despite policy and review gates
- Documentation and deployed-state drift can weaken audit confidence if not actively maintained

These risks must stay in the risk register and be reviewed during quarterly security review and after major architecture changes.

## 10. Required Evidence

The minimum evidence expected alongside this threat model is:

- Current risk register
- Security pipeline and scan results
- Access control and RBAC implementation evidence
- Audit logging and monitoring evidence
- Safety interlock and approval workflow evidence
- Incident response and change control records

## 11. Review Trigger

This summary must be reviewed when any of the following occur:

- New external integration
- New control capability or autonomous action path
- New AI routing or tool execution path
- Major auth, tenancy, or data-handling change
- Any P1 or P2 security or safety incident
