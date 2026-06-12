# Secret Lifecycle

**Phase 226.1.8** — Developer guide for managing secrets across the SENTINEL BMS Intelligence platform.
Owner: Security Engineering. Review cycle: quarterly.

## Storage

| Location | Use | Mode | Owner |
|----------|-----|------|-------|
| `/etc/sentinel/secrets.env` | Production secrets (API keys, tokens, DB passwords) | `0600` | `root:bederf` |
| `/etc/sentinel/backend.env` | Non-secret runtime config (URLs, log levels, feature flags) | `0640` | `root:bederf` |
| `backend/.env` | Local development overrides | gitignored | developer |
| `backend/.env.enc` | SOPS-encrypted shared dev secrets | committed | team |
| `/etc/systemd/system/sentinel-backend.service.d/*.conf` | systemd DropIns | `0640` | `root:bederf` |

**DropIns are for non-secret directives only.** Never put a secret in a DropIn file — they are world-readable in some tooling chains.

## Adding a new secret

1. Generate the secret in the provider's dashboard.
2. Add it to `/etc/sentinel/secrets.env` (NOT to a systemd DropIn, NOT to `.env` in the repo).
3. Reload and restart the backend:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl restart sentinel-backend
   ```
4. Verify the service picked up the secret: `curl -fsS http://localhost:9095/api/health | jq`.
5. Add an entry to the **Secret Inventory** table in `docs/09-security/secret-rotation-log.md`.
6. Commit the *use* of the secret (env-var reference) in source — never the value.

## Rotation SLA

| Severity | Definition | SLA | Example |
|----------|------------|-----|---------|
| Critical | Production-facing; breach = data exposure | < 24 hours | Supabase service role key, Telegram bot token, Anthropic API key |
| High | Operator-facing; breach = operational impact | < 7 days | Mosquitto MQTT password, Sentry DSN, Grafana admin |
| Medium | Internal; breach = limited blast radius | < 30 days | Dev/test API keys, advisory webhook tokens |

Track each rotation in `secret-rotation-log.md` with: name, severity, previous_hash-prefix, new_hash-prefix, operator, ticket.

## Local dev with secrets

- Use SOPS-encrypted files (`*.env.enc`) for shared dev secrets.
- Plain `.env` files are **BLOCKED** by the pre-commit hook `check-env-files`.
- For one-off testing, use a local `.env.local` (gitignored via `backend/.gitignore`).
- Never copy a production secret into a local `.env` — generate a separate dev credential.

## CI enforcement

| Layer | Tool | Trigger | Action |
|-------|------|---------|--------|
| Pre-commit | gitleaks (`.pre-commit-config.yaml`) | every `git commit` | blocks local commit |
| PR gate | `secrets-pr-gate` job in `security-scan.yml` | every pull_request | **blocks merge** |
| Push scan | `secrets-scan` job in `security-scan.yml` | every push to main | fails workflow |
| Weekly scan | `security-scan.yml` schedule (`0 6 * * 1`) | Monday 06:00 UTC | reports to summary |

Branch protection must require the status check named **"PR Gate: Gitleaks (zero tolerance)"** to block PR merge on any new finding.

## False positive handling

Two paths, in order of preference:

1. **Inline allow (preferred)**: add `# gitleaks:allow` on the line with a one-line justification comment.
   ```python
   TELEGRAM_TOKEN = "***TELEGRAM_BOT_TOKEN_REDACTED***"  # gitleaks:allow — example value in docs
   ```

2. **Path allowlist (use sparingly)**: add a path or regex to the `[allowlist]` section of `.gitleaks.toml` with a comment explaining why.
   ```toml
   [allowlist]
   paths = [
     '''backend/tests/fixtures/example_webhook\.json''',  # Fixture used in test_webhook_signature.py
   ]
   ```

**Never use a global disable.** Every allow-list entry must be reviewed at every quarterly security review. Entries older than 6 months without a justification comment will be flagged and removed.

## Incident response — secret already committed

If a real secret reaches `main`:

1. **Rotate the secret immediately** at the provider. Do this first; do not wait for cleanup.
2. Purge from git history with `git filter-repo` (NOT `git rebase` — leaves dangling blobs).
3. Force-push the cleaned branch (coordinate with reviewers).
4. Add a `CRITICAL` row to `secret-rotation-log.md` with the timeline.
5. File an incident in the security ticket queue within 24h.
6. Notify the security engineering lead via Telegram `#sentinel-sec` channel.

Git history is **not** safe even after a force-push — GitHub retains events, fork mirrors may have copies, and CI caches can persist. The secret MUST be rotated.

## References

- `docs/09-security/secret-rotation-log.md` — secret inventory + rotation log
- `docs/09-security/cryptography-key-management-policy.md` — key strength + storage rules
- `docs/09-security/incident-response-process.md` — breach playbook
- `docs/09-security/application-security-pipeline.md` — full CI security pipeline
- `.github/workflows/security-scan.yml` — CI workflow definition
- `.gitleaks.toml` — gitleaks rules + allow-lists
- `.pre-commit-config.yaml` — pre-commit hook configuration
