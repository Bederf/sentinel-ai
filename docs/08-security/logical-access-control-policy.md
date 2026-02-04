# Logical Access Control Policy

**Document:** SENTINEL BMS Platform - Logical Access Control Policy
**Document ID:** SENT-POL-LAC-001
**FSR Domain:** 4.7 - Logical Access Control (current 3.0, target 4.0 - HIGH gap)
**Version:** 1.0
**Effective Date:** 2026-02-04
**Owner:** Information Security Officer
**Review Cadence:** Annual (next review: 2027-02-04)
**Classification:** Internal

---

## 1. Purpose

This policy establishes the requirements for controlling logical access to all SENTINEL BMS Intelligence Platform systems, applications, and infrastructure. It ensures that access is granted based on the principle of least privilege, subject to proper authorisation, and continuously monitored. This policy addresses FSR Domain 4.7 (Logical Access Control), which is rated as a HIGH gap requiring remediation before FSR supplier onboarding.

## 2. Scope

This policy applies to:

- All SENTINEL systems: Contabo VPS (Ubuntu 24), Docker containers, Supabase (PostgreSQL), InfluxDB
- All SENTINEL applications: FastAPI backend, React frontend, MCP server, ML pipeline
- All external services: Cloudflare Tunnel, Claude API (Anthropic), MRI Evolution FSI API, WhatsApp/Telegram bots
- All users: SENTINEL personnel, contractors, client personnel, service accounts, and automated systems
- All access methods: SSH, API, web UI, database clients, Docker CLI

## 3. Regulatory and Standards Framework

| Reference | Relevance |
|---|---|
| FSR Privacy and Service Risk Assessment V8, Domain 4.7 | Logical Access Control requirements |
| POPIA (Act 4 of 2013) | Access to personal information |
| ISO 27001:2022 Annex A.5.15-5.18 | Access control policy, identity management, authentication |
| CIS Controls v8, Control 6 | Access control management |

---

## 4. Access Control Principles

### 4.1 Least Privilege

Users and systems are granted only the minimum access necessary to perform their designated functions. Access is not granted by default; it must be requested, justified, and approved.

### 4.2 Need-to-Know

Access to Confidential and Restricted data (as defined in the Information Classification Policy, SENT-POL-IC-001) requires a documented business need. Classification level determines who may access data and under what conditions.

### 4.3 Separation of Duties

Critical functions are divided among different individuals to prevent fraud and error:

- Code deployment and production access are separated (Developer deploys, Admin approves)
- Database schema changes require review before execution
- BMS device control actions are logged independently of the operator performing them
- Break-glass credential custody is split between two authorised individuals

### 4.4 Defence in Depth

Access control is enforced at multiple layers:

1. **Network layer:** Cloudflare Tunnel, no exposed ports, IP allowlisting
2. **OS layer:** Linux PAM groups, SSH key authentication, sudo restrictions
3. **Container layer:** Docker group membership, no root containers
4. **Application layer:** FastAPI auth middleware, RBAC endpoint classification
5. **Database layer:** Supabase Row Level Security (RLS), scoped API keys
6. **BMS layer:** Safety engine validates all device control commands

**Evidence:** Layered architecture implemented in Phase 63-04. See `docs/08-security/access-control-implementation.md` for architecture diagram.

---

## 5. Identity and Access Management (IAM)

### 5.1 User Provisioning

All new access requests follow this lifecycle:

| Step | Action | Responsible | SLA |
|---|---|---|---|
| 1. Request | Access request submitted with role justification and business need | Requesting manager | N/A |
| 2. Approve | Role-appropriate approver reviews and authorises | See Approval Matrix (5.1.1) | 2 business days |
| 3. Create | Admin creates user account across required systems | SENTINEL Admin | 1 business day |
| 4. Verify | New user confirms access works correctly | New user + Admin | 1 business day |
| 5. Document | Access grant recorded in audit log with approval reference | SENTINEL Admin | Same day as creation |

#### 5.1.1 Approval Matrix

| Requested Role | Approver | Escalation |
|---|---|---|
| Auditor | Operations Manager | Information Security Officer |
| Operator | Operations Manager | CTO |
| Developer | Development Lead | CTO |
| Admin | CTO/CISO (dual approval) | CEO |

#### 5.1.2 Account Creation Checklist

For each new account, the Admin must:

