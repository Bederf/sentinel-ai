# SENTINEL Incident Response Process

**Document ID:** SENTINEL-IRP-002
**Version:** 1.0
**Effective Date:** 2026-02-04
**Review Cadence:** Annual, or after any P1 incident
**Classification:** Internal — FSR Supplier Confidential
**FSR Domains:** 4.13 (Information Security Incident Detection), 4.14 (Information Security Incident Management)
**Alignment:** NIST SP 800-61 Rev. 2 (Computer Security Incident Handling Guide)

---

## 1. Purpose

This document provides step-by-step operational procedures for handling security incidents across the full incident lifecycle. It operationalises the Incident Response Policy (`docs/08-security/incident-response-policy.md`) with SENTINEL-specific commands, tools, and workflows.

All IRT members must be familiar with these procedures and able to execute them under pressure. This document is designed for use during live incidents — procedures are written in actionable, sequential format.

## 2. Incident Lifecycle Overview

SENTINEL's incident response process follows the NIST SP 800-61 framework, adapted for the SENTINEL BMS platform:

```
┌─────────────┐    ┌───────────────────┐    ┌──────────────┐
│   Phase 1   │    │      Phase 2      │    │   Phase 3    │
│ Preparation │───▶│ Detection &       │───▶│ Containment  │
│             │    │ Analysis          │    │              │
└─────────────┘    └───────────────────┘    └──────┬───────┘
                                                    │
┌─────────────┐    ┌───────────────────┐    ┌──────▼───────┐
│   Phase 6   │    │      Phase 5      │    │   Phase 4    │
│ Post-       │◀───│    Recovery       │◀───│ Eradication  │
│ Incident    │    │                   │    │              │
└─────────────┘    └───────────────────┘    └──────────────┘
```

---

## Phase 1: Preparation

**Objective:** Maintain readiness so the IRT can respond effectively when incidents occur.

### 1.1 Incident Response Toolkit

The following tools and resources must be maintained and accessible to all IRT members:

| Category | Tool/Resource | Location | Verification |
|----------|--------------|----------|-------------|
| Log Analysis | Grafana Loki dashboard | `https://[grafana-url]:3000` | Login and query recent logs |
| SIEM Alerts | Grafana alerting panel | `https://[grafana-url]:3000/alerting/list` | Confirm 6 alert rules active |
| Host IDS | Wazuh agent dashboard | Wazuh manager console | Confirm agent connected |
| WAF | Cloudflare dashboard | `https://dash.cloudflare.com` | Confirm 9 WAF rules active |
| Brute Force | Fail2Ban status | `sudo fail2ban-client status` | Confirm jails active |
| Container Mgmt | Docker CLI | `docker ps`, `docker logs` | Confirm containers running |
| Backup Access | DR runbook | `infrastructure/bcpdr/dr-runbook.md` | Review annually |
| Contact List | IRT contact sheet | Secured internal document | Review quarterly |
| Incident Register | Incident log | Secured internal document | Verify accessible |
| Communication | Notification templates | Section 7 of this document | Review annually |

### 1.2 Contact List Maintenance

Maintain current contact details for:

- **IRT Members:** Primary and secondary phone/email for Incident Manager, Technical Lead, Communications Lead
- **FSR Contacts:** FSR Security Operations team, FSR account manager, FSR CISO office
- **POPIA Information Regulator:** Notification submission portal and email
- **Third-Party Vendors:** Contabo support, Cloudflare support, Anthropic security team
- **Law Enforcement:** SAPS Cybercrime unit (if required for criminal investigation)

**Review frequency:** Quarterly, and immediately upon personnel changes.

### 1.3 Detection System Verification

Verify detection systems operational on a monthly basis:

