---
title: "Unified Control Applicability Matrix"
type: "register"
status: "active"
version: "1.0.0"
created: "2026-02-23"
updated: "2026-02-23"
author: "SENTINEL Governance Team"
tags: ["ai-governance", "iso-42001", "nist-ai-rmf", "eu-ai-act", "control-mapping", "compliance"]
domain: "compliance"
audience: "all"
complexity: "advanced"
estimated_read_time: 20
---

# Unified Control Applicability Matrix

## Introduction

This matrix provides a single cross-framework view of all AI governance controls applicable to the SENTINEL BMS Intelligence Platform. It maps controls from three frameworks -- ISO/IEC 42001 (AI Management System), NIST AI Risk Management Framework 1.0, and the EU AI Act -- to concrete SENTINEL implementation evidence.

Each entry identifies:

- The specific control requirement from its source framework
- Where SENTINEL implements the control (code, service, or policy document)
- The evidence artifact that proves the control is operating
- The accountable owner role
- The current implementation status

This matrix consolidates the per-framework mappings in `02-control-mapping-iso42001.md` and `03-control-mapping-nist-airmf.md` into a unified register suitable for cross-framework audit and gap analysis.

## Control Applicability Matrix

### ISO/IEC 42001 Controls

| # | Control ID | Framework | Control Description | SENTINEL Implementation | Evidence Link | Owner | Status |
|---|-----------|-----------|--------------------|-----------------------|--------------|-------|--------|
| 1 | ISO-A.2.2 | ISO 42001 | AI policy and objectives | AI Management Policy defining mode discipline, write policy, and operational boundaries | `docs/08-ai-ml/write-policy-and-rollout.md` | Security Officer | Implemented |
| 2 | ISO-A.2.3 | ISO 42001 | Roles, responsibilities, and authorities | Role segregation across Architecture Lead, AI Engineering Lead, Security/Compliance Lead, Operations Lead | `docs/architecture-repository/governance/architecture-capability.md` | Compliance Lead | Implemented |
| 3 | ISO-A.4.1 | ISO 42001 | AI risk assessment | Risk classification framework with per-use-case risk tiers (limited/high) | `docs/ai-governance/01-risk-classification.md` | AI Engineering Lead | Implemented |
| 4 | ISO-A.4.2 | ISO 42001 | AI risk treatment | Quality gate enforcement with mode-specific thresholds (42 entries across 14 metrics x 3 modes) | `backend/app/services/quality_gate_policy.py` | AI Engineering Lead | Implemented |
| 5 | ISO-A.5.1 | ISO 42001 | Data governance for AI | POPIA-compliant data privacy policy covering 7 PI categories, retention schedules, and cross-border transfers | `docs/09-security/data-privacy-policy.md` | Information Security Officer | Implemented |
| 6 | ISO-A.5.2 | ISO 42001 | Data quality management | Data quality gate with freshness, match coverage, and truth-check metrics; mode-specific confidence scoring | `backend/app/services/health_data_quality_gate.py` | AI Engineering Lead | Implemented |
| 7 | ISO-A.6.1 | ISO 42001 | AI system lifecycle management | 4-mode lifecycle (simulation, shadow_live, live_control, automatic) with phased rollout checklist | `docs/08-ai-ml/write-policy-and-rollout.md` | AI Engineering Lead | Implemented |
| 8 | ISO-A.6.2 | ISO 42001 | Safety validation in AI systems | Safety Interlocks Engine with 6 rule types, 3 severity levels, and defense-in-depth rule matching | `docs/06-safety-compliance/safety-interlocks-engine.md`, `backend/app/services/safety_interlocks.py` | AI Engineering Lead | Implemented |
| 9 | ISO-A.7.1 | ISO 42001 | Third-party AI risk management | Third-party security register covering Anthropic Claude API, WhatsApp, Telegram, and sub-processors | `docs/09-security/third-party-security-register.md` | Security Officer | Partial |
| 10 | ISO-A.8.1 | ISO 42001 | Monitoring and measurement of AI | MLOps monitoring with drift detection, model health scoring, and feedback capture rate tracking | `backend/app/api/mlops.py`, `docs/ai-governance/08-monitoring-and-metrics.md` | MLOps Owner | Partial |
| 11 | ISO-A.8.2 | ISO 42001 | Audit trail and traceability | Immutable audit log with correlation IDs, decision pipeline events, and login audit; encryption at rest | `docs/06-safety-compliance/audit-logging.md`, `backend/app/services/audit_logger.py` | Security Engineering | Implemented |
| 12 | ISO-A.10.1 | ISO 42001 | Human oversight of AI decisions | Tier-based approval workflow: Tier 1 advisory, Tier 2 human approval, Tier 3 auto-execute with quality gates | `backend/app/services/approval_service.py` | Ops Lead | Implemented |
| 13 | ISO-A.10.2 | ISO 42001 | AI system transparency | Recommendation explanations include confidence score, reasoning chain, and evidence references | `backend/app/services/optimization_tier_router.py` | AI Engineering Lead | Partial |

