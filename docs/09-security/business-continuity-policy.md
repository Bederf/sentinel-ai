---
title: "SENTINEL Business Continuity Management Policy"
type: "policy"
status: "approved"
version: "1.1.0"
created: "2026-03-31"
updated: "2026-06-23"
tags: ["sentinel", "documentation"]
related: []
domain: "security"
audience: "all"
complexity: "intermediate"
estimated_read_time: 10
---

# SENTINEL Business Continuity Management Policy

**Document Owner:** Information Security Officer
**Version:** 1.0
**Effective Date:** 2026-02-04
**Review Cadence:** Annual, or after any DR invocation
**FSR Reference:** Domain 4.15 -- Business Continuity Management
**Classification:** Confidential
**Status:** Active

---

## 1. Purpose

This policy ensures that SENTINEL BMS Intelligence Platform can maintain or rapidly restore critical services following any disruption -- whether infrastructure failure, cyberattack, natural disaster, or third-party service outage. It establishes the governance framework for business continuity planning (BCP) and disaster recovery (DR) across all SENTINEL systems, services, and data processing activities.

This policy wraps and governs the technical DR procedures deployed in Phase 63-06 (see `infrastructure/bcpdr/dr-runbook.md` and `infrastructure/bcpdr/bcp-test-plan.md`).

---

## 2. Scope

This policy applies to:

- All SENTINEL platform components (backend, frontend, database, AI services, monitoring)
- All data processing activities (BMS telemetry, occupant personal information, work orders)
- All hosting infrastructure (Contabo VPS, Cloudflare, Supabase)
- All third-party integrations (Claude API, MRI Evolution/FSI, WhatsApp, Telegram)
- All personnel with operational responsibility for SENTINEL

---

## 3. Business Process Register

SENTINEL business processes ranked by criticality for recovery prioritisation.

### 3.1 Critical (RTO 1 hour)

| Process | Description | Dependencies | Impact of Loss |
|---------|-------------|--------------|----------------|
| **BMS telemetry collection** | Ingest real-time sensor data from BACnet/Modbus devices | VPS, Docker, InfluxDB, device adapters | Loss of real-time building monitoring; safety-critical readings unavailable |
| **Safety monitoring** | Validate safety interlocks, temperature/pressure limits | VPS, Docker, safety engine | Unmonitored safety conditions; potential building damage or occupant risk |
| **Fire alarm integration** | Read fire panel status, trigger HVAC shutdown interlocks | VPS, Docker, BACnet | Fire safety interlock failure; regulatory non-compliance |

### 3.2 High (RTO 4 hours)

| Process | Description | Dependencies | Impact of Loss |
|---------|-------------|--------------|----------------|
| **AI chat and conversational interface** | Building management queries, comfort complaints, technician support | VPS, Docker, Claude/Ollama | Loss of AI-assisted operations; technicians revert to manual processes |
| **Work order creation** | Generate and dispatch work orders from anomalies and complaints | VPS, Docker, FSI API | Delayed maintenance dispatch; increased response times |
| **Alert processing** | Detect anomalies, generate alerts, notify operators | VPS, Docker, ML models | Missed equipment failure warnings; reactive maintenance only |
| **Device control** | Remote BMS device control (HVAC setpoints, DALI lighting) | VPS, Docker, device adapters | Loss of remote optimisation capability |

### 3.3 Medium (RTO 24 hours)

| Process | Description | Dependencies | Impact of Loss |
|---------|-------------|--------------|----------------|
| **ML predictions** | LSTM/autoencoder failure predictions, survival analysis | VPS, Docker, ML models | Reduced predictive maintenance capability |
| **Reporting and dashboards** | Operational dashboards, energy analytics, KPIs | VPS, Docker, database | Delayed management reporting |
| **Historical trend analysis** | Trend analysis, pattern detection, baseline comparisons | VPS, Docker, InfluxDB | Reduced analytical capability |

### 3.4 Low (RTO 72 hours)

| Process | Description | Dependencies | Impact of Loss |
|---------|-------------|--------------|----------------|
| **Training data generation** | Feature store computation, training dataset creation | VPS, Docker, InfluxDB | Delayed ML model improvement |
| **Fleet learning** | Cross-site pattern analysis, portfolio insights | VPS, Docker, database | No fleet-level intelligence |
| **Documentation and API docs** | System documentation, Swagger/OpenAPI specification | VPS, static files | Reference material unavailable |

---

## 4. Recovery Objectives

### 4.1 Recovery Time Objectives (RTO)

Maximum acceptable downtime before each component must be restored.

