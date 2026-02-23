# SENTINEL Unified Compliance Programme

Last updated: 2026-02-23
Phase 1 status: 12 items complete
Scope: `/opt/bms-intelligence` (SENTINEL only)

## 1) Framework Scope

This programme unifies:

- ISO/IEC 42001 (AI Management System)
- NIST AI RMF 1.0
- EU AI Act readiness
- TOGAF 10 Foundation enablement (architecture governance structure)
- FSR security/compliance alignment (as linked control baseline)

## 2) Current Baseline

Completed baseline artifacts:

- AI governance pack under `docs/ai-governance/`
- EU AI Act register: `docs/compliance/eu-ai-act-compliance-register.md`
- EU AI Act policy: `docs/compliance/eu-ai-act-policy.md`
- EU AI Act internal audit draft: `docs/compliance/eu-ai-act-internal-audit-2026Q2.md`
- EU AI addendum in incident policy: `docs/09-security/incident-response-policy.md`
- TOGAF-aligned architecture repository scaffold: `docs/architecture-repository/`
- ADM mapping: `docs/architecture-repository/governance/adm-mapping-sentinel.md`
- Architecture capability model: `docs/architecture-repository/governance/architecture-capability.md`
- AI Management Policy: `docs/ai-governance/ai-management-policy.md`
- AIMS scope finalized: `docs/ai-governance/00-scope-and-system-boundaries.md`
- Management review template: `docs/ai-governance/management-review-template.md`
- CAPA register: `docs/ai-governance/nonconformity-capa-register.md`
- Control applicability matrix: `docs/ai-governance/control-applicability-matrix.md`
- Architecture Board charter: `docs/architecture-repository/governance/architecture-board-charter.md`
- Model cards (6): `docs/ai-governance/model-cards/`
- Data sheets: `docs/ai-governance/evidence/data-sheets/`
- Per-feature risk classification: `docs/ai-governance/01-risk-classification.md`
- Prohibited practices checklist: `docs/compliance/eu-ai-act-prohibited-practices-checklist.md`
- Prometheus /metrics endpoint: `backend/app/api/metrics.py`
- Monitoring & metrics guide: `docs/ai-governance/08-monitoring-and-metrics.md`

## 3) Consolidated Gap Backlog

### ISO/IEC 42001 (AIMS)

- [x] Finalize AIMS scope statement, exclusions, and boundaries
  Owner: `Compliance Lead` | Target: `2026-03-07` | Done: `2026-02-23` | Evidence: `docs/ai-governance/00-scope-and-system-boundaries.md`
- [x] Publish AI Management Policy with measurable objectives/KPIs
  Owner: `Information Security Officer` | Target: `2026-03-14` | Done: `2026-02-23` | Evidence: `docs/ai-governance/ai-management-policy.md`
- [x] Establish management review cadence and decision logs
  Owner: `Architecture Lead` | Target: `2026-03-21` | Done: `2026-02-23` | Evidence: `docs/ai-governance/management-review-template.md`
- [x] Implement AI nonconformity + CAPA workflow
  Owner: `Compliance Lead` | Target: `2026-03-28` | Done: `2026-02-23` | Evidence: `docs/ai-governance/nonconformity-capa-register.md`
- [x] Complete control applicability matrix with owners/evidence links
  Owner: `Compliance Lead` | Target: `2026-04-15` | Done: `2026-02-23` | Evidence: `docs/ai-governance/control-applicability-matrix.md`
- [ ] Create competence/training register and annual refresh evidence  
  Owner: `HR Lead` | Target: `2026-04-30`
- [ ] Define live-control entry criteria evidence pack  
  Owner: `AI Engineering Lead` | Target: `2026-05-15`

### NIST AI RMF

- [x] Complete model cards for active models
  Owner: `AI Engineering Lead` | Target: `2026-04-15` | Done: `2026-02-23` | Evidence: `docs/ai-governance/model-cards/` (6 models)
- [x] Complete data sheets for governed datasets/corpora
  Owner: `Data Governance Lead` | Target: `2026-04-22` | Done: `2026-02-23` | Evidence: `docs/ai-governance/evidence/data-sheets/`
- [ ] Implement fairness/bias baseline analysis  
  Owner: `ML Lead` | Target: `2026-05-06`
- [ ] Publish residual risk disclosure for operators  
  Owner: `Operations Lead` | Target: `2026-05-13`
- [ ] Document retraining cadence + trigger policy + run logs  
  Owner: `MLOps Lead` | Target: `2026-05-20`
- [ ] Formalize third-party AI risk register and link to security risk register  
  Owner: `Security Lead` | Target: `2026-05-27`