- [ ] Create Linux user on Contabo VPS
- [ ] Add user to appropriate `sentinel-*` PAM group (admin/operator/developer/auditor)
- [ ] Install user's SSH public key (Ed25519 or RSA 4096-bit)
- [ ] Configure 2FA (Google Authenticator TOTP)
- [ ] Create Supabase account with `sentinel_role` metadata (if API access needed)
- [ ] Generate API key (`sent_sk_*`) with appropriate scopes (if service integration needed)
- [ ] Update Cloudflare Access policy (if remote access needed)
- [ ] Record account creation in audit log with approval reference
- [ ] Schedule access review date (monthly for standard, quarterly for privileged)

### 5.2 User Deprovisioning

Access must be revoked when a user's role no longer requires it or employment/contract ends.

#### 5.2.1 Termination (Immediate Revocation)

**Trigger:** Employment termination, contract end, security incident
**SLA:** Within 1 hour of notification

| Step | Action | Responsible |
|---|---|---|
| 1. Disable | Lock Linux account, remove from all `sentinel-*` groups | SENTINEL Admin |
| 2. Revoke | Remove SSH authorized keys, revoke API keys | SENTINEL Admin |
| 3. Terminate sessions | Kill active SSH sessions, invalidate tokens | SENTINEL Admin |
| 4. Disable external | Disable Supabase account, update Cloudflare Access | SENTINEL Admin |
| 5. Verify | Confirm no residual access across all systems | SENTINEL Admin |
| 6. Document | Record deprovisioning in audit log | SENTINEL Admin |

#### 5.2.2 Role Change

**Trigger:** Job function change, project reassignment
**SLA:** Within 24 hours of approved role change

| Step | Action | Responsible |
|---|---|---|
| 1. Request | Manager submits role change request | Requesting manager |
| 2. Approve | New role approver reviews | See Approval Matrix |
| 3. Adjust | Remove old group memberships, add new ones | SENTINEL Admin |
| 4. Update | Adjust API key scopes, Supabase role metadata | SENTINEL Admin |
| 5. Verify | Supervisor confirms correct access | Supervisor |
| 6. Document | Change recorded in audit log | SENTINEL Admin |

### 5.3 Access Modification

Any change to existing access (scope expansion, additional system access, temporary elevation) follows the same Request-Approve-Implement-Audit cycle as provisioning.

**Temporary privilege elevation:**
- Maximum duration: 8 hours
- Requires Admin approval
- Must specify exact scope and justification
- Automatically reverts after duration expires
- All actions during elevation are logged

---

## 6. Role-Based Access Control (RBAC)

### 6.1 Role Definitions

SENTINEL implements four hierarchical roles. Higher roles inherit all permissions of lower roles.

| Role | Code | Level | Description | Typical Assignment |
|---|---|---|---|---|
| Auditor | `SentinelRole.AUDITOR` | 1 (lowest) | Read-only access for compliance review | External auditors, compliance staff |
| Operator | `SentinelRole.OPERATOR` | 2 | BMS operations including device control | FM technicians, building operators |
| Developer | `SentinelRole.DEVELOPER` | 3 | Development, debugging, and deployment | Software engineers, ML engineers |
| Admin | `SentinelRole.ADMIN` | 4 (highest) | Full platform administration | CTO, CISO, designated admin |

**Hierarchy:**
```
Admin (4) --> inherits Developer, Operator, Auditor
Developer (3) --> inherits Operator, Auditor
Operator (2) --> inherits Auditor
Auditor (1) --> base read-only access
```

**Implementation:** `backend/app/models/auth.py` defines the role hierarchy and auth levels.

### 6.2 Authentication Levels

SENTINEL API endpoints are classified into four authentication levels:

| Auth Level | Minimum Role | Scope |
|---|---|---|
| PUBLIC | None | Health checks, API documentation (`/api/health`, `/docs`) |
| AUTHENTICATED | Auditor | Read access to equipment, sensors, alerts, chat |
| OPERATOR | Operator | Device control, optimization, HVAC management, MCP tool calls |
| ADMIN | Admin | Simulation control, admin configuration, user management |

**Implementation:** `backend/app/middleware/auth_middleware.py` enforces auth level classification for every endpoint.

### 6.3 Permission Matrix

