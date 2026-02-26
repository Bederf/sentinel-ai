# Password Security Standard

**Document:** SENTINEL BMS Platform - Password Security Standard
**Document ID:** SENT-STD-PWD-001
**FSR Domain:** 4.7 - Logical Access Control (supporting standard)
**Version:** 1.0
**Effective Date:** 2026-02-04
**Owner:** Information Security Officer
**Review Cadence:** Annual (next review: 2027-02-04)
**Classification:** Internal

---

## 1. Purpose

This standard defines the minimum requirements for passwords, passphrases, API keys, SSH keys, and all other authentication credentials used within the SENTINEL BMS Intelligence Platform. It supports the Logical Access Control Policy (SENT-POL-LAC-001) and ensures that authentication mechanisms meet FSR Domain 4.7 requirements and industry best practices.

## 2. Scope

This standard applies to:

- All user accounts on SENTINEL systems (Linux, Supabase, Docker)
- All service accounts and API keys
- SSH keys for server access
- Database connection credentials
- Third-party API credentials (Anthropic, FSI, WhatsApp, Telegram)
- Any other authentication credential associated with SENTINEL operations

---

## 3. Password Requirements

### 3.1 Minimum Complexity

| Requirement | Standard |
|---|---|
| Minimum length | **14 characters** |
| Maximum length | 128 characters (no artificial upper limit below this) |
| Character classes required | At least 3 of 4: uppercase, lowercase, digits, special characters |
| Dictionary words | Prohibited (common password lists checked) |
| Personal information | Prohibited (no username, email, name, date of birth) |
| Sequential characters | Prohibited (no `abc`, `123`, `qwerty`) |
| Repeated characters | Maximum 3 consecutive identical characters |

### 3.2 Password History and Rotation

| Requirement | Standard |
|---|---|
| Password history | Last 12 passwords cannot be reused |
| Regular account rotation | 90 days maximum |
| Privileged account rotation | 60 days maximum |
| Forced change on first login | Required for all new accounts |
| Compromise-triggered rotation | Immediate change required |

### 3.3 Passphrases

Passphrases (4+ unrelated words) are encouraged as an alternative to complex passwords, provided they meet the 14-character minimum. Examples of acceptable passphrases:

- `correct horse battery staple` (28 characters) -- Acceptable
- `S3nt1nel-Builds-Smart-Cities!` (29 characters) -- Acceptable

Passphrases must not use:
- Common phrases or song lyrics
- Publicly available quotes
- Personal information

---

## 4. Multi-Factor Authentication (MFA)

### 4.1 MFA Requirements

| Access Type | MFA Required | Method |
|---|---|---|
| SSH server access | **Mandatory** | SSH key (factor 1) + TOTP (factor 2) |
| Cloudflare Tunnel access | **Mandatory** | SSO + device posture check |
| Admin API access | **Mandatory** | Bearer token from MFA-enabled Supabase auth |
| Supabase dashboard | **Mandatory** | Supabase native MFA (TOTP) |
| Standard API access (Operator) | Recommended | Bearer token (MFA via Supabase when enabled) |
| Read-only API access (Auditor) | Recommended | Bearer token |
| Docker management | **Mandatory** | Inherits SSH 2FA (requires SSH to server) |

### 4.2 Approved MFA Methods

| Method | Use Case | Implementation |
|---|---|---|
| TOTP (Time-based One-Time Password) | SSH access, Supabase | Google Authenticator, Authy |
| SSH public key | Server authentication | Ed25519 or RSA 4096-bit |
| Device posture | Remote access | Cloudflare Access device trust |

### 4.3 MFA Recovery

- Backup codes generated at MFA setup (10 one-time codes)
- Backup codes stored securely (encrypted password manager or sealed envelope)
- MFA reset requires identity verification by Admin + supervisor approval
- MFA reset logged as a security event

**Implementation:** SSH 2FA configured via `libpam-google-authenticator` (Phase 63-04). Configuration: `google-authenticator -t -d -f -r 3 -R 30 -w 3`.

---

## 5. Password Storage

### 5.1 Hashing Requirements