```bash
# Verify Promtail is shipping logs to Loki
curl -s http://localhost:3100/ready | grep ready

# Verify Grafana alerting rules are active
curl -s http://localhost:3000/api/v1/provisioning/alert-rules | jq '.[] | .title'

# Verify Wazuh agent is connected
sudo /var/ossec/bin/agent_control -l

# Verify Fail2Ban jails are active
sudo fail2ban-client status

# Verify Docker containers running
docker ps --format "table {{.Names}}\t{{.Status}}"

# Verify SENTINEL security audit logging
curl -s http://localhost:9095/api/health | jq '.status'
```

### 1.4 Tabletop Exercises

- **Frequency:** Annual minimum, or after significant infrastructure changes
- **Scenarios:** Rotate through P1, P2, and P3 scenarios
- **Participants:** All IRT members
- **Output:** Exercise report with findings and improvement actions
- **Reference scenarios:** BCP/DR test procedures at `infrastructure/bcpdr/bcp-test-plan.md`

---

## Phase 2: Detection and Analysis

**Objective:** Identify security events, determine if they constitute incidents, classify severity, and begin investigation.

### 2.1 Detection Sources

Security events may be detected from the following sources:

| Source | Alert Mechanism | Typical Severity |
|--------|----------------|-----------------|
| **Grafana Loki SIEM rules** | Automated alert (6 rules) | P2-P4 |
| **Wazuh IDS alerts** | FIM changes, rootkit detection, active response triggers | P1-P3 |
| **Cloudflare WAF** | Block events, rate limit triggers, bot challenges | P3-P4 |
| **Fail2Ban** | SSH ban events, API brute force bans | P3-P4 |
| **SENTINEL audit logs** | Unusual device control patterns, safety interlock triggers | P2-P3 |
| **User/operator reports** | Direct report from FM operator or building occupant | P2-P4 |
| **Third-party notifications** | Anthropic, Cloudflare, or Contabo security advisories | P2-P3 |
| **Vulnerability scans** | Scheduled or ad-hoc security scanning results | P3-P4 |

### 2.2 SIEM Alert Rule Reference

The following Grafana Loki SIEM rules generate automated alerts:

| Rule ID | Rule Name | Detection Logic | Default Action |
|---------|-----------|----------------|----------------|
| SIEM-001 | Brute Force SSH | 5+ SSH auth failures in 5 minutes from same source | Alert + auto-ban via Fail2Ban |
| SIEM-002 | Failed API Auth | 10+ API auth failures in 5 minutes | Alert + review access logs |
| SIEM-003 | Privilege Escalation | sudo/su by non-authorised user | Alert + immediate investigation |
| SIEM-004 | BMS Write Anomaly | Device control writes outside normal hours/frequency | Alert + review audit trail |
| SIEM-005 | After-Hours Access | System access outside defined business hours | Alert + verify authorisation |
| SIEM-006 | Data Exfiltration | Large data transfer volume threshold exceeded | Alert + immediate investigation |

**Alert configuration:** `infrastructure/grafana/provisioning/alerting/security-alerts.yaml`

### 2.3 Triage Procedure

Upon receiving a security event alert or report, the responding IRT member executes the following triage:

**Step 1: Verify the alert is genuine (not a false positive)**

```bash
# Check Loki logs for the triggering event
# Replace {query} with relevant LogQL query
curl -G "http://localhost:3100/loki/api/v1/query_range" \
  --data-urlencode 'query={job="sentinel-backend"} |= "error"' \
  --data-urlencode 'start=1h' | jq '.data.result'

# Check Wazuh alerts
sudo cat /var/ossec/logs/alerts/alerts.json | tail -20 | jq '.'

# Check Fail2Ban recent bans
sudo fail2ban-client status sshd
sudo fail2ban-client status sentinel-api

# Check Cloudflare WAF events (via dashboard or API)
# Review recent WAF events in Cloudflare dashboard > Security > Events
```

**Step 2: Classify severity (P1-P4)**

Apply the severity classification criteria from the Incident Response Policy (Section 4). Consider:
- Is there confirmed data exposure or compromise?
- Are FSR systems or data affected?
- Is BMS device control integrity compromised?
- What is the scope of impact (single system vs. multiple)?

