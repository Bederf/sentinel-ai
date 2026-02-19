# Application Security Pipeline

> SENTINEL BMS Intelligence - Automated Security Testing Pipeline
>
> **FSR Domains:** 4.9 (Application Security), 4.10 (Vulnerability Management)
>
> **Last Updated:** 2026-02-04

## Overview

SENTINEL implements a multi-layered application security pipeline that integrates security testing throughout the Software Development Lifecycle (SDLC). This document describes the automated security gates, tools, remediation processes, and metrics used to maintain application security posture.

## SDLC Security Gates

Security checks are integrated at three points in the development lifecycle:

```
Developer Workstation          CI/CD Pipeline              Production
====================          ==============              ==========

  [Code Change]
       |
  [Pre-commit Hooks] -----> gate 1: shift-left
       |                    - secrets detection
       |                    - .env file blocking
       |                    - safety rules validation
       |                    - hardcoded API key check
       |
  [Git Push / PR]
       |
  [GitHub Actions] -------> gate 2: automated pipeline
       |                    - Python SAST (Bandit)
       |                    - Frontend audit (npm)
       |                    - Dependency check (pip-audit)
       |                    - Container scan (Trivy)
       |                    - Secrets scan (Gitleaks)
       |
  [Merge to Main]
       |
  [Weekly Schedule] ------> gate 3: continuous monitoring
       |                    - Full security scan (Monday 06:00 UTC)
       |                    - Dependabot dependency updates
       |                    - Vulnerability database refresh
       |
  [Deployed] ----------------> runtime protection
                               - Cloudflare WAF (Phase 63-02)
                               - Wazuh IDS (Phase 63-02)
                               - Fail2Ban (Phase 63-02)
```

## CI/CD Pipeline

The security scanning pipeline runs as a GitHub Actions workflow (`.github/workflows/security-scan.yml`).

### Pipeline Diagram

```
                    +------------------+
                    |  Push / PR /     |
                    |  Weekly Schedule |
                    +--------+---------+
                             |
              +--------------+--------------+
              |              |              |
     +--------v--+    +------v-----+   +----v--------+
     | sast-python|    |sast-frontend|   |dependency-  |
     | (Bandit)   |    |(npm audit) |   |check        |
     +--------+---+    +------+-----+   |(pip-audit)  |
              |              |          +----+--------+
              |              |               |
              |    +---------v--------+      |
              |    | container-scan   |      |
              |    | (Trivy)          |      |
              |    +---------+--------+      |
              |              |               |
              |    +---------v--------+      |
              |    | secrets-scan     |      |
              |    | (Gitleaks)       |      |
              |    +---------+--------+      |
              |              |               |
              +--------------+---------------+
                             |
                    +--------v---------+
                    | security-summary |
                    | (aggregate)      |
                    +------------------+
```

### Trigger Conditions

| Trigger | Scope | Frequency |
|---------|-------|-----------|
| Push to `main` | Full pipeline | Every merge |
| Pull request to `main` | Full pipeline | Every PR |
| Scheduled (cron) | Full pipeline | Monday 06:00 UTC (08:00 SAST) |

### Jobs Detail

#### 1. Python SAST (Bandit)

