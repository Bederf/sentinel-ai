# Vulnerability Scanning Infrastructure

SENTINEL BMS Intelligence Platform - Operational vulnerability scanning for FSR domain 4.10 compliance.

## Overview

This directory contains scanning scripts for monthly external and quarterly internal vulnerability assessments. Both SENTINEL and AimTheLaw share the Contabo VPS, so internal scans cover both products.

**Infrastructure:**
- **Host:** Contabo VPS (Ubuntu 24.04), South Africa region
- **Access:** Cloudflare Tunnel (no direct port exposure)
- **Orchestration:** Docker Swarm
- **Stack:** FastAPI (Python 3.11), React/TypeScript, Supabase (PostgreSQL), InfluxDB

## Scanning Schedule

| Scan Type | Frequency | Schedule | Script |
|-----------|-----------|----------|--------|
| External  | Monthly   | 1st Monday at 02:00 SAST | `external-scan.sh` |
| Internal  | Quarterly | 1st Monday of Jan/Apr/Jul/Oct at 03:00 SAST | `internal-scan.sh` |
| CI/CD     | Every PR  | Automated in GitHub Actions | See `.github/workflows/` |

## Scripts

### External Scan (`external-scan.sh`)

Scans Internet-facing endpoints through Cloudflare. Five check categories:

1. **TLS/SSL Validation** - Certificate expiry, protocol versions, cipher suites
2. **HTTP Security Headers** - HSTS, CSP, X-Frame-Options, X-Content-Type-Options, etc.
3. **Open Port Scan** - VPS public IP for accidentally exposed ports (should be none via Tunnel)
4. **API Endpoint Testing** - Information disclosure, CORS, sensitive endpoints, Swagger access
5. **DNS Configuration** - SPF, DKIM, DMARC, CAA records, dangling CNAMEs

**Prerequisites:**
```bash
# Install required tools
sudo apt install nmap dnsutils openssl curl
```

**Usage:**
```bash
# Basic scan (uses default domain)
./external-scan.sh

# Specify domain and VPS IP
./external-scan.sh --domain sentinel.bfrancois.com --vps-ip 123.45.67.89

# Show help
./external-scan.sh --help
```

**Environment variables (optional):**
```bash
SENTINEL_DOMAIN=sentinel.bfrancois.com   # Override SENTINEL domain
AIMTHELAW_DOMAIN=aimthelaw.bfrancois.com # Override AimTheLaw domain
VPS_PUBLIC_IP=123.45.67.89              # VPS IP for port scanning
```

### Internal Scan (`internal-scan.sh`)

Comprehensive internal infrastructure assessment. Seven check categories:

1. **Host Security Audit (Lynis)** - System hardening index and recommendations
2. **Docker Security** - Container configuration, image vulnerabilities (Trivy), privileges
3. **OS Patch Status** - Pending security updates
4. **User & Access Audit** - Accounts, SSH keys, sudo access, stale accounts
5. **Service & Process Audit** - Listening services, unexpected processes
6. **File Permission Audit** - Sensitive file permissions (.env, SSH keys, Docker socket)
7. **Database Security** - Connection encryption, default credentials, privilege checks

**Prerequisites:**
```bash
# Install required tools
sudo apt install lynis
# Trivy should already be installed from CI/CD setup (Plan 63-03)
```

**Usage:**
```bash
# Run as root or with sudo (required for Lynis and service checks)
sudo ./internal-scan.sh

# Show help
sudo ./internal-scan.sh --help
```

## Report Storage

Reports are saved to `/opt/bms-intelligence/security-reports/`:

```
security-reports/
  external/
    2026-02-03/          # Date-stamped directory per scan
      scan-summary.txt   # Overall summary with findings count
      tls-report.txt     # TLS/SSL check results
      headers-report.txt # HTTP security headers
      port-scan-report.txt
      api-scan-report.txt
      dns-report.txt
  internal/
    2026-01-06/          # Date-stamped directory per scan
      scan-summary.txt
      lynis-report.dat
      docker-security-report.txt
      patch-status-report.txt
      access-audit-report.txt
      service-audit-report.txt
      permissions-report.txt
      database-security-report.txt
```

**Retention:** Keep 12 months of scan reports. Reports older than 12 months may be archived or deleted.

## Cron Configuration

Add the following to `/etc/crontab` or the root user's crontab (`sudo crontab -e`):

