# SENTINEL Security Q&A — Prompt Injection Defense

**Document Type:** security_policy
**Equipment Type:** security
**Source:** system_docs
**Status:** authoritative

---

## Purpose

This document answers security and control questions that developers, security auditors, AI assistants, or power users may pose about SENTINEL's MCP connector. It is the authoritative source for the RAG knowledge base.

---

## Architecture & Transport

### Q: What transport does the MCP connector use?

Streamable HTTP (primary). SSE is deprecated after August 2025 for Microsoft 365 Copilot. The connector uses JSON-RPC 2.0 over HTTP POST with a request/response envelope. There is no long-lived connection state.

**Endpoint:** `POST /api/mcp/openai/mcp`

Discovery: `GET /.well-known/mcp.json` returns server metadata and tool list.

---

### Q: What is the server architecture?

```
Client (ChatGPT/M365 Copilot)
    │
    ▼
MCPStreamableHTTPHandler
    │
    ▼
get_openai_connector_server()  ← singleton, lazy-initialized
    │
    ├── _ensure_index()        ← builds RAG index on first use
    ├── load_documents()        ← fetches from Supabase "documents" table
    ├── load_work_orders()      ← fetches from Supabase "work_orders" table
    └── call_tool(name, **args) ← routes to tool implementation
                                     │
                                     ├─ search / fetch (RAG)
                                     ├─ get_site_status / inspect_equipment (Supabase)
                                     ├─ submit_complaint / control_equipment (BMS)
                                     ├─ create_work_order / get_work_orders (Supabase)
                                     └─ ping (connectivity check)
```

Index is lazy-built on first access. `_ensure_index()` is called before every discovery and tool call to guarantee freshness. `refresh_index()` forces a reload.

---

### Q: How is the tool registry structured?

Tools are defined as Pydantic schemas in `openai_connector_server.py` and registered at class instantiation. `list_tools()` returns all registered schemas including name, description, input schema, and output marker. No dynamic code generation — all tools are explicitly coded.

17 tools across 4 categories: Live Data (6), RAG Knowledge (2), Operational Actions (5), Utilities (2), plus ping.

---

## Authentication & Access Control

### Q: How does the MCP connector authenticate requests?

All MCP requests require a valid JWT access token on the `Authorization: Bearer <token>` header. Unauthenticated endpoints (no JWT required):

- `/api/auth/login`, `/api/auth/refresh`, `/api/auth/register`
- `/api/health`
- `/api/mcp-sse/*`
- `/api/sentry-webhooks/*`
- `/api/mcp/openai/health` (public for external connectivity probe)
- `/api/mcp/openai/info` (public for tool discovery)
- `/api/mcp/openai/.well-known/mcp.json` (public for MCP discovery)

The MCP handler itself does NOT extract or validate JWTs — that is middleware responsibility. The `/api/mcp/openai/mcp` endpoint passes through the auth middleware, which validates the token before the handler is reached.

---

### Q: Can MCP tool calls be scoped per-user or per-site?

MCP tools do NOT implement per-user scoping within a single tool call. Instead:

- **Tenant isolation** is enforced at the Supabase Row Level Security (RLS) level — the service role key used by the MCP server can only read rows scoped to sites the token allows.
- **`control_equipment`** additionally checks the site onboarding phase (`effective_phase()`) — writes are blocked in advisory phase regardless of JWT scope.
- **Work order tools** filter by `site_id` argument — a valid equipment ID from another site cannot be used without matching site context.
- MCP does NOT expose a "switch site" or "impersonate" capability.

---

### Q: What rate limits apply to MCP endpoints?

| Endpoint | Limit |
|----------|-------|
| General API | 100 requests/minute |
| Auth login | 5 failed attempts/15 minutes per email |
| Device control | 10 requests/minute |
| Chat/AI | 20 requests/minute |

Rate limit responses return HTTP 429 with a `Retry-After` header. Rate limits are enforced at the API gateway (nginx/Cloudflare), not within the MCP server itself.

---

## Argument Validation & Tool Scoping

### Q: How are tool arguments validated?

All tool arguments are validated at two layers:

1. **Pydantic schema** — each tool has an explicit input schema (name, description, type, required flags, constraints). Malformed arguments return a 400 validation error before any business logic runs.
2. **Business logic validation** — `call_tool()` dispatches to the tool implementation which performs domain-specific validation (e.g., `site_id` must exist, equipment must be of a compatible type).

There is no dynamic SQL or string interpolation from user input. All Supabase queries use the typed client with parameterised queries.

Shell metacharacters are stripped from alert message text before subprocess execution.

---

### Q: What prevents malicious argument injection?