| Capability | Auditor | Operator | Developer | Admin |
|---|---|---|---|---|
| View equipment, sensors, alerts | Yes | Yes | Yes | Yes |
| View audit logs | Yes | Yes | Yes | Yes |
| View predictions, analytics | Yes | Yes | Yes | Yes |
| Use AI chat (read queries) | Yes | Yes | Yes | Yes |
| Control BMS devices | No | Yes | Yes | Yes |
| Execute optimization recommendations | No | Yes | Yes | Yes |
| Call MCP tools (write operations) | No | Yes | Yes | Yes |
| Submit work orders | No | Yes | Yes | Yes |
| Access Docker containers (ps, logs) | No | Yes | Yes | Yes |
| Restart services | No | No | Yes | Yes |
| Access Docker (exec, build) | No | No | Yes | Yes |
| Database access (data queries) | No | No | Yes | Yes |
| Deploy code changes | No | No | Yes | Yes |
| Manage users and groups | No | No | No | Yes |
| Configure firewalls | No | No | No | Yes |
| Manage API keys | No | No | No | Yes |
| Access break-glass credentials | No | No | No | Yes |
| Configure Cloudflare Access | No | No | No | Yes |
| Run simulations | No | No | No | Yes |

### 6.4 Role Assignment Workflow

1. Manager requests role assignment with justification
2. Approver reviews per Approval Matrix (Section 5.1.1)
3. Admin provisions role across all systems
4. User confirms access and signs acceptable use acknowledgement
5. Assignment documented in audit log with approval reference

**Principle:** No user may approve their own role assignment. Dual approval required for Admin role.

---

## 7. System-Specific Access Controls

### 7.1 Contabo VPS (Ubuntu 24)

| Control | Implementation | Reference |
|---|---|---|
| SSH key-only authentication | `PasswordAuthentication no` | `infrastructure/ssh/sshd_hardening.conf` |
| No root login | `PermitRootLogin no` | `infrastructure/ssh/sshd_hardening.conf` |
| 2FA (TOTP) required | `libpam-google-authenticator` | Phase 63-04 |
| Sudo via PAM groups | 4 groups with scoped privileges | `infrastructure/pam/sudo-sentinel.conf` |
| Max 3 auth attempts | `MaxAuthTries 3` | `infrastructure/ssh/sshd_hardening.conf` |
| Strong ciphers only | ChaCha20-Poly1305, AES-256-GCM | `infrastructure/ssh/sshd_hardening.conf` |
| No X11/TCP forwarding | `AllowTcpForwarding no` | `infrastructure/ssh/sshd_hardening.conf` |
| Session timeout | `ClientAliveInterval 300` (5 min) | `infrastructure/ssh/sshd_hardening.conf` |

### 7.2 Docker Containers

| Control | Implementation |
|---|---|
| Container management restricted | Docker group membership required (developer and admin only) |
| No root containers | All SENTINEL containers run as non-root users |
| No privileged mode | `--privileged` flag prohibited |
| Read-only filesystems | Application containers use read-only root filesystems where possible |
| Resource limits | CPU and memory limits enforced per container |
| Image scanning | Container images scanned for vulnerabilities before deployment (Phase 63-05) |

### 7.3 Supabase / PostgreSQL

| Control | Implementation |
|---|---|
| Named database accounts | No shared credentials; each service has dedicated account |
| Row Level Security (RLS) | Tenant isolation enforced at database level |
| API key scoping | Separate anon key (public), service role key (admin) |
| Connection encryption | TLS required for all database connections |
| Query logging | All queries logged for audit trail |

### 7.4 Cloudflare

| Control | Implementation |
|---|---|
| Dashboard access restricted | SSO with MFA required |
| API tokens scoped per service | Separate tokens for DNS, Tunnel, WAF management |
| Tunnel-only access | No direct port exposure; all traffic via Cloudflare Tunnel |
| Access policies | Geo-restriction and device posture checks via Cloudflare Access |

### 7.5 Claude API (Anthropic)

| Control | Implementation |
|---|---|
| Single service account | One `ANTHROPIC_API_KEY` per environment |
| Usage monitoring | Token usage tracked per request |
| PII guard | `backend/app/middleware/pii_guard.py` redacts PI before API calls |
| Rate limiting | Application-level rate limiting on chat endpoints |
| No Restricted data | Policy prohibits sending Restricted-classified data to Claude API |

### 7.6 MRI Evolution FSI API

| Control | Implementation |
|---|---|
| Service account | Dedicated API credentials for SENTINEL integration |
| Certificate pinning | TLS certificate validation to FSI gateway |
| Scoped permissions | API access limited to work order and asset operations |
| Audit logging | All FSI API calls logged with request/response metadata |

