# Secure Coding Standards

SENTINEL BMS Intelligence Platform

**Document Classification:** Confidential
**FSR Domain:** 4.9 - Application Security
**Version:** 1.0
**Effective Date:** 2026-02-04
**Review Cadence:** Annual, or upon major framework change
**Owner:** Information Security Officer
**Approved By:** SENTINEL Product Owner

---

## 1. Purpose

This document defines the mandatory secure coding standards for all SENTINEL software development. It provides language-specific and framework-specific guidance for preventing common vulnerabilities, with particular attention to BMS-specific security concerns unique to building management systems.

All developers contributing to SENTINEL are required to understand and adhere to these standards. Compliance is verified through code review (see [Application Security Policy](./application-security-policy.md), Section 4) and automated scanning (see [Application Security Pipeline](./application-security-pipeline.md)).

## 2. Scope

These standards apply to all custom-developed code across the SENTINEL platform:

- **Python/FastAPI backend code** (`backend/app/`)
- **React/TypeScript frontend code** (`frontend/src/`)
- **ML pipeline code** (`backend/ml/`)
- **BMS connector code** (BACnet/IP, Modbus TCP, DALI-2 adapters)
- **MCP server tools** (`backend/app/mcp/`)
- **Integration services** (log parsers, point matchers, CAFM connectors)
- **Deployment scripts and infrastructure-as-code** (Dockerfiles, Compose files, CI/CD workflows)

## 3. Input Validation

### 3.1 API Input Validation (FastAPI/Pydantic)

All API inputs must be validated using Pydantic models. Direct access to raw request data without validation is prohibited.

**Required:**
```python
# CORRECT: Pydantic model validates all inputs
from pydantic import BaseModel, Field, validator

class DeviceControlRequest(BaseModel):
    device_id: str = Field(..., pattern=r'^S\d{3}-[A-Z]+-[A-Z0-9]+-[A-Z0-9]+$')
    point_name: str = Field(..., min_length=1, max_length=100)
    value: float = Field(..., ge=-50, le=100)

@router.post("/devices/{device_id}/control")
async def control_device(device_id: str, request: DeviceControlRequest):
    ...
```

**Prohibited:**
```python
# WRONG: Direct access to raw request body without validation
@router.post("/devices/{device_id}/control")
async def control_device(device_id: str, request: Request):
    body = await request.json()  # No validation
    value = body["value"]        # No type checking
```

### 3.2 SQL Injection Prevention

Parameterised queries are mandatory. String concatenation or f-strings in SQL queries are prohibited.

**Required:**
```python
# CORRECT: Parameterised query via Supabase client
result = supabase.table("equipment").select("*").eq("id", equipment_id).execute()

# CORRECT: Parameterised query via SQLAlchemy
result = session.execute(text("SELECT * FROM equipment WHERE id = :id"), {"id": equipment_id})
```

**Prohibited:**
```python
# WRONG: String concatenation in SQL
query = f"SELECT * FROM equipment WHERE id = '{equipment_id}'"
result = session.execute(text(query))

# WRONG: Direct string formatting
query = "SELECT * FROM equipment WHERE id = '%s'" % equipment_id
```

### 3.3 XSS Prevention

React's default JSX escaping provides XSS protection for rendered content. The following rules apply:

**Required:**
```tsx
// CORRECT: React automatically escapes content
<div>{userInput}</div>
<span>{equipment.name}</span>
```

**Prohibited:**
```tsx
// WRONG: Never use dangerouslySetInnerHTML with untrusted content
<div dangerouslySetInnerHTML={{ __html: userInput }} />

// WRONG: Never inject user content into href or src attributes without validation
<a href={userInput}>Link</a>  // Must validate URL scheme (https only)
```

If `dangerouslySetInnerHTML` is ever required (e.g., rendering markdown from AI responses), content must be sanitised using a library such as DOMPurify before injection.

### 3.4 Command Injection Prevention

System command execution must use argument lists, never shell interpolation.

**Required:**
```python
# CORRECT: Argument list (no shell interpretation)
import subprocess
result = subprocess.run(["ping", "-c", "1", host], capture_output=True, text=True)
```

**Prohibited:**
```python
# WRONG: shell=True allows command injection
import subprocess
subprocess.run(f"ping -c 1 {host}", shell=True)

# WRONG: os.system is always vulnerable
import os
os.system(f"ping -c 1 {host}")
```

### 3.5 Path Traversal Prevention

All file path operations must validate and sanitise inputs to prevent directory traversal.

