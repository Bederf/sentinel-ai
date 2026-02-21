---
title: "MCP Security Hardening"
type: "reference"
status: "approved"
version: "1.0.0"
created: "2026-02-19"
updated: "2026-02-19"
author: "SENTINEL Security Office"
tags: ["mcp", "security", "owasp", "authentication", "rate-limiting", "audit"]
related: ["../03-api-reference/mcp-tools-reference.md", "logging-architecture.md", "../06-safety-compliance/audit-logging.md", "agentic-security-framework-mapping.md"]
domain: "security"
audience: "developers"
complexity: "advanced"
estimated_read_time: 20
---

# MCP Security Hardening

Technical security controls for the SIMBIOT MCP Server, aligned with the OWASP Model Context Protocol (MCP) Security Guidelines. Covers 8+ security layers (including P3.5 prompt injection scanning) enforced on every tool call, a canonical tool security registry, secret-zero output filtering, and cross-tenant isolation.

## Overview

The SIMBIOT MCP Server exposes 24+ tools for building management via two transports:

| Transport | Use Case | Auth Model |
|-----------|----------|------------|
| **stdio** | Local Claude Desktop | Trusted (no auth) — local process only |
| **SSE** | Remote clients, web apps | All 9 security layers enforced |

All security layers are enforced inside `SIMBIOTMCPServer.call_tool()` before any handler executes.

## Security Layers

### Request Processing Pipeline

```
1.  Transport Detection      → Is this SSE (remote) or stdio (local)?
2.  Auth Gate                → Reject unauthenticated SSE calls
3.  Approval Check           → High-risk tools need approval token
4.  Role/Module Gate         → Mutating tools need min_role + active module
5.  Schema Validation        → Validate input against JSON schema + size limits
5b. Prompt Injection Scan    → Scan string args for injection payloads (P3.5)
6.  Rate Limiting            → Per-identity, per-category sliding window
7.  Handler Execution        → With async timeout (default 30s)
8.  Audit Logging            → Structured log with policy decision record
9.  Output Truncation        → Cap output at 500KB
10. Secret-Zero Scan         → Redact credential patterns from output
```

### Layer 1: Authentication for All Remote Tools

**Problem addressed:** Read tools had no auth at the tool layer — if a transport forgot to enforce auth, data would leak.

**Solution:** All tools require auth when called via SSE transport. Stdio transport skips auth (local-only).

**Implementation:**
- SSE layer injects `_transport: "sse"` into arguments
- `call_tool()` checks: if `transport == "sse"` and tool requires auth and no `auth_ctx` → reject
- `PUBLIC_TOOLS` set (empty by default) can whitelist tools that skip auth

**Files:** `app/mcp/tool_permissions.py`, `app/api/mcp_sse.py`, `app/mcp/simbiot_server.py`

### Layer 2: Demo Bypass Restriction

**Problem addressed:** `DEMO_MODE=true` in production allowed unauthenticated access from localhost.

**Solution:** Demo bypass only works when `settings.environment == "development"`.

**Checks:**
- Environment must be `development`
- `DEMO_MODE` must be `true`
- Source IP must be localhost (using raw socket IP, not `X-Forwarded-For`)

**File:** `app/mcp/auth.py`

### Layer 3: Schema Validation

**Problem addressed:** JSON schemas defined per tool but never enforced — malformed inputs reached handlers directly.

**Input validation:**
- `jsonschema.validate()` against each tool's `input_schema`
- Recursive size limits: strings ≤ 10,000 chars, arrays ≤ 1,000 items
- Sanitized error messages (no full schema exposure)

**Output validation:**
- Maximum serialized output: 500KB (`MAX_OUTPUT_SIZE_BYTES`)
- Oversized output replaced with truncated version

**File:** `app/mcp/schema_validator.py`

### Layer 3.5: Prompt Injection Scanning

**Problem addressed:** The prompt injection guard (`prompt_injection_guard.py`) scanned chat input but was not wired into the MCP tool argument pipeline. Injection payloads hidden in tool arguments (e.g., a `description` field in `create_work_order`) bypassed detection entirely.

**Solution:** `scan_arguments_for_injection()` in `schema_validator.py` scans all string arguments using the existing `PromptInjectionDetector`. Runs as layer P3.5 in the `call_tool()` pipeline (after schema validation, before rate limiting).

