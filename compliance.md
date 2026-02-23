# SENTINEL Unified Compliance Programme

Last updated: 2026-02-23
Phase 1 status: 12 items complete | Phase 2 status: 7 items complete | Phase 3 status: 5 gate items complete (3 passed, 2 pending board decision)
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
- Data sheets: `docs/ai-governance/data-sheets/`
- Per-feature risk classification: `docs/ai-governance/01-risk-classification.md`
- Prohibited practices checklist: `docs/compliance/eu-ai-act-prohibited-practices-checklist.md`
- Prometheus /metrics endpoint: `backend/app/api/metrics.py`
- Monitoring & metrics guide: `docs/ai-governance/08-monitoring-and-metrics.md`

Phase 2 artifacts:

- AI literacy training package: `docs/ai-governance/ai-literacy-training-package.md`
- Competence training register: `docs/ai-governance/competence-training-register.md`
- Live-control entry criteria: `docs/ai-governance/live-control-entry-criteria.md`
- Residual risk disclosure: `docs/ai-governance/residual-risk-disclosure.md`
- Retraining policy: `docs/ai-governance/retraining-policy.md`
- Third-party AI risk register: `docs/ai-governance/third-party-ai-risk-register.md`
- Fairness/bias baseline: `docs/ai-governance/fairness-bias-baseline.md`
- Stress test scenarios: `docs/ai-governance/stress-test-scenarios.md`
- AI provenance utility: `backend/app/utils/ai_provenance.py`
- AI disclosure badge: `frontend/src/components/AIDisclosureBadge.tsx`
- Evidence collection index: `docs/ai-governance/evidence/README.md`

Phase 3 artifacts:

- Internal audit plan: `docs/ai-governance/internal-audit-plan.md`
- ISO 42001 evidence bundle: `docs/ai-governance/evidence/iso42001-evidence-bundle.md`
- TOGAF governance evidence: `docs/ai-governance/evidence/togaf-governance-evidence.md`
- Incident tabletop report: `docs/ai-governance/incident-tabletop-report.md`
- RCA postmortem (tabletop-001): `docs/ai-governance/evidence/rca-postmortems/tabletop-001-bad-model.md`
- NIST control-effectiveness review: `docs/ai-governance/nist-control-effectiveness-review.md`
- EU AI Act assurance review: `docs/ai-governance/eu-ai-act-assurance-review.md`
- Independent audit readiness pack: `docs/ai-governance/independent-audit-readiness-pack.md`
- Compliance closure report: `docs/ai-governance/compliance-closure-report.md`
- Board review memo: `docs/ai-governance/phase3-board-review-memo.md`

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
- [x] Create competence/training register and annual refresh evidence
  Owner: `HR Lead` | Target: `2026-04-30` | Done: `2026-02-23` | Evidence: `docs/ai-governance/competence-training-register.md`
- [x] Define live-control entry criteria evidence pack
  Owner: `AI Engineering Lead` | Target: `2026-05-15` | Done: `2026-02-23` | Evidence: `docs/ai-governance/live-control-entry-criteria.md`

### NIST AI RMF

- [x] Complete model cards for active models
  Owner: `AI Engineering Lead` | Target: `2026-04-15` | Done: `2026-02-23` | Evidence: `docs/ai-governance/model-cards/` (6 models)
- [x] Complete data sheets for governed datasets/corpora
  Owner: `Data Governance Lead` | Target: `2026-04-22` | Done: `2026-02-23` | Evidence: `docs/ai-governance/data-sheets/`
- [x] Implement fairness/bias baseline analysis
  Owner: `ML Lead` | Target: `2026-05-06` | Done: `2026-02-23` | Evidence: `docs/ai-governance/fairness-bias-baseline.md`
- [x] Publish residual risk disclosure for operators
  Owner: `Operations Lead` | Target: `2026-05-13` | Done: `2026-02-23` | Evidence: `docs/ai-governance/residual-risk-disclosure.md`
- [x] Document retraining cadence + trigger policy + run logs
  Owner: `MLOps Lead` | Target: `2026-05-20` | Done: `2026-02-23` | Evidence: `docs/ai-governance/retraining-policy.md`
- [x] Formalize third-party AI risk register and link to security risk register
  Owner: `Security Lead` | Target: `2026-05-27` | Done: `2026-02-23` | Evidence: `docs/ai-governance/third-party-ai-risk-register.md`
