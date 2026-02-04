# Access Control Implementation

**Document:** SENTINEL BMS Platform - Access Control Architecture
**FSR Domain:** 4.7 - Logical Access Control (current 3.0, target 4.0 - HIGH gap)
**Version:** 1.0
**Last Updated:** 2026-02-04
**Review Cadence:** Monthly (access review), Quarterly (privileged accounts)

## Overview

SENTINEL implements a layered access control architecture spanning four layers:
1. **OS/Infrastructure** - Linux PAM, SSH hardening, sudo restrictions
2. **Container** - Docker group membership, Swarm role separation
3. **Database** - Supabase Row Level Security (RLS), API key scoping
4. **Application** - FastAPI middleware, RBAC dependencies, endpoint classification

Each layer enforces the principle of least privilege independently, providing defense in depth.

## Architecture Diagram

```
                    ┌─────────────────────────────────────┐
                    │         Cloudflare Tunnel            │
                    │    (SSO + device posture checks)     │
                    └──────────────┬──────────────────────┘
                                   │
          ┌────────────────────────┼────────────────────────┐
          │                        │                        │
    ┌─────▼─────┐          ┌──────▼──────┐          ┌──────▼──────┐
    │    SSH     │          │  Frontend   │          │   API Key   │
    │  Key+2FA  │          │   (React)   │          │ (sent_sk_*) │
    └─────┬─────┘          └──────┬──────┘          └──────┬──────┘
          │                       │                        │
    ┌─────▼─────┐          ┌──────▼──────────────────────▼─┐
    │   Linux   │          │        FastAPI Backend          │
    │   PAM /   │          │  ┌──────────────────────────┐  │
    │  Sudoers  │          │  │  Auth Middleware          │  │
    │           │          │  │  - Bearer Token (JWT)     │  │
    └───────────┘          │  │  - API Key validation     │  │
                           │  │  - Demo mode bypass       │  │
                           │  └──────────┬───────────────┘  │
                           │             │                   │
                           │  ┌──────────▼───────────────┐  │
                           │  │  RBAC Authorization       │  │
                           │  │  - AuthLevel check        │  │
                           │  │  - Role hierarchy         │  │
                           │  │  - Endpoint classification│  │
                           │  └──────────┬───────────────┘  │
                           │             │                   │
                           │  ┌──────────▼───────────────┐  │
                           │  │  Safety Engine            │  │
                           │  │  - Device control rules   │  │
                           │  │  - Emergency lockdown     │  │
                           │  └──────────┬───────────────┘  │
                           │             │                   │
                           │  ┌──────────▼───────────────┐  │
                           │  │  Audit Logging            │  │
                           │  │  - All control actions    │  │
                           │  │  - Auth attempts          │  │
                           │  │  - Access decisions       │  │
                           │  └──────────────────────────┘  │
                           │                                 │
                           │  ┌──────────────────────────┐  │
                           │  │  Supabase (PostgreSQL)    │  │
                           │  │  - Row Level Security     │  │
                           │  │  - JWT token validation   │  │
                           │  └──────────────────────────┘  │
                           └─────────────────────────────────┘
```

## Role-Based Access Control (RBAC)

### Role Definitions

| Role | Code | Hierarchy Level | Description |
|------|------|----------------|-------------|
| Admin | `SentinelRole.ADMIN` | 4 (highest) | Full platform administration |
| Developer | `SentinelRole.DEVELOPER` | 3 | Development and debugging |
| Operator | `SentinelRole.OPERATOR` | 2 | BMS operations and control |
| Auditor | `SentinelRole.AUDITOR` | 1 (lowest) | Read-only compliance review |

### Role Hierarchy

Roles are hierarchical: higher roles inherit all permissions of lower roles.

```
ADMIN (4) ──► inherits DEVELOPER, OPERATOR, AUDITOR
DEVELOPER (3) ──► inherits OPERATOR, AUDITOR
OPERATOR (2) ──► inherits AUDITOR
AUDITOR (1) ──► base read-only access
```

### Authentication Levels

Endpoints are classified into four authentication levels:

| Level | Minimum Role | Examples |
|-------|-------------|---------|
| `PUBLIC` | None | `/api/health`, `/docs`, `/openapi.json` |
| `AUTHENTICATED` | Auditor | `/api/chat`, `/api/equipment`, `/api/sensors` |
| `OPERATOR` | Operator | `/api/devices/*/control`, `/api/optimization/*` |
| `ADMIN` | Admin | `/api/simulation/*`, admin configuration |

