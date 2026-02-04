# SENTINEL Intrusion Detection Architecture

**Version:** 1.0
**Last Updated:** 2026-02-04
**FSR Domains:** 4.13 Incident Detection (HIGH gap), 4.9 Application Security (HIGH gap)

## Overview

SENTINEL employs a defence-in-depth intrusion detection strategy combining host-based IDS (Wazuh), network-based IPS (Cloudflare WAF), application-level security logging, and automated response. This architecture protects the Contabo VPS hosting both SENTINEL and AimTheLaw.

## Architecture Diagram

```
                          Internet
                              |
                    +---------v---------+
                    |  Cloudflare Edge   |
                    |  - WAF (9 rules)   |
                    |  - DDoS Protection  |
                    |  - Bot Management   |
                    |  - Rate Limiting    |
                    |  - Geo Filtering    |
                    +---------+---------+
                              |
                    Cloudflare Tunnel (encrypted)
                              |
              +---------------v---------------+
              |    Contabo VPS (Ubuntu 24.04)  |
              |                               |
              |  +----------+  +-----------+  |
              |  | Fail2Ban |  |  Wazuh    |  |
              |  | (iptable |  |  Agent    |  |
              |  |  rules)  |  |  (FIM,    |  |
              |  +----+-----+  |  rootkit, |  |
              |       |        |  log      |  |
              |       |        |  analysis)|  |
              |       |        +-----+-----+  |
              |       |              |         |
              |  +----v--------------v------+  |
              |  |     Docker Containers     |  |
              |  |                           |  |
              |  |  +--------+ +----------+ |  |
              |  |  |SENTINEL| |AimTheLaw | |  |
              |  |  |Backend | |Backend   | |  |
              |  |  |Security| |Security  | |  |
              |  |  |Logging | |Logging   | |  |
              |  |  +---+----+ +----+-----+ |  |
              |  |      |           |        |  |
              |  |  +---v-----------v-----+  |  |
              |  |  |  Promtail           |  |  |
              |  |  |  (log collector)    |  |  |
              |  |  +--------+------------+  |  |
              |  |           |               |  |
              |  |  +--------v-----------+   |  |
              |  |  |  Grafana Loki      |   |  |
              |  |  |  (log storage,     |   |  |
              |  |  |   SIEM alerting)   |   |  |
              |  |  +--------------------+   |  |
              |  +---------------------------+  |
              +---------------------------------+
```

## Host-Based IDS: Wazuh Agent

### Capabilities

| Capability | Description | Frequency |
|------------|-------------|-----------|
| **File Integrity Monitoring (FIM)** | Detect changes to critical system and application files | Every 10 minutes |
| **Log Analysis** | Parse auth.log, syslog, Docker logs for security events | Real-time |
| **Rootkit Detection** | Scan for kernel rootkits, hidden processes, trojan binaries | Every 12 hours |
| **Active Response** | Automated IP blocking via firewall-drop on detected attacks | Real-time |

### Configuration

- **Docker image:** `wazuh/wazuh-agent:4.9.0`
- **Network mode:** Host (full network visibility for active response)
- **Persistence:** Named volume `wazuh-data` for alert history
- **Mode:** Standalone (local analysis without central manager)

### File Integrity Monitoring

The following files are monitored for unauthorized changes:

| File/Directory | Why Monitored | Alert Level |
|----------------|---------------|-------------|
| `/etc/passwd`, `/etc/shadow` | Account manipulation detection | CRITICAL (12) |
| `/etc/ssh/sshd_config` | SSH configuration tampering | HIGH (10) |
| `/root/.ssh/authorized_keys` | Unauthorized SSH key injection | HIGH (10) |
| `/etc/docker/daemon.json` | Docker configuration changes | HIGH (8) |
| `/opt/bms-intelligence/backend/.env` | Credential/API key changes | HIGH (10) |
| `/opt/bms-intelligence/docker-compose.yml` | Infrastructure configuration | MEDIUM (8) |
| `/opt/aimthelaw/.env` | AimTheLaw credential changes | HIGH (10) |
| `/etc/crontab`, `/var/spool/cron` | Scheduled task manipulation | HIGH (10) |
| `/usr/bin`, `/usr/sbin`, `/sbin` | Trojan binary replacement | MEDIUM (6) |

### Custom Rules (local_rules.xml)