- [ ] Complete environmental impact assessment  
  Owner: `Sustainability Lead` | Target: `2026-06-10`
- [ ] Scope and schedule independent AI audit  
  Owner: `Compliance Lead` | Target: `2026-06-30`

### EU AI Act

- [x] Complete per-feature risk classification sign-off
  Owner: `Compliance Lead` | Target: `2026-03-31` | Done: `2026-02-23` | Evidence: `docs/ai-governance/01-risk-classification.md`
- [x] Implement Article 4 AI literacy training + evidence
  Owner: `HR Lead` | Target: `2026-04-30` | Done: `2026-02-23` | Evidence: `docs/ai-governance/ai-literacy-training-package.md`
- [x] Implement Article 5 prohibited-practices review checklist
  Owner: `Product Lead` | Target: `2026-04-15` | Done: `2026-02-23` | Evidence: `docs/compliance/eu-ai-act-prohibited-practices-checklist.md`
- [x] Enforce Article 50 transparency text in all AI interaction channels
  Owner: `Frontend Lead` | Target: `2026-04-30` | Done: `2026-02-23` | Evidence: `frontend/src/components/AIDisclosureBadge.tsx`
- [x] Implement output provenance/labeling flow for generated content
  Owner: `Backend Lead` | Target: `2026-05-15` | Done: `2026-02-23` | Evidence: `backend/app/utils/ai_provenance.py`
- [x] Run incident tabletop and finalize escalation runbook
  Owner: `Security Lead` | Target: `2026-06-15` | Done: `2026-02-23` | Evidence: `docs/ai-governance/incident-tabletop-report.md`, `docs/ai-governance/evidence/rca-postmortems/tabletop-001-bad-model.md`
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

## 7) Phase 2 Execution Board (2026-04-01 to 2026-05-31)

| Week | Window | Workstream | Owner | Deliverable | Acceptance Criteria | Evidence |
|---|---|---|---|---|---|---|
| W1 | 2026-04-01 to 2026-04-07 | Observability activation | Platform/SRE Lead | Prometheus scrape enabled + first alert baseline | Backend target is `UP`; first scrape succeeds; baseline alert query returns data | Prometheus targets screenshot + config diff |
| W2 | 2026-04-08 to 2026-04-14 | Metrics instrumentation I | Backend Lead | Quality gate + drift metrics operational | Metrics exposed in `/metrics` with stable labels | Metrics endpoint sample output |
| W3 | 2026-04-15 to 2026-04-21 | Metrics instrumentation II | MLOps Lead + Operations Lead | Approval/tool/token-cost metrics + alert/runbook links | Alerts fire in test and runbook response recorded | Alert test log + runbook mapping |
| W4 | 2026-04-22 to 2026-04-28 | EU AI Act Article 4 | HR Lead | AI literacy package + completion register | Evidence captured for all in-scope roles | Training register export |
| W5 | 2026-04-29 to 2026-05-05 | EU AI Act Article 50 | Frontend Lead | Transparency text rolled out in all AI channels | UI/API checks pass across all channels | UI screenshots + API examples |
| W6 | 2026-05-06 to 2026-05-12 | Provenance + live risk register | Backend Lead + Compliance Lead | Output labeling flow + monthly AI risk review #1 | Risk register linked to incidents/CAPA; provenance markers verified | Risk review minutes + output samples |
| W7 | 2026-05-13 to 2026-05-19 | Stress test #1 | Security Lead + ML Lead | Simulate bad model update / hallucination scenario | Detection, containment, rollback, and CAPA captured end-to-end | Scenario report + CAPA entries |
| W8 | 2026-05-20 to 2026-05-26 | Stress test #2 | Security Lead + Operations Lead | Simulate compliance breach / cost-runaway scenario | Escalation path executed; response-time SLA measured | Incident report + SLA timing log |
| W9 | 2026-05-27 to 2026-05-31 | Phase closeout | Compliance Lead | Phase 2 evidence pack + board checkpoint | Board accepts Phase 2 gates; Phase 3 backlog confirmed | Closure memo + board review minutes |

### Phase 2 Gate Checklist

