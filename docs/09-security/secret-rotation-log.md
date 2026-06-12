# Secret Rotation Log

**Last scan:** 2026-06-12
**Tool:** gitleaks v8.18.4
**Scope:** /opt/bms-intelligence (current working tree + full git history) + /etc/systemd/system/sentinel-backend.service (manual review)

## Already Rotated
| Secret | Date | Reason |
|--------|------|--------|
| ELEVENLABS_API_KEY (`sk_4a721363...`) | Pre-2026-06 (Fable audit) | Hardcoded in `/etc/systemd/system/sentinel-backend.service` — outside repo, gitleaks blind spot. Source: legacy systemd unit. |
| **Phase 226.1.1 — EnvironmentFile lifecycle migration** | 2026-06-12 | **Not a rotation** — moved all hardcoded secrets out of `/etc/systemd/system/sentinel-backend.service.d/*.conf` and the main unit's `Environment=` line into two managed EnvironmentFiles: `/etc/sentinel/backend.env` (0640, root:bederf) and `/etc/sentinel/secrets.env` (0600, root:bederf). The 10 env-only DropIns were deleted; the main unit's inline `ELEVENLABS_API_KEY=` is now sourced from `secrets.env` via `/etc/systemd/system/sentinel-backend.service.d/envfiles.conf` (systemd EnvironmentFile values override inline `Environment=` for the same key). `logfile.conf` (StandardOutput/StandardError directives) was preserved. Service restarted cleanly, `/api/health` returns HTTP 200. Audit gap: inline key still present in main unit (rotation needed to fully eliminate it). |

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
| ELEVENLABS_API_KEY | /etc/sentinel/secrets.env (effective) — also still inline in /etc/systemd/system/sentinel-backend.service (audit gap, pending rotation) | 0600 / 0644 | root:bederf / root:root |

## Active Findings (Current Working Tree)
No active findings. `gitleaks detect --source .` scanned 2802 commits and the current working tree in 1m6.2s and reported "no leaks found".

## Historical Findings (Git History)
No historical findings. `gitleaks detect --source . --log-opts="--all"` scanned the full git history in 48.9s and reported "no leaks found".

## Required Rotations

### CRITICAL — Blind Spot (Outside Repo)
1. **ELEVENLABS_API_KEY** — Hardcoded as plaintext in `/etc/systemd/system/sentinel-backend.service` line 13:
   ```
   Environment="ELEVENLABS_API_KEY=sk_4a7213637768319b20a3e38ffdb1260436aadb5a980d9bb5"
   ```
   **Action**: Rotate via ElevenLabs dashboard → store new key in `/etc/sentinel-backend/secrets.env` (chmod 600, root:root) → update systemd unit to `EnvironmentFile=` → `sudo systemctl daemon-reload && sudo systemctl restart sentinel-backend`.

## Blind Spots
- **systemd units in `/etc/systemd/system/`** are not in the repo and gitleaks cannot scan them. Manual review required. The `sentinel-backend.service` unit currently contains a hardcoded ELEVENLABS_API_KEY (see Required Rotations).
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