| Component | RTO | Justification |
|-----------|-----|---------------|
| Docker services (containers) | 30 minutes | Stateless; restart from images |
| Cloudflare Tunnel | 1 hour | Auto-reconnect; SSH fallback available |
| Supabase (PostgreSQL) | 2 hours | Managed service with PITR; JSON fallback active |
| Contabo VPS | 4 hours | Snapshot restoration or rebuild from configuration-as-code |
| InfluxDB (telemetry) | 4 hours | Docker volume restoration from VM snapshot |
| AI Services (Claude API) | Automatic | Circuit breaker triggers Ollama fallback immediately |
| ML Models | 24 hours | Restore from model registry or retrain |
| Environment Configuration | 1 hour | Restore from encrypted offline backup |

### 4.2 Recovery Point Objectives (RPO)

Maximum acceptable data loss per component.

| Component | RPO | Backup Method |
|-----------|-----|---------------|
| Supabase (PostgreSQL) | 1 hour | Continuous backup with point-in-time recovery |
| Docker services | 0 (stateless) | Container images; no persistent state |
| JSON data files | 24 hours | Included in daily VM snapshot |
| InfluxDB telemetry | 24 hours | Docker volume included in VM snapshot |
| Audit logs | 0 (dual-write) | JSON file + Loki real-time streaming |
| Consent records | 0 (dual-write) | Supabase + JSON file (immutable, append-only) |
| ML model weights | N/A | Model registry files; retrain from training data |

### 4.3 DR Scenario-Specific Targets

Reference: Phase 63-06 BCP test plan (`infrastructure/bcpdr/bcp-test-plan.md`) defines 5 DR scenarios:

| Scenario | RTO Target | RPO Target | Recovery Method |
|----------|-----------|-----------|-----------------|
| **Container recovery** | 30 minutes | 0 | Docker service restart / redeploy |
| **Database restore** | 2 hours | 1 hour | Supabase PITR; verify data integrity |
| **Full VM disaster** | 4 hours | 24 hours | New VPS provisioning + snapshot restore |
| **Network partition** | 1 hour | 0 | Cloudflare tunnel reconnect / SSH fallback |
| **Security incident** | 2 hours | 0 | Isolation, forensics, clean redeploy |

---

## 5. Business Continuity Strategies

### 5.1 Docker Container Orchestration

- Docker Swarm provides automatic container restart on failure
- Service health checks detect unresponsive containers
- Rolling updates ensure zero-downtime deployments
- All service definitions maintained as code in `docker-compose.yml`
- Container images stored in registry for rapid redeployment

### 5.2 Database Backup and Recovery

| Database | Backup Strategy | Recovery Strategy |
|----------|----------------|-------------------|
| **Supabase (PostgreSQL)** | Continuous backup with PITR (managed service) | Point-in-time recovery via Supabase dashboard |
| **InfluxDB** | Docker volume included in daily VM snapshots | Volume restoration from snapshot |
| **JSON data files** | Included in daily VM snapshots; version controlled in Git | Restore from snapshot or Git repository |
| **Consent records** | Dual-write (Supabase + JSON); immutable append-only | Restore from either source; reconcile if needed |

### 5.3 Configuration as Code

All infrastructure and application configuration is maintained as code:

- `docker-compose.yml` -- Service definitions, networking, volumes
- `infrastructure/` directory -- Caddy, monitoring, security configuration
- `.env` files -- Encrypted offline backup (not in version control)
- `supabase/migrations/` -- Database schema versioning
- Git repository -- Complete application source code

This enables a full environment rebuild from source in under 4 hours.

### 5.4 Cloudflare Protection and Failover

- DDoS protection for all web traffic
- WAF rules blocking common attack patterns
- Cloudflare Tunnel provides zero-trust network access (no open ports)
- Automatic tunnel reconnection on network interruption
- SSH direct access as fallback if tunnel is unavailable

### 5.5 Circuit Breaker Patterns

External API integrations implement circuit breaker patterns to prevent cascading failures:

| Integration | Circuit Breaker | Fallback |
|-------------|----------------|----------|
| **Claude API** | Timeout + error rate threshold | Ollama local LLM (free, no external dependency) |
| **Supabase** | Connection timeout | JSON file fallback for reads; writes queued |
| **MRI Evolution/FSI** | API timeout | Work orders queued locally; sync on recovery |
| **WhatsApp/Telegram** | Message delivery timeout | Messages queued; retry with backoff |

---

## 6. BCP Testing

### 6.1 Testing Requirements

- **Minimum frequency:** Annual full BCP/DR test
- **Additional triggers:** After any DR invocation, major infrastructure change, or new critical dependency
- **Test scenarios:** Reference `infrastructure/bcpdr/bcp-test-plan.md` for 5 documented test scenarios
- **Test types:** Component tests (quarterly), tabletop exercises (semi-annually), full DR simulation (annually)

### 6.2 Annual Test Schedule