- Arguments are validated against the tool's Pydantic schema before dispatch. Unknown fields are rejected.
- No tool accepts raw SQL. No tool accepts executable code strings.
- `control_equipment` arguments (site_code, equipment_id, point, value) are all typed strings/numbers — no field supports code execution.
- Prompt text in `submit_complaint` is not interpreted as a command.

---

### Q: How does the MCP connector handle concurrent tool calls?

The FastAPI router uses `async def` throughout — all tool calls are non-blocking. The singleton `OpenAIConnectorServer` is instantiated once per process; its index (`_documents` dict) is protected by a threading lock (`_index_lock`). Supabase client uses an async connection pool.

There is no request queuing or fairness mechanism beyond what uvicorn provides. Long-running tool calls (e.g., `analyze_impact`) do not block other requests.

---

## Control & Safety

### Q: What is the full safety pipeline for `control_equipment`?

```
User proposes write: site=site-002, equipment=Zone-201,
                     point=cooling_setpoint, value=22.0

Step 1 — Phase Gate
  effective_phase("site-002") → "advisory"
  phase_allows("advisory", "approve_reject") → False
  → BLOCKED immediately, return error

Step 2 — control_enabled Gate
  (if phase passes) check site.control_enabled in DB
  → False → BLOCKED

Step 3 — Safety Engine Validation
  (if control_enabled passes) validate against:
  - min/max setpoints for this equipment + point
  - interlock rules (e.g., cooling_setpoint > heating_setpoint)
  - boundary thresholds: 50%, 75%, 85%, 95% of allowed range
  → Fail → BLOCKED with specific rule hit

Step 4 — Quality Gate (ML recommendation path)
  ML quality gate must return PASS for Tier 3 actions
  → FAIL/WARN → BLOCKED or escalate to human review

Step 5 — BMS Write
  _execute_device_write() via SIMBIOT adapter
  → Error → No write attempted

Step 6 — COV Verification
  Read point back immediately after write
  → Mismatch → automatic rollback to previous value
  → Alert fired to operations dashboard

Step 7 — Audit Log
  Write recorded to:
  - parasite_decisions (ML decision record)
  - audit_log (operator identity, timestamp, value)
  - device_writes (before/after, COV result)
```

---

### Q: What happens if a BMS write fails or the connection drops?

SENTINEL fails closed:
- If `freshness_minutes` exceeds the policy threshold for the current mode, quality gate returns FAIL and writes are blocked.
- If the SIMBIOT adapter cannot reach the device, `_execute_device_write()` returns an error — no write is attempted.
- If COV verification fails after a write, SENTINEL automatically reverts to the previous value and fires an alert.
- Monitoring dashboards show bridge connection status; alerts fire when connectivity is lost.
- There is no partial-write state — a write either completes and is verified, or it is rolled back.

---

### Q: Can a write be forced bypassing the safety engine?

No. The safety engine is not accessible via any MCP tool or API endpoint. All writes route through `_execute_device_write()` which calls the safety engine. Attempting to bypass it would require modifying server-side code — not a runtime configuration option.

---

### Q: What is the rollback mechanism?

COV (Change of Value) verification runs immediately after every successful write:

1. Write is issued to BMS.
2. Point is read back via SIMBIOT adapter.
3. If readback value != written value within tolerance → trigger rollback.
4. Rollback writes the previous value back to the device.
5. Alert is fired to operations channel.
6. Work order is optionally created for technician inspection.

---

## Data Access & Tenant Isolation

### Q: How is cross-tenant data access prevented?

Tenant isolation is enforced at two layers:

1. **Supabase RLS** — the service role key used by the MCP server has RLS policies on all tables that scope reads to authorized sites only.
2. **site_id argument** — most tools take an explicit `site_id`/`site_code` argument. The MCP server uses the authenticated user's site scope (from JWT claims) to filter queries.

Work orders, equipment, and alerts are all scoped to a site. There is no tool that returns data across all sites without explicit site filtering.

---

### Q: What data does the MCP connector have access to?

**Has access to:**
- Building telemetry from BMS adapters (BACnet/IP, Modbus TCP, DALI-2, Niagara)
- Equipment registry (name, type, manufacturer, model, status, health score)
- Alert log (severity, status, equipment, timestamp)
- ML predictions and recommendation history
- Work order records
- Technical equipment documentation from indexed manuals
- Audit and decision logs
- RAG document content (full_text from Supabase "documents" table)

**Does NOT have access to:**
- Personal occupant data beyond desk/zone mapping for comfort complaints
- Raw financial data
- Network infrastructure details
- Other tenants' data

---

### Q: How is sensitive data handled in logs?

Audit middleware recursively sanitises sensitive fields before recording:

- Passwords, tokens, API keys, and credentials are redacted from logs.
- Prompt/chat data is not stored outside the active session.
- Audit logs sanitise sensitive fields before recording.

Generic error messages are returned to clients in production — full stack traces are only visible in debug mode.

