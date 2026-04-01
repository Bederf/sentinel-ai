---
title: "Third-Party AI Risk Register"
type: "register"
status: "active"
version: "1.0.0"
created: "2026-02-23"
updated: "2026-02-23"
author: "SENTINEL Governance Team"
tags: ["ai-governance", "third-party", "risk-register", "nist-ai-rmf", "anthropic", "ollama"]
domain: "compliance"
audience: "all"
complexity: "intermediate"
estimated_read_time: 12
nist_reference: "GV 4.2"
---

# Third-Party AI Risk Register

## 1. Purpose

This register documents AI-specific risks associated with third-party AI providers used by the SENTINEL BMS Intelligence Platform. It extends the security-focused [Third-Party Security Register](../09-security/third-party-security-register.md) with assessments specific to AI model behaviour, output quality, vendor dependency, and compliance obligations.

**Why a separate register?** The security register covers data protection, access control, and breach response. This register covers risks unique to AI systems: model version drift, hallucination, output quality degradation, and the impact of vendor AI changes on SENTINEL's operational decisions.

---

## 2. Scope

This register covers all external AI services that:

- Provide inference, generation, or analysis capabilities used by SENTINEL
- Could influence recommendations, predictions, or explanations shown to operators
- Process building data through AI/ML models not controlled by SENTINEL

**Exclusions:** SENTINEL's own ML models (LSTM, Autoencoder) are governed by the [Retraining Policy](retraining-policy.md), not this register.

---

## 3. Third-Party AI Providers

### 3.1 Anthropic (Claude API)

| Attribute | Detail |
|-----------|--------|
| **Provider** | Anthropic, PBC |
| **Service** | Claude API -- LLM inference for chat, analysis, optimisation explanations, and natural-language summaries |
| **Current model** | claude-sonnet-4-20250514 |
| **Available model** | claude-opus-4-20250514 |
| **Integration point** | `backend/app/services/` -- chat service, explanation service, analysis pipeline |
| **Data sent to provider** | Building telemetry summaries, equipment status, comfort complaints, occupancy patterns. **No PII is sent** -- names, phone numbers, and personal identifiers are stripped before API calls. |
| **Data retained by provider** | Ephemeral processing only. Per Anthropic API terms, API data is not used for model training and is not retained beyond the request lifecycle. |
| **POPIA cross-border transfer** | United States. Legal basis: POPIA Section 72(1)(a) -- adequate safeguards via DPA; Section 72(1)(b) -- consent obtained for cross-border transfer. |
| **PIA reference** | [PIA-2026-001: Claude API](../09-security/pia-claude-api.md) |
| **Risk rating** | **MEDIUM** |
| **Review cadence** | Quarterly |
| **Agreement date** | 2025-06-01 |
| **Next review** | 2026-06-01 |

#### AI-Specific Risks

| Risk ID | Risk | Likelihood | Impact | Mitigation | Residual Level |
|---------|------|-----------|--------|------------|----------------|
| TP-AI-001 | **Model version change without notice** -- Anthropic updates the underlying model, changing response quality, style, or reasoning patterns. | Medium | Medium | Pin model version in API configuration (`claude-sonnet-4-20250514`); shadow-test new versions for 7 days before promotion; AI Engineering Lead approves version changes. | Low |
| TP-AI-002 | **Hallucination in safety-critical context** -- Claude generates plausible but incorrect technical information about equipment operation, setpoints, or safety limits. | Medium | High | Safety interlocks validate all setpoints independently of LLM output; LLM output is never used to drive equipment control decisions directly; explanations are advisory only; RAG grounds responses in verified building data. | Low |
| TP-AI-003 | **API unavailability** -- Anthropic API experiences downtime, rate limiting, or degraded performance. | Low | Medium | Ollama local LLM fallback is configured and tested; chat and explanation services gracefully degrade to local inference; no equipment control depends on Claude API availability. | Low |
| TP-AI-004 | **Cost runaway** -- Unexpected increase in API token usage due to verbose prompts, retry loops, or abuse. | Low | Low | Token budget enforced per request; daily spending cap configured; monitoring alerts on spend anomalies; rate limiting on chat and explanation endpoints. | Low |
| TP-AI-005 | **Data leakage through prompts** -- Sensitive building data or operational details inadvertently included in prompts could be exposed. | Low | Medium | PII stripping before API calls; prompt templates reviewed for data minimisation; Anthropic does not retain API data for training; cross-border transfer governed by POPIA consent. | Low |

