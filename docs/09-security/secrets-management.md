# Secrets Management

> **Last audit**: 2026-06-12 (gitleaks v8.18.4)
> **Status**: SOPS-encrypted with age, EnvironmentFile-based runtime, gitleaks-integrated
> **Owner**: Infrastructure team
> **Rotation cadence**: See [Rotation Schedule](#rotation-schedule) below

## Architecture

### Authoritative Source Chain

```
┌─────────────────────────────────────────┐
│  SOPS-encrypted source of truth         │
│  backend/.env.enc                       │
│  (age-encrypted, decoupled from runtime)│
└────────────────┬────────────────────────┘
                 │ sops -d (requires age key)
                 ▼
┌─────────────────────────────────────────┐
│  /etc/sentinel/secrets.env  (0600)      │
│  AUTHORITATIVE for production secrets   │
│  → AI keys, bot tokens, SMTP passwords  │
│  → systemd EnvironmentFile              │
└────────────────┬────────────────────────┘
                 │ systemd reads at startup
                 ▼
┌─────────────────────────────────────────┐
│  /etc/sentinel/backend.env  (0640)      │
│  Non-secret config only                 │
│  → URLs, feature flags, site IDs         │
│  → systemd EnvironmentFile              │
└────────────────┬────────────────────────┘
                 │ systemd reads at startup
                 ▼
┌─────────────────────────────────────────┐
│  Application (uvicorn workers)          │
│  os.environ populated by systemd        │
└─────────────────────────────────────────┘
```

### Development Overlay

```
┌─────────────────────────────────────────┐
│  backend/.env  (0600, bederf)           │
│  ⚠️ Currently contains BOTH config      │
│     AND production secrets              │
│  Target state: development defaults     │
│  only. No production secrets.           │
└─────────────────────────────────────────┘
```

### Policy

> **Production secrets SHALL NOT be maintained in `backend/.env`.**
> The authoritative production source is `/etc/sentinel/secrets.env`.
> `backend/.env` is for local development defaults only.

## Secret Inventory

### Class 1: AI Provider Keys

| Secret | Provider | Authoritative Source | Also In | Rotation |
|--------|----------|---------------------|---------|----------|
| `ANTHROPIC_API_KEY` | Anthropic | `secrets.env` | `backend/.env`, `rlm-runner.env`, `sentry-gateway.env` | 90 days |
| `OPENAI_API_KEY` | OpenAI | `secrets.env` | `backend/.env`, `sentry-gateway.env` | 90 days |
| `DEEPSEEK_API_KEY` | DeepSeek | `secrets.env` | `backend/.env` | 90 days |
| `MINIMAX_API_KEY` | MiniMax | `secrets.env` | `backend/.env` | 90 days |
| `ZAI_API_KEY` | Z.AI | `secrets.env` | `backend/.env` | 90 days |
| `ELEVENLABS_API_KEY` | ElevenLabs | `secrets.env` | — | Done 2026-06-12 |
| `OLLAMA_API_KEY` | Ollama (local) | `sentry-gateway.env` | — | N/A (local) |
| `FIRECRAWL_API_KEY` | Firecrawl | `secrets.env` | `backend/.env` | 90 days |

### Class 2: Supabase & Database

| Secret | Value | Locations | Encrypted? |
|--------|-------|-----------|------------|
| `SUPABASE_SERVICE_ROLE_KEY` | `eyJ...` (JWT) | `backend/.env`, `/etc/sentinel/secrets.env` | ❌ Plaintext in `.env`, ✅ 0600 in secrets |
| `SUPABASE_KEY` (anon) | `eyJ...` (JWT) | `backend/.env`, `/etc/sentinel/secrets.env` | ❌ Plaintext in `.env` |
| `DATABASE_URL` | `postgresql://postgres:postgres@...` | `backend/.env` | ❌ Plaintext (local only) |
| `JWT_SECRET_KEY` | Hex key | `backend/.env` | ❌ Plaintext |
| `ENCRYPTION_KEY` | Base64 key | `backend/.env` | ❌ Plaintext |

### Class 3: Telegram Bots

| Bot | Token | Location | Last Rotated |
|-----|-------|----------|-------------|
| Sentry Bot (manager) | `8347514089:AAF1T-...` | `backend/.env`, `/etc/sentinel/secrets.env` | 2026-06-12 |
| Sentry Client Bot | `8702621666:AAEt...` | `backend/.env`, `/etc/sentinel/secrets.env` | 2026-06-12 |
| Sentry Tech Bot | `8699640183:AAF4...` | `backend/.env`, `/etc/sentinel/secrets.env` | 2026-06-12 |
| Home Bot | `8949946171:AAGQ...` | `backend/.env`, `/etc/sentinel/secrets.env` | 2026-06-12 |
| Manager Bot | `8347514089:AAF1T-...` | `/etc/sentinel/secrets.env` only | 2026-06-12 |

**Note**: `backend/.env` still contains older versions of some tokens. The `secrets.env` file has the rotated values. Both must be kept in sync.

### Class 4: Communication & Email

| Secret | Location | Encrypted? |
|--------|----------|------------|
| `TWILIO_ACCOUNT_SID` | `backend/.env` | ❌ Plaintext |
| `TWILIO_AUTH_TOKEN` | `backend/.env` | ❌ Plaintext |
| `WHATSAPP_API_TOKEN` | `backend/.env` | ❌ Plaintext |
| `SMTP_PASSWORD` (workorder@) | `backend/.env`, `/etc/sentinel/secrets.env` | ❌ Plaintext in `.env`, ✅ 0600 in secrets |
| `SMTP_PASSWORD` (info@) | `backend/.env` | ❌ Plaintext |
| `SMTP_PASSWORD` (rooms@) | `backend/.env` | ❌ Plaintext |
| `NOTIFICATION_SMTP_PASSWORD` | `backend/.env` | ❌ Plaintext |
| `ROOMS_IMAP_PASSWORD` | `backend/.env` | ❌ Plaintext |
| `ROOMS_SMTP_PASSWORD` | `backend/.env` | ❌ Plaintext |

### Class 5: Infrastructure & Integrations

| Secret | Location | Encrypted? |
|--------|----------|------------|
| `BRIDGE_API_TOKEN` | Legacy fallback in `/etc/sentinel/secrets.env` | ✅ 0600 in secrets |
| `BRIDGE_API_TOKEN_SITE_###` | Site-scoped bridge token in `/etc/sentinel/secrets.env` | ✅ 0600 in secrets |
| `METRICS_BEARER_TOKEN` | `backend/.env`, `/etc/sentinel/backend.env` | ❌ Plaintext |
| `INTERNAL_SERVICE_KEY` | `backend/.env` | ❌ Plaintext |
| `ESKOMSEPUSH_API_TOKEN` | `backend/.env` | ❌ Plaintext |
| `MCP_API_KEY` | `backend/.env` | ❌ Plaintext |
| `SOLARMAN_APP_SECRET` | `backend/.env` | ❌ Plaintext |
| `OPENWEATHER_API_KEY` | `backend/.env` | ❌ Plaintext |
| `INFLUXDB_TOKEN` | `backend/.env` | ❌ Plaintext (dev token) |
| `SENTRY_BOT_API_KEY` | `backend/.env`, `/etc/sentinel/sentry-gateway.env`, `/etc/sentinel/secrets.env` | ❌ Plaintext in `.env`, ✅ 0600 in secrets |
| `SENTRY_WEBHOOK_SECRET` | `backend/.env`, `/etc/sentinel/sentry-gateway.env` | ❌ Plaintext |
| `GOOGLE_CLIENT_ID` | `/etc/sentinel/sentry-gateway.env` | ✅ 0600 file |
| `GOOGLE_CLIENT_SECRET` | `/etc/sentinel/sentry-gateway.env` | ✅ 0600 file |
| `CONSENT_HASH_SALT` | `backend/.env` | ❌ Plaintext |
| `ADMIN_PIN_HASH` | `/etc/sentinel/secrets.env` | ✅ 0600 file (bcrypt hash) |
| `TUNER_DB_PASSWORD` | `/etc/sentinel/secrets.env` | ✅ 0600 file (DB role password for `sentinel_tuner`) |
| `SENTINEL_OPERATOR_PASSWORD` | `backend/.env` | ❌ Plaintext |
| `N8N_API_KEY` | `backend/.env` | ❌ Plaintext |

### Class 6: Backup & Infrastructure Keys

| Secret | Location | Format | Purpose |
|--------|----------|--------|---------|
| SOPS age private key | `/etc/sentinel/sops-key.txt` (0600, root:root) | `AGE-SECRET-KEY-...` | Decrypt `.env.enc` files |
| Backup age private key | `/etc/sentinel/backup-age.key` (0600) | `AGE-SECRET-KEY-...` | Decrypt offsite backups |
| Legacy backup SSH key | `/etc/sentinel/backup-ssh-key` (0600), if present | Ed25519 private key | Legacy/offline recovery only; not the normal bridge access path |
| Cloudflare tunnel cert | `~/.cloudflared/*.json` (644) | JWT | Tunnel auth |
| SSH keys | `~/.ssh/id_ed25519*` (600) | Ed25519 | Server access |

## Storage Locations

| Location | Contents | Permissions | Risk Level |
|----------|----------|-------------|------------|
| `backend/.env` | **30+ plaintext secrets** — AI keys, DB creds, bot tokens, SMTP passwords | `644` | 🔴 HIGH — world-readable |
| `/etc/sentinel/secrets.env` | 12 high-value secrets (rotated 2026-06-12) | `0600 root:bederf` | 🟢 LOW |
| `/etc/sentinel/backend.env` | 20+ config items (non-secret) | `0640 root:bederf` | 🟢 LOW |
| `/etc/sentinel/sentry-gateway.env` | OpenAI key, Google OAuth, webhook secrets | `0640 root:bederf` | 🟡 MEDIUM |
| `/etc/sentinel/rlm-runner.env` | Anthropic key | `0640 root:sentinel-runner` | 🟡 MEDIUM |
| `/etc/sentinel/sops-key.txt` | **Master SOPS decryption key** | `0600 root:root` | 🟢 LOW (root-only) |
| `~/.cloudflared/*.json` | Cloudflare tunnel credentials | `644` | 🟡 MEDIUM |
| `backend/.env.enc` | SOPS-encrypted copy of `.env` | `644` | 🟢 LOW (encrypted) |

## Access Model

| Role | Can read `secrets.env` | Can decrypt SOPS | Can read `backend/.env` | Can SSH |
|------|----------------------|------------------|------------------------|---------|
| `bederf` (primary admin) | ✅ | ✅ (has age key path) | ✅ | ✅ |
| `root` | ✅ | ✅ (owns sops-key.txt) | ✅ | ✅ |
| `sentinel-runner` | ❌ | ❌ | ❌ | ❌ |
| Other system users | ❌ | ❌ | ✅ (644) | ❌ |

**🔴 Issue**: Any process or user on the system can read `backend/.env` (mode 644).

## Rotation

### Rotation Log

Rotations are tracked at `docs/09-security/secret-rotation-log.md`. Last rotation batch: **2026-06-12** (Phase 226).

### Recently Rotated (2026-06-12)

| Secret | Old Value | New Value | Method |
|--------|-----------|-----------|--------|
| `ADMIN_PIN_HASH` | Legacy | `$2b$12$...` | `bcrypt.hashpw()` |
| `BRIDGE_API_TOKEN` | Legacy | `3016b935...` | `secrets.token_hex(32)` |
| `HOME_BOT_WEBHOOK_SECRET` | Legacy | `8cff7b3d...` | `secrets.token_hex(32)` |
| `ELEVENLABS_API_KEY` | `sk_4a721363...` | `sk_4fdd6902...` | ElevenLabs dashboard |
| All Telegram bot tokens (5) | Legacy | Rotated | BotFather |

### Rotation Procedure

```bash
# 1. Generate new secret
python3 -c "import secrets; print(secrets.token_hex(32))"

# 2. Update in /etc/sentinel/secrets.env
sudo sed -i 's/^SECRET_NAME=.*$/SECRET_NAME=<new-value>/' /etc/sentinel/secrets.env

# 3. Sync to backend/.env if present there
sed -i 's/^SECRET_NAME=.*$/SECRET_NAME=<new-value>/' /opt/bms-intelligence/backend/.env

# 4. Restart service
sudo systemctl daemon-reload && sudo systemctl restart sentinel-backend

# 5. Verify
curl -fsS http://localhost:9095/api/health | jq .

# 6. Log rotation
echo "| SECRET_NAME | YYYY-MM-DD | Rotated via <method> |" >> docs/09-security/secret-rotation-log.md
```

### Pending Rotations

| Secret | Provider | Action Required |
|--------|----------|-----------------|
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase dashboard | Rotate → copy to `secrets.env` + `backend/.env` → restart |
| `SUPABASE_KEY` (anon) | Supabase dashboard | Same as above |
| `SMTP_PASSWORD` | Email provider | Replace in `secrets.env` + `backend/.env` → restart |

## Rotation Schedule

| Secret Class | Rotation Interval | Trigger | Owner |
|-------------|-------------------|---------|-------|
| AI Provider Keys (Anthropic, OpenAI, etc.) | 90 days | Calendar + incident | Infrastructure team |
| Telegram Bot Tokens | 90 days | Calendar + compromise | Infrastructure team |
| SMTP / IMAP Passwords | 180 days | Calendar | Infrastructure team |
| Database Credentials (PostgreSQL) | 180 days | Calendar | Infrastructure team |
| JWT Signing Key | Annual + incident-driven | Calendar + rotation event | Infrastructure team |
| Encryption Keys (SOPS, ENCRYPTION_KEY) | Review annually | Calendar | Infrastructure team |
| Bridge / Internal Service Tokens | 180 days | Calendar | Infrastructure team |
| Third-party API Keys (EskomSePush, OpenWeather, etc.) | Per provider policy | Vendor notification | Infrastructure team |

### Rotation Procedure

```bash
# 1. Generate replacement
python3 -c "import secrets; print(secrets.token_hex(32))"

# 2. Update authoritative source
sudo sed -i 's/^SECRET_NAME=.*$/SECRET_NAME=<new-value>/' /etc/sentinel/secrets.env

# 3. If the secret is also in backend/.env, update it too
sed -i 's/^SECRET_NAME=.*$/SECRET_NAME=<new-value>/' /opt/bms-intelligence/backend/.env

# 4. Copy to any service-specific env files
#    Check: /etc/sentinel/rlm-runner.env, /etc/sentinel/sentry-gateway.env

# 5. Rotate at the provider (revoke old key, activate new)
#    Provider dashboards:
#      Anthropic:   https://console.anthropic.com/settings/keys
#      OpenAI:      https://platform.openai.com/api-keys
#      Telegram:    https://t.me/BotFather
#      Supabase:    https://supabase.com/dashboard/project/weujfmfubskndhvokixy

# 6. Restart affected services
sudo systemctl daemon-reload
sudo systemctl restart sentinel-backend
# If RLM runner key changed:
sudo systemctl restart sentinel-rlm-runner

# 7. Verify
curl -fsS http://localhost:9095/api/health | jq .
# Check specific integration: send test message, run inference, etc.

# 8. Record rotation
echo "| SECRET_NAME | $(date +%Y-%m-%d) | <reason> |" >> docs/09-security/secret-rotation-log.md
```

### Emergency Credential Compromise

If a secret is suspected compromised:

```bash
# 1. Generate new value immediately
python3 -c "import secrets; print(secrets.token_hex(32))"

# 2. Update everywhere simultaneously
sudo sed -i 's/^COMPROMISED_SECRET=.*$/COMPROMISED_SECRET=<new-value>/' \
  /etc/sentinel/secrets.env \
  /opt/bms-intelligence/backend/.env

# 3. Revoke old credential at provider FIRST (before restart)
#    This prevents the old process from maintaining access

# 4. Restart services
sudo systemctl daemon-reload && sudo systemctl restart sentinel-backend

# 5. Verify health
curl -fsS http://localhost:9095/api/health | jq .

# 6. Investigate and log
echo "| COMPROMISED_SECRET | $(date +%Y-%m-%d) | EMERGENCY rotation — <incident ref> |" \
  >> docs/09-security/secret-rotation-log.md
```

## Migration Plan: Eliminate Secret Duplication

### Current Problem

Secrets are duplicated across up to 3 files:
- `backend/.env` — loaded by `load_dotenv()`, currently has 30+ production secrets
- `/etc/sentinel/secrets.env` — authoritative target, currently has 12 secrets
- Service-specific env files (rlm-runner.env, sentry-gateway.env)

This creates rotation skew: a secret can be rotated in one file but not another.

### Target State

```
/etc/sentinel/secrets.env  ← AUTHORITATIVE (all production secrets)
backend/.env               ← Development defaults only (no real secrets)
/etc/sentinel/rlm-runner.env ← Derived from secrets.env (documented)
/etc/sentinel/sentry-gateway.env ← Derived from secrets.env (documented)
```

### Phase 1: Inventory (done — see Secret Inventory above)

All 30+ secrets in `.env` are catalogued with their locations.

### Phase 2: Migrate Missing Secrets to secrets.env

Secrets currently ONLY in `backend/.env` that need to be added to `secrets.env`:

| Secret | Target File |
|--------|-------------|
| `ANTHROPIC_API_KEY` | `secrets.env`, `rlm-runner.env`, `sentry-gateway.env` |
| `OPENAI_API_KEY` | `secrets.env`, `sentry-gateway.env` |
| `DEEPSEEK_API_KEY` | `secrets.env` |
| `MINIMAX_API_KEY` | `secrets.env` |
| `ZAI_API_KEY` | `secrets.env` |
| `FIRECRAWL_API_KEY` | `secrets.env` |
| `TWILIO_AUTH_TOKEN` | `secrets.env` |
| `WHATSAPP_API_TOKEN` | `secrets.env` |
| `SMTP_PASSWORD` (all variants) | `secrets.env` |
| `NOTIFICATION_SMTP_PASSWORD` | `secrets.env` |
| `ROOMS_IMAP_PASSWORD` | `secrets.env` |
| `ROOMS_SMTP_PASSWORD` | `secrets.env` |
| `JWT_SECRET_KEY` | `secrets.env` |
| `ENCRYPTION_KEY` | `secrets.env` |
| `BRIDGE_API_TOKEN` | Legacy fallback in `secrets.env` ✅ |
| `BRIDGE_API_TOKEN_SITE_002` | Site 002 bridge token in `secrets.env` ✅ |
| `BRIDGE_API_TOKEN_SITE_005` | Site 005 bridge token in `secrets.env` ✅ |
| `METRICS_BEARER_TOKEN` | `secrets.env` (or `backend.env` as non-secret) |
| `INTERNAL_SERVICE_KEY` | `secrets.env` |
| `ESKOMSEPUSH_API_TOKEN` | `secrets.env` |
| `MCP_API_KEY` | `secrets.env` |
| `SOLARMAN_APP_SECRET` | `secrets.env` |
| `OPENWEATHER_API_KEY` | `secrets.env` |
| `N8N_API_KEY` | `secrets.env` |
| `SENTRY_WEBHOOK_SECRET` | `secrets.env` |
| `SENTINEL_OPERATOR_PASSWORD` | `secrets.env` |
| `CONSENT_HASH_SALT` | `secrets.env` |
| `SENTRY_BOT_API_KEY` | Already in `secrets.env` ✅ |
| `SENTRY_CLIENT_BOT_TOKEN` | Already in `secrets.env` ✅ |
| `SENTRY_TECH_BOT_TOKEN` | Already in `secrets.env` ✅ |
| `SENTINEL_HOME_BOT_TOKEN` | Already in `secrets.env` ✅ |
| `SENTRY_MANAGER_BOT_TOKEN` | Already in `secrets.env` ✅ |

### Phase 3: Remove Duplicates from backend/.env

After Phase 2, strip all secrets from `backend/.env`, leaving only:
- `APP_NAME`, `APP_VERSION`, `DEBUG`, `ENVIRONMENT`
- `SUPABASE_URL` (non-secret)
- `DATABASE_URL` (if pointing to local dev DB)
- `CORS_ORIGINS`
- Feature flags (`PARASITE_ENABLED`, `BLOCK_BOOKING_ENABLED`, etc.)
- Non-secret defaults

```bash
# After migration, secrets in backend/.env become empty or dev-only:
sed -i 's/^ANTHROPIC_API_KEY=.*$/ANTHROPIC_API_KEY=/' backend/.env
sed -i 's/^OPENAI_API_KEY=.*$/OPENAI_API_KEY=/' backend/.env
# ... repeat for all secrets
# Or restore from .env.example and configure dev-only values
```

### Phase 4: Verify

```bash
sudo systemctl restart sentinel-backend
curl -fsS http://localhost:9095/api/health | jq .
# Verify each integration: chat, Telegram, SMTP, etc.
```

### Phase 5: Prevent Recurrence

- Add `backend/.env` to gitleaks scan path
- PR review checklist item: "No production secrets in `.env`"
- Document in onboarding: `secrets.env` is authoritative, `.env` is dev-only

## Secret Scanning

| Tool | Scope | Last Run | Result |
|------|-------|----------|--------|
| gitleaks v8.18.4 | Current working tree + full git history (2802 commits) | 2026-06-12 | Zero active findings, zero historical findings |
| Manual systemd audit | `/etc/systemd/system/sentinel-backend.service` | 2026-06-12 | No inline secrets (migrated to EnvironmentFiles) |

Gitleaks configuration: `infrastructure/gitleaks/.gitleaks.toml`

## Recovery

If the production server is lost:

1. **SOPS key** is at `/etc/sentinel/sops-key.txt` (0600, root:root). Must be restored from backup if rebuilding.
2. **Backup decryption key** is at `/etc/sentinel/backup-age.key` (0600). Also needed for offsite restore.
3. **Legacy backup SSH key**, if present, is at `/etc/sentinel/backup-ssh-key`. Use only if the active DR runbook for the deployment still requires it.
4. **Cloudflare tunnel** credentials are in `~/.cloudflared/*.json`. Will need re-auth if lost.
5. **AI provider keys** (Anthropic, OpenAI) can be regenerated from provider dashboards.
6. **Telegram bot tokens** can be regenerated from BotFather.
7. **SMTP passwords** can be reset from email provider.

## Known Gaps

1. **`backend/.env` is world-readable (644)** with 30+ plaintext secrets. This is the highest-priority fix. These secrets should be migrated to `/etc/sentinel/secrets.env` and `.env` should contain only non-secret defaults.
2. **Secret duplication** — the same secret exists in `backend/.env`, `secrets.env`, and sometimes service-specific env files. Creates skew risk during rotation.
3. **No automated rotation** — all rotations are manual. No schedule for periodic rotation.
4. **CI/CD secrets** (GitHub Actions) not audited — visible only via GitHub web UI.
5. **Cloudflare tunnel certs** are world-readable (644). Should be restricted to cloudflared user/group.

## Audit Checklist

- [ ] gitleaks run shows zero findings
- [ ] No inline secrets in systemd units
- [ ] `/etc/sentinel/secrets.env` is 0600
- [ ] `/etc/sentinel/backend.env` is 0640
- [ ] `backend/.env` does not contain secrets (target state)
- [ ] All Telegram bot tokens rotated within 90 days
- [ ] All AI provider keys rotated within 90 days
- [ ] SOPS key backed up offline
- [ ] Backup encryption key backed up offline
- [ ] GitHub Actions secrets audited
- [ ] Restore drill verified secrets recovery
