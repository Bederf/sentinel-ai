---
title: SENTINEL Security Control Matrix
version: 1.0
date: 2026-03-22
status: active
frameworks: [ISO-42001, NIST-AI-RMF, EU-AI-Act, FSR-4.7, POPIA]
---

# SENTINEL Security Control Matrix

Derived from existing governance docs + live code audit (2026-03-22).
**Purpose:** Single enforcement reference for gsd:master and coding agents.
Any new code touching a hotspot file MUST satisfy the relevant controls below.

---

## Coverage Summary

| Framework | Controls Mapped | Implemented | Partial/Gap |
|-----------|----------------|-------------|-------------|
| ISO/IEC 42001 | 20 | 18 | 2 |
| NIST AI RMF | 9 | 8 | 1 |
| EU AI Act | 10 | 7 | 3 |
| FSR Domain 4.7 | 6 | 5 | 1 |
| **Total** | **54** | **45 (83%)** | **9 (17%)** |

---

## A. Control Matrix

| ID | Control | Source Doc | Code Area | Enforcement | Proof |
|----|---------|-----------|-----------|-------------|-------|
| AUTH-001 | JWT Bearer Token Validation | auth_middleware.py | `middleware/auth_middleware.py` lines 125-256 | `require_auth(AuthLevel)` dependency | JWT parsing, HS256, 15min access / 7d refresh TTL |
| AUTH-002 | Role Hierarchy & RBAC | control-applicability-matrix.md (ISO-A.2.3) | `models/auth.py` ROLE_HIERARCHY | `AuthContext.has_role()` at endpoint | ADMIN=4, OPERATOR=2, AUDITOR=1, BOT_AGENT=1 |
| AUTH-003 | Brute-Force Login Protection | AUTH-INFRASTRUCTURE-DISCOVERY-REPORT.md | `api/auth.py` lines 100-118 | `@limiter.limit("5/15minutes")` | 5 failures → 15-min lockout per email |
| AUTH-004 | API Key Hashing | AUTH-INFRASTRUCTURE-DISCOVERY-REPORT.md | `middleware/auth_middleware.py` `_API_KEY_STORE` | SHA-256 in-memory store; cache TTL=300s | **PARTIAL** — production migration to Supabase pending |
| AUTH-005 | Webhook Signature Verification | control-applicability-matrix.md (ISO-A.8.2) | `api/whatsapp_webhooks.py`, `security/webhook_auth.py` | HMAC-based payload validation | WhatsApp handshake + hub.challenge echo |
| AUTH-006 | Demo Mode Auth Bypass | CLAUDE.md | `middleware/auth_middleware.py` | Gated by `DEMO_MODE=true` env only | No production deploy with DEMO_MODE; startup check needed |
| APPROVAL-001 | Tier-Based Approval Workflow | control-applicability-matrix.md (ISO-A.10.1, NIST-MP-3.5) | `services/approval_service.py`, `api/approval_workflow.py` | Tier routing: Tier1=advisory, Tier2=human, Tier3=auto | Approval records: `approved_by`, `approved_at`, `execution_result` |
| APPROVAL-002 | HIGH/CRITICAL Locked to Human Approval | control-applicability-matrix.md (NIST-MP-3.5) | `services/tier_routing_engine.py` | Quality gate evaluator caps tier | Confidence cap @ 0.59 for CAP_CONFIDENCE enforcement |
| APPROVAL-003 | Safety Validation in Approval Path | control-applicability-matrix.md (ISO-A.6.2) | `services/approval_service.py` lines 85-100 | SafetyEngine evaluates before execution | **PARTIAL** — placeholder noted in oversight docs line 45 |
| APPROVAL-004 | Approval Token Resolution | whatsapp_webhooks.py | `api/whatsapp_webhooks.py` lines 28-52 | APPROVE/REJECT command parsing | Recommendation ID prefix matching |
| QUALITY-GATE-001 | Mode-Specific Quality Metrics | control-applicability-matrix.md (NIST-GV-1.5) | `services/quality_gate_policy.py` | 14 metrics × 3 modes; frozen policy constants | NORMAL→CAP_CONFIDENCE→SUPPRESS_TIER3→BLOCK_WRITES |
| QUALITY-GATE-002 | Data Freshness & Ingest Error Rate | 08-monitoring-and-metrics.md | `services/quality_gate_policy.py` | Freshness threshold per mode | Fail-closed JSON defaults for live modes |
| QUALITY-GATE-003 | Match Coverage & Commissioning Gates | control-applicability-matrix.md (NIST-MS-1.1) | `quality_gate_evaluator.py` | Truth check pass rate tracked | Consecutive pass days threshold |
| SAFETY-001 | Safety Interlock Rule Engine | control-applicability-matrix.md (ISO-A.6.2) | `services/safety_interlocks.py` | 6 rule types, 3 severity levels | Safety rules JSON; fallback file |
| SAFETY-002 | Temperature Range Validation | safety_interlocks.py | `models/safety_rules.py` | Min/max bounds on device writes | Rule severity: WARNING→BLOCK→ALARM |
| SAFETY-003 | Device Control Kill Switches | control-applicability-matrix.md (NIST-MG-2.4) | `services/approval_service.py` | Global/site/equipment/auto-downgrade | Emergency stop endpoint |
| AUDIT-001 | Immutable Audit Trail | control-applicability-matrix.md (ISO-A.8.2, EU-Art.12) | `services/audit_logger.py` | 7-stage decision pipeline logged; encrypted at rest | `data/audit_log.json`; max 10,000 entries |
| AUDIT-002 | Audit Event Completeness | 02-control-mapping-iso42001.md | `middleware/audit_middleware.py` | All control actions captured | AuditLogEntry: action_type, result_type, actor, timestamp, correlation_id |
| AUDIT-003 | Structured Audit Logging for SIEM | audit_logger.py | `sentinel.audit` logger → Promtail → Loki | JSON-structured events | Prometheus: `sentinel_approval_decisions_total`, `sentinel_safety_violations_total` |
| CRYPTO-001 | Encryption at Rest for Audit Logs | control-applicability-matrix.md (EU-Art.15) | `services/encryption_service.py` | Fernet encryption on sensitive fields | Decryption on load; `encryption_service.enabled` flag |
| CONSENT-001 | POPIA Consent Capture | control-applicability-matrix.md (EU-Art.10) | `services/consent_service.py` | CONSENT_HASH_SALT from env; fail-closed in live | Three consent types; salt required |
| CONSENT-002 | Consent Withdrawal (STOP command) | POPIA-data-subject-rights-workflow.md | `api/consent.py` | STOP message → withdrawal | Phone number hashing; 90-day raw + 2-year aggregate |
| CONSENT-003 | DSR SLA (30 days) | POPIA-data-subject-rights-workflow.md | `api/privacy.py` | Auto-expired after due date | `data/privacy_requests.json`; status tracking |
| MONITORING-001 | Prometheus Metrics | 08-monitoring-and-metrics.md | `api/metrics.py` | 16 metric families; scrape @ 30s | **GAP** — endpoint unauthenticated, exposes operational state |
| MONITORING-002 | Quality Gate Metrics | 08-monitoring-and-metrics.md | `services/quality_gate_evaluator.py` | `sentinel_quality_gate_evaluations_total` | Site-level pass/warn/fail |
| MONITORING-003 | Recommendation Tier Tracking | 08-monitoring-and-metrics.md | `services/tier_routing_engine.py` | `sentinel_recommendations_total` | Tier/action labels prove Tier1 advisory-only |
| MONITORING-004 | Safety Violation Tracking | 08-monitoring-and-metrics.md | `services/safety_interlocks.py` | `sentinel_safety_violations_total` | Per site + equipment type |
| RISK-001 | AI Risk Classification | control-applicability-matrix.md (EU-Art.9) | All API endpoints | Feature classification: MINIMAL/LIMITED/HIGH | RISK-003 (Tier 3) flagged HIGH — pending legal review |
| POLICY-001 | AI Management Policy (4-mode lifecycle) | control-applicability-matrix.md (ISO-A.2.2) | `docs/ai-governance/` + write-policy-and-rollout.md | QualityGatePolicy thresholds + EnforcementAction routing | Simulation→shadow_live→live_control→automatic |
| POLICY-002 | Human Oversight Requirements | control-applicability-matrix.md (ISO-A.10.1, EU-Art.14) | `services/approval_service.py` | Tier 2 mandatory; HIGH/CRITICAL locked forever | Approval: identity, timestamp, rationale, safety result |