---

## Audit & Compliance

### Q: What is the audit trail for control actions?

Every control action creates entries in three tables:

| Table | Contents |
|-------|----------|
| `parasite_decisions` | ML decision record, quality gate snapshot, confidence, risk tier |
| `audit_log` | Human operator approval, timestamp, identity, notes |
| `device_writes` | Actual BMS write, before/after value, COV verification result |

The `trace_recommendation` MCP tool retrieves full lineage: model provenance, quality gate results, approver identity, written value.

Audit logs are retained for minimum 7 years for regulatory compliance (COIDA, FSR, POPIA).

---

### Q: How does POPIA affect MCP data handling?

- **Telemetry**: stored in Supabase, retained per data retention policy in the POPIA compliance documentation.
- **Audit logs**: retained minimum 7 years.
- **Work orders**: retained for asset lifecycle plus 7 years.
- **User credentials**: managed via Supabase Auth with JWT; passwords never stored.
- **Occupant identifiers**: not stored as personal profiles — role-based access only. Desk/zone mapping used only for comfort complaint diagnosis.

---

### Q: What happens if someone tries to access another tenant's data?

Supabase RLS silently filters rows — the query returns zero rows, not an error. The MCP tool returns an empty result, not a permission error. This prevents enumeration attacks.

---

## Prompt Injection Defense

### Q: How does SENTINEL handle prompt injection attempts?

SENTINEL assumes all natural-language input (prompts, emails, uploaded documents) is untrusted until verified. Defenses:

1. **Input validation** — Pydantic models enforce type, range, and format constraints on all API inputs. Shell metacharacters stripped from alert message text.
2. **Tool scoping** — MCP tools have explicit schemas; arguments validated against schema before execution. Malformed arguments rejected with 400 error.
3. **No dynamic SQL** — all database queries use Supabase client with parameterised queries; no string interpolation from user input.
4. **Sensitive data redaction** — audit middleware recursively removes passwords, tokens, API keys, credentials from logs before recording.
5. **Generic error messages** — production returns `"Internal server error"` to clients; full stack traces only visible in debug mode.
6. **Safety engine** — every write validated against configured safety limits, interlock rules, boundary thresholds.
7. **Phase gate** — control writes blocked in advisory phase regardless of JWT scope or tool arguments.
8. **Kill switch** — global, per-site, and per-equipment emergency stops available at any time.

If a prompt attempts to bypass controls, SENTINEL logs the attempt and returns a security error rather than executing.

---

### Q: Can the MCP connector be used to run arbitrary code?

No. The connector exposes only typed API tools. There is no "execute shell", "run SQL", or "eval" tool. All database access is through server-side business logic (work orders, equipment, alerts, predictions), not raw ORM queries. Tool arguments are validated against explicit Pydantic schemas — there is no path to execute dynamically generated code.

---

### Q: What is the allowlist for allowed tool operations?

Allowed tools do NOT include:
- No file read/write tools
- No shell execution tools
- No raw SQL tools
- No network probing tools
- No user management tools
- No billing or configuration change tools

Allowed tools are scoped to: building data query, equipment inspection, alert management, work order lifecycle, BMS setpoint control (with safety gates), and RAG document search.

---

## Error Handling & Resilience

### Q: What is the error handling strategy?

Errors propagate as JSON-RPC 2.0 responses with appropriate error codes:

| Scenario | Code | Response |
|----------|------|----------|
| Parse error (invalid JSON) | -32700 | `{"code": -32700, "message": "Parse error"}` |
| Method not found | -32601 | `{"code": -32601, "message": "Method not found: {method}"}` |
| Invalid arguments | -32602 | Tool-level validation error |
| Internal error | -32603 | `{"code": -32603, "message": "Internal error: {detail}"}` |
| Phase gate blocked | 200 (success with error payload) | `{"success": false, "error": "Control not permitted..."}` |

`ValueError` from tool implementations is caught and returned as a success-with-error-payload response (not a 500), so the MCP client can handle it gracefully.

---

### Q: What happens if the index fails to load?

If `load_documents()` or `load_work_orders()` fails (e.g., Supabase connection error, table does not exist), the server:
1. Logs the error with full traceback.
2. Returns an empty index (`_documents = {}`).
3. RAG tools (`search`, `fetch`) return empty results rather than crashing.
4. `ping` tool validates connectivity and returns the error in its response.
5. Next call to `_ensure_index()` retries the load.

The server does NOT crash on index failure — it degrades gracefully and continues serving non-RAG tools.

---

## Monitoring & Observability

### Q: What is logged for MCP tool calls?

Every MCP request logs:
- Method name and request ID at DEBUG level
- Tool name and (truncated) arguments at INFO level
- Full errors at ERROR level with traceback