### 7.7 WhatsApp / Telegram Bots

| Control | Implementation |
|---|---|
| Bot tokens stored securely | Environment variables, never in source code |
| Consent verification | Consent captured before processing user messages (Phase 63-06) |
| Message retention limits | Messages not retained beyond processing window |
| Pre-commit hooks | Block hardcoded tokens in source code (Phase 63-03) |

---

## 8. Privileged Access Management (PAM)

### 8.1 Definition of Privileged Access

| Access Type | Classification | Controls Required |
|---|---|---|
| Full sudo on server | Privileged | sentinel-admin group, MFA, session logging |
| Docker exec (shell into container) | Privileged | Admin/Developer role, justification logged |
| Database write access | Privileged | Admin/Developer role, query logging |
| BMS device control (write commands) | Privileged | Operator role, safety engine validation, audit log |
| User/group management | Privileged | Admin only, dual approval for admin role grants |
| Firewall configuration | Privileged | Admin only |
| API key management | Privileged | Admin only |
| Break-glass credential access | Privileged | Admin only, post-use review required |

### 8.2 PAM Controls

**Implementation:** `infrastructure/pam/sudo-sentinel.conf`

| Group | Permitted Commands |
|---|---|
| sentinel-admin | Full sudo (with password re-authentication) |
| sentinel-operator | `docker ps`, `docker logs`, `systemctl restart sentinel-*` |
| sentinel-developer | Docker management, service management (no user/firewall) |
| sentinel-auditor | Read-only log access (`cat`, `less` on log files) |

### 8.3 Administrative Access Requirements

- All administrative access requires MFA (SSH key + TOTP)
- Privileged sessions are logged with full I/O recording (`/var/log/sudo.log`)
- Administrative actions are auditable and attributable to named individuals
- Shared administrative accounts are prohibited
- Generic accounts (root, postgres, docker) are not used for interactive access

### 8.4 Emergency Break-Glass Procedure

For system emergencies requiring immediate access beyond normal authorisation:

| Step | Action | SLA |
|---|---|---|
| 1. Trigger | System emergency identified (service outage, security incident, safety event) | Immediate |
| 2. Access | Retrieve break-glass credentials from secure vault (password manager or sealed envelope) | < 15 minutes |
| 3. Authenticate | Log in with break-glass credentials; all actions fully audited | Immediate |
| 4. Resolve | Perform minimum necessary actions to resolve emergency | Duration of incident |
| 5. Report | Document all actions taken during emergency access | Within 4 hours |
| 6. Review | Post-incident review by Information Security Officer | Within 24 hours |
| 7. Rotate | Break-glass credentials rotated after each use | Within 24 hours |

**BMS-specific emergency controls:**

SENTINEL includes BMS-specific emergency modes implemented in `backend/app/middleware/emergency_controls.py`:

| Mode | Effect | Trigger |
|---|---|---|
| MAINTENANCE | Blocks write operations | Planned downtime |
| READ_ONLY | Blocks all database writes | Database maintenance |
| SAFETY_LOCKDOWN | Blocks all device control commands | Building emergency |
| API_SHUTDOWN | Blocks all API calls | Full system shutdown |

---

## 9. Access Reviews

### 9.1 Monthly Review

| Review Item | Responsible | Output |
|---|---|---|
| All active accounts reviewed | Team leads | Stale account report |
| Role assignments verified | Operations Manager | Role verification log |
| Dormant accounts identified (>30 days inactive) | SENTINEL Admin | Warning notifications sent |
| Sudo log review for anomalies | Information Security Officer | Anomaly report |
| Failed authentication attempts reviewed | Information Security Officer | Threat assessment |

### 9.2 Quarterly Review (Privileged Accounts)

| Review Item | Responsible | Output |
|---|---|---|
| Admin and Developer accounts reviewed | CISO / Security Lead | Privileged access report |
| Full audit of privileged access usage | Information Security Officer | Usage analysis |
| 2FA status verified for all privileged users | SENTINEL Admin | MFA compliance report |
| Service account ownership confirmed | Service account owners | Ownership register |
| API key rotation status checked | SENTINEL Admin | Rotation compliance report |

### 9.3 Annual Review

| Review Item | Responsible | Output |
|---|---|---|
| Complete policy review | Information Security Officer | Updated policy (if needed) |
| Role definitions and hierarchy assessment | CTO | Role effectiveness report |
| Authentication method effectiveness | Information Security Officer | Technology assessment |
| Emergency access procedure test | SENTINEL Admin | Procedure validation report |