### Endpoint Classification

```python
# Public - no auth required
PUBLIC_ENDPOINTS = {"/api/health", "/docs", "/redoc", "/openapi.json"}

# Admin-only endpoints
("/api/simulation/", AuthLevel.ADMIN)

# Operator endpoints (control actions)
("/api/devices/", AuthLevel.OPERATOR)
("/api/optimization/", AuthLevel.OPERATOR)
("/api/mcp/simbiot/call", AuthLevel.OPERATOR)
("/api/hvac/", AuthLevel.OPERATOR)

# Authenticated endpoints (read access)
("/api/chat", AuthLevel.AUTHENTICATED)
("/api/equipment", AuthLevel.AUTHENTICATED)
# ... etc
```

## Authentication Methods

### 1. SSH Key + 2FA (TOTP)

**Used for:** Server access (Contabo VPS)

- **Factor 1:** Ed25519 SSH key (something you have)
- **Factor 2:** Google Authenticator TOTP (something you know)
- **Configuration:** `infrastructure/ssh/sshd_hardening.conf`
- **Status:** Active and enforced

**SSH Hardening:**
- Root login disabled (`PermitRootLogin no`)
- Password auth disabled (`PasswordAuthentication no`)
- Max 3 auth attempts, 30-second grace time
- Only `sentinel-admin`, `sentinel-operator`, `sentinel-developer` groups
- Strong ciphers only (ChaCha20-Poly1305, AES-256-GCM)
- No X11/TCP forwarding

### 2. Bearer Token (Supabase JWT)

**Used for:** Application access (frontend, API clients)

- Token issued by Supabase authentication
- HS256 signature verification against `SUPABASE_KEY`
- Expiry validation enforced
- Role extracted from `user_metadata.sentinel_role` or `app_metadata.sentinel_role`
- Supports standard JWT claims (`sub`, `email`, `exp`, `iss`)

**Token Flow:**
```
User login ──► Supabase Auth ──► JWT issued
                                       │
API request ──► Bearer header ──► Middleware validates ──► AuthContext created
                                                                   │
                                                          Endpoint checks ──► Authorized/Denied
```

### 3. API Key (`sent_sk_*`)

**Used for:** Service accounts, external integrations, automated systems

- Prefix: `sent_sk_` (identifies SENTINEL service keys)
- Storage: SHA-256 hash stored; plaintext shown once at creation
- Validation: Hash comparison using `secrets.compare_digest` (timing-safe)
- Extraction: `Authorization: Bearer sent_sk_...` or `X-API-Key: sent_sk_...`

**API Key Lifecycle:**
1. Generate key with `generate_api_key()` -> returns (plaintext, hash)
2. Store hash in key store with owner, role, scopes
3. Show plaintext to user once (never stored)
4. Validate incoming requests by hashing and comparing
5. Rotate annually or immediately if compromised

### 4. Cloudflare Access

**Used for:** Remote access to SENTINEL (Cloudflare Tunnel)

- SSO integration for authorized users
- Device posture checks (managed devices only)
- Geographical access policies
- No direct port exposure on the internet

## Privileged Access Management (PAM)

### What Constitutes Privileged Access

| Access Type | Classification | Controls |
|-------------|---------------|----------|
| Full sudo on server | Privileged | sentinel-admin group only |
| Docker exec (shell into container) | Privileged | admin and developer only |
| Database write access | Privileged | admin and developer only |
| Device control (BMS write) | Privileged | operator and above |
| User/group management | Privileged | admin only |
| Firewall configuration | Privileged | admin only |
| API key management | Privileged | admin only |

### Sudo Configuration

Defined in `infrastructure/pam/sudo-sentinel.conf`:

- **sentinel-admin:** Full sudo with password required
- **sentinel-operator:** Restricted to docker ps/logs/restart, systemctl restart sentinel-*
- **sentinel-developer:** Docker access, service management (no user/firewall management)
- **sentinel-auditor:** Read-only log access only

**All sudo commands are logged** to `/var/log/sudo.log` with full I/O recording.

### Access Control Matrix

Full matrix documented in `infrastructure/pam/access-matrix.md`, covering:
- OS/Infrastructure (SSH, sudo, packages)
- Docker/Containers (ps, exec, rm, build, Swarm)
- Database (full, schema, data, backup)
- Application (read, write, control, admin)
- Cloudflare (tunnel, DNS, WAF, access policies)
- Monitoring (Grafana, Loki, Wazuh)

## MFA Implementation

### Current State