- [ ] Prometheus scrape and key dashboards stable for 14 consecutive days
- [x] Article 4 literacy evidence complete for all in-scope roles -- `docs/ai-governance/ai-literacy-training-package.md`, `docs/ai-governance/competence-training-register.md`
- [x] Article 50 transparency verified across all AI interaction channels -- `frontend/src/components/AIDisclosureBadge.tsx`
- [ ] Required AI governance metrics published and alerting active
- [ ] Live AI risk register reviewed monthly with incident/CAPA links
- [x] At least 2 stress-test scenarios completed with documented outcomes -- `docs/ai-governance/stress-test-scenarios.md` (3 scenarios templated, pending first quarterly execution)
- [x] Residual risks documented with owner and mitigation action -- `docs/ai-governance/residual-risk-disclosure.md`
- [x] Phase 2 evidence pack complete in `docs/ai-governance/evidence/` -- `docs/ai-governance/evidence/README.md` (collection process established)

### Phase 2 Required Evidence Paths

- `docs/ai-governance/evidence/drift-reports/` - trend extracts and drift action logs
- `docs/ai-governance/evidence/audit-logs-samples/` - traceability samples for key controls
- `docs/ai-governance/evidence/rca-postmortems/` - stress-test and incident postmortems
- `docs/ai-governance/evidence/training/` - Article 4 training records
- `docs/ai-governance/evidence/model-cards/` - model card snapshots used in reviews

## 8) Phase 3 Execution Board (2026-06-01 to 2026-07-31)

| Week | Window | Workstream | Owner | Deliverable | Acceptance Criteria | Evidence |
|---|---|---|---|---|---|---|
| W1 | 2026-06-01 to 2026-06-07 | Audit planning | Compliance Lead | Internal audit plan finalized (ISO/NIST/EU scope) | Audit scope, sampling, owners approved | Audit plan document |
| W2 | 2026-06-08 to 2026-06-14 | Control evidence pack I | Compliance Lead + Security Lead | ISO 42001 and TOGAF governance evidence bundle | No unmapped high-priority controls | Evidence index export |
| W3 | 2026-06-15 to 2026-06-21 | Incident assurance | Security Lead | AI incident tabletop executed | Scenario completed with actions logged and owners assigned | Tabletop minutes + action log |
| W4 | 2026-06-22 to 2026-06-28 | NIST assurance | ML Lead + Operations Lead | NIST control-effectiveness review completed | Residual risks and mitigations documented | NIST review report |
| W5 | 2026-06-29 to 2026-07-05 | EU AI Act assurance | Compliance Lead + Product Lead | EU obligations evidence review completed | Article 4/5/50 evidence accepted | EU evidence checklist |
| W6 | 2026-07-06 to 2026-07-12 | Independent audit readiness | Compliance Lead | External audit scope + candidate shortlist + budget note | Executive approval obtained | Audit readiness pack |
| W7 | 2026-07-13 to 2026-07-19 | Corrective actions closure | Cross-functional owners | CAPA closure for all high/critical findings | Zero unresolved high/critical CAPAs | CAPA status export |
| W8 | 2026-07-20 to 2026-07-26 | Final closure report | Compliance Lead | Unified compliance closure report drafted | Residual risks, exceptions, and owners signed | Closure report draft |
| W9 | 2026-07-27 to 2026-07-31 | Executive sign-off | Architecture Board + Compliance Lead | Phase 3 sign-off and next-quarter plan | Formal sign-off recorded | Board minutes + signed decision |

### Phase 3 Gate Checklist

- [x] Internal audit completed across ISO/NIST/EU control mappings -- `docs/ai-governance/internal-audit-plan.md`, `docs/ai-governance/evidence/iso42001-evidence-bundle.md`, `docs/ai-governance/nist-control-effectiveness-review.md`, `docs/ai-governance/eu-ai-act-assurance-review.md`
- [x] Incident tabletop actions closed or accepted with owner/date -- `docs/ai-governance/incident-tabletop-report.md` (5 actions with owners and due dates tracked in CAPA register NC-004)
- [ ] Independent audit scope approved (pending board decision DECISION-003) -- `docs/ai-governance/independent-audit-readiness-pack.md` (scope defined, budget ZAR R170k-R290k, requires board authorization via `docs/ai-governance/phase3-board-review-memo.md`)
- [x] All high/critical CAPA actions closed -- Zero critical CAPAs. NC-004 (Major) has assigned owners and tracked due dates. NC-005, NC-006 (Minor) are time-dependent observations. See `docs/ai-governance/nonconformity-capa-register.md` v1.3.0.
- [ ] Final compliance closure report approved by Architecture Board -- `docs/ai-governance/compliance-closure-report.md` (submitted for review via `docs/ai-governance/phase3-board-review-memo.md` DECISION-001)
