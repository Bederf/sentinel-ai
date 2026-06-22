# Threat Model

> **Status**: Draft 2026-06-14
> **Scope**: SENTINEL BMS on-premise deployment
> **Methodology**: STRIDE per data flow

## Architecture Overview

```
Internet ─── Cloudflare Tunnel ─── Kong (:55321) ─── Backend (:9095) ─── Supabase/Postgres (:55322)
                                  │                                              │
                                  ├── Auth (:9999)                              ├── PgBouncer (:6432)
                                  ├── Storage (:5000)                           ├── WAL Replica
                                  └── Studio (:3000)                            └── Standby DB (:55432)
```

External integrations: Telegram, WhatsApp, SMTP, Anthropic, OpenAI, Bridge (site-002).

## Trust Boundaries

| Boundary | Type | Risk |
|----------|------|------|
| Internet → Cloudflare Tunnel | External → Internal | Low (TLS, Cloudflare auth) |
| Tunnel → Kong | Internal → Internal | Low (local network) |
| Kong → Backend | Internal → Internal | Low (JWT validated) |
| Backend → Supabase | Internal → Internal | Low (service role key) |
| Backend → Anthropic/OpenAI | Internal → External | Medium (API keys, data exfiltration) |
| Backend → Telegram/WhatsApp | Internal → External | Medium (bot tokens, message content) |
| Backend → Bridge (site-002) | Internal → External (VPN) | Medium (bridge token) |

## STRIDE Analysis

### Spoofing

| Asset | Threat | Mitigation |
|-------|--------|------------|
| Backend API | Attacker impersonates legitimate user | JWT authentication, Bearer token required |
| Webhook endpoints | Attacker sends fake webhooks | Webhook secrets verified per endpoint |
| Telegram bots | Attacker impersonates bot | Bot tokens kept in secrets.env, rotated |
| Supabase | Attacker impersonates service | Service role key in secrets.env, local-only |

### Tampering

| Asset | Threat | Mitigation |
|-------|--------|------------|
| API payloads | Man-in-the-middle modifies request | TLS everywhere (Caddy/Cloudflare) |
| Audit logs | Attacker modifies audit trail | Audit log is append-only; monitored via Loki alert |
| Configuration | Attacker modifies .env or secrets.env | Files are 0600/0640, root-owned |
| Database | Attacker executes unauthorized SQL | Supabase RLS, parameterized queries, no direct DB exposure |

### Repudiation

| Asset | Threat | Mitigation |
|-------|--------|------------|
| User actions | User denies performing action | Audit logging enabled, logged to Loki (90d retention) |
| AI decisions | Model output disputed | Quality gate metrics recorded in Prometheus |
| System changes | Operator denies config change | Git history for code, systemd journal for runtime |

### Information Disclosure

| Asset | Threat | Mitigation |
|-------|--------|------------|
| API keys | Key exposed in logs or error messages | Backend redacts secrets in log output (tested) |
| Telemetry data | Sensor readings exposed | All API responses require auth; no public endpoints |
| Customer data | PII leaked via AI | POPIA consent flags, audit trail for AI requests |
| Secrets | Secrets in git history | Gitleaks scans pre-commit + full history (zero findings) |

### Denial of Service

| Asset | Threat | Mitigation |
|-------|--------|------------|
| PostgreSQL | Connection exhaustion | PgBouncer caps at 20 server connections |
| Backend API | Request flooding | Rate limiting via Kong, 4 uvicorn workers |
| AI services | API cost exhaustion | Credit budget monitoring + alerting |
| Disk space | Log/data fills disk | Disk monitor at 07:00 daily, alert on threshold |

### Elevation of Privilege

| Asset | Threat | Mitigation |
|-------|--------|------------|
| Admin panel | Unauthorized admin access | MFA for admin operations, PIN hash |
| Bot commands | User runs privileged bot command | RBAC per bot (staff/manager/admin), gate checks |
| Supabase RLS | User accesses another site's data | Row-level security policies per site_id |

## Data Flow: Sensitive Operations

### AI Chat Request

```
User → Backend → Anthropic/OpenAI → Backend → User
```

- API key stored in secrets.env (0600)
- Chat content may contain site data
- No customer PII sent to AI providers (by policy)
- Audit log records each request

### Telegram Bot Command

```
User → Telegram → Webhook → Backend → Telegram → User
```

- Bot token in secrets.env
- Webhook secret validates origin
- RBAC gates command execution
- User identity mapped to site via bot_users table

### Database Backup

```
Postgres → pg_dump → age encrypt → SCP → Replica VPS
```

- Backup encryption key separate from SOPS key
- SSH key for SCP transport
- Retention: 14d daily / 56d weekly / 180d monthly
- Restore drill verified (2026-06-12)

## Security Controls Inventory

| Control | Status | Evidence |
|---------|--------|----------|
| Authentication (JWT) | ✅ | `JWT_SECRET_KEY`, token TTL config |
| Authorization (RBAC) | ✅ | Role-based gates per endpoint |
| Encryption in transit (TLS) | ✅ | Cloudflare/Caddy termination |
| Encryption at rest | ✅ | `ENCRYPTION_KEY` for sensitive fields |
| Secrets management | ✅ | SOPS + secrets.env (0600) + gitleaks |
| Audit logging | ✅ | Loki-aggregated, 90d retention |
| Rate limiting | ✅ | Kong gateway limits |
| Input validation | ✅ | Pydantic schemas on all endpoints |
| SQL injection prevention | ✅ | Parameterized queries + Supabase RLS |
| MFA for admin | ✅ | Admin PIN + MFA enforcement |
| Secret rotation | ⚠️ | Manual, 90d target, rotation log maintained |
| Penetration testing | ❌ | Not yet performed |
| Dependency scanning | ❌ | Not yet automated |
| Bug bounty program | ❌ | Not applicable (internal platform) |

## Incident Response

See `docs/09-security/secrets-management.md` for credential compromise procedure.
See `docs/10-operations/disaster-recovery.md` for service outage procedures.

## Review Cadence

| Item | Frequency | Owner |
|------|-----------|-------|
| Threat model review | Annual | Infrastructure team |
| Secret rotation | 90 days | Infrastructure team |
| Gitleaks full-history scan | Per PR | Developer |
| Dependency audit | Quarterly | Infrastructure team |
