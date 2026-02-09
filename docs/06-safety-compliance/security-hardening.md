---
title: "Security Hardening"
type: "reference"
status: "approved"
version: "2.0.0"
created: "2026-02-06"
updated: "2026-02-06"
author: "Sentinel Development Team"
tags: ["security", "authentication", "rate-limiting", "cors", "headers"]
domain: "security"
audience: "developers"
complexity: "intermediate"
estimated_read_time: 10
---

# Security Hardening (Phase 58-03)

This document describes the security hardening measures applied to the SENTINEL BMS Intelligence Platform as part of Phase 58-03.

## Overview

The hardening addresses Critical and High priority findings from the security audit:

| ID   | Severity | Fix                                      | Status |
|------|----------|------------------------------------------|--------|
| C-1  | Critical | Global authentication on all API routes   | Done   |
| C-2  | Critical | Secure JWT signing (no hardcoded secret)  | Done   |
| C-4  | Critical | Demo mode restricted to localhost         | Done   |
| H-1  | High     | Rate limiting on sensitive endpoints      | Done   |
| H-2  | High     | CORS restricted to configured origins     | Done   |
| H-6  | High     | Security headers on all responses         | Done   |
| H-7  | High     | HSTS enforcement in non-debug mode        | Done   |

## Authentication Enforcement (C-1)

### Approach: Global Middleware

Rather than adding `Depends(require_auth(...))` to each of the 60+ router files, a **global HTTP middleware** in `main.py` protects all `/api/` routes by default.

```python
@app.middleware("http")
async def enforce_authentication(request: Request, call_next):
    # Skip non-API routes and whitelisted public paths
    # In demo mode: allow localhost, require auth for remote
    # In production: require real auth on every request
```

### Public Paths (No Auth Required)

| Path                        | Reason                          |
|-----------------------------|---------------------------------|
| `/api/auth/login`           | Login endpoint                  |
| `/api/auth/login/mfa-complete` | MFA completion              |
| `/api/auth/refresh`         | Refresh token exchange          |
| `/api/auth/register`        | User registration               |
| `/api/auth/mfa/verify`      | MFA verification                |
| `/api/auth/verify`          | Token verification              |
| `/api/health`               | Health check                    |
| `/docs`, `/redoc`           | API documentation               |
| `/openapi.json`             | OpenAPI schema                  |
| `/api/clawd-webhooks/*`     | Telegram bot callbacks          |
| `/api/mcp-sse/*`            | MCP SSE transport               |

### Behaviour by Mode

- **Demo mode (localhost):** Auth bypassed, demo context created with ADMIN role
- **Demo mode (remote):** Real auth required; returns 403 if missing
- **Non-demo mode:** Real auth always required; returns 401 if missing

Individual endpoints can still use `Depends(require_auth(AuthLevel.ADMIN))` for role elevation on top of the global check.

## JWT Secret Configuration (C-2)

### Settings

| Variable         | Required | Description                         |
|------------------|----------|-------------------------------------|
| `JWT_SECRET_KEY` | Yes*     | Primary signing key (256-bit hex)   |
| `SUPABASE_KEY`   | Fallback | Used if JWT_SECRET_KEY not set      |

*Required when `DEMO_MODE=false`.

### Startup Validation

- If `DEMO_MODE=false` and neither `JWT_SECRET_KEY` nor `SUPABASE_KEY` is set, the application **refuses to start**.
- If `JWT_SECRET_KEY` is shorter than 32 characters, a warning is logged.

### Generating a Secure Secret

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

## Demo Mode Localhost Restriction (C-4)

When `DEMO_MODE=true`, authentication bypass is restricted to localhost IPs only:

- `127.0.0.1`
- `::1`
- `localhost`

Remote clients in demo mode must provide valid credentials. This prevents accidental exposure of the unauthenticated demo mode on network-accessible deployments.

Additionally, `DEMO_MODE=true` is **blocked in production** (`ENVIRONMENT=production`) at startup.

## Rate Limiting (H-1)

Powered by `slowapi` (built on `limits` library).

### Default Limits

| Endpoint Category     | Rate Limit    | Rationale                    |
|-----------------------|---------------|------------------------------|
| General (all routes)  | 100/minute    | Default protection           |
| Auth login            | 5/15minutes   | Brute force prevention       |
| Auth MFA complete     | 5/15minutes   | Brute force prevention       |
| Auth refresh          | 5/15minutes   | Refresh abuse prevention     |
| Admin API requests    | 30/minute     | Protect privileged surface   |
| Device control        | 10/minute     | Prevent control flooding     |
| Chat                  | 20/minute     | AI cost protection           |

### Response on Limit Exceeded

```json
HTTP 429 Too Many Requests
Retry-After: <seconds>

{"detail": "Rate limit exceeded. Please try again later."}
```

### Configuration

Rate limits are keyed by remote IP address (`CF-Connecting-IP`, `X-Forwarded-For`, `X-Real-IP`, then client host fallback). In a reverse proxy setup, ensure forwarding headers are passed correctly.

## CORS Configuration (H-2)

### Settings

```python
# In settings.py
cors_origins: list[str] = ["http://localhost:9096"]

# Override via environment variable:
CORS_ORIGINS='["http://localhost:9096","https://app.example.com"]'
```

### Allowed Methods and Headers

