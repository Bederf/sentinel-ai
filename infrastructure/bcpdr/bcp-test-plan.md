# SENTINEL Business Continuity Plan — Test Plan

**Document Owner:** SENTINEL Platform Team
**Version:** 1.0
**Created:** 2026-02-04
**Review Cycle:** Annual (after each test)
**Status:** Active

---

## 1. Overview

This document defines test procedures for validating the SENTINEL BMS Intelligence Platform's business continuity and disaster recovery capabilities. Testing ensures recovery procedures work as documented and meet RTO/RPO targets.

**Regulatory Reference:** FSR Domain 4.15 — Business Continuity Management (current 3.0 / target 4.0)

---

## 2. Test Frequency

| Test Type | Frequency | Duration | Participants |
|-----------|-----------|----------|-------------|
| **Full DR test** | Annual | 4-8 hours | All technical staff |
| **Tabletop exercise** | Semi-annual | 2 hours | Technical staff + management |
| **Component test** | Quarterly | 1-2 hours | Relevant technical staff |
| **Backup verification** | Monthly | 30 minutes | Operations |

---

## 3. Test Scenarios

### Scenario 1: Contabo VM Failure — Complete VM Loss

**Objective:** Restore SENTINEL to operational state from VM snapshot
**RTO Target:** 4 hours
**RPO Target:** 24 hours (daily snapshots)
**Test Type:** Full DR test (annual)

**Pre-conditions:**
- Current VM snapshot available (< 24 hours old)
- Contabo account credentials accessible
- Docker Compose / Swarm configuration backed up
- `.env` files backed up securely

**Test Steps:**

| Step | Action | Expected Result | Actual Result | Pass/Fail |
|------|--------|-----------------|---------------|-----------|
| 1 | Document current service versions and state | Inventory captured | | |
| 2 | (Simulated) Mark current VM as "failed" | VM inaccessible | | |
| 3 | Log into Contabo control panel | Access confirmed | | |
| 4 | Provision new VM from latest snapshot | VM provisioned and booting | | |
| 5 | SSH into new VM, verify OS | Shell access confirmed | | |
| 6 | Verify Docker daemon running | `docker info` returns OK | | |
| 7 | Restore Docker Swarm stack | `docker stack deploy` succeeds | | |
| 8 | Verify all services healthy | `docker service ls` shows replicas running | | |
| 9 | Restore environment variables | `.env` files in place | | |
| 10 | Verify Cloudflare Tunnel reconnects | External URL accessible | | |
| 11 | Test backend API health | `curl /api/health` returns 200 | | |
| 12 | Test frontend loads | Browser loads UI | | |
| 13 | Verify database connectivity | Supabase queries succeed | | |
| 14 | Verify AI services | Chat endpoint responds | | |
| 15 | Record total recovery time | Time <= 4 hours | | |

**Success Criteria:**
- All Docker services running within 4 hours
- API endpoints return expected responses
- Frontend accessible via Cloudflare Tunnel
- Database queries return valid data
- No data loss beyond 24-hour RPO window

---

### Scenario 2: Database Corruption — Supabase Data Loss

**Objective:** Restore database from Supabase backup
**RTO Target:** 2 hours
**RPO Target:** 1 hour (Supabase continuous backup)
**Test Type:** Full DR test (annual)

**Pre-conditions:**
- Supabase project backups enabled
- Supabase admin credentials available
- Database schema migrations documented

**Test Steps:**

| Step | Action | Expected Result | Actual Result | Pass/Fail |
|------|--------|-----------------|---------------|-----------|
| 1 | Document current database state (row counts) | Baseline captured | | |
| 2 | (Simulated) Identify "corruption" scenario | Scope defined | | |
| 3 | Stop application writes (maintenance mode) | API returns 503 | | |
| 4 | Access Supabase dashboard | Dashboard accessible | | |
| 5 | Initiate point-in-time recovery | Recovery started | | |
| 6 | Wait for restoration to complete | Database restored | | |
| 7 | Verify schema integrity | All tables present | | |
| 8 | Verify row counts match baseline | Data consistent | | |
| 9 | Run application migrations | Migrations pass | | |
| 10 | Resume application writes | API returns 200 | | |
| 11 | Verify JSON fallback data intact | JSON files valid | | |
| 12 | Record total recovery time | Time <= 2 hours | | |

