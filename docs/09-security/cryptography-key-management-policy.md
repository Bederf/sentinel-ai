# Cryptography and Key Management Policy

**Document ID:** SENTINEL-CKM-001
**Version:** 1.1
**Effective Date:** 2026-02-04
**Review Cadence:** Annual, or on cryptographic standard update
**Owner:** SENTINEL Platform Team
**Classification:** Internal

---

## 1. Purpose

This policy defines SENTINEL's cryptographic controls and key management practices for protecting information confidentiality, integrity, and authenticity. It documents the cryptographic standards in use, key lifecycle management, and compliance requirements for POPIA and FSR.

---

## 2. Scope

This policy covers all cryptographic operations across:

- SENTINEL infrastructure (VPS, Docker containers, SSH)
- Application layer (FastAPI backend, React frontend, ML pipeline)
- Data storage (Supabase/PostgreSQL, InfluxDB)
- Data in transit (API communications, web traffic, third-party integrations)
- Authentication and authorisation (JWT, passwords, API keys)
- Data integrity (consent records, audit logs)
- Third-party service integrations (Claude API, Cloudflare, GitHub, messaging platforms)

---

## 3. Cryptographic Standards

### 3.1 Approved Algorithms

| Purpose | Algorithm | Key Size / Parameters | Standard |
|---------|-----------|----------------------|----------|
| **Encryption at rest** | AES-256 | 256-bit key | NIST FIPS 197 |
| **Encryption in transit (minimum)** | TLS 1.2 | Per cipher suite | IETF RFC 5246 |
| **Encryption in transit (preferred)** | TLS 1.3 | Per cipher suite | IETF RFC 8446 |
| **Password hashing** | bcrypt | Cost factor 12+ | OpenBSD bcrypt |
| **Data integrity hashing** | SHA-256 | 256-bit output | NIST FIPS 180-4 |
| **SSH keys (preferred)** | Ed25519 | 256-bit key | IETF RFC 8709 |
| **SSH keys (acceptable)** | RSA | 4096-bit minimum | NIST SP 800-57 |
| **JWT signing** | RS256 or HS256 | 256-bit minimum key | IETF RFC 7518 |
| **Random number generation** | CSPRNG | Per implementation | OS-provided (os.urandom) |

### 3.2 Prohibited Algorithms

The following algorithms must NOT be used in SENTINEL systems:

| Algorithm | Reason | Replacement |
|-----------|--------|-------------|
| **MD5** | Collision vulnerabilities, broken for integrity | SHA-256 |
| **SHA-1** | Collision attacks demonstrated, deprecated | SHA-256 |
| **DES** | 56-bit key length, trivially broken | AES-256 |
| **3DES** | Performance issues, approaching end of life | AES-256 |
| **RC4** | Multiple biases and vulnerabilities | AES-256 |
| **RSA < 2048-bit** | Insufficient key length for current threat landscape | RSA 4096-bit or Ed25519 |
| **TLS 1.0/1.1** | Deprecated, known vulnerabilities (BEAST, POODLE) | TLS 1.2+ |
| **SSL 2.0/3.0** | Severely broken, multiple CVEs | TLS 1.2+ |

### 3.3 Deployed Cryptographic Controls

The following cryptographic controls are currently deployed in SENTINEL:

| Control | Implementation | Deployed In |
|---------|---------------|-------------|
| TLS 1.2+ for all API and web traffic | Cloudflare-managed certificates (automatic renewal) | Infrastructure |
| AES-256 encryption at rest (database) | Supabase/PostgreSQL native encryption | Supabase |
| AES-256 encryption at rest (time-series) | InfluxDB storage encryption | InfluxDB |
| SSH Ed25519/RSA keys | Key-only authentication, no password login (Phase 63-04) | VPS |
| JWT tokens for API authentication | httpOnly, secure flag, signed tokens | Backend API |
| bcrypt password hashing | Cost factor 12+, per-user salt | Backend API |
| SHA-256 consent record hashing | Application-level hashing with salt (Phase 63-06) | Consent service |
| Fernet encryption at rest (audit logs) | AES-128-CBC + HMAC-SHA256 via Python `cryptography` library (Phase 81-01) | Backend audit service |
| Pre-commit secret detection | detect-secrets and gitleaks hooks (Phase 63-03) | CI/CD pipeline |
| Environment variables for runtime secrets | No hardcoded secrets in source code | All environments |

---

## 4. Key Categories and Management

### 4.1 TLS Certificates

| Attribute | Detail |
|-----------|--------|
| **Provider** | Cloudflare (managed certificates) |
| **Renewal** | Automatic (90-day cycle) |
| **Monitoring** | Phase 63-05 external scanning includes certificate expiry check |
| **Storage** | Managed by Cloudflare -- no local certificate management |
| **Revocation** | Via Cloudflare dashboard if compromise suspected |

### 4.2 SSH Keys

