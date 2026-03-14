---
title: "EU AI Act Assurance Review"
version: "1.0.0"
date: "2026-02-23"
framework: "EU AI Act (Regulation (EU) 2024/1689)"
status: "completed"
review_period: "2026-01 to 2026-02"
author: "SENTINEL Governance Team"
tags: ["ai-governance", "eu-ai-act", "assurance-review", "compliance"]
---

# EU AI Act Assurance Review

**Review Period:** January -- February 2026
**Reviewer:** SENTINEL Governance Team
**Framework:** EU AI Act (Regulation (EU) 2024/1689)
**Scope:** All AI capabilities deployed in SENTINEL BMS Intelligence platform
**Risk Classification:** Limited Risk (Article 50 transparency obligations apply)

---

## Executive Summary

This review assesses SENTINEL's compliance against applicable EU AI Act articles. SENTINEL is classified as a **Limited Risk** AI system (building management optimization, not biometric, employment, or critical infrastructure classification per Article 6). The primary obligations are under Article 4 (AI Literacy), Article 5 (Prohibited Practices), and Article 50 (Transparency for limited-risk systems).

### Summary Table

| Article | Requirement | Compliance Status | Evidence Count | Gaps |
|---------|-------------|-------------------|----------------|------|
| Article 4 | AI Literacy | Partially Compliant | 3 artifacts | Training records not collected |
| Article 5 | Prohibited Practices | Compliant | 1 artifact | None |
| Article 50 | Transparency | Partially Compliant | 4 artifacts | Export watermark gap; transparency inventory follow-through |
| Articles 52/53 | Registration & Documentation | Partially Compliant | 2 artifacts | EU database registration pending |
| **Overall** | | **75% Compliant** | **10 artifacts** | **3 gaps identified** |

**Overall EU AI Act Compliance: 75% (1 Compliant, 3 Partially Compliant, 0 Non-Compliant)**

---

## Article 4: AI Literacy

### Requirement

Article 4 requires providers and deployers of AI systems to ensure a sufficient level of AI literacy of their staff and other persons dealing with the operation and use of AI systems, taking into account their technical knowledge, experience, education and training, the context the AI systems are to be used in, and the persons or groups of persons on whom the AI systems are to be used.

### Evidence Assessment

| # | Evidence Artifact | Status | Assessment |
|---|-------------------|--------|------------|
| 1 | `docs/ai-governance/ai-literacy-training-package.md` (v1.0.0) | Present | Comprehensive training package exists covering: AI fundamentals for BMS operators, SENTINEL-specific AI capabilities and limitations, confidence scores and quality gates, when to override AI recommendations, and escalation procedures. Training is role-differentiated (operator, engineer, manager, compliance). |
| 2 | `docs/ai-governance/competence-training-register.md` (v1.0.0) | Present | Register structure exists with role definitions, competence requirements per role, and assessment criteria. Follows ISO 42001 Clause 7.2 competence framework. |
| 3 | `docs/ai-governance/live-control-entry-criteria.md` (v1.0.0) | Present | Entry criteria checklist includes operator training verification as a mandatory gate before transitioning any feature to live_control mode. Operators must demonstrate understanding of AI override procedures. |

### Compliance Status: Partially Compliant

### Gaps Identified

| # | Gap | Severity | Impact |
|---|-----|----------|--------|
| G-4.1 | **Training completion records not collected.** Training package exists but no evidence of delivery to personnel. No signed attendance records, quiz scores, or competence assessments on file. | Major | Cannot demonstrate to auditor that personnel have actually received AI literacy training. Article 4 requires evidence of measures taken, not just materials prepared. |
| G-4.2 | **No refresher training schedule.** Initial training is defined but no periodic refresher cadence established. AI capabilities evolve with each release. | Minor | Operators may lack awareness of new AI features or changed behaviours after platform updates. |

### Recommended Actions