### NIST AI RMF Controls

| # | Control ID | Framework | Control Description | SENTINEL Implementation | Evidence Link | Owner | Status |
|---|-----------|-----------|--------------------|-----------------------|--------------|-------|--------|
| 14 | NIST-GV-1.2 | NIST AI RMF | AI governance and mode discipline | 4-mode write policy with escalating permissions (simulation through live_control); fail-closed on missing metrics | `docs/08-ai-ml/write-policy-and-rollout.md` | AI Engineering Lead | Implemented |
| 15 | NIST-GV-1.5 | NIST AI RMF | Organizational AI risk tolerance | Quality gate thresholds define risk tolerance per mode; live_control treats NA metrics as FAIL | `backend/app/services/quality_gate_policy.py` | Architecture Lead | Implemented |
| 16 | NIST-GV-3.1 | NIST AI RMF | AI workforce diversity and competence | AI competence register and training programme | `docs/ai-governance/evidence/training/` | HR + Compliance | Planned |
| 17 | NIST-MP-3.5 | NIST AI RMF | Human-AI decision allocation | Tier routing engine allocates decisions by confidence and risk level; HIGH/CRITICAL locked to Tier 2 maximum | `backend/app/services/optimization_tier_router.py`, `backend/app/services/approval_service.py` | Ops Lead | Implemented |
| 18 | NIST-MS-1.1 | NIST AI RMF | Quality gates for AI decisions | 14-metric quality gate evaluator with CAP_CONFIDENCE, SUPPRESS_TIER3, BLOCK_WRITES, and NORMAL enforcement actions | `backend/app/services/quality_gate_evaluator.py` | AI Engineering Lead | Implemented |
| 19 | NIST-MS-2.6 | NIST AI RMF | Safety and security of AI systems | Safety engine validates all device control operations; 8 default rules covering temperature, pressure, interlocks, runtime | `backend/app/services/safety_interlocks.py`, `backend/app/data/safety_rules.json` | AI Engineering Lead | Implemented |
| 20 | NIST-MS-2.8 | NIST AI RMF | AI system logging and auditability | Decision pipeline event logger with 7 stages, Grafana dashboards, Loki integration, and PARASITE decision audit trail | `backend/app/services/decision_event_logger.py`, `docs/06-safety-compliance/audit-logging.md` | Security Engineering | Implemented |
| 21 | NIST-MG-2.4 | NIST AI RMF | AI system deactivation (kill switch) | Global, per-site, per-equipment, and auto-downgrade kill switches; emergency stop endpoint | `docs/08-ai-ml/write-policy-and-rollout.md` (Section D), `docs/06-safety-compliance/safety-interlocks-engine.md` | Ops Lead | Implemented |
| 22 | NIST-MG-4.3 | NIST AI RMF | Incident response for AI systems | NIST SP 800-61-aligned incident response with BMS-specific procedures (unauthorized device control, safety bypass, anomalous writes) | `docs/09-security/incident-response-process.md` | Security Officer | Implemented |

### EU AI Act Controls

