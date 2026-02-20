# SENTINEL Business Continuity and Disaster Recovery Procedures

**Document Owner:** SENTINEL Platform Team
**Version:** 1.0
**Created:** 2026-02-04
**FSR Reference:** Domain 4.15 — Business Continuity Management
**Status:** Active

---

## 1. Overview

This document describes the business continuity planning (BCP) and disaster recovery (DR) procedures for the SENTINEL BMS Intelligence Platform. SENTINEL is a cloud-hosted building management system that provides predictive maintenance, conversational AI, and device control capabilities for facilities management.

**Platform Architecture:**
- **Hosting:** Contabo VPS with Docker Swarm orchestration
- **Database:** Supabase (PostgreSQL) with JSON file fallback
- **Remote Access:** Cloudflare Tunnel (zero-trust networking)
- **AI Services:** Claude API (primary) + Ollama (local fallback)
- **Monitoring:** Loki/Grafana centralised logging, Wazuh SIEM

---

## 2. Business Process Register

SENTINEL processes ranked by business criticality for recovery prioritisation.

### Critical Processes (RTO: < 4 hours)

| Process | Description | Dependencies | Impact of Loss |
|---------|-------------|-------------|----------------|
| **BMS data ingestion** | Collect sensor data from BACnet/Modbus devices | VPS, Docker, InfluxDB | Loss of real-time monitoring |
| **Anomaly detection** | ML models detect equipment anomalies | VPS, Docker, ML models | Missed failure warnings |
| **Alert generation** | Create and dispatch alerts for anomalies | VPS, Docker, database | Delayed incident response |

### High Priority Processes (RTO: < 8 hours)

| Process | Description | Dependencies | Impact of Loss |
|---------|-------------|-------------|----------------|
| **Work order creation** | Generate work orders from anomalies | VPS, Docker, FSI API | Delayed maintenance dispatch |
| **AI chat** | Conversational building management queries | VPS, Docker, Claude/Ollama | Loss of AI-assisted operations |
| **Device control** | Remote BMS device control commands | VPS, Docker, BACnet/Modbus | Loss of remote control capability |

### Medium Priority Processes (RTO: < 24 hours)

| Process | Description | Dependencies | Impact of Loss |
|---------|-------------|-------------|----------------|
| **Reporting** | Dashboard reporting and analytics | VPS, Docker, database | Delayed management reporting |
| **Historical analysis** | Trend analysis and pattern detection | VPS, Docker, InfluxDB | Reduced analytical capability |
| **ML training** | Model retraining and improvement | VPS, Docker, training data | Delayed model updates |

### Low Priority Processes (RTO: < 72 hours)

| Process | Description | Dependencies | Impact of Loss |
|---------|-------------|-------------|----------------|
| **Documentation** | System and API documentation | VPS, static files | Reference material unavailable |
| **Development tools** | Development and testing environments | VPS, Docker | Development paused |

---

## 3. RTO/RPO Summary

| Component | RTO | RPO | Backup Method | Recovery Method |
|-----------|-----|-----|---------------|-----------------|
| **Contabo VPS** | 4 hours | 24 hours | Daily VM snapshots | Snapshot restoration |
| **Supabase (PostgreSQL)** | 2 hours | 1 hour | Continuous backup (PITR) | Point-in-time recovery |
| **Docker Services** | 30 minutes | 0 (stateless) | Container images | Service restart / redeploy |
| **Cloudflare Tunnel** | 1 hour | N/A | Configuration backup | Tunnel reconfiguration |
| **AI Services (Claude)** | Automatic | N/A | Circuit breaker | Ollama fallback |
| **JSON Data Files** | 4 hours | 24 hours | Part of VM snapshot | Snapshot restoration |
| **InfluxDB (telemetry)** | 4 hours | 24 hours | Docker volume in snapshot | Volume restoration |
| **ML Models** | 24 hours | N/A | Model registry files | Retrain or restore from backup |
| **Environment Config** | 1 hour | N/A | Encrypted offline backup | Manual restoration |

---

## 4. DR Architecture

### Resilience Layers

```
Layer 1: Application Resilience
├── Docker Swarm auto-restart (container failures)
├── Circuit breaker pattern (external API failures)
├── Hybrid AI routing (Claude -> Ollama fallback)
├── Dual-write storage (Supabase + JSON fallback)
└── Graceful degradation (features disabled, core preserved)

Layer 2: Infrastructure Resilience
├── Contabo VM snapshots (daily, automated)
├── Supabase continuous backup (PITR)
├── Docker image registry (rebuild from images)
├── Cloudflare Tunnel (encrypted, auto-reconnect)
└── SSH fallback (direct access if tunnel down)

Layer 3: Data Resilience
├── Supabase PITR (1-hour RPO)
├── JSON file fallback (part of VM snapshot)
├── InfluxDB data (Docker volume, snapshotted)
├── Audit logs (JSON + structured logging to Loki)
└── Consent records (immutable append-only JSON)

Layer 4: Operational Resilience
├── Documented recovery procedures (DR runbook)
├── Annual BCP testing
├── Escalation path and emergency contacts
├── Communication plan
└── Post-incident review process
```