---

## B. Hotspot Files

Files that sit at real control boundaries. Any PR touching these requires explicit control verification.

| File | Boundary | Risk | Critical Controls |
|------|----------|------|------------------|
| `middleware/auth_middleware.py` | All authentication | CRITICAL | AUTH-001, AUTH-002, AUTH-006 |
| `models/auth.py` | Role definitions | CRITICAL | AUTH-002 |
| `services/approval_service.py` | Approval + safety gate | CRITICAL | APPROVAL-001, APPROVAL-003, SAFETY-003 |
| `services/safety_interlocks.py` | Device safety | CRITICAL | SAFETY-001, SAFETY-002 |
| `services/quality_gate_evaluator.py` | Quality + enforcement | CRITICAL | QUALITY-GATE-001, QUALITY-GATE-002 |
| `services/tier_routing_engine.py` | Tier allocation | HIGH | APPROVAL-002, RISK-001 |
| `api/whatsapp_webhooks.py` | External webhook auth | HIGH | AUTH-005, APPROVAL-004 |
| `api/sentry_webhooks.py` | Sentry callback auth | HIGH | AUTH-005 (H-1 fixed 2026-03-22) |
| `api/approval_workflow.py` | Approval endpoints | HIGH | APPROVAL-001, POLICY-002 |
| `services/audit_logger.py` | Audit trail | HIGH | AUDIT-001, AUDIT-002, CRYPTO-001 |
| `services/consent_service.py` | POPIA consent | HIGH | CONSENT-001 (H-2 fixed 2026-03-22) |
| `api/auth.py` | Login / token issuance | HIGH | AUTH-001, AUTH-003 |
| `api/remote_commands.py` | Role extraction | HIGH | AUTH-002 (C-1 fixed 2026-03-22) |
| `api/autonomous.py` | Autonomous decisions | HIGH | APPROVAL-001, POLICY-002 (C-2 fixed 2026-03-22) |
| `api/metrics.py` | Prometheus exposure | MEDIUM | MONITORING-001 (GAP — unauthenticated) |
| `startup/middleware.py` | TESTING bypass | MEDIUM | AUTH-006 (M-1 fixed 2026-03-22) |
| `integrations/whatsapp_service.py` | Token comparison | MEDIUM | AUTH-005 (M-2 fixed 2026-03-22) |