| Attribute | Detail |
|-----------|--------|
| **Algorithm** | Ed25519 (primary), RSA 4096-bit (minimum acceptable) |
| **Passphrase** | Required on all SSH keys |
| **Storage** | Authorised devices only, never on shared systems |
| **Distribution** | Public key added to `~/.ssh/authorized_keys` via secure channel |
| **Configuration** | Hardened sshd configuration (Phase 63-04): `infrastructure/ssh/sshd_hardening.conf` |
| **Restrictions** | Root login disabled, password authentication disabled, key-only access |

### 4.3 API Keys

| Attribute | Detail |
|-----------|--------|
| **Generation** | Minimum 32-character cryptographically random tokens |
| **Storage** | Environment variables only (`.env` files, not in source code) |
| **Protection** | Pre-commit hooks (detect-secrets, gitleaks) block hardcoded keys (Phase 63-03) |
| **Services** | Anthropic Claude API key, Supabase key, Supabase service role key |
| **Scope** | Each key scoped to minimum required permissions |

### 4.4 Database Encryption Keys

| Attribute | Detail |
|-----------|--------|
| **Supabase/PostgreSQL** | Provider-managed encryption keys (AES-256 at rest) |
| **InfluxDB** | Self-managed storage encryption (AES-256) |
| **Rotation** | Per provider schedule (Supabase) or annually (InfluxDB) |
| **Access** | No direct access to encryption keys -- managed by respective platforms |

### 4.5 JWT Signing Keys

| Attribute | Detail |
|-----------|--------|
| **Algorithm** | RS256 or HS256 |
| **Key size** | Minimum 256-bit |
| **Generation** | Application-generated using Python `secrets` module |
| **Storage** | Environment variables, never in source code |
| **Flags** | JWT tokens issued with httpOnly and secure flags |

### 4.6 Consent Hashing Keys

| Attribute | Detail |
|-----------|--------|
| **Algorithm** | SHA-256 |
| **Purpose** | Hash consent records for PI protection (Phase 63-06) |
| **Salt** | Application-level salt for PI hashing |
| **Storage** | Salt stored in environment variables |

---

## 5. Key Lifecycle Management

### 5.1 Key Generation

| Requirement | Detail |
|-------------|--------|
| **Random source** | Cryptographically secure random number generators only |
| **Python** | `os.urandom()`, `secrets` module, or `cryptography` library |
| **Prohibition** | Never use `random` module for key generation (not cryptographically secure) |
| **Key size** | Must meet or exceed minimum sizes in Section 3.1 |

### 5.2 Key Distribution

| Requirement | Detail |
|-------------|--------|
| **Channel** | Secure channel only (SSH, encrypted transfer) |
| **Prohibition** | Never distribute keys via email, chat, or unencrypted channels |
| **Split knowledge** | For highly sensitive keys, use split-knowledge or multi-party generation |
| **Verification** | Recipient confirms receipt via separate channel |

### 5.3 Key Storage

| Requirement | Detail |
|-------------|--------|
| **Environment variables** | Primary method for all runtime secrets |
| **Source code** | Keys must NEVER appear in source code |
| **Enforcement** | Pre-commit hooks (detect-secrets, gitleaks from Phase 63-03) automatically block commits containing secrets |
| **Backup** | Key backups encrypted and stored separately from systems using them |
| **Access control** | Key access restricted to roles that require them |

### 5.4 Key Rotation Schedule

| Key Type | Rotation Period | Trigger |
|----------|----------------|---------|
| **API keys** (Claude, Supabase) | Every 90 days | Scheduled, or on personnel change |
| **SSH keys** | Annually | Scheduled, or on personnel departure |
| **TLS certificates** | Automatic via Cloudflare (90-day cycle) | Automatic |
| **JWT signing keys** | Every 6 months | Scheduled, or on suspected compromise |
| **Database encryption keys** | Per provider schedule, or annually | Provider-managed or scheduled |
| **Consent hashing salt** | Annually | Scheduled, or on compromise |

### 5.5 Key Revocation

Keys must be immediately revoked when:

- Key compromise is suspected or confirmed
- Personnel with key access depart (reference Leavers Process in HR Security Policy)
- Key reaches end of rotation period
- Associated system or service is decommissioned

**Revocation process:**

1. Immediately disable the compromised key in all systems
2. Generate new key using approved method (Section 5.1)
3. Distribute replacement via secure channel (Section 5.2)
4. Verify old key no longer provides access
5. Document revocation in key inventory

### 5.6 Key Destruction

When keys are no longer needed:

- Securely overwrite key material (not just delete)
- Confirm removal from all backup locations
- Remove from environment files, configuration, and secrets managers
- Document destruction in key inventory
- Verify no systems still reference the destroyed key

---

## 6. Key Compromise Response

When a key compromise is suspected or confirmed:

| Step | Action | Timing |
|------|--------|--------|
| 1 | **Immediately revoke** the compromised key across all systems | Within 1 hour |
| 2 | **Generate new key** using approved method | Within 4 hours |
| 3 | **Distribute replacement** via secure channel | Within 4 hours |
| 4 | **Audit access logs** for the period of potential compromise | Within 24 hours |
| 5 | **Report as security incident** (reference incident response policy) | Within 24 hours |
| 6 | **Update key inventory** with compromise details and new key reference | Within 24 hours |
| 7 | **Assess impact** -- determine what data or systems were potentially exposed | Within 48 hours |
| 8 | **Notify affected parties** -- including FSR if their data was potentially affected | Within 72 hours |