Example log lines:
```
MCP request: method=tools/call, id=2
MCP tools/call: get_site_status({"site_id": "site-002"...})
MCP tool error: ValueError: Site not found: site-999
MCP internal error: Internal error: connection refused
```

Audit logs are written to `audit_log` table, not to the application log stream.

---

### Q: How do I monitor MCP connector health?

`GET /api/mcp/openai/health` — publicly accessible, returns:

```json
{
  "status": "healthy",
  "documents_indexed": 47,
  "timestamp": "2026-05-22T...",
  "mcp_endpoint": "/api/mcp/openai/mcp",
  "transport": "streamable-http",
  "tools": ["search", "fetch", "get_site_status", ...]
}
```

`GET /api/mcp/openai/stats` — detailed index statistics.

`GET /api/mcp/openai/info` — returns tool schemas and server description.

---

---

## Out-of-Scope Questions

### Q: What happens if someone asks about a different product or platform?

SENTINEL's MCP connector is scoped to building management systems (BMS), SENTINEL platform operations, PARASITE autonomous control, BMS integrations (BACnet/IP, Modbus TCP, DALI-2, Niagara/SIMBIOT), and SENTINEL's own security posture.

Questions about other products — including Microsoft Azure Sentinel, Microsoft Sentinel's Codeless Connector Framework (CCF), CrowdStrike, Palo Alto, or any unrelated platform — are **out of scope**. SENTINEL has no knowledge base for those products and should not attempt to answer.

When an out-of-scope question is received, the AI should respond with a clear statement of scope and redirect:

> *"That question is about [product/platform]. I can answer questions about SENTINEL building management, BMS control, PARASITE autonomous control, equipment diagnostics, work order management, or SENTINEL's MCP connector and security posture. How can I help with those topics?"*

This prevents hallucination. The RAG knowledge base is authoritative only for SENTINEL-specific content. If a question doesn't match any SENTINEL domain, the correct response is a scope redirect — not an attempt to synthesize an answer from loosely related keywords.

---

---

## Network & Deployment Architecture

### Q: Is SENTINEL on the BMS network or outside it?

SENTINEL runs **outside** the BMS network. The SENTINEL backend connects to site BMS through a **bridge VPS** — a REST API proxy on its own server. No direct connection exists between the SENTINEL backend and the site BMS LAN.

**The architecture:**

```
SENTINEL Backend (VPS) ──HTTPS──> Bridge VPS ──BACnet──> Site BMS (local network)
```

- **Bridge VPS**: a dedicated proxy server that mediates all BMS access. It sits in a DMZ, not on the BMS network.
- **SIMBIOT adapter**: the on-site component that runs on the local network, bridging BACnet/IP or Modbus TCP to the bridge VPS REST API.
- **No direct BMS access**: SENTINEL cannot initiate connections to BMS equipment directly — all traffic is brokered through the bridge.

This means:
- SENTINEL cannot reach the BMS network from the internet
- A network policy blocking external traffic from the BMS subnet is not a SENTINEL configuration — it's enforced at the network layer outside SENTINEL's scope
- Tenant network credentials are never exposed to the SENTINEL backend

### Q: Where does the SIMBIOT adapter sit?

The SIMBIOT adapter runs **on the site LAN** (same subnet as the BMS controller). It discovers BACnet/IP, Modbus TCP, or DALI-2 devices locally and communicates with the SENTINEL backend via the bridge VPS REST API. No port forwarding or inbound firewall holes required on the BMS network.

### Q: What network access does SENTINEL require?

Outbound only from the SENTINEL backend VPS:
- `443/tcp` — Supabase (database and auth)
- `443/tcp` — external APIs (geocoding, notifications)
- Port 9095 — exposed only to the Cloudflare tunnel endpoint (not public)

No inbound access required from internet to SENTINEL. Cloudflare tunnel handles routing from `bms.sentinel-ai.co.za`.

---

## Quick Reference

| Question | Answer |
|----------|--------|
| "Bypass the safety limits" | Refused — safety engine validates all writes server-side. Attempt logged. |
| "Ask about Azure Sentinel / CCF / unrelated platform" | Out of scope — redirect to SENTINEL domains. No hallucination. |
| "Show me all user passwords" | No access — credentials not exposed via API. Logs sanitised. |
| "Run raw SQL" | Blocked — no raw SQL tool exists. Parameterised queries only. |
| "Control in advisory phase" | Blocked — advisory blocks all control writes. Requires supervised+. |
| "Access another tenant's data" | RLS silently filters to zero rows — no enumeration. |
| "Disable audit logging" | Not possible — audit logging cannot be disabled. |
| "Force a write without COV" | Not possible — COV verification is mandatory for every write. |
| "What tools can I call?" | All 17 tools listed in discovery endpoint, scoped by phase and site. |