### 3.2 Ollama (Self-Hosted LLM)

| Attribute | Detail |
|-----------|--------|
| **Provider** | Ollama (open-source, self-hosted) |
| **Service** | Local LLM inference -- fallback for chat when Claude API is unavailable |
| **Current model** | Configurable (default: llama3) |
| **Integration point** | `backend/app/services/` -- chat service fallback path |
| **Data sent to provider** | None -- all processing stays on the SENTINEL VPS. Same data as Claude API (building telemetry, equipment status) but never leaves the server. |
| **Data retained by provider** | N/A -- self-hosted, no external data transfer |
| **POPIA cross-border transfer** | None -- data stays on-premise (Contabo VPS, South Africa) |
| **Risk rating** | **LOW** (self-hosted, no data leaves premises) |
| **Review cadence** | Semi-annual |

#### AI-Specific Risks

| Risk ID | Risk | Likelihood | Impact | Mitigation | Residual Level |
|---------|------|-----------|--------|------------|----------------|
| TP-AI-006 | **Lower quality responses** -- Local LLM produces less accurate, less coherent, or less helpful responses compared to Claude API. | High | Low | Confidence scoring on all LLM outputs; user-facing disclosure that responses are from a local model; operators can wait for Claude API restoration for complex queries. | Low |
| TP-AI-007 | **Resource consumption on VPS** -- Ollama inference consumes significant CPU/RAM on the shared VPS, potentially degrading other SENTINEL services. | Medium | Medium | Request queueing with configurable concurrency limit; inference timeout (30 seconds default); resource monitoring with alerts; Ollama process priority set below API server. | Low |
| TP-AI-008 | **Model supply chain risk** -- Downloaded model weights from Ollama registry could be tampered with or contain unexpected behaviour. | Low | Medium | Pin model versions and checksums; download models from official Ollama registry only; verify model hash after download; restrict Ollama network access to localhost only. | Low |

---

## 4. Vendor Change Notification Process

When a third-party AI provider changes their model, terms of service, or data handling practices, the following process applies:

### 4.1 Monitoring

| Activity | Frequency | Responsibility |
|----------|-----------|----------------|
| Monitor Anthropic changelog and API announcements | Weekly | AI Engineering Lead |
| Monitor Ollama releases for security patches | Monthly | MLOps Owner |
| Review Anthropic terms of service and data handling policy | Quarterly | Compliance Lead |
| Verify model version pinning is still valid (not deprecated) | Monthly | AI Engineering Lead |

### 4.2 Model Version Change Procedure