**Required:**
```python
# CORRECT: Resolve and validate against allowed directory
from pathlib import Path

ALLOWED_DIR = Path("/opt/bms-intelligence/backend/app/data")

def read_data_file(filename: str) -> dict:
    filepath = (ALLOWED_DIR / filename).resolve()
    if not filepath.is_relative_to(ALLOWED_DIR):
        raise ValueError("Path traversal detected")
    return json.loads(filepath.read_text())
```

**Prohibited:**
```python
# WRONG: No path validation
def read_data_file(filename: str) -> dict:
    return json.loads(open(f"app/data/{filename}").read())  # ../../../etc/passwd
```

## 4. Authentication and Authorisation

### 4.1 FastAPI Authentication

Use `FastAPI Depends()` with authentication dependency injection. Never implement ad-hoc authentication checks.

**Required:**
```python
from fastapi import Depends
from app.auth import require_auth, require_role

@router.get("/admin/users")
async def list_users(user = Depends(require_role("admin"))):
    ...

@router.get("/devices")
async def list_devices(user = Depends(require_auth)):
    ...
```

### 4.2 Credential Management

- **Never store credentials in code.** All credentials must be loaded from environment variables or a secrets manager.
- **Pre-commit hook enforcement:** The `detect-secrets` and `check-hardcoded-secrets` pre-commit hooks block commits containing API key patterns.
- **API keys via environment variables:** Use the `Settings` class (`app/config/settings.py`) for all configuration, which reads from environment variables.
- **JWT tokens:** Must use `httpOnly` cookies, `Secure` flag, short expiry (15 minutes for access tokens), and `SameSite=Strict` or `SameSite=Lax`.
- **API key rotation:** All API keys must be rotated every 90 days. Track rotation dates in the asset register.

### 4.3 Secrets in Configuration

**Required:**
```python
# CORRECT: Environment variables via Settings class
from app.config.settings import settings
api_key = settings.ANTHROPIC_API_KEY
```

**Prohibited:**
```python
# WRONG: Hardcoded credentials
ANTHROPIC_API_KEY = "sk-ant-api03-..."

# WRONG: Credentials in configuration files committed to git
# .env files are blocked by pre-commit hooks
```

## 5. Error Handling

### 5.1 Error Sanitisation

Never expose internal details to API clients. Return generic error messages while logging full details server-side.

**Required:**
```python
# CORRECT: Generic message to client, full details to log
import logging
logger = logging.getLogger(__name__)

@router.get("/equipment/{equipment_id}")
async def get_equipment(equipment_id: str):
    try:
        equipment = repository.get(equipment_id)
        if not equipment:
            raise HTTPException(status_code=404, detail="Equipment not found")
        return equipment
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get equipment {equipment_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")
```

**Prohibited:**
```python
# WRONG: Exposing stack trace, internal paths, or database errors
@router.get("/equipment/{equipment_id}")
async def get_equipment(equipment_id: str):
    try:
        equipment = repository.get(equipment_id)
        return equipment
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))  # Exposes internals
```

### 5.2 Information Not to Expose

The following must never appear in API error responses:

- Stack traces or traceback information
- Database connection strings or query details
- File system paths (`/opt/bms-intelligence/...`)
- Internal IP addresses or hostnames
- Software version numbers or framework details
- Configuration values or environment variable contents

## 6. Secrets Management

### 6.1 Runtime Secrets

- All runtime secrets are stored as environment variables, loaded via the `Settings` class
- `.env` files are used for local development only and are blocked from git commits by the pre-commit `check-env-files` hook
- Production secrets are injected via Docker Swarm secrets or environment variables in the deployment configuration

### 6.2 Secret Types and Rotation

| Secret Type | Storage | Rotation Period | Owner |
|-------------|---------|----------------|-------|
| `ANTHROPIC_API_KEY` | Environment variable | 90 days | Security Officer |
| `SUPABASE_KEY` | Environment variable | 90 days | Security Officer |
| `SUPABASE_SERVICE_ROLE_KEY` | Environment variable | 90 days | Security Officer |
| `DATABASE_URL` | Environment variable | On compromise | Security Officer |
| SSH keys | `~/.ssh/` (600 permissions) | Annual | Operations |
| TLS certificates | Cloudflare managed | Auto-renewed | Cloudflare |
| Docker registry tokens | Docker config | 90 days | Operations |

### 6.3 Secret Detection

Secrets accidentally committed to the repository are detected by:

1. **Pre-commit:** `detect-secrets` hook scans staged files before commit
2. **CI/CD:** Gitleaks scans full repository history on every push
3. **Manual review:** Quarterly review of `.env` files and configuration as part of internal scan

