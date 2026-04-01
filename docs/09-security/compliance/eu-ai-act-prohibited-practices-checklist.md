---
title: "EU AI Act Prohibited Practices Checklist"
type: "checklist"
status: "approved"
version: "1.0.0"
created: "2026-02-23"
updated: "2026-02-23"
author: "SENTINEL Compliance Team"
tags: ["compliance", "eu-ai-act", "prohibited-practices", "article-5", "checklist"]
domain: "compliance"
audience: "compliance, security, engineering, legal"
complexity: "intermediate"
estimated_read_time: 10
---

# EU AI Act Prohibited Practices Checklist

## 1. Purpose

This checklist assesses every prohibited AI practice defined in Article 5 of the EU AI Act (Regulation (EU) 2024/1689) against the SENTINEL BMS Intelligence platform. The assessment determines whether any SENTINEL feature engages in or could be construed as engaging in a prohibited practice.

**Regulatory reference:** Article 5, Regulation (EU) 2024/1689
**Effective date:** 2 February 2025 (prohibited practices provisions already in force)

---

## 2. Assessment Methodology

Each Article 5 prohibited practice was evaluated by:

1. Reviewing the regulatory text of the specific prohibition.
2. Mapping SENTINEL features, data flows, and AI outputs against the prohibition scope.
3. Documenting a specific justification for the NOT APPLICABLE determination.
4. Identifying any edge cases or future feature plans that could change the assessment.

---

## 3. Prohibited Practices Assessment

### 3.1 Social Scoring (Article 5(1)(c))

| Attribute | Value |
|-----------|-------|
| **Prohibition** | AI systems that evaluate or classify natural persons based on their social behaviour or personal characteristics, leading to detrimental or unfavourable treatment |
| **SENTINEL Assessment** | **NOT APPLICABLE** |
| **Justification** | SENTINEL scores equipment health, not people. The Health Rating Calculator (5-component weighted formula) evaluates mechanical and electrical equipment condition using sensor telemetry, service records, and runtime data. No personal data, social behaviour, or individual characteristics are used as inputs. No person receives a "score" from SENTINEL. |
| **Data processed** | Equipment sensor readings, maintenance logs, runtime hours, fault counts |
| **Edge cases** | None identified. Even occupancy data is zone-level aggregate (e.g., "Zone 101: 12 occupants"), never individual-level. |

### 3.2 Subliminal Manipulation (Article 5(1)(a))

| Attribute | Value |
|-----------|-------|
| **Prohibition** | AI systems that deploy subliminal techniques beyond a person's consciousness to materially distort behaviour in a manner likely to cause harm |
| **SENTINEL Assessment** | **NOT APPLICABLE** |
| **Justification** | SENTINEL provides transparent, explainable recommendations to trained building operators. All AI outputs are presented as explicit text recommendations with confidence scores, rationale, and expected outcomes. The Explanation Service uses RAG to generate clear natural-language justifications. No hidden persuasion, subliminal cues, or unconscious manipulation techniques are employed. Operators can accept, reject, or modify every recommendation. |
| **Transparency controls** | Confidence scores displayed; recommendation rationale provided; audit trail of all decisions |

### 3.3 Exploitation of Vulnerabilities (Article 5(1)(b))

| Attribute | Value |
|-----------|-------|
| **Prohibition** | AI systems that exploit vulnerabilities of specific groups of persons due to age, disability, or social/economic situation to materially distort behaviour |
| **SENTINEL Assessment** | **NOT APPLICABLE** |
| **Justification** | SENTINEL targets building equipment and systems, not vulnerable groups of people. The system's users are trained facilities management professionals and building operators. AI outputs (recommendations, predictions, health scores) relate to equipment performance and building operations. No feature targets, profiles, or exploits any characteristic of building occupants. |
| **User base** | Professional FM operators, technicians, and building managers with domain expertise |

### 3.4 Real-Time Remote Biometric Identification (Article 5(1)(d))

| Attribute | Value |
|-----------|-------|
| **Prohibition** | Real-time remote biometric identification systems in publicly accessible spaces for law enforcement purposes (with narrow exceptions) |
| **SENTINEL Assessment** | **NOT APPLICABLE** |
| **Justification** | SENTINEL does not process biometric data of any kind. The platform has no facial recognition, fingerprint scanning, voice identification, gait analysis, or any other biometric capability. The security module (CCTV/ACC equipment monitoring) tracks equipment health status only (e.g., camera uptime, access controller battery), not the content of video feeds or access logs. |
| **Biometric data processed** | None |

### 3.5 Emotion Recognition in Workplace/Education (Article 5(1)(f))

| Attribute | Value |
|-----------|-------|
| **Prohibition** | AI systems to infer emotions of natural persons in the areas of workplace and education institutions (with limited medical/safety exceptions) |
| **SENTINEL Assessment** | **NOT APPLICABLE** |
| **Justification** | SENTINEL does not infer, detect, or process human emotions in any context. Occupancy detection is zone-level aggregate headcount (e.g., "Zone 201: 8 occupants") derived from PIR/DALI occupancy sensors. No individual identification, sentiment analysis, facial expression recognition, or emotion inference is performed. The system cannot determine who is in a zone, only how many occupants are present. |
| **Occupancy data model** | Zone-level aggregate counts only; no individual tracking |