**Step 3: Assign incident reference number**

Format: `INC-YYYY-NNN`

Example: `INC-2026-001` (first incident of 2026)

Sequential numbering, never reuse. Increment NNN for each new incident within the year.

**Step 4: Create incident register entry**

Record the following in the incident register:
- Incident reference number
- Date/time detected (ISO 8601 with timezone)
- Detection source
- Initial severity classification
- Brief description
- Assigned IRT member(s)
- Initial status: OPEN

**Step 5: Notify Incident Manager if P1/P2**

- P1: Immediate notification via phone call, followed by message
- P2: Notification via message within 30 minutes
- P3: Notification via email within 2 hours
- P4: Logged in register, reviewed at next monthly review

### 2.4 Evidence Collection

Preserve evidence before any containment actions that might alter or destroy forensic data:

**Log preservation:**
```bash
# Mark Loki retention-hold for the incident timeframe
# Export relevant logs to secure storage
curl -G "http://localhost:3100/loki/api/v1/query_range" \
  --data-urlencode 'query={job="sentinel-backend"}' \
  --data-urlencode "start=$(date -d '24 hours ago' -Iseconds)" \
  --data-urlencode "end=$(date -Iseconds)" \
  > /secure/evidence/INC-YYYY-NNN/loki-export-$(date +%Y%m%d%H%M%S).json

# Export Wazuh alerts for the incident period
sudo cp /var/ossec/logs/alerts/alerts.json \
  /secure/evidence/INC-YYYY-NNN/wazuh-alerts-$(date +%Y%m%d%H%M%S).json

# Export Fail2Ban logs
sudo cp /var/log/fail2ban.log \
  /secure/evidence/INC-YYYY-NNN/fail2ban-$(date +%Y%m%d%H%M%S).log
```

**Cloudflare evidence:**
- Screenshot Cloudflare Security > Events showing relevant WAF blocks
- Export Cloudflare Analytics for the incident period
- Save to `/secure/evidence/INC-YYYY-NNN/`

**Docker container state:**
```bash
# Capture running container state
docker ps -a > /secure/evidence/INC-YYYY-NNN/docker-state-$(date +%Y%m%d%H%M%S).txt

# Inspect affected container
docker inspect [container_name] > /secure/evidence/INC-YYYY-NNN/docker-inspect-$(date +%Y%m%d%H%M%S).json

# Capture container filesystem diff (shows modified files)
docker diff [container_name] > /secure/evidence/INC-YYYY-NNN/docker-diff-$(date +%Y%m%d%H%M%S).txt
```

**Timeline documentation:**
- Maintain a chronological timeline of events in the incident register
- Record all actions taken with timestamps and operator identity
- Note any decisions made and their rationale

---

## Phase 3: Containment

**Objective:** Limit the impact of the incident and prevent further damage.

### 3.1 Short-Term Containment (Stop the Bleeding)

Execute the appropriate containment actions based on incident type:

**Isolate affected container(s):**
```bash
# Stop affected container
docker stop [container_name]

# Disconnect container from network (preserves filesystem for forensics)
docker network disconnect [network_name] [container_name]
```

**Block attacking IP(s):**
```bash
# Block via Fail2Ban (immediate)
sudo fail2ban-client set [jail_name] banip [attacker_ip]

# Block via Cloudflare WAF (persistent)
# Add IP to Cloudflare > Security > WAF > Tools > IP Access Rules > Block

# Block via iptables (if Fail2Ban/Cloudflare not sufficient)
sudo iptables -A INPUT -s [attacker_ip] -j DROP
```

**Revoke compromised credentials:**
```bash
# Rotate Anthropic API key
# 1. Generate new key at console.anthropic.com
# 2. Update backend/.env with new ANTHROPIC_API_KEY
# 3. Restart backend container
docker restart sentinel-backend

# Rotate Supabase keys
# 1. Regenerate keys in Supabase dashboard > Settings > API
# 2. Update backend/.env with new SUPABASE_KEY, SUPABASE_SERVICE_ROLE_KEY
# 3. Restart backend container

# Invalidate all active sessions
# Restart backend to clear in-memory session state
docker restart sentinel-backend
```

