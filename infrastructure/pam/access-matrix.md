# SENTINEL Access Control Matrix

**Document:** Privileged Access Management (PAM) - Access Matrix
**FSR Domain:** 4.7 - Logical Access Control
**Last Updated:** 2026-02-04
**Review Cadence:** Monthly (access review), Quarterly (privileged accounts)

## Role Definitions

### Admin (sentinel-admin)
- **Purpose:** Full system administration, infrastructure management, security operations
- **Typical Users:** Shadow IT / DevOps engineers, Platform owner
- **Assignment:** Requires CTO/CIO approval + documented justification
- **Review:** Quarterly by security lead

### Operator (sentinel-operator)
- **Purpose:** Day-to-day BMS operations, service monitoring, log review
- **Typical Users:** FM operations team, NOC engineers, building managers
- **Assignment:** Requires Operations Manager approval
- **Review:** Monthly by operations lead

### Developer (sentinel-developer)
- **Purpose:** Application development, debugging, testing
- **Typical Users:** Software developers, integration engineers
- **Assignment:** Requires Development Lead approval
- **Review:** Monthly by development lead

### Auditor (sentinel-auditor)
- **Purpose:** Compliance verification, security review, audit trail inspection
- **Typical Users:** Internal audit, compliance officers, external auditors
- **Assignment:** Requires Compliance Officer or CTO approval
- **Review:** Monthly, access granted for specific audit periods only

## Access Matrix

| Resource | Admin | Operator | Developer | Auditor |
|----------|-------|----------|-----------|---------|
| **OS / Infrastructure** | | | | |
| SSH Access | Full | Restricted | Full | None |
| Sudo (system commands) | Full | Restricted set | Docker + services | Read-only logs |
| User management | Yes | No | No | No |
| Firewall/network config | Yes | No | No | No |
| System package install | Yes | No | No | No |
| **Docker / Containers** | | | | |
| docker ps / logs / stats | Yes | Yes | Yes | logs only |
| docker restart | Yes | Yes | Yes | No |
| docker exec (shell into container) | Yes | No | Yes | No |
| docker rm / rmi (destructive) | Yes | No | No | No |
| docker build / run | Yes | No | Yes | No |
| Docker Swarm management | Yes | No | No | No |
| **Database (Supabase/PostgreSQL)** | | | | |
| Full database access | Yes | No | Read-write | Read-only |
| Schema migrations | Yes | No | Yes (dev) | No |
| User data access | Yes | No | Anonymized | Read-only |
| Backup/restore | Yes | No | No | No |
| **Application (SENTINEL API)** | | | | |
| /api/health, /docs | Yes | Yes | Yes | Yes |
| /api/chat, /api/equipment (read) | Yes | Yes | Yes | Yes |
| /api/devices/*/control (write) | Yes | Yes | Yes | No |
| /api/optimization/* (actions) | Yes | Yes | No | No |
| /api/simulation/* (demo) | Yes | No | Yes | No |
| /api/mcp/simbiot/call (MCP tools) | Yes | Yes | Yes | No |
| Admin configuration endpoints | Yes | No | No | No |
| **Cloudflare** | | | | |
| Tunnel management | Yes | No | No | No |
| DNS configuration | Yes | No | No | No |
| WAF rule management | Yes | No | No | No |
| Access policy management | Yes | No | No | No |
| **Monitoring** | | | | |
| Grafana dashboards (view) | Yes | Yes | Yes | Yes |
| Grafana alerting (configure) | Yes | No | No | No |
| Log access (Loki/Promtail) | Yes | Yes | Yes | Yes |
| Security alerts (Wazuh) | Yes | Yes (view) | No | Yes (view) |

## Authentication Methods

| Method | Where Used | Details |
|--------|-----------|---------|
| SSH Key + 2FA (TOTP) | Server access | Ed25519 keys + Google Authenticator |
| API Key (`sent_sk_*`) | Service accounts | Rotated annually, documented ownership |
| Bearer Token (Supabase JWT) | Application access | Validated via Supabase auth |
| Cloudflare Access | Remote access | SSO + device posture checks |

## Access Lifecycle Management

### Provisioning Process
1. **Request:** User/manager submits access request with role justification
2. **Approve:** Role-appropriate approver reviews (see Role Definitions above)
3. **Provision:** Admin creates account, assigns to appropriate group
4. **Verify:** New user confirms access works, 2FA configured
5. **Document:** Access grant recorded in audit log with approval reference

### Deprovisioning Process
1. **Termination:** Immediate revocation (within 1 hour of notification)
   - SSH keys removed from `~/.ssh/authorized_keys`
   - User removed from all sentinel-* groups
   - API keys revoked
   - Supabase account disabled
   - Active sessions terminated
2. **Role Change:** Access adjusted within 24 hours
   - Old group memberships removed
   - New group memberships added
   - Verified by supervisor

### Access Review Schedule
- **Monthly:** All active accounts reviewed by respective leads
  - Verify each account still needed
  - Confirm role assignments are correct
  - Check for dormant accounts
- **Quarterly:** Privileged accounts (Admin, Developer) reviewed by security lead
  - Full audit of admin-level access
  - Review sudo logs for anomalies
  - Verify 2FA is active for all privileged users

### Stale Account Policy
- **>90 days inactive:** Account disabled, user notified
- **>180 days inactive:** Account deleted after manager confirmation
- **Exception:** Service accounts exempt but require annual ownership confirmation

## Password Policy
- **Minimum length:** 14 characters
- **Complexity:** At least 1 uppercase, 1 lowercase, 1 digit, 1 special character
- **History:** No reuse of last 12 passwords
- **Expiry:** 90 days for regular accounts, 60 days for privileged accounts
- **Lockout:** Account locked after 5 failed attempts, auto-unlock after 30 minutes
- **Note:** SSH key authentication is primary; passwords used for sudo only

## Service Account Management
- **Naming:** `svc-sentinel-<purpose>` (e.g., `svc-sentinel-backup`)
- **API Key prefix:** `sent_sk_` followed by unique identifier
- **Rotation:** API keys rotated annually (minimum), or immediately if compromised
- **Ownership:** Each service account has a documented human owner
- **Review:** Quarterly review of all service accounts and their permissions

## Emergency Access (Break-Glass)
1. **Trigger:** System emergency requiring immediate admin access
2. **Process:**
   - Break-glass credentials stored in sealed envelope / password manager vault
   - Access logged immediately with incident reference
   - All actions during emergency access are fully audited
   - Post-incident review within 24 hours
   - Break-glass credentials rotated after each use
3. **Scope:** Emergency access grants full admin for the duration of the incident only
4. **Documentation:** Emergency access events documented in incident report

## References
- FSR Domain 4.7: Logical Access Control
- SENTINEL sudo configuration: `infrastructure/pam/sudo-sentinel.conf`
- SENTINEL SSH hardening: `infrastructure/ssh/sshd_hardening.conf`
- SENTINEL auth middleware: `backend/app/middleware/auth_middleware.py`