---

## C. Open Gaps (Prioritised)

Gaps are controls that exist in policy but lack code enforcement or test proof.

| Priority | Gap | File | Missing | Framework Ref | Suggested Fix |
|----------|-----|------|---------|--------------|---------------|
| ~~**CRITICAL**~~ CLOSED | ~~Safety validation placeholder in approval path~~ | `services/approval_service.py` | Fixed 2026-03-22: fail-open (no adapter→allow) → fail-closed (no adapter→reject, SAFETY-001) | ISO-A.6.2, NIST-MS-2.6 | See commit 3096a1c6 |
| **HIGH** | API key in-memory store not production-ready | `middleware/auth_middleware.py` | Supabase migration with hashed keys + rotation | ISO-A.7.1 | Move `_API_KEY_STORE` to `api_keys` table |
| **HIGH** | Demo mode bypass not startup-gated for production | `middleware/auth_middleware.py` | Startup check: DEMO_MODE=true + prod domain → fail | FSR 4.7 | Add startup validation in `main.py` |
| **HIGH** | Approval endpoint role not proven in tests | `api/approval_workflow.py` | Test: viewer POSTs approve → 403 | ISO-A.10.1 | Add integration test |
| **HIGH** | Tier 2 lock for HIGH/CRITICAL not tested | `services/tier_routing_engine.py` | Test: RISK_HIGH + confidence=0.9 → tier=TIER_2 (never TIER_3) | NIST-MP-3.5 | Add parametrised test |
| **HIGH** | Safety rules enforcement not proven on device writes | `repositories/safety_rules_repository.py` | Integration test: temp > 45°C approval → BLOCKED | ISO-A.6.2 | Add end-to-end safety test |
| **MEDIUM** | `/metrics` endpoint unauthenticated | `api/metrics.py` | AuthLevel.AUDITOR guard or rate limit | NIST-MS-2.8 | `require_auth(AuthLevel.AUDITOR)` or scrape token |
| **MEDIUM** | Audit log has no rotation / archival | `services/audit_logger.py` | Monthly archival to immutable storage | ISO-A.8.2 | Implement log rotation + 12-month retention |
| **MEDIUM** | Decision events not linked by correlation ID | `services/decision_event_logger.py` | correlation_id threaded through all emit calls | ISO-A.8.2, EU-Art.12 | Add param; link audit_logger entries |
| **MEDIUM** | MFA enforcement for ADMIN not tested | `api/auth.py` | Test: ADMIN login without MFA → 403 MFA required | ISO-A.2.3 | Add MFA regression test |
| **MEDIUM** | BOT_AGENT rejected from control endpoints not tested | `models/auth.py` | Test: bot agent POSTs approval → 403 | Phase 120-03 | Add role boundary test |