### Graceful Degradation

When external dependencies fail, SENTINEL degrades gracefully rather than going offline:

| Dependency | Failure Mode | Degraded Capability | Full Recovery |
|------------|-------------|---------------------|---------------|
| **Claude API** | API unreachable | Ollama handles basic queries; demo cache active | Automatic when API recovers |
| **Supabase** | Database unreachable | JSON fallback for reads; writes queued | Resume on reconnection |
| **FSI Concept API** | API unreachable | Work orders queued locally | Sync on recovery |
| **Cloudflare Tunnel** | Tunnel disconnect | SSH direct access fallback | Auto-reconnect |
| **InfluxDB** | Container crash | Historical trends unavailable; real-time continues | Docker auto-restart |

---

## 5. Backup Procedures

### Automated Backups

| Backup | Frequency | Retention | Location | Verification |
|--------|-----------|-----------|----------|-------------|
| VM snapshot | Daily | 7 days | Contabo infrastructure | Monthly restore test |
| Supabase backup | Continuous (PITR) | 7 days (Pro) | Supabase infrastructure | Monthly data check |
| JSON data files | With VM snapshot | 7 days | Contabo infrastructure | Part of VM verify |
| Docker images | On build | Latest + previous | Container registry | Build pipeline |
| Audit logs | Real-time (Loki) | 30 days (Loki) | Grafana Loki storage | Dashboard query test |
| Config backup | Weekly manual | Indefinite | Encrypted offline | Monthly verification |

### Manual Backup Requirements

| Item | Frequency | Method | Storage |
|------|-----------|--------|---------|
| `.env` files | On change | Encrypted copy | Offline encrypted storage |
| SSH keys | On rotation | Encrypted copy | Offline encrypted storage |
| Cloudflare tunnel config | On change | Export from dashboard | Encrypted document store |
| Docker Compose files | Version controlled | Git repository | GitHub/GitLab |

---

## 6. Annual Test Schedule

| Quarter | Test Type | Scenario | RTO Verified | Status |
|---------|-----------|----------|-------------|--------|
| Q1 | Component | Docker service recovery (30 min RTO) | Yes | Planned |
| Q2 | Tabletop | VM failure + DB recovery discussion | Yes | Planned |
| Q3 | Component | Tunnel loss + API dependency (1 hr RTO) | Yes | Planned |
| Q4 | Full DR | Complete VM recovery (4 hr RTO) | Yes | Planned |

### Test Results Tracking

| Test Date | Scenario | RTO Target | Actual Time | Result | Issues | Remediation |
|-----------|----------|-----------|-------------|--------|--------|-------------|
| _[To be populated after first test]_ | | | | | | |

---

## 7. Roles and Responsibilities

| Role | Responsibility |
|------|---------------|
| **Platform Lead** | BCP programme owner, annual review, test approval |
| **On-call Operator** | First responder, initial assessment, L1 recovery |
| **DevOps Engineer** | Infrastructure recovery, Docker/VM management |
| **Database Admin** | Supabase recovery, data integrity verification |
| **Security Lead** | Incident classification, compliance notifications |
| **Management** | Escalation decisions, resource allocation, comms approval |

---

## 8. Compliance and Audit

### FSR Domain 4.15 Evidence

| FSR Requirement | SENTINEL Evidence |
|----------------|-------------------|
| Documented BCP | This document + `infrastructure/bcpdr/bcp-test-plan.md` |
| Documented DR procedures | `infrastructure/bcpdr/dr-runbook.md` |
| RTO/RPO definitions | Section 3 of this document |
| Annual testing | Test schedule in Section 6; results in test plan |
| Business process criticality | Business Process Register in Section 2 |
| Communication plan | DR runbook Section 5 |
| Post-incident review | DR runbook Section 6 |

### Audit Checklist

- [ ] BCP/DR documentation current (reviewed within 12 months)
- [ ] Annual full DR test completed
- [ ] Test results documented with issues and remediation
- [ ] RTO/RPO targets met in latest test
- [ ] Communication plan tested
- [ ] Backup verification completed (monthly)
- [ ] Lessons learned from previous incidents incorporated

---

## 9. Document Control

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-02-04 | SENTINEL Platform Team | Initial creation |

---

## 10. References

- BCP Test Plan: `infrastructure/bcpdr/bcp-test-plan.md`
- DR Runbook: `infrastructure/bcpdr/dr-runbook.md`
- Logging Architecture: `docs/08-security/logging-architecture.md`
- Vulnerability Management: `docs/08-security/vulnerability-management.md`
- Access Control: `docs/08-security/access-control-implementation.md`
- FSR Domain 4.15: Business Continuity Management
- ISO 22301:2019: Business Continuity Management Systems
- NIST SP 800-34: Contingency Planning Guide for Federal Information Systems

---

*Document maintained by SENTINEL Platform Team. Annual review required for FSR compliance.*