---

## 7. Controls Verification

### 7.1 Automated Verification

| Check | Frequency | Tool / Process |
|-------|-----------|----------------|
| TLS certificate validity | Monthly | Phase 63-05 external scan (`infrastructure/scanning/external-scan.sh`) |
| Secret detection in code | Every commit | Pre-commit hooks: detect-secrets, gitleaks (Phase 63-03) |
| Secret detection in CI/CD | Every push/PR | GitHub Actions: gitleaks job (Phase 63-03) |
| Dependency vulnerabilities | Every push/PR | GitHub Actions: pip-audit, safety, Trivy (Phase 63-03) |
| Dependabot alerts | Continuous | Dependabot across 4 ecosystems (Phase 63-03) |

### 7.2 Manual Verification

| Check | Frequency | Performed By |
|-------|-----------|-------------|
| API key rotation compliance | Quarterly | System Administrator |
| SSH key inventory review | Quarterly | System Administrator |
| Full cryptographic controls review | Annual | Platform Team |
| Key access review (who has what) | Semi-annual | System Administrator |

---

## 8. Cross-Border Encryption

### 8.1 Data Transfers to Claude API (United States)

| Requirement | Implementation |
|-------------|---------------|
| **Encryption in transit** | TLS 1.2+ for all API communication |
| **Data minimisation** | Only building/equipment data sent; occupant PI stripped by PII guard (Phase 63-04) |
| **Anonymisation** | Occupant identifiers pseudonymised before transfer where possible |
| **Consent** | Consent capture service records user consent for data processing (Phase 63-06) |

### 8.2 Data Transfers to Supabase (AWS Regions)

| Requirement | Implementation |
|-------------|---------------|
| **Encryption in transit** | TLS 1.2+ for all database connections |
| **Encryption at rest** | AES-256 (Supabase-managed) |
| **Access control** | Row-level security, API key authentication |

### 8.3 Consent Record Protection

| Requirement | Implementation |
|-------------|---------------|
| **Hashing** | SHA-256 hash of consent records before any external storage |
| **Salt** | Application-level salt to prevent rainbow table attacks |
| **Integrity** | Hash verification ensures consent records have not been tampered with |

---

## 9. Regulatory Compliance

### 9.1 POPIA Compliance

This policy addresses POPIA Section 19 (Security safeguards) requirements:

- **Appropriate technical measures**: AES-256 encryption at rest, TLS 1.2+ in transit
- **PI protection**: bcrypt hashing for passwords, SHA-256 for consent records
- **Cross-border transfers**: TLS-encrypted, data-minimised transfers with POPIA Section 72 compliance
- **Access control**: Cryptographic authentication (SSH keys, JWT tokens)

### 9.2 FSR Compliance

This policy addresses FSR questionnaire domain 4.12 (Cryptography and Key Management):

- **Cryptographic standards documented**: Section 3 of this policy
- **Key management lifecycle defined**: Section 5 of this policy
- **Rotation schedules established**: Section 5.4 of this policy
- **Prohibited algorithms identified**: Section 3.2 of this policy
- **Controls verification**: Section 7 of this policy

---

## 10. Key Inventory

The following key types are currently in use across SENTINEL:

| Key ID | Type | Algorithm | Location | Rotation Due | Owner |
|--------|------|-----------|----------|-------------|-------|
| CKM-TLS-001 | TLS Certificate | Cloudflare-managed | Cloudflare | Automatic (90 days) | System Administrator |
| CKM-SSH-001 | SSH Server Key | Ed25519 | VPS | 2027-02-04 | System Administrator |
| CKM-API-001 | Anthropic API Key | Random token | .env | 2026-05-04 | System Administrator |
| CKM-API-002 | Supabase API Key | Random token | .env | 2026-05-04 | System Administrator |
| CKM-API-003 | Supabase Service Role Key | Random token | .env | 2026-05-04 | System Administrator |
| CKM-JWT-001 | JWT Signing Key | HS256/RS256 | .env | 2026-08-04 | System Administrator |
| CKM-DB-001 | PostgreSQL Encryption Key | AES-256 | Supabase-managed | Provider schedule | Supabase |
| CKM-DB-002 | InfluxDB Encryption Key | AES-256 | Docker volume | 2027-02-04 | System Administrator |
| CKM-CST-001 | Consent Hashing Salt | SHA-256 salt | .env | 2027-02-04 | System Administrator |
| CKM-AUD-001 | Audit Log Encryption Key | Fernet (AES-128-CBC) | .env (ENCRYPTION_KEY) | 2027-02-19 | System Administrator |

---

## 11. Version History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-02-04 | SENTINEL Platform Team | Initial cryptography and key management policy |
| 1.1 | 2026-02-19 | SENTINEL Platform Team | Added Fernet encryption at rest for audit logs (Phase 81-01) |

---

*Document: SENTINEL-CKM-001*
*Classification: Internal*
*Next Review: 2027-02-04*