**Activate BMS safety lockdown (if device control compromised):**
```bash
# The safety engine automatically blocks device control when triggered
# Verify safety lockdown is active
curl -s http://localhost:9095/api/safety/status | jq '.status'

# If manual lockdown required, stop device control service
# This prevents ALL device write commands
docker exec sentinel-backend python -c "
from app.services.device_abstraction import device_manager
if device_manager:
    print('Device manager active - control suspended via safety engine')
"
```

### 3.2 Long-Term Containment (Stabilise)

After immediate bleeding is stopped:

**Deploy patched/clean containers:**
```bash
# Rebuild from clean source
docker compose build --no-cache [service_name]

# Deploy clean container
docker compose up -d [service_name]

# Verify clean deployment
docker logs --tail 50 [service_name]
```

**Rotate all potentially compromised credentials:**
- All API keys (Anthropic, Supabase, FSI Public API)
- All service account passwords
- SSH keys if host-level compromise suspected
- Database connection strings if database compromise suspected
- JWT signing secrets if authentication compromise suspected

**Enable enhanced monitoring:**
```bash
# Increase Loki log verbosity temporarily
# Set SENTINEL backend to DEBUG logging
docker exec sentinel-backend bash -c "export DEBUG=true && kill -HUP 1"

# Monitor security events in real-time
curl -G "http://localhost:3100/loki/api/v1/tail" \
  --data-urlencode 'query={job="sentinel-backend"} |= "security"'
```

**Preserve evidence before cleanup:**
- Ensure all evidence from Phase 2.4 is collected and secured
- Take full container filesystem snapshot if needed for forensics
- Document all containment actions taken with timestamps

---

## Phase 4: Eradication

**Objective:** Remove the threat, patch the vulnerability, and ensure no persistence mechanisms remain.

### 4.1 Root Cause Identification

- Review all evidence collected in Phase 2
- Analyse attack timeline to identify initial access vector
- Determine if vulnerability was known (check CVE databases) or zero-day
- Identify all systems accessed during the incident

### 4.2 Threat Removal

**Remove malware/backdoors if present:**
```bash
# Run Wazuh rootkit check
sudo /var/ossec/bin/rootcheck_control -l

# Check for suspicious processes
ps aux | grep -v "[[:space:]]root\|$(whoami)"

# Check for suspicious cron entries
crontab -l
ls -la /etc/cron.d/ /etc/cron.daily/ /etc/cron.hourly/

# Check for suspicious SSH authorised keys
cat ~/.ssh/authorized_keys
cat /root/.ssh/authorized_keys

# Check for modified system binaries
sudo debsums -c 2>/dev/null  # Debian/Ubuntu
```

### 4.3 Vulnerability Remediation

```bash
# Apply security patches
sudo apt update && sudo apt upgrade -y

# Update Docker images to latest patched versions
docker compose pull
docker compose up -d

# Update Python dependencies
cd /opt/bms-intelligence/backend
source venv/bin/activate
pip install --upgrade -r requirements.txt
```

### 4.4 Persistence Verification

**Verify no persistence mechanisms remain using Wazuh FIM baseline comparison:**
```bash
# Run Wazuh FIM integrity check
sudo /var/ossec/bin/syscheck_control -l

# Compare current file hashes against known-good baseline
# Review any files flagged as modified since pre-incident baseline

# Check Docker container integrity
docker inspect --format='{{.Image}}' [container_name]
# Compare image hash against known-good build
```

### 4.5 Detection Rule Updates

