---
title: "Agentic Security Framework Mapping"
type: "reference"
status: "approved"
version: "1.0.0"
created: "2026-02-19"
updated: "2026-02-19"
author: "SENTINEL Security Office"
tags: ["mcp", "security", "owasp-asi", "mitre-atlas", "cosai", "agentic-ai", "framework-mapping"]
related: ["mcp-security-hardening.md", "logging-architecture.md", "../06-safety-compliance/audit-logging.md"]
domain: "security"
audience: "security-architects, developers, auditors"
complexity: "advanced"
estimated_read_time: 25
---

# Agentic Security Framework Mapping

Formal mapping of SENTINEL's MCP security controls against three agentic AI security frameworks: OWASP ASI Top 10 (2026), MITRE ATLAS Agentic Techniques, and the CoSAI MCP Security Taxonomy. This document identifies coverage status, gaps, and a prioritized hardening roadmap.

---

## 1. Executive Summary

SENTINEL's SIMBIOT MCP Server enforces a **9-layer security pipeline** (including P3.5 prompt injection scanning) with **120 tests** across 4 test suites. This document maps those controls against the three leading agentic security frameworks:

| Framework | Threats Mapped | Full | Partial | N/A | Gap |
|-----------|---------------|------|---------|-----|-----|
| **OWASP ASI Top 10** | 10 | 5 | 3 | 2 | 0 |
| **MITRE ATLAS Agentic** | 14 | 5 | 3 | 5 | 1 |
| **CoSAI MCP Taxonomy** | 12 | 10 | 2 | 0 | 0 |
| **Totals** | **36** | **20** | **8** | **7** | **1** |

**Key finding:** SENTINEL has **full coverage** on 20 of 36 mapped threats (56%), **partial** on 8 (22%), **not applicable** for 7 (19%), and **gaps** on 1 (3%). The P1 prompt injection gap was closed — `scan_arguments_for_injection()` in `schema_validator.py` now scans MCP tool string arguments using the existing `PromptInjectionDetector` (layer P3.5 in the security pipeline).

**Existing controls reference:** [MCP Security Hardening](mcp-security-hardening.md)

---

## 2. OWASP ASI Top 10 Mapping (2026)

The OWASP Agentic Security Initiative (ASI) Top 10 defines the most critical threats to AI agent systems. Each threat is mapped to SENTINEL's existing controls.

| ASI ID | Threat | SENTINEL Control | Coverage | Notes |
|--------|--------|-----------------|----------|-------|
| **ASI01** | Agent Goal Hijacking | Prompt injection guard scans chat input (`prompt_injection_guard.py`) **and** MCP tool string arguments via `scan_arguments_for_injection()` (P3.5 layer) | **FULL** | All string args >10 chars scanned on SSE transport. Stdio trusted. Blocked calls return `INJECTION_BLOCKED` with audit trail. |
| **ASI02** | Tool Misuse | Tool Security Registry + RBAC + approval tokens + JSON schema validation | **FULL** | All 24+ tools classified in registry. Mutating tools require role + module. High-risk tools require approval token. |
| **ASI03** | Identity & Privilege Abuse | Multi-layer auth: SSE transport auth gate → role tiers → site-scoped access → module gating | **FULL** | Per-tool `min_role` and `required_module` enforced. Cross-tenant isolation via per-identity rate limits and approval tokens. |
| **ASI04** | Supply Chain Compromise | SHA-256 manifest hashing for first-party tools; optional pinned hash via `mcp_tool_manifest_hash` setting | **PARTIAL** | Covers tool definition tampering. Does not cover third-party tool vetting (all tools are first-party today). No SBOM for tool dependencies. |
| **ASI05** | Unexpected Code Execution | No code execution tools exposed; `code_search`, `code_fetch`, `code_structure` are read-only | **FULL** | Tools return source text only. No eval/exec capability in any handler. |
| **ASI06** | Memory & Context Poisoning | No persistent agent memory in Sentry MCP path; each tool call is stateless | **N/A** | SIMBIOT operates statelessly — no memory store to poison. Risk re-emerges if persistent memory is added. |
| **ASI07** | Insecure Inter-Agent Communication | Single-agent architecture (Sentry bot only); no agent-to-agent messaging | **N/A** | Not applicable today. Risk re-emerges if multi-agent orchestration is added. |
| **ASI08** | Cascading Hallucination/Failure | Rate limiting (per-identity sliding window) + async timeouts (30s default) + concurrency semaphore | **PARTIAL** | Timeouts and rate limits prevent resource exhaustion. Missing: circuit breaker pattern to stop cascading failures across dependent services. |
| **ASI09** | Human-Agent Trust Boundary | Approval tokens required for high-risk tools (`write_device_point`, `create_building`, `activate_building`) | **FULL** | Explicit human confirmation before destructive actions. Token is single-use, tool-scoped, 60s TTL. |
| **ASI10** | Rogue Agent Detection | Manifest integrity verification + structured audit logging + rate limits | **PARTIAL** | Tampering is detectable via manifest hash. Behavioral anomaly detection (e.g., unusual tool call patterns) does not exist. |