| # | Control ID | Framework | Control Description | SENTINEL Implementation | Evidence Link | Owner | Status |
|---|-----------|-----------|--------------------|-----------------------|--------------|-------|--------|
| 23 | EU-Art.4 | EU AI Act | AI literacy obligation | Security awareness training programme including AI-specific privacy-by-design and POPIA modules | `docs/09-security/data-privacy-policy.md` (Section 15) | HR + Compliance | Planned |
| 24 | EU-Art.5 | EU AI Act | Prohibited AI practices | No prohibited practices identified; SENTINEL does not perform social scoring, real-time biometrics, or emotion recognition | `docs/ai-governance/01-risk-classification.md` | Compliance Lead | Implemented |
| 25 | EU-Art.9 | EU AI Act | Risk management system for high-risk AI | Risk classification per AI use case; quality gate enforcement prevents high-risk actions without controls | `docs/ai-governance/01-risk-classification.md`, `backend/app/services/quality_gate_evaluator.py` | AI Engineering Lead | Implemented |
| 26 | EU-Art.10 | EU AI Act | Data and data governance | Data privacy policy with 9 retention categories, consent management service, and PIA process for new processing activities | `docs/09-security/data-privacy-policy.md`, `backend/app/services/consent_service.py` | Information Security Officer | Implemented |
| 27 | EU-Art.12 | EU AI Act | Record-keeping and traceability | Immutable audit trail with correlation IDs linking recommendations through tier routing, safety validation, device writes, and COV verification | `docs/06-safety-compliance/audit-logging.md`, `backend/app/services/audit_logger.py` | Security Engineering | Implemented |
| 28 | EU-Art.13 | EU AI Act | Transparency and provision of information | Model cards for active ML models (AHU, CHILLER, FCU, UPS, GENERATOR, DALI) | `docs/08-ai-ml/` | AI Engineering Lead | Planned |
| 29 | EU-Art.14 | EU AI Act | Human oversight measures | Approval service enforces human-in-the-loop for Tier 2 decisions; HIGH/CRITICAL risk locked to human approval permanently | `backend/app/services/approval_service.py` | Ops Lead | Implemented |
| 30 | EU-Art.15 | EU AI Act | Accuracy, robustness, and cybersecurity | Health data quality gate with mode-specific confidence; safety interlocks prevent out-of-range actions; Fernet encryption at rest | `backend/app/services/health_data_quality_gate.py`, `backend/app/services/encryption_service.py` | AI Engineering Lead | Implemented |
| 31 | EU-Art.50 | EU AI Act | Transparency obligations for AI-generated content | AI recommendations include confidence scores and tier classification; users informed when interacting with AI chat | `backend/app/services/optimization_tier_router.py` | AI Engineering Lead | Partial |
| 32 | EU-Art.62 | EU AI Act | Reporting of serious incidents | Incident response process with P1-P4 severity classification, POPIA Section 22 breach notification, and FSR escalation templates | `docs/09-security/incident-response-process.md` | Security Officer | Implemented |

## Gap Summary

The following controls are marked as Planned or Partial and require completion:

| # | Control ID | Gap Description | Target Date | Priority |
|---|-----------|----------------|-------------|----------|
| 1 | ISO-A.7.1 | Third-party AI risk register needs AI-specific expansion beyond security focus | 2026-04-15 | Medium |
| 2 | ISO-A.8.1 | Prometheus-grade control effectiveness metrics not fully wired; monitoring evidence split across systems | 2026-04-15 | Medium |
| 3 | ISO-A.10.2 | Recommendation transparency needs standardised explanation templates | 2026-04-30 | Low |
| 4 | NIST-GV-3.1 | AI competence register and role-based training programme not established | 2026-04-30 | Medium |
| 5 | EU-Art.4 | AI literacy training programme planned but not yet delivered | 2026-04-30 | Medium |
| 6 | EU-Art.13 | Model cards incomplete for all 6 active ML models | 2026-03-31 | High |
| 7 | EU-Art.50 | AI-generated content marking not fully standardised across all interfaces | 2026-04-30 | Low |

## Cross-Reference Index

The following table shows where a single SENTINEL component satisfies controls across multiple frameworks simultaneously:

| SENTINEL Component | ISO 42001 | NIST AI RMF | EU AI Act |
|--------------------|-----------|-------------|-----------|
| `quality_gate_policy.py` / `quality_gate_evaluator.py` | A.4.2, A.8.1 | MS-1.1, GV-1.5 | Art.9, Art.15 |
| `approval_service.py` | A.10.1 | MP-3.5 | Art.14 |
| `safety_interlocks.py` | A.6.2 | MS-2.6 | Art.15 |
| `audit_logger.py` / `decision_event_logger.py` | A.8.2 | MS-2.8 | Art.12 |
| `write-policy-and-rollout.md` | A.2.2, A.6.1 | GV-1.2 | -- |
| `data-privacy-policy.md` / `consent_service.py` | A.5.1 | -- | Art.10, Art.26 |
| `incident-response-process.md` | -- | MG-4.3 | Art.62 |
| `optimization_tier_router.py` | A.10.2 | MP-3.5 | Art.50 |
| Kill switches (write policy Section D) | -- | MG-2.4 | -- |

## Review Schedule

- **Monthly:** Review control statuses and update evidence links
- **Quarterly:** Full gap analysis with target date tracking
- **Annually:** Comprehensive matrix review aligned with framework updates

## Related Documents

- [ISO 42001 Control Mapping](02-control-mapping-iso42001.md) -- Detailed ISO 42001 mapping
- [NIST AI RMF Control Mapping](03-control-mapping-nist-airmf.md) -- Detailed NIST AI RMF mapping
- [Risk Classification](01-risk-classification.md) -- AI use-case risk tiers
- [Write Policy and Rollout](../08-ai-ml/write-policy-and-rollout.md) -- Mode discipline
- [Safety Interlocks Engine](../06-safety-compliance/safety-interlocks-engine.md) -- Safety rules
- [Audit Logging](../06-safety-compliance/audit-logging.md) -- Audit trail
- [Data Privacy Policy](../09-security/data-privacy-policy.md) -- POPIA compliance
- [Incident Response Process](../09-security/incident-response-process.md) -- Incident handling