| # | Action | Owner | Due Date |
|---|--------|-------|----------|
| A-4.1 | Deliver AI literacy training to Site S002 operations team and collect signed attendance records. Store evidence in `docs/ai-governance/evidence/training/`. | Operations Lead | 2026-04-01 |
| A-4.2 | Define refresher training cadence (recommended: annually or upon major release) in training package. | Compliance Lead | 2026-03-15 |
| A-4.3 | Implement competence assessment quiz aligned with training package. Record scores in competence register. | AI Engineering Lead | 2026-04-15 |

---

## Article 5: Prohibited Practices

### Requirement

Article 5 prohibits certain AI practices including: subliminal manipulation, exploitation of vulnerabilities, social scoring, real-time remote biometric identification (with exceptions), emotion recognition in workplace/education, untargeted facial image scraping, and biometric categorisation for inferring sensitive characteristics.

### Evidence Assessment

| # | Evidence Artifact | Status | Assessment |
|---|-------------------|--------|------------|
| 1 | `docs/compliance/eu-ai-act-prohibited-practices-checklist.md` (v1.0.0, approved) | Present | Comprehensive checklist assessing every Article 5 prohibited practice against SENTINEL. Each practice evaluated with applicability determination, evidence of non-engagement, and technical controls preventing future engagement. All 8 prohibited practice categories assessed. |

### Compliance Status: Compliant

### Assessment Detail

SENTINEL is a Building Management System that optimises HVAC, lighting, and electrical equipment. It does not:

- Process biometric data of any kind
- Perform emotion recognition
- Engage in social scoring
- Target individuals for manipulation
- Perform facial recognition or image scraping
- Categorise persons by sensitive characteristics

The prohibited practices checklist documents technical controls that prevent scope creep into prohibited areas:

1. **No biometric data ingestion.** SENTINEL ingests BMS sensor data (temperature, humidity, power, airflow) only. No camera feeds, microphones, or biometric sensors connected.
2. **No individual profiling.** Occupancy data is anonymous zone-level counts only (e.g., "Zone 101: 15 occupants"), not individual identification.
3. **Equipment-only decisions.** All AI recommendations target equipment setpoints (chillers, AHUs, lighting), not people.

### Gaps Identified

None. SENTINEL's scope (building equipment management) does not intersect with any Article 5 prohibited practice.

---

## Article 50: Transparency for Limited-Risk AI Systems

### Requirement

Article 50 requires that AI systems intended to interact with natural persons are designed and developed in such a way that the natural persons concerned are informed they are interacting with an AI system, unless this is obvious from the circumstances and context of use. Content generated by AI systems must be marked in a machine-readable format as artificially generated or manipulated.

### Evidence Assessment

| # | Evidence Artifact | Status | Assessment |
|---|-------------------|--------|------------|
| 1 | `backend/app/utils/ai_provenance.py` | Present | `AIProvenance` Pydantic model provides standardised transparency metadata: `ai_generated` (bool), `model` (string), `provider` (string), `disclosure` (human-readable text), `correlation_id` (trace). Convenience constructors for Claude-generated and SENTINEL-local content. |
| 2 | Backend API endpoints (9 instrumented) | Present | AI-facing endpoints include provenance metadata in response bodies via `AIProvenance` model. HTTP headers set: `X-AI-Generated: true`, `X-AI-Model: <model>`, `X-AI-Provider: <provider>`, `X-AI-Disclosure: <text>`. Endpoints include: chat, recommendations, predictions, optimisation suggestions, energy analysis, health assessments, risk analysis, anomaly detection, work order suggestions. |
| 3 | `frontend/src/components/AIDisclosureBadge.tsx` | Present | Reusable React component with 3 variants (badge, label, footer) for marking AI-generated content in the UI. Deployed across 9 frontend components that display AI outputs. Visually distinguishable with consistent styling. |
| 4 | HTTP response headers | Present | All AI-generated responses include machine-readable headers: `X-AI-Generated`, `X-AI-Model`, `X-AI-Provider`, `X-AI-Disclosure`. These satisfy the "machine-readable format" requirement for downstream systems to detect AI content. |