- **Methods:** `GET`, `POST`, `PUT`, `DELETE`, `OPTIONS`
- **Headers:** `Authorization`, `Content-Type`
- **Credentials:** Allowed (`allow_credentials=True`)

The wildcard (`*`) is no longer used for origins, methods, or headers.

## Security Headers (H-6, H-7)

Every HTTP response includes the following headers:

| Header                        | Value                               | Purpose                           |
|-------------------------------|-------------------------------------|-----------------------------------|
| `X-Content-Type-Options`      | `nosniff`                           | Prevent MIME sniffing             |
| `X-Frame-Options`             | `DENY`                              | Prevent clickjacking              |
| `X-XSS-Protection`            | `1; mode=block`                     | Legacy XSS protection             |
| `Referrer-Policy`             | `strict-origin-when-cross-origin`   | Limit referrer leakage            |
| `Strict-Transport-Security`   | `max-age=31536000; includeSubDomains` | HTTPS enforcement (non-debug)   |

HSTS is only set when `DEBUG=false` to avoid issues in local development.

## Files Modified

| File                                    | Changes                                      |
|-----------------------------------------|----------------------------------------------|
| `backend/app/main.py`                   | Global auth, rate limiter, CORS, sec headers  |
| `backend/app/config/settings.py`        | CORS origins default, JWT validation          |
| `backend/app/middleware/auth_middleware.py` | Demo mode localhost restriction            |
| `backend/app/api/auth.py`               | Rate limit on login endpoints                 |
| `backend/app/api/devices.py`            | Rate limit on control endpoint                |
| `backend/app/api/chat.py`               | Rate limit on chat endpoint                   |
| `backend/requirements.txt`              | Added `slowapi>=0.1.9`                        |
| `backend/tests/conftest.py`             | Enable demo mode for test environment         |

## Medium Priority Fixes (Phase 58-04)

Completed as part of Phase 58-04. These fixes complement the critical/high priority work from 58-03.

| ID   | Severity | Fix                                        | Status |
|------|----------|--------------------------------------------|--------|
| M-1  | Medium   | Pydantic input validation on device control | Done   |
| H-5  | High     | Subprocess call sanitisation               | Done   |
| M-3  | Medium   | JWT expiration reduced to 8 hours          | Done   |
| M-4  | Medium   | Sensitive data redacted from audit logs     | Done   |
| M-5  | Medium   | Brute force protection (5 attempts/15 min) | Done   |
| M-8  | Medium   | Generic error handler hides stack traces    | Done   |

### Input Validation on Device Control (M-1)

`DeviceControlRequest` Pydantic model validates all device control requests:

- **point**: alphanumeric + `_` `-` `.` `/` only, max 100 characters
- **value**: numeric -1000 to 10000, boolean, or string (max 200 chars, no shell metacharacters)
- **priority**: integer 1-16 (enforced by Pydantic `ge`/`le`)

This catches malformed input before it reaches the safety engine or device adapter.

### Subprocess Sanitisation (H-5)

`AlertNotifier._sanitize_for_shell()` strips shell metacharacters (`;&|` backtick `$(){}[]<>!#\`) from alert messages before passing to `subprocess.run()`. Arguments are always passed as a list (never `shell=True`) for defence in depth.

### JWT Expiration (M-3)

Token lifetime reduced from 30 days to 8 hours (one work shift). Configurable via `JWT_EXPIRATION_HOURS` environment variable. Default: 8.

### Audit Log Sanitisation (M-4)

`_sanitize_log_data()` in `audit_middleware.py` recursively redacts sensitive keys:
`password`, `token`, `secret`, `api_key`, `authorization`, `access_token`, `refresh_token`, `jwt`, `credential`, etc.

Applied to both request body and query parameter extraction.

### Brute Force Protection (M-5)

In-memory tracking keyed by email address:
- **Limit**: 5 failed attempts within 15 minutes
- **Response**: HTTP 429 with retry message
- **Scope**: Login and MFA completion endpoints
- Complements slowapi rate limiting which is keyed by IP address

### Generic Error Handler (M-8)

Global `Exception` handler in `main.py`:
- **Debug mode**: Returns full error detail (`str(exc)`)
- **Production**: Logs full error server-side, returns generic `"Internal server error"` to client

### Files Modified (58-04)

| File                                                  | Changes                              |
|-------------------------------------------------------|--------------------------------------|
| `backend/app/api/devices.py`                          | Pydantic DeviceControlRequest model  |
| `backend/app/services/clawd_integration/alert_notifier.py` | Subprocess sanitisation        |
| `backend/app/config/settings.py`                      | `jwt_expiration_hours` setting       |
| `backend/app/api/auth.py`                             | 8h expiry, brute force protection    |
| `backend/app/middleware/audit_middleware.py`           | Recursive log data sanitisation      |
| `backend/app/main.py`                                 | Global exception handler             |

### Deferred / Accepted Risk

| ID   | Item                    | Status         | Rationale                                              |
|------|-------------------------|----------------|--------------------------------------------------------|
| H-3  | Password authentication | Deferred       | Supabase Auth integration planned                      |
| M-2  | Request body size limits| Deferred       | Low risk with current JSON payloads                    |
| M-6  | CSP header              | Deferred       | Frontend served via Vite dev server; CSP on prod proxy |
| M-7  | CSRF protection         | Accepted risk  | API uses Bearer tokens (not cookies)                   |