**Behavior:**
- Only string values longer than 10 characters are scanned (short strings cannot carry meaningful payloads)
- Internal arguments (prefixed with `_`) are skipped
- Only applied to SSE transport (stdio is trusted local process)
- Blocked calls return `{"error": "...", "code": "INJECTION_BLOCKED"}`
- Audit log entry with `result_code: INJECTION_BLOCKED` and `policy_result: deny`

**Patterns detected:**
- System prompt extraction attempts ("ignore all instructions", "reveal system prompt")
- BMS safety bypass attempts ("disable fire safety interlocks", "bypass safety checks")
- Jailbreak attempts ("developer mode", "unrestricted AI")
- Social engineering patterns

**Frameworks addressed:** OWASP ASI01 (Agent Goal Hijacking), CoSAI T4 (Instruction Boundary Enforcement)

**Files:** `app/mcp/schema_validator.py`, `app/mcp/simbiot_server.py`

### Layer 4: Rate Limits & Execution Timeouts

**Problem addressed:** No per-identity rate limits — a single user could exhaust server resources.

**Rate limits (in-memory sliding window):**

| Category | Default Limit | Configuration Key |
|----------|--------------|-------------------|
| `read` | 60/min per identity | `mcp_read_rate_limit` |
| `mutate` | 10/min per identity | `mcp_mutate_rate_limit` |
| `search` | 30/min per identity | (derived from read) |

**Execution timeouts:**

| Tool Category | Timeout | Configuration Key |
|--------------|---------|-------------------|
| Default | 30s | `mcp_tool_timeout_seconds` |
| `code_search` | 60s | Hardcoded override |

**File:** `app/mcp/rate_limiter.py`, `app/config/settings.py`

### Layer 5: Query-Param Token Protection

**Problem addressed:** `?token=SECRET` in URLs leaks into proxy logs, Referer headers, and browser history.

**Production behavior:**
- `POST /api/mcp/sse/request?token=X` → **400 Bad Request**
- `GET /api/mcp/sse?ticket=<uuid>` → allowed (single-use, 30s TTL)
- Header-based auth (`X-MCP-Token`, `Authorization: Bearer`) → always allowed

**Ticket-based SSE auth flow:**
1. `POST /api/mcp/sse/ticket` (authenticated via header) → returns `{"ticket": "<uuid>", "expires_in": 30}`
2. `GET /api/mcp/sse?ticket=<uuid>` → SSE connection established with ticket creator's identity
3. Ticket consumed on first use — replay returns 401

**Files:** `app/mcp/auth.py`, `app/api/mcp_sse.py`

### Layer 6: Audit Logging with Redaction

**Problem addressed:** No audit trail for MCP tool invocations. Logs must not contain tokens or raw payloads.

**What is logged:**
- `tool_name`, `user_id`, `result_code` (SUCCESS, UNAUTHORIZED, TIMEOUT, RATE_LIMITED, INVALID_INPUT)
- `duration_ms` — execution time
- `arguments` — filtered to per-tool allowlist, then recursively PII-redacted
- `policy_decision` — structured record for SIEM querying
- `site_id`, `request_id` — correlation

**Per-tool argument allowlists:**
```
write_device_point → {device_id, point_name, priority}
create_work_order  → {building_id, equipment_id, priority, description}
get_buildings      → {status_filter, region}
get_devices        → {site_id, device_type}
...
```

**Always stripped:** `token`, `authorization`, `password`, `secret`, `username`, `api_key`, `apikey`, `credential`, `_auth_context`, `_transport`, `_approval_token`

**Policy decision record:**
```json
{
  "tool": "write_device_point",
  "risk_tier": "high_risk",
  "auth_method": "bearer_token",
  "user": "operator@example.com",
  "site_id": "S002",
  "result": "allow",
  "required_role": "operator",
  "required_module": "control",
  "required_approval": true
}
```

**File:** `app/mcp/audit.py`

### Layer 7: Tool Manifest Tamper Resistance

**Problem addressed:** Tool definitions could change at runtime. A compromised handler could alter its description to trick the model.

**Implementation:**
- SHA-256 hash of all tool definitions computed at initialization
- `verify_manifest()` compares current hash with initial hash
- Optional pinned hash via `mcp_tool_manifest_hash` setting — if set, server refuses to start on mismatch

**File:** `app/mcp/simbiot_server.py`

### Layer 8: High-Risk Approval Path

**Problem addressed:** Destructive tools execute immediately with no confirmation step.