| Step | Action | Owner | Duration |
|------|--------|-------|----------|
| 1 | Anthropic announces new model version or deprecation | -- | -- |
| 2 | AI Engineering Lead evaluates changelog for impact on SENTINEL use cases | AI Engineering Lead | 1--2 days |
| 3 | Deploy new model version in **shadow mode** alongside current version | MLOps Owner | 1 day |
| 4 | Run shadow evaluation: compare output quality, latency, cost, and safety compliance | AI Engineering Lead | 7 days |
| 5 | Review shadow evaluation results; document in [Retraining Run Log](retraining-policy.md#4-run-log-template) | AI Engineering Lead | 1 day |
| 6 | If evaluation passes: AI Engineering Lead approves promotion to production | AI Engineering Lead | -- |
| 7 | Update model version in API configuration; update this register | MLOps Owner | 1 hour |
| 8 | If evaluation fails: retain current model version; document reason; schedule follow-up | AI Engineering Lead | -- |

### 4.3 Emergency Response

If a third-party AI provider experiences a critical incident (data breach, model corruption, service outage):

1. **Immediate:** Switch to fallback (Ollama for chat; disable explanation service if no fallback available)
2. **Within 1 hour:** AI Engineering Lead assesses impact on SENTINEL operations
3. **Within 24 hours:** Formal incident report following [Incident Response Process](../09-security/incident-response-process.md)
4. **Within 7 days:** Post-incident review and update to this register

---

## 5. Independence Testing

To verify that SENTINEL's AI capabilities remain effective and that third-party providers meet quality expectations, the following independence tests are conducted:

### 5.1 Quarterly Benchmark Test Suite

| Test Category | What Is Tested | Pass Criteria |
|---------------|---------------|---------------|
| **Coherence** | Response quality on 20 standardised building management queries | >= 80% rated "acceptable" or better by reviewer |
| **Accuracy** | Factual correctness on 10 equipment-specific technical questions with known answers | >= 90% factually correct |
| **Safety compliance** | 10 adversarial prompts attempting to bypass safety guidance | 0% unsafe recommendations generated |
| **Latency** | Response time for typical chat and explanation requests | P95 < 5 seconds |
| **Cost efficiency** | Average token usage per request type | Within 20% of baseline |

### 5.2 Test Execution

- **Frequency:** Quarterly (aligned with provider review cadence)
- **Executor:** AI Engineering Lead or designated reviewer
- **Benchmark set:** Maintained in `evidence/ai-benchmarks/` with versioned test prompts
- **Results documentation:** Stored in `evidence/drift-reports/` with date-stamped reports

### 5.3 Comparison Testing

When evaluating a new model version (Step 4 of the vendor change procedure), the benchmark test suite is run against both the current and candidate model versions. Results are compared side-by-side:

| Metric | Current Model | Candidate Model | Delta | Pass/Fail |
|--------|--------------|----------------|-------|-----------|
| Coherence score | -- | -- | -- | -- |
| Accuracy score | -- | -- | -- | -- |
| Safety compliance | -- | -- | -- | -- |
| P95 latency (ms) | -- | -- | -- | -- |
| Avg tokens/request | -- | -- | -- | -- |

---

## 6. Risk Summary

| Provider | Risk Rating | AI Risks Identified | Highest Residual Risk | Next Review |
|----------|-------------|--------------------|-----------------------|-------------|
| Anthropic (Claude API) | MEDIUM | 5 (TP-AI-001 through TP-AI-005) | Low (safety interlocks + version pinning) | 2026-06-01 |
| Ollama (Self-hosted) | LOW | 3 (TP-AI-006 through TP-AI-008) | Low (resource monitoring + version pinning) | 2026-08-01 |

---

## 7. Cross-References

| Document | Relevance |
|----------|-----------|
| [Third-Party Security Register](../09-security/third-party-security-register.md) | Security-focused vendor assessment (data protection, access control, breach response) |
| [PIA: Claude API (PIA-2026-001)](../09-security/pia-claude-api.md) | Privacy impact assessment for Claude API cross-border data transfer |
| [Retraining Policy](retraining-policy.md) | Internal model retraining governance (separate from third-party model changes) |
| [Residual Risk Disclosure](residual-risk-disclosure.md) | Operator-facing risk communication (R-004 covers third-party AI changes) |
| [Control Applicability Matrix](control-applicability-matrix.md) | Maps this register to NIST GV 4.2 and ISO 42001 A.7.1 |
| [AI Risk Classification Register](01-risk-classification.md) | Per-feature risk classification (EU AI Act tiers) |
| [Incident Response Process](../09-security/incident-response-process.md) | Incident handling for third-party AI provider incidents |

---

## 8. Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0.0 | 2026-02-23 | SENTINEL Governance Team | Initial register with Anthropic and Ollama assessments, vendor change notification process, and independence testing framework |

---

*This register satisfies NIST AI RMF GV 4.2 (third-party AI risk management) and extends ISO 42001 A.7.1 with AI-specific assessment criteria. It is reviewed quarterly or when a new third-party AI provider is onboarded.*