### Compliance Status: Partially Compliant

### Assessment Detail

**What is working well:**

1. **Body-level provenance.** API responses for standard REST endpoints include `ai_provenance` field in the JSON body with full metadata (model, provider, disclosure text, correlation ID).
2. **Header-level provenance.** All AI responses set 4 HTTP headers enabling machine-readable detection by downstream systems, proxies, and audit tools.
3. **UI disclosure.** The `AIDisclosureBadge` component is deployed across 9 UI components. Users see clear visual indicators when viewing AI-generated content. Three variants (badge for cards, label for panels, footer for chat) provide contextually appropriate disclosure.
4. **Consistent model.** The `AIProvenance` class in `ai_provenance.py` ensures all endpoints use the same metadata structure, preventing inconsistency.

### Gaps Identified

| # | Gap | Severity | Impact |
|---|-----|----------|--------|
| G-50.1 | **No provenance on exported reports.** When AI-generated analysis is exported as PDF or CSV, the AI-generated marker is not included in the exported document. | Minor | Exported documents could circulate without AI disclosure. Low risk given current usage is internal to building operations teams. |
| G-50.2 | **Transparency inventory needs final audit packaging.** Non-streaming AI and recommendation APIs now expose body-level provenance plus runtime version metadata, and streaming chat exposes provenance in HTTP headers by design. The remaining gap is documenting those integration points in one concise audit-facing inventory. | Minor | Audit friction rather than user harm. Disclosure exists but should be easier to evidence. |

### Recommended Actions

| # | Action | Owner | Due Date |
|---|--------|-------|----------|
| A-50.1 | Include AI-generated watermark/footer in exported PDF and CSV reports. | Frontend Lead | 2026-04-15 |
| A-50.2 | Document all AI-disclosure integration points in a single transparency inventory for audit reference. | Compliance Lead | 2026-03-15 |

---

## Articles 52/53: Registration and Documentation

### Requirement

Article 52 requires registration of high-risk AI systems in the EU database before placing on the market. Article 53 requires detailed technical documentation for high-risk systems. While SENTINEL is classified as **Limited Risk** (not high-risk), registration and documentation best practices are assessed for completeness and future-readiness.

### Evidence Assessment

| # | Evidence Artifact | Status | Assessment |
|---|-------------------|--------|------------|
| 1 | `docs/compliance/eu-ai-act-compliance-register.md` (v0.2.0, approved) | Present | Internal compliance register documents: system description, risk classification rationale, applicable articles, compliance status per article, and responsible parties. Serves as the internal system of record for EU AI Act readiness. |
| 2 | `docs/ai-governance/01-risk-classification.md` (v1.0.0, approved) | Present | Risk classification completed using EU AI Act Article 6 Annex III criteria. SENTINEL assessed against all high-risk categories (biometric, critical infrastructure, employment, essential services, law enforcement, migration, democratic processes). Correctly classified as Limited Risk -- does not fall into any Annex III high-risk category. Building energy management is not listed as a high-risk domain. |

### Compliance Status: Partially Compliant

### Assessment Detail

**Classification rationale is sound:** SENTINEL manages building equipment (HVAC, lighting, electrical) and does not make decisions about natural persons. The classification as Limited Risk is defensible and well-documented.

**Documentation is thorough for current classification:** Even though high-risk documentation obligations (Article 11) do not formally apply, SENTINEL maintains documentation that would substantially satisfy high-risk requirements:
- Model cards for all 6 ML models (MP 4.1)
- Data sheets for training data provenance
- Quality management via quality gate evaluator
- Risk management via residual risk disclosure
- Human oversight via approval service and mode-based controls

### Gaps Identified

| # | Gap | Severity | Impact |
|---|-----|----------|--------|
| G-52.1 | **EU database registration not performed.** While not legally required for Limited Risk systems, best practice for transparency. If SENTINEL's classification were ever challenged, lack of registration could be a procedural gap. | Minor | Low immediate impact. Precautionary measure for regulatory credibility. |
| G-52.2 | **Compliance register at v0.2.0.** Register exists but is still in early versioning, suggesting it has not been through a full review cycle. Some fields may be incomplete. | Minor | Register should be matured to v1.0 through a dedicated review. |