### ASI Coverage Summary

```
FULL     █████████████████████████      5/10  (50%)
PARTIAL  ████████████████               3/10  (30%)
N/A      ████████                       2/10  (20%)
GAP      ░░░░                           0/10  ( 0%)
```

---

## 3. MITRE ATLAS Agentic Techniques Mapping

MITRE ATLAS catalogs adversarial techniques against AI systems. The agentic subset (T0080–T0101) targets tool-using agents. Techniques not relevant to MCP architectures are marked N/A.

| ATLAS ID | Technique | SENTINEL Control | Coverage | Notes |
|----------|-----------|-----------------|----------|-------|
| **T0080** | Context Window Poisoning | No persistent MCP memory; each call is stateless | **N/A** | No stored context to poison. Chat-side context is separate from MCP pipeline. |
| **T0081** | Modify Agent Configuration | SHA-256 manifest hash pinning; optional `mcp_tool_manifest_hash` setting enforced at startup | **FULL** | Runtime tool definition changes are detectable. Pinned hash prevents server start on mismatch. |
| **T0082** | Credential Harvesting from RAG | No RAG pipeline in MCP path; RAG service (`rag_service.py`) is separate from tool execution | **N/A** | MCP tools do not query the RAG index. |
| **T0083** | Credential Extraction from Agent Config | Secret-zero output filter scans all tool output for credential patterns (keys, JWTs, bearer tokens) | **PARTIAL** | Output scanning is comprehensive. **Input arguments are not scanned** for injected credential-harvesting prompts. |
| **T0084** | Discover Agent Capabilities | `tools/list` gated by SSE auth; tool schemas only visible to authenticated users | **FULL** | Unauthenticated users cannot enumerate available tools or their schemas. |
| **T0085** | Data Exfiltration from AI Services | Per-tool RBAC + module gating + site-scoped access; tools only return data within user's authorized scope | **FULL** | A user can only access data for their assigned sites and active modules. |
| **T0086** | Exfiltration via Tool Invocation | Structured audit logging with policy decisions; per-tool argument allowlists | **PARTIAL** | All invocations are logged. **No real-time anomaly alerting** on unusual exfiltration patterns (e.g., rapid data reads). |
| **T0087** | Prompt Injection via Tool Output | Tool outputs are not re-injected into agent prompts within MCP pipeline | **N/A** | SIMBIOT returns tool results directly to the client. No chain-of-thought re-injection. |
| **T0088** | Model Inference Manipulation | Not applicable — SIMBIOT does not perform ML inference in tool handlers | **N/A** | ML inference is handled by separate services, not MCP tools. |
| **T0098** | Tool Credential Harvesting | Secret-zero filter + per-tool `audit_fields` allowlist limits what reaches logs; `secret_zero_risk` flag on sensitive tools | **PARTIAL** | Output credentials are redacted. Input-side scanning for credential-probing arguments is missing. |
| **T0099** | Tool Input Poisoning / Data Poisoning | JSON schema validation per tool + recursive size limits (strings ≤10K chars, arrays ≤1K items) | **FULL** | Malformed or oversized inputs rejected before reaching handlers. |
| **T0100** | Agent UI Manipulation (Clickbait) | MCP returns structured JSON only; no HTML/UI rendering in tool responses | **N/A** | Not applicable — SIMBIOT has no UI rendering surface. |
| **T0101** | Data Destruction via Tool Invocation | Approval tokens required for `write_device_point`; all mutating tools require operator+ role | **FULL** | Destructive operations require explicit human confirmation. |
| **T0102** | Denial of Service via Tool Flooding | Per-identity sliding window rate limits + concurrency semaphore + async timeouts | **PARTIAL** | Effective for single-identity DoS. **No distributed rate limiting** across multiple identities targeting the same resource. |

