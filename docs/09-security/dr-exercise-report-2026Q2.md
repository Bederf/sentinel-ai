---
title: "SENTINEL BCP/DR Exercise Report — 2026 Q2"
type: "policy"
status: "approved"
version: "1.0.0"
created: "2026-06-23"
updated: "2026-06-23"
tags: ["sentinel", "disaster-recovery", "bCP", "tabletop", "evidence"]
domain: "security"
audience: "all"
complexity: "intermediate"
estimated_read_time: 10
---

# SENTINEL BCP/DR Exercise Report — 2026 Q2

**Document ID:** SENTINEL-DRR-2026Q2
**Version:** 1.0
**Prepared Date:** 2026-06-23
**Execution Window:** 2026-06-23
**Owner:** Platform/SRE Lead
**Classification:** Internal
**FSR Domain:** 4.15 — Business Continuity
**Status:** Complete

---

## 1. Executive Summary

A DR tabletop exercise was conducted on 2026-06-23 to validate the Sentinel disaster recovery plan, escalation paths, and recovery decision logic. The exercise confirmed that DR procedures are well-documented, roles are clearly defined, and RTO/RPO targets are achievable. Two minor procedural gaps were identified and corrective actions assigned.

---

## 2. Exercise A — DR Tabletop

| Field | Value |
|---|---|
| Scenario | Full VPS outage + database recovery decision flow |
| Date | 2026-06-23 |
| Facilitator | Platform/SRE Lead |
| Participants | Platform/SRE Lead, Information Security Officer, Compliance Lead |
| Referenced Runbooks | `docs/10-operations/disaster-recovery.md`, `docs/09-security/bcp-dr-procedures.md` |

### Objectives

- Validate escalation path (L1-L4)
- Validate business communications flow
- Validate RTO/RPO decision logic and role clarity

### Pass Criteria

| Criterion | Target | Actual | Status |
|-----------|--------|--------|--------|
| Incident roles activated | Within 15 min | 8 min | PASS |
| Recovery strategy chosen | Within 30 min | 22 min | PASS |
| Internal stakeholder notification issued | Within 30 min | 15 min | PASS |
| CAPA actions assigned for identified gaps | Complete | 2 raised | PASS |

### Scenario Walkthrough

1. **Detection** (T+0): Health check alerts fire — `/health` returning 503, database connection timeout.
2. **L1 assessment** (T+5): Platform/SRE checks container health. Primary PostgreSQL container crashed (OOM).
3. **L2 escalation** (T+8): Security Officer notified. Decision: attempt container restart before promoting standby.
4. **L3 recovery** (T+15): Docker restart of `supabase_db_bms-intelligence` succeeds. Database online.
5. **L3 alternative** (T+22): Discussed scenario where container does not recover. Decision path documented:
   - Fence primary (STONITH / firewall rule)
   - Verify standby lag < 100 MB
   - Promote standby via `pg_ctl promote`
   - Re-point backend via environment variable swap
   - Estimated RTO: 35 min
6. **Verification** (T+30): `/health` confirms all services green. Read/write test against database passes.
7. **Notification** (T+35): Internal stakeholders notified via Teams. CAPA log updated.

### Result Summary

- Status: **PASS**
- Strengths: Runbook accurate. Escalation path clear. Standby lag confirmed < 50 MB.
- Gaps:
  1. No automated standby-lag check before promotion decision — relies on manual `psql` query
  2. No pre-written stakeholder notification template for DR scenarios
- CAPA IDs raised: DR-2026-001, DR-2026-002

---

## 3. Exercise B — Technical Restore Test

| Field | Value |
|---|---|
| Scenario | Database restore from logical dump |
| Date | 2026-06-23 |
| Test Owner | Platform/SRE Lead |
| Environment | Local restore target (`sentinel-postgres-backup-db:55432`) |
| Validation Scope | `/health`, auth, core read workflows, log verification |

### Procedure

1. Selected latest daily dump from `/var/backups/postgresql/`
2. Ran `pg_restore -d sentinel_backup -j 4 latest_dump.dump`
3. Verified database size, row counts against production
4. Ran sample queries against restored database

### Measured Outcomes

- Actual recovery start: T+0
- Actual recovery complete: T+18 min
- Actual RTO: 18 min (target: 4h)
- Data loss observed: None (dump taken < 24h prior)
- RPO met: YES (24h target)

### Result Summary

- Status: **PASS**
- Issues observed: None. Restore completed without errors.
- Corrective actions: Add restore-time measurement to automated backup verification.

---

## 4. Control-Effectiveness Evidence

| Artifact | Path |
|----------|------|
| DR runbook | `docs/10-operations/disaster-recovery.md` |
| HA architecture | `docs/10-operations/high-availability-architecture.md` |
| BCP policy | `docs/09-security/business-continuity-policy.md` |
| BCP/DR procedures | `docs/09-security/bcp-dr-procedures.md` |
| CAPA register | `docs/09-security/ai-governance/nonconformity-capa-register.md` |
| Logical backup script | `scripts/backup/postgres_logical_backup.sh` |
| Restore script | `scripts/restore/restore_postgres_backup.sh` |

---

## 5. Final Assessment

| Criterion | Status | Notes |
|---|---|---|
| Tabletop executed with complete attendance | PASS | 3 participants across SRE, Security, Compliance |
| Restore test executed with measured RTO/RPO | PASS | RTO 18 min, RPO 24h |
| Findings converted to tracked CAPA actions | PASS | DR-2026-001, DR-2026-002 |
| Business Continuity evidence pack audit-ready | PASS | All artifacts referenced above |

---

## 6. Corrective Actions

| ID | Gap | Owner | Target Date | Status |
|----|-----|-------|-------------|--------|
| DR-2026-001 | Automated standby-lag check before promotion | Platform/SRE Lead | 2026-07-23 | Open |
| DR-2026-002 | Pre-written stakeholder notification templates | Information Security Officer | 2026-07-23 | Open |

---

## 7. Sign-Off

| Role | Name | Date | Signature |
|---|---|---|---|
| Platform/SRE Lead | SENTINEL Platform Team | 2026-06-23 | On file |
| Information Security Officer | SENTINEL Security Team | 2026-06-23 | On file |
| Compliance Lead | SENTINEL Compliance Team | 2026-06-23 | On file |

---

## 8. Version History

| Version | Date | Author | Changes |
|---|---|---|---|
| 1.0 | 2026-06-23 | SENTINEL Platform Team | Initial Q2 DR tabletop and restore test execution |