| Requirement | Standard |
|---|---|
| Hashing algorithm | **bcrypt** (preferred) or **Argon2id** |
| bcrypt work factor | Minimum 12 rounds |
| Argon2id parameters | memory: 64MB, iterations: 3, parallelism: 4 |
| Plaintext storage | **Absolutely prohibited** anywhere in the system |
| Reversible encryption for passwords | **Prohibited** |
| Salt | Unique per password (bcrypt and Argon2id include salt automatically) |

### 5.2 Where Passwords Must Never Appear

- Source code (enforced by pre-commit hooks, Phase 63-03)
- Configuration files committed to version control
- Log files (auth middleware must not log passwords)
- API responses
- Error messages
- Email or chat messages
- Clipboard history (users should use password managers)

**Enforcement:** Pre-commit hooks from Phase 63-03 scan for hardcoded API keys, passwords, and secrets patterns. Commits containing detected secrets are blocked.

---

## 6. API Key Management

### 6.1 API Key Requirements

| Requirement | Standard |
|---|---|
| Minimum length | **32 characters** (256 bits of entropy) |
| Character set | Alphanumeric + URL-safe characters |
| Prefix | `sent_sk_` (identifies SENTINEL service keys) |
| Generation | Cryptographically secure random (`secrets.token_urlsafe(32)`) |
| Storage | SHA-256 hash stored; plaintext shown to user **once** at creation |
| Validation | Timing-safe comparison (`secrets.compare_digest`) |
| Rotation | Every **90 days** for integration keys |
| Immediate rotation | Required on suspected compromise |

### 6.2 API Key Lifecycle

| Phase | Action | Responsible |
|---|---|---|
| Generation | `generate_api_key()` creates (plaintext, hash) pair | SENTINEL Admin |
| Delivery | Plaintext shown once via secure channel (HTTPS only) | SENTINEL Admin |
| Storage | Hash stored in key store with owner, role, scopes, expiry | SENTINEL Admin |
| Usage | Validated via `Authorization: Bearer sent_sk_...` or `X-API-Key: sent_sk_...` | Application middleware |
| Monitoring | Usage tracked per key (request counts, last used) | Application middleware |
| Rotation | New key generated, old key revoked with 24-hour grace period | Key owner + Admin |
| Revocation | Key hash removed from store, all sessions terminated | SENTINEL Admin |

### 6.3 API Key Scoping

Each API key is scoped to specific permissions:

| Scope | Permissions |
|---|---|
| `read` | Read-only access to equipment, sensors, alerts |
| `write` | Read + device control, work order creation |
| `admin` | Full access including user management |

Keys must be granted the minimum scope required for their function.

**Implementation:** `backend/app/models/auth.py` defines API key validation and scope checking.

---

## 7. SSH Key Management

### 7.1 SSH Key Requirements

| Requirement | Standard |
|---|---|
| Algorithm | **Ed25519** (preferred) or RSA |
| RSA minimum key size | **4096 bits** |
| Passphrase | **Required** on all private keys |
| Key storage (private) | User's local machine, never on shared drives or in code |
| Key storage (public) | `~/.ssh/authorized_keys` on server |
| Key format | OpenSSH format |
| Key labelling | Comment field must include `user@device` identifier |

### 7.2 SSH Key Lifecycle

| Phase | Action | SLA |
|---|---|---|
| Generation | User generates key pair on their machine | Before access request |
| Submission | Public key submitted to Admin via verified channel | With access request |
| Installation | Admin adds public key to server `authorized_keys` | Within 1 business day of approval |
| Rotation | Annual minimum, or immediately on device loss/compromise | Annual / Immediate |
| Revocation | Public key removed from `authorized_keys` on termination | Within 1 hour |

### 7.3 SSH Configuration

The following SSH server settings are enforced per `infrastructure/ssh/sshd_hardening.conf` (Phase 63-04):

