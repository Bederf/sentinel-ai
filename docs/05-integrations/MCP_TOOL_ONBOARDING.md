# MCP Tool Onboarding Checklist (C3 + H5)

When adding a new MCP tool to the SIMBIOT server, every item below must be completed
before the tool ships. CI enforces registry completeness via
`test_mcp_registry_completeness.py`.

---

## 1. Define the Tool

Add a tool definition dict to `MCP_TOOLS` in `backend/app/mcp/simbiot_server.py`:

```python
{
    "name": "my_new_tool",
    "description": "Two sentences max. What it does and when to use it.",
    "input_schema": { ... }
}
```

**Rules:**
- Description: max 2 sentences, no internal file paths, no schema details
- `input_schema`: complete JSON Schema with `required` array
- `enum` constraints on string fields wherever possible

## 2. Implement the Handler

Add an `async def my_new_tool_handler(...)` function and register it in
`SIMBIOTMCPServer.__init__` → `self.tool_handlers`.

## 3. Register in Tool Security Registry

Add a `ToolSecurityProfile` entry in `backend/app/mcp/tool_security_registry.py`:

```python
_r(ToolSecurityProfile(
    name="my_new_tool",
    mutating=False,          # True if it changes state
    high_risk=False,         # True if destructive (requires approval token)
    rate_class="read",       # "read" | "mutate" | "search"
    min_role=None,           # SentinelRole.OPERATOR / .ADMIN for mutating tools
    required_module=None,    # ModuleType if module-gated
    audit_fields=frozenset({"building_id"}),  # Fields safe for audit logs
    secret_zero_risk=False,  # True if accepts/returns credentials
))
```

## 4. Register in Tool Permissions (mutating tools only)

If `mutating=True`, add entries in `backend/app/mcp/tool_permissions.py`:

| Registry | Purpose |
|----------|---------|
| `MCP_TOOL_MODULE_REQUIREMENTS` | Which module must be active |
| `MCP_TOOL_MIN_ROLE` | Minimum SentinelRole |
| `HIGH_RISK_TOOLS` (if destructive) | Requires approval token |

## 5. Write Tests

- Unit test for the handler function
- Integration test via `SIMBIOTMCPServer.call_tool()`
- Verify auth gating if mutating

## 6. Update Manifest Hash (if pinned)

If `MCP_TOOL_MANIFEST_HASH` is set in `.env`, update it:

```bash
# Get the new hash from server init logs
grep "manifest=" backend/logs/app.log
# Update .env
MCP_TOOL_MANIFEST_HASH=<new-hash>
```

---

## CI Enforcement

`backend/tests/api/test_mcp_registry_completeness.py` verifies:

1. Every tool in `SIMBIOTMCPServer.tools` has a `ToolSecurityProfile` entry
2. Every mutating tool in the registry has entries in `MCP_TOOL_MODULE_REQUIREMENTS`
   and `MCP_TOOL_MIN_ROLE`
3. Every high-risk tool is in `HIGH_RISK_TOOLS`
4. Tool descriptions are ≤ 2 sentences and contain no internal file paths
5. All tools have a registered handler

---

## Non-Human Identities (H5)

The following service identities are used in the MCP system. Review quarterly
to confirm scopes remain appropriate.

| Identity | Auth Method | Role | Scopes | Purpose |
|----------|-------------|------|--------|---------|
| `mcp-client` | MCP shared token | OPERATOR | `operator:all` | Generic MCP client via shared token |
| `demo-user` | Demo bypass | OPERATOR | `operator:all` | Development/demo mode only |
| `system` | Internal | ADMIN | `*` | Background scheduler, automated workflows |
| `sentry-bot` | Sentry webhook | OPERATOR | Notifications only | Telegram bot for alerts/work orders |
| `mcp:<email>` | JWT Bearer | Per-user | Per-user | Real user identity via JWT on MCP tools |

### Rotation Schedule

| Token | Rotation Cadence | Config Key |
|-------|-----------------|------------|
| MCP shared token | Every 30 days | `MCP_AUTH_TOKEN` + `MCP_AUTH_TOKEN_PREVIOUS` |
| JWT secret | On compromise only | `JWT_SECRET_KEY` |
| Sentry webhook secret | On compromise only | `SENTRY_WEBHOOK_SECRET` |

### Scope Restrictions

- `mcp-client` (shared token): Should only be used by trusted automation.
  Cannot create buildings or activate sites (requires ADMIN role).
- `demo-user`: Only valid when `DEMO_MODE=true` AND `environment=development`
  AND request originates from localhost.
- `system`: Used by `background_scheduler.py` for automated health checks
  and alert generation. Never exposed to external requests.