| Quarter | Test Type | Scenario | RTO Verified |
|---------|-----------|----------|-------------|
| Q1 | Component | Docker service recovery (30 min RTO) | Yes |
| Q2 | Tabletop | VM failure + database recovery discussion | Yes |
| Q3 | Component | Network partition + API dependency (1 hr RTO) | Yes |
| Q4 | Full DR | Complete VM disaster recovery (4 hr RTO) | Yes |

### 6.3 Test Results Documentation

All test results must be documented with:

- Test date and participants
- Scenario executed
- RTO/RPO targets vs actual recovery times
- Issues discovered during testing
- Remediation actions with owners and deadlines
- Sign-off by BCP Owner

Test results are stored in `infrastructure/bcpdr/` and reviewed during annual BCP policy review.

### 6.4 Improvement Tracking

- Issues identified during testing are logged as remediation actions
- Each action is assigned an owner and target completion date
- Actions are tracked to completion and verified in subsequent tests
- Lessons learned are incorporated into DR procedures and this policy

---

## 7. Risk Management for BCP Shortfalls

### 7.1 Single VPS Hosting Risk (Contabo)

| Aspect | Detail |
|--------|--------|
| **Risk** | Single point of failure; VPS outage affects all SENTINEL services |
| **Likelihood** | Low (Contabo 99.9% SLA) |
| **Impact** | High (complete service outage) |
| **Current mitigation** | Daily VM snapshots, configuration-as-code, documented rebuild procedure |
| **Recovery** | New VPS provisioning + snapshot restore (4 hr RTO) |
| **Future mitigation** | Multi-region deployment when scale justifies cost |

### 7.2 Cloud API Dependency Risk (Claude, Supabase)

| Aspect | Detail |
|--------|--------|
| **Risk** | Claude API or Supabase outage degrades SENTINEL capability |
| **Likelihood** | Medium (external service dependencies) |
| **Impact** | Medium (degraded but not offline) |
| **Current mitigation** | Ollama fallback for AI; JSON file fallback for database |
| **Recovery** | Automatic via circuit breaker patterns |
| **Residual risk** | Degraded AI quality (Ollama vs Claude); read-only database mode |

### 7.3 Network Connectivity Risk

| Aspect | Detail |
|--------|--------|
| **Risk** | Network outage between VPS and users/BMS devices |
| **Likelihood** | Low |
| **Impact** | High (service inaccessible) |
| **Current mitigation** | Cloudflare Tunnel redundancy; SSH direct access fallback |
| **Recovery** | Tunnel auto-reconnect; manual SSH if needed (1 hr RTO) |
| **Future mitigation** | Secondary ISP connection at VPS level |

### 7.4 Supply Chain Disruption

| Aspect | Detail |
|--------|--------|
| **Risk** | Critical third-party provider discontinues service or suffers breach |
| **Likelihood** | Low |
| **Impact** | High (dependent on severity and provider) |
| **Current mitigation** | Third-party security register with annual review (see `docs/08-security/third-party-security-register.md`); fallback options documented for critical dependencies |
| **Recovery** | Migration plan to alternative provider (timeline depends on provider) |

---

## 8. Roles and Responsibilities

| Role | Responsibility | Scope |
|------|---------------|-------|
| **BCP Owner (Information Security Officer)** | Overall accountability for BCP programme; annual review and approval; test sign-off | Policy and governance |
| **DR Technical Lead (System Administrator)** | Execute DR procedures; infrastructure recovery; test coordination | Technical recovery |
| **Application Lead** | Application-level recovery; data integrity verification; service validation | Application recovery |
| **Database Administrator** | Database recovery (Supabase PITR); data integrity checks | Data recovery |
| **Security Lead** | Incident classification; forensics during security-related DR; compliance notifications | Security and compliance |
| **Communication Coordinator** | Stakeholder notification; FSR communication; status updates | Communication |

### 8.1 Escalation Path

```
Level 1: On-call operator detects issue
    ↓ (15 min assessment)
Level 2: DR Technical Lead notified
    ↓ (if RTO at risk)
Level 3: BCP Owner notified; DR invoked
    ↓ (if client-impacting)
Level 4: Management and FSR notification
```

---

## 9. Privacy Considerations During DR

### 9.1 PI Protection During Recovery

- All backup media containing personal information must remain encrypted
- Access controls must be maintained during emergency operations (no bypassing authentication)
- Recovery procedures must not expose PI to unauthorized personnel
- Temporary access granted during DR must be revoked within 24 hours of resolution

### 9.2 Backup Encryption Requirements

| Backup Type | Encryption | Key Management |
|------------|-----------|----------------|
| VM snapshots | Contabo infrastructure encryption | Contabo managed |
| Supabase backups | AES-256 at rest (Supabase managed) | Supabase managed |
| JSON data files | Part of encrypted VM snapshot | Contabo managed |
| `.env` files (offline backup) | GPG encryption | Manual key management |
| Config exports | GPG encryption | Manual key management |

