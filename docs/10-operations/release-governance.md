---
title: "SENTINEL Release & CI/CD Governance"
type: "guide"
status: "draft"
version: "1.0.0"
created: "2026-06-14"
---

# SENTINEL Release & CI/CD Governance

## Deployment Workflow

```
Developer commits → GitHub → pre-commit hooks → PR → merge → deploy
```

### Pre-commit (local)

| Hook | Tool | Purpose |
|------|------|---------|
| Formatting | ruff format | Enforce code style |
| Linting | ruff check | Catch common errors |
| Secrets scan | gitleaks | Detect committed secrets |
| MyPy | mypy (regression gate) | Type checking — fails only on new errors |

### Pull Request

Before merging to `main`, a PR should:
- Have a descriptive title and summary
- Pass all CI checks (if configured)
- Include or reference tests for new functionality
- Not introduce new gitleaks findings

### Merge to Main

- Direct pushes to `main` are blocked
- Only squash-merges via PR
- PR description becomes the commit message

### Deployment

The production stack is deployed via systemd units on a single VPS:

| Service | Unit | Restart Method |
|---------|------|----------------|
| Backend API | `sentinel-backend.service` | `sudo systemctl restart sentinel-backend` |
| Frontend | `sentinel-frontend.service` | `sudo systemctl restart sentinel-frontend` |
| Supabase | Docker (supabase CLI) | `supabase stop && supabase start` |
| Monitoring | Docker compose | `docker compose -f docker-compose.monitoring.yml restart` |

**Manual deploy procedure:**

```bash
# 1. Pull latest
cd /opt/bms-intelligence && git pull origin main

# 2. Install dependencies (if requirements.txt changed)
cd backend && venv/bin/pip install -r requirements.txt

# 3. Run migrations (if new .sql files in supabase/migrations/)
supabase db push

# 4. Restart services
sudo systemctl restart sentinel-backend

# 5. Verify
curl -fsS http://localhost:9095/api/health | jq .
```

## Rollback Procedure

```bash
# 1. Revert to previous commit
cd /opt/bms-intelligence && git revert HEAD

# 2. If database migration was applied, apply rollback migration
#    (or restore from backup if irreversible)
supabase db reset  # Resets to migration baseline
scripts/restore/restore_postgres_backup.sh latest

# 3. Restart
sudo systemctl restart sentinel-backend

# 4. Verify
curl -fsS http://localhost:9095/api/health | jq .
```

## Testing Coverage

| Layer | Tool | Scope | CI |
|-------|------|-------|----|
| API tests | pytest | Endpoints, auth, permissions | Manual |
| Unit tests | pytest | Services, repositories, models | Manual |
| Performance | k6 | API benchmarks | Manual |
| Security | gitleaks | Secret detection | Pre-commit |

Known gap: Tests are not automatically run in CI/CD. All testing is currently manual/developer-driven.

## Environment Separation

| Environment | Backend URL | Supabase | Secrets Source |
|-------------|-------------|----------|----------------|
| Production | `localhost:9095` | Local (`:55322`) | `/etc/sentinel/secrets.env` |
| Development | `localhost:8000` | Local (`:55322`) | `backend/.env` |

All environments use the same local Supabase instance. There is no separate staging environment.

## Known Gaps

1. **No automated CI pipeline** — no GitHub Actions or equivalent. All testing is manual.
2. **No staging environment** — production is the only deployed environment.
3. **No automated rollback testing** — rollback procedure exists but is untested.
4. **No release artifacts** — deployments are git pull + restart, no versioned releases.