### Recommended Actions

| # | Action | Owner | Due Date |
|---|--------|-------|----------|
| A-52.1 | Evaluate whether voluntary EU AI Act database registration would benefit SENTINEL's market positioning. Document decision. | Compliance Lead | 2026-05-01 |
| A-52.2 | Complete compliance register review, address any incomplete fields, and promote to v1.0.0. | Compliance Lead | 2026-03-30 |

---

## Overall Compliance Summary

### By Article

| Article | Status | Key Strength | Key Gap |
|---------|--------|-------------|---------|
| Article 4 (AI Literacy) | Partially Compliant | Training package comprehensive and role-differentiated | No delivery records; no competence assessments collected |
| Article 5 (Prohibited Practices) | Compliant | Thorough checklist; SENTINEL's scope inherently avoids prohibited practices | None |
| Article 50 (Transparency) | Partially Compliant | Backend provenance + frontend badges + HTTP headers provide layered disclosure; non-streaming APIs now include body-level provenance and runtime version metadata | Export watermark gap; transparency inventory packaging |
| Articles 52/53 (Registration) | Partially Compliant | Risk classification well-documented; internal register exists | Register still at v0.2.0; EU database registration not evaluated |

### Compliance Percentage by Article

| Article | Compliant Items | Total Items | Percentage |
|---------|----------------|-------------|------------|
| Article 4 | 3 artifacts present | 5 expected (+ delivery records, refresher schedule) | 60% |
| Article 5 | 1 artifact, all practices cleared | 1 required | 100% |
| Article 50 | 4 artifacts present, 2 gaps | 6 expected (+ export watermark, transparency inventory) | 67% |
| Articles 52/53 | 2 artifacts present | 3 expected (+ register maturity) | 67% |
| **Weighted Overall** | | | **75%** |

### Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Auditor challenge on AI literacy | Medium | Medium | Deliver training and collect records (A-4.1) |
| Third-party SSE consumer without headers | Low | Low | Add body-level provenance to SSE (A-50.1) |
| Classification challenge | Very Low | High | Maintain robust classification documentation |
| Regulatory scope expansion | Low | Medium | Monitor EU AI Act implementing guidance; re-assess classification quarterly |

---

## Next Review

- **Scheduled:** Q2 2026 (after training delivery and compliance register v1.0)
- **Focus areas:** Training delivery evidence, SSE transparency fix, compliance register maturation, monitoring of EU AI Act implementing acts and guidance

---

## Cross-References

- AI Literacy Training Package: `docs/ai-governance/ai-literacy-training-package.md`
- Competence Register: `docs/ai-governance/competence-training-register.md`
- Live-Control Entry Criteria: `docs/ai-governance/live-control-entry-criteria.md`
- Prohibited Practices Checklist: `docs/compliance/eu-ai-act-prohibited-practices-checklist.md`
- AI Provenance Utility: `backend/app/utils/ai_provenance.py`
- AI Disclosure Badge: `frontend/src/components/AIDisclosureBadge.tsx`
- EU AI Act Compliance Register: `docs/compliance/eu-ai-act-compliance-register.md`
- Risk Classification: `docs/ai-governance/01-risk-classification.md`
- Model Cards: `docs/ai-governance/model-cards/` (6 models)
- Data Sheets: `docs/ai-governance/data-sheets/`
- Quality Gate Evaluator: `backend/app/services/quality_gate_evaluator.py`
- Approval Service: `backend/app/services/approval_service.py`
- Prometheus Metrics: `backend/app/api/metrics.py`

---

## Document History

| Version | Date | Author | Change |
|---------|------|--------|--------|
| 1.0.0 | 2026-02-23 | SENTINEL Governance Team | Initial EU AI Act assurance review covering Articles 4, 5, 50, and 52/53 |