```cron
# =============================================================================
# SENTINEL Vulnerability Scanning Schedule
# =============================================================================

# Monthly external scan - 1st Monday at 02:00 SAST (00:00 UTC)
0 0 * * 1 root [ $(date +\%d) -le 7 ] && /opt/bms-intelligence/infrastructure/scanning/external-scan.sh --vps-ip <VPS_IP> >> /var/log/sentinel-external-scan.log 2>&1

# Quarterly internal scan - 1st Monday of Jan/Apr/Jul/Oct at 03:00 SAST (01:00 UTC)
0 1 * * 1 root [ $(date +\%d) -le 7 ] && echo "1 4 7 10" | grep -q $(date +\%-m) && /opt/bms-intelligence/infrastructure/scanning/internal-scan.sh >> /var/log/sentinel-internal-scan.log 2>&1

# =============================================================================
```

**Cron logic:**
- `[ $(date +\%d) -le 7 ]` - Only runs if today is the 1st-7th (ensures 1st Monday)
- `echo "1 4 7 10" | grep -q $(date +\%-m)` - Only runs in Jan, Apr, Jul, Oct (quarterly)

## Interpreting Results

### Severity Levels

| Severity | SLA | Examples |
|----------|-----|---------|
| **Critical** | 7 days | Expired TLS cert, CORS reflects arbitrary origins, RCE vulnerability |
| **High** | 14 days | Missing HSTS, deprecated TLS protocols, exposed database ports |
| **Medium** | 30 days | Missing CSP header, publicly accessible API docs, no SPF record |
| **Low** | 90 days | Information disclosure headers, missing CAA records |

### Expected Results (Healthy System)

**External scan should show:**
- TLS certificates valid with 30+ days remaining
- All security headers present (HSTS, CSP, X-Frame-Options)
- No ports exposed directly (everything via Cloudflare Tunnel)
- /docs and /openapi.json restricted or disabled in production
- CORS restricted to allowed origins only
- SPF, DKIM, DMARC records present

**Internal scan should show:**
- Lynis hardening index > 70
- No Docker containers running as root (except where required)
- All OS security patches applied
- No accounts without passwords or SSH keys
- No SUID binaries outside expected set
- All .env files with 600 permissions
- Database connections using SSL

## Escalation Process

1. **Scan completes** - Review findings in scan summary
2. **Log findings** - Update `remediation-tracker.md` with new vulnerabilities
3. **Assign ownership** - Each finding assigned to responsible team member
4. **SLA tracking** - Monitor remediation against SLA deadlines
5. **Escalation triggers:**
   - Critical: Escalate to management after 3 days if unresolved
   - High: Escalate after 7 days
   - Medium: Escalate after 21 days
   - Low: Review at next quarterly scan
6. **Verification** - Re-scan after remediation to confirm fix
7. **Close** - Mark as remediated in tracker with verification date

## Troubleshooting

### Common Issues

**nmap: command not found**
```bash
sudo apt install nmap
```

**dig: command not found**
```bash
sudo apt install dnsutils
```

**Lynis: command not found**
```bash
sudo apt install lynis
```

**Trivy: command not found**
See Plan 63-03 for Trivy installation or install directly:
```bash
curl -sfL https://raw.githubusercontent.com/aquasecurity/trivy/main/contrib/install.sh | sudo sh -s -- -b /usr/local/bin
```

**Permission denied on scan scripts**
```bash
chmod +x external-scan.sh internal-scan.sh
```

**Port scan times out**
The VPS may have firewall rules blocking nmap. This is actually a good result - it means ports are properly filtered.

## Related Documentation

- [Vulnerability Management Process](../../docs/08-security/vulnerability-management.md)
- [Remediation Tracker](./remediation-tracker.md)
- [Application Security Pipeline](../../docs/08-security/application-security-pipeline.md) (Plan 63-03)
- [Access Control Implementation](../../docs/08-security/access-control-implementation.md) (Plan 63-04)

## FSR Compliance

This scanning infrastructure addresses **FSR domain 4.10 (Vulnerability Management)**:

| Requirement | Implementation |
|-------------|---------------|
| Regular vulnerability scanning | Monthly external + quarterly internal |
| Remediation SLAs | Critical 7d, High 14d, Medium 30d, Low 90d |
| Scanning tools | nmap, Lynis, Trivy, openssl, curl |
| Report retention | 12 months of scan reports |
| Escalation process | Defined with time-based triggers |
| Risk acceptance | Documented in remediation tracker |