### ATLAS Coverage Summary

```
FULL     ████████████████████          5/14  (36%)
PARTIAL  ████████████████               4/14  (29%)
N/A      ████████████████████          5/14  (36%)
GAP      ░░░░                           0/14  ( 0%)
```

---

## 4. CoSAI MCP Security Taxonomy Mapping

The Coalition for Secure AI (CoSAI) MCP Security Taxonomy defines 12 categories with ~40 specific threats for MCP server implementations.

| Cat | Threat Area | SENTINEL Control | Coverage | Notes |
|-----|-------------|-----------------|----------|-------|
| **T1** | Authentication & Identity | Multi-credential auth: `X-MCP-Token`, `Authorization: Bearer`, ticket-based SSE auth. Per-identity isolation for rate limits and approvals. | **FULL** | Three auth methods supported. Ticket-based SSE prevents token-in-URL leakage. |
| **T2** | Access Control & Authorization | Tool Security Registry: per-tool `auth_required`, `min_role`, `required_module`. Confused deputy mitigated via `site_id` extraction from auth context (not user input). | **FULL** | Site-scoped access prevents cross-tenant data access. Registry is the single source of truth. |
| **T3** | Input Validation & Sanitization | JSON schema validation per tool + recursive size limits. Schema errors return sanitized messages (no schema exposure). | **FULL** | Every tool has a defined `input_schema`. Validation runs before handler execution. |
| **T4** | Instruction Boundary Enforcement | Prompt injection guard scans chat input **and** MCP tool arguments via `scan_arguments_for_injection()` (P3.5 layer in `schema_validator.py`) | **FULL** | All string args >10 chars scanned on SSE transport. Blocked calls return `INJECTION_BLOCKED` code with audit logging. |
| **T5** | Data Protection & Secret Management | Secret-zero output filter: scans by key name (16 patterns) and value regex (API keys, JWTs, bearer tokens). Redacts matches with `***REDACTED_BY_SECRET_ZERO_FILTER***`. | **FULL** | Output-side protection is comprehensive. Audit logs use per-tool `audit_fields` allowlists. |
| **T6** | Integrity & Verification | SHA-256 manifest hash of all tool definitions. `verify_manifest()` compares runtime hash with initial. Optional pinned hash for production. | **FULL** | Tool definition tampering is detectable at runtime and preventable at startup. |
| **T7** | Session & Transport Security | Ticket-based SSE: single-use UUID tickets (30s TTL), query-param token rejection in production, JSON-RPC envelope validation, CORS headers. | **FULL** | Tickets prevent replay attacks. `?token=` rejected to avoid URL leakage. |
| **T8** | Network Isolation | Localhost validation in dev (demo bypass). Production: Cloudflared tunnel, no direct internet exposure. SSE endpoint behind Caddy reverse proxy. | **FULL** | Dev and prod isolation models are appropriate for each environment. |
| **T9** | Trust Boundary & Confirmation | Approval tokens for high-risk tools. Single-use, 60s TTL, tool-scoped. | **PARTIAL** | Core confirmation flow is solid. **No approval fatigue mitigation** — repeated confirmations for the same operation type could lead to rubber-stamping. |
| **T10** | Rate Limiting & Resource Control | Per-identity sliding window: read=60/min, mutate=10/min, search=30/min. Concurrency semaphore. Async timeouts (30s default, 60s for code_search). | **FULL** | Configurable via settings. Different limits per tool category. |
| **T11** | Supply Chain & Tool Provenance | All tools are first-party. Manifest hash pinning prevents runtime modification. No third-party tool loading mechanism. | **FULL** | Closed tool ecosystem eliminates third-party supply chain risk. |
| **T12** | Logging, Monitoring & Audit | Structured audit logs with `tool_name`, `user_id`, `result_code`, `duration_ms`, `policy_decision`. Per-tool `audit_fields` allowlists. Grafana dashboard for MCP security alerts. | **FULL** | Policy decision records enable SIEM querying. Grafana dashboard deployed (`mcp-security-alerts.json`). |