| Component | MFA Status | Method |
|-----------|-----------|--------|
| SSH Server Access | Active | SSH Key + TOTP (2FA) |
| Cloudflare Tunnel | Active | SSO + device posture |
| Supabase Dashboard | Active | Supabase MFA (if enabled) |
| SENTINEL API | Planned | Bearer token (Supabase handles MFA) |
| Docker Admin | Active | SSH required (inherits SSH 2FA) |

### SSH 2FA Setup

SSH 2FA is configured via `libpam-google-authenticator`:

```bash
# Add 2FA for a new user
su - <username>
google-authenticator -t -d -f -r 3 -R 30 -w 3
# Scan QR code with authenticator app
# Save backup codes securely
```

### Application MFA (Planned)

When Supabase MFA is enabled for a user:
1. User logs in with email/password via Supabase
2. Supabase prompts for TOTP verification
3. Token issued only after MFA verification
4. SENTINEL middleware validates the MFA-verified token

## Access Provisioning Process

### New User Access

```
1. REQUEST    ──► Manager submits access request form
                   - User identity verified
                   - Role justification documented
                   - Business need confirmed

2. APPROVE    ──► Role-appropriate approver reviews
                   - Admin: CTO/CIO approval required
                   - Operator: Operations Manager approval
                   - Developer: Development Lead approval
                   - Auditor: Compliance Officer approval

3. PROVISION  ──► Admin creates account
                   - Linux user created
                   - Added to appropriate sentinel-* group
                   - SSH key installed
                   - 2FA configured
                   - API key generated (if needed)
                   - Supabase account created (if needed)

4. VERIFY     ──► New user confirms access
                   - SSH login with 2FA tested
                   - API access verified
                   - Role-appropriate actions tested

5. DOCUMENT   ──► Access grant recorded
                   - Audit log entry created
                   - Approval reference documented
                   - Review date scheduled
```

### Role Change

```
1. REQUEST    ──► Manager submits role change request
2. APPROVE    ──► New role approver reviews
3. ADJUST     ──► Within 24 hours:
                   - Old group memberships removed
                   - New group memberships added
                   - API key scopes updated (if applicable)
4. VERIFY     ──► Supervisor verifies correct access
5. DOCUMENT   ──► Change recorded in audit log
```

## Access Deprovisioning Process

### Termination (Immediate Revocation)

Within **1 hour** of termination notification:

```
1. SSH keys removed from ~/.ssh/authorized_keys
2. User removed from all sentinel-* groups
3. API keys revoked
4. Supabase account disabled
5. Active sessions terminated
6. Cloudflare Access policy updated
7. Deprovisioning documented in audit log
```

### Role Change (24-hour window)

```
1. Old group memberships removed
2. New group memberships added
3. API key scopes adjusted
4. Verified by supervisor
5. Change documented
```

## Access Review Schedule

### Monthly Review

- All active accounts reviewed by respective team leads
- Verify each account still needed
- Confirm role assignments are correct
- Check for dormant accounts (>30 days inactive)
- Review sudo logs for anomalous activity
- Document review completion and findings

### Quarterly Review (Privileged Accounts)

- All Admin and Developer accounts reviewed by security lead
- Full audit of privileged access usage
- Review sudo command history for anomalies
- Verify 2FA is active for all privileged users
- Confirm service account ownership current
- API key rotation status checked

### Annual Review

- Complete access control policy review
- Role definitions and hierarchy assessment
- Authentication method effectiveness evaluation
- Emergency access procedure test

## Stale Account Policy

| Condition | Action |
|-----------|--------|
| >30 days inactive | Warning notification to user and manager |
| >90 days inactive | Account disabled, user notified |
| >180 days inactive | Account deleted after manager confirmation |
| Service accounts | Exempt from inactivity, annual ownership confirmation required |

## Password Policy

| Requirement | Value |
|-------------|-------|
| Minimum length | 14 characters |
| Complexity | Upper + lower + digit + special character |
| History | No reuse of last 12 passwords |
| Expiry (regular) | 90 days |
| Expiry (privileged) | 60 days |
| Lockout threshold | 5 failed attempts |
| Lockout duration | 30 minutes (auto-unlock) |

**Note:** SSH key authentication is the primary method. Passwords are used for sudo re-authentication only.

## Service Account Management

| Aspect | Policy |
|--------|--------|
| Naming | `svc-sentinel-<purpose>` (e.g., `svc-sentinel-backup`) |
| API Key prefix | `sent_sk_` |
| Rotation | Annual minimum; immediate if compromised |
| Ownership | Each account has documented human owner |
| Review | Quarterly review of all service accounts |
| Logging | All service account activity logged |