### 9.3 Access Control During Emergency Operations

- DR team members must authenticate before accessing recovery systems
- Emergency access credentials stored in sealed, encrypted offline storage
- All emergency access logged for post-incident audit
- Principle of least privilege maintained; only grant access needed for specific recovery tasks
- Post-incident access review within 48 hours

---

## 10. Supply Chain Resilience

### 10.1 Third-Party Dependencies

All third-party service dependencies are documented in the Third-Party Security Register (`docs/08-security/third-party-security-register.md`). Key dependencies for BCP:

| Provider | Service | Criticality | Fallback |
|----------|---------|------------|----------|
| **Contabo** | VPS hosting | Critical | Rebuild on alternative provider (documented procedure) |
| **Cloudflare** | CDN/WAF/Tunnel | Critical | Direct IP access; alternative CDN provider |
| **Anthropic** | Claude API | High | Ollama local LLM (automatic circuit breaker) |
| **Supabase** | PostgreSQL hosting | High | JSON file fallback (automatic dual-write) |
| **MRI Evolution/FSI** | CAFM API | Medium | Local work order queue; manual dispatch |
| **Meta/WhatsApp** | Messaging | Medium | Telegram fallback; web portal |
| **Telegram** | Messaging | Medium | WhatsApp fallback; web portal |
| **GitHub** | Source code/CI/CD | Low | Local Git repository; mirror to alternative |

### 10.2 Concentration Risk

- No single third-party provider hosts more than one critical function
- AI processing has local fallback (Ollama) eliminating single-provider dependency
- Database has dual-write architecture eliminating single-database dependency
- Messaging has dual-channel capability (WhatsApp + Telegram)

---

## 11. Communication Plan

### 11.1 Internal Communication

| When | Who | Channel | Content |
|------|-----|---------|---------|
| DR invoked | DR Technical Lead | Internal messaging | Incident summary, ETA, actions |
| Every 30 min during DR | DR Technical Lead | Internal messaging | Status update, progress, blockers |
| DR resolved | BCP Owner | Email + messaging | Resolution summary, post-incident review schedule |

### 11.2 External Communication (FSR and Clients)

| When | Who | Channel | Content |
|------|-----|---------|---------|
| Service disruption > 1 hour | Communication Coordinator | Email | Incident notification, impact, ETA |
| Every 2 hours during extended DR | Communication Coordinator | Email | Status update |
| DR resolved | BCP Owner | Email | Resolution confirmation, root cause summary |
| Post-incident review complete | BCP Owner | Formal report | Full incident report with lessons learned |

**FSR notification:** Promptly notify FSR of any disruption affecting their data or service availability, as required by contractual obligations and the third-party security register.

---

## 12. Post-Incident Review

After every DR invocation or significant incident:

1. **Timeline reconstruction** -- What happened, when, and what actions were taken
2. **RTO/RPO assessment** -- Were recovery targets met? If not, why?
3. **Root cause analysis** -- What caused the disruption?
4. **Improvement actions** -- What changes are needed to prevent recurrence?
5. **Policy update** -- Does this policy or DR procedures need updating?
6. **Stakeholder debrief** -- Summary provided to management and affected clients

Post-incident review must be completed within 5 business days of DR resolution.

---

## 13. Document Control

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-02-04 | SENTINEL Platform Team | Initial policy creation |

**Review schedule:** Annual review required, or triggered by:
- Any DR invocation
- Major infrastructure change
- New critical third-party dependency
- Significant change in business process criticality
- Regulatory or contractual requirement change

---

## 14. References

| Document | Location |
|----------|----------|
| DR Runbook | `infrastructure/bcpdr/dr-runbook.md` |
| BCP Test Plan | `infrastructure/bcpdr/bcp-test-plan.md` |
| BCP/DR Procedures | `docs/08-security/bcp-dr-procedures.md` |
| Third-Party Security Register | `docs/08-security/third-party-security-register.md` |
| Data Privacy Policy | `docs/08-security/data-privacy-policy.md` |
| Consent and Privacy Controls | `docs/08-security/consent-and-privacy.md` |
| Logging Architecture | `docs/08-security/logging-architecture.md` |
| Vulnerability Management | `docs/08-security/vulnerability-management.md` |
| Access Control Implementation | `docs/08-security/access-control-implementation.md` |
| ISO 22301:2019 | Business Continuity Management Systems |
| NIST SP 800-34 | Contingency Planning Guide |

---

*This policy is owned by the Information Security Officer and subject to annual review. Non-compliance must be reported to the BCP Owner for risk assessment and remediation.*