| Rule ID | Description | Level | Trigger |
|---------|-------------|-------|---------|
| 100100 | Docker container started | 8 | Container lifecycle event |
| 100101 | Docker container stopped unexpectedly | 10 | Service disruption detection |
| 100102 | New Docker image pulled | 6 | Supply chain monitoring |
| 100110 | System credential file modified | 12 | /etc/passwd or /etc/shadow change |
| 100111 | SSH key added or modified | 10 | authorized_keys change |
| 100112 | SENTINEL .env modified | 10 | Credential change detection |
| 100113 | AimTheLaw .env modified | 10 | Credential change detection |
| 100114 | docker-compose.yml modified | 8 | Infrastructure change |
| 100115 | Crontab modified | 10 | Scheduled task change |
| 100120 | BMS device control action | 8 | Audit trail event |
| 100121 | Safety system override | 12 | Immediate review required |
| 100122 | Multiple auth failures (5 in 5min) | 10 | Brute force detection |
| 100123 | Suspicious path pattern | 12 | Injection attempt |
| 100130 | New user account created | 10 | Authorization verification |
| 100131 | Sudo escalation to root | 8 | Privilege escalation audit |
| 100132 | SSH login from new IP | 6 | New access source detection |

### Active Response Procedures

When Wazuh detects an attack, automated responses are triggered:

1. **SSH Brute Force (Rule 5712):**
   - Trigger: 5 failed SSH login attempts
   - Action: `firewall-drop` (iptables block)
   - Duration: 1 hour initial, escalating (60min, 120min, 720min, 1440min)

2. **Repeated Offenders:**
   - Fail2Ban escalation: 50 total violations across all jails triggers 24-hour ban
   - SSH-aggressive jail: Single attempt after first ban triggers 24-hour ban

## Network-Based IPS: Cloudflare WAF

### Managed Services

Cloudflare provides network-level protection as a managed service:

- **DDoS Protection:** Automatic L3/L4/L7 DDoS mitigation
- **WAF:** 9 custom rules + OWASP managed ruleset
- **Bot Management:** Challenge automated scanners
- **Rate Limiting:** 4-tier endpoint-specific limits
- **SSL/TLS:** Full encryption via Cloudflare Tunnel

### WAF Rules Summary

| Rule | Protection | Action | Target |
|------|-----------|--------|--------|
| OWASP Core Rule Set | Top 10 vulnerabilities | Challenge | All traffic |
| SQL Injection | Database manipulation | Block | Query params, body |
| XSS Protection | Script injection | Block | URI, body |
| Path Traversal | File system access | Block | URI patterns |
| AI Chat Rate Limit | Cost abuse | Block | 30 req/min |
| MCP Tool Rate Limit | BMS tool safety | Block | 60 req/min |
| Device Control Rate Limit | Safety-critical | Block | 20 req/min |
| General API Rate Limit | General abuse | Challenge | 120 req/min |
| Bot Protection | Automated scanners | Challenge | Non-verified bots |
| Geographic Access | Regional control | Challenge | Non-ZA traffic |
| Request Size | DoS prevention | Block | >10MB bodies |
| Header Validation | Content confusion | Block | Missing Content-Type |

### Rate Limiting Rationale

| Endpoint | Limit | Why |
|----------|-------|-----|
| `/api/chat` | 30/min | Claude API costs ~R0.17/query. Prevents cost runaway. |
| `/api/mcp/simbiot/call` | 60/min | BMS tool calls affect building systems. Moderate limit. |
| `/api/devices/*/control` | 20/min | Safety-critical: changes temperature setpoints, lighting. Strict limit. |
| `/api/*` general | 120/min | Normal dashboard usage. Challenge (not block) for legitimate users. |

## Application-Level Security Logging

### SecurityLoggingMiddleware (Phase 63-01)

The SENTINEL backend includes structured security logging middleware that captures:

- **AUTH_FAILURE:** Failed authentication (401 responses)
- **ACCESS_DENIED:** Forbidden access (403 responses)
- **SUSPICIOUS_USER_AGENT:** Known scanner/tool user agents
- **SUSPICIOUS_PATH:** SQL injection, path traversal, XSS patterns
- **BMS_CONTROL_ACTION:** Device setpoint changes, approvals
- **SAFETY_OVERRIDE:** Safety system override attempts (CRITICAL)
- **SERVER_ERROR:** 5xx responses indicating potential exploitation

Events are output as structured JSON, collected by Promtail, and shipped to Grafana Loki.

### SIEM Alerting Rules (Phase 63-01)

Six Grafana Loki alerting rules provide real-time notification:

1. **Auth Failure Spike:** >5 failures in 5 minutes
2. **Safety Override Detected:** Any safety override attempt
3. **Suspicious Path Pattern:** SQL injection, XSS, traversal
4. **Server Error Spike:** >10 errors in 5 minutes
5. **BMS Control After Hours:** Control actions outside 06:00-22:00 SAST
6. **Brute Force Detection:** >10 failures from single IP in 10 minutes