### CoSAI Coverage Summary

```
FULL     ████████████████████████████████████████  10/12  (83%)
PARTIAL  ████████                                   2/12  (17%)
GAP      ░░░░                                       0/12  ( 0%)
```

---

## 5. Coverage Heat Map

### Cross-Framework Summary

| Threat Domain | OWASP ASI | MITRE ATLAS | CoSAI | Overall |
|--------------|-----------|-------------|-------|---------|
| **Authentication** | FULL (ASI03) | FULL (T0084) | FULL (T1) | FULL |
| **Authorization / RBAC** | FULL (ASI02) | FULL (T0085) | FULL (T2) | FULL |
| **Input Validation** | FULL (ASI02) | FULL (T0099) | FULL (T3) | FULL |
| **Prompt Injection** | FULL (ASI01) | N/A (T0080) | FULL (T4) | **FULL** |
| **Secret Protection** | FULL (ASI03) | PARTIAL (T0083) | FULL (T5) | PARTIAL |
| **Integrity** | PARTIAL (ASI04) | FULL (T0081) | FULL (T6) | FULL |
| **Transport Security** | — | — | FULL (T7) | FULL |
| **Network Isolation** | — | — | FULL (T8) | FULL |
| **Human Confirmation** | FULL (ASI09) | FULL (T0101) | PARTIAL (T9) | PARTIAL |
| **Rate Limiting / DoS** | PARTIAL (ASI08) | PARTIAL (T0102) | FULL (T10) | PARTIAL |
| **Supply Chain** | PARTIAL (ASI04) | — | FULL (T11) | FULL |
| **Audit / Monitoring** | PARTIAL (ASI10) | PARTIAL (T0086) | FULL (T12) | PARTIAL |
| **Code Execution** | FULL (ASI05) | N/A (T0088) | — | FULL |
| **Memory Poisoning** | N/A (ASI06) | N/A (T0080) | — | N/A |
| **Multi-Agent Comms** | N/A (ASI07) | N/A (T0087) | — | N/A |

### Visual Coverage

```
Authentication       [████████████████████] FULL
Authorization        [████████████████████] FULL
Input Validation     [████████████████████] FULL
Prompt Injection     [████████████████████] FULL    ← P1 CLOSED
Secret Protection    [██████████████░░░░░░] PARTIAL
Integrity            [████████████████████] FULL
Transport Security   [████████████████████] FULL
Network Isolation    [████████████████████] FULL
Human Confirmation   [██████████████░░░░░░] PARTIAL
Rate Limiting / DoS  [██████████████░░░░░░] PARTIAL
Supply Chain         [████████████████████] FULL
Audit / Monitoring   [██████████████░░░░░░] PARTIAL
Code Execution       [████████████████████] FULL
```

---

## 6. Gap Analysis & Prioritized Roadmap

### P1 — Critical Gaps

~~All P1 gaps have been resolved.~~

#### 1. ~~Prompt Injection Detection in MCP Pipeline~~ RESOLVED
- **Frameworks:** ASI01, CoSAI T4
- **Resolution:** `scan_arguments_for_injection()` added to `schema_validator.py`, wired as layer P3.5 in `simbiot_server.py` `call_tool()`. All string arguments >10 chars are scanned on SSE transport using the existing `PromptInjectionDetector`. Blocked calls return `INJECTION_BLOCKED` with full audit trail.
- **Files:** `app/mcp/schema_validator.py`, `app/mcp/simbiot_server.py`
- **Tests:** 7 tests in `tests/api/test_mcp_sse_security_p2.py` (class `TestP3_5InjectionScanning`)

