---
title: "Cybercrimes Act Response Procedure"
type: "procedure"
status: "active"
version: "0.1.0"
created: "2026-05-19"
updated: "2026-05-19"
author: "SENTINEL Compliance Team"
tags: ["cybercrimes", "incident-response", "south-africa", "legal", "mandatory-reporting"]
domain: "compliance"
audience: "compliance, security, engineering, management"
complexity: "high"
estimated_read_time: 15
---

# Cybercrimes Act Response Procedure

## 1. Purpose and Legal Basis

This procedure defines how SENTINEL responds to cyber offences under the Cybercrimes Act 19 of 2020 (hereafter "the Act"). It satisfies the mandatory reporting obligation under section 3(3) and the "reasonable steps" defence under section 2.

**Reference:** Cybercrimes Act 19/2020, Sections 2, 3, 4, 5, 6, 9, 10, 11, 12.
**Review period:** Annually or after any incident.
**Owner:** Information Security Officer (ISO) / Managing Director.

> **Legal disclaimer:** This procedure is for internal governance use only. It does not constitute legal advice. Consult qualified legal counsel when an actual incident occurs.

---

## 2. Offence Categories Under the Act

The following offences are most relevant to SENTINEL operations:

| Section | Offence | SENTINEL Relevance |
|---------|---------|-------------------|
| **s3(1)(a)** | Unlawful access to computer system / data | Unauthorized intrusion into BMS gateway, Supabase, or API |
| **s3(1)(b)** | Unlawful access with intent to commit further offence | Compromised bridge used as pivot to attack other systems |
| **s3(2)** | Unlawful interception of data in transit | MQTT wiretap of site bridge traffic |
| **s4(1)(a)** | Unlawful acquisition of data | Exfiltration of building telemetry, credentials, or personal information |
| **s4(1)(b)** | Unlawful possession of data obtained unlawfully | Ransomware group holding building operational data |
| **s5** | Unlawful acts in respect of malicious communications | Phishing to obtain technician credentials or admin access |
| **s9** | Unlawful interference with data or computer system | Ransomware, DDoS, or manual override of BMS controls |
| **s10** | Cyber fraud | Social engineering resulting in fraudulent HVAC schedule change |
| **s11** | Common electronic fraud | Phishing, credential theft for financial gain |

**Priority classification:**
- **Category A (CRISA Reporting Required):** s3(1)(a-b), s4, s9, s10 — offences that threaten critical infrastructure or involve data exfiltration
- **Category B (Internal Log Only):** s3(2), s5, s11 — lesser offences without infrastructure impact

---

## 3. Response Chain of Command

```
INCIDENT DETECTED
       │
       ▼
Duty Officer ( rota via on-call schedule )
       │
       ├─ Category A → escalate immediately
       │                 │
       │                 ▼
       │          Managing Director + Legal Counsel
       │                 │
       │                 ▼
       │          CRISA notification (within 72h)
       │                 │
       │                 ▼
       │          SAPS (if Category A involves harm/threat)
       │
       └─ Category B → log + internal review within 5 business days
```

**Duty Officer rotation:** Managed via `on_call_schedule` table in Supabase. Primary: Information Security Officer. Backup: Managing Director. Contact details in `emergency-contacts.md` (not stored in git for security).

---

## 4. Incident Detection Triggers

The following Prometheus alerts constitute immediate Category A escalation triggers:

| Alert Name | Trigger | Action |
|-----------|---------|--------|
| `SentinelBruteForceAttempt` | >10 failed auth/min from same instance for 2min | Duty Officer pages immediately |
| `SentinelSuspiciousUserAgent` | sqlmap/burp/nikto scanner detected | Duty Officer pages immediately |
| `SentinelAlertBridgeDown` | Sentry-Telegram bridge down >2min | IT ops responds; not Cybercrimes unless deliberate |
| `PrometheusTargetDown` | Backend scrape target unreachable | Investigate; escalate if duration >30min without explanation |
| `HighErrorRate` | >5% 5xx rate sustained 5min | Security review; not always cyber-related |

**Manual triggers (any team member):**
- Unauthorized access to Grafana or Supabase
- Suspicious Telegram messages from unknown numbers requesting credentials
- Unexpected configuration changes in BMS setpoints or schedules
- MQTT authentication failures from unexpected locations
- Ransomware note or blackmail demand received

---

## 5. Incident Response Steps

### Step 1 — Confirm and Contain (0–4 hours)

1. **Duty Officer acknowledges alert** — confirm via on-call schedule.
2. **Initial triage** — determine if offence is Category A or B using Section 2 classification.
3. **Isolate affected system** — do NOT power off (preserves forensic evidence):
   - Site bridge compromised: `sudo ufw deny <source_ip>` immediately, then disable WireGuard peer
   - Supabase access: revoke affected service role keys via Supabase dashboard; do not delete user
   - API compromised: block via Cloudflare firewall rule (rule name: `INCIDENT-<date>`)
4. **Document initial state** — screenshot of alert, log timestamps, source IP. Save to `incidents/<YYYY-MM-DD>-<brief-description>.md` in SENTINEL vault (`/home/bederf/sentinel-vault/incidents/`).
5. **Preserve logs** — Loki logs and Prometheus metrics for affected time window must be extracted before rotation. Command: `scripts/export-loki-range.sh <start> <end> <output_file>`.