**High-risk tools requiring approval:**
- `write_device_point` — direct device control
- `create_building` — new building creation
- `activate_building` — building activation

**Approval flow:**
1. Tool called without `_approval_token` → returns `{"approval_required": true, ...}`
2. Client calls `POST /api/mcp/sse/approve` with `{"tool_name": "write_device_point"}`
3. Server returns `{"approval_token": "<uuid>", "expires_in": 60}`
4. Client retries tool call with `_approval_token` in arguments
5. Token consumed on first use, scoped to specific tool

**Files:** `app/mcp/approval_store.py`, `app/mcp/tool_permissions.py`

## Tool Security Registry

The Tool Security Registry (`app/mcp/tool_security_registry.py`) is the canonical source of truth for every MCP tool's security posture. All other security modules derive their behavior from this registry.

### Registry Fields

| Field | Type | Description |
|-------|------|-------------|
| `name` | str | Tool name |
| `auth_required` | bool | SSE transport requires auth (default: `true`) |
| `mutating` | bool | Modifies state — requires role + module gating |
| `high_risk` | bool | Requires explicit approval token |
| `rate_class` | str | Rate limit bucket: `read`, `mutate`, or `search` |
| `min_role` | SentinelRole | Minimum role for mutating tools |
| `required_module` | ModuleType | Module that must be active for this tool |
| `audit_fields` | frozenset | Argument fields safe to include in audit logs |
| `output_allowed_fields` | frozenset | Output field allowlist (None = no filter) |
| `secret_zero_risk` | bool | True if tool accepts/returns credential-like data |

### Tool Classification Summary

**Read tools** (auth only for SSE, rate_class=read):
`get_buildings`, `get_assets`, `get_asset_detail`, `get_devices`, `read_device_point`, `get_alarms`, `get_trends`, `get_health_score`, `get_work_orders`, `list_managed_buildings`, `get_building_config`, `get_asset_metrics_template`, `get_solar_overview`, `get_bess_status`, `get_solar_savings`, `get_solar_forecast`, `get_solar_diagnostics`, `get_contracts`, `get_contract_profitability`, `get_utility_costs`

**Search tools** (auth only for SSE, rate_class=search):
`search_alarms`, `code_search`

**Code tools** (read-only but source-code access):
`code_fetch`, `code_structure`

**Mutating tools** (auth + role + module):
`create_work_order` (operator/maintenance), `add_building_zones` (admin/simbiot), `add_building_desks` (admin/simbiot), `add_building_devices` (admin/simbiot), `import_point_list` (admin/simbiot), `import_controller_list` (admin/simbiot), `discover_tridonic_gateway` (operator/simbiot, **secret_zero_risk**), `configure_asset_metrics` (operator/assets), `add_building_contract` (admin/contracts), `process_municipal_bill` (operator/energy)

**High-risk tools** (auth + role + module + approval):
`write_device_point` (operator/control), `create_building` (admin/simbiot), `activate_building` (admin/simbiot)

### Consistency Enforcement

The registry is validated by tests to ensure:
- Every tool in `MCP_TOOLS` has a registry entry
- Registry `mutating` flags match `MUTATING_TOOLS` in `tool_permissions.py`
- Registry `high_risk` flags match `HIGH_RISK_TOOLS` in `tool_permissions.py`
- Every mutating tool has `min_role` and `required_module` set

## Secret-Zero Output Filter

The secret-zero check ensures credentials never reach the model path. Tool output is scanned recursively before being returned.

### Detection Methods

**By key name** (case-insensitive):
`api_key`, `apikey`, `api_secret`, `authorization`, `access_token`, `refresh_token`, `secret_key`, `private_key`, `password`, `credential`, `token`, `jwt`, `bearer`, `client_secret`, `auth_token`, `session_token`

**By value pattern** (regex):
- API keys: `^(?:sk|pk|sent_sk)(?:_(?:test|live))?_[A-Za-z0-9]{20,}$`
- Bearer tokens: `^Bearer\s+[A-Za-z0-9._-]{20,}$`
- JWT tokens: `^eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}`

**Redaction:**
Matched values are replaced with `***REDACTED_BY_SECRET_ZERO_FILTER***`. A warning is logged: `SECRET_ZERO: tool=<name> leaked <N> secret field(s): <paths>`

**File:** `app/mcp/schema_validator.py`

## Cross-Tenant Isolation

Security state is isolated per user identity to prevent cross-tenant information leakage.