| Setting | Value | Purpose |
|---|---|---|
| `PermitRootLogin` | `no` | No direct root access |
| `PasswordAuthentication` | `no` | Key-only authentication |
| `MaxAuthTries` | `3` | Limit brute force |
| `LoginGraceTime` | `30` seconds | Fast timeout on idle auth |
| `AllowGroups` | `sentinel-admin sentinel-operator sentinel-developer sentinel-auditor` | Group-based access |
| `Ciphers` | `chacha20-poly1305@openssh.com,aes256-gcm@openssh.com` | Strong ciphers only |
| `KexAlgorithms` | `curve25519-sha256` | Strong key exchange |
| `MACs` | `hmac-sha2-512-etm@openssh.com,hmac-sha2-256-etm@openssh.com` | Strong MACs |
| `AllowTcpForwarding` | `no` | No tunnelling |
| `X11Forwarding` | `no` | No X11 forwarding |

---

## 8. Service Account Credentials

### 8.1 Storage Requirements

| Requirement | Standard |
|---|---|
| Storage method | **Environment variables** or **secrets manager** |
| Source code | **Never** stored in source code |
| Configuration files | **Never** committed to version control |
| Docker Compose | Referenced via `.env` file (not committed) or Docker secrets |
| File permissions | `.env` files: `chmod 600` (owner read/write only) |

### 8.2 Current Service Account Credentials

| Credential | Storage | Rotation |
|---|---|---|
| `ANTHROPIC_API_KEY` | `.env` file (600 perms) | Annually |
| `SUPABASE_URL` | `.env` file | Static (URL does not change) |
| `SUPABASE_KEY` | `.env` file (600 perms) | Annually |
| `SUPABASE_SERVICE_ROLE_KEY` | `.env` file (600 perms) | Annually |
| `DATABASE_URL` | `.env` file (600 perms) | Annually |
| WhatsApp Bot Token | `.env` file (600 perms) | Annually |
| Telegram Bot Token | `.env` file (600 perms) | Annually |
| FSI API credentials | `.env` file (600 perms) | Annually |

### 8.3 Pre-Commit Enforcement

Phase 63-03 pre-commit hooks enforce credential hygiene:

| Hook | Function |
|---|---|
| `detect-secrets` | Scans for high-entropy strings, AWS keys, private keys |
| Hardcoded API key blocker | Blocks patterns matching `sk-`, `sent_sk_`, API key patterns |
| `.env` commit prevention | Blocks `.env` files from being committed |

---

## 9. Session Management

### 9.1 Session Timeout

| Session Type | Inactivity Timeout | Maximum Duration |
|---|---|---|
| SSH session | **5 minutes** (`ClientAliveInterval 300`) | 8 hours |
| API bearer token | **30 minutes** of inactivity | 8 hours (token expiry) |
| Supabase dashboard | **30 minutes** | Supabase default |
| Cloudflare Access | As configured per policy | 24 hours (re-authentication required) |

### 9.2 Session Controls

| Control | Implementation |
|---|---|
| Concurrent session limit | Maximum 3 active SSH sessions per user |
| Session logging | All SSH sessions logged (`/var/log/auth.log`, `/var/log/sudo.log`) |
| Session termination on role change | Active sessions terminated when permissions change |
| Forced logout on deprovisioning | All active sessions killed within 1 hour |

---

## 10. Account Lockout

### 10.1 Lockout Thresholds

| Condition | Action |
|---|---|
| **5 failed attempts** | Account locked for **15 minutes** (auto-unlock) |
| **10 failed attempts** | Account **disabled** pending manual review |
| 3 failed SSH attempts | Connection terminated (`MaxAuthTries 3`) |
| Suspicious login pattern | Alert generated for Security Officer review |

### 10.2 Account Unlock Procedure

| Lockout Type | Unlock Method | Responsible |
|---|---|---|
| 15-minute auto-lock | Automatic unlock after 15 minutes | System |
| Account disabled | Identity verification + Admin unlock | SENTINEL Admin |
| Suspicious activity | Security review + Admin approval | Information Security Officer |

---

## 11. Password Reset

### 11.1 Self-Service Reset

1. User requests password reset via Supabase authentication
2. Reset link sent to verified email address
3. Reset link expires in **1 hour**
4. New password must meet all complexity requirements (Section 3.1)
5. Password change logged as security event

### 11.2 Admin-Assisted Reset

Required when self-service is unavailable:

1. User contacts SENTINEL Admin via verified channel (not email alone)
2. Identity verification: at least 2 of the following:
   - Verbal confirmation of identity by supervisor
   - Verification question (pre-registered)
   - Video call verification