**Success Criteria:**
- Database restored within 2 hours
- Data loss within 1-hour RPO window
- All schema migrations applied successfully
- JSON fallback data unaffected
- Application resumes normal operations

---

### Scenario 3: Container Failure — Docker Service Crash

**Objective:** Restore individual Docker service
**RTO Target:** 30 minutes
**RPO Target:** 0 (stateless containers)
**Test Type:** Component test (quarterly)

**Pre-conditions:**
- Docker Swarm running
- Service images available in registry
- Health check endpoints configured

**Test Steps:**

| Step | Action | Expected Result | Actual Result | Pass/Fail |
|------|--------|-----------------|---------------|-----------|
| 1 | Identify target service for test | Service selected | | |
| 2 | (Simulated) Kill service container | Container stops | | |
| 3 | Check Docker Swarm auto-restart | New container starting | | |
| 4 | Wait for health check to pass | Service healthy | | |
| 5 | If auto-restart fails: force update service | `docker service update --force` | | |
| 6 | If persistent: rebuild from image | `docker service update --image` | | |
| 7 | Verify service health endpoint | Returns 200 | | |
| 8 | Verify dependent services reconnect | Integration verified | | |
| 9 | Record total recovery time | Time <= 30 minutes | | |

**Success Criteria:**
- Service restored within 30 minutes
- Docker Swarm auto-restart detected failure
- No data loss (stateless containers)
- Dependent services reconnect automatically

---

### Scenario 4: Cloudflare Tunnel Loss — Remote Access Disruption

**Objective:** Restore remote access to SENTINEL
**RTO Target:** 1 hour
**Test Type:** Component test (quarterly)

**Pre-conditions:**
- Cloudflare account credentials available
- Cloudflared tunnel configuration backed up
- Direct SSH access available as fallback

**Test Steps:**

| Step | Action | Expected Result | Actual Result | Pass/Fail |
|------|--------|-----------------|---------------|-----------|
| 1 | Verify current tunnel status | Tunnel active | | |
| 2 | (Simulated) Stop cloudflared service | Tunnel disconnected | | |
| 3 | Verify external URL inaccessible | Connection refused | | |
| 4 | Restart cloudflared service | `systemctl restart cloudflared` | | |
| 5 | Verify tunnel reconnects | Tunnel status: healthy | | |
| 6 | Test external URL | Frontend loads | | |
| 7 | If Cloudflare outage (not simulated): | | | |
| 7a | Activate direct SSH fallback | SSH tunnel established | | |
| 7b | Configure port forwarding | Ports 9095/9096 forwarded | | |
| 7c | Notify users of temporary access | Users informed | | |
| 8 | Record total recovery time | Time <= 1 hour | | |

**Success Criteria:**
- Remote access restored within 1 hour
- Cloudflared service restarts successfully
- Fallback SSH tunnel tested and documented
- Users notified of any temporary access changes

---

### Scenario 5: API Dependency Failure — Claude API or FSI API Unavailable

**Objective:** Maintain degraded but functional service
**RTO Target:** Automatic (circuit breakers)
**Test Type:** Component test (quarterly)

**Pre-conditions:**
- Circuit breaker patterns configured
- Ollama available as AI fallback
- Cached/demo responses configured

**Test Steps:**