**Update WAF/Fail2Ban rules to prevent recurrence:**
```bash
# Add new Fail2Ban filter rule if attack pattern identified
sudo vi /etc/fail2ban/filter.d/sentinel-custom.conf
# Add detection regex for the specific attack pattern

# Update Cloudflare WAF rules via dashboard
# Add new custom rule blocking the identified attack pattern

# Update Grafana Loki SIEM rules if new detection logic needed
# Edit: infrastructure/grafana/provisioning/alerting/security-alerts.yaml
```

---

## Phase 5: Recovery

**Objective:** Restore systems to normal operation with confidence in their integrity.

### 5.1 Restore from Backups (if necessary)

Reference DR runbook: `infrastructure/bcpdr/dr-runbook.md`

```bash
# Restore database from backup
# Follow DR runbook Section X for Supabase/PostgreSQL restoration

# Restore application from clean Git repository
cd /opt/bms-intelligence
git fetch origin
git checkout main
git pull

# Rebuild all containers from clean source
docker compose build --no-cache
docker compose up -d
```

### 5.2 System Integrity Verification

Before returning systems to production:

```bash
# Verify all containers healthy
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

# Verify backend API responding
curl -s http://localhost:9095/api/health | jq '.'

# Verify database connectivity
curl -s http://localhost:9095/api/stats | jq '.status'

# Verify security logging operational
curl -s http://localhost:9095/api/audit/recent | jq '.count'

# Verify safety engine operational
curl -s http://localhost:9095/api/safety/status | jq '.'

# Verify detection systems active
sudo fail2ban-client status
sudo /var/ossec/bin/agent_control -l
curl -s http://localhost:3100/ready
```

### 5.3 Gradual Restoration

1. **Enable read-only mode first** — allow monitoring and data collection, block control actions
2. **Enable limited control access** — restore device control for trusted operators only
3. **Enable full access** — restore normal operations after 24-hour monitoring period
4. **Monitor for recurrence** — enhanced monitoring for 7 days post-recovery

### 5.4 Business Process Verification

- Confirm SENTINEL API endpoints responding correctly
- Confirm building telemetry data flowing (InfluxDB ingestion)
- Confirm AI chat operational (Claude API connectivity)
- Confirm BMS device control operational (safety interlocks active)
- Confirm integration sources active (MRI Evolution, EskomSePush)
- Confirm all Grafana dashboards displaying current data

---

## Phase 6: Post-Incident

**Objective:** Learn from the incident and improve defences.

### 6.1 Lessons Learned Review

**Timeline:** Within 5 business days of incident closure for P1/P2 incidents.

**Participants:** All IRT members who participated in the incident response.

**Review Agenda:**

1. **Timeline reconstruction:** Minute-by-minute timeline from detection to closure
2. **What worked:** Detection, containment, and recovery actions that were effective
3. **What failed:** Gaps in detection, delays in response, communication breakdowns
4. **Root cause analysis:** Why did this happen? What vulnerability was exploited?
5. **Improvement recommendations:** Specific, actionable items with owners and deadlines
6. **Detection rule updates:** New or modified rules to detect similar attacks
7. **Process updates:** Changes to this document or the incident response policy
8. **Training needs:** Skill gaps identified during response

### 6.2 Incident Register Update

Update the incident register with final details:
- Final severity classification (may differ from initial)
- Confirmed root cause
- Full timeline of events
- All containment and remediation actions taken
- Lessons learned summary
- FSR/POPIA notification status and dates
- Status: CLOSED (with closure date)

### 6.3 Documentation and Rule Updates

- Update detection rules (Grafana Loki SIEM, Wazuh custom rules)
- Update WAF/Fail2Ban configurations
- Update safety interlock rules if BMS-related
- Update this process document if gaps identified
- Update the Incident Response Policy if scope changes needed
- Update security training content with anonymised case study

### 6.4 Improvement Action Tracking

All improvement actions are:
- Assigned to a specific owner
- Given a completion deadline
- Tracked in the incident register
- Reviewed at the next monthly security review
- Reported to FSR in the quarterly incident report (anonymised)

---

## 7. Incident Communication Templates

### 7.1 Initial FSR Notification Template