> **Critical:** Do not wipe or reformat any compromised device until CRISA has been consulted. Destroying evidence is a separate offence under s12 of the Act.

### Step 2 — Assess (4–24 hours)

6. **Scope assessment** — determine:
   - What data was accessed or exfiltrated?
   - Was personal information involved (POPIA trigger)?
   - Was the BMS control system affected (safety implication)?
   - What is the business impact (operational, reputational, legal)?
7. **Escalate to Managing Director** — if Category A, Managing Director must be notified within 4 hours of classification.
8. **Engage legal counsel** — if data exfiltration, personal information, or critical infrastructure involved.

### Step 3 — Report (24–72 hours)

9. **CRISA notification** — for Category A offences, notify CRISA (Cybercrime Response Centre):
   - Website: https://cybercrime.gov.za
   - Email: report@cybercrime.gov.za
   - Phone: 082 123 4567 (SAPS Cybercrime Hub)
   - Form: Online reporting form at cybercrime.gov.za
   - Required information: description of offence, date/time first detected, systems affected, initial actions taken, contact details
10. **SAPS notification** — only required if:
    - The offence involved actual harm or threat to a person (s3(1)(b) applied)
    - The offender is identifiable
    - There is a risk of continued harm
11. **POPIA breach notification** — if personal information was accessed/exfiltrated, notify Information Regulator within 72 hours per POPIA s22. Template: `popia-breach-notification-template.md`.
12. **FNB notification** — if SENTINEL is providing services under FNB supplier contract, notify FNB IT security team within 72h.

### Step 4 — Recover (72h+)

13. **Root cause analysis** — determine how the attacker gained access.
14. **System hardening** — close the attack vector before restoring service.
15. **Restore from clean backup** — do not restore from any backup taken after compromise date.
16. **Monitoring elevation** — increase Prometheus alert sensitivity for 30 days post-incident.
17. **Lessons learned** — document in incident file within 10 business days.

---

## 6. Evidence Preservation

Chain of custody requirements under the Act:

| Evidence Type | Preservation Method | Retention |
|-------------|---------------------|-----------|
| Loki logs | Export via `scripts/export-loki-range.sh` to immutable storage | 5 years |
| Prometheus metrics | `promtool query range` export to JSON file | 5 years |
| Cloudflare firewall logs | Export via Cloudflare dashboard | 2 years minimum |
| WireGuard tunnel logs | `/var/log/wireguard/*.log` — rotate only after export | 5 years |
| Supabase auth logs | `auth.users` audit log export via pg_dump | 5 years |
| Network captures | If available — pcap from site bridge mirror port | 90 days (store securely) |

**Forensic extraction commands:**
```bash
# Export Loki logs for incident window
./scripts/export-loki-range.sh "2026-05-19T00:00:00Z" "2026-05-19T12:00:00Z" incident-20260519.json

# Export Prometheus metrics
promtool query range 'sentinel_http_requests_total' "2026-05-19T00:00:00Z" "2026-05-19T12:00:00Z" > incident-20260519-metrics.json

# Export Cloudflare firewall events
# (via Cloudflare dashboard — Logs section, filter by date range and rule name)
```

---

## 7. "Reasonable Steps" Documentation

The "reasonable steps" defence under s2 requires that SENTINEL can demonstrate it took proportionate security measures. The companion document `cybercrimes-reasonable-steps-evidence.md` provides the evidence package.

**Key evidence items for the defence:**
- This response procedure (documented, trained, practiced)
- TLS 1.3 enforced on all API paths
- WireGuard VPN for all site bridge connections
- Cloudflare WAF with rate limiting and bot detection
- Prometheus alerts on unauthorized access patterns
- Access logs retained for minimum 90 days (Loki: 90d retention)
- Credential rotation policy documented
- Multi-factor authentication enforced on Supabase and Grafana
- Network segmentation (OT devices not directly internet-accessible)

---

## 8. Incident Classification Quick Reference

| Indicator | Category A | Category B |
|-----------|-----------|-----------|
| BMS control system affected | ✅ Yes | ❌ No |
| Personal information accessed | ✅ Yes | ❌ No |
| Data exfiltrated | ✅ Yes | ❌ No |
| Critical infrastructure targeted | ✅ Yes | ❌ No |
| Unknown attacker identity | ✅ Yes | ❌ No |
| Suspicious scanning only, no access gained | ❌ No | ✅ Yes |
| Phishing attempt with no credential compromise | ❌ No | ✅ Yes |
| Single failed auth (brute force blocked) | ❌ No | ✅ Yes |

---

## 9. Document Control

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 0.1.0 | 2026-05-19 | Compliance Team | Initial Cybercrimes Act response procedure |

### Approval

- **Information Security Officer:** ___________________ Date: ___________
- **Legal Counsel Review:** ___________________ Date: ___________
- **Managing Director:** ___________________ Date: ___________

---

## 10. Related Documents

- [South African Regulatory Compliance Register](south-africa-regulatory-compliance-register.md)
- [Cybercrimes "Reasonable Steps" Evidence Package](cybercrimes-reasonable-steps-evidence.md)
- [POPIA Breach Notification Template](popia-breach-notification-template.md)
- [Incident Response Policy](incident-response-policy.md)
- [Information Security Policy](../information-security-policy.md)

---

*This document is a controlled record under Cybercrimes Act s2 defence documentation. Unauthorized modification is prohibited.*