If a secret is detected in the repository:
1. Rotate the secret immediately
2. Remove from git history using `git filter-repo` or `BFG Repo-Cleaner`
3. Log the incident in the security incident register
4. Review and strengthen detection mechanisms

## 7. BMS-Specific Secure Coding

### 7.1 Device Write Operations

All device write operations must pass through the `SafetyEngine` before execution. Direct writes bypassing safety validation are prohibited.

**Required:**
```python
# CORRECT: Safety validation before write
from app.services.safety_interlocks import get_safety_engine

safety_engine = get_safety_engine()
validation = safety_engine.validate_action(device_id, point_name, value)
if validation.severity == "BLOCK" or validation.severity == "ALARM":
    raise HTTPException(status_code=403, detail=f"Safety blocked: {validation.message}")
# Proceed with write only after validation passes
```

**Prohibited:**
```python
# WRONG: Direct write without safety validation
device.write_point(point_name, value)
```

### 7.2 Audit Logging for Control Actions

Every control action must be logged with before/after state. The audit log entry must be created regardless of success or failure of the actual write operation.

**Required fields in control audit log:**
- `timestamp` - ISO 8601 timestamp
- `action` - "device_control"
- `user` - User or system that initiated the action
- `device_id` - v2.0 format equipment ID
- `point_name` - Controlled parameter
- `previous_value` - Value before command
- `commanded_value` - Value sent to device
- `safety_result` - Validation outcome from SafetyEngine
- `execution_result` - Success or failure with error details

### 7.3 Rate Limiting for Device Writes

Device write operations are rate-limited to prevent rapid successive commands that could damage equipment or create unsafe conditions:

- **Per-device limit:** Maximum 10 write commands per minute per device
- **Per-user limit:** Maximum 20 write commands per minute per user
- **Global limit:** Maximum 60 write commands per minute across all devices
- **Rate limit enforcement:** At the API layer before safety validation

### 7.4 BACnet/Modbus Write Constraints

- **BACnet Priority Level:** All BACnet write commands must use Priority 8 (manual override level). Priorities 1-7 are reserved for life safety systems and must never be used by SENTINEL.
- **Modbus Write Register Validation:** Validate target register addresses against an allowlist of known safe registers for each device type.
- **DALI Command Validation:** DALI brightness commands constrained to configured minimum (10%) to prevent complete blackout of safety-critical areas.

## 8. Logging

### 8.1 Structured Logging

All logging must use structured JSON format for machine parsing:

**Required:**
```python
import structlog
logger = structlog.get_logger()

logger.info("device_control_executed",
    device_id="S002-CHILLER-B1-001",
    point_name="chw_supply_temp",
    value=22.5,
    user="system",
    correlation_id=request_id
)
```

### 8.2 Personal Information in Logs

Never log personal information (PI). The following must be excluded or redacted:

- Phone numbers (WhatsApp/Telegram)
- Email addresses
- Occupant names
- Physical addresses
- Any data classifiable as personal under POPIA

**Required:**
```python
# CORRECT: Log reference ID, not personal details
logger.info("complaint_submitted", desk_id="201", complaint_type="too_hot")
```

**Prohibited:**
```python
# WRONG: Logging personal information
logger.info(f"Complaint from John Smith (083-555-1234) at desk 201")
```

### 8.3 Correlation IDs

All HTTP requests must include a correlation ID for request tracing across services:

- Generate a UUID for each incoming request
- Pass the correlation ID in log entries for the request lifecycle
- Include in responses as `X-Request-ID` header

## 9. Dependency Management

### 9.1 Version Pinning

All dependencies must be pinned to specific versions in requirements files:

**Required:**
```
# CORRECT: Pinned versions
fastapi==0.109.0
pydantic==2.5.3
uvicorn==0.25.0
```

**Prohibited:**
```
# WRONG: Unpinned or range versions
fastapi>=0.109.0
pydantic
uvicorn~=0.25
```

### 9.2 Dependabot PR Review

Dependabot pull requests must be reviewed within the following SLAs:

| Severity | Review SLA | Merge SLA |
|----------|-----------|-----------|
| Critical | 3 days | 7 days |
| High | 7 days | 14 days |
| Medium | 14 days | 30 days |
| Low | 30 days | 90 days |

### 9.3 New Dependency Checklist

Before adding any new dependency:

- [ ] Run `pip-audit` or `npm audit` to check for known vulnerabilities
- [ ] Verify licence compatibility (MIT, Apache 2.0, BSD, ISC accepted)
- [ ] Confirm package is actively maintained (release within 12 months)
- [ ] Check download count and community adoption
- [ ] Review package for minimal scope (does not pull in unnecessary transitive dependencies)
- [ ] Document the reason for adding the dependency in the commit message