## Brute Force Protection: Fail2Ban

### Configuration (Ported from AimTheLaw)

| Jail | Max Attempts | Window | Ban Duration | Purpose |
|------|-------------|--------|--------------|---------|
| `sshd` | 3 | 10 min | 1 hour | SSH login protection |
| `sshd-aggressive` | 1 | 24 hours | 24 hours | Repeat SSH offenders |
| `docker-auth` | 5 | 10 min | 30 min | Docker auth monitoring |
| `sentinel-api` | 10 | 5 min | 15 min | API rate limit enforcement |
| `sentinel-control` | 5 | 10 min | 1 hour | Device control abuse |
| `recidive` | 50 | 24 hours | 24 hours | Cross-jail escalation |

### Escalation Flow

```
First Violation:    30 min ban (default)
SSH Violation:      1 hour ban
Repeat SSH:         24 hour ban (sshd-aggressive)
50 Total Violations: 24 hour ban across ALL jails (recidive)
```

## Monitoring and Review

### Daily Review Checklist

- [ ] Check Grafana Loki alert dashboard for triggered alerts
- [ ] Review Cloudflare Security Events for blocked/challenged requests
- [ ] Check Fail2Ban ban list: `fail2ban-client status`
- [ ] Review Wazuh alerts: `/var/ossec/logs/alerts/alerts.json`
- [ ] Verify FIM baseline integrity

### Weekly Review

- [ ] Review rate limiting metrics and adjust thresholds
- [ ] Analyse geographic access patterns
- [ ] Review new Docker images pulled (supply chain)
- [ ] Check for false positives in WAF rules

### Monthly Review

- [ ] Update OWASP ruleset sensitivity
- [ ] Review and update geographic allow-list
- [ ] Audit SSH key inventory
- [ ] Review Fail2Ban escalation thresholds

## Incident Escalation Workflow

```
Detection                Alert                  Review                 Response
   |                       |                      |                      |
   v                       v                      v                      v
Wazuh/Cloudflare    Loki Alert Rule     FM Security Team        Remediation
detects anomaly  --> fires notification --> investigates    --> takes action
                    (Grafana alert)      (within 1 hour)     (block/patch/report)
                                              |
                                              v
                                        Document in
                                        incident log
```

### Severity Response Times

| Severity | Example | Response Time | Action |
|----------|---------|---------------|--------|
| **CRITICAL** | Safety override, credential theft | Immediate | Block source, investigate, report |
| **HIGH** | Brute force, injection attempt | 1 hour | Review logs, verify no breach |
| **MEDIUM** | Suspicious user agent, auth failure | 4 hours | Monitor, add to watchlist |
| **LOW** | Unusual access pattern | Next business day | Review in weekly report |

## FSR Evidence Mapping

| FSR Control | Implementation | Evidence |
|-------------|----------------|----------|
| 4.9.1 WAF for internet-facing apps | 9 Cloudflare WAF rules | `infrastructure/cloudflare/waf-rules.json` |
| 4.9.2 Input validation | Header validation, size limits, injection blocking | WAF rules 002-004, 008-009 |
| 4.13.1 Host-based IDS | Wazuh agent with FIM, log analysis, rootkit detection | `infrastructure/wazuh/ossec.conf` |
| 4.13.2 Network-based IPS | Cloudflare WAF + DDoS protection | Cloudflare dashboard |
| 4.13.3 Active response | Fail2Ban + Wazuh firewall-drop | `infrastructure/fail2ban/jail.local` |
| 4.13.4 Incident detection | SIEM alerting via Grafana Loki | `infrastructure/grafana/siem-alerting-rules.yaml` |
| 4.13.5 Log retention | 90-day retention in Loki | `infrastructure/loki/loki-config.yaml` |

## Key Files

| File | Purpose |
|------|---------|
| `docker-compose.yml` | Wazuh agent and Fail2Ban Docker services |
| `infrastructure/wazuh/ossec.conf` | Wazuh agent configuration (FIM, log analysis, rootkit, active response) |
| `infrastructure/wazuh/local_rules.xml` | 15 custom detection rules for SENTINEL |
| `infrastructure/fail2ban/jail.local` | 6 jails with escalation (ported from AimTheLaw) |
| `infrastructure/cloudflare/waf-rules.json` | 9 WAF rules for Cloudflare |
| `infrastructure/cloudflare/README.md` | WAF application instructions |
| `backend/app/middleware/security_logging.py` | Application-level security event logging |
| `infrastructure/grafana/siem-alerting-rules.yaml` | 6 SIEM alerting rules |

---
*SENTINEL BMS Intelligence Platform - Security Documentation*
*Phase 63-02: Intrusion Detection and WAF Configuration*