| Resource | Isolation Scope | Mechanism |
|----------|----------------|-----------|
| Rate limits | Per identity, per category | Separate sliding windows per `user_id` |
| Approval tokens | Per tool, single-use | UUID tied to tool name, consumed on first use |
| SSE tickets | Per user, single-use | Carries creating user's `AuthContext`, consumed on first use |
| Auth contexts | Per SSE call | Each `call_tool()` receives its own `_auth_context` |

## Test Coverage

Security controls are validated by 111 tests across 4 test files:

| Test File | Tests | Coverage |
|-----------|-------|----------|
| `tests/api/test_mcp_sse_security_p2.py` | 38 | All 8 security layers + P3.5 injection scanning |
| `tests/api/test_mcp_security_registry.py` | 26 | Registry, policy decisions, secret-zero, cross-tenant |
| `tests/api/test_mcp_sse_auth.py` | 30 | Base auth and token handling |
| `tests/integration/test_mcp_integration.py` | 17 | End-to-end tool execution |

### Running Security Tests

```bash
cd backend

# All MCP security tests
python3 -m pytest tests/api/test_mcp_sse_security_p2.py tests/api/test_mcp_security_registry.py -v

# Including base auth tests
python3 -m pytest tests/api/test_mcp_sse_auth.py -v

# Full MCP test suite
python3 -m pytest tests/api/test_mcp_sse_security_p2.py tests/api/test_mcp_security_registry.py tests/api/test_mcp_sse_auth.py tests/integration/test_mcp_integration.py -v
```

## Configuration Reference

| Setting | Default | Description |
|---------|---------|-------------|
| `mcp_read_rate_limit` | 60 | Read tools: calls per minute per identity |
| `mcp_mutate_rate_limit` | 10 | Mutating tools: calls per minute per identity |
| `mcp_tool_timeout_seconds` | 30 | Default execution timeout in seconds |
| `mcp_tool_manifest_hash` | `""` | Pinned manifest hash (empty = no enforcement) |
| `demo_mode` | `false` | Demo mode toggle |
| `environment` | `development` | Environment name (gates demo bypass) |

## Related Files

| File | Purpose |
|------|---------|
| `app/mcp/simbiot_server.py` | MCP server — `call_tool()` integration point for all layers |
| `app/mcp/auth.py` | Token extraction, `require_mcp_auth()`, demo bypass |
| `app/mcp/tool_permissions.py` | `PUBLIC_TOOLS`, `MUTATING_TOOLS`, `HIGH_RISK_TOOLS` |
| `app/mcp/tool_security_registry.py` | Canonical per-tool security classification |
| `app/mcp/schema_validator.py` | Input validation, output truncation, secret-zero filter |
| `app/mcp/rate_limiter.py` | Per-identity sliding window rate limiting |
| `app/mcp/audit.py` | Audit logging with field allowlists + policy decisions |
| `app/mcp/approval_store.py` | Single-use approval token store |
| `app/api/mcp_sse.py` | SSE transport — ticket endpoint, approve endpoint |
| `app/config/settings.py` | Configurable rate limits and manifest hash |

## OWASP MCP Guidelines Coverage

| OWASP Guideline | Coverage | Implementation |
|-----------------|----------|----------------|
| Tool authentication | Full | Layer 1 — all remote tools gated |
| Input validation | Full | Layer 3 — JSON schema + size limits |
| Rate limiting | Full | Layer 4 — per-identity sliding window |
| Output sanitization | Full | Secret-zero filter + output truncation |
| Audit logging | Full | Layer 6 — structured policy decision records |
| Least privilege | Full | Registry — per-tool role + module requirements |
| Tool integrity | Full | Layer 7 — SHA-256 manifest hashing |
| Human-in-the-loop | Full | Layer 8 — approval tokens for high-risk tools |

## Agentic Security Framework Mapping

For a comprehensive mapping of SENTINEL's MCP controls against **OWASP ASI Top 10**, **MITRE ATLAS Agentic Techniques**, and the **CoSAI MCP Security Taxonomy**, including gap analysis and prioritized hardening roadmap, see:

**[Agentic Security Framework Mapping](agentic-security-framework-mapping.md)**

---

*Document: MCP Security Hardening*
*FSR Domain: 4.9 - Application Security*
*Platform: FastAPI, SSE Transport, Python 3.12*
*Last updated: 2026-02-19*