### 3.6 Predictive Policing (Article 5(1)(d) related / Article 5(1)(e))

| Attribute | Value |
|-----------|-------|
| **Prohibition** | AI systems for making risk assessments of natural persons to predict criminal offences based solely on profiling or personality traits |
| **SENTINEL Assessment** | **NOT APPLICABLE** |
| **Justification** | SENTINEL's predictive capabilities are limited to equipment failure prediction and remaining useful life (RUL) estimation. The Predictive Maintenance module predicts mechanical and electrical failures using sensor telemetry patterns. No predictions are made about human behaviour, criminal activity, or individual risk. The term "risk" in SENTINEL exclusively refers to equipment failure risk and operational risk. |
| **Prediction targets** | Equipment failure probability, remaining useful life, anomaly detection on sensor data |

### 3.7 Facial Recognition Database Scraping (Article 5(1)(e))

| Attribute | Value |
|-----------|-------|
| **Prohibition** | AI systems that create or expand facial recognition databases through untargeted scraping of facial images from the internet or CCTV footage |
| **SENTINEL Assessment** | **NOT APPLICABLE** |
| **Justification** | SENTINEL does not create, maintain, or access any facial recognition database. No facial images are collected, stored, or processed. The CCTV equipment monitoring tracks camera device health (uptime, connectivity, maintenance schedule), not video content. SENTINEL has no capability to extract, store, or match facial images from any source. |
| **Image processing** | None. CCTV module monitors camera hardware health only. |

### 3.8 Biometric Categorization (Article 5(1)(g))

| Attribute | Value |
|-----------|-------|
| **Prohibition** | AI systems for biometric categorisation that individually categorise natural persons based on biometric data to deduce or infer race, political opinions, trade union membership, religious/philosophical beliefs, sex life, or sexual orientation (with limited law enforcement exceptions) |
| **SENTINEL Assessment** | **NOT APPLICABLE** |
| **Justification** | SENTINEL processes no biometric data whatsoever. The platform manages building equipment telemetry (temperatures, pressures, voltages, vibration levels, flow rates). No personal data categories -- biometric or otherwise -- are collected, inferred, or stored. The system has no capability to categorize individuals by any characteristic. |
| **Personal data categories processed** | None. User accounts contain name, role, and contact information for platform access only. |

---

## 4. Assessment Conclusion

**SENTINEL does not engage in any prohibited practice under Article 5 of the EU AI Act.**

The platform operates exclusively in the building management and facilities maintenance domain. All AI features target equipment and building systems, not natural persons. The only human-related data processed is:

- **User accounts:** Name, role, and contact information for platform authentication and authorization
- **Technician assignments:** Name, specialty, and contact information for work order routing
- **Zone occupancy:** Aggregate headcount per zone for HVAC optimization (no individual identification)

None of these data uses fall within the scope of any Article 5 prohibition.

---

## 5. Review Trigger

This assessment must be reassessed when any of the following occurs:

| Trigger | Action Required |
|---------|-----------------|
| New AI feature added that processes personal data | Full Article 5 re-assessment |
| New AI feature added with biometric or emotion-related capabilities | Immediate compliance review before development begins |
| SENTINEL deployed in a context involving individual-level monitoring | Legal review of prohibited practices applicability |
| EU AI Act implementing regulations or guidelines published | Review against updated regulatory interpretation |
| Regulatory authority issues guidance specific to BMS/building AI | Assess applicability to SENTINEL features |
| Annual scheduled review | Confirm no scope changes; update document version |

**Next scheduled review:** 2026-08-23 (6-month cycle)

---

## 6. Sign-Off

| Role | Name | Date | Signature |
|------|------|------|-----------|
| Compliance Lead | ___________________ | ____-__-__ | ___________________ |
| Product Lead | ___________________ | ____-__-__ | ___________________ |
| AI Engineering Lead | ___________________ | ____-__-__ | ___________________ |
| Legal Reviewer | ___________________ | ____-__-__ | ___________________ |

**Document classification:** Internal -- Compliance
**Retention period:** Duration of SENTINEL operation + 5 years post-decommission

---

## 7. Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0.0 | 2026-02-23 | SENTINEL Compliance Team | Initial assessment of all 8 Article 5 prohibited practices |

---

## 8. References

- Regulation (EU) 2024/1689, Article 5: [Official text](https://eur-lex.europa.eu/eli/reg/2024/1689/oj)
- SENTINEL AI Risk Classification: [01-risk-classification.md](../ai-governance/01-risk-classification.md)
- SENTINEL EU AI Act Compliance Register: [eu-ai-act-compliance-register.md](eu-ai-act-compliance-register.md)
- SENTINEL EU AI Act Readiness Mapping: [04-eu-ai-act-readiness.md](../ai-governance/04-eu-ai-act-readiness.md)