## 10. OWASP Top 10 Mitigation Reference

The following table maps each OWASP Top 10 (2021) risk to SENTINEL's specific mitigations:

| # | OWASP Risk | SENTINEL Mitigation | Implementation |
|---|-----------|---------------------|----------------|
| A01 | **Broken Access Control** | FastAPI `Depends()` with `require_auth`/`require_role` decorators; safety engine for device control authorisation; audit logging of all control actions | `app/auth/`, `app/services/safety_interlocks.py`, `app/api/audit.py` |
| A02 | **Cryptographic Failures** | TLS 1.2+ for all API traffic (Cloudflare); AES-256 at-rest encryption (Supabase); JWT with `httpOnly`/`Secure` flags; no plaintext secrets in code | Cloudflare TLS, Supabase encryption, `.pre-commit-config.yaml` |
| A03 | **Injection** | Pydantic input validation on all API endpoints; parameterised queries via Supabase client/SQLAlchemy; no `shell=True` in subprocess; no `os.system()`; Cloudflare WAF SQLi/XSS rules | `app/models/`, `app/database/repositories/`, WAF rules 2-4 |
| A04 | **Insecure Design** | STRIDE threat modelling at Design gate; SafetyEngine for BMS write operations; OT/IT network segmentation; safety-first device control architecture | Section 3.2 of this standards document, `app/services/safety_interlocks.py` |
| A05 | **Security Misconfiguration** | Pre-commit hooks prevent debug mode and secret leaks; production config review at Deploy gate; Docker container hardening; Lynis quarterly system audit | `.pre-commit-config.yaml`, deploy checklist, `infrastructure/scanning/internal-scan.sh` |
| A06 | **Vulnerable and Outdated Components** | Dependabot automated updates (4 ecosystems); pip-audit and Safety in CI/CD; Trivy container scanning; version pinning with SLA-driven review | `.github/dependabot.yml`, `.github/workflows/security-scan.yml` |
| A07 | **Identification and Authentication Failures** | JWT with short expiry (15 min) and refresh rotation; `httpOnly`/`Secure`/`SameSite` cookie flags; fail2ban for brute force protection; rate limiting on auth endpoints | `app/auth/`, fail2ban config, Cloudflare rate limits |
| A08 | **Software and Data Integrity Failures** | Gitleaks secrets scanning in CI/CD; detect-secrets pre-commit hook; signed commits encouraged; Docker image integrity via digest pinning | `.github/workflows/security-scan.yml`, `.pre-commit-config.yaml` |
| A09 | **Security Logging and Monitoring Failures** | Structured JSON audit logging; Wazuh host-based IDS; Grafana/Loki centralised log aggregation; API anomaly detection; tamper-evident audit trail | `app/services/audit_logger.py`, Wazuh config, Grafana/Loki stack |
| A10 | **Server-Side Request Forgery (SSRF)** | URL validation for external API calls; allowlisted external endpoints (Claude API, FSI API, Ollama); no user-controlled URLs passed to server-side HTTP clients without validation | `app/services/claude_service.py`, `app/services/ollama_client.py` |

## 11. Frontend-Specific Standards

### 11.1 TypeScript Strictness

- Enable strict TypeScript compilation (`strict: true` in `tsconfig.json`)
- Use `import type { X }` for type-only imports (verbatimModuleSyntax compliance)
- No `any` types in security-sensitive code (API responses, user inputs)

### 11.2 API Client Security

- All API calls through the centralised `api.ts` client
- Include CSRF tokens in state-changing requests
- Validate API response shapes before rendering
- Handle authentication errors with redirect to login

### 11.3 State Management

- Never store sensitive data (tokens, credentials) in `localStorage` or `sessionStorage`
- Use `httpOnly` cookies for authentication tokens
- Clear sensitive state on logout/session expiry

## 12. Version History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-02-04 | SENTINEL Security | Initial standards creation |

## 13. Related Documents

- [Application Security Policy](./application-security-policy.md) - Overarching application security policy
- [Application Security Pipeline](./application-security-pipeline.md) - CI/CD security implementation (Phase 63-03)
- [Vulnerability Management Process](./vulnerability-management-process.md) - Vulnerability lifecycle policy
- [Access Control Implementation](./access-control-implementation.md) - Authentication and authorisation (Phase 63-04)

---

*Document: Secure Coding Standards*
*Phase: 64-03 (RISK Governance Foundation)*
*Classification: Confidential*
*Review: Annual or on major framework change*