### P2 — Partial Coverage

These represent threats with some mitigation but identifiable weaknesses.

#### 2. Secret-Zero Input Scanning
- **Frameworks:** ATLAS T0083, T0098
- **Current state:** Output is scanned for credentials. Input arguments are not.
- **Risk:** Crafted tool arguments could trick the system into echoing back credentials from internal state.
- **Recommended fix:** Add input-side credential pattern scanning in `schema_validator.py` using existing regex patterns.
- **Effort:** Low (1 day). Reuse existing `SECRET_KEY_PATTERNS` and `SECRET_VALUE_PATTERNS`.

#### 3. Exfiltration Anomaly Alerting
- **Frameworks:** ATLAS T0086
- **Current state:** All tool invocations are audit-logged. No real-time alerting on anomalous patterns.
- **Risk:** Slow exfiltration via many legitimate-looking read calls would not trigger any alarm.
- **Recommended fix:** Add a Grafana alert rule on the MCP audit dashboard: flag identities exceeding N read calls in T minutes on sensitive tools.
- **Effort:** Low (1 day). Dashboard already exists; add alert threshold.

#### 4. Circuit Breaker for Cascading Failures
- **Frameworks:** ASI08
- **Current state:** Timeouts and rate limits prevent single-call resource exhaustion. No circuit breaker to halt cascading failures across dependent services.
- **Risk:** If a downstream service (e.g., Supabase) goes down, tool handlers may timeout repeatedly, consuming server resources.
- **Recommended fix:** Implement a simple circuit breaker (open after N consecutive timeouts, half-open after cooldown) in `simbiot_server.py`.
- **Effort:** Medium (2 days).

#### 5. Rogue Agent Behavioral Detection
- **Frameworks:** ASI10
- **Current state:** Manifest integrity prevents tool definition tampering. No behavioral baseline to detect anomalous usage patterns.
- **Risk:** A compromised client could call tools in an unusual sequence or at unusual hours without triggering alerts.
- **Recommended fix:** Define behavioral baselines per user role (typical tools, call frequency, time-of-day). Alert on deviation.
- **Effort:** High (5+ days). Requires baseline collection period.

### P3 — Future Hardening

These represent defense-in-depth improvements with lower immediate risk.

#### 6. Distributed Rate Limiting
- **Frameworks:** ATLAS T0102
- **Current state:** Rate limits are in-memory, per-process. Multi-instance deployments have per-instance limits.
- **Recommended fix:** Move rate limit state to Redis for cross-instance enforcement.
- **Effort:** Medium (2 days).

#### 7. Request Signing (HMAC) for JSON-RPC Envelopes
- **Frameworks:** CoSAI T7 (hardening)
- **Current state:** Envelope validation checks structure but not cryptographic integrity.
- **Recommended fix:** Add optional HMAC signing for JSON-RPC requests in production.
- **Effort:** Medium (3 days).

#### 8. Approval Fatigue Mitigation
- **Frameworks:** CoSAI T9
- **Current state:** Approval tokens require explicit confirmation. Repeated confirmations for the same operation type could lead to rubber-stamping.
- **Recommended fix:** Implement randomized challenge words for approval confirmation. Add cooldown periods after rapid successive approvals.
- **Effort:** Low (1–2 days).

### Roadmap Summary

| Priority | Item | Effort | Frameworks Addressed |
|----------|------|--------|---------------------|
| ~~**P1**~~ | ~~MCP prompt injection scanning~~ **DONE** | ~~Medium~~ | ASI01, CoSAI T4 |
| **P2** | Secret-zero input scanning | Low | ATLAS T0083, T0098 |
| **P2** | Exfiltration anomaly alerting | Low | ATLAS T0086 |
| **P2** | Circuit breaker pattern | Medium | ASI08 |
| **P2** | Behavioral anomaly detection | High | ASI10 |
| **P3** | Distributed rate limiting | Medium | ATLAS T0102 |
| **P3** | HMAC request signing | Medium | CoSAI T7 |
| **P3** | Approval fatigue mitigation | Low | CoSAI T9 |