| Step | Action | Expected Result | Actual Result | Pass/Fail |
|------|--------|-----------------|---------------|-----------|
| 1 | Document current API dependency status | All APIs available | | |
| 2 | (Simulated) Block Claude API endpoint | API unreachable | | |
| 3 | Send chat query to SENTINEL | | | |
| 4 | Verify circuit breaker activates | Fallback to Ollama | | |
| 5 | Verify Ollama handles Tier 1 queries | Response received | | |
| 6 | Verify demo responses still work | Cached responses returned | | |
| 7 | Verify non-AI features unaffected | Dashboard, devices, sensors OK | | |
| 8 | (Simulated) Restore Claude API | API reachable | | |
| 9 | Verify circuit breaker resets | Full AI service restored | | |
| 10 | Test FSI API failure independently | SIMBIOT connector degrades gracefully | | |
| 11 | Record degraded service capability | Capability matrix documented | | |

**Success Criteria:**
- Circuit breaker activates within 30 seconds
- Ollama fallback provides basic AI responses
- Non-AI features fully operational during API outage
- Full service restored when dependency recovers
- No user-facing errors (graceful degradation)

---

## 4. Test Execution Checklist

### Pre-Test Preparation

- [ ] Test scenario selected and approved by management
- [ ] Test participants identified and available
- [ ] Current system state documented (baseline)
- [ ] Backup status verified (snapshots, database backups)
- [ ] Test environment prepared (if not testing production)
- [ ] Communication plan in place (notify affected users if production test)
- [ ] Rollback plan documented
- [ ] Test recording tools ready (timestamps, screenshots, logs)

### During Test

- [ ] Start time recorded
- [ ] Each step executed and documented
- [ ] Actual results recorded for each step
- [ ] Timing captured for each recovery phase
- [ ] Issues and deviations noted
- [ ] Screenshots/logs captured at key points

### Post-Test

- [ ] End time recorded, total duration calculated
- [ ] All steps marked pass/fail
- [ ] Issues categorised (critical, major, minor)
- [ ] Lessons learned discussed with participants
- [ ] Remediation tasks created for any failures
- [ ] Procedures updated based on findings
- [ ] Test results archived

---

## 5. Test Results Template

### Test Record

| Field | Value |
|-------|-------|
| **Test Date** | YYYY-MM-DD |
| **Scenario** | Scenario 1/2/3/4/5 |
| **Test Type** | Full DR / Tabletop / Component |
| **Participants** | [Names and roles] |
| **Start Time** | HH:MM |
| **End Time** | HH:MM |
| **Total Duration** | [duration] |
| **RTO Target** | [target from scenario] |
| **Actual Recovery Time** | [actual time] |
| **RTO Met?** | Yes/No |
| **RPO Target** | [target from scenario] |
| **Actual Data Loss** | [if applicable] |
| **RPO Met?** | Yes/No |
| **Overall Result** | PASS / FAIL / PARTIAL |
| **Issues Found** | [count] |

### Issues Found

| # | Severity | Description | Remediation | Owner | Due Date | Status |
|---|----------|-------------|-------------|-------|----------|--------|
| 1 | Critical/Major/Minor | [description] | [action] | [name] | YYYY-MM-DD | Open/Closed |

### Lessons Learned

1. [Finding] — [Improvement action]
2. [Finding] — [Improvement action]

---

## 6. Annual Test Schedule

| Quarter | Test Type | Scenario | Target Date | Status |
|---------|-----------|----------|-------------|--------|
| Q1 2026 | Component test | Scenario 3 (Container) | March 2026 | Planned |
| Q2 2026 | Tabletop exercise | Scenario 1+2 (VM + DB) | June 2026 | Planned |
| Q3 2026 | Component test | Scenario 4+5 (Tunnel + API) | September 2026 | Planned |
| Q4 2026 | Full DR test | Scenario 1 (VM recovery) | December 2026 | Planned |

---

## 7. References

- FSR Domain 4.15: Business Continuity Management
- ISO 22301:2019 Business Continuity Management
- NIST SP 800-34: Contingency Planning Guide
- SENTINEL DR Runbook: `infrastructure/bcpdr/dr-runbook.md`
- SENTINEL BCP/DR Documentation: `docs/08-security/bcp-dr-procedures.md`

---

*Test plan maintained by SENTINEL Platform Team. Updated after each test cycle.*
