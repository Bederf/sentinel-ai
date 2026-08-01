# Security Policy

## Reporting a vulnerability

Please **do not** open a public GitHub issue for security vulnerabilities.

Use GitHub's private vulnerability reporting: go to the **Security** tab of this repository → **Report a
vulnerability**. This opens a private advisory visible only to maintainers until it's resolved.

## What's in scope

- Authentication/authorization bypass
- Injection (SQL, command, prompt injection against AI agents)
- Exposed credentials or secrets
- Data isolation failures between sites/tenants
- Anything allowing an unauthenticated or under-privileged actor to read, write, or trigger equipment actions
  they shouldn't be able to

## Automated security gates

Every push and pull request to `main` runs:

- **Bandit** — Python static analysis (SAST)
- **npm audit** — frontend dependency vulnerabilities
- **pip-audit** / **Safety** — backend dependency vulnerabilities
- **Snyk** — dependency + code vulnerability scanning, results published to the repo's Security tab
  (requires a `SNYK_TOKEN` repository secret; skipped, not failed, until one is configured)
- **Gitleaks** — secrets detection (PR-blocking on any finding via the zero-tolerance PR gate)
- **Dependabot** — weekly dependency update scans across pip, npm, GitHub Actions, and Docker base images

Branch protection on `main` requires the Bandit and Gitleaks PR-gate checks to pass before a pull
request — including Dependabot's own — can be merged.

See [`.github/workflows/security-scan.yml`](.github/workflows/security-scan.yml) for the exact checks.

## Remediation SLAs

| Severity | SLA |
|----------|-----|
| Critical | 7 days |
| High | 14 days |
| Medium | 30 days |

## Further reading

- [`docs/09-security/SECURITY-PRIVACY.md`](docs/09-security/SECURITY-PRIVACY.md) — data privacy and security architecture
- [`docs/09-security/security-audit-programme.md`](docs/09-security/security-audit-programme.md) — audit programme
- [`docs/06-safety-compliance/security-hardening.md`](docs/06-safety-compliance/security-hardening.md) — hardening guidance