- **Tool:** [Bandit](https://bandit.readthedocs.io/) - Python static analysis for security
- **Scope:** `backend/app/` (excludes `backend/app/data/`)
- **Severity threshold:** Medium and above
- **Failure condition:** Any HIGH or CRITICAL findings
- **Output:** `bandit-report.json` (artifact, 90-day retention)

Bandit checks for common Python security issues:
- SQL injection patterns
- Use of `eval()`, `exec()`, `subprocess` with shell=True
- Hardcoded passwords and secrets
- Insecure cryptographic practices
- XML parsing vulnerabilities

#### 2. Frontend Security Audit

- **Tool:** `npm audit` - Node.js dependency vulnerability scanner
- **Scope:** `frontend/package.json` and dependency tree
- **Failure condition:** Any CRITICAL vulnerabilities
- **Output:** `npm-audit-report.json` (artifact, 90-day retention)

#### 3. Dependency Vulnerability Check

- **Tools:**
  - [pip-audit](https://pypi.org/project/pip-audit/) - Python dependency auditing
  - [Safety](https://pypi.org/project/safety/) - Python vulnerability database
- **Scope:** `backend/requirements.txt`
- **Failure condition:** Warning at 5+ vulnerable dependencies
- **Output:** `pip-audit-report.json`, `safety-report.json` (artifacts, 90-day retention)

#### 4. Container Scan (Trivy)

- **Tool:** [Trivy](https://aquasecurity.github.io/trivy/) by Aqua Security
- **Scans:**
  - Container image: `sentinel-backend:scan` (built from `backend/Dockerfile`)
  - Filesystem: `backend/` directory
- **Checks:** Vulnerabilities (CVEs), secrets, misconfigurations
- **Failure condition:** Any CRITICAL findings in container image
- **Configuration:** `infrastructure/trivy/trivy.yaml`
- **Output:** `trivy-container-report.json`, `trivy-fs-report.json` (artifacts, 90-day retention)

Trivy configuration highlights:
- Ignores unfixed vulnerabilities (no available patch)
- Skips test files, documentation, and non-essential directories
- Checks for Dockerfile best practices

#### 5. Secrets Detection (Gitleaks)

- **Tool:** [Gitleaks](https://gitleaks.io/) - secrets detection in git history
- **Scope:** Full repository history
- **Failure condition:** Any secret detected
- **Note:** Scans entire git history, not just current commit

## Scan Frequency

| Check Type | On PR | On Merge | Weekly | Dependabot |
|------------|-------|----------|--------|------------|
| Python SAST | Yes | Yes | Yes | - |
| Frontend audit | Yes | Yes | Yes | - |
| Dependency vulnerabilities | Yes | Yes | Yes | Weekly |
| Container scan | Yes | Yes | Yes | Monthly |
| Secrets detection | Yes | Yes | Yes | - |
| GitHub Actions updates | - | - | - | Monthly |
| Docker base image updates | - | - | - | Monthly |

## Remediation SLAs

Per FSR gap analysis requirements:

| Severity | SLA | Action Required |
|----------|-----|-----------------|
| **Critical** | **7 days** | Immediate remediation. Block deployment if found in CI. Assign to on-call engineer. |
| **High** | **14 days** | Prioritize in current sprint. Create tracking issue. |
| **Medium** | **30 days** | Schedule in backlog. Review in next planning session. |
| **Low** | **90 days** | Address during regular maintenance cycles. |
| **Informational** | No SLA | Document for awareness. No action required. |

### SLA Escalation Process

1. **Day 0:** Finding detected, issue created automatically
2. **50% SLA:** Reminder notification to assignee
3. **75% SLA:** Escalation to team lead
4. **100% SLA:** Escalation to security owner, finding marked overdue

## Finding Triage Process

### Workflow

1. **Detection:** Automated scan identifies vulnerability
2. **Classification:** Assign severity (Critical/High/Medium/Low)
3. **Triage:** Security review within 24 hours for Critical/High
4. **Assignment:** Assign to appropriate engineer with SLA deadline
5. **Remediation:** Fix applied (patch, upgrade, code change)
6. **Verification:** Re-scan confirms finding resolved
7. **Closure:** Finding closed with resolution notes

### Triage Decision Matrix

| Factor | Weight | Criteria |
|--------|--------|----------|
| CVSS Score | 40% | Base score from vulnerability database |
| Exploitability | 25% | Public exploit available? Network-accessible? |
| Data exposure | 20% | Access to BMS controls, PII, credentials? |
| Compensating controls | 15% | WAF, IDS, network segmentation in place? |

### BMS-Specific Considerations

When triaging vulnerabilities in SENTINEL, consider:

- **Safety impact:** Could exploitation affect building safety systems (fire, access control)?
- **Operational impact:** Could it disrupt HVAC, lighting, or energy management?
- **Tenant impact:** Could it affect building occupant comfort or safety?
- **Regulatory impact:** Does it affect compliance with SANS 10400 or OHS Act?

## Exception Process

When a vulnerability cannot be remediated within SLA:

1. **Document the exception** in the risk register
2. **Provide justification:** Why remediation is not feasible
3. **Identify compensating controls:** What mitigates the risk
4. **Set review date:** When to re-evaluate (max 90 days)
5. **Approval:** Security owner signs off on accepted risk

Exception template:
```
Exception ID: SEC-EXC-YYYY-NNN
Vulnerability: CVE-YYYY-NNNNN
Severity: HIGH
Justification: [reason remediation is deferred]
Compensating Controls: [what mitigates the risk]
Review Date: YYYY-MM-DD
Approved By: [name]
```

## Local Development Scanning

Developers can run the full security scan locally:

```bash
# Full scan (all 5 checks)
./scripts/security-scan.sh

# Quick scan (skip container scanning - faster)
./scripts/security-scan.sh --quick
```

### Pre-commit Hooks

Security checks run automatically before each commit:

```bash
# Install pre-commit hooks (one-time setup)
pip install pre-commit
pre-commit install

# Run manually on all files
pre-commit run --all-files
```

Active pre-commit hooks:
- **detect-secrets:** Scans for hardcoded secrets using entropy and regex
- **check-hardcoded-secrets:** Blocks commits with API keys (sk-ant-*, eyJhbGci*)
- **check-env-files:** Prevents .env files from being committed
- **validate-safety-rules:** Ensures safety rules JSON has required fields
- **check-debug-patterns:** Warns about debug statements (pdb, breakpoint, console.log)
- **check-equipment-id-format:** Validates v2.0 naming convention compliance

## Dependabot Configuration

Automated dependency updates via GitHub Dependabot (`.github/dependabot.yml`):

| Ecosystem | Directory | Frequency | Time (SAST) |
|-----------|-----------|-----------|-------------|
| Python (pip) | `/backend` | Weekly | Monday 08:00 |
| Node.js (npm) | `/frontend` | Weekly | Monday 09:00 |
| GitHub Actions | `/` | Monthly | - |
| Docker | `/backend`, `/frontend` | Monthly | - |

Dependabot groups related updates (security, AI/ML, UI) to reduce PR noise.

## Metrics Tracked

### Security Posture Metrics

| Metric | Description | Target |
|--------|-------------|--------|
| **Open findings by severity** | Count of unresolved vulnerabilities | Critical: 0, High: <3 |
| **Mean time to remediate (MTTR)** | Average days from detection to fix | Critical: <3d, High: <10d |
| **Scan pass rate** | % of CI runs with no critical findings | >95% |
| **Dependency currency** | % of dependencies on latest patch version | >80% |
| **Pre-commit adoption** | % of developers with hooks installed | 100% |
| **Exception count** | Number of active risk exceptions | <5 |

### Reporting

- **Weekly:** Automated scan results summary (GitHub Actions)
- **Monthly:** Dependency update status review
- **Quarterly:** Full security posture assessment for FSR evidence

## Tools Reference

| Tool | Purpose | License | Integration |
|------|---------|---------|-------------|
| [Bandit](https://bandit.readthedocs.io/) | Python SAST | Apache 2.0 | CI + local |
| [pip-audit](https://pypi.org/project/pip-audit/) | Python dependency audit | Apache 2.0 | CI + local |
| [Safety](https://pypi.org/project/safety/) | Python vulnerability DB | MIT | CI + local |
| [Trivy](https://aquasecurity.github.io/trivy/) | Container + filesystem scan | Apache 2.0 | CI + local |
| [Gitleaks](https://gitleaks.io/) | Secrets detection | MIT | CI |
| [detect-secrets](https://github.com/Yelp/detect-secrets) | Secrets baseline | Apache 2.0 | Pre-commit |
| [npm audit](https://docs.npmjs.com/cli/v8/commands/npm-audit) | Node.js dependency audit | Built-in | CI + local |
| [Dependabot](https://docs.github.com/en/code-security/dependabot) | Automated updates | GitHub | GitHub |
| [pre-commit](https://pre-commit.com/) | Git hook framework | MIT | Local |

## Technology Stack Coverage

| Layer | Technology | Security Tools |
|-------|-----------|----------------|
| Backend | Python 3.11 + FastAPI | Bandit (SAST), pip-audit, Safety |
| Frontend | React + TypeScript + Vite | npm audit |
| Container | Docker (python:3.11-slim) | Trivy |
| Dependencies | pip, npm | Dependabot |
| Repository | Git (GitHub) | Gitleaks, detect-secrets |
| Runtime | Cloudflare, Linux | WAF (Phase 63-02), Wazuh IDS |

## FSR Evidence

This pipeline provides evidence for:

- **FSR 4.9 (Application Security):** Automated SAST, dependency scanning, container scanning, and secrets detection integrated into CI/CD pipeline with pre-commit shift-left hooks. Current score: **3.8/5.0**.
- **FSR 4.10 (Vulnerability Management):** Defined remediation SLAs (Critical 7d, High 14d, Medium 30d), automated Dependabot updates across 4 ecosystems, triage process, exception handling, and metrics tracking. Current score: **4.3/5.0** — exceeds threat model requirements for local deployment with only Telegram/WhatsApp external interfaces.

### Audit Artifacts

All scan reports are retained for 90 days as GitHub Actions artifacts:
- `bandit-sast-report` - Python SAST findings
- `npm-audit-report` - Frontend dependency vulnerabilities
- `dependency-audit-reports` - pip-audit + Safety results
- `trivy-scan-reports` - Container and filesystem scan results

---

*Document: Application Security Pipeline*
*Phase: 63-03 (Risk Technical Implementation)*
*Version: 1.0*