## Emergency Access (Break-Glass)

### Procedure

1. **Trigger:** System emergency requiring immediate admin access
2. **Access:** Break-glass credentials from secure vault (password manager / sealed envelope)
3. **Logging:** All actions during emergency access fully audited
4. **Review:** Post-incident review within 24 hours
5. **Rotation:** Break-glass credentials rotated after each use
6. **Scope:** Emergency access grants full admin for incident duration only

### BMS Safety Lockdown

SENTINEL includes a BMS-specific emergency mode:

```python
from app.middleware.emergency_controls import get_emergency_controls, EmergencyMode

# Activate safety lockdown (blocks all device control)
service = get_emergency_controls()
service.activate(EmergencyMode.SAFETY_LOCKDOWN, "admin-user", "Building emergency")

# Deactivate when safe
service.deactivate("admin-user")
```

Emergency modes:
- **MAINTENANCE:** Blocks write operations (planned downtime)
- **READ_ONLY:** Blocks all writes (database maintenance)
- **SAFETY_LOCKDOWN:** Blocks device control (building emergency)
- **API_SHUTDOWN:** Blocks all API calls (full shutdown)

## Security Middleware Stack

### Available Components

| Middleware | File | Purpose | Status |
|-----------|------|---------|--------|
| Auth Middleware | `middleware/auth_middleware.py` | Bearer/API key authentication | Created, opt-in |
| Error Sanitization | `middleware/error_sanitization.py` | Prevents info disclosure | Created, opt-in |
| PII Guard | `middleware/pii_guard.py` | SA ID/phone/email detection | Created, utility |
| Emergency Controls | `middleware/emergency_controls.py` | Safety lockdown/maintenance | Created, opt-in |
| Audit Middleware | `middleware/audit_middleware.py` | Control action logging | Active |
| Security Logging | `middleware/security_logging.py` | Security event logging | Active |

### Usage Pattern

```python
from app.middleware.auth_middleware import require_auth, require_role
from app.models.auth import AuthLevel, SentinelRole

# Require authentication level
@router.get("/api/equipment")
async def get_equipment(auth: AuthContext = Depends(require_auth(AuthLevel.AUTHENTICATED))):
    ...

# Require specific role
@router.post("/api/devices/{id}/control")
async def control_device(auth: AuthContext = Depends(require_role(SentinelRole.OPERATOR))):
    ...

# PII redaction before LLM processing
from app.middleware.pii_guard import pii_guard
result = pii_guard.redact("Technician SA ID: 8801235111089")
# result.redacted_text contains placeholders instead of PII
```

### Demo Mode Behavior

When `DEMO_MODE=true`:
- Auth middleware creates demo AuthContext with ADMIN role
- All endpoints accessible without credentials
- Authentication attempts are still logged
- No breaking changes to existing demo flows

## Compliance References

| FSR Domain | Control | Implementation |
|-----------|---------|---------------|
| 4.7 Logical Access Control | RBAC model | 4 roles, hierarchy, endpoint classification |
| 4.7 Logical Access Control | PAM controls | Sudo restrictions, SSH hardening |
| 4.7 Logical Access Control | MFA enforcement | SSH 2FA active, app MFA via Supabase |
| 4.7 Logical Access Control | Access reviews | Monthly/quarterly schedule defined |
| 4.11 Incident Response | Emergency controls | Safety lockdown, maintenance mode |
| 4.12 Data Privacy | PII protection | SA ID/phone/email redaction guard |

## Implementation Files

| Category | File Path |
|----------|-----------|
| Auth Models | `backend/app/models/auth.py` |
| Auth Middleware | `backend/app/middleware/auth_middleware.py` |
| Error Sanitization | `backend/app/middleware/error_sanitization.py` |
| PII Guard | `backend/app/middleware/pii_guard.py` |
| Emergency Controls | `backend/app/middleware/emergency_controls.py` |
| Sudo Configuration | `infrastructure/pam/sudo-sentinel.conf` |
| SSH Hardening | `infrastructure/ssh/sshd_hardening.conf` |
| Access Matrix | `infrastructure/pam/access-matrix.md` |
| Audit Middleware | `backend/app/middleware/audit_middleware.py` |
| Security Logging | `backend/app/middleware/security_logging.py` |

---
*SENTINEL BMS Intelligence Platform - Access Control Implementation*
*FSR Domain 4.7 - Logical Access Control*
*Last Updated: 2026-02-04*