---

## D. Recently Fixed (2026-03-22)

| Finding | File | Fix |
|---------|------|-----|
| CRITICAL: Safety validation fail-open | `services/approval_service.py` | No-adapter path now returns `is_safe=False` (SAFETY-001); was `is_safe=True` |

| Finding | File | Fix |
|---------|------|-----|
| C-1: Role escalation via X-User-Role header | `api/remote_commands.py` | Reads `request.state.auth.role.value` only |
| C-2: No role guard on autonomous POSTs | `api/autonomous.py` | All 5 POSTs use `Depends(require_role(2))` |
| H-2: Hardcoded POPIA consent salt | `services/consent_service.py` | `CONSENT_HASH_SALT` from env; fail-closed in live |
| H-1: Unauthenticated Sentry webhooks | `api/sentry_webhooks.py` | `_require_sentry_secret()` with `hmac.compare_digest` |
| M-1: TESTING bypass in all environments | `startup/middleware.py` | Guarded by `not settings.is_live_mode` |
| M-2: Timing attack on WhatsApp token | `integrations/whatsapp_service.py` | `hmac.compare_digest` |

---

## How to Use This Matrix

**In gsd:master Architecture Challenge:**
> Before executing any plan, check if the modified files appear in Section B (Hotspots).
> If yes, the plan must satisfy the listed controls. Missing enforcement = BLOCKER.

**In code review / PR:**
> If a PR modifies a hotspot file, verify the relevant control column is still satisfied.
> A PR that removes `require_auth` from an approval endpoint is a hard block.

**In test design:**
> Section C (Gap List) is the backlog for abuse-case tests.
> Each gap must have one concrete test before it can be closed.

**Update cadence:**
> Update this file after any security fix, new hotspot file added, or gap closed.
> Version bump required when a new framework mapping is added.