```
Subject: SENTINEL Security Incident Notification — [INC-YYYY-NNN]

To: FSR Security Operations
From: SENTINEL Communications Lead
Date: [Date]
Severity: [P1 Critical / P2 High]

INCIDENT SUMMARY
─────────────────────────────────────────

Incident Reference: INC-YYYY-NNN
Date/Time Detected: [ISO 8601 with timezone]
Severity: [P1/P2]
Status: [OPEN / CONTAINED]

DESCRIPTION
─────────────────────────────────────────

[2-3 sentence factual summary of what was detected and its potential impact]

SYSTEMS AFFECTED
─────────────────────────────────────────

[List of affected SENTINEL components and whether FSR data is potentially impacted]

CONTAINMENT ACTIONS TAKEN
─────────────────────────────────────────

1. [Action 1 with timestamp]
2. [Action 2 with timestamp]
3. [Action 3 with timestamp]

CURRENT STATUS
─────────────────────────────────────────

[Brief status of investigation and next steps]

NEXT STEPS
─────────────────────────────────────────

1. [Next investigation step]
2. [Expected timeline for detailed report]
3. [Planned communication cadence]

CONTACT
─────────────────────────────────────────

Incident Manager: [Name, Phone, Email]
Technical Lead: [Name, Phone, Email]

A detailed follow-up report will be provided within 72 hours.
```

### 7.2 POPIA Information Regulator Notification Template

```
NOTIFICATION OF SECURITY COMPROMISE
(Section 22 of the Protection of Personal Information Act 4 of 2013)

To: Information Regulator
From: [Responsible Party — SENTINEL Smart Building Solutions]
Date: [Date]

1. DESCRIPTION OF SECURITY COMPROMISE
─────────────────────────────────────────

[Describe the nature of the compromise, how it was discovered, and what happened]

2. PERSONAL INFORMATION AFFECTED
─────────────────────────────────────────

Categories of personal information compromised:
- [ ] Names
- [ ] Phone numbers
- [ ] Email addresses
- [ ] Location data (desk/zone identifiers)
- [ ] Occupancy patterns
- [ ] Other: [specify]

3. DATA SUBJECTS AFFECTED
─────────────────────────────────────────

Estimated number of affected data subjects: [Number or range]
Categories: [Building occupants / Technicians / Other]

4. POSSIBLE CONSEQUENCES
─────────────────────────────────────────

[Describe potential consequences for data subjects — identity theft, unwanted contact, etc.]

5. MEASURES TAKEN TO ADDRESS COMPROMISE
─────────────────────────────────────────

[List containment and remediation actions taken]

6. RECOMMENDATIONS TO DATA SUBJECTS
─────────────────────────────────────────

[Recommended actions for affected data subjects to protect themselves]

7. CONTACT DETAILS
─────────────────────────────────────────

Information Officer: [Name]
Contact: [Phone, Email]
Reference: [INC-YYYY-NNN]
```

### 7.3 Data Subject Notification Template

```
Subject: Important Notice About Your Personal Information — SENTINEL BMS Platform

Dear [Data Subject / Building Occupant / Technician],

We are writing to inform you of a security incident that may have affected
your personal information processed by the SENTINEL Building Management
System.

WHAT HAPPENED
─────────────────────────────────────────

On [date], we detected [brief factual description of the incident].

WHAT INFORMATION WAS INVOLVED
─────────────────────────────────────────

The following categories of your personal information may have been affected:
- [List specific categories — phone number, name, location, etc.]

WHAT WE ARE DOING
─────────────────────────────────────────

We have taken the following steps to address this incident:
1. [Containment action]
2. [Remediation action]
3. [Prevention measure]

We have notified the Information Regulator as required by the Protection
of Personal Information Act (POPIA).

WHAT YOU CAN DO
─────────────────────────────────────────

We recommend the following precautionary steps:
- [Recommendation 1 — e.g., be alert for suspicious messages]
- [Recommendation 2 — e.g., verify any unexpected contact]

CONTACT US
─────────────────────────────────────────

If you have questions or concerns, please contact:
[Information Officer Name]
[Phone]
[Email]
Reference: [INC-YYYY-NNN]

We sincerely apologise for any inconvenience and are committed to
protecting your personal information.

[Signature]
[Organisation Name]
```

