---
title: "CI/CD Pipeline"
type: "operations"
status: "approved"
version: "1.0.0"
created: "2026-06-14"
updated: "2026-06-14"
author: "SENTINEL Platform Team"
tags: ["ci-cd", "github-actions", "testing", "security", "deployment"]
domain: "operations"
audience: "developer"
complexity: "intermediate"
estimated_read_time: 8
---

# CI/CD Pipeline

## Overview

SENTINEL uses GitHub Actions for all automated quality gates. Three pipelines run on every
pull request and push to `main` or `develop`.

```
Pull Request
    │
    ├── Test Suite          (frontend + backend + E2E)
    ├── Ruff Lint           (Python formatting and style)
    └── Security Scan       (SAST + dependency audit + secrets detection)
            │
            ▼ all pass
        Merge permitted
```

---

## Pipeline 1 — Test Suite (`.github/workflows/test.yml`)

Triggers: every PR and push to `main` / `develop`.

### Jobs

| Job | Runner | Key steps |
|-----|--------|-----------|
| `frontend-tests` | ubuntu-latest | `npm ci` → ESLint → TypeScript type-check → Vitest unit tests → coverage upload (Codecov) |
| `backend-tests` | ubuntu-latest | Python 3.11 → pytest (unit, excludes integration/performance/slow) → coverage upload |
| `e2e-tests` | ubuntu-latest | Playwright (Chromium) against live backend; `continue-on-error: true` (E2E references outdated nav, non-blocking) |

### Backend test scope

Unit tests run with:
```bash
pytest tests/ \
  -m "not integration and not performance and not slow" \
  --ignore=tests/integration \
  --ignore=tests/load \
  --timeout=30
```

Integration tests (requiring live Supabase) run in the nightly pipeline separately.

### Coverage

Both frontend and backend upload to Codecov with flags `frontend` / `backend`.

---

## Pipeline 2 — Ruff Lint (`.github/workflows/ruff-lint.yml`)

Triggers: PR and push to `main` / `develop`, only when `backend/**/*.py` changes.

Two gates, both fail-hard (no `continue-on-error`):

```bash
ruff format --check .   # formatting
ruff check .            # lint rules from pyproject.toml
```

**Pre-commit order** (enforced locally and in CI): `ruff format` → `ruff check` → `git commit`.
Never reverse order — format must run before lint.

---

## Pipeline 3 — Security Scan (`.github/workflows/security-scan.yml`)

Triggers: push to `main`, every PR, and weekly schedule (Monday 06:00 UTC).

Addresses FSR domains 4.9 (Application Security) and 4.10 (Vulnerability Management).

### Jobs

| Job | Tool | Blocks merge |
|-----|------|-------------|
| `sast-python` | Bandit | Yes — fails on any HIGH/CRITICAL finding in `backend/app/` |
| `sast-frontend` | npm audit | Yes — fails on any CRITICAL frontend dependency CVE |
| `dependency-check` | pip-audit + Safety | Warning only (>5 vulns triggers warning) |
| `container-scan` | Trivy | Disabled — runner disk too small; re-enable on self-hosted |
| `secrets-scan` | Gitleaks | Yes — zero tolerance on push to `main` |
| `secrets-pr-gate` | Gitleaks | Yes — **blocks PR merge** on any secret finding |

### Secrets PR gate

The `secrets-pr-gate` job posts a PR comment on failure with remediation steps pointing
to `docs/09-security/secret-lifecycle.md` and `docs/09-security/secret-rotation-log.md`.
Branch protection must target this job name: `"PR Gate: Gitleaks (zero tolerance)"`.

### Remediation SLAs

| Severity | SLA |
|----------|-----|
| Critical | 7 days |
| High | 14 days |
| Medium | 30 days |

All scan reports are retained for 90 days as FSR audit evidence.

---

## Deployment

SENTINEL is deployed to a Contabo VPS running systemd services. There is no automated
deployment pipeline — deployment is a manual, gated process:

```
1. All CI checks pass on main
2. Developer SSHs to VPS (Ed25519 key + TOTP 2FA)
3. git pull on the VPS
4. ruff format + ruff check (verify clean)
5. systemctl restart sentinel-backend
6. Wait 30s minimum, then poll /api/health
7. Check Grafana for error rate / latency regression
```

### Rollback

```bash
# Roll back to previous commit
git log --oneline -5               # find the previous good commit
git checkout <previous-sha>        # check out that version
systemctl restart sentinel-backend
# Verify /api/health returns 200
```

There is no blue/green or canary deployment at present. The VPS runs a single instance.
Rollback window is bounded by `/api/health` polling — a bad deploy is detected within
the 30s startup window.

### Environment promotion

| Environment | How |
|-------------|-----|
| Local dev | `uvicorn app.main:app --reload` |
| Staging | Not a separate environment — integration tests run against a test Supabase project |
| Production | Manual SSH deploy from `main` after all CI gates pass |

---

## Branch Strategy

| Branch | Protection | Purpose |
|--------|-----------|---------|
| `main` | All CI required + Gitleaks PR gate | Production |
| `develop` | Test + Ruff required | Integration branch |
| Feature branches | None (CI runs but non-blocking) | Development |

---

## Adding a New Test

**Backend:**
```python
# tests/your_module/test_your_feature.py
import pytest

@pytest.mark.asyncio
async def test_your_feature():
    ...
```

Mark integration tests that need Supabase with `@pytest.mark.integration` — they are
excluded from the PR pipeline and run only in the nightly job.

**Frontend:**
```typescript
// src/components/__tests__/YourComponent.test.tsx
import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
```

---

## Key Files

| File | Purpose |
|------|---------|
| `.github/workflows/test.yml` | Test suite (frontend + backend + E2E) |
| `.github/workflows/ruff-lint.yml` | Python format and lint gate |
| `.github/workflows/security-scan.yml` | SAST, dependency audit, secrets scanning |
| `.gitleaks.toml` | Gitleaks allow-list configuration |
| `backend/pyproject.toml` | Ruff rule configuration |
| `frontend/package.json` | `test:run`, `test:coverage`, `lint` scripts |