3. Admin generates temporary password
4. User must change password on first login
5. Reset logged as security event with verification method recorded

---

## 12. Prohibited Practices

The following practices are explicitly prohibited for all SENTINEL personnel:

| Practice | Reason |
|---|---|
| Password sharing | Accountability requires individual credentials |
| Password reuse across systems | Compromise of one system compromises all |
| Storing passwords in browsers | Browser password stores lack enterprise security controls |
| Writing passwords on paper or sticky notes | Physical exposure risk |
| Sending passwords via email or chat | Unencrypted transmission, persistent storage |
| Using personal passwords for work accounts | Blurs personal and professional security boundaries |
| Using default or vendor-supplied passwords | Well-known credentials are immediately exploitable |
| Storing passwords in source code | Detected and blocked by pre-commit hooks (Phase 63-03) |
| Using the same API key for multiple integrations | Limits blast radius, enables scoped revocation |
| Disabling MFA for convenience | MFA is mandatory for all privileged access |

---

## 13. Password Manager

### 13.1 Approved Password Managers

SENTINEL recommends the use of approved password managers for credential storage:

| Manager | Approved For | Notes |
|---|---|---|
| 1Password / Bitwarden | Personal and team credentials | End-to-end encrypted, MFA support |
| **SOPS + age** | **Service & application secrets** | **Deployed — encrypts .env to .env.enc (AES-256-GCM). Key at `/etc/sentinel/sops-key.txt`. 90-day rotation via `infra/scripts/sops-rotate-key.sh`** |
| HashiCorp Vault | Service account secrets (large-scale) | Infrastructure-grade secrets management (not deployed — SOPS+age covers current needs) |

### 13.2 Password Manager Requirements

- Master password must meet or exceed the 14-character minimum
- MFA must be enabled on the password manager account
- Password manager must use zero-knowledge architecture (provider cannot access stored passwords)
- Browser autofill is acceptable only from approved password managers (not browser built-in)
- Password manager access must be revoked during offboarding

---

## 14. Compliance Evidence

The following Phase 63-04 technical controls serve as evidence that this standard is implemented:

| Standard Requirement | Technical Control | Implementation |
|---|---|---|
| SSH key-only auth | `PasswordAuthentication no` | `infrastructure/ssh/sshd_hardening.conf` |
| MFA enforcement | SSH key + TOTP | `libpam-google-authenticator` |
| Strong ciphers | ChaCha20-Poly1305, AES-256-GCM | `infrastructure/ssh/sshd_hardening.conf` |
| Credential detection | Pre-commit hooks | `.pre-commit-config.yaml` (Phase 63-03) |
| API key security | Hashed storage, timing-safe comparison | `backend/app/models/auth.py` |
| Session management | ClientAliveInterval, MaxAuthTries | `infrastructure/ssh/sshd_hardening.conf` |
| PAM group restrictions | Scoped sudo per role | `infrastructure/pam/sudo-sentinel.conf` |
| PII guard | SA ID/phone/email redaction | `backend/app/middleware/pii_guard.py` |

---

## 15. Enforcement

Violations of this standard are handled per the Logical Access Control Policy (SENT-POL-LAC-001) enforcement section. Key consequences:

| Violation | Example | Consequence |
|---|---|---|
| Minor | Password below 14 characters (system-enforced, unlikely) | Password change required |
| Moderate | Password sharing, MFA not configured | Formal warning, mandatory training |
| Severe | Storing credentials in code, disabling MFA | Access revocation, disciplinary action |
| Critical | Credential theft or intentional exposure | Immediate access revocation, investigation, legal action |

---

## 16. Related Documents

| Document | Reference |
|---|---|
| Logical Access Control Policy | SENT-POL-LAC-001 |
| Information Classification Policy | SENT-POL-IC-001 |
| Access Control Implementation (Technical) | `docs/08-security/access-control-implementation.md` |

---

## 17. Version Control

| Version | Date | Author | Changes |
|---|---|---|---|
| 1.0 | 2026-02-04 | Information Security Officer | Initial standard creation |

---

*SENTINEL BMS Intelligence Platform - Password Security Standard*
*FSR Domain 4.7 - Logical Access Control (Supporting Standard)*
*Classification: Internal*