### 7.4 Internal Communication Template

```
Subject: [CONFIDENTIAL] Security Incident — [INC-YYYY-NNN] — [Severity]

To: IRT Members
From: Incident Manager
Date: [Date]
Classification: CONFIDENTIAL — Do not forward

STATUS UPDATE
─────────────────────────────────────────

Incident: INC-YYYY-NNN
Severity: [P1/P2/P3/P4]
Status: [OPEN / CONTAINED / ERADICATING / RECOVERING / CLOSED]
Last Updated: [Timestamp]

CURRENT SITUATION
─────────────────────────────────────────

[2-3 sentence summary of current state]

ACTIONS REQUIRED
─────────────────────────────────────────

[Assigned person]: [Specific action required]
[Assigned person]: [Specific action required]
Deadline: [Timestamp]

NEXT CHECK-IN
─────────────────────────────────────────

[Date/time for next status update or stand-up]

COMMUNICATION RULES
─────────────────────────────────────────

- All external communications go through Communications Lead
- Do not discuss incident details outside IRT
- Use incident reference number in all related communications
- Preserve all evidence — do not delete logs or modify systems without approval
```

---

## 8. Escalation Matrix

| Severity | Primary Handler | Escalation Path | FSR Notification | POPIA Trigger |
|----------|----------------|-----------------|-----------------|---------------|
| **P4 (Low)** | Technical Lead | Log in register, handle independently | No (quarterly summary) | No |
| **P3 (Medium)** | Technical Lead | Notify Incident Manager via email | No (monthly summary) | No |
| **P2 (High)** | Incident Manager leads | Notify Communications Lead, prepare FSR notification | Yes — within 24 hours | If PI involved |
| **P1 (Critical)** | All IRT mobilised | FSR notified within 24h, POPIA obligations triggered if PI involved | Yes — within 24 hours | Yes — within 72 hours |

### 8.1 Escalation Triggers

An incident should be escalated to a higher severity if:

- Scope expands beyond initial assessment
- Additional systems or data found to be affected
- Containment actions fail to stop the threat
- FSR data involvement confirmed (automatic P2 minimum)
- Personal information breach confirmed (triggers POPIA — automatic P2 minimum)
- BMS safety system compromise confirmed (automatic P1)
- Media or public attention (automatic P1)

### 8.2 De-escalation Criteria

An incident may be de-escalated if:

- Initial assessment proves less severe than initially classified
- Confirmed as false positive after thorough investigation
- Scope is narrower than initial estimate
- De-escalation is documented with rationale in incident register

---

## 9. Incident Response Checklists

### 9.1 P1 Critical Incident Checklist

```
□ Acknowledge within 15 minutes
□ Assign incident reference (INC-YYYY-NNN)
□ Create incident register entry
□ Mobilise all IRT members
□ Begin evidence collection (logs, container state, screenshots)
□ Execute short-term containment (isolate, block, revoke)
□ Activate BMS safety lockdown if device control affected
□ Draft initial FSR notification
□ Send FSR notification within 24 hours
□ Assess POPIA breach — if PI involved, begin 72-hour notification clock
□ Execute long-term containment (clean deploy, credential rotation)
□ Begin root cause analysis
□ Execute eradication (remove threat, patch vulnerability)
□ Verify eradication (FIM comparison, persistence check)
□ Execute recovery (restore, verify integrity, gradual restoration)
□ Conduct lessons learned review within 5 business days
□ Send detailed report to FSR within 72 hours
□ Send root cause analysis to FSR within 10 business days
□ Update incident register — status: CLOSED
□ Track and complete improvement actions
```

### 9.2 P2 High Incident Checklist

