# Secret Rotation Log

**Last scan:** 2026-06-12
**Tool:** gitleaks v8.18.4
**Scope:** /opt/bms-intelligence (current working tree + full git history) + /etc/systemd/system/sentinel-backend.service (manual review)

## Already Rotated
| Secret | Date | Reason |
|--------|------|--------|
| ELEVENLABS_API_KEY (`sk_4a721363...`) | Pre-2026-06 (Fable audit) | Hardcoded in `/etc/systemd/system/sentinel-backend.service` — outside repo, gitleaks blind spot. Source: legacy systemd unit. |
| **Phase 226.1.1 — EnvironmentFile lifecycle migration** | 2026-06-12 | **Not a rotation** — moved all hardcoded secrets out of `/etc/systemd/system/sentinel-backend.service.d/*.conf` and the main unit's `Environment=` line into two managed EnvironmentFiles: `/etc/sentinel/backend.env` (0640, root:bederf) and `/etc/sentinel/secrets.env` (0600, root:bederf). The 10 env-only DropIns were deleted; `logfile.conf` (StandardOutput/StandardError directives) was preserved. Service restarted cleanly, `/api/health` returns HTTP 200. |
| ADMIN_PIN_HASH | 2026-06-12 | Rotated via `bcrypt.hashpw()`. New PIN: `198104`. Old hash replaced in `/etc/sentinel/secrets.env`. |
| BRIDGE_API_TOKEN | 2026-06-12 | Rotated via `secrets.token_hex(32)`. New: `3016b935...`. Old value replaced in `/etc/sentinel/secrets.env`. |
| HOME_BOT_WEBHOOK_SECRET | 2026-06-12 | Rotated via `secrets.token_hex(32)`. New: `8cff7b3d...`. Old value replaced in `/etc/sentinel/secrets.env`. |
| ELEVENLABS_API_KEY (inline cleanup) | 2026-06-12 | Removed inline `Environment="ELEVENLABS_API_KEY=..."` and `Environment="ELEVENLABS_TTS_ENABLED=true"` from `/etc/systemd/system/sentinel-backend.service`. `ELEVENLABS_TTS_ENABLED` moved to `/etc/sentinel/backend.env`. Service now reads both values from EnvironmentFiles. Key value NOT YET ROTATED — old key still in `secrets.env` pending ElevenLabs dashboard rotation. |

## Secret Inventory (current locations)

| Secret | Location | Permissions | Owner |
|--------|----------|-------------|-------|
| ADMIN_PIN_HASH | /etc/sentinel/secrets.env | 0600 | root:bederf |
| SUPABASE_SERVICE_ROLE_KEY | /etc/sentinel/secrets.env | 0600 | root:bederf |
| SUPABASE_KEY | /etc/sentinel/secrets.env | 0600 | root:bederf |
| BRIDGE_API_TOKEN | /etc/sentinel/secrets.env | 0600 | root:bederf |
| SENTINEL_HOME_BOT_TOKEN | /etc/sentinel/secrets.env | 0600 | root:bederf |
| HOME_BOT_WEBHOOK_SECRET | /etc/sentinel/secrets.env | 0600 | root:bederf |
| SENTRY_BOT_API_KEY | /etc/sentinel/secrets.env | 0600 | root:bederf |
| SENTRY_CLIENT_BOT_TOKEN | /etc/sentinel/secrets.env | 0600 | root:bederf |
| SENTRY_TECH_BOT_TOKEN | /etc/sentinel/secrets.env | 0600 | root:bederf |
| SENTRY_MANAGER_BOT_TOKEN | /etc/sentinel/secrets.env | 0600 | root:bederf |
| SMTP_PASSWORD | /etc/sentinel/secrets.env | 0600 | root:bederf |
| ELEVENLABS_API_KEY | /etc/sentinel/secrets.env only (inline removed from systemd) | 0600 | root:bederf |

## Active Findings (Current Working Tree)
No active findings. `gitleaks detect --source .` scanned 2802 commits and the current working tree in 1m6.2s and reported "no leaks found".

## Historical Findings (Git History)
No historical findings. `gitleaks detect --source . --log-opts="--all"` scanned the full git history in 48.9s and reported "no leaks found".

## Required Rotations

### PENDING — Provider Dashboard Required

| Secret | Provider | Action | Prep Status |
|--------|----------|--------|-------------|
| ELEVENLABS_API_KEY | ElevenLabs dashboard | Generate new key → replace value in `/etc/sentinel/secrets.env` → restart | Inline removed from systemd; `secrets.env` ready |
| SUPABASE_SERVICE_ROLE_KEY | Supabase dashboard | Rotate → copy new value → `sudo sed -i 's/^SUPABASE_SERVICE_ROLE_KEY=.*$/SUPABASE_SERVICE_ROLE_KEY=<new>/' /etc/sentinel/secrets.env` → restart | `secrets.env` ready |
| SUPABASE_KEY (anon) | Supabase dashboard (same project) | Same as above | `secrets.env` ready |
| SENTINEL_HOME_BOT_TOKEN | BotFather → `/revoke` → `/token` | Replace in `secrets.env` → restart | `secrets.env` ready |
| SENTRY_BOT_API_KEY | BotFather → Sentry Bot 1 | Replace in `secrets.env` → restart | `secrets.env` ready |
| SENTRY_CLIENT_BOT_TOKEN | BotFather → Sentry Bot 2 | Replace in `secrets.env` → restart | `secrets.env` ready |
| SENTRY_TECH_BOT_TOKEN | BotFather → Sentry Bot 3 | Replace in `secrets.env` → restart | `secrets.env` ready |
| SENTRY_MANAGER_BOT_TOKEN | BotFather → Sentry Bot 4 | Replace in `secrets.env` → restart | `secrets.env` ready |
| SMTP_PASSWORD | Email provider dashboard | Replace in `secrets.env` → restart | `secrets.env` ready |

**Post-rotation command**:
```bash
sudo systemctl daemon-reload && sudo systemctl restart sentinel-backend
```

Then verify: `curl -fsS http://localhost:9095/api/health | jq .`

## Blind Spots
- **systemd units in `/etc/systemd/system/`** are not in the repo and gitleaks cannot scan them. Manual review required. As of 2026-06-12, `sentinel-backend.service` no longer contains inline secrets — all secrets sourced from `/etc/sentinel/secrets.env`. Verify periodically.
- **CI/CD secrets in GitHub Actions** are visible only via the GitHub web UI (Settings → Secrets and variables → Actions). Run a separate audit on Actions secrets before customer onboarding.
- **Environment files** (`.env`, `backend/.env`, `frontend/.env*`) are gitignored but may contain live secrets on the server. Manual review of `bederf@<host>` home dir and `/opt/bms-intelligence/.env*` recommended.
- **Cloudflare R2 / Supabase service role / Anthropic / OpenAI / Telegram bot tokens** — verify none are committed by spot-checking `git log -p --all | grep -iE 'sk-|sk_|sk-ant-|eyJ|bot[0-9]+:'` (already covered by gitleaks history scan, but manual grep provides defense in depth).

## Verification Checklist
- [x] gitleaks run shows zero active findings
- [x] Historical findings either rotated or documented as false positive
- [x] Blind spot (ELEVENLABS_API_KEY in systemd) documented
- [ ] ELEVENLABS_API_KEY rotated and systemd unit updated
- [ ] GitHub Actions secrets audited
- [ ] Server `.env*` files audited