---

## 10. Service Account Management

### 10.1 Service Account Inventory

| Account | Purpose | Owner | Rotation Schedule |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | Claude AI API access | CTO | Annually |
| `SUPABASE_KEY` | Database anon access | Developer Lead | Annually |
| `SUPABASE_SERVICE_ROLE_KEY` | Database admin access | CTO | Annually |
| FSI API credentials | MRI Evolution integration | Operations Manager | Annually |
| WhatsApp Bot token | Telegram bot access | Developer Lead | Annually |
| Telegram Bot token | Telegram bot access | Developer Lead | Annually |
| `sent_sk_*` API keys | External integrations | Per integration owner | Every 90 days |

### 10.2 Service Account Policies

- **Naming convention:** `svc-sentinel-<purpose>` (e.g., `svc-sentinel-backup`)
- **No interactive login:** Service accounts cannot be used for interactive access
- **Individual ownership:** Each service account has a documented human owner
- **Rotation:** Mandatory rotation per schedule; immediate rotation if compromise suspected
- **Monitoring:** All service account activity logged and reviewed quarterly
- **Minimum scope:** Service accounts granted only permissions required for their function

---

## 11. Remote Access

### 11.1 Remote Access Method

All remote access to SENTINEL infrastructure is via **Cloudflare Tunnel**. No ports are directly exposed to the internet.

| Control | Implementation |
|---|---|
| Access method | Cloudflare Tunnel (encrypted, authenticated) |
| Authentication | SSO + device posture checks |
| Port exposure | Zero (all traffic via tunnel) |
| SSH access | Via Cloudflare Tunnel with SSH key + 2FA |
| Geographic restriction | Configurable geo-policies via Cloudflare Access |

### 11.2 Prohibited Remote Access Methods

- Direct SSH to public IP (no ports exposed)
- VPN concentrators (Cloudflare Tunnel replaces VPN)
- Remote desktop protocols (RDP, VNC)
- Unencrypted protocols (telnet, FTP, HTTP)

---

## 12. Compliance Evidence

The following Phase 63-04 technical controls serve as evidence that this policy is implemented:

| Policy Requirement | Technical Control | Implementation File |
|---|---|---|
| RBAC model | 4 roles with hierarchical inheritance | `backend/app/models/auth.py` |
| Auth middleware | Bearer token + API key validation | `backend/app/middleware/auth_middleware.py` |
| SSH hardening | Key-only, no root, 2FA | `infrastructure/ssh/sshd_hardening.conf` |
| PAM groups | Scoped sudo per role | `infrastructure/pam/sudo-sentinel.conf` |
| Access matrix | Full permission documentation | `infrastructure/pam/access-matrix.md` |
| PII protection | SA ID/phone/email redaction | `backend/app/middleware/pii_guard.py` |
| Error sanitisation | No stack traces in production | `backend/app/middleware/error_sanitization.py` |
| Emergency controls | Safety lockdown modes | `backend/app/middleware/emergency_controls.py` |
| Audit logging | All control actions logged | `backend/app/middleware/audit_middleware.py` |
| Security logging | Security events captured | `backend/app/middleware/security_logging.py` |

---

## 13. Enforcement

Violations of this policy are handled according to severity:

| Violation | Example | Consequence |
|---|---|---|
| Minor | Using a shared account for convenience | Corrective training, access review |
| Moderate | Bypassing approval for access grant | Formal warning, access audit |
| Severe | Sharing credentials, disabling MFA | Access revocation, disciplinary action |
| Critical | Unauthorised access to Restricted data | Immediate access revocation, investigation, potential legal action |

---

## 14. Related Documents

| Document | Reference |
|---|---|
| Information Classification Policy | SENT-POL-IC-001 |
| Password Security Standard | SENT-STD-PWD-001 |
| Access Control Implementation (Technical) | `docs/08-security/access-control-implementation.md` |
| Information Security Framework | SENT-POL-ISF-001 (Phase 64-01) |

---

## 15. Version Control

| Version | Date | Author | Changes |
|---|---|---|---|
| 1.0 | 2026-02-04 | Information Security Officer | Initial policy creation |

---

*SENTINEL BMS Intelligence Platform - Logical Access Control Policy*
*FSR Domain 4.7 - Logical Access Control*
*Classification: Internal*