- [ ] Complete environmental impact assessment  
  Owner: `Sustainability Lead` | Target: `2026-06-10`
- [ ] Scope and schedule independent AI audit  
  Owner: `Compliance Lead` | Target: `2026-06-30`

### EU AI Act

- [x] Complete per-feature risk classification sign-off
  Owner: `Compliance Lead` | Target: `2026-03-31` | Done: `2026-02-23` | Evidence: `docs/ai-governance/01-risk-classification.md`
- [ ] Implement Article 4 AI literacy training + evidence  
  Owner: `HR Lead` | Target: `2026-04-30`
- [x] Implement Article 5 prohibited-practices review checklist
  Owner: `Product Lead` | Target: `2026-04-15` | Done: `2026-02-23` | Evidence: `docs/compliance/eu-ai-act-prohibited-practices-checklist.md`
- [ ] Enforce Article 50 transparency text in all AI interaction channels  
  Owner: `Frontend Lead` | Target: `2026-04-30`
- [ ] Implement output provenance/labeling flow for generated content  
  Owner: `Backend Lead` | Target: `2026-05-15`
- [ ] Run incident tabletop and finalize escalation runbook  
  Owner: `Security Lead` | Target: `2026-06-15`
- [ ] Publish final gap closure report and residual risk sign-off  
  Owner: `Compliance Lead` | Target: `2026-07-15`

### TOGAF 10 Enablement

- [ ] Complete TOGAF Foundation study plan  
  Owner: `Architecture Lead` | Target: `2026-03-15`
- [ ] Book and sit TOGAF 10 Level 1 exam  
  Owner: `Architecture Lead` | Target: `2026-04-30`
- [x] Start recurring Architecture Board minutes and action log
  Owner: `Architecture Lead` | Target: `2026-03-31` | Done: `2026-02-23` | Evidence: `docs/architecture-repository/governance/architecture-board-charter.md`
- [x] Keep ADM mapping linked to maintained implementation evidence
  Owner: `Architecture Lead` | Target: `2026-04-15` | Done: `2026-02-23` | Evidence: `docs/architecture-repository/governance/adm-mapping-sentinel.md`

### Observability Control-Effectiveness

- [x] Add Prometheus-format `/metrics` endpoint in SENTINEL backend
  Owner: `Backend Lead` | Target: `2026-04-15` | Done: `2026-02-23` | Evidence: `backend/app/api/metrics.py`
- [ ] Enable backend scrape in `/opt/aimthelaw/config/prometheus.yml`  
  Owner: `Platform/SRE Lead` | Target: `2026-04-22`
- [ ] Validate scrape health + Grafana signal quality  
  Owner: `Platform/SRE Lead` | Target: `2026-04-29`
- [ ] Publish AI governance metrics  
  Owner: `MLOps Lead` | Target: `2026-05-20`
  - [ ] quality gate pass/fail by rule
  - [ ] drift score by model/corpus
  - [ ] tool-call error rate
  - [ ] approval latency/failure rate
  - [ ] token/cost by route and tenant
- [ ] Add alert rules mapped to runbooks  
  Owner: `Operations Lead` | Target: `2026-05-31`

## 4) Delivery Roadmap

### Phase 1: Foundations (2026-02-23 to 2026-03-31)

Outcomes:

- Baseline governance artifacts complete and cross-linked
- Architecture governance structure active
- Compliance backlog normalized with owners

Must deliver:

- Final AIMS scope and AI management policy
- Ownership/approval matrix for unified controls
- TOGAF study completion and exam booking

### Phase 2: Control Implementation (2026-04-01 to 2026-05-31)

Outcomes:

- Core controls implemented and measurable
- Governance evidence flows are operational

Must deliver:

- Prometheus metrics endpoint and scrape wiring
- AI literacy register, prohibited-practices checklist, transparency rollout
- Model cards, data sheets, retraining policy baseline

### Phase 3: Assurance and Closure (2026-06-01 to 2026-07-31)

Outcomes:

- Internal assurance completed with residual risk transparency
- Executive-ready compliance pack

Must deliver:

- Internal audit cycle (ISO/NIST/EU mapping evidence)
- Incident tabletop and postmortem package
- Final closure report with open-risk exceptions

## 5) Governance Cadence

- Weekly: engineering/compliance working session (control implementation)
- Monthly: Architecture Board and compliance review
- Quarterly: formal management review with KPI trend and CAPA status

## 6) Success Criteria

- 100% in-scope AI features classified with owner sign-off
- No placeholder safety path in production approval logic
- Cross-framework control matrix kept current in `docs/ai-governance/`
- Measurable control-effectiveness telemetry active
- Internal audit completed with no unresolved critical findings