---

## 7. Comparison: SENTINEL vs SecureClaw

SecureClaw (by Adversa AI) markets itself as the first MCP security product mapped to all three agentic security frameworks. This section compares architectural approaches.

### Where SENTINEL Leads

| Capability | SENTINEL | SecureClaw |
|-----------|----------|------------|
| **Integrated security pipeline** | 8 layers enforced inline in `call_tool()` — zero-latency between auth and execution | External proxy / middleware pattern — adds network hop |
| **Domain-specific RBAC** | Per-tool role + module + site scoping. Registry knows that `write_device_point` requires `operator` role + `hvac_control` module for site `S002` | Generic role-based policies, no domain-aware tool classification |
| **Approval token flow** | Single-use, tool-scoped, 60s TTL tokens with structured audit trail | Unclear public documentation on human-in-the-loop implementation |
| **Manifest integrity** | SHA-256 hash of tool definitions computed at startup, with optional pinned hash for production | Framework mapping only; no documented manifest verification |
| **BMS-specific safety** | SafetyEngine + ApprovalService + site-scoped access for building control tools | Generic AI security; no vertical-specific safety controls |
| **Test coverage** | 104 security tests across 4 suites, run in CI | Compliance-focused; testing approach not publicly documented |

### Where SecureClaw Leads

| Capability | SecureClaw | SENTINEL |
|-----------|------------|----------|
| **Framework mapping maturity** | Published mapping to OWASP ASI, MITRE ATLAS, CoSAI with compliance scoring | This document is our first formal mapping |
| **Prompt injection in tool pipeline** | Claims inline scanning of tool arguments for injection patterns | `scan_arguments_for_injection()` scans all string args via P3.5 layer — on par |
| **Behavioral anomaly detection** | Advertises ML-based agent behavior baselines | No behavioral baseline — audit logs exist but no anomaly model |
| **Multi-agent security** | Supports multi-agent communication security | N/A — single-agent architecture (Sentry only) |
| **Compliance certification** | Positions for SOC 2 / ISO 27001 alignment of MCP deployments | Internal controls only; no external certification framework |

### Architectural Differences

| Dimension | SENTINEL (SIMBIOT) | SecureClaw |
|-----------|-------------------|------------|
| **Deployment** | Embedded in application — security layers in `call_tool()` | External proxy / sidecar — intercepts MCP traffic |
| **Tool awareness** | Full registry: knows every tool's schema, risk tier, required role/module | Framework-agnostic: treats tools as opaque operations |
| **Scope** | Single-tenant BMS platform with domain-specific safety | Multi-tenant SaaS for any MCP deployment |
| **Open source** | Internal codebase; security design documented | Commercial product; public compliance reports |

### Key Takeaway

SENTINEL's strength is **deep, domain-specific security integration** — our controls understand BMS operations, equipment safety, and site-scoped access. SecureClaw's strength is **framework compliance breadth** and **multi-agent scenarios**. The P1 gap (MCP prompt injection scanning) is now closed. Adding behavioral baselines (P2) would further strengthen framework coverage while maintaining our domain-specific advantage.

---

## Appendix: Framework References

- **OWASP ASI Top 10 (2026):** [OWASP Agentic Security Initiative](https://owasp.org/www-project-agentic-security-initiative/)
- **MITRE ATLAS:** [ATLAS Matrix — Agentic Techniques](https://atlas.mitre.org/)
- **CoSAI MCP Security Taxonomy:** [Coalition for Secure AI — MCP Working Group](https://www.cosai.dev/)
- **SENTINEL MCP Security Hardening:** [mcp-security-hardening.md](mcp-security-hardening.md)

---

*Document: Agentic Security Framework Mapping*
*FSR Domain: 4.9 — Application Security*
*Platform: FastAPI, SSE Transport, Python 3.12*
*Last updated: 2026-02-19*