```
□ Acknowledge within 30 minutes
□ Assign incident reference (INC-YYYY-NNN)
□ Create incident register entry
□ Notify Incident Manager and Communications Lead
□ Begin evidence collection
□ Execute containment within 4 hours
□ Assess POPIA breach — if PI involved, begin 72-hour clock
□ Draft FSR notification
□ Send FSR notification within 24 hours
□ Execute eradication
□ Execute recovery
□ Conduct lessons learned review within 5 business days
□ Send detailed report to FSR within 72 hours
□ Update incident register — status: CLOSED
□ Track improvement actions
```

### 9.3 P3 Medium Incident Checklist

```
□ Acknowledge within 2 hours
□ Assign incident reference (INC-YYYY-NNN)
□ Create incident register entry
□ Notify Incident Manager
□ Investigate and assess
□ Contain within 24 hours
□ Document findings and resolution
□ Update detection rules if applicable
□ Include in monthly incident summary
□ Update incident register — status: CLOSED
```

### 9.4 P4 Low Incident Checklist

```
□ Acknowledge within 8 hours
□ Assign incident reference (INC-YYYY-NNN)
□ Create incident register entry
□ Assess within 5 business days
□ Document as false positive or minor event
□ Include in quarterly incident report
□ Update incident register — status: CLOSED
```

---

## 10. BMS-Specific Incident Procedures

### 10.1 Unauthorised Device Control

If an unauthorised device control command is detected:

1. **Immediate:** Safety engine blocks the command automatically (BLOCK severity)
2. **Verify:** Check audit log for operator identity and command details
   ```bash
   curl -s http://localhost:9095/api/audit/recent?limit=20 | jq '.entries[] | select(.action == "device_control")'
   ```
3. **Assess:** Is this a compromised credential, insider threat, or misconfiguration?
4. **Contain:** Revoke operator credentials, suspend device control access
5. **Notify:** P1 if safety-critical device targeted, P2 otherwise
6. **Recover:** Re-enable device control only after investigation complete

### 10.2 Safety Interlock Bypass Attempt

If a safety interlock bypass attempt is detected:

1. **Immediate:** Safety engine logs ALARM-level event
2. **Suspend:** All device control suspended pending investigation
3. **Investigate:** Review safety rules (`backend/app/data/safety_rules.json`) for modification
4. **Verify:** Confirm safety rules integrity against known-good baseline
5. **Restore:** Re-enable device control only after safety rules verified

### 10.3 Anomalous BMS Write Pattern

If SIEM rule SIEM-004 (BMS Write Anomaly) triggers:

1. **Review:** Check device control audit trail for the anomalous period
2. **Compare:** Compare write patterns against established baselines
3. **Investigate:** Identify the source of anomalous writes
4. **Assess:** Determine if writes caused operational impact
5. **Update:** Adjust SIEM thresholds if false positive, or escalate if genuine

---

## 11. Document Governance

### 11.1 Review Schedule

| Trigger | Action |
|---------|--------|
| Annual review | Full process review and tabletop exercise |
| After any P1 incident | Review and update within 15 business days |
| Significant infrastructure change | Review affected procedures |
| Detection system update | Update tool references and commands |
| Personnel change | Update contact lists and role assignments |

### 11.2 Version History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-02-04 | SENTINEL Security | Initial process creation |

---

**Related Documents:**
- [Incident Response Policy](./incident-response-policy.md) — Policy framework and severity definitions
- [Logging Architecture](./logging-architecture.md) — Centralised logging and SIEM alerting details
- [Intrusion Detection](./intrusion-detection.md) — IDS/WAF/Fail2Ban architecture details
- [BCP/DR Procedures](./bcp-dr-procedures.md) — Business continuity and disaster recovery runbooks
- [Access Control Implementation](./access-control-implementation.md) — Logical access controls

*SENTINEL BMS Intelligence Platform — Incident Response Process v1.0*
*Effective: 2026-02-04*